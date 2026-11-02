"""SHACL shapes for AGS4 data expressed with the data model in :mod:`.ontology`.

One ``sh:NodeShape`` per GROUP (targeting the group's class) and one
``sh:PropertyShape`` per HEADING occurrence. What is checked, and at what
severity:

=================================  ==========  =============================================
Check                              Severity    Source
=================================  ==========  =============================================
at most one literal per field      Violation   AGS file structure (one VARIABLE per FIELD)
REQUIRED field present (*R / R)    Violation   Rule 10b
unique combination of KEY fields   Violation   Rule 10a (SPARQL constraint)
parent link targets parent group   Violation   Rule 10c
key fields shared with the parent  Violation   Rule 10c (SPARQL constraint)
match the parent record
single row in PROJ / TRAN          Violation   Rules 13, 14 (derived from the rule text)
value of the suggested type        Warning     the dictionary TYPE is a suggestion; files may
(number, date, Y/N...)                         declare another TYPE (Rule 8)
exact suggested format (e.g. 2DP)  Warning     as above
standard abbreviation / unit /     Warning     Rules 15, 16, 17 - non-standard values are
data type code                                 allowed when defined in ABBR / UNIT / TYPE
=================================  ==========  =============================================

KEY fields may be null (Rule 10a) so they are not ``sh:minCount 1`` unless
also REQUIRED. Rules that depend on what a particular file declares (its TYPE
and UNIT rows, ABBR/UNIT/TYPE groups: Rules 8, 15, 16, 17) are checked by
:func:`ags_rdf.convert.check_file` when an AGS file is converted.
"""

from __future__ import annotations

import hashlib
import re

from rdflib import BNode, OWL, RDF, RDFS, SH, SKOS, XSD, Graph, Literal, URIRef

from ..datatypes import alternation, codes_pattern, type_spec
from ..model import Group, Heading
from .common import BuildContext

SINGLE_ROW = re.compile(r"contain the (\w+) GROUP which shall contain only one data row", re.I)


