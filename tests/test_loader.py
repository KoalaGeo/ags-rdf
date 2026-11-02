import json

from ags_rdf.loader import clean_text, load_dictionary
from ags_rdf.releases import discover_releases
from ags_rdf.sources import open_local


def test_groups_and_headings(dictionary):
    d = dictionary
    assert list(d.groups)[:5] == ["PROJ", "ABBR", "DICT", "TRAN", "TYPE"]  # dictionary order
    loca, samp = d.groups["LOCA"], d.groups["SAMP"]
    assert loca.description == "Location Details"
    assert samp.parent == "LOCA" and loca.parent == "PROJ"
    assert [h.code for h in samp.keys] == ["LOCA_ID", "SAMP_TOP", "SAMP_REF", "SAMP_TYPE", "SAMP_ID"]
    proj_id = d.groups["PROJ"].heading("PROJ_ID")
    assert proj_id.is_key and proj_id.is_required
    assert loca.notes and "LOCA" in loca.notes
    assert d.groups["ISTG"].is_new


def test_shared_heading_uses_home_definition(dictionary):
    occ = dictionary.heading_occurrences()["LOCA_ID"]
    assert len(occ) > 1
    assert dictionary.defining_occurrence("LOCA_ID").group == "LOCA"


def test_mis_encoded_characters_are_cleaned(dictionary):
    # The 4.2.0 JSON has "Rule�17" (a mis-encoded non-breaking space)
    assert dictionary.groups["TYPE"].status_text == "Required in all files (Rule 17)"
    assert any(i.category == "encoding" for i in dictionary.issues)


def test_clean_text():
    assert clean_text("a<br>b") == "a b"
    assert clean_text("a<br>b", keep_newlines=True) == "a\nb"
    assert clean_text("<ul><li>x</li><li>y</li></ul>", keep_newlines=True) == "• x\n• y"
    assert clean_text("&bull; a\xa0 b") == "• a b"


def test_registers_filtered_by_version_and_status(dictionary):
    d = dictionary
    assert "LOCA_TYPE" in d.abbreviations
    statuses = {a.status.lower() for abbrs in d.abbreviations.values() for a in abbrs}
    assert statuses <= {"approved", "accepted", "deprecated"}
    assert "kN/m2" in d.units and "%" in d.units
    assert "nDP" in d.data_types and "U" in d.data_types  # U is borrowed from 4.0/4.1
    assert d.data_types["U"].defined_for
    assert any(i.category == "data-type" and "'U'" in i.message for i in d.issues)
    assert "10a" in d.rules and d.rules["10a"].parent_ref == "10"


def test_concatenated_abbreviation_is_reported(mini_copy):
    # In the real register all codes containing "+" are Declined; add an approved one
    p = mini_copy / "AGS4/abbr4.json"
    rows = json.loads(p.read_text())
    rows.append({"Group": "LOCA_TYPE", "Code": "CP+RC", "Description": "Cable percussion and rotary",
                 "Status": "Approved", "Date": "01/01/2025", "Comments": "", "Version": "4.2"})
    p.write_text(json.dumps(rows))
    snap = open_local(mini_copy)
    d = load_dictionary(snap, discover_releases(snap)["4.2.0"])
    assert any(i.category == "abbreviation-concatenation" and i.code == "CP+RC" for i in d.issues)


def test_duplicate_register_entries_resolved(mini_copy):
    p = mini_copy / "AGS4/abbr4.json"
    rows = json.loads(p.read_text())
    first = dict(rows[0])
    rows.append(dict(first, Description="Something else", Status="Declined", Date="01/01/2025"))
    p.write_text(json.dumps(rows))
    snap = open_local(mini_copy)
    d = load_dictionary(snap, discover_releases(snap)["4.2.0"])
    kept = [a for a in d.abbreviations[first["Group"]] if a.code == str(first["Code"])]
    assert len(kept) == 1 and kept[0].description == first["Description"]
    assert any(i.category == "register-duplicate" for i in d.issues)


def test_strict_version_tags_and_fallback(mini_copy):
    from ags_rdf.config import Settings

    snap = open_local(mini_copy)
    rel = discover_releases(snap)["4.2.0"]
    strict = load_dictionary(snap, rel)
    loose = load_dictionary(snap, rel, Settings(register_version_fallbacks={"4.2": ("4.1",)}))
    assert len(loose.contaminant_codes) > len(strict.contaminant_codes)


def test_rule_checks(mini_copy):
    p = mini_copy / "AGS4/AGS4_2/4_2_0/groupsandheadings4-2-0.json"
    rows = json.loads(p.read_text())
    bad = dict(rows[-1], heading="TOOLONGHEADING", in_group_order="99")
    rows.append(bad)
    p.write_text(json.dumps(rows))
    snap = open_local(mini_copy)
    d = load_dictionary(snap, discover_releases(snap)["4.2.0"])
    cats = {i.category for i in d.issues}
    assert "rule-19a" in cats
