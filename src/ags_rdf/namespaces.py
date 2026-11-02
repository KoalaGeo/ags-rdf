"""Third-party namespaces and the registry-status vocabulary used by VocPub/VocExcel."""

from rdflib import Namespace, URIRef

REG = Namespace("http://purl.org/linked-data/registry#")
REG_STATUS = Namespace("https://linked.data.gov.au/def/reg-statuses/")
DASH = Namespace("http://datashapes.org/dash#")
ISOROLES = Namespace("http://def.isotc211.org/iso19115/-1/2018/CitationAndResponsiblePartyInformation/code/CI_RoleCode/")

# VocPub-recommended status values (the same IRIs VocExcel understands)
STATUS = {
    "stable": REG_STATUS.stable,
    "accepted": REG_STATUS.accepted,
    "deprecated": REG_STATUS.deprecated,
    "experimental": REG_STATUS.experimental,
    "submitted": REG_STATUS.submitted,
    "notAccepted": REG_STATUS.notAccepted,
    "retired": REG_STATUS.retired,
}

# Register status in the AGS JSON -> registry status IRI
REGISTER_STATUS: dict[str, URIRef] = {
    "approved": STATUS["accepted"],
    "accepted": STATUS["accepted"],
    "deprecated": STATUS["deprecated"],
    "proposed": STATUS["submitted"],
    "declined": STATUS["notAccepted"],
}

PREFIXES = {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dcterms": "http://purl.org/dc/terms/",
    "owl": "http://www.w3.org/2002/07/owl#",
    "prov": "http://www.w3.org/ns/prov#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "schema": "https://schema.org/",
    "sh": "http://www.w3.org/ns/shacl#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "reg": str(REG),
    "status": str(REG_STATUS),
}
