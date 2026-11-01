"""Markdown/JSON reports: source data quality and validation results."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def _md_escape(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def write_reports(ctx, result, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    d = ctx.dictionary
    snap = ctx.snapshot
    paths = []

    # ---- data quality
    issues = sorted(d.issues, key=lambda i: (SEVERITY_ORDER[i.severity], i.category, i.group or "",
                                              i.heading or "", i.code or ""))
    lines = [f"# AGS {d.version} source data quality", "",
             f"Source: {snap.origin}" + (f" (commit `{snap.commit[:12]}`" if snap.commit else "")
             + (f", {snap.committed_date[:10]})" if snap.committed_date else ")" if snap.commit else ""),
             "", "Files: " + ", ".join(f"`{f}`" for f in sorted({f for fs in d.sources.values() for f in fs})),
             "", "| Groups | Headings (occurrences) | Unique headings | Abbreviations | Units | Data types | "
             "Contaminant codes | Rules |", "|---|---|---|---|---|---|---|---|",
             f"| {len(d.groups)} | {len(d.headings())} | {len(d.heading_occurrences())} | "
             f"{sum(len(v) for v in d.abbreviations.values())} | {len(d.units)} | {len(d.data_types)} | "
             f"{len(d.contaminant_codes)} | {len(d.rules)} |", "",
             "Findings are about the JSON as published; nothing has been changed to \"fix\" them.", ""]
    counts = Counter((i.severity, i.category) for i in issues)
    lines += ["## Summary", "", "| Severity | Category | Count |", "|---|---|---|"]
    lines += [f"| {s} | {c} | {n} |" for (s, c), n in sorted(counts.items(),
                                                          key=lambda kv: (SEVERITY_ORDER[kv[0][0]], kv[0][1]))]
    by_cat = defaultdict(list)
    for i in issues:
        by_cat[(i.severity, i.category)].append(i)
    for (sev, cat), items in by_cat.items():
        lines += ["", f"## {sev}: {cat} ({len(items)})", "", "| Group | Heading | Code | Message |",
                  "|---|---|---|---|"]
        lines += [f"| {i.group or ''} | {i.heading or ''} | {_md_escape(i.code or '')} | {_md_escape(i.message)} |"
                  for i in items]

    examples = next((r for r in result.results if r.check == "examples vs shapes"), None)
    if examples is not None:
        lines += ["", "## Dictionary examples validated against the shapes", "",
                  "Each group's example values were turned into one synthetic record and validated "
                  "against the generated shapes. Findings point at examples that do not match their own "
                  "suggested data type, or key examples that differ between parent and child groups.", "",
                  f"{examples.violations} violations, {examples.warnings} warnings.", ""]
        lines += [f"- {_md_escape(x)}" for x in examples.details]
    p = out / "data-quality.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    paths.append(p)
    p = out / "issues.json"
    p.write_text(json.dumps([asdict(i) for i in issues], indent=1) + "\n", encoding="utf-8", newline="\n")
    paths.append(p)

    # ---- validation
    if result.results:
        lines = [f"# AGS {d.version} validation", "", "| Result | Check | Target | Violations | Warnings |",
                 "|---|---|---|---|---|"]
        for r in result.results:
            state = "info" if r.check == "examples vs shapes" else ("pass" if r.conforms else "**FAIL**")
            lines.append(f"| {state} | {r.check} | {r.target} | {r.violations} | {r.warnings} |")
        for r in result.results:
            if r.details and r.check != "examples vs shapes":
                lines += ["", f"## {r.check} - {r.target}", ""] + [f"- {_md_escape(x)}" for x in r.details]
        p = out / "validation.md"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        paths.append(p)
    return paths
