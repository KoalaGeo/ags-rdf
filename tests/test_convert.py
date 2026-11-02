from pathlib import Path

import pytest
from rdflib import RDF, RDFS, XSD, Literal, URIRef

from ags_rdf.cli import main
from ags_rdf.convert import AgsConverter, check_file, declared_type_shapes, pick_release, read_ags
from ags_rdf.releases import Release
from ags_rdf.validate import shacl_validate

FIXTURE = Path(__file__).parent / "fixtures" / "asg4-mini"
BASE = "https://example.org/data/test/"

GOOD = '''"GROUP","PROJ"
"HEADING","PROJ_ID","PROJ_NAME"
"UNIT","",""
"TYPE","ID","X"
"DATA","121415","Test project"

"GROUP","TRAN"
"HEADING","TRAN_ISNO","TRAN_DATE","TRAN_PROD","TRAN_STAT","TRAN_AGS","TRAN_RECV","TRAN_RCON"
"UNIT","","yyyy-mm-dd","","","","",""
"TYPE","X","DT","X","X","X","X","X"
"DATA","1","2026-01-15","ACME","FINAL","4.2","Client","+"

"GROUP","UNIT"
"HEADING","UNIT_UNIT","UNIT_DESC"
"UNIT","",""
"TYPE","X","X"
"DATA","m","metre"
"DATA","yyyy-mm-dd","year month day"

"GROUP","TYPE"
"HEADING","TYPE_TYPE","TYPE_DESC"
"UNIT","",""
"TYPE","X","X"
"DATA","ID","Unique identifier"
"DATA","X","Text"
"DATA","DT","Date"
"DATA","2DP","Value with 2 decimal places"
"DATA","3DP","Value with 3 decimal places"
"DATA","PA","Text listed in ABBR group"

"GROUP","ABBR"
"HEADING","ABBR_HDNG","ABBR_CODE","ABBR_DESC"
"UNIT","","",""
"TYPE","X","X","X"
"DATA","LOCA_TYPE","CP","Cable percussion"
"DATA","LOCA_TYPE","RC","Rotary core"
"DATA","SAMP_TYPE","B","Bulk disturbed sample"

"GROUP","DICT"
"HEADING","DICT_TYPE","DICT_GRP","DICT_HDNG","DICT_STAT","DICT_DTYP","DICT_DESC","DICT_UNIT"
"UNIT","","","","","","",""
"TYPE","X","X","X","X","X","X","X"
"DATA","HEADING","LOCA","LOCA_XTRA","OTHER","X","Extra remark",""

"GROUP","LOCA"
"HEADING","LOCA_ID","LOCA_TYPE","LOCA_NATE","LOCA_STAR","LOCA_XTRA"
"UNIT","","","m","yyyy-mm-dd",""
"TYPE","ID","PA","3DP","DT","X"
"DATA","BH1","CP+RC","523145.000","2026-01-05","user value"

"GROUP","SAMP"
"HEADING","LOCA_ID","SAMP_TOP","SAMP_REF","SAMP_TYPE","SAMP_ID"
"UNIT","","m","","",""
"TYPE","ID","2DP","X","PA","ID"
"DATA","BH1","1.50","1","B","S1"
"DATA","BH1","2.00","","B","S2"
'''


@pytest.fixture
def good(tmp_path) -> Path:
    p = tmp_path / "good.ags"
    p.write_text(GOOD.replace("\n", "\r\n"), newline="")
    return p


@pytest.fixture
def bad(tmp_path) -> Path:
    text = GOOD + '''"DATA","BH1","2.00","","B","S2"
"DATA","BH9","3.00","3","ZZ","S3"
"DATA","BH1","deep","4","B","S4"
'''
    text = text.replace('"UNIT","","m","","",""', '"UNIT","","ft","","",""')
    p = tmp_path / "bad.ags"
    p.write_text(text, newline="")
    return p


