"""把两个 run 的输出对同一 case 渲染成 side-by-side HTML。"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console


console = Console()


@dataclass
class SideEntry:
    case_id: str
    label: str
    note: str
    a_article: str
    b_article: str
    a_meta: dict[str, Any]
    b_meta: dict[str, Any]


def _load_run(run_dir: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"找不到 meta.json：{meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    cases: dict[str, dict[str, Any]] = {}
    for p in run_dir.glob("*.json"):
        if p.name == "meta.json":
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            cases[data["case_id"]] = data
        except (json.JSONDecodeError, KeyError):
            continue
    return meta, cases


def _try_load_case_label(case_id: str, cases_dir: Path) -> tuple[str, str]:
    """从 cases/ 下读 label/note（若存在）。"""
    p = cases_dir / f"{case_id}.json"
    if not p.exists():
        return "", ""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get("label", ""), d.get("note", "")
    except json.JSONDecodeError:
        return "", ""


def render_diff(
    run_a: Path,
    run_b: Path,
    *,
    out: Path,
    cases_dir: Path,
) -> Path:
    meta_a, cases_a = _load_run(run_a)
    meta_b, cases_b = _load_run(run_b)

    common = sorted(set(cases_a.keys()) & set(cases_b.keys()))
    if not common:
        console.print("[red]两个 run 没有共同的 case_id[/red]")

    entries: list[SideEntry] = []
    for cid in common:
        label, note = _try_load_case_label(cid, cases_dir)
        entries.append(
            SideEntry(
                case_id=cid,
                label=label,
                note=note,
                a_article=cases_a[cid].get("final_article", ""),
                b_article=cases_b[cid].get("final_article", ""),
                a_meta={
                    "tokens": cases_a[cid].get("total_tokens", 0),
                    "cost": cases_a[cid].get("total_cost_yuan", 0),
                    "kind": cases_a[cid].get("pipeline_kind", ""),
                    "error": cases_a[cid].get("error", ""),
                },
                b_meta={
                    "tokens": cases_b[cid].get("total_tokens", 0),
                    "cost": cases_b[cid].get("total_cost_yuan", 0),
                    "kind": cases_b[cid].get("pipeline_kind", ""),
                    "error": cases_b[cid].get("error", ""),
                },
            )
        )

    html_str = _render_html(meta_a, meta_b, entries, run_a, run_b)
    out.write_text(html_str, encoding="utf-8")
    console.print(f"[green]✓ 已生成[/green] {out}")
    console.print(f"  共 {len(entries)} 个共同 case；A only: {len(set(cases_a)-set(cases_b))}；B only: {len(set(cases_b)-set(cases_a))}")
    return out


def _render_html(meta_a: dict, meta_b: dict, entries: list[SideEntry], run_a: Path, run_b: Path) -> str:
    rows = []
    for e in entries:
        a_html = _markdown_to_html(e.a_article)
        b_html = _markdown_to_html(e.b_article)

        label_html = ""
        if e.label or e.note:
            label_html = f"""
            <div class="label-row">
              <span class="label label-{html.escape(e.label or 'unknown')}">{html.escape(e.label or '未标')}</span>
              <span class="note">{html.escape(e.note)}</span>
            </div>"""

        a_err = f"<div class='err'>⚠ {html.escape(e.a_meta['error'])}</div>" if e.a_meta.get("error") else ""
        b_err = f"<div class='err'>⚠ {html.escape(e.b_meta['error'])}</div>" if e.b_meta.get("error") else ""

        rows.append(f"""
        <section class="case">
          <h2 class="case-id">{html.escape(e.case_id)}</h2>
          {label_html}
          <div class="grid">
            <div class="col">
              <div class="col-header">
                <div class="col-title">A · {html.escape(meta_a.get('version',''))}</div>
                <div class="col-meta">{e.a_meta['kind']} · {e.a_meta['tokens']:,} tokens · ¥{e.a_meta['cost']:.4f}</div>
              </div>
              {a_err}
              <article class="article">{a_html}</article>
            </div>
            <div class="col">
              <div class="col-header">
                <div class="col-title">B · {html.escape(meta_b.get('version',''))}</div>
                <div class="col-meta">{e.b_meta['kind']} · {e.b_meta['tokens']:,} tokens · ¥{e.b_meta['cost']:.4f}</div>
              </div>
              {b_err}
              <article class="article">{b_html}</article>
            </div>
          </div>
        </section>
        """)

    summary = _render_summary(meta_a, meta_b, run_a, run_b)

    return f"""<!doctype html>
