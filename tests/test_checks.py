import csv

from ags_rdf.checks.standard_dictionary import compare_standard_dictionary


def write_dict_file(path, dictionary, tweak=None):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        heads = ["DICT_TYPE", "DICT_GRP", "DICT_HDNG", "DICT_STAT", "DICT_DTYP", "DICT_DESC", "DICT_UNIT",
                 "DICT_EXMP", "DICT_PGRP", "DICT_REM", "FILE_FSET"]
        w.writerow(["GROUP", "DICT"])
        w.writerow(["HEADING", *heads])
        stat = {"*": "KEY", "R": "REQUIRED", "*R": "KEY+REQUIRED", "": "OTHER"}
        for g in dictionary.groups.values():
            w.writerow(["DATA", "GROUP", g.code, "", "", "", g.description, "", "", g.parent or "-", "", ""])
            for h in g.headings:
                desc = tweak(h) if tweak else h.description
                w.writerow(["DATA", "HEADING", g.code, h.code, stat[h.status], h.data_type, desc, h.unit,
                            h.example, "", "", ""])


def test_standard_dictionary_identical(tmp_path, snapshot, release, dictionary):
    p = tmp_path / "dict.ags"
    write_dict_file(p, dictionary)
    rep = compare_standard_dictionary(snapshot, release, p)
    assert rep.differences == [] and rep.headings_pdf == rep.headings_json


def test_standard_dictionary_differences(tmp_path, snapshot, release, dictionary):
    p = tmp_path / "dict.ags"
    write_dict_file(p, dictionary, tweak=lambda h: "changed" if h.code == "LOCA_NATE" else h.description)
    rep = compare_standard_dictionary(snapshot, release, p)
    assert [(d.group, d.heading, d.field) for d in rep.differences] == [("LOCA", "LOCA_NATE", "description")]
    assert "LOCA_NATE" in rep.to_markdown()
