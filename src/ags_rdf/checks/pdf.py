"""Cross-check the JSON dictionary against the published AGS dictionary PDF.

The only dictionary PDF in the ASG4 repository is ``AGS4/downloads/AGS_4_0_4.pdf``
(AGS 4.0.4, February 2017), so by default release 4.0.4 is compared. The group
tables ("Group Name: LOCA - Location Details" followed by Status / Heading /
Suggested Unit / Type / Description / Example rows) are extracted with
pdfplumber and compared field by field with the JSON.

The JSON remains the authoritative source; this check only reports where the
two publications disagree.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from ..loader import load_dictionary
from ..releases import Release
from ..sources import Snapshot

GROUP_TITLE = re.compile(r"Group Name:\s*([A-Z0-9]{4})\s*[-–]\s*(.+)", re.S)
HEADING = re.compile(r"^[A-Z0-9]{2,4}_[A-Z0-9_]+$")
FIELDS = ("status", "unit", "data_type", "description", "example")


@dataclass
class PdfHeading:
    group: str
    code: str
    order: int
    status: str
    unit: str
    data_type: str
    description: str
    example: str
    page: int


@dataclass
class Difference:
    group: str
    heading: str | None
    field: str
    json_value: str
    pdf_value: str
    page: int | None = None


@dataclass
class PdfReport:
    version: str
    pdf: str
    json_file: str
    other_label: str = "PDF"
    groups_json: int = 0
    groups_pdf: int = 0
    headings_json: int = 0
    headings_pdf: int = 0
    differences: list[Difference] = field(default_factory=list)

    def by_field(self) -> dict[str, list[Difference]]:
        out: dict[str, list[Difference]] = {}
        for d in self.differences:
            out.setdefault(d.field, []).append(d)
        return out

    def summary(self) -> str:
        parts = [f"{k}: {len(v)}" for k, v in self.by_field().items()]
        return (f"AGS {self.version}: JSON {self.groups_json} groups / {self.headings_json} headings; {self.other_label} "
                f"{self.groups_pdf} groups / {self.headings_pdf} headings. Differences - "
                + (", ".join(parts) if parts else "none"))

    def to_markdown(self) -> str:
        esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")  # noqa: E731
        o = self.other_label
        lines = [f"# AGS {self.version}: JSON vs {o}", "",
                 f"- JSON: `{self.json_file}`", f"- {o}: `{self.pdf}`", "",
                 f"| | JSON | {o} |", "|---|---|---|",
                 f"| Groups | {self.groups_json} | {self.groups_pdf} |",
                 f"| Headings (occurrences) | {self.headings_json} | {self.headings_pdf} |", "",
                 "Comparison after normalising whitespace, line-break hyphenation, quotes and dashes. "
                 "The JSON is the authoritative source; \"other\" below means the " + o + ".", "",
                 "| Field | Differences |", "|---|---|"]
        lines += [f"| {k} | {len(v)} |" for k, v in self.by_field().items()]
        for f, diffs in self.by_field().items():
            lines += ["", f"## {f} ({len(diffs)})", "", f"| Group | Heading | JSON | {o} | Page/line |",
                      "|---|---|---|---|---|"]
            lines += [f"| {d.group} | {d.heading or ''} | {esc(d.json_value)} | {esc(d.pdf_value)} | "
                      f"{d.page or ''} |" for d in diffs]
        return "\n".join(lines) + "\n"


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2013", "-").replace("\u2014", "-").replace("\u00b5", "u")
    s = re.sub(r"-\s*\n\s*", "-", s)  # hyphenated line breaks: "yyyy-\nmm-dd"
    return re.sub(r"\s+", " ", s).strip()


def extract_pdf(pdf_path: Path) -> tuple[dict[str, str], list[PdfHeading]]:
    """(group code -> title, heading rows) from the dictionary tables of an AGS PDF."""
    import pdfplumber

    groups: dict[str, str] = {}
    rows: list[PdfHeading] = []
    order: dict[str, int] = {}
    group = None  # carried over to continuation pages, which repeat no "Group Name" row
    with pdfplumber.open(str(pdf_path)) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if "Group Name:" not in text and group is None:
                continue
            tables = page.extract_tables()
            if not tables:
                group = None  # left the dictionary section
            for table in tables:
                for raw in table:
                    cells = [c for c in raw if c is not None]
                    joined = " ".join(c for c in cells if c)
                    m = GROUP_TITLE.search(joined)
                    if m:
                        group = m.group(1)
                        groups.setdefault(group, _norm(m.group(2)))
                        continue
                    if group is None or len(cells) < 6:
                        continue
                    status, code, unit, dtype, desc, example = (cells[0], cells[1], cells[2], cells[3],
                                                                cells[4], " ".join(c for c in cells[5:] if c))
                    code = _norm(code)
                    if not code and rows and rows[-1].group == group and (desc or example):
                        # a row split over a page break: append to the previous heading
                        last = rows[-1]
                        last.description = _norm(f"{last.description} {desc or ''}")
                        last.example = _norm(f"{last.example} {example or ''}")
                        continue
                    if not HEADING.match(code):
                        continue
                    order[group] = order.get(group, 0) + 1
                    rows.append(PdfHeading(group, code, order[group], _norm(status), _norm(unit),
                                           _norm(dtype), _norm(desc), _norm(example), pno))
    return groups, rows


def compare_pdf(snapshot: Snapshot, release: Release, pdf_path: Path, label: str | None = None) -> PdfReport:
    d = load_dictionary(snapshot, release)
    groups_pdf, rows = extract_pdf(pdf_path)
    rep = PdfReport(release.version, label or str(pdf_path), snapshot.url_for(release.groups_and_headings))
    compare_tables(d, groups_pdf, rows, rep)
    return rep


def compare_tables(d, other_groups: dict[str, str], rows: list[PdfHeading], rep: PdfReport) -> PdfReport:
    """Compare a loaded dictionary with group titles + heading rows from another publication."""
    rep.groups_json, rep.groups_pdf, rep.headings_json = len(d.groups), len(other_groups), len(d.headings())
    pdf_index: dict[tuple[str, str], PdfHeading] = {}
    for r in rows:
        pdf_index.setdefault((r.group, r.code), r)  # tables repeat on continuation pages
    rep.headings_pdf = len(pdf_index)

    for code in sorted(set(d.groups) - set(other_groups)):
        rep.differences.append(Difference(code, None, "group missing from other", code, ""))
    for code in sorted(set(other_groups) - set(d.groups)):
        rep.differences.append(Difference(code, None, "group missing from JSON", "", code))
    for code, grp in d.groups.items():
        if code in other_groups and _norm(grp.description) != other_groups[code]:
            rep.differences.append(Difference(code, None, "group title", grp.description, other_groups[code]))

    for grp in d.groups.values():
        if grp.code not in other_groups:
            continue
        json_codes = [h.code for h in grp.headings]
        pdf_codes = [r.code for r in sorted((r for (g, _), r in pdf_index.items() if g == grp.code),
                                            key=lambda r: r.order)]
        for h in grp.headings:
            p = pdf_index.get((grp.code, h.code))
            if p is None:
                rep.differences.append(Difference(grp.code, h.code, "heading missing from other", h.code, ""))
                continue
            for f in FIELDS:
                jv, pv = _norm(getattr(h, f)), getattr(p, f)
                if jv != pv:
                    rep.differences.append(Difference(grp.code, h.code, f, getattr(h, f), pv, p.page))
        for c in pdf_codes:
            if c not in json_codes:
                p = pdf_index[(grp.code, c)]
                rep.differences.append(Difference(grp.code, c, "heading missing from JSON", "", c, p.page))
        common_json = [c for c in json_codes if c in pdf_codes]
        common_pdf = [c for c in pdf_codes if c in json_codes]
        if common_json != common_pdf:
            rep.differences.append(Difference(grp.code, None, "heading order", ", ".join(common_json),
                                              ", ".join(common_pdf)))
    return rep
