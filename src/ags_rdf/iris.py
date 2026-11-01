"""IRI minting - the single place where identifiers are decided.

All IRIs are minted under a configurable base (``Settings.base_iri``) and are
*unversioned*: ``LOCA_ID`` has the same IRI in every release, and each release
is published as a new version of the vocabularies/ontology/shapes (recorded with
``owl:versionIRI`` and ``schema:version``). Stable, unversioned term IRIs are
what future mappings (DIGGS, ISO 23386/28258/22475/14688 ...) should point at.

Layout under the base (``{b}``)::

    {b}ont/<Term>                 meta-ontology (agso:) - Record, parent, dataType ...
    {b}def/<GROUP>|<HEADING>      data model (ags:) - classes per GROUP, properties per HEADING
    {b}shapes/<GROUP>[-<HEADING>] SHACL node/property shapes (agssh:)
    {b}voc/<vocab>/<local>        SKOS vocabularies and their concepts/collections

Local names must survive a VocExcel round trip, so they only use
``[A-Za-z0-9_.-]`` (percent-encoding is mangled by VocExcel). Codes containing
other characters (``CP+RC``, ``kN/m2``, ``% dry weight``) are transliterated by
:func:`local_name`, and :class:`LocalNames` guarantees uniqueness per namespace.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from rdflib import Namespace, URIRef

_SUBS = {"%": "pct", "+": "plus", "/": "per", "&": "and", "#": "no", "<": "lt", ">": "gt", "=": "eq"}
_LETTERS = {"µ": "u", "μ": "u", "°": "deg"}  # unit symbols that read as part of a word


def local_name(text: str) -> str:
    """Readable, VocExcel-safe local name for an arbitrary code."""
    out = []
    for ch in str(text):
        if ch.isascii() and (ch.isalnum() or ch in "-_."):
            out.append(ch)
        elif ch in _LETTERS:
            out.append(_LETTERS[ch])
        elif ch in _SUBS:
            out.append(f"_{_SUBS[ch]}_")
        else:
            ascii_ = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode()
            out.append(ascii_ if ascii_.isalnum() else "_")
    s = re.sub(r"_+", "_", "".join(out)).strip("_.")
    return s or "x" + hashlib.sha1(str(text).encode()).hexdigest()[:8]


def slug(text: str) -> str:
    """Lower-case hyphenated slug for titles (e.g. group categories)."""
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


class LocalNames:
    """Hands out unique local names within one namespace, deterministically."""

    def __init__(self):
        self._by_key: dict[str, str] = {}
        self._taken: dict[str, str] = {}

    def __call__(self, key: str, preferred: str | None = None) -> str:
        if key in self._by_key:
            return self._by_key[key]
        name = preferred or local_name(key)
        if name in self._taken and self._taken[name] != key:
            name = f"{name}_{hashlib.sha1(key.encode()).hexdigest()[:6]}"
        self._by_key[key] = name
        self._taken[name] = key
        return name


class IRIs:
    """Mints every IRI used in the outputs."""

    VOCABS = ("dictionary", "abbreviations", "units", "data-types", "rules", "contaminant-codes")

    def __init__(self, base: str):
        if not base.endswith(("/", "#")):
            base += "/"
        self.base = base
        self.AGSO = Namespace(base + "ont/")
        self.AGS = Namespace(base + "def/")
        self.SH = Namespace(base + "shapes/")
        self.VOC = Namespace(base + "voc/")
        self._names: dict[str, LocalNames] = {}

    # ----------------------------------------------------------- documents
    @property
    def meta_ontology(self) -> URIRef:
        return URIRef(self.base + "ont")

    @property
    def ontology(self) -> URIRef:
        return URIRef(self.base + "def")

    @property
    def shapes_graph(self) -> URIRef:
        return URIRef(self.base + "shapes")

    @property
    def catalogue(self) -> URIRef:
        return URIRef(self.base + "catalogue")

    def version_iri(self, iri: URIRef, version: str) -> URIRef:
        return URIRef(f"{iri}/{version}")

    # ---------------------------------------------------------- data model
    def group_class(self, group: str) -> URIRef:
        return self.AGS[group]

    def heading_property(self, heading: str) -> URIRef:
        return self.AGS[heading]

    def node_shape(self, group: str) -> URIRef:
        return self.SH[group]

    def property_shape(self, group: str, heading: str, suffix: str = "") -> URIRef:
        return self.SH[f"{group}-{heading}{suffix}"]

    def parent_shape(self, group: str) -> URIRef:
        return self.SH[f"{group}-parent"]

    # ---------------------------------------------------------- vocabulary
    def scheme(self, vocab: str) -> URIRef:
        return URIRef(self.VOC + vocab)

    def vocab_ns(self, vocab: str) -> Namespace:
        return Namespace(f"{self.VOC}{vocab}/")

    def _local(self, vocab: str, key: str, preferred: str | None = None) -> URIRef:
        names = self._names.setdefault(vocab, LocalNames())
        return self.vocab_ns(vocab)[names(key, preferred)]

    def group_concept(self, group: str) -> URIRef:
        return self._local("dictionary", group, group)

    def heading_concept(self, heading: str) -> URIRef:
        return self._local("dictionary", heading, heading)

    def category_collection(self, category: str) -> URIRef:
        return self._local("dictionary", "category:" + category, "category-" + slug(category))

    def abbreviation(self, heading: str, code: str) -> URIRef:
        return self._local("abbreviations", f"{heading}\x00{code}", f"{heading}-{local_name(code)}")

    def abbreviation_list(self, heading: str) -> URIRef:
        return self._local("abbreviations", f"list\x00{heading}", heading)

    def unit(self, code: str) -> URIRef:
        return self._local("units", code)

    def unit_collection(self, quantity: str) -> URIRef:
        return self._local("units", "quantity:" + quantity, "quantity-" + slug(quantity))

    def data_type(self, code: str) -> URIRef:
        return self._local("data-types", code)

    def rule(self, ref: str) -> URIRef:
        return self._local("rules", ref, "rule-" + local_name(ref))

    def contaminant_code(self, code: str) -> URIRef:
        return self._local("contaminant-codes", code)
