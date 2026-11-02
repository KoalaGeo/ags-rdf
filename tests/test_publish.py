from rdflib import RDFS, Graph

from ags_rdf.cli import main
from ags_rdf.publish import PREZ_LITE_MANIFEST, export_prez_lite, latest_release


def test_background_labels_cover_cross_vocabulary_links(built, ctx):
    labels = Graph().parse(built.out_dir / "background" / f"ags4-{built.version}-labels.ttl")
    i = ctx.iris
    # the dictionary links headings to data type and unit concepts defined in other vocabularies
    assert (i.data_type("2DP"), RDFS.label, None) in labels
    assert (i.unit("m"), RDFS.label, None) in labels
    assert (i.AGSO.dataType, RDFS.label, None) in labels
    assert (i.heading_property("LOCA_ID"), RDFS.label, None) in labels
    manifest = (built.out_dir / "manifest.ttl").read_text()
    assert "background/*.ttl" in manifest


def test_export_prez_lite(built, tmp_path):
    data = tmp_path / "data"
    res = export_prez_lite(built.out_dir, data)
    names = sorted(p.name for p in (data / "vocabs").iterdir())
    assert len(names) == 6 and all(n.startswith(f"ags4-{built.version}-") for n in names)
    assert (data / "background" / f"ags4-{built.version}-labels.ttl").exists()
    assert res.manifest == "written" and res.problems == []
    assert (data / "manifest.ttl").read_text() == PREZ_LITE_MANIFEST


def test_export_prez_lite_flags_non_vocabularies_and_keeps_custom_manifest(built, tmp_path):
    data = tmp_path / "data"
    (data / "vocabs").mkdir(parents=True)
    (data / "manifest.ttl").write_text("# my own manifest\n")
    for name in (f"ags4-{built.version}-all.ttl", f"ags4-{built.version}-shapes.ttl", "catalogue.ttl"):
        (data / "vocabs" / name).write_bytes((built.out_dir / name).read_bytes())
    res = export_prez_lite(built.out_dir, data)
    assert res.manifest == "kept"
    assert sorted(p.split(":")[0] for p in res.problems) == sorted(
        [f"ags4-{built.version}-all.ttl", f"ags4-{built.version}-shapes.ttl", "catalogue.ttl"])


def test_export_replaces_copied_build_manifest(built, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "manifest.ttl").write_bytes((built.out_dir / "manifest.ttl").read_bytes())
    assert export_prez_lite(built.out_dir, data).manifest == "written"


def test_cli_prez_lite(built, tmp_path):
    dist = built.out_dir.parent
    assert latest_release(dist) == built.version
    assert main(["prez-lite", str(tmp_path / "data"), "--dist", str(dist)]) == 0
    assert main(["prez-lite", str(tmp_path / "data"), "--dist", str(tmp_path / "nothing")]) == 2
