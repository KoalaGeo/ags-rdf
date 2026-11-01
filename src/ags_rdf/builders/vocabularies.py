"""SKOS vocabularies conforming to the VocPub profile (one ConceptScheme each).

Each vocabulary is a separate graph/file because VocPub (and VocExcel) require a
single ConceptScheme per file:

* ``dictionary``        GROUPs (top concepts) and HEADINGs (narrower concepts of
                        every group they appear in); group categories are Collections
* ``abbreviations``     standard abbreviations (ABBR pick lists), one Collection per heading
* ``units``             standard units (UNIT), one Collection per quantity type
* ``data-types``        data TYPEs; generic types (nDP) with the specific ones used (2DP)
* ``rules``             the AGS4 rules, sub-rules narrower than their main rule
* ``contaminant-codes`` ELRG/ERES contaminant & determinand codes

Add a vocabulary by writing a ``_build_<name>`` method and listing it in
:data:`VOCABULARIES`.
"""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import PROV, RDF, RDFS, SDO, SKOS, XSD, Graph, Literal, URIRef

from ..datatypes import generic_code, type_spec
from ..model import Dictionary
from ..namespaces import REGISTER_STATUS, STATUS
from .common import BuildContext


@dataclass(frozen=True)
class VocabSpec:
    name: str
    prefix: str
    title: str
    description: str


VOCABULARIES: list[VocabSpec] = [
    VocabSpec("dictionary", "agsdict", "AGS {v} Groups and Headings",
              "The GROUPs and HEADINGs of the AGS {v} data dictionary (Electronic Transfer of "
              "Geotechnical and Geoenvironmental Data). Groups are top concepts and each heading is a "
              "narrower concept of every group it appears in. Group categories are collections."),
    VocabSpec("abbreviations", "agsabbr", "AGS {v} Abbreviations",
              "The standard abbreviations (pick-list codes) of AGS {v} for headings of data type PA, "
              "one collection per heading. Only entries with status {statuses} are included."),
    VocabSpec("units", "agsunit", "AGS {v} Units",
              "The standard units of measurement of AGS {v} (UNIT group), grouped by quantity type. "
              "Only entries with status {statuses} are included."),
    VocabSpec("data-types", "agsdt", "AGS {v} Data Types",
              "The data TYPEs of AGS {v}. Generic types such as nDP are top concepts; the specific "
              "types used in the dictionary (e.g. 2DP) are narrower concepts."),
    VocabSpec("rules", "agsrule", "AGS {v} Rules",
              "The rules of the AGS {v} data format. Sub-rules (e.g. 10a) are narrower than their "
              "main rule (10)."),
    VocabSpec("contaminant-codes", "agselrg", "AGS {v} Contaminant and Determinand Codes",
              "Codes for chemical contaminants and determinands used in ELRG_CODE (AGS 4.1 onwards) and "
              "ERES_CODE (AGS 4.0). Only entries with status {statuses} are included."),
]


