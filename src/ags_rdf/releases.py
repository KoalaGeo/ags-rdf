"""Discover the AGS4 dictionary releases present in a source snapshot.

Each release is published as a ``groupsandheadings<major>-<minor>[-<patch>].json``
file, with companion ``group_notes.json``, ``Changelog.JSON`` and ``rules.json``
files in the same folder (or, for rules, a parent folder). Shared registers -
abbreviations, units, data types and contaminant codes - live at the top of
``AGS4/`` and carry a ``Version`` field (e.g. ``"4.0,4.1,4.2"``) saying which
release families they apply to.

Releases are discovered from file names rather than hard-coded, so a new
release dropped into GitLab (e.g. ``AGS4_2/4_2_1/groupsandheadings4-2-1.json``)
is picked up automatically. Draft files such as ``groupsandheadings4-2CPT.JSON``
do not match the pattern and are ignored.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field

from .sources import DICTIONARY_ROOT, Snapshot

RELEASE_FILE = re.compile(r"groupsandheadings(\d+)-(\d+)(?:-(\d+))?\.json$", re.IGNORECASE)

# Facts about releases that are not in the JSON. Dates/statuses come from the
# ASG4 repository's changelog.json; only what is published there is recorded.
KNOWN_RELEASES: dict[str, dict] = {
    "4.0.3": {"published": "2011-10", "status": "deprecated", "title": "AGS4 Addendum 3 (4.0.3)"},
    "4.0.4": {"published": "2017-02", "status": "deprecated", "title": "AGS 4.0.4"},
    "4.1": {"published": "2020-09", "title": "AGS 4.1"},
    "4.1.1": {"title": "AGS 4.1.1"},
    "4.2.0": {"title": "AGS 4.2"},
}


def version_key(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split("."))


@dataclass
class Release:
    version: str
    groups_and_headings: str
    group_notes: str | None = None
    changelog: str | None = None
    rules: str | None = None
    # changelogs of earlier releases in the same major version, oldest first
    history: list[tuple[str, str]] = field(default_factory=list)
    published: str | None = None
    status: str | None = None
    title: str | None = None

    @property
    def family(self) -> str:
        """``4.1.1`` -> ``4.1``: the value used in the registers' ``Version`` fields."""
        return ".".join(self.version.split(".")[:2])

    @property
    def slug(self) -> str:
        return self.version

    def source_files(self) -> list[str]:
        files = [self.groups_and_headings, self.group_notes, self.changelog, self.rules]
        return [f for f in files if f]


@dataclass
class Registers:
    """Paths of the shared, version-tagged register files."""

    abbreviations: str | None = None
    units: str | None = None
    data_types: str | None = None
    contaminant_codes: str | None = None


def _sibling(snapshot: Snapshot, folder: str, name_rx: str, walk_up: bool = False) -> str | None:
    rx = re.compile(name_rx, re.IGNORECASE)
    while True:
        hits = [f for f in snapshot.list_files(folder)
                if posixpath.dirname(f) == folder and rx.fullmatch(posixpath.basename(f))]
        if hits:
            return sorted(hits)[0]
        if not walk_up or folder in ("", DICTIONARY_ROOT):
            return None
        folder = posixpath.dirname(folder)


def discover_releases(snapshot: Snapshot) -> dict[str, Release]:
    releases: dict[str, Release] = {}
    for rel in snapshot.list_files():
        m = RELEASE_FILE.search(posixpath.basename(rel))
        if not m:
            continue
        version = ".".join(p for p in m.groups() if p is not None)
        folder = posixpath.dirname(rel)
        r = Release(
            version=version,
            groups_and_headings=rel,
            group_notes=_sibling(snapshot, folder, r"group_notes\.json"),
            changelog=_sibling(snapshot, folder, r"changelog\.json"),
            rules=_sibling(snapshot, folder, r"rules\.json", walk_up=True),
            **KNOWN_RELEASES.get(version, {}),
        )
        if r.changelog and posixpath.dirname(r.changelog) != folder:
            r.changelog = None
        releases[version] = r

    # A release folder shared by two releases (4.0.3 and 4.0.4 both live in AGS4_0/)
    # means the companion changelog describes the newest one only.
    ordered = sorted(releases, key=version_key)
    for v in ordered:
        r = releases[v]
        same_dir = [o for o in ordered if posixpath.dirname(releases[o].groups_and_headings)
                    == posixpath.dirname(r.groups_and_headings)]
        if r.changelog and same_dir[-1] != v:
            r.changelog = None
        r.history = [(o, releases[o].changelog) for o in ordered
                     if version_key(o) < version_key(v) and releases[o].changelog
                     and o.split(".")[0] == v.split(".")[0]]
    return dict(sorted(releases.items(), key=lambda kv: version_key(kv[0])))


def discover_registers(snapshot: Snapshot) -> Registers:
    def one(name_rx: str) -> str | None:
        hits = snapshot.find(rf"(^|/){name_rx}$")
        # prefer the shallowest match (the shared register at the top of AGS4/)
        return sorted(hits, key=lambda h: (h.count("/"), h))[0] if hits else None

    return Registers(
        abbreviations=one(r"abbr4\.json"),
        units=one(r"unit\.json"),
        data_types=one(r"data_types\.json"),
        contaminant_codes=one(r"elrg\.json"),
    )


def select_releases(available: dict[str, Release], wanted: list[str] | None) -> list[Release]:
    """``None``/``["latest"]`` -> newest; ``["all"]`` -> every release; else exact versions."""
    if not available:
        return []
    if not wanted or wanted == ["latest"]:
        return [available[list(available)[-1]]]
    if wanted == ["all"]:
        return list(available.values())
    missing = [w for w in wanted if w not in available]
    if missing:
        raise KeyError(f"Unknown release(s) {missing}; available: {', '.join(available)}")
    return [available[w] for w in wanted]
