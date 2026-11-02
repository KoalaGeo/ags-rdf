"""Serialise graphs to Turtle and N-Triples, and vocabularies to VocExcel workbooks."""

from __future__ import annotations

import logging
from pathlib import Path

from rdflib import RDF, SDO, SKOS, Graph

log = logging.getLogger(__name__)

# Stand-in for "@" in VocExcel Preferred Label cells (see write_vocexcel)
FULLWIDTH_AT = "\uff20"


def write_rdf(g: Graph, stem: Path, formats: tuple[str, ...] = ("ttl", "nt")) -> list[Path]:
    """Write ``stem.ttl`` (rdflib "longturtle", stable and diff-friendly) and ``stem.nt`` (sorted)."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    out = []
    for fmt in formats:
        path = stem.parent / f"{stem.name}.{fmt}"
        if fmt == "ttl":
            g.serialize(destination=path, format="longturtle", encoding="utf-8")
        elif fmt == "nt":
            lines = g.serialize(format="nt", encoding="utf-8").decode("utf-8").splitlines()
            path.write_text("\n".join(sorted(set(ln for ln in lines if ln.strip()))) + "\n",
                            encoding="utf-8", newline="\n")
        else:
            g.serialize(destination=path, format=fmt, encoding="utf-8")
        out.append(path)
    return out


def write_vocexcel(ttl: Path, xlsx: Path) -> Path:
    """Convert a VocPub vocabulary file to a VocExcel 1.0 workbook.

    VocExcel's RDF-to-Excel writer puts the scheme status in lower case (and
    the text "None" when absent), which its own Excel-to-RDF reader then
    rejects; the cell is corrected so the workbook round-trips.
    """
    from vocexcel.convert import rdf_to_excel
    from vocexcel.utils import STATUSES

    wb = rdf_to_excel(ttl, output_format="blob", error_format="python")
    if isinstance(wb, Exception):
        raise wb
    g = Graph().parse(ttl)
    cs = g.value(predicate=RDF.type, object=SKOS.ConceptScheme)
    status = g.value(cs, SDO.status) if cs is not None else None
    wb["Concept Scheme"]["B17"] = next((k for k, v in STATUSES.items() if v == str(status)), None)
    # VocExcel reads "label@xx" in the Concepts sheet's Preferred Label column as a language
    # tag, so a literal "@" (e.g. "Dry Solids @ 30 Deg.C") would make the workbook unreadable.
    ws = wb["Concepts"]
    replaced = 0
    for row in range(4, ws.max_row + 1):
        cell = ws[f"B{row}"]
        if isinstance(cell.value, str) and "@" in cell.value:
            cell.value = cell.value.replace("@", FULLWIDTH_AT)
            replaced += 1
    if replaced:
        cs_sheet = wb["Concept Scheme"]
        cs_sheet["B12"] = (f"{cs_sheet['B12'].value} In this workbook '@' in {replaced} preferred label(s) is "
                           f"written as '{FULLWIDTH_AT}' (U+FF20) because VocExcel reads '@' as a language "
                           "tag; the RDF files keep '@'.")
    xlsx.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(xlsx))
    return xlsx
