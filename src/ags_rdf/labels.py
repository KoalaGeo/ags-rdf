"""Background labels: an ``rdfs:label`` (and ``schema:description``) for every IRI the outputs use.

Vocabulary viewers such as Prez and prez-lite show a label for every IRI in a
vocabulary, but each vocabulary file only labels its own concepts. Links to
other vocabularies (a heading's ``agso:dataType`` points into the data types
vocabulary), meta-model properties, registry statuses and source files would
otherwise be shown as bare IRIs. This graph supplies those labels; prez-lite
reads it from ``data/background/``.
"""

from __future__ import annotations

import re

from rdflib import DCTERMS, OWL, PROV, RDF, RDFS, SDO, SKOS, Graph, Literal, URIRef

from .namespaces import REG

STANDARD_LABELS = {
    RDF.type: "type",
    RDFS.label: "label", RDFS.comment: "comment", RDFS.isDefinedBy: "is defined by",
    RDFS.seeAlso: "see also", RDFS.subClassOf: "subclass of", RDFS.range: "range", RDFS.domain: "domain",
    SKOS.prefLabel: "preferred label", SKOS.altLabel: "alternative label", SKOS.definition: "definition",
    SKOS.notation: "notation", SKOS.broader: "broader", SKOS.narrower: "narrower",
    SKOS.inScheme: "in scheme", SKOS.topConceptOf: "top concept of", SKOS.hasTopConcept: "has top concept",
    SKOS.member: "member", SKOS.historyNote: "history note", SKOS.scopeNote: "scope note",
    SKOS.example: "example", SKOS.Concept: "Concept", SKOS.ConceptScheme: "Concept Scheme",
    SKOS.Collection: "Collection",
    SDO.status: "status", SDO.creator: "creator", SDO.publisher: "publisher",
    SDO.copyrightHolder: "copyright holder", SDO.dateCreated: "date created",
    SDO.dateModified: "date modified", SDO.datePublished: "date published", SDO.version: "version",
    SDO.citation: "citation", SDO.name: "name", SDO.url: "url", SDO.description: "description",
    SDO.Organization: "Organization",
    PROV.wasDerivedFrom: "was derived from", DCTERMS.rights: "rights", REG.status: "registry status",
    OWL.versionIRI: "version IRI", OWL.versionInfo: "version info", OWL.Class: "Class",
    OWL.DatatypeProperty: "Datatype Property", OWL.ObjectProperty: "Object Property",
    OWL.AnnotationProperty: "Annotation Property", OWL.Ontology: "Ontology", OWL.deprecated: "deprecated",
}

STATUS_LABELS = {
    "stable": "Stable", "accepted": "Accepted", "deprecated": "Deprecated", "experimental": "Experimental",
    "submitted": "Submitted", "notAccepted": "Not Accepted", "retired": "Retired", "superceded": "Superseded",
    "valid": "Valid", "invalid": "Invalid", "unstable": "Unstable", "reserved": "Reserved",
}


def _text(g: Graph, s, preds, lang: str) -> str | None:
    values = [o for p in preds for o in g.objects(s, p) if isinstance(o, Literal)]
    preferred = [o for o in values if o.language == lang] or values
    return str(preferred[0]) if preferred else None


def build_labels(graphs: list[Graph], lang: str = "en") -> Graph:
    src = Graph()
    for g in graphs:
        src += g
    out = Graph(bind_namespaces="none")
    out.bind("rdfs", RDFS)
    out.bind("schema", SDO)

    def add(iri, label, description=None):
        out.add((iri, RDFS.label, Literal(label, lang=lang)))
        if description and description != label:
            out.add((iri, SDO.description, Literal(description, lang=lang)))

    for s in set(src.subjects()):
        if not isinstance(s, URIRef):
            continue
        label = _text(src, s, (SKOS.prefLabel, RDFS.label, SDO.name), lang)
        if label:
            add(s, label, _text(src, s, (SKOS.definition, RDFS.comment, SDO.description), lang))

    used = set(src.predicates()) | set(src.objects(None, RDF.type))
    for iri, label in STANDARD_LABELS.items():
        if iri in used and (iri, RDFS.label, None) not in out:
            add(iri, label)
    for status in set(src.objects(None, SDO.status)) | set(src.objects(None, REG.status)):
        key = str(status).rstrip("/").rsplit("/", 1)[-1]
        if key in STATUS_LABELS:
            add(status, STATUS_LABELS[key])
    for f in set(src.objects(None, PROV.wasDerivedFrom)):
        m = re.search(r"/-/blob/[^/]+/(.+)$", str(f))
        if isinstance(f, URIRef) and m:
            add(f, m.group(1), "AGS data dictionary source file (AGS Data Format Working Group, GitLab)")
    return out
