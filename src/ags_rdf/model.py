"""A normalised, source-format-independent model of one AGS4 dictionary release.

The loader (:mod:`ags_rdf.loader`) turns the raw JSON into these objects; every
RDF builder works from this model only. Keeping this layer independent of both
the JSON quirks and of RDF is what makes it straightforward to add further
outputs later (e.g. mappings to DIGGS or ISO dictionaries).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .releases import Release

Severity = Literal["error", "warning", "info"]


@dataclass
class Issue:
    """A data-quality finding about the source JSON."""

    severity: Severity
    category: str
    message: str
    source: str | None = None
    group: str | None = None
    heading: str | None = None
    code: str | None = None


@dataclass
class Heading:
    """A HEADING as it occurs in one GROUP (attributes can differ between groups)."""

    group: str
    code: str
    order: int
    status: str  # raw status: "", "*", "R", "*R", "DEPRECATED"
    data_type: str
    unit: str
    description: str
    example: str

    @property
    def is_key(self) -> bool:
        return "*" in self.status

    @property
    def is_required(self) -> bool:
        return "R" in self.status.replace("DEPRECATED", "")

    @property
    def is_deprecated(self) -> bool:
        return "DEPRECATED" in self.status.upper()

    @property
    def is_home(self) -> bool:
        """True when the heading is defined by this group (``LOCA_ID`` in ``LOCA``)."""
        return self.code.startswith(self.group + "_")


@dataclass
class Group:
    code: str
    order: int
    description: str  # the group title, e.g. "Location Details"
    category: str  # the "class", e.g. "Locations and Exploratory Hole Construction Details"
    status_text: str  # raw group_status
    parent: str | None
    children: list[str]
    headings: list[Heading] = field(default_factory=list)
    notes: str | None = None
    rules_text: str | None = None

    @property
    def is_deprecated(self) -> bool:
        return "DEPRECATED" in self.status_text.upper()

    @property
    def is_new(self) -> bool:
        return self.status_text.strip().lower().startswith("new")

    @property
    def keys(self) -> list[Heading]:
        return [h for h in self.headings if h.is_key]

    def heading(self, code: str) -> Heading | None:
        return next((h for h in self.headings if h.code == code), None)


@dataclass
class DataType:
    code: str  # generic code, e.g. "nDP" or "X"
    description: str
    notes: str
    # set when the type is not defined for the release's family and the
    # definition was borrowed from these families
    defined_for: list[str] = field(default_factory=list)


@dataclass
class Unit:
    code: str
    description: str
    quantity: str  # "Type" in UNIT.json, e.g. "Length"
    status: str
    date: str
    comments: str


@dataclass
class Abbreviation:
    heading: str
    code: str
    description: str
    status: str
    date: str
    comments: str


@dataclass
class ContaminantCode:
    code: str
    description: str
    status: str
    date: str
    comments: str


@dataclass
class Rule:
    ref: str
    description: str
    order: int

    @property
    def parent_ref(self) -> str | None:
        main = self.ref.rstrip("abcdefghijklmnopqrstuvwxyz")
        return main if main != self.ref else None


@dataclass
class ChangeEntry:
    version: str
    action: str
    group: str
    heading: str | None
    comments: str


@dataclass
class Dictionary:
    release: Release
    groups: dict[str, Group]
    data_types: dict[str, DataType]
    units: dict[str, Unit]
    abbreviations: dict[str, list[Abbreviation]]  # heading code -> codes
    contaminant_codes: dict[str, ContaminantCode]
    rules: dict[str, Rule]
    changes: list[ChangeEntry]
    issues: list[Issue]
    # source file paths that fed each part, for provenance
    sources: dict[str, list[str]] = field(default_factory=dict)

    @property
    def version(self) -> str:
        return self.release.version

    def headings(self) -> list[Heading]:
        return [h for g in self.groups.values() for h in g.headings]

    def heading_occurrences(self) -> dict[str, list[Heading]]:
        occ: dict[str, list[Heading]] = {}
        for h in self.headings():
            occ.setdefault(h.code, []).append(h)
        return occ

    def defining_occurrence(self, code: str) -> Heading:
        """The occurrence that best defines a heading shared by several groups.

        The "home" group (whose code prefixes the heading) wins; otherwise the
        most common description, ties broken by dictionary order.
        """
        occ = self.heading_occurrences()[code]
        home = [h for h in occ if h.is_home]
        if home:
            return home[0]
        counts: dict[str, int] = {}
        for h in occ:
            counts[h.description] = counts.get(h.description, 0) + 1
        best = max(counts.values())
        return next(h for h in occ if counts[h.description] == best)

    def changes_for(self, group: str, heading: str | None = None) -> list[ChangeEntry]:
        return [c for c in self.changes if c.group == group and c.heading == heading]
