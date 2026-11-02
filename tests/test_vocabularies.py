from rdflib import RDF, RDFS, SKOS

from ags_rdf.validate import validate_vocab


def test_expected_vocabularies(vocabs):
    assert set(vocabs) == {"dictionary", "abbreviations", "units", "data-types", "rules", "contaminant-codes"}


def test_each_vocab_is_one_vocpub_conformant_scheme(vocabs):
    for name, g in vocabs.items():
        assert len(set(g.subjects(RDF.type, SKOS.ConceptScheme))) == 1, name
        r = validate_vocab(g, name)
        assert r.conforms and r.warnings == 0, (name, r.details)


def test_dictionary_hierarchy(vocabs, ctx, dictionary):
    g, i = vocabs["dictionary"], ctx.iris
    cs = i.scheme("dictionary")
    assert set(g.objects(cs, SKOS.hasTopConcept)) == {i.group_concept(c) for c in dictionary.groups}
    # a shared heading is narrower than every group it occurs in
    loca_id = i.heading_concept("LOCA_ID")
    groups_with = {h.group for h in dictionary.heading_occurrences()["LOCA_ID"]}
    assert set(g.objects(loca_id, SKOS.broader)) == {i.group_concept(c) for c in groups_with}
    assert (loca_id, SKOS.notation, None) in g
    assert (i.group_concept("SAMP"), i.AGSO.parentGroup, i.group_concept("LOCA")) in g
    assert all((c, RDFS.isDefinedBy, cs) in g for c in g.subjects(RDF.type, SKOS.Concept))


def test_abbreviation_collections(vocabs, ctx):
    g, i = vocabs["abbreviations"], ctx.iris
    col = i.abbreviation_list("LOCA_TYPE")
    assert (col, RDF.type, SKOS.Collection) in g
    assert (col, SKOS.member, i.abbreviation("LOCA_TYPE", "CP")) in g


def test_data_type_hierarchy(vocabs, ctx):
    g, i = vocabs["data-types"], ctx.iris
    assert (i.data_type("2DP"), SKOS.broader, i.data_type("nDP")) in g


def test_rules_hierarchy(vocabs, ctx):
    g, i = vocabs["rules"], ctx.iris
    assert (i.rule("10a"), SKOS.broader, i.rule("10")) in g
