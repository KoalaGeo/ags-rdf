"""Cross-check the JSON against an AGS *standard dictionary* file (``.ags`` with a DICT group).

The AGS publishes the dictionary of each release as an AGS4 file whose DICT
group lists every GROUP and HEADING (the same files are bundled with the
``python-ags4`` package as ``Standard_dictionary_v4_*.ags``). Note that these
files state they were compiled from the AGS working group's repository, so they
are a consistency check rather than a fully independent source.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..loader import load_dictionary
from ..releases import Release
from ..sources import Snapshot
from .pdf import PdfHeading, PdfReport, _norm, compare_tables

STATUS = {"KEY": "*", "REQUIRED": "R", "KEY+REQUIRED": "*R", "OTHER": "", "": ""}


def read_dict_group(path: Path) -> tuple[dict[str, str], list[PdfHeading]]:
    groups: dict[str, str] = {}
    rows: list[PdfHeading] = []
    order: dict[str, int] = {}
    group, headings = None, []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for lineno, rec in enumerate(csv.reader(f), start=1):
            if not rec:
                continue
            kind = rec[0]
            if kind == "GROUP":
                group, headings = rec[1], []
            elif kind == "HEADING":
                headings = rec[1:]
            elif kind == "DATA" and group == "DICT":
                r = dict(zip(headings, rec[1:], strict=False))
                g = r.get("DICT_GRP", "")
                if r.get("DICT_TYPE") == "GROUP":
                    groups.setdefault(g, _norm(r.get("DICT_DESC")))
                elif r.get("DICT_TYPE") == "HEADING":
                    order[g] = order.get(g, 0) + 1
                    rows.append(PdfHeading(g, r.get("DICT_HDNG", ""), order[g],
                                           STATUS.get(r.get("DICT_STAT", "").upper(), r.get("DICT_STAT", "")),
                                           _norm(r.get("DICT_UNIT")), _norm(r.get("DICT_DTYP")),
                                           _norm(r.get("DICT_DESC")), _norm(r.get("DICT_EXMP")), lineno))
    return groups, rows


def compare_standard_dictionary(snapshot: Snapshot, release: Release, path: Path) -> PdfReport:
    d = load_dictionary(snapshot, release)
    groups, rows = read_dict_group(Path(path))
    rep = PdfReport(release.version, Path(path).name, snapshot.url_for(release.groups_and_headings),
                    other_label="standard dictionary")
    return compare_tables(d, groups, rows, rep)
