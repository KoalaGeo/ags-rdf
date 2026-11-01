"""OWL ontology: the AGS meta-model (``agso:``) and the generated data model (``ags:``).

Instance data model (what the SHACL shapes validate):

* every DATA row of a GROUP is a resource typed with the group's class
  (``ags:LOCA``, a subclass of ``agso:Record``);
* every non-null field is one triple ``<row> ags:<HEADING> "value"``, with the
  literal datatype given by :mod:`ags_rdf.datatypes`;
* a row is linked to the row in its PARENT GROUP with ``agso:parent`` (Rule 10c).

Heading properties are shared by every group that uses the heading (``LOCA_ID``
in ``SAMP`` is the same property as in ``LOCA``), so they deliberately have no
``rdfs:domain``. Each class/property links to its dictionary concept with
``agso:dictionaryEntry``, which is the natural anchor for future mappings
(e.g. ``owl:equivalentClass`` / ``skos:closeMatch`` to DIGGS or ISO terms).
"""

from __future__ import annotations

from rdflib import OWL, RDF, RDFS, SKOS, XSD, Graph, Literal, URIRef

from ..datatypes import type_spec
from .common import BuildContext

# (local name, kind, label, comment, domain, range)
META_TERMS: list[tuple[str, URIRef, str, str, str | None, URIRef | str | None]] = [
    ("Record", OWL.Class, "Record", "A DATA row of an AGS GROUP. Each group's class is a subclass.", None, None),
    ("parent", OWL.ObjectProperty, "parent record",
     "Links a record to the record in its PARENT GROUP whose KEY fields it shares (AGS Rule 10c).",
     "Record", "Record"),
    ("parentGroup", OWL.AnnotationProperty, "parent group",
     "The PARENT GROUP of a group (between group classes or group concepts).", None, None),
    ("groupClass", OWL.AnnotationProperty, "group class",
     "Links a group concept in the dictionary vocabulary to the OWL class of its records.", None, None),
    ("property", OWL.AnnotationProperty, "heading property",
     "The OWL property used for a heading's values (from a heading concept or a field definition).",
     None, None),
    ("dictionaryEntry", OWL.AnnotationProperty, "dictionary entry",
     "Links an OWL class, OWL property or SHACL shape to the concept describing it in the AGS "
     "dictionary vocabulary.", None, None),
    ("dataType", OWL.AnnotationProperty, "data type",
     "The suggested AGS data TYPE of a heading (a concept in the data types vocabulary).", None, None),
    ("suggestedUnit", OWL.AnnotationProperty, "suggested unit",
     "The suggested AGS UNIT of a heading (a concept in the units vocabulary, or a literal when the "
     "unit is not in the standard UNIT list).", None, None),
    ("headingStatus", OWL.AnnotationProperty, "heading status",
     "The raw AGS heading status: '*' (KEY), 'R' (REQUIRED), '*R' (both) or '' (OTHER).", None, None),
    ("isKey", OWL.AnnotationProperty, "is key", "True if the heading is a KEY field in the group (Rule 10a).",
     None, None),
    ("isRequired", OWL.AnnotationProperty, "is required",
     "True if the heading is a REQUIRED field in the group (Rule 10b).", None, None),
    ("abbreviationList", OWL.AnnotationProperty, "abbreviation list",
     "The collection of standard abbreviations for a heading of type PA.", None, None),
    ("heading", OWL.AnnotationProperty, "heading",
     "The heading concept an abbreviation (or abbreviation list) belongs to.", None, None),
    ("rule", OWL.AnnotationProperty, "rule", "An AGS rule (concept in the rules vocabulary) a shape implements.",
     None, None),
    # --- terms used when converting AGS data files (ags_rdf.convert)
    ("DataFile", OWL.Class, "AGS data file", "An AGS data file converted to RDF.", None, None),
    ("dataFile", OWL.ObjectProperty, "data file", "The AGS data file a record was read from.",
     "Record", "DataFile"),
    ("agsVersion", OWL.DatatypeProperty, "AGS version",
     "The AGS edition a data file declares in TRAN_AGS.", "DataFile", XSD.string),
    ("FieldDefinition", OWL.Class, "field definition",
     "The UNIT and TYPE a data file gives for one HEADING of one GROUP (AGS Rule 8). File values are "
     "typed using these, not the dictionary's suggested unit and type.", None, None),
    ("field", OWL.ObjectProperty, "field", "A field definition of a data file.", "DataFile", "FieldDefinition"),
    ("group", OWL.AnnotationProperty, "group", "The group class a field definition belongs to.", None, None),
    ("unit", OWL.AnnotationProperty, "unit",
     "The UNIT declared in a data file (a units concept, or a literal for non-standard units).", None, None),
    ("type", OWL.AnnotationProperty, "type",
     "The TYPE declared in a data file (a data types concept, or a literal).", None, None),
    ("position", OWL.AnnotationProperty, "position", "Position of a heading in a group's HEADING row.",
     None, None),
    ("userDefined", OWL.AnnotationProperty, "user defined",
     "True for a group or heading not in the AGS dictionary (defined in the file's DICT group, Rule 18).",
     None, None),
]


