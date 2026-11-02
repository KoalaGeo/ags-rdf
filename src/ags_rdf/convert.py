"""Convert AGS4 data files (``.ags``) to RDF using the generated data model.

Mapping (the same model the SHACL shapes validate):

* each DATA row -> a record ``<{data_base}{GROUP}/{key}/{key}...>`` typed with
  the group's class (``ags:LOCA``); the IRI is built from the row's KEY fields,
  falling back to the row number when a group has no keys or a key combination
  repeats;
* each non-null VARIABLE -> one triple ``<record> ags:<HEADING> literal``; the
  literal is typed with the file's own TYPE (and UNIT for dates), because the
  file's TYPE/UNIT rows take precedence over the dictionary's suggestions (Rule 8);
* each record -> ``agso:parent`` the row of its PARENT GROUP whose KEY fields it
  shares (Rule 10c); no link is made when there is no single match, so the
  shapes report the problem;
* the file -> an ``agso:DataFile`` with one ``agso:FieldDefinition`` per heading
  recording the UNIT and TYPE rows;
* groups/headings not in the dictionary (user defined, Rule 18) -> terms under
  ``{data_base}def/``, labelled from the file's DICT group when present.

Values are not "corrected": anything that does not fit its declared type stays a
plain string so that validation reports it.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from rdflib import DCTERMS, OWL, RDF, RDFS, XSD, Graph, Literal, Namespace, URIRef

from .builders.common import BuildContext
from .iris import local_name
from .datatypes import type_spec
from .model import Dictionary, Issue
from .releases import Release, version_key
from .values import to_literal

log = logging.getLogger(__name__)

DESCRIPTORS = ("GROUP", "HEADING", "UNIT", "TYPE", "DATA")


# ------------------------------------------------------------------ reading
@dataclass
class AgsTable:
    group: str
    line: int
    headings: list[str] = field(default_factory=list)
    units: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    rows: list[tuple[int, list[str]]] = field(default_factory=list)  # (line number, values)

    def column(self, heading: str) -> int | None:
        return self.headings.index(heading) if heading in self.headings else None

    def records(self) -> list[dict[str, str]]:
        return [dict(zip(self.headings, values, strict=False)) for _, values in self.rows]


@dataclass
class AgsFile:
    path: Path
    tables: dict[str, AgsTable]
    issues: list[str] = field(default_factory=list)

    def value(self, group: str, heading: str) -> str | None:
        t = self.tables.get(group)
        if not t or not t.rows:
            return None
        i = t.column(heading)
        return t.rows[0][1][i] if i is not None and i < len(t.rows[0][1]) else None

    @property
    def ags_version(self) -> str | None:
        return (self.value("TRAN", "TRAN_AGS") or "").strip() or None


def read_ags(path: Path) -> AgsFile:
    """Parse an AGS4 file into tables (no dictionary needed)."""
    path = Path(path)
    raw = path.read_bytes()
    issues: list[str] = []
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
        issues.append("File is not UTF-8; read as Windows-1252")
    if any(ord(c) > 127 for c in text):
        issues.append("File contains non-ASCII characters (Rule 1)")

    tables: dict[str, AgsTable] = {}
    current: AgsTable | None = None
    for lineno, rec in enumerate(csv.reader(io.StringIO(text)), start=1):
        if not rec or all(not c.strip() for c in rec):
            continue
        kind, values = rec[0].strip().upper(), rec[1:]
        if kind not in DESCRIPTORS:
            issues.append(f"line {lineno}: unknown data descriptor {rec[0]!r} (Rule 3)")
            continue
        if kind == "GROUP":
            name = values[0].strip() if values else ""
            if name in tables:
                issues.append(f"line {lineno}: group {name} appears more than once; rows are appended")
                current = tables[name]
            else:
                current = tables[name] = AgsTable(name, lineno)
            continue
        if current is None:
            issues.append(f"line {lineno}: {kind} row before any GROUP row")
            continue
        if kind == "HEADING":
            current.headings = [v.strip() for v in values]
        elif kind == "UNIT":
            current.units = [v.strip() for v in values]
        elif kind == "TYPE":
            current.types = [v.strip() for v in values]
        else:
            if len(values) != len(current.headings):
                issues.append(f"line {lineno}: {current.group} DATA row has {len(values)} values for "
                              f"{len(current.headings)} headings")
            current.rows.append((lineno, values))
    for t in tables.values():
        for what, row in (("UNIT", t.units), ("TYPE", t.types)):
            if len(row) != len(t.headings):
                issues.append(f"{t.group}: {what} row has {len(row)} entries for {len(t.headings)} headings "
                              "(Rule 2b)")
    return AgsFile(path, tables, issues)


def pick_release(releases: dict[str, Release], declared: str | None) -> Release:
    """The dictionary release for a file's TRAN_AGS value: exact match, else newest of that family."""
    if declared in releases:
        return releases[declared]
    if declared:
        family = [v for v in releases if v == declared or v.startswith(declared + ".")]
        if family:
            return releases[max(family, key=version_key)]
    return releases[max(releases, key=version_key)]


