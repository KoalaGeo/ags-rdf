"""Validation of the generated RDF.

* shapes graph  -> W3C SHACL-SHACL (is it well-formed SHACL?) and executability:
                   pySHACL must load every shape, including the SPARQL constraints
* vocabularies  -> the VocPub 5.1 profile shipped with VocExcel
* workbooks     -> VocExcel round trip: xlsx -> RDF gives back the same concepts,
                   labels, definitions, hierarchy, notations and collection members
* examples      -> the dictionary's own example values, turned into one synthetic
                   record per group, validated against the shapes (a consistency
                   check of the source JSON, reported but never fatal)
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

from rdflib import RDF, RDFS, SDO, SH, SKOS, Graph, Literal, URIRef

log = logging.getLogger(__name__)


@dataclass
class Result:
    target: str
    check: str
    conforms: bool
    violations: int = 0
    warnings: int = 0
    infos: int = 0
    details: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        state = "PASS" if self.conforms else "FAIL"
        return (f"{state} {self.check} - {self.target}: {self.violations} violations, "
                f"{self.warnings} warnings, {self.infos} infos")


def _results(report: Graph, limit: int = 50, ignore_shapes: set | None = None) -> tuple[int, int, int, list[str]]:
    counts = {SH.Violation: 0, SH.Warning: 0, SH.Info: 0}
    details = []
    for r in report.subjects(RDF.type, SH.ValidationResult):
        if (None, SH.detail, r) in report:  # nested result of sh:node etc.; counted via its parent
            continue
        if ignore_shapes and report.value(r, SH.sourceShape) in ignore_shapes:
            continue
        sev = report.value(r, SH.resultSeverity)
        counts[sev] = counts.get(sev, 0) + 1
        if len(details) < limit:
            focus = report.value(r, SH.focusNode)
            path = report.value(r, SH.resultPath)
            msg = report.value(r, SH.resultMessage)
            details.append(f"[{str(sev).split('#')[-1]}] {focus} {path or ''}: {msg}")
    return counts[SH.Violation], counts[SH.Warning], counts[SH.Info], sorted(details)


@contextmanager
def cached_sparql():
    """Cache parsed SPARQL queries while validating.

    pySHACL passes each SPARQL constraint to rdflib as text once per focus node,
    and rdflib parses and translates the text on every call; for large groups
    that dominates validation time. Within this context a query text is parsed
    once. (rdflib Query objects are designed to be reused with different
    initial bindings.)
    """
    from rdflib.plugins.sparql import processor

    original = processor.SPARQLProcessor.query
    cache: dict = {}

    def query(self, strOrQuery, initBindings=None, initNs=None, base=None, DEBUG=False):  # noqa: N803
        if isinstance(strOrQuery, str):
            key = (strOrQuery, base, tuple(sorted((initNs or {}).items())))
            if key not in cache:
                cache[key] = processor.translateQuery(processor.parseQuery(strOrQuery), base, initNs)
            strOrQuery = cache[key]
        return original(self, strOrQuery, initBindings, initNs, base, DEBUG)

    processor.SPARQLProcessor.query = query
    try:
        yield
    finally:
        processor.SPARQLProcessor.query = original


def shacl_validate(data: Graph, shapes: Graph, target: str, check: str, advanced: bool = False,
                   ont: Graph | None = None, limit: int = 50, ignore_shapes: set | None = None) -> Result:
    import kurra.shacl

    data_graph = data if ont is None else data + ont
    with cached_sparql():
        conforms, report, text = kurra.shacl.validate(data_graph, shapes, advanced=advanced)
    if not isinstance(report, Graph):  # pySHACL returns a ValidationFailure on runtime errors
        return Result(target, check, False, 1, details=[str(report)])
    v, w, i, details = _results(report, limit, ignore_shapes)
    return Result(target, check, v == 0, v, w, i, details)


def shacl_shacl() -> Graph:
    return Graph().parse(files("pyshacl") / "assets" / "shacl-shacl.ttl", format="turtle")


def vocpub() -> Graph:
    return Graph().parse(files("vocexcel") / "vocpub-5.1.ttl", format="turtle")


def validate_shapes(shapes: Graph, target: str = "shapes") -> list[Result]:
    """SHACL-SHACL conformance, then execute every shape with pySHACL.

    SHACL-SHACL does not look inside SPARQL constraints, so the shapes are also
    run against a graph holding one empty instance of every target class; this
    executes every constraint (including SPARQL ones) at least once.
    """
    import pyshacl

    check = "pySHACL execution (all constraints, incl. SPARQL)"
    out = [shacl_validate(shapes, shacl_shacl(), target, "SHACL-SHACL")]
    probe = Graph()
    for i, cls in enumerate(sorted(set(shapes.objects(None, SH.targetClass)))):
        probe.add((URIRef(f"urn:ags-rdf:probe:{i}"), RDF.type, cls))
    try:
        _, report, text = pyshacl.validate(probe, shacl_graph=shapes, allow_warnings=True)
        if not isinstance(report, Graph):
            raise RuntimeError(str(report))
        out.append(Result(target, check, True))
    except Exception as e:  # noqa: BLE001
        out.append(Result(target, check, False, 1, details=[str(e)]))
    return out


def validate_vocab(g: Graph, target: str) -> Result:
    return shacl_validate(g, vocpub(), target, "VocPub 5.1")


def check_xlsx_roundtrip(xlsx: Path, original: Graph, target: str) -> Result:
    """Read the workbook back with VocExcel and compare the SKOS content."""
    from vocexcel.convert import excel_to_rdf

    from .export import FULLWIDTH_AT

    try:
        g2 = excel_to_rdf(xlsx, output_format="graph", error_format="python")
    except Exception as e:  # noqa: BLE001 - VocExcel raises on unreadable workbooks
        return Result(target, "VocExcel round trip", False, 1, details=[f"{type(e).__name__}: {e}"])
    if not isinstance(g2, Graph):
        return Result(target, "VocExcel round trip", False, 1, details=[str(g2)])
    for s_, p_, o_ in list(g2.triples((None, SKOS.prefLabel, None))):
        if FULLWIDTH_AT in o_:
            g2.set((s_, p_, Literal(str(o_).replace(FULLWIDTH_AT, "@"), lang=o_.language)))

    def facts(g: Graph) -> set:
        out = set()
        for c in set(g.subjects(RDF.type, SKOS.Concept)) | set(g.subjects(RDF.type, SKOS.Collection)):
            out.add((c, RDF.type, g.value(c, RDF.type)))
            for p in (SKOS.prefLabel, SKOS.definition, SKOS.broader, SKOS.member, SKOS.altLabel,
                      SKOS.historyNote, SKOS.example, SDO.status, RDFS.isDefinedBy, SKOS.inScheme):
                for o in g.objects(c, p):
                    out.add((c, p, str(o).strip() if isinstance(o, Literal) else o))
            for o in g.objects(c, SKOS.notation):
                out.add((c, SKOS.notation, str(o)))
        return out

    a, b = facts(original), facts(g2)
    missing, extra = a - b, b - a
    details = [f"missing after round trip: {t}" for t in sorted(missing, key=str)[:25]]
    details += [f"extra after round trip: {t}" for t in sorted(extra, key=str)[:25]]
    return Result(target, "VocExcel round trip", not missing and not extra,
                  len(missing) + len(extra), details=details)


def validate_examples(ctx, shapes: Graph, ontology: Graph) -> Result:
    """Validate one synthetic record per group, built from the dictionary's example values."""
    from .values import to_literal

    d, iris = ctx.dictionary, ctx.iris
    data = Graph()
    rec = {code: URIRef(f"{iris.base}example/{d.version}/{code}") for code in d.groups}
    for grp in d.groups.values():
        r = rec[grp.code]
        data.add((r, RDF.type, iris.group_class(grp.code)))
        if grp.parent in rec:
            data.add((r, iris.AGSO.parent, rec[grp.parent]))
        for h in grp.headings:
            lit = to_literal(h.example, h.data_type)
            if lit is not None:
                data.add((r, iris.heading_property(h.code), lit))
    res = shacl_validate(data, shapes, f"AGS {d.version} dictionary examples",
                         "examples vs shapes", ont=ontology, limit=100_000)
    res.conforms = True  # informative only: findings are about the source examples
    return res
