"""Build settings: base IRI, agents and register filtering.

Settings can be given on the command line or in a TOML file (``ags-rdf.toml``)::

    base_iri = "https://w3id.org/ags4/"
    register_statuses = ["approved", "accepted", "deprecated"]

    [publisher]
    iri = "https://github.com/KoalaGeo"
    name = "KoalaGeo"
    url = "https://github.com/KoalaGeo"

    [register_version_fallbacks]
    "4.2" = ["4.1"]
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

# Placeholder namespace. It is NOT registered with w3id.org; register it
# (https://github.com/perma-id/w3id.org) or pass your own with --base-iri.
DEFAULT_BASE_IRI = "https://w3id.org/ags4/"


@dataclass(frozen=True)
class Agent:
    iri: str
    name: str
    url: str


AGS = Agent(
    iri="https://www.ags.org.uk/",
    name="Association of Geotechnical and Geoenvironmental Specialists (AGS)",
    url="https://www.ags.org.uk/",
)
DEFAULT_PUBLISHER = Agent(
    iri="https://github.com/KoalaGeo",
    name="KoalaGeo",
    url="https://github.com/KoalaGeo",
)


@dataclass(frozen=True)
class Settings:
    base_iri: str = DEFAULT_BASE_IRI
    creator: Agent = AGS
    publisher: Agent = DEFAULT_PUBLISHER
    rights_holder: Agent = AGS
    # Register (abbreviation, unit, contaminant code) entries with these statuses
    # become concepts. "proposed" and "declined" entries are not part of the
    # standard, so they are excluded unless asked for.
    register_statuses: tuple[str, ...] = ("approved", "accepted", "deprecated")
    # Also accept register entries tagged for these families, e.g. {"4.2": ("4.1",)}.
    # Empty by default: the JSON "Version" tags are followed strictly.
    register_version_fallbacks: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Pick-list headings with more standard codes than this get no sh:pattern
    # (the code list is still referenced from the shape).
    max_pattern_codes: int = 1000
    language: str = "en"

    def __post_init__(self):
        if not self.base_iri.endswith(("/", "#")):
            object.__setattr__(self, "base_iri", self.base_iri + "/")

    def accepts_status(self, status: str) -> bool:
        return status.strip().lower() in self.register_statuses

    def families_for(self, family: str) -> set[str]:
        return {family, *self.register_version_fallbacks.get(family, ())}

    @classmethod
    def load(cls, path: Path | None = None, **overrides) -> "Settings":
        data: dict = {}
        if path is not None:
            data = tomllib.loads(Path(path).read_text())
        for key in ("creator", "publisher", "rights_holder"):
            if key in data:
                data[key] = Agent(**data[key])
        if "register_statuses" in data:
            data["register_statuses"] = tuple(s.lower() for s in data["register_statuses"])
        if "register_version_fallbacks" in data:
            data["register_version_fallbacks"] = {
                k: tuple(v) for k, v in data["register_version_fallbacks"].items()}
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Unknown setting(s) in {path}: {', '.join(sorted(unknown))}")
        settings = cls(**data)
        clean = {k: v for k, v in overrides.items() if v is not None}
        return replace(settings, **clean) if clean else settings
