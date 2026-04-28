"""voxpress-prompt-lab CLI: pl run / pl diff / pl list-versions / pl list-runs。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from pl.config import CASES_DIR, PROMPTS_DIR, RUNS_DIR
from pl.diff import render_diff
from pl.runner import run_eval


app = typer.Typer(
    name="pl",
    help="VoxPress Prompt Lab — organize 阶段 prompt 调优 / eval 工作台",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


@app.command("run")
def cmd_run(
    version: str = typer.Option(..., "--version", "-v", help="prompt 版本目录名，如 v0_single / v1_multi"),
    cases: list[Path] = typer.Option(
        None,
        "--cases",
        "-c",
        help="case 文件或目录，可多次指定。默认扫 cases/ 下所有 case_*.json",
    ),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="只跑前 N 个 case"),
    concurrency: Optional[int] = typer.Option(None, "--concurrency", "-j", help="跨 case 并发数（覆盖 .env）"),
):
    """跑 eval：在指定 prompt version 下，对一批 case 跑 pipeline，结果写入 runs/<timestamp>-<version>/"""
    case_paths = list(cases or [CASES_DIR])
    run_eval(version, case_paths, limit=limit, concurrency=concurrency)


@app.command("diff")
def cmd_diff(
    a: Path = typer.Option(..., "--a", help="run A 目录（runs/<...>）"),
    b: Path = typer.Option(..., "--b", help="run B 目录（runs/<...>）"),
    out: Path = typer.Option(Path("diff.html"), "--out", "-o", help="输出 HTML 路径"),
    cases_dir: Path = typer.Option(CASES_DIR, "--cases-dir", help="case 目录（用于读 label/note）"),
):
    """生成两个 run 的 side-by-side HTML 对比"""
    if not a.exists() or not b.exists():
        console.print("[red]A 或 B 目录不存在[/red]")
        raise typer.Exit(1)
    render_diff(a, b, out=out, cases_dir=cases_dir)
    console.print(f"  在浏览器打开：[link]file://{out.resolve()}[/link]")


@app.command("list-versions")
def cmd_list_versions():
    """列出所有可用的 prompt 版本"""
    table = Table(title="Prompt versions", show_lines=False)
    table.add_column("version", style="cyan")
    table.add_column("kind")
    table.add_column("files")

    for vdir in sorted(PROMPTS_DIR.iterdir()):
        if not vdir.is_dir():
            continue
        files = [f.name for f in vdir.iterdir() if f.suffix == ".txt"]
        if "prompt.txt" in files:
            kind = "single_pass"
        elif {"outline.txt", "draft.txt", "polish.txt"}.issubset(set(files)):
            kind = "multi_pass"
        else:
            kind = "未识别"
        table.add_row(vdir.name, kind, ", ".join(sorted(files)))
    console.print(table)


@app.command("list-runs")
def cmd_list_runs(limit: int = typer.Option(15, "--limit", "-n")):
    """列出最近的 run，便于挑选两个做 diff"""
    if not RUNS_DIR.exists():
        console.print("[yellow]runs/ 不存在[/yellow]")
        return
    table = Table(title="Recent runs", show_lines=False)
    table.add_column("dir", style="cyan", no_wrap=True)
    table.add_column("version")
    table.add_column("model")
    table.add_column("cases")
    table.add_column("¥cost")
    table.add_column("tokens")

    runs = sorted(
        [d for d in RUNS_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )[:limit]
    for d in runs:
        meta_path = d / "meta.json"
        if not meta_path.exists():
            table.add_row(d.name, "—", "—", "—", "—", "—")
            continue
        try:
            m = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            table.add_row(d.name, "—", "—", "—", "—", "—")
            continue
        table.add_row(
            d.name,
            str(m.get("version", "")),
            str(m.get("model", "")),
            f"{m.get('success_count', 0)}/{m.get('case_count', 0)}",
            f"¥{m.get('total_cost_yuan', 0):.4f}",
            f"{m.get('total_tokens', 0):,}",
        )
    console.print(table)


@app.command("list-cases")
def cmd_list_cases():
    """列出所有 cases/ 下的 case 及其 label"""
    if not CASES_DIR.exists():
        console.print("[yellow]cases/ 不存在[/yellow]")
        return
    table = Table(title="Cases", show_lines=False)
    table.add_column("case_id", style="cyan")
    table.add_column("creator")
    table.add_column("label")
    table.add_column("note")
    for p in sorted(CASES_DIR.glob("case_*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            table.add_row(p.stem, "—", "—", "(JSON 解析失败)")
            continue
        table.add_row(
            d.get("case_id", p.stem),
            d.get("creator", ""),
            d.get("label", ""),
            d.get("note", "")[:80],
        )
    console.print(table)


if __name__ == "__main__":
    app()
