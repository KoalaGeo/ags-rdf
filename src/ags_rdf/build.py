"""Build pipeline: one release -> RDF files, VocExcel workbooks, validation and reports.

Output layout (``<out>/<version>/``)::

    ags4-<v>-ontology.ttl|nt      OWL: meta-model + class per GROUP, property per HEADING
    ags4-<v>-shapes.ttl|nt        SHACL shapes
    vocabs/ags4-<v>-<name>.ttl|nt|xlsx
                                  SKOS vocabularies (VocPub) + VocExcel workbooks
    ags4-<v>-all.ttl|nt           everything above in one graph
    catalogue.ttl                 dcat:Catalog of the above
    manifest.ttl                  Prez/KGM manifest (for kgm validate / kgm load)
    reports/                      data-quality and validation reports (Markdown + JSON)

Extra builders (e.g. future DIGGS or ISO mapping sets) can be registered in
:data:`EXTRA_BUILDERS`: callables taking a :class:`BuildContext` and returning
``{name: Graph}``; their graphs are written next to the others and included in
the combined graph.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from rdflib import DCAT, DCTERMS, RDF, SDO, Graph, Literal, Namespace, URIRef

from .builders.common import BuildContext
from .builders.ontology import OntologyBuilder
from .builders.shapes import ShapesBuilder
from .builders.vocabularies import VocabularyBuilder
from .config import Settings
from .export import write_rdf, write_vocexcel
from .loader import load_dictionary
from .releases import Release
from .report import write_reports
from .sources import Snapshot
from .validate import (Result, check_xlsx_roundtrip, validate_examples, validate_shapes,
                       validate_vocab)

log = logging.getLogger(__name__)

EXTRA_BUILDERS: list[Callable[[BuildContext], dict[str, Graph]]] = []

PREZ = Namespace("https://prez.dev/")
MRR = Namespace("https://prez.dev/ManifestResourceRoles/")
PROF = Namespace("http://www.w3.org/ns/dx/prof/")


@dataclass
class BuildResult:
    version: str
    out_dir: Path
    files: list[Path] = field(default_factory=list)
    results: list[Result] = field(default_factory=list)
    graphs: dict[str, Graph] = field(default_factory=dict, repr=False)

    @property
    def ok(self) -> bool:
        return all(r.conforms for r in self.results)


def build_release(snapshot: Snapshot, release: Release, out: Path, settings: Settings | None = None,
                  xlsx: bool = True, validate: bool = True, examples: bool = True) -> BuildResult:
    settings = settings or Settings()
    d = load_dictionary(snapshot, release, settings)
    ctx = BuildContext(d, snapshot, settings)
    v = d.version
    base = Path(out) / v
    res = BuildResult(v, base)
    log.info("AGS %s: %d groups, %d headings", v, len(d.groups), len(d.headings()))

    ontology = OntologyBuilder(ctx).build()
    shapes = ShapesBuilder(ctx).build()
    vocabs = VocabularyBuilder(ctx).build_all()
    extras: dict[str, Graph] = {}
    for builder in EXTRA_BUILDERS:
        extras.update(builder(ctx))

    res.files += write_rdf(ontology, base / f"ags4-{v}-ontology")
    res.files += write_rdf(shapes, base / f"ags4-{v}-shapes")
    vocab_files: dict[str, Path] = {}
    for name, g in vocabs.items():
        paths = write_rdf(g, base / "vocabs" / f"ags4-{v}-{name}")
        vocab_files[name] = paths[0]
        res.files += paths
    for name, g in extras.items():
        res.files += write_rdf(g, base / "extras" / f"ags4-{v}-{name}")

    combined = ctx.new_graph()
    for g in [ontology, shapes, *vocabs.values(), *extras.values()]:
        combined += g
    res.files += write_rdf(combined, base / f"ags4-{v}-all")
    res.files.append(_write_catalogue(ctx, base, vocabs))
    res.files.append(_write_manifest(base, v, vocabs, extras))

    if xlsx:
        for name, ttl in vocab_files.items():
            path = base / "vocabs" / f"ags4-{v}-{name}.xlsx"
            log.info("VocExcel %s", path.name)
            res.files.append(write_vocexcel(ttl, path))

    if validate:
        res.results += validate_shapes(shapes, f"ags4-{v}-shapes")
        for name, g in vocabs.items():
            res.results.append(validate_vocab(g, f"ags4-{v}-{name}"))
            xp = base / "vocabs" / f"ags4-{v}-{name}.xlsx"
            if xlsx and xp.exists():
                res.results.append(check_xlsx_roundtrip(xp, g, xp.name))
        if examples:
            res.results.append(validate_examples(ctx, shapes, ontology))

    res.files += write_reports(ctx, res, base / "reports")
    res.graphs = {"ontology": ontology, "shapes": shapes, **vocabs, **extras}
    return res


def _write_catalogue(ctx: BuildContext, base: Path, vocabs: dict[str, Graph]) -> Path:
    iris, d = ctx.iris, ctx.dictionary
    g = ctx.new_graph()
    cat = iris.catalogue
    g.add((cat, RDF.type, DCAT.Catalog))
    g.add((cat, DCTERMS.title, ctx.text(f"AGS {d.version} data dictionary in RDF")))
    g.add((cat, DCTERMS.description, ctx.text(
        f"SKOS vocabularies, an OWL data model and SHACL shapes generated from the AGS {d.version} "
        "data dictionary JSON.")))
    g.add((cat, SDO.version, Literal(d.version)))
    g.add((cat, DCTERMS.publisher, ctx.add_agent(g, ctx.settings.publisher)))
    g.add((cat, DCTERMS.creator, ctx.add_agent(g, ctx.settings.creator)))
    for part in [iris.ontology, iris.shapes_graph, *(iris.scheme(n) for n in vocabs)]:
        g.add((cat, DCTERMS.hasPart, part))
    path = base / "catalogue.ttl"
    g.serialize(destination=path, format="longturtle", encoding="utf-8")
    return path


def _write_manifest(base: Path, v: str, vocabs: dict, extras: dict) -> Path:
    """A Prez/KGM manifest, so ``kgm validate|load`` can work with the output folder."""
    g = Graph()
    for p, ns in (("prez", PREZ), ("mrr", MRR), ("prof", PROF), ("schema", SDO)):
        g.bind(p, ns)
    m = URIRef(f"urn:ags-rdf:manifest:{v}")
    g.add((m, RDF.type, PREZ.Manifest))

    def resource(name: str, artifacts: list[str], role: URIRef, description: str) -> None:
        r = URIRef(f"urn:ags-rdf:manifest:{v}:{name.lower().replace(' ', '-')}")
        g.add((m, PROF.hasResource, r))
        g.add((r, SDO.name, Literal(name)))
        g.add((r, SDO.description, Literal(description)))
        g.add((r, PROF.hasRole, role))
        for a in artifacts:
            g.add((r, PROF.hasArtifact, Literal(a)))

    resource("Catalogue", ["catalogue.ttl"], MRR.CatalogueData,
             "dcat:Catalog describing the AGS vocabularies, ontology and shapes")
    resource("Vocabularies", ["vocabs/*.ttl"], MRR.ResourceData,
             "SKOS ConceptSchemes (VocPub profile), one per file")
    resource("Data model and shapes", [f"ags4-{v}-ontology.ttl", f"ags4-{v}-shapes.ttl"],
             MRR.ResourceModel, "OWL data model and SHACL shapes for AGS data in RDF")
    if extras:
        resource("Extras", ["extras/*.ttl"], MRR.ResourceData, "Additional generated graphs")
    path = base / "manifest.ttl"
    g.serialize(destination=path, format="longturtle", encoding="utf-8")
    return path


def write_summary(results: list[BuildResult], out: Path) -> Path:
    data = [{"version": r.version, "ok": r.ok, "results": [asdict(x) | {"details": x.details[:10]}
                                                         for x in r.results]} for r in results]
    path = Path(out) / "build-summary.json"
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path
