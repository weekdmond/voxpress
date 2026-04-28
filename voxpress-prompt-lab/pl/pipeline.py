"""Pipeline 执行器：single_pass / multi_pass。

- single_pass：一次 LLM call，对应 voxpress 当前线上 organize 阶段的 baseline
- multi_pass：三次 LLM call，outline → draft → polish，每步独立 prompt 文件

每个版本的 prompt 放在 pl/prompts/<version>/ 下，按文件名匹配 pipeline 类型：
- 含 prompt.txt → single_pass
- 含 outline.txt + draft.txt + polish.txt → multi_pass
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Any

from pl.config import PROMPTS_DIR, Settings
from pl.llm import CallSpec, LLMClient, LLMResult, parse_json_safe
from pl.preprocess import clean_transcript


@dataclass
class CaseInput:
    case_id: str
    transcript: str
    title_hint: str = ""
    creator: str = ""
    duration_sec: int | None = None
    label: str = ""  # 用户标的"优/中/差"
    note: str = ""   # 用户说"为什么这样标"


@dataclass
class StageOutput:
    """单个 LLM 调用的结果（pipeline 内一个 stage）。"""
    stage: str
    prompt_path: str
    content: str
    parsed: Any = None  # JSON 解析后；若解析失败则为 None
    llm: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineRun:
    case_id: str
    version: str
    pipeline_kind: str           # "single_pass" | "multi_pass"
    final_article: str           # 最终输出（markdown 或纯文本）
    stages: list[StageOutput] = field(default_factory=list)
    total_cost_yuan: float = 0.0
    total_tokens: int = 0
    total_latency_ms: int = 0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "version": self.version,
            "pipeline_kind": self.pipeline_kind,
            "final_article": self.final_article,
            "total_cost_yuan": round(self.total_cost_yuan, 6),
            "total_tokens": self.total_tokens,
            "total_latency_ms": self.total_latency_ms,
            "error": self.error,
            "stages": [
                {
                    "stage": s.stage,
                    "prompt_path": s.prompt_path,
                    "content": s.content,
                    "parsed": s.parsed,
                    "llm": s.llm,
                }
                for s in self.stages
            ],
        }


# ---- prompt loading ----

def load_prompt(version: str, name: str) -> tuple[str, Path]:
    path = PROMPTS_DIR / version / name
    if not path.exists():
        raise FileNotFoundError(f"prompt 文件不存在：{path}")
    return path.read_text(encoding="utf-8"), path


def detect_pipeline_kind(version: str) -> str:
    vdir = PROMPTS_DIR / version
    if not vdir.exists():
        raise FileNotFoundError(
            f"prompt 版本目录不存在：{vdir}。可用版本：{[p.name for p in PROMPTS_DIR.iterdir() if p.is_dir()]}"
        )
    if (vdir / "prompt.txt").exists():
        return "single_pass"
    if all((vdir / f).exists() for f in ("outline.txt", "draft.txt", "polish.txt")):
        return "multi_pass"
    raise ValueError(
        f"{vdir} 既不像 single_pass（缺 prompt.txt），也不像 multi_pass（缺 outline/draft/polish.txt）"
    )


def render_prompt(template_text: str, **vars: Any) -> str:
    """支持 {{var}} 风格的简单模板替换。"""
    out = template_text
    for k, v in vars.items():
        if isinstance(v, (dict, list)):
            v_str = json.dumps(v, ensure_ascii=False, indent=2)
        else:
            v_str = str(v) if v is not None else ""
        out = out.replace("{{" + k + "}}", v_str)
    return out


# ---- pipeline runners ----

def run_single_pass(
    case: CaseInput,
    version: str,
    settings: Settings,
    client: LLMClient,
) -> PipelineRun:
    prompt_text, prompt_path = load_prompt(version, "prompt.txt")
    transcript = clean_transcript(case.transcript)
    user = render_prompt(
        prompt_text,
        transcript=transcript,
        title_hint=case.title_hint or "",
        creator=case.creator or "",
    )

    spec = CallSpec(
        model=settings.default_model,
        system="你是一位资深中文编辑，擅长把视频口播转成可读、可保留的文章。",
        user=user,
        temperature=settings.default_temperature,
        max_tokens=settings.default_max_tokens,
    )
    result = client.call(spec)

    stage = StageOutput(
        stage="single_pass",
        prompt_path=str(prompt_path.relative_to(PROMPTS_DIR.parent.parent)),
        content=result.content,
        parsed=parse_json_safe(result.content),
        llm=result.to_dict(),
    )

    return PipelineRun(
        case_id=case.case_id,
        version=version,
        pipeline_kind="single_pass",
        final_article=result.content,
        stages=[stage],
        total_cost_yuan=result.cost_yuan,
        total_tokens=result.total_tokens,
        total_latency_ms=result.latency_ms,
    )


def run_multi_pass(
    case: CaseInput,
    version: str,
    settings: Settings,
    client: LLMClient,
) -> PipelineRun:
    transcript = clean_transcript(case.transcript)

    stages: list[StageOutput] = []
    total_cost = 0.0
    total_tokens = 0
    total_latency = 0

    # ---- Stage 1: outline ----
    outline_text, outline_path = load_prompt(version, "outline.txt")
    outline_user = render_prompt(
        outline_text,
        transcript=transcript,
        title_hint=case.title_hint or "",
        creator=case.creator or "",
    )
    outline_result = client.call(
        CallSpec(
            model=settings.default_model,
            system="你是一位资深中文编辑。下面会给你一段视频口播转写，你的任务是先做结构化分析，输出 JSON 大纲。",
            user=outline_user,
            temperature=settings.default_temperature,
            max_tokens=settings.default_max_tokens,
            json_mode=True,
        )
    )
    outline_parsed = parse_json_safe(outline_result.content)
    stages.append(
        StageOutput(
            stage="outline",
            prompt_path=str(outline_path.relative_to(PROMPTS_DIR.parent.parent)),
            content=outline_result.content,
            parsed=outline_parsed,
            llm=outline_result.to_dict(),
        )
    )
    total_cost += outline_result.cost_yuan
    total_tokens += outline_result.total_tokens
    total_latency += outline_result.latency_ms

    if outline_parsed is None:
        return PipelineRun(
            case_id=case.case_id,
            version=version,
            pipeline_kind="multi_pass",
            final_article="",
            stages=stages,
            total_cost_yuan=total_cost,
            total_tokens=total_tokens,
            total_latency_ms=total_latency,
            error="outline 阶段返回的不是合法 JSON，pipeline 中止",
        )

    # ---- Stage 2: draft ----
    draft_text, draft_path = load_prompt(version, "draft.txt")
    draft_user = render_prompt(
        draft_text,
        transcript=transcript,
        outline_json=outline_parsed,
        creator=case.creator or "",
    )
    draft_result = client.call(
        CallSpec(
            model=settings.default_model,
            system="你是一位资深中文编辑。下面会给你大纲和原始转写，你按大纲扩写一篇草稿，输出 JSON。",
            user=draft_user,
            temperature=settings.default_temperature,
            max_tokens=settings.default_max_tokens,
            json_mode=True,
        )
    )
    draft_parsed = parse_json_safe(draft_result.content)
    stages.append(
        StageOutput(
            stage="draft",
            prompt_path=str(draft_path.relative_to(PROMPTS_DIR.parent.parent)),
            content=draft_result.content,
            parsed=draft_parsed,
            llm=draft_result.to_dict(),
        )
    )
    total_cost += draft_result.cost_yuan
    total_tokens += draft_result.total_tokens
    total_latency += draft_result.latency_ms

    if draft_parsed is None:
        return PipelineRun(
            case_id=case.case_id,
            version=version,
            pipeline_kind="multi_pass",
            final_article="",
            stages=stages,
            total_cost_yuan=total_cost,
            total_tokens=total_tokens,
            total_latency_ms=total_latency,
            error="draft 阶段返回的不是合法 JSON，pipeline 中止",
        )

    # ---- Stage 3: polish ----
    polish_text, polish_path = load_prompt(version, "polish.txt")
    polish_user = render_prompt(
        polish_text,
        draft_json=draft_parsed,
    )
    polish_result = client.call(
        CallSpec(
            model=settings.default_model,
            system="你是一位资深中文编辑。下面会给你一篇文章草稿，做最后一轮 polish 并以 JSON 返回。",
            user=polish_user,
            temperature=settings.default_temperature,
            max_tokens=settings.default_max_tokens,
            json_mode=True,
        )
    )
    polish_parsed = parse_json_safe(polish_result.content)
    stages.append(
        StageOutput(
            stage="polish",
            prompt_path=str(polish_path.relative_to(PROMPTS_DIR.parent.parent)),
            content=polish_result.content,
            parsed=polish_parsed,
            llm=polish_result.to_dict(),
        )
    )
    total_cost += polish_result.cost_yuan
    total_tokens += polish_result.total_tokens
    total_latency += polish_result.latency_ms

    final_article = ""
    if polish_parsed and isinstance(polish_parsed, dict):
        final_article = (
            polish_parsed.get("正文_markdown")
            or polish_parsed.get("article_markdown")
            or polish_result.content
        )
    else:
        final_article = polish_result.content

    return PipelineRun(
        case_id=case.case_id,
        version=version,
        pipeline_kind="multi_pass",
        final_article=final_article,
        stages=stages,
        total_cost_yuan=total_cost,
        total_tokens=total_tokens,
        total_latency_ms=total_latency,
    )


def run_pipeline(
    case: CaseInput,
    version: str,
    settings: Settings,
    client: LLMClient,
) -> PipelineRun:
    kind = detect_pipeline_kind(version)
    if kind == "single_pass":
        return run_single_pass(case, version, settings, client)
    if kind == "multi_pass":
        return run_multi_pass(case, version, settings, client)
    raise ValueError(f"未知 pipeline kind: {kind}")