class OntologyBuilder:
    def __init__(self, ctx: BuildContext):
        self.ctx = ctx
        self.d = ctx.dictionary
        self.iris = ctx.iris

    def build(self) -> Graph:
        g = self.ctx.new_graph()
        self._meta(g)
        self._model(g)
        return g

    def _meta(self, g: Graph) -> None:
        ont = self.iris.meta_ontology
        AGSO = self.iris.AGSO
        g.add((ont, RDF.type, OWL.Ontology))
        g.add((ont, RDFS.label, self.ctx.text("AGS meta-model")))
        g.add((ont, RDFS.comment, self.ctx.text(
            "Format-level terms used to describe AGS groups, headings and records in RDF.")))
        for local, kind, label, comment, domain, range_ in META_TERMS:
            t = AGSO[local]
            g.add((t, RDF.type, kind))
            g.add((t, RDFS.label, self.ctx.text(label)))
            g.add((t, RDFS.comment, self.ctx.text(comment)))
            g.add((t, RDFS.isDefinedBy, ont))
            if domain:
                g.add((t, RDFS.domain, AGSO[domain]))
            if range_:
                g.add((t, RDFS.range, range_ if isinstance(range_, URIRef) else AGSO[range_]))
        g.add((AGSO.dictionaryEntry, RDFS.subPropertyOf, RDFS.seeAlso))

    def _model(self, g: Graph) -> None:
        d, iris, ctx = self.d, self.iris, self.ctx
        ont = iris.ontology
        ctx.describe_document(
            g, ont, OWL.Ontology, f"AGS {d.version} data model",
            f"OWL classes for the GROUPs and datatype properties for the HEADINGs of the AGS {d.version} "
            "data dictionary. Each DATA row of a group is an instance of the group's class.",
            d.sources.get("dictionary", []))
        g.add((ont, OWL.imports, iris.meta_ontology))

        for grp in d.groups.values():
            c = iris.group_class(grp.code)
            g.add((c, RDF.type, OWL.Class))
            g.add((c, RDFS.subClassOf, iris.AGSO.Record))
            g.add((c, RDFS.label, ctx.text(grp.description or grp.code)))
            g.add((c, SKOS.notation, Literal(grp.code, datatype=XSD.token)))
            g.add((c, RDFS.isDefinedBy, ont))
            g.add((c, iris.AGSO.dictionaryEntry, iris.group_concept(grp.code)))
            if grp.parent:
                g.add((c, iris.AGSO.parentGroup, iris.group_class(grp.parent)))
            if grp.is_deprecated:
                g.add((c, OWL.deprecated, Literal(True)))

        for code, occ in d.heading_occurrences().items():
            h = d.defining_occurrence(code)
            p = iris.heading_property(code)
            g.add((p, RDF.type, OWL.DatatypeProperty))
            g.add((p, RDFS.label, ctx.text(h.description or code)))
            g.add((p, SKOS.notation, Literal(code, datatype=XSD.token)))
            g.add((p, RDFS.isDefinedBy, ont))
            g.add((p, iris.AGSO.dictionaryEntry, iris.heading_concept(code)))
            ranges = {type_spec(o.data_type).range for o in occ}
            g.add((p, RDFS.range, ranges.pop() if len(ranges) == 1 else RDFS.Literal))
            if all(o.is_deprecated or d.groups[o.group].is_deprecated for o in occ):
                g.add((p, OWL.deprecated, Literal(True)))
