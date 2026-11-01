import pyshacl
import pytest
from rdflib import RDF, SH, XSD, Graph, Literal, URIRef

from ags_rdf.validate import _results, validate_shapes


def test_shapes_are_valid_shacl(shapes):
    results = validate_shapes(shapes)
    assert all(r.conforms for r in results), [r.details for r in results]


def test_one_node_shape_per_group(shapes, dictionary, ctx):
    targets = set(shapes.objects(None, SH.targetClass))
    assert targets == {ctx.iris.group_class(g) for g in dictionary.groups}


def test_shapes_link_to_dictionary(shapes, ctx):
    ps = ctx.iris.property_shape("SAMP", "SAMP_TOP")
    assert (ps, ctx.iris.AGSO.dictionaryEntry, ctx.iris.heading_concept("SAMP_TOP")) in shapes
    assert (ps, ctx.iris.AGSO.isKey, Literal(True)) in shapes
    assert (ps, SH.order, None) in shapes


class Data:
    def __init__(self, ctx):
        self.g, self.A, self.O = Graph(), ctx.iris.AGS, ctx.iris.AGSO

    def rec(self, name, group, parent=None, **values):
        node = URIRef(f"urn:test:{name}")
        self.g.add((node, RDF.type, self.A[group]))
        if parent:
            self.g.add((node, self.O.parent, URIRef(f"urn:test:{parent}")))
        for k, v in values.items():
            self.g.add((node, self.A[k], v if isinstance(v, Literal) else Literal(v)))
        return node


def valid_data(ctx) -> Data:
    d = Data(ctx)
    d.rec("proj", "PROJ", PROJ_ID="121415")
    d.rec("tran", "TRAN", TRAN_ISNO="1", TRAN_DATE=Literal("2026-01-01", datatype=XSD.date),
          TRAN_PROD="ACME", TRAN_STAT="FINAL", TRAN_AGS="4.2", TRAN_RECV="Client", TRAN_RCON="+")
    d.rec("bh1", "LOCA", "proj", LOCA_ID="BH1", LOCA_TYPE="CP+RC",
          LOCA_NATE=Literal("523145.00", datatype=XSD.decimal))
    d.rec("s1", "SAMP", "bh1", LOCA_ID="BH1", SAMP_TOP=Literal("1.50", datatype=XSD.decimal),
          SAMP_REF="1", SAMP_TYPE="B", SAMP_ID="S1")
    d.rec("spt", "ISPT", "bh1", LOCA_ID="BH1", ISPT_TOP=Literal("2.00", datatype=XSD.decimal),
          ISPT_ROCK="Y")
    return d


def run(ctx, shapes, ontology, data):
    _, report, _ = pyshacl.validate(data.g, shacl_graph=shapes, ont_graph=ontology, allow_warnings=True)
    v, w, _, details = _results(report, 1000)
    return v, w, details


def test_valid_data_conforms(ctx, shapes, ontology):
    v, w, details = run(ctx, shapes, ontology, valid_data(ctx))
    assert (v, w) == (0, 0), details


@pytest.mark.parametrize("mutate,expect", [
    (lambda d: d.rec("bh1b", "LOCA", "proj", LOCA_ID="BH1"), "same combination of KEY fields"),
    (lambda d: d.rec("proj2", "PROJ", PROJ_ID="2"), "only one PROJ data row"),
    (lambda d: d.g.remove((URIRef("urn:test:proj"), d.A.PROJ_ID, None)), "Less than 1 values"),
    (lambda d: d.rec("s2", "SAMP", "bh1", LOCA_ID="BH9"), "no matching LOCA parent"),
    (lambda d: d.rec("s3", "SAMP", None, LOCA_ID="BH1"), "no matching LOCA parent"),
    (lambda d: d.rec("s4", "SAMP", "bh1", LOCA_ID="BH1", SAMP_TOP="deep"), "NumericValue"),
    (lambda d: d.rec("spt2", "ISPT", "bh1", LOCA_ID="BH1", ISPT_TOP=Literal("3.00", datatype=XSD.decimal),
                     ISPT_ROCK="Yes"), "YesNoValue"),
    (lambda d: d.g.add((URIRef("urn:test:s1"), d.A.SAMP_REF, Literal("2"))), "More than 1 values"),
    (lambda d: d.rec("s5", "SAMP", "proj", LOCA_ID="BH1", SAMP_ID="S5"), "Value does not have class"),
])
def test_violations(ctx, shapes, ontology, mutate, expect):
    data = valid_data(ctx)
    mutate(data)
    v, _, details = run(ctx, shapes, ontology, data)
    assert v > 0 and any(expect in x for x in details), details


@pytest.mark.parametrize("values,expect", [
    ({"LOCA_NATE": Literal("523145.1", datatype=XSD.decimal)}, "suggested format 2DP"),
    ({"LOCA_TYPE": "ZZ"}, "not a standard AGS 4.2.0 abbreviation"),
])
def test_warnings(ctx, shapes, ontology, values, expect):
    data = valid_data(ctx)
    data.rec("bh2", "LOCA", "proj", LOCA_ID="BH2", **values)
    v, w, details = run(ctx, shapes, ontology, data)
    assert v == 0 and w == 1 and expect in details[0], details
