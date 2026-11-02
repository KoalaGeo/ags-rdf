"""Copy a built release into the ``data/`` folder of a prez-lite site.

prez-lite (https://github.com/Kurrawong/prez-lite) treats every ``data/vocabs/*.ttl``
as one vocabulary: it uses the first ``skos:ConceptScheme`` in the file and puts
every concept in the file under it. So only the per-vocabulary files belong in
``data/vocabs/`` - not the combined ``-all`` graph (several schemes), nor the
ontology, shapes or catalogue (no scheme). Labels for IRIs a vocabulary links to
go in ``data/background/``.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from rdflib import RDF, SKOS, Graph

PREZ_LITE_MANIFEST = """PREFIX mrr: <https://prez.dev/ManifestResourceRoles/>
PREFIX prez: <https://prez.dev/>
PREFIX prof: <http://www.w3.org/ns/dx/prof/>
PREFIX schema: <https://schema.org/>

# Written by ags-rdf (prez-lite layout)
[]  a prez:Manifest ;
    prof:hasResource
        [
            prof:hasArtifact "vocabs/*.ttl" ;
            prof:hasRole mrr:ResourceData ;
            schema:description "SKOS vocabularies in Turtle format, one ConceptScheme per file" ;
            schema:name "Vocabulary Data" ;
        ] ,
        [
            prof:hasArtifact "background/*.ttl" ;
            prof:hasRole mrr:IncompleteCatalogueAndResourceLabels ;
            schema:description "Background labels for external IRI resolution" ;
            schema:name "Background Labels" ;
        ] ;
.
"""


@dataclass
class PublishResult:
    copied: list[Path] = field(default_factory=list)
    manifest: str = "kept"  # "written" | "kept"
    problems: list[str] = field(default_factory=list)


def scheme_count(path: Path) -> int:
    g = Graph().parse(path)
    return len(set(g.subjects(RDF.type, SKOS.ConceptScheme)))


def latest_release(dist: Path) -> str:
    from .releases import version_key

    versions = [p.name for p in Path(dist).iterdir()
                if p.is_dir() and (p / "vocabs").is_dir() and all(x.isdigit() for x in p.name.split("."))]
    if not versions:
        raise FileNotFoundError(f"No built releases in {dist}; run 'ags-rdf build' first")
    return max(versions, key=version_key)


def export_prez_lite(release_dir: Path, data_dir: Path) -> PublishResult:
    release_dir, data_dir = Path(release_dir), Path(data_dir)
    vocabs = sorted((release_dir / "vocabs").glob("*.ttl"))
    if not vocabs:
        raise FileNotFoundError(f"No vocabularies in {release_dir / 'vocabs'}; run 'ags-rdf build' first")
    res = PublishResult()
    for sub, files in (("vocabs", vocabs), ("background", sorted((release_dir / "background").glob("*.ttl")))):
        (data_dir / sub).mkdir(parents=True, exist_ok=True)
        for f in files:
            dest = data_dir / sub / f.name
            shutil.copyfile(f, dest)
            res.copied.append(dest)

    manifest = data_dir / "manifest.ttl"
    if not manifest.exists() or "urn:ags-rdf:manifest" in manifest.read_text(encoding="utf-8"):
        # missing, or the ags-rdf build manifest copied by hand (its paths do not fit prez-lite)
        manifest.write_text(PREZ_LITE_MANIFEST, encoding="utf-8", newline="\n")
        res.manifest = "written"

    for f in sorted((data_dir / "vocabs").glob("*.ttl")):
        try:
            n = scheme_count(f)
        except Exception as e:  # noqa: BLE001
            res.problems.append(f"{f.name}: not readable as Turtle ({e})")
            continue
        if n != 1:
            res.problems.append(f"{f.name}: has {n} ConceptSchemes; prez-lite needs exactly one per file in "
                                "data/vocabs/ - remove it (ags-rdf's -all, ontology, shapes and catalogue "
                                "files are not vocabularies)")
    return res