def test_read_ags(good):
    ags = read_ags(good)
    assert list(ags.tables) == ["PROJ", "TRAN", "UNIT", "TYPE", "ABBR", "DICT", "LOCA", "SAMP"]
    assert ags.ags_version == "4.2" and not ags.issues
    assert ags.tables["SAMP"].records()[1]["SAMP_REF"] == ""


def test_pick_release():
    rels = {v: Release(v, "x") for v in ("4.0.3", "4.0.4", "4.1", "4.1.1", "4.2.0")}
    assert [pick_release(rels, v).version for v in ("4.0", "4.0.3", "4.1", "4.1.1", "4.2", None, "9")] == \
        ["4.0.4", "4.0.3", "4.1", "4.1.1", "4.2.0", "4.2.0", "4.2.0"]


def test_conversion(ctx, good):
    g, issues = AgsConverter(ctx, BASE).convert(read_ags(good))
    assert not issues, issues
    A, O = ctx.iris.AGS, ctx.iris.AGSO
    loca = URIRef(BASE + "LOCA/BH1")
    s1, s2 = URIRef(BASE + "SAMP/BH1/1.50/1/B/S1"), URIRef(BASE + "SAMP/BH1/2.00/_/B/S2")
    assert (s1, RDF.type, A.SAMP) in g and (s2, RDF.type, A.SAMP) in g
    assert (s1, O.parent, loca) in g and (loca, O.parent, URIRef(BASE + "PROJ/121415")) in g
    assert (s1, A.SAMP_TOP, Literal("1.50", datatype=XSD.decimal)) in g
    assert (loca, A.LOCA_STAR, Literal("2026-01-05", datatype=XSD.date)) in g
    assert (s2, A.SAMP_REF, None) not in g  # null values are not written
    # the file's own UNIT/TYPE rows are kept
    fd = URIRef(BASE + "field/LOCA/LOCA_NATE")
    assert (fd, O.unit, ctx.iris.unit("m")) in g and (fd, O.position, Literal(3)) in g
    # user-defined heading from DICT
    xtra = URIRef(BASE + "def/LOCA_XTRA")
    assert (loca, xtra, Literal("user value")) in g and (xtra, RDFS.label, Literal("Extra remark")) in g


def test_valid_file_passes(ctx, shapes, ontology, good):
    ags = read_ags(good)
    g, _ = AgsConverter(ctx, BASE).convert(ags)
    assert check_file(ags, ctx.dictionary) == []
    ignore = declared_type_shapes(ags, ctx.dictionary, ctx.iris)
    assert ctx.iris.property_shape("LOCA", "LOCA_NATE", "-format") in ignore  # file says 3DP, dictionary 2DP
    r = shacl_validate(g, shapes, "good", "shapes", ont=ontology, ignore_shapes=ignore)
    assert r.violations == 0 and r.warnings == 0, r.details


def test_broken_file_is_reported(ctx, shapes, ontology, bad):
    ags = read_ags(bad)
    rules = {i.category for i in check_file(ags, ctx.dictionary) if i.severity == "error"}
    assert {"rule-8", "rule-10a", "rule-10c", "rule-15", "rule-16"} <= rules
    g, _ = AgsConverter(ctx, BASE).convert(ags)
    r = shacl_validate(g, shapes, "bad", "shapes", ont=ontology)
    text = "\n".join(r.details)
    assert "same combination of KEY fields" in text and "no matching LOCA parent" in text


def test_cli_convert(tmp_path, good, bad):
    out = tmp_path / "out"
    (tmp_path / "copy").mkdir()
    dup = tmp_path / "copy" / "good.ags"
    dup.write_bytes(good.read_bytes())
    rc = main(["convert", "--source", str(FIXTURE), str(good), str(dup), "-o", str(out), "--validate",
               "--format", "ttl", "nt"])
    assert rc == 0
    assert {p.name for p in out.iterdir()} >= {"good.ttl", "good.nt", "good~2.ttl", "good.validation.txt"}
    assert main(["convert", "--source", str(FIXTURE), str(bad), "-o", str(tmp_path / "bad.ttl"),
                 "--validate"]) == 1