# --------------------------------------------------------------- converting
class AgsConverter:
    def __init__(self, ctx: BuildContext, data_base: str):
        if not data_base.endswith(("/", "#")):
            data_base += "/"
        self.ctx = ctx
        self.d: Dictionary = ctx.dictionary
        self.iris = ctx.iris
        self.base = data_base
        self.UD = Namespace(data_base + "def/")  # user-defined groups and headings
        self.known_headings = set(self.d.heading_occurrences())
        self.known_types = set(self.d.data_types) | {h.data_type for h in self.d.headings()}

    def convert(self, ags: AgsFile) -> tuple[Graph, list[str]]:
        g = self.ctx.new_graph({"data": self.base, "ud": str(self.UD)})
        issues = list(ags.issues)
        iris, AGSO = self.iris, self.iris.AGSO
        file_node = URIRef(self.base)
        g.add((file_node, RDF.type, AGSO.DataFile))
        g.add((file_node, DCTERMS.source, Literal(ags.path.name)))
        g.add((file_node, DCTERMS.conformsTo, iris.version_iri(iris.ontology, self.d.version)))
        if ags.ags_version:
            g.add((file_node, AGSO.agsVersion, Literal(ags.ags_version)))
        if ags.ags_version and not self.d.version.startswith(ags.ags_version.split(".")[0]):
            issues.append(f"File declares AGS {ags.ags_version} but is converted with the "
                          f"{self.d.version} dictionary")

        user_dict = self._dict_definitions(ags)
        record_iris: dict[str, list[URIRef]] = {}
        for table in ags.tables.values():
            record_iris[table.group] = self._table(g, file_node, table, user_dict, issues)
        self._link_parents(g, ags, record_iris, issues)
        return g, issues

    # ------------------------------------------------------------- tables
    def _group_class(self, g: Graph, group: str, user_dict: dict) -> URIRef:
        if group in self.d.groups:
            return self.iris.group_class(group)
        c = self.UD[group]
        if (c, RDF.type, OWL.Class) not in g:
            g.add((c, RDF.type, OWL.Class))
            g.add((c, RDFS.subClassOf, self.iris.AGSO.Record))
            g.add((c, RDFS.label, Literal(user_dict.get((group, None), group))))
            g.add((c, self.iris.AGSO.userDefined, Literal(True)))
        return c

    def _property(self, g: Graph, group: str, heading: str, user_dict: dict) -> URIRef:
        if heading in self.known_headings:
            return self.iris.heading_property(heading)
        p = self.UD[heading]
        if (p, RDF.type, OWL.DatatypeProperty) not in g:
            g.add((p, RDF.type, OWL.DatatypeProperty))
            g.add((p, RDFS.label, Literal(user_dict.get((group, heading), heading))))
            g.add((p, self.iris.AGSO.userDefined, Literal(True)))
        return p

    def _table(self, g: Graph, file_node: URIRef, t: AgsTable, user_dict: dict, issues: list[str]) -> list[URIRef]:
        iris, AGSO = self.iris, self.iris.AGSO
        cls = self._group_class(g, t.group, user_dict)
        if t.group not in self.d.groups and (t.group, None) not in user_dict:
            issues.append(f"{t.group}: group is neither in the AGS {self.d.version} dictionary nor in DICT (Rule 18)")
        props = [self._property(g, t.group, h, user_dict) for h in t.headings]
        for j, h in enumerate(t.headings):
            fd = URIRef(f"{self.base}field/{t.group}/{local_name(h)}")
            g.add((file_node, AGSO.field, fd))
            g.add((fd, RDF.type, AGSO.FieldDefinition))
            g.add((fd, AGSO.group, cls))
            g.add((fd, AGSO.property, props[j]))
            g.add((fd, AGSO.position, Literal(j + 1)))
            unit = t.units[j] if j < len(t.units) else ""
            dtype = t.types[j] if j < len(t.types) else ""
            if unit:
                g.add((fd, AGSO.unit, iris.unit(unit) if unit in self.d.units else Literal(unit)))
            if dtype:
                g.add((fd, AGSO.type, iris.data_type(dtype) if dtype in self.known_types else Literal(dtype)))
            if h not in self.known_headings and (t.group, h) not in user_dict:
                issues.append(f"{t.group}: heading {h} is neither in the dictionary nor in DICT (Rule 9)")

        grp = self.d.groups.get(t.group)
        keys = [h.code for h in grp.keys if h.code in t.headings] if grp else []
        key_cols = [t.headings.index(k) for k in keys]
        used: set[URIRef] = set()
        out = []
        for n, (_lineno, values) in enumerate(t.rows, start=1):
            key_vals = [values[c].strip() if c < len(values) else "" for c in key_cols]
            if key_vals and any(key_vals):
                path = "/".join(local_name(v) if v else "_" for v in key_vals)
            else:
                path = f"row-{n}"
            rec = URIRef(f"{self.base}{t.group}/{path}")
            if rec in used:
                rec = URIRef(f"{self.base}{t.group}/{path}-row-{n}")
            used.add(rec)
            out.append(rec)
            g.add((rec, RDF.type, cls))
            g.add((rec, AGSO.dataFile, file_node))
            for j, value in enumerate(values[:len(t.headings)]):
                dtype = t.types[j] if j < len(t.types) else ""
                unit = t.units[j] if j < len(t.units) else ""
                lit = to_literal(value, dtype, unit)
                if lit is not None:
                    g.add((rec, props[j], lit))
        return out

    # ------------------------------------------------------------- parents
    def _link_parents(self, g: Graph, ags: AgsFile, record_iris: dict, issues: list[str]) -> None:
        for t in ags.tables.values():
            grp = self.d.groups.get(t.group)
            if not grp or not grp.parent:
                continue
            parent_table = ags.tables.get(grp.parent)
            if parent_table is None:
                if t.rows:
                    issues.append(f"{t.group}: parent group {grp.parent} is not in the file (Rule 10c)")
                continue
            parent = self.d.groups[grp.parent]
            shared = [h.code for h in parent.keys if h.code in t.headings and h.code in parent_table.headings]
            index: dict[tuple, list[URIRef]] = {}
            for rec, row in zip(record_iris[grp.parent], parent_table.records(), strict=True):
                index.setdefault(tuple(row.get(k, "").strip() for k in shared), []).append(rec)
            for rec, row in zip(record_iris[t.group], t.records(), strict=True):
                key = tuple(row.get(k, "").strip() for k in shared)
                matches = index.get(key, []) if shared else record_iris[grp.parent]
                if len(matches) == 1:
                    g.add((rec, self.iris.AGSO.parent, matches[0]))

    @staticmethod
    def _dict_definitions(ags: AgsFile) -> dict:
        """(group, heading or None) -> description, from the file's DICT group."""
        out = {}
        t = ags.tables.get("DICT")
        for r in t.records() if t else []:
            grp, hdng, desc = r.get("DICT_GRP", ""), r.get("DICT_HDNG", ""), r.get("DICT_DESC", "")
            if r.get("DICT_TYPE", "").upper() == "GROUP":
                out[(grp, None)] = desc or grp
            elif hdng:
                out[(grp, hdng)] = desc or hdng
        return out