class ShapesBuilder:
    def __init__(self, ctx: BuildContext):
        self.ctx = ctx
        self.d = ctx.dictionary
        self.iris = ctx.iris

    def build(self) -> Graph:
        d, iris, ctx = self.d, self.iris, self.ctx
        g = ctx.new_graph()
        sg = iris.shapes_graph
        ctx.describe_document(
            g, sg, OWL.Ontology, f"AGS {d.version} SHACL shapes",
            f"SHACL shapes validating AGS {d.version} data expressed in RDF with the AGS {d.version} "
            "data model: one node shape per GROUP and one property shape per HEADING. Violations "
            "implement the AGS rules; warnings flag departures from suggested types and standard "
            "abbreviations, units and types.", d.sources.get("dictionary", []))
        g.add((sg, OWL.imports, iris.ontology))
        for prefix, ns in (("ags", iris.AGS), ("agso", iris.AGSO), ("rdf", RDF)):
            decl = self._bnode(sg, "declare", prefix)
            g.add((sg, SH.declare, decl))
            g.add((decl, SH.prefix, Literal(prefix)))
            g.add((decl, SH.namespace, Literal(str(ns), datatype=XSD.anyURI)))

        single_row = {m.group(1).upper(): ref for ref, r in d.rules.items()
                      if (m := SINGLE_ROW.search(r.description))}
        for grp in d.groups.values():
            self._group(g, grp, single_row.get(grp.code))
        return g

    # ------------------------------------------------------------------ group
    def _group(self, g: Graph, grp: Group, single_row_rule: str | None) -> None:
        iris, ctx = self.iris, self.ctx
        ns = iris.node_shape(grp.code)
        g.add((ns, RDF.type, SH.NodeShape))
        g.add((ns, SH.targetClass, iris.group_class(grp.code)))
        g.add((ns, SH.name, Literal(grp.code)))
        g.add((ns, SH.description, ctx.text(grp.description or grp.code)))
        g.add((ns, RDFS.isDefinedBy, iris.shapes_graph))
        g.add((ns, iris.AGSO.dictionaryEntry, iris.group_concept(grp.code)))
        for ref in re.findall(r"Rule\s*(\d+[a-z]?)", grp.status_text):
            if ref in self.d.rules:
                g.add((ns, iris.AGSO.rule, iris.rule(ref)))
        if grp.is_deprecated:
            g.add((ns, OWL.deprecated, Literal(True)))

        for h in grp.headings:
            self._heading(g, ns, grp, h)
        if grp.parent and grp.parent in self.d.groups:
            self._parent(g, ns, grp)
        if grp.keys:
            self._key_uniqueness(g, ns, grp)
        if single_row_rule:
            self._single_row(g, ns, grp, single_row_rule)

    # ---------------------------------------------------------------- heading
    def _heading(self, g: Graph, ns: URIRef, grp: Group, h: Heading) -> None:
        iris, ctx, d = self.iris, self.ctx, self.d
        ps = iris.property_shape(grp.code, h.code)
        path = iris.heading_property(h.code)
        spec = type_spec(h.data_type)
        g.add((ns, SH.property, ps))
        g.add((ps, RDF.type, SH.PropertyShape))
        g.add((ps, SH.path, path))
        g.add((ps, SH.name, Literal(h.code)))
        if h.description:
            g.add((ps, SH.description, ctx.text(h.description)))
        g.add((ps, SH.order, Literal(h.order)))
        g.add((ps, SH.maxCount, Literal(1)))
        g.add((ps, SH.nodeKind, SH.Literal))
        if h.is_required:
            g.add((ps, SH.minCount, Literal(1)))
            g.add((ps, iris.AGSO.rule, iris.rule("10b")))
        if h.is_key:
            g.add((ps, iris.AGSO.rule, iris.rule("10a")))
        if spec.datatypes:
            # The dictionary type is only *suggested*: a file may declare another TYPE (Rule 8),
            # so a value outside its value space is a warning here. ags_rdf.convert checks values
            # against the TYPE each file actually declares.
            ts = iris.property_shape(grp.code, h.code, "-type")
            self._warning(g, ns, ts, path,
                          f"{h.code}: value is not of the suggested type {h.data_type} "
                          f"({self._family(spec)}). This is allowed if the file's TYPE row declares "
                          "another type (Rule 8).")
            if len(spec.datatypes) == 1 and not spec.values:
                g.add((ts, SH.datatype, spec.datatypes[0]))
            else:
                g.add((ts, SH.node, self._value_shape(g, spec)))
        # documentation / links
        if h.example:
            g.add((ps, SKOS.example, Literal(h.example)))
        if h.status:
            g.add((ps, iris.AGSO.headingStatus, Literal(h.status)))
        g.add((ps, iris.AGSO.isKey, Literal(h.is_key)))
        g.add((ps, iris.AGSO.isRequired, Literal(h.is_required)))
        g.add((ps, iris.AGSO.dictionaryEntry, iris.heading_concept(h.code)))
        if h.data_type:
            g.add((ps, iris.AGSO.dataType, iris.data_type(h.data_type)))
        if h.unit:
            g.add((ps, iris.AGSO.suggestedUnit, iris.unit(h.unit) if h.unit in d.units else Literal(h.unit)))
        if h.is_deprecated:
            g.add((ps, OWL.deprecated, Literal(True)))

        # warnings
        if spec.format_pattern:
            self._warning(g, ns, iris.property_shape(grp.code, h.code, "-format"), path,
                          f"{h.code}: value is not in the suggested format {h.data_type} "
                          f"({spec.format_label}). This is allowed if the file's TYPE row declares "
                          "another type (Rule 8).", pattern=spec.format_pattern)
        pattern, list_iri, what, rule = self._standard_values(h)
        if pattern:
            ws = iris.property_shape(grp.code, h.code, "-codes")
            self._warning(g, ns, ws, path,
                          f"{h.code}: value is not a standard AGS {d.version} {what}. Non-standard "
                          f"values must be defined in the file (Rule {rule}).", pattern=pattern)
            g.add((ws, iris.AGSO.rule, iris.rule(rule)))
        if list_iri is not None:
            g.add((ps, iris.AGSO.abbreviationList, list_iri))

    def _standard_values(self, h: Heading) -> tuple[str | None, URIRef | None, str, str]:
        """Warning-level pattern of standard values for PA, PU and PT headings.

        Contaminant codes (ELRG_CODE/ERES_CODE) are a large, frequently extended
        register, so they get no pattern.
        """
        d, iris = self.d, self.iris
        limit = self.ctx.settings.max_pattern_codes
        if h.data_type == "PA" and h.code in d.abbreviations:
            codes = [a.code for a in d.abbreviations[h.code]]
            pattern = codes_pattern(codes) if len(codes) <= limit else None
            return pattern, iris.abbreviation_list(h.code), f"abbreviation for {h.code}", "16"
        if h.data_type == "PU" and d.units and len(d.units) <= limit:
            return f"^({alternation(d.units)})$", None, "unit", "15"
        if h.data_type == "PT" and d.data_types:
            fixed = [t for t in d.data_types if not t.startswith("n")]
            return f"^({alternation(fixed)}|[0-9]+(DP|SF|SCI))$", None, "data type", "17"
        return None, None, "", ""

    # ----------------------------------------------------------------- parent
    def _parent(self, g: Graph, ns: URIRef, grp: Group) -> None:
        iris, ctx, d = self.iris, self.ctx, self.d
        parent = d.groups[grp.parent]
        ps = iris.parent_shape(grp.code)
        g.add((ns, SH.property, ps))
        g.add((ps, RDF.type, SH.PropertyShape))
        g.add((ps, SH.path, iris.AGSO.parent))
        g.add((ps, SH.name, Literal("parent")))
        g.add((ps, SH.description, ctx.text(f"The {parent.code} ({parent.description}) record this "
                                             f"{grp.code} record belongs to (Rule 10c).")))
        g.add((ps, SH["class"], iris.group_class(parent.code)))
        g.add((ps, SH.maxCount, Literal(1)))
        g.add((ps, iris.AGSO.rule, iris.rule("10c")))

        shared = [h.code for h in parent.keys if grp.heading(h.code) is not None]
        if not shared:
            return
        # (SHACL-SPARQL constraints may not use VALUES, hence FILTER ... IN)
        paths = ", ".join(f"ags:{c}" for c in shared)
        self._sparql(g, ns, iris.SH[f"{grp.code}-parent-keys"],
                     f"Key field {{?path}} = {{?value}} has no matching {parent.code} parent record (Rule 10c)",
                     f"""SELECT $this ?path ?value WHERE {{
    $this ?path ?value .
    FILTER (?path IN ({paths}))
    FILTER (STR(?value) != "")
    FILTER NOT EXISTS {{
        $this agso:parent ?parent .
        ?parent ?path ?parentValue .
        FILTER (STR(?parentValue) = STR(?value))
    }}
}}""")

    # ------------------------------------------------------------------- keys
    def _key_uniqueness(self, g: Graph, ns: URIRef, grp: Group) -> None:
        """Rule 10a as two SPARQL constraints, written so that pySHACL/rdflib stays fast.

        * ``<G>-key``: rows whose KEY fields all have values - a plain join on the
          key values, so candidate duplicates are found through the index;
        * ``<G>-key-null``: rows with a null KEY field (allowed by Rule 10a) - compared
          with every row of the group, but guarded so it costs nothing otherwise.

        The duplicate is named ``?xother`` (not ``?other``) on purpose: rdflib orders
        triple patterns lexically, and this makes it evaluate the ``$this`` patterns
        (whose subject is pre-bound) before looking for other rows.
        """
        keys = [h.code for h in grp.keys]
        message = (f"Another {grp.code} record has the same combination of KEY fields "
                   f"({', '.join(keys)}): {{?xother}} (Rule 10a)")
        # Join on the group's own keys (e.g. MOND_DTIM), which are selective; keys inherited
        # from parent groups (LOCA_ID, SAMP_ID...) are often shared by many rows, so they are
        # only checked for the candidates found.
        own = [k for k in keys if k.startswith(grp.code + "_")] or keys
        this = "".join(f"    $this ags:{k} ?v{i} .\n" for i, k in enumerate(keys))
        other = "".join(f"    ?xother ags:{k} ?v{i} .\n" for i, k in enumerate(keys) if k in own)
        inherited = "".join(f"    FILTER EXISTS {{ ?xother ags:{k} ?v{i} }}\n"
                            for i, k in enumerate(keys) if k not in own)
        self._sparql(g, ns, self.iris.SH[f"{grp.code}-key"], message,
                     f"""SELECT $this ?xother WHERE {{
{this}{other}    FILTER (?xother != $this)
{inherited}    FILTER EXISTS {{ ?xother a ags:{grp.code} }}
}}""")
        guard = " || ".join(f"NOT EXISTS {{ $this ags:{k} ?n{i} }}" for i, k in enumerate(keys))
        optional = "".join(f"    OPTIONAL {{ $this ags:{k} ?a{i} }} OPTIONAL {{ ?xother ags:{k} ?b{i} }}\n"
                           for i, k in enumerate(keys))
        same = " && ".join(f'COALESCE(STR(?a{i}), "") = COALESCE(STR(?b{i}), "")' for i in range(len(keys)))
        self._sparql(g, ns, self.iris.SH[f"{grp.code}-key-null"], message,
                     f"""SELECT $this ?xother WHERE {{
    {{ FILTER ({guard}) }}
    ?xother a ags:{grp.code} .
    FILTER (?xother != $this)
{optional}    FILTER ({same})
}}""")

    def _single_row(self, g: Graph, ns: URIRef, grp: Group, rule: str) -> None:
        c = self._sparql(g, ns, self.iris.SH[f"{grp.code}-single-row"],
                         f"A data file shall contain only one {grp.code} data row (Rule {rule})",
                         f"""SELECT $this ?other WHERE {{
    ?other a ags:{grp.code} .
    FILTER (?other != $this)
}}""")
        g.add((c, self.iris.AGSO.rule, self.iris.rule(rule)))

    @staticmethod
    def _family(spec) -> str:
        from .. import datatypes as dts

        if spec.values:
            return "one of " + ", ".join(spec.values)
        if set(spec.datatypes) <= set(dts.NUMERIC):
            return "a number"
        if set(spec.datatypes) == set(dts.DATETIME):
            return "an ISO 8601 date/time"
        if spec.datatypes == dts.TEXT:
            return "text"
        return "a " + " or ".join(str(d).split("#")[-1] for d in spec.datatypes)

    # ------------------------------------------------------------ value shapes
    VALUE_SHAPE_NAMES = {"NUMERIC": "NumericValue", "DATETIME": "DateTimeValue",
                         "XN": "TextOrNumericValue", "T": "ElapsedTimeValue", "YN": "YesNoValue"}

    def _value_shape(self, g: Graph, spec) -> URIRef:
        """A shared node shape for a value space allowing several datatypes (or a value list)."""
        from .. import datatypes as dts

        key = ("NUMERIC" if spec.datatypes == dts.NUMERIC else "DATETIME" if spec.datatypes == dts.DATETIME
               else spec.code if spec.code in self.VALUE_SHAPE_NAMES else "_".join(
                   str(d).split("#")[-1] for d in spec.datatypes))
        iri = self.iris.SH[self.VALUE_SHAPE_NAMES.get(key, key + "Value")]
        if (iri, RDF.type, SH.NodeShape) in g:
            return iri
        names = ", ".join("xsd:" + str(d).split("#")[-1] for d in spec.datatypes)
        g.add((iri, RDF.type, SH.NodeShape))
        g.add((iri, RDFS.isDefinedBy, self.iris.shapes_graph))
        g.add((iri, SH.name, Literal(self.VALUE_SHAPE_NAMES.get(key, key + "Value"))))
        g.add((iri, SH.description, self.ctx.text(f"A literal of one of the datatypes {names}"
                                                  + (f", with a value in {list(spec.values)}" if spec.values else "")
                                                  + ".")))
        g.add((iri, SH.nodeKind, SH.Literal))
        self._or(g, iri, [((SH.datatype, dt),) for dt in spec.datatypes])
        if spec.values:
            members = [Literal(v) for v in spec.values]
            if XSD.boolean in spec.datatypes:
                members += [Literal(True), Literal(False)]
            self._list(g, iri, SH["in"], members)
        return iri

    # ---------------------------------------------------------------- helpers
    def _sparql(self, g: Graph, ns: URIRef, iri: URIRef, message: str, select: str) -> URIRef:
        g.add((ns, SH.sparql, iri))
        g.add((iri, RDF.type, SH.SPARQLConstraint))
        g.add((iri, SH.message, Literal(message)))
        g.add((iri, SH.prefixes, self.iris.shapes_graph))
        g.add((iri, SH.select, Literal(select)))
        return iri

    def _warning(self, g: Graph, ns: URIRef, iri: URIRef, path: URIRef, message: str,
                 pattern: str | None = None) -> None:
        g.add((ns, SH.property, iri))
        g.add((iri, RDF.type, SH.PropertyShape))
        g.add((iri, SH.path, path))
        g.add((iri, SH.severity, SH.Warning))
        g.add((iri, SH.message, Literal(message)))
        if pattern:
            g.add((iri, SH.pattern, Literal(pattern)))

    @staticmethod
    def _bnode(*seed) -> BNode:
        """Deterministic blank node, so repeated builds give identical N-Triples."""
        return BNode("b" + hashlib.sha1("|".join(map(str, seed)).encode()).hexdigest()[:20])

    def _list(self, g: Graph, s, p, items) -> None:
        items = list(items)
        cells = [self._bnode(s, p, "list", i) for i in range(len(items))]
        for i, (cell, item) in enumerate(zip(cells, items, strict=True)):
            g.add((cell, RDF.first, item))
            g.add((cell, RDF.rest, cells[i + 1] if i + 1 < len(cells) else RDF.nil))
        g.add((s, p, cells[0] if cells else RDF.nil))

    def _or(self, g: Graph, s, alternatives) -> None:
        nodes = []
        for i, alt in enumerate(alternatives):
            n = self._bnode(s, "or", i)
            for p, o in alt:
                g.add((n, p, o))
            nodes.append(n)
        self._list(g, s, SH["or"], nodes)
