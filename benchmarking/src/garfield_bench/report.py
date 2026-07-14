from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .aggregate import aggregate_runs


def write_reports(
    runs_root: Path, output_root: Path, factory_authoring_tokens: int | None = None
) -> dict[str, Any]:
    report = aggregate_runs(runs_root, factory_authoring_tokens)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    markdown = _markdown(report)
    (output_root / "report.md").write_text(markdown)
    (output_root / "report.html").write_text(_html(report, markdown))
    return report


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Garfield benchmark",
        "",
        f"Completed runs: {report['run_count']}",
        "",
        "| Case | Treatment | Success | Raw tree tokens | Uncached input | Cached input | Output | Coordinator | Delegated | Agents | Wall ms |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for group in report["groups"]:
        lines.append(
            "| {case_id} | {treatment} | {successes}/{runs} | {tree} | {uncached} | {cached} | {output} | {coord} | {delegated} | {agents} | {wall} |".format(
                **group,
                tree=_display(group["median_total_agent_tree_tokens"]),
                uncached=_display(group["median_uncached_input_tokens"]),
                cached=_display(group["median_cached_input_tokens"]),
                output=_display(group["median_output_tokens"]),
                coord=_display(group["median_coordinator_tokens"]),
                delegated=_display(group["median_delegated_tokens"]),
                agents=_display(group["median_agent_count"]),
                wall=_display(group["median_wall_clock_ms"]),
            )
        )
    lines.extend(["", "## Amortization", ""])
    if report["amortization"]:
        lines.extend(
            [
                "| Work items | Garfield tokens | Swamp-Garfield tokens |",
                "|---:|---:|---:|",
            ]
        )
        for row in report["amortization"]:
            lines.append(
                f"| {row['work_items']} | {_display(row['garfield_tokens'])} | {_display(row['swamp_garfield_tokens'])} |"
            )
    else:
        lines.append("Insufficient paired data for amortization.")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    return "\n".join(lines) + "\n"


def _html(report: dict[str, Any], markdown: str) -> str:
    payload = html.escape(json.dumps(report, indent=2, sort_keys=True))
    bars = _token_bars(report)
    amortization = _amortization_chart(report)
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Garfield benchmark</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}}pre{{white-space:pre-wrap;background:#f5f5f5;padding:1rem}}table{{border-collapse:collapse}}th,td{{border:1px solid #bbb;padding:.4rem}}.bar-row{{display:grid;grid-template-columns:280px 1fr 110px;gap:.6rem;margin:.5rem 0}}.bar{{background:#d85f45;height:1.2rem}}svg{{max-width:100%;height:auto;border:1px solid #ddd}}</style></head>
<body><h1>Garfield benchmark</h1>
<p>Machine-readable data is embedded below. The Markdown report is available beside this page.</p>
<h2>Median complete agent-tree tokens</h2>{bars}
<h2>Cumulative and amortized tokens</h2>{amortization}
<h2>Report data</h2><pre>{payload}</pre>
<h2>Markdown</h2><pre>{html.escape(markdown)}</pre></body></html>
"""


def _display(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _token_bars(report: dict[str, Any]) -> str:
    groups = [group for group in report["groups"] if group["median_total_agent_tree_tokens"] is not None]
    if not groups:
        return "<p>No completed token data.</p>"
    maximum = max(float(group["median_total_agent_tree_tokens"]) for group in groups) or 1.0
    rows = []
    for group in groups:
        value = float(group["median_total_agent_tree_tokens"])
        width = 100 * value / maximum
        label = html.escape(f"{group['case_id']} · {group['treatment']}")
        rows.append(
            f'<div class="bar-row"><span>{label}</span><span><span class="bar" style="display:block;width:{width:.2f}%"></span></span><strong>{_display(value)}</strong></div>'
        )
    return "".join(rows)


def _amortization_chart(report: dict[str, Any]) -> str:
    rows = [row for row in report["amortization"] if row["swamp_garfield_tokens"] is not None]
    if not rows:
        return "<p>Provide factory authoring tokens and paired run data to render amortization.</p>"
    width, height, margin = 720, 280, 45
    maximum = max(max(float(row["garfield_tokens"]), float(row["swamp_garfield_tokens"])) for row in rows) or 1.0

    def points(field: str) -> str:
        result = []
        for index, row in enumerate(rows):
            x = margin + index * (width - 2 * margin) / max(1, len(rows) - 1)
            y = height - margin - float(row[field]) * (height - 2 * margin) / maximum
            result.append(f"{x:.1f},{y:.1f}")
        return " ".join(result)

    labels = []
    for index, row in enumerate(rows):
        x = margin + index * (width - 2 * margin) / max(1, len(rows) - 1)
        labels.append(f'<text x="{x:.1f}" y="{height - 12}" text-anchor="middle">{row["work_items"]}</text>')
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Cumulative token comparison">'
        f'<line x1="{margin}" y1="{height - margin}" x2="{width - margin}" y2="{height - margin}" stroke="#555"/>'
        f'<polyline points="{points("garfield_tokens")}" fill="none" stroke="#d85f45" stroke-width="4"/>'
        f'<polyline points="{points("swamp_garfield_tokens")}" fill="none" stroke="#3d7399" stroke-width="4"/>'
        + "".join(labels)
        + '<text x="55" y="25" fill="#d85f45">Garfield</text><text x="145" y="25" fill="#3d7399">Swamp-Garfield</text>'
        + f'<text x="{width / 2}" y="{height - 1}" text-anchor="middle">work items</text></svg>'
    )
