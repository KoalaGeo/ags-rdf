import re

import pytest
from rdflib import XSD, Literal

from ags_rdf.datatypes import codes_pattern, generic_code, regex_escape, type_spec
from ags_rdf.iris import IRIs, LocalNames, local_name
from ags_rdf.values import to_literal

VOCEXCEL_SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")


@pytest.mark.parametrize("code,expected", [
    ("CP", "CP"), ("CP+RC", "CP_plus_RC"), ("kN/m2", "kN_per_m2"), ("%", "pct"),
    ("% dry weight", "pct_dry_weight"), ("W/(K-m)", "W_per_K-m"), ("1 LITRE", "1_LITRE"),
    ("GRO (C6-C7 Aliphatic)", "GRO_C6-C7_Aliphatic"), ("µm", "um"),
])
def test_local_name(code, expected):
    assert local_name(code) == expected
    assert VOCEXCEL_SAFE.match(local_name(code))


def test_local_names_are_unique():
    names = LocalNames()
    a, b = names("CP+RC"), names("CP plus RC")
    assert a != b and names("CP+RC") == a


def test_iri_layout():
    i = IRIs("https://example.org/ags4")
    assert str(i.group_class("LOCA")) == "https://example.org/ags4/def/LOCA"
    assert str(i.heading_concept("LOCA_ID")) == "https://example.org/ags4/voc/dictionary/LOCA_ID"
    assert str(i.abbreviation("LOCA_TYPE", "CP+RC")) == \
        "https://example.org/ags4/voc/abbreviations/LOCA_TYPE-CP_plus_RC"
    assert str(i.property_shape("SAMP", "LOCA_ID")) == "https://example.org/ags4/shapes/SAMP-LOCA_ID"
    assert str(i.version_iri(i.scheme("units"), "4.2.0")) == "https://example.org/ags4/voc/units/4.2.0"


def test_type_specs():
    assert generic_code("2DP") == "nDP" and generic_code("X") == "X"
    s = type_spec("2DP")
    assert re.match(s.format_pattern, "523145.00") and not re.match(s.format_pattern, "523145.1")
    assert re.match(type_spec("0DP").format_pattern, "-12")
    assert type_spec("ID").datatypes == (XSD.string,)
    assert type_spec("YN").values == ("Y", "N")
    assert type_spec("").datatypes == ()


def test_regex_escape_is_xsd_compatible():
    # XSD regex only allows escaping metacharacters; Python's re.escape escapes spaces too
    assert regex_escape("CP+RC 1.5 a-b #&~") == r"CP\+RC 1\.5 a\-b #&~"
    p = codes_pattern(["CP", "RC", "1 LITRE"])
    assert re.match(p, "CP+RC") and re.match(p, "1 LITRE") and not re.match(p, "CP+XX")


@pytest.mark.parametrize("value,dtype,expected", [
    ("523145.00", "2DP", Literal("523145.00", datatype=XSD.decimal)),
    ("7.31E4", "2SCI", Literal("7.31E4", datatype=XSD.double)),
    ("NP", "XN", Literal("NP")),
    ("34", "XN", Literal("34", datatype=XSD.decimal)),
    ("1991-03-18", "DT", Literal("1991-03-18", datatype=XSD.date)),
    ("2011-06-01T10:30", "DT", Literal("2011-06-01T10:30:00", datatype=XSD.dateTime)),
    ("10:30", "DT", Literal("10:30:00", datatype=XSD.time)),
    ("2011", "DT", Literal("2011", datatype=XSD.gYear)),
    ("Y", "YN", Literal("Y")),
    ("BH1", "ID", Literal("BH1")),
    ("", "X", None),
])
def test_to_literal(value, dtype, expected):
    lit = to_literal(value, dtype)
    assert lit == expected and (lit is None or str(lit) == str(expected))