class VocabularyBuilder:
    def __init__(self, ctx: BuildContext):
        self.ctx = ctx
        self.d: Dictionary = ctx.dictionary
        self.iris = ctx.iris

    # ------------------------------------------------------------------ API
    def build_all(self) -> dict[str, Graph]:
        out = {}
        for spec in VOCABULARIES:
            g = getattr(self, "_build_" + spec.name.replace("-", "_"))(spec)
            if g is not None:
                out[spec.name] = g
        return out

    # -------------------------------------------------------------- helpers
    def _scheme(self, spec: VocabSpec, status: URIRef | None = None) -> tuple[Graph, URIRef]:
        v = self.d.version
        cs = self.iris.scheme(spec.name)
        g = self.ctx.new_graph({spec.prefix: str(self.iris.vocab_ns(spec.name))})
        statuses = ", ".join(s.title() for s in self.ctx.settings.register_statuses)
        rel_status = STATUS["deprecated"] if self.d.release.status == "deprecated" else status
        self.ctx.describe_document(g, cs, SKOS.ConceptScheme, spec.title.format(v=v),
                                   spec.description.format(v=v, statuses=statuses),
                                   self.d.sources.get(spec.name, []), rel_status)
        return g, cs

    def _concept(self, g: Graph, cs: URIRef, iri: URIRef, label: str, definition: str, *,
                 notation: str | None = None, alt: list[str] = (), top: bool = False,
                 broader: list[URIRef] = (), status: URIRef | None = None,
                 history: str | None = None, example: str | None = None,
                 source: str | None = None) -> URIRef:
        t = self.ctx.text
        g.add((iri, RDF.type, SKOS.Concept))
        g.add((iri, SKOS.inScheme, cs))
        # without it VocExcel writes "None" into "Is Defined By" and reads back <None>
        g.add((iri, RDFS.isDefinedBy, cs))
        g.add((iri, SKOS.prefLabel, t(label)))
        g.add((iri, SKOS.definition, t(definition or label)))
        for a in dict.fromkeys(alt):
            if a and a != label:
                g.add((iri, SKOS.altLabel, t(a)))
        if notation:
            g.add((iri, SKOS.notation, Literal(notation, datatype=XSD.token)))
        if top:
            g.add((iri, SKOS.topConceptOf, cs))
            g.add((cs, SKOS.hasTopConcept, iri))
        for b in broader:
            g.add((iri, SKOS.broader, b))
            g.add((b, SKOS.narrower, iri))
        if status is not None:
            g.add((iri, SDO.status, status))
        if history:
            g.add((iri, SKOS.historyNote, Literal(history)))
        if example:
            g.add((iri, SKOS.example, Literal(example)))
        if source:
            g.add((iri, PROV.wasDerivedFrom, self.ctx.source_url(source)))
        return iri

    def _collection(self, g: Graph, cs: URIRef, iri: URIRef, label: str, definition: str,
                    members: list[URIRef]) -> None:
        t = self.ctx.text
        g.add((iri, RDF.type, SKOS.Collection))
        g.add((iri, SKOS.inScheme, cs))
        g.add((iri, RDFS.isDefinedBy, cs))
        g.add((iri, SKOS.prefLabel, t(label)))
        g.add((iri, SKOS.definition, t(definition)))
        for m in members:
            g.add((iri, SKOS.member, m))

    def _changes_note(self, group: str, heading: str | None = None) -> str | None:
        entries = self.d.changes_for(group, heading)
        if heading is not None:  # a heading's changes may be logged against any group
            entries = [c for c in self.d.changes if c.heading == heading]
        if not entries:
            return None
        parts = []
        for c in entries:
            where = "" if heading is None or c.group == heading.split("_")[0] else f" in {c.group}"
            parts.append(f"AGS {c.version}: {c.action}{where}" + (f" - {c.comments}" if c.comments else ""))
        return "\n".join(dict.fromkeys(parts))

    @staticmethod
    def _register_history(date: str, status: str, comments: str) -> str:
        bits = [f"Status in the AGS register: {status}" + (f" ({date})" if date else "")]
        if comments:
            bits.append(comments)
        return ". ".join(bits)

    # ----------------------------------------------------------- dictionary
    def _build_dictionary(self, spec: VocabSpec) -> Graph:
        d, iris, agso = self.d, self.iris, self.iris.AGSO
        g, cs = self._scheme(spec, STATUS["stable"])
        src = d.release.groups_and_headings
        categories: dict[str, list[URIRef]] = {}

        for grp in d.groups.values():
            iri = iris.group_concept(grp.code)
            history = [x for x in (f"Group status: {grp.status_text}" if grp.status_text else None,
                                   self._changes_note(grp.code)) if x]
            self._concept(g, cs, iri, grp.description or grp.code, grp.description or grp.code,
                          notation=grp.code, alt=[grp.code], top=True,
                          status=STATUS["deprecated"] if grp.is_deprecated else STATUS["stable"],
                          history="\n".join(history) or None, source=src)
            if grp.notes:
                g.add((iri, SKOS.scopeNote, self.ctx.text(grp.notes)))
            if grp.rules_text:
                g.add((iri, SKOS.scopeNote, self.ctx.text("Group rules: " + grp.rules_text)))
            if grp.parent:
                g.add((iri, agso.parentGroup, iris.group_concept(grp.parent)))
            g.add((iri, agso.groupClass, iris.group_class(grp.code)))
            if grp.category:
                categories.setdefault(grp.category, []).append(iri)

        groups_of: dict[str, list] = {}
        for h in d.headings():
            groups_of.setdefault(h.code, []).append(h)
        for code, occ in groups_of.items():
            h = d.defining_occurrence(code)
            iri = iris.heading_concept(code)
            deprecated = all(o.is_deprecated or d.groups[o.group].is_deprecated for o in occ)
            self._concept(g, cs, iri, h.description or code, h.description or code, notation=code,
                          alt=[code], broader=[iris.group_concept(o.group) for o in occ],
                          status=STATUS["deprecated"] if deprecated else STATUS["stable"],
                          history=self._changes_note(h.group, code), example=h.example or None,
                          source=src)
            g.add((iri, agso.property, iris.heading_property(code)))
            if h.data_type:
                g.add((iri, agso.dataType, iris.data_type(h.data_type)))
            if h.unit:
                g.add((iri, agso.suggestedUnit, iris.unit(h.unit) if h.unit in d.units else Literal(h.unit)))

        for cat, members in categories.items():
            self._collection(g, cs, iris.category_collection(cat), cat,
                             f"AGS {d.version} groups in the category '{cat}'.", members)
        return g

    # -------------------------------------------------------- abbreviations
    def _build_abbreviations(self, spec: VocabSpec) -> Graph | None:
        d, iris = self.d, self.iris
        if not d.abbreviations:
            return None
        g, cs = self._scheme(spec, STATUS["stable"])
        src = d.sources["abbreviations"][0]
        occ = d.heading_occurrences()
        for heading, abbrs in d.abbreviations.items():
            members = []
            for a in abbrs:
                iri = iris.abbreviation(heading, a.code)
                self._concept(g, cs, iri, a.description or a.code, a.description or a.code,
                              notation=a.code, alt=[a.code], top=True,
                              status=REGISTER_STATUS.get(a.status.lower()),
                              history=self._register_history(a.date, a.status, a.comments), source=src)
                g.add((iri, iris.AGSO.heading, iris.heading_concept(heading)))
                members.append(iri)
            desc = d.defining_occurrence(heading).description if heading in occ else None
            col = iris.abbreviation_list(heading)
            self._collection(g, cs, col, f"{heading} abbreviations",
                             f"Standard AGS {d.version} abbreviations for the heading {heading}"
                             + (f" ({desc})." if desc else "."), members)
            g.add((col, iris.AGSO.heading, iris.heading_concept(heading)))
        return g

    # ---------------------------------------------------------------- units
    def _build_units(self, spec: VocabSpec) -> Graph | None:
        d, iris = self.d, self.iris
        if not d.units:
            return None
        g, cs = self._scheme(spec, STATUS["stable"])
        src = d.sources["units"][0]
        by_quantity: dict[str, list[URIRef]] = {}
        for u in d.units.values():
            iri = iris.unit(u.code)
            self._concept(g, cs, iri, u.description or u.code, u.description or u.code,
                          notation=u.code, alt=[u.code], top=True,
                          status=REGISTER_STATUS.get(u.status.lower()),
                          history=self._register_history(u.date, u.status, u.comments), source=src)
            by_quantity.setdefault(u.quantity or "Unclassified", []).append(iri)
        for q, members in by_quantity.items():
            self._collection(g, cs, iris.unit_collection(q), q, f"AGS {d.version} units of {q.lower()}.",
                             members)
        return g

    # ----------------------------------------------------------- data types
    def _build_data_types(self, spec: VocabSpec) -> Graph | None:
        d, iris = self.d, self.iris
        if not d.data_types:
            return None
        g, cs = self._scheme(spec, STATUS["stable"])
        src = d.sources["data-types"][0]
        for t in d.data_types.values():
            definition = t.description + (f". {t.notes}" if t.notes else "")
            history = None
            if t.defined_for:
                history = (f"data_types.json does not define {t.code} for AGS {d.release.family}, but the "
                           f"dictionary uses it; definition taken from the entry for "
                           f"{', '.join(t.defined_for)}.")
            self._concept(g, cs, iris.data_type(t.code), t.description or t.code, definition,
                          notation=t.code, alt=[t.code], top=True, status=STATUS["stable"],
                          history=history, source=src)
        used = sorted({h.data_type for h in d.headings() if h.data_type}, key=lambda c: (generic_code(c), c))
        for code in used:
            gen = generic_code(code)
            if gen == code:
                continue
            spec_ = type_spec(code)
            parent = d.data_types.get(gen)
            label = f"{code}: {spec_.format_label}" if spec_.format_label else code
            definition = (f"Data type {code}: {spec_.format_label}. A specific form of the generic type "
                          f"{gen}" + (f" ({parent.description})." if parent else "."))
            self._concept(g, cs, iris.data_type(code), label, definition, notation=code, alt=[code],
                          broader=[iris.data_type(gen)] if parent else [], top=parent is None,
                          status=STATUS["stable"], source=d.release.groups_and_headings)
        return g

    # ---------------------------------------------------------------- rules
    def _build_rules(self, spec: VocabSpec) -> Graph | None:
        d, iris = self.d, self.iris
        if not d.rules:
            return None
        g, cs = self._scheme(spec, STATUS["stable"])
        src = d.sources["rules"][0]
        for r in sorted(d.rules.values(), key=lambda r: r.order):
            parent = r.parent_ref if r.parent_ref in d.rules else None
            self._concept(g, cs, iris.rule(r.ref), f"Rule {r.ref}", r.description, notation=r.ref,
                          top=parent is None, broader=[iris.rule(parent)] if parent else [],
                          status=STATUS["stable"], source=src)
        return g

    # ----------------------------------------------------- contaminant codes
    def _build_contaminant_codes(self, spec: VocabSpec) -> Graph | None:
        d, iris = self.d, self.iris
        if not d.contaminant_codes:
            return None
        g, cs = self._scheme(spec, STATUS["stable"])
        src = d.sources["contaminant-codes"][0]
        for c in d.contaminant_codes.values():
            self._concept(g, cs, iris.contaminant_code(c.code), c.description or c.code,
                          c.description or c.code, notation=c.code, alt=[c.code], top=True,
                          status=REGISTER_STATUS.get(c.status.lower()),
                          history=self._register_history(c.date, c.status, c.comments), source=src)
        return g