<html lang="zh-Hans">
<head>
<meta charset="utf-8">
<title>VoxPress Prompt Lab — Diff</title>
<style>
:root {{
  --bg: #fafafa;
  --panel: #ffffff;
  --border: #e5e7eb;
  --muted: #6b7280;
  --accent: #2563eb;
  --good: #10b981;
  --mid: #f59e0b;
  --bad: #ef4444;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: #111827; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; line-height: 1.7; }}
header.top {{ background: #0f172a; color: #fff; padding: 16px 24px; }}
header.top h1 {{ margin: 0 0 4px; font-size: 18px; font-weight: 600; }}
header.top .sub {{ font-size: 13px; opacity: 0.7; }}
.summary {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 20px 24px; background: var(--panel); border-bottom: 1px solid var(--border); }}
.summary .panel {{ border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; }}
.summary .panel h3 {{ margin: 0 0 8px; font-size: 14px; }}
.summary .panel dl {{ margin: 0; display: grid; grid-template-columns: max-content 1fr; gap: 4px 12px; font-size: 13px; }}
.summary .panel dt {{ color: var(--muted); }}
.summary .panel dd {{ margin: 0; }}
.cases {{ padding: 20px 24px; }}
.case {{ background: var(--panel); border: 1px solid var(--border); border-radius: 10px; margin-bottom: 24px; overflow: hidden; }}
.case-id {{ margin: 0; padding: 14px 20px; background: #f3f4f6; font-size: 15px; font-weight: 600; border-bottom: 1px solid var(--border); }}
.label-row {{ padding: 8px 20px; background: #fffbea; border-bottom: 1px solid var(--border); font-size: 13px; }}
.label {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-right: 8px; color: #fff; }}
.label-优 {{ background: var(--good); }}
.label-中 {{ background: var(--mid); }}
.label-差 {{ background: var(--bad); }}
.label-未标, .label-unknown {{ background: var(--muted); }}
.note {{ color: var(--muted); }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; }}
.col {{ padding: 16px 20px; border-right: 1px solid var(--border); }}
.col:last-child {{ border-right: none; }}
.col-header {{ margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }}
.col-title {{ font-weight: 600; font-size: 14px; color: var(--accent); }}
.col-meta {{ font-size: 12px; color: var(--muted); margin-top: 2px; }}
.article {{ font-size: 15px; }}
.article h1, .article h2, .article h3 {{ font-weight: 600; margin: 16px 0 8px; }}
.article h1 {{ font-size: 20px; }}
.article h2 {{ font-size: 17px; }}
.article h3 {{ font-size: 15px; color: var(--muted); }}
.article p {{ margin: 0 0 12px; }}
.article ul, .article ol {{ padding-left: 24px; margin: 8px 0 12px; }}
.article code {{ background: #f3f4f6; padding: 1px 6px; border-radius: 3px; font-size: 13px; }}
.err {{ background: #fee2e2; color: #991b1b; padding: 8px 12px; border-radius: 6px; font-size: 13px; margin-bottom: 12px; }}
@media (max-width: 1100px) {{
  .grid {{ grid-template-columns: 1fr; }}
  .col {{ border-right: none; border-bottom: 1px solid var(--border); }}
  .summary {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<header class="top">
  <h1>VoxPress Prompt Lab — Diff</h1>
  <div class="sub">A: {html.escape(str(run_a))} &nbsp;·&nbsp; B: {html.escape(str(run_b))}</div>
</header>
{summary}
<div class="cases">
{''.join(rows)}
</div>
</body>
</html>"""


def _render_summary(meta_a: dict, meta_b: dict, run_a: Path, run_b: Path) -> str:
    def panel(title: str, m: dict) -> str:
        return f"""
        <div class="panel">
          <h3>{html.escape(title)}</h3>
          <dl>
            <dt>version</dt><dd>{html.escape(str(m.get('version','')))}</dd>
            <dt>model</dt><dd>{html.escape(str(m.get('model','')))}</dd>
            <dt>temperature</dt><dd>{m.get('temperature','')}</dd>
            <dt>cases</dt><dd>{m.get('success_count',0)}/{m.get('case_count',0)} 成功</dd>
            <dt>tokens</dt><dd>{m.get('total_tokens',0):,}</dd>
            <dt>成本</dt><dd>¥{m.get('total_cost_yuan',0):.4f}</dd>
            <dt>耗时</dt><dd>{m.get('elapsed_sec',0):.1f}s</dd>
          </dl>
        </div>"""
    return f"""
    <div class="summary">
      {panel("A · " + str(run_a.name), meta_a)}
      {panel("B · " + str(run_b.name), meta_b)}
    </div>"""


def _markdown_to_html(text: str) -> str:
    """极简 markdown → html（不引第三方依赖以保持 lab 项目轻量）。"""
    if not text:
        return "<p class='muted'>（无输出）</p>"
    out_lines: list[str] = []
    in_list = False
    for raw in text.split("\n"):
        line = raw.rstrip()
        if not line:
            if in_list:
                out_lines.append("</ul>")
                in_list = False
            out_lines.append("")
            continue
        if line.startswith("### "):
            if in_list:
                out_lines.append("</ul>"); in_list = False
            out_lines.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            if in_list:
                out_lines.append("</ul>"); in_list = False
            out_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            if in_list:
                out_lines.append("</ul>"); in_list = False
            out_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith(("- ", "* ")):
            if not in_list:
                out_lines.append("<ul>"); in_list = True
            out_lines.append(f"<li>{html.escape(line[2:])}</li>")
        else:
            if in_list:
                out_lines.append("</ul>"); in_list = False
            out_lines.append(f"<p>{html.escape(line)}</p>")
    if in_list:
        out_lines.append("</ul>")
    return "\n".join(out_lines)
