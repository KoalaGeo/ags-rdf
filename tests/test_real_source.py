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