# ------------------------------------------------------------ file checks
def check_file(ags: AgsFile, d: Dictionary) -> list[Issue]:
    """Rules that depend on what this file declares, which the dictionary shapes cannot see.

    * Rule 8  - each value fits the TYPE declared in the file's TYPE row
      (errors for the wrong kind of value, warnings for the wrong number of decimal places)
    * Rule 15 - units in UNIT rows and in PU fields are listed in the UNIT group
    * Rule 16 - codes in PA fields (split on TRAN_RCON, default "+") are listed in ABBR
    * Rule 17 - types in TYPE rows are listed in the TYPE group
    * Rules 13/14/15/17 - the PROJ, TRAN, UNIT and TYPE groups are present
    * Rules 10a/10c - repeated KEY combinations and rows without a parent row, with line
      numbers (the shapes check these too, on the RDF)
    """
    issues: list[Issue] = []
    src = ags.path.name

    def add(sev, rule, msg, group=None, heading=None, code=None):
        issues.append(Issue(sev, f"rule-{rule}", msg, source=src, group=group, heading=heading, code=code))

    for grp, rule in (("PROJ", "13"), ("TRAN", "14"), ("UNIT", "15"), ("TYPE", "17")):
        if grp not in ags.tables:
            add("error", rule, f"the {grp} group is missing", group=grp)

    rcon = (ags.value("TRAN", "TRAN_RCON") or "+").strip() or "+"
    units = {r.get("UNIT_UNIT", "") for r in ags.tables["UNIT"].records()} if "UNIT" in ags.tables else set()
    types = {r.get("TYPE_TYPE", "") for r in ags.tables["TYPE"].records()} if "TYPE" in ags.tables else set()
    abbr: dict[str, set[str]] = {}
    for r in ags.tables["ABBR"].records() if "ABBR" in ags.tables else []:
        abbr.setdefault(r.get("ABBR_HDNG", ""), set()).add(r.get("ABBR_CODE", ""))

    for t in ags.tables.values():
        for j, h in enumerate(t.headings):
            unit = t.units[j] if j < len(t.units) else ""
            dtype = t.types[j] if j < len(t.types) else ""
            if unit and "UNIT" in ags.tables and unit not in units:
                add("error", "15", f"unit {unit!r} of {t.group}.{h} is not listed in the UNIT group",
                    t.group, h, unit)
            if dtype and "TYPE" in ags.tables and dtype not in types:
                add("error", "17", f"type {dtype!r} of {t.group}.{h} is not listed in the TYPE group",
                    t.group, h, dtype)
            spec = type_spec(dtype)
            m = re.match(r"^(\d+)DP$", dtype)
            bad, places = [], []
            for lineno, values in t.rows:
                v = values[j].strip() if j < len(values) else ""
                if not v:
                    continue
                lit = to_literal(v, dtype, unit)
                if spec.datatypes and lit is not None and lit.datatype not in spec.datatypes \
                        and not (lit.datatype is None and XSD.string in spec.datatypes):
                    bad.append((lineno, v))
                elif spec.values and v not in spec.values:
                    bad.append((lineno, v))
                elif m and lit is not None and lit.datatype is not None and not re.fullmatch(
                        spec.format_pattern, v):
                    places.append((lineno, v))
                if dtype == "PA" and "ABBR" in ags.tables:
                    for code in v.split(rcon):
                        if code and code not in abbr.get(h, set()):
                            add("error", "16", f"line {lineno}: {t.group}.{h} code {code!r} is not listed in "
                                "the ABBR group", t.group, h, code)
                if dtype == "PU" and "UNIT" in ags.tables and v not in units:
                    add("error", "15", f"line {lineno}: {t.group}.{h} unit {v!r} is not listed in the UNIT "
                        "group", t.group, h, v)
            if bad:
                add("error", "8", f"{t.group}.{h}: {len(bad)} value(s) do not fit the declared TYPE {dtype} "
                    f"(first: line {bad[0][0]} {bad[0][1]!r})", t.group, h)
            if places:
                add("warning", "8", f"{t.group}.{h}: {len(places)} value(s) do not have the {m.group(1)} decimal "
                    f"places of TYPE {dtype} (first: line {places[0][0]} {places[0][1]!r})", t.group, h)
    # Rule 10a: unique KEY combinations; Rule 10c: KEY entries exist in the parent group
    for t in ags.tables.values():
        grp = d.groups.get(t.group)
        if grp is None:
            continue
        keys = [h.code for h in grp.keys if h.code in t.headings]
        seen_keys: dict[tuple, int] = {}
        for (lineno, _), rec in zip(t.rows, t.records(), strict=True):
            k = tuple(rec.get(h, "").strip() for h in keys)
            if keys and k in seen_keys:
                add("error", "10a", f"line {lineno}: {t.group} repeats the KEY fields of line {seen_keys[k]} "
                    f"({', '.join(f'{h}={v!r}' for h, v in zip(keys, k, strict=True))})", t.group)
            seen_keys.setdefault(k, lineno)
        parent_table = ags.tables.get(grp.parent) if grp.parent else None
        if parent_table is None:
            continue
        shared = [h.code for h in d.groups[grp.parent].keys if h.code in t.headings and h.code in parent_table.headings]
        parent_keys = {tuple(r.get(h, "").strip() for h in shared) for r in parent_table.records()}
        missing = [(lineno, k) for (lineno, _), rec in zip(t.rows, t.records(), strict=True)
                   if shared and any(k := tuple(rec.get(h, "").strip() for h in shared)) and k not in parent_keys]
        if missing:
            add("error", "10c", f"{t.group}: {len(missing)} row(s) have no matching {grp.parent} row (first: line "
                f"{missing[0][0]}, {', '.join(f'{h}={v!r}' for h, v in zip(shared, missing[0][1], strict=True))})",
                t.group)
    # de-duplicate repeated code/unit findings
    seen, out = set(), []
    for i in issues:
        k = (i.category, i.group, i.heading, i.code)
        if i.category in ("rule-15", "rule-16") and k in seen:
            continue
        seen.add(k)
        out.append(i)
    return out


def declared_type_shapes(ags: AgsFile, d: Dictionary, iris) -> set[URIRef]:
    """Warning shapes about the *suggested* type that do not apply to this file.

    Where the file's TYPE row declares a different type from the dictionary's
    suggestion (allowed by Rule 8), the "not the suggested type/format" warnings
    are expected; :func:`check_file` checks values against the declared type instead.
    """
    out: set[URIRef] = set()
    for t in ags.tables.values():
        grp = d.groups.get(t.group)
        if grp is None:
            continue
        for j, h in enumerate(t.headings):
            occ = grp.heading(h)
            declared = t.types[j] if j < len(t.types) else ""
            if occ is not None and declared and declared != occ.data_type:
                out |= {iris.property_shape(t.group, h, "-format"), iris.property_shape(t.group, h, "-type")}
    return out


def default_data_base(path: Path) -> str:
    return f"https://example.org/ags/{local_name(Path(path).stem)}/"
