"""跑 Eval：cases × version → runs/<timestamp>-<version>/。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from pl.config import CASES_DIR, RUNS_DIR, Settings, load_settings
from pl.llm import LLMClient
from pl.pipeline import CaseInput, PipelineRun, run_pipeline


console = Console()


def load_cases(case_paths: list[Path]) -> list[CaseInput]:
    cases: list[CaseInput] = []
    for p in case_paths:
        if p.is_dir():
            cases.extend(load_cases(sorted(p.glob("case_*.json"))))
            continue
        if not p.exists():
            console.print(f"[red]case 文件不存在: {p}[/red]")
            continue
        if p.name.startswith("_"):  # 跳过 _template.json 等
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            console.print(f"[red]case JSON 解析失败 {p}: {e}[/red]")
            continue
        cases.append(
            CaseInput(
                case_id=data.get("case_id") or p.stem,
                transcript=data["transcript"],
                title_hint=data.get("title_hint", ""),
                creator=data.get("creator", ""),
                duration_sec=data.get("duration_sec"),
                label=data.get("label", ""),
                note=data.get("note", ""),
            )
        )
    return cases


def _git_hash() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return ""


def _make_run_dir(version: str) -> Path:
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y%m%dT%H%M%S")
    safe = version.replace("/", "_")
    d = RUNS_DIR / f"{ts}-{safe}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run_one(
    case: CaseInput,
    version: str,
    settings: Settings,
    client: LLMClient,
    run_dir: Path,
) -> tuple[str, PipelineRun | None, str]:
    try:
        run = run_pipeline(case, version, settings, client)
    except Exception as e:
        tb = traceback.format_exc()
        console.print(f"[red]case {case.case_id} 抛错: {e}[/red]")
        return case.case_id, None, tb

    out_path = run_dir / f"{case.case_id}.json"
    out_path.write_text(
        json.dumps(run.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md_path = run_dir / f"{case.case_id}.md"
    md_path.write_text(run.final_article, encoding="utf-8")

    return case.case_id, run, ""


def run_eval(
    version: str,
    case_paths: list[Path],
    *,
    limit: int | None = None,
    concurrency: int | None = None,
) -> Path:
    settings = load_settings()
    client = LLMClient(settings)

    cases = load_cases(case_paths)
    if limit:
        cases = cases[:limit]
    if not cases:
        console.print("[yellow]没有找到任何 case，请先在 cases/ 下创建 case_*.json[/yellow]")
        sys.exit(1)

    run_dir = _make_run_dir(version)
    console.print(f"[bold cyan]Run dir:[/bold cyan] {run_dir}")
    console.print(f"[bold cyan]Version:[/bold cyan] {version}")
    console.print(f"[bold cyan]Cases:[/bold cyan] {len(cases)}")
    console.print(f"[bold cyan]Model:[/bold cyan] {settings.default_model}")
    console.print(f"[bold cyan]Temperature:[/bold cyan] {settings.default_temperature}")
    console.print()

    cc = concurrency or settings.concurrency

    runs: list[PipelineRun] = []
    failures: dict[str, str] = {}
    t_start = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("[cyan]running...", total=len(cases))

        with ThreadPoolExecutor(max_workers=cc) as pool:
            futures = {
                pool.submit(_run_one, c, version, settings, client, run_dir): c
                for c in cases
            }
            for fut in as_completed(futures):
                case_id, run, err = fut.result()
                if run is not None:
                    runs.append(run)
                if err:
                    failures[case_id] = err
                progress.advance(task_id)

    elapsed = time.time() - t_start
    total_cost = sum(r.total_cost_yuan for r in runs)
    total_tokens = sum(r.total_tokens for r in runs)

    meta = {
        "version": version,
        "started_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "model": settings.default_model,
        "temperature": settings.default_temperature,
        "max_tokens": settings.default_max_tokens,
        "git_hash": _git_hash(),
        "case_count": len(cases),
        "success_count": len(runs),
        "failure_count": len(failures),
        "total_tokens": total_tokens,
        "total_cost_yuan": round(total_cost, 6),
        "elapsed_sec": round(elapsed, 2),
        "failures": failures,
    }
    (run_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    console.print()
    console.print(f"[bold green]✓ 完成[/bold green]  成功 {len(runs)}/{len(cases)}  耗时 {elapsed:.1f}s")
    console.print(f"  总 tokens: {total_tokens:,}  总成本: ¥{total_cost:.4f}  均价: ¥{(total_cost/max(1,len(runs))):.4f}/篇")
    if failures:
        console.print(f"  [red]失败 case：{', '.join(failures.keys())}[/red]")
    console.print(f"  产物目录: [link]{run_dir}[/link]")

    return run_dir
