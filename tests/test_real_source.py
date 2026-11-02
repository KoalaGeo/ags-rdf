"""Optional end-to-end checks against the full AGS source (set AGS_RDF_SOURCE)."""
import pytest

from ags_rdf.build import build_release
from ags_rdf.releases import discover_releases


def test_all_releases_discovered(real_source):
    assert {"4.0.3", "4.0.4", "4.1", "4.1.1", "4.2.0"} <= set(discover_releases(real_source))


@pytest.mark.parametrize("version", ["4.0.4", "4.2.0"])
def test_real_release_builds_valid(real_source, tmp_path, version):
    rel = discover_releases(real_source)[version]
    r = build_release(real_source, rel, tmp_path, xlsx=False)
    assert r.ok, [x.summary for x in r.results if not x.conforms]


def test_json_matches_pdf_404(real_source):
    pytest.importorskip("pdfplumber")
    from ags_rdf.checks.pdf import compare_pdf

    rel = discover_releases(real_source)["4.0.4"]
    pdf = real_source.path("AGS4/downloads/AGS_4_0_4.pdf")
    rep = compare_pdf(real_source, rel, pdf)
    assert rep.groups_json == rep.groups_pdf and rep.headings_json == rep.headings_pdf
    assert len(rep.differences) < 25


def test_ags_example_file_converts_and_validates(real_source, tmp_path):
    """The AGS's own 4.0 example file (AGS4/examples/*.zip) is valid after conversion."""
    import zipfile

    from ags_rdf.builders.common import BuildContext
    from ags_rdf.builders.ontology import OntologyBuilder
    from ags_rdf.builders.shapes import ShapesBuilder
    from ags_rdf.convert import AgsConverter, check_file, declared_type_shapes, pick_release, read_ags
    from ags_rdf.loader import load_dictionary
    from ags_rdf.validate import shacl_validate

    zpath = real_source.path("AGS4/examples/AGS4_Example_File_v07_130502.zip")
    with zipfile.ZipFile(zpath) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".ags"))
        path = tmp_path / "example.ags"
        path.write_bytes(zf.read(name))
    ags = read_ags(path)
    rel = pick_release(discover_releases(real_source), ags.ags_version)
    assert rel.version == "4.0.4"
    ctx = BuildContext(load_dictionary(real_source, rel), real_source)
    g, _ = AgsConverter(ctx, "https://example.org/ags/example/").convert(ags)
    assert [i for i in check_file(ags, ctx.dictionary) if i.severity == "error"] == []
    r = shacl_validate(g, ShapesBuilder(ctx).build(), "example", "shapes", ont=OntologyBuilder(ctx).build(),
                       ignore_shapes=declared_type_shapes(ags, ctx.dictionary, ctx.iris))
    assert r.violations == 0, r.details
