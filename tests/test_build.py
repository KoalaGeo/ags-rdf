from rdflib import Graph

from ags_rdf.build import build_release
from ags_rdf.config import Settings


def test_build_writes_all_outputs(built):
    names = {p.name for p in built.files}
    v = built.version
    for stem in (f"ags4-{v}-ontology", f"ags4-{v}-shapes", f"ags4-{v}-all"):
        assert f"{stem}.ttl" in names and f"{stem}.nt" in names
    for vocab in ("dictionary", "abbreviations", "units", "data-types", "rules", "contaminant-codes"):
        for ext in ("ttl", "nt", "xlsx"):
            assert f"ags4-{v}-{vocab}.{ext}" in names
    assert {"catalogue.ttl", "manifest.ttl", "data-quality.md", "validation.md", "issues.json",
            f"ags4-{v}-labels.ttl"} <= names


def test_build_validation_passes(built):
    failing = [r.summary for r in built.results if not r.conforms]
    assert not failing, failing
    checks = {r.check for r in built.results}
    assert {"SHACL-SHACL", "VocPub 5.1", "VocExcel round trip", "examples vs shapes"} <= checks


def test_outputs_parse_and_ttl_equals_nt(built):
    for p in built.files:
        if p.suffix == ".ttl" and p.name.startswith("ags4-") and p.parent.name != "background":
            nt = p.with_name(p.name[:-4] + ".nt")
            assert len(Graph().parse(p)) == len(Graph().parse(nt, format="nt")), p.name


def test_builds_are_deterministic(tmp_path, snapshot, release):
    a = build_release(snapshot, release, tmp_path / "a", Settings(), xlsx=False, validate=False)
    b = build_release(snapshot, release, tmp_path / "b", Settings(), xlsx=False, validate=False)
    for pa in a.files:
        if pa.suffix == ".nt":
            pb = b.out_dir / pa.relative_to(a.out_dir)
            assert pa.read_bytes() == pb.read_bytes(), pa.name


def test_base_iri_is_configurable(tmp_path, snapshot, release):
    r = build_release(snapshot, release, tmp_path, Settings(base_iri="https://example.org/x"), xlsx=False,
                      validate=False)
    text = (r.out_dir / f"ags4-{r.version}-shapes.ttl").read_text()
    assert "https://example.org/x/shapes/" in text and "w3id.org" not in text


def test_manifest_valid_for_kgm(built):
    """Validate manifest.ttl with kgm's own manifest validator, if kgm is installed."""
    import pytest

    kgm = pytest.importorskip("kgm")
    from importlib.resources import files

    import pyshacl

    shapes = Graph().parse(files(kgm) / "validator.ttl")
    data = Graph().parse(built.out_dir / "manifest.ttl") + Graph().parse(files(kgm) / "mrr.ttl")
    conforms, _, text = pyshacl.validate(data, shacl_graph=shapes)
    assert conforms, text
