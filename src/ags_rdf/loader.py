"""Load one AGS4 release from a source snapshot into the normalised model.

Normalisation is deliberately conservative - the JSON is the authoritative
source, so values are only cleaned of formatting artefacts (HTML tags and
entities, non-breaking spaces, stray line breaks, mis-encoded characters).
Anything odd is recorded as an :class:`~ags_rdf.model.Issue` rather than being
silently "fixed", and the issues are written to the data-quality report.
"""

from __future__ import annotations

import datetime as dt
import html
import re
from collections import Counter, defaultdict

from .config import Settings
from .model import (Abbreviation, ChangeEntry, ContaminantCode, DataType, Dictionary, Group,
                    Heading, Issue, Rule, Unit)
from .releases import Release, discover_registers
from .sources import Snapshot

HEADING_CODE = re.compile(r"^[A-Z0-9]+_[A-Z0-9_]+$")
GROUP_CODE_RULE = re.compile(r"^[A-Z0-9]{1,4}$")  # Rule 19
HEADING_CODE_RULE = re.compile(r"^[A-Z0-9_]{1,9}$")  # Rule 19a
NUMERIC_TYPE = re.compile(r"^(\d+)(DP|SF|SCI)$")
KNOWN_STATUSES = {"", "*", "R", "*R", "DEPRECATED"}
STATUS_RANK = {"approved": 0, "accepted": 0, "deprecated": 1, "proposed": 2, "declined": 3}


# ----------------------------------------------------------------- cleaning
_TAG = re.compile(r"<[^>]+>")


def clean_text(value, keep_newlines: bool = False) -> str:
    """Strip formatting artefacts from a JSON string value."""
    if value is None:
        return ""
    s = str(value)
    s = re.sub(r"(?i)<li[^>]*>", "\n• ", s)
    s = re.sub(r"(?i)<br\s*/?>|</br>|</p>|</li>|</?ul>", "\n", s)
    s = _TAG.sub("", s)
    s = html.unescape(s)
    s = s.replace("�", " ").replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    if keep_newlines:
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in s.split("\n")]
        s = "\n".join(ln for ln in lines if ln)
    else:
        s = re.sub(r"\s+", " ", s)
    return s.strip()


def clean_code(value) -> str:
    return "" if value is None else str(value).strip()


def _first(rows: list[dict], key: str, skip: tuple[str, ...] = ("",)) -> str:
    for r in rows:
        v = clean_text(r.get(key))
        if v not in skip:
            return v
    return ""


def _parse_date(s: str) -> dt.date | None:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _versions(value) -> set[str]:
    return {v.strip() for v in str(value or "").split(",") if v.strip()}


# ------------------------------------------------------------------- loader
class Loader:
    def __init__(self, snapshot: Snapshot, release: Release, settings: Settings | None = None):
        self.snapshot = snapshot
        self.release = release
        self.settings = settings or Settings()
        self.issues: list[Issue] = []
        self.registers = discover_registers(snapshot)
        self.families = self.settings.families_for(release.family)

    def issue(self, severity, category, message, **kw) -> None:
        self.issues.append(Issue(severity, category, message, **kw))

    # ------------------------------------------------------------------
    def load(self) -> Dictionary:
        r = self.release
        groups = self._groups()
        self._group_notes(groups)
        d = Dictionary(
            release=r,
            groups=groups,
            data_types=self._data_types(),
            units=self._units(),
            abbreviations=self._abbreviations(),
            contaminant_codes=self._contaminant_codes(),
            rules=self._rules(),
            changes=self._changes(),
            issues=self.issues,
        )
        d.sources = {
            "dictionary": [f for f in [r.groups_and_headings, r.group_notes, r.changelog,
                                       *(c for _, c in r.history)] if f],
            "abbreviations": [f for f in [self.registers.abbreviations] if f],
            "units": [f for f in [self.registers.units] if f],
            "data-types": [f for f in [self.registers.data_types, r.groups_and_headings] if f],
            "contaminant-codes": [f for f in [self.registers.contaminant_codes] if f],
            "rules": [f for f in [r.rules] if f],
        }
        check_dictionary(d, self)
        return d

    # ------------------------------------------------------------- groups
    def _groups(self) -> dict[str, Group]:
        src = self.release.groups_and_headings
        rows = self.snapshot.read_json(src)
        by_group: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            by_group[clean_code(row.get("group"))].append(row)

        if any("�" in str(v) for row in rows for v in row.values()):
            self.issue("warning", "encoding",
                       "Contains U+FFFD replacement characters (mis-encoded non-breaking spaces, "
                       "e.g. 'Rule�17'); replaced with spaces", source=src)

        groups: dict[str, Group] = {}
        for code, grows in by_group.items():
            parent = _first(grows, "parent")
            children = _first(grows, "child")
            try:
                order = int(_first(grows, "group_order") or 0)
            except ValueError:
                order = 0
                self.issue("warning", "group-order", f"Non-numeric group_order for {code}",
                           source=src, group=code)
            g = Group(
                code=code,
                order=order,
                description=_first(grows, "group_description"),
                category=_first(grows, "class"),
                status_text=_first(grows, "group_status", skip=("", "-")),
                parent=None if parent in ("", "-") else parent,
                children=[c.strip() for c in children.split("+") if c.strip() not in ("", "-")],
            )
            for k in ("class", "group_description", "group_order"):
                vals = {clean_text(x.get(k)) for x in grows} - {""}
                if len(vals) > 1:
                    self.issue("warning", "group-inconsistent",
                               f"{code}: rows disagree on {k}: {sorted(vals)}", source=src, group=code)
            for row in grows:
                h = self._heading(g, row, src)
                if h is not None:
                    g.headings.append(h)
            g.headings.sort(key=lambda h: h.order)
            groups[code] = g
        return dict(sorted(groups.items(), key=lambda kv: (kv[1].order, kv[0])))

    def _heading(self, g: Group, row: dict, src: str) -> Heading | None:
        code = clean_code(row.get("heading"))
        if not code:
            self.issue("error", "heading-missing", f"{g.code}: row without a heading code",
                       source=src, group=g.code)
            return None
        status = clean_code(row.get("heading_status")).upper()
        if status not in KNOWN_STATUSES:
            self.issue("warning", "heading-status", f"Unrecognised heading_status {status!r}",
                       source=src, group=g.code, heading=code)
        try:
            order = int(clean_code(row.get("in_group_order")) or 0)
        except ValueError:
            order = 0
            self.issue("warning", "heading-order", "Non-numeric in_group_order",
                       source=src, group=g.code, heading=code)
        raw_desc = str(row.get("description") or "")
        if re.search(r"\S[\r\n]+\S", raw_desc) and not g.code == "DICT":
            self.issue("info", "line-break", "Description contains a line break (PDF copy artefact?)",
                       source=src, group=g.code, heading=code)
        return Heading(
            group=g.code,
            code=code,
            order=order,
            status=status,
            data_type=clean_code(row.get("suggested_type")),
            unit=clean_text(row.get("suggested_unit")),
            description=clean_text(row.get("description")),
            example=clean_text(row.get("example")),
        )

    def _group_notes(self, groups: dict[str, Group]) -> None:
        src = self.release.group_notes
        if not src:
            return
        for row in self.snapshot.read_json(src):
            code = clean_code(row.get("Group Name"))
            notes = clean_text(row.get("Group Notes", row.get("Notes for Guidance")), keep_newlines=True)
            rules = clean_text(row.get("Group Rules"), keep_newlines=True)
            if code not in groups:
                self.issue("info", "notes-orphan", f"Group notes exist for {code}, which is not in "
                           f"release {self.release.version}", source=src, group=code)
                continue
            groups[code].notes = notes if notes not in ("", "-") else None
            groups[code].rules_text = rules if rules not in ("", "-") else None

    # ----------------------------------------------------------- registers
    def _applies(self, row: dict, key: str = "Version") -> bool:
        return bool(_versions(row.get(key)) & self.families)

    def _data_types(self) -> dict[str, DataType]:
        src = self.registers.data_types
        out: dict[str, DataType] = {}
        if not src:
            self.issue("error", "missing-source", "data_types.json not found")
            return out
        rows = self.snapshot.read_json(src)
        for row in rows:
            if self._applies(row):
                code = clean_code(row.get("Type"))
                out[code] = DataType(code, clean_text(row.get("Desc")), clean_text(row.get("Notes"), True))
        # Types used by the release but not defined for its family: fall back to the
        # newest definition (check_dictionary reports the gap).
        rows_gh = self.snapshot.read_json(self.release.groups_and_headings)
        used = {NUMERIC_TYPE.sub(lambda m: "n" + m.group(2), clean_code(r.get("suggested_type")))
                for r in rows_gh}
        self.missing_data_types = sorted(u for u in used if u and u not in out)
        for row in rows:
            code = clean_code(row.get("Type"))
            if code in self.missing_data_types:
                out[code] = DataType(code, clean_text(row.get("Desc")), clean_text(row.get("Notes"), True),
                                     defined_for=sorted(_versions(row.get("Version"))))
        return out

    def _units(self) -> dict[str, Unit]:
        src = self.registers.units
        out: dict[str, Unit] = {}
        if not src:
            self.issue("error", "missing-source", "UNIT.json not found")
            return out
        rows = [r for r in self.snapshot.read_json(src) if self._applies(r)]
        for row in self._dedupe(rows, lambda r: clean_code(r.get("Unit")), "Status", "Date", src, "unit"):
            if not self.settings.accepts_status(clean_code(row.get("Status"))):
                continue
            code = clean_code(row.get("Unit"))
            out[code] = Unit(code, clean_text(row.get("Description")), clean_text(row.get("Type")),
                             clean_code(row.get("Status")), clean_code(row.get("Date")),
                             clean_text(row.get("Comments")))
        return out

    def _abbreviations(self) -> dict[str, list[Abbreviation]]:
        src = self.registers.abbreviations
        out: dict[str, list[Abbreviation]] = defaultdict(list)
        if not src:
            self.issue("error", "missing-source", "abbr4.json not found")
            return out
        all_rows = self.snapshot.read_json(src)
        n_int = sum(1 for r in all_rows if isinstance(r.get("Code"), (int, float)))
        if n_int:
            self.issue("info", "code-type", f"{n_int} abbreviation codes are JSON numbers, not strings",
                       source=src)
        rows = [r for r in all_rows if self._applies(r)]
        key = lambda r: (clean_code(r.get("Group")), clean_code(r.get("Code")))  # noqa: E731
        for row in self._dedupe(rows, key, "Status", "Date", src, "abbreviation"):
            if not self.settings.accepts_status(clean_code(row.get("Status"))):
                continue
            heading, code = key(row)
            if "+" in code:
                self.issue("warning", "abbreviation-concatenation",
                           f"{heading}: code {code!r} contains the default concatenation character '+' "
                           "(Rule 16a says combined codes should be listed separately)",
                           source=src, heading=heading, code=code)
            out[heading].append(Abbreviation(heading, code, clean_text(row.get("Description")),
                                             clean_code(row.get("Status")), clean_code(row.get("Date")),
                                             clean_text(row.get("Comments"))))
        return dict(sorted(out.items()))

    def _contaminant_codes(self) -> dict[str, ContaminantCode]:
        src = self.registers.contaminant_codes
        out: dict[str, ContaminantCode] = {}
        if not src:
            return out
        all_rows = self.snapshot.read_json(src)
        rows = [r for r in all_rows if bool(_versions(r.get("version")) & self.families)]
        per_family = Counter(f for r in all_rows for f in _versions(r.get("version")))
        prev = f"{self.release.family.split('.')[0]}.{int(self.release.family.split('.')[1]) - 1}"
        if per_family.get(self.release.family, 0) < 0.5 * per_family.get(prev, 0):
            self.issue("warning", "register-version-tags",
                       f"Only {per_family.get(self.release.family, 0)} contaminant codes are tagged for "
                       f"{self.release.family}, against {per_family.get(prev, 0)} for {prev}. The "
                       "'version' tags in this register look incomplete; they are followed strictly "
                       f"(use register_version_fallbacks to also accept {prev} codes)", source=src)
        for row in self._dedupe(rows, lambda r: clean_code(r.get("Code")), "status",
                                "Date Last Reviewed", src, "contaminant code"):
            if not self.settings.accepts_status(clean_code(row.get("status"))):
                continue
            code = clean_code(row.get("Code"))
            out[code] = ContaminantCode(code, clean_text(row.get("description")),
                                        clean_code(row.get("status")),
                                        clean_code(row.get("Date Last Reviewed")),
                                        clean_text(row.get("AGS_response")))
        return out

    def _dedupe(self, rows, key, status_field, date_field, src, what):
        """Resolve duplicate register keys: best status wins, then the newest date."""
        buckets: dict = defaultdict(list)
        for r in rows:
            buckets[key(r)].append(r)
        result = []
        for k, items in buckets.items():
            if len(items) > 1:
                items.sort(key=lambda r: (STATUS_RANK.get(clean_code(r.get(status_field)).lower(), 9),
                                          -(_parse_date(clean_code(r.get(date_field))) or dt.date.min).toordinal()))
                kept = items[0]
                descs = {clean_text(i.get("Description", i.get("description"))) for i in items}
                statuses = [clean_code(i.get(status_field)) for i in items]
                accepted = [s for s in statuses if self.settings.accepts_status(s)]
                sev = "warning" if len(accepted) > 1 and len(descs) > 1 else "info"
                label = k if isinstance(k, str) else " ".join(k)
                self.issue(sev, "register-duplicate",
                           f"Duplicate {what} {label!r} ({', '.join(statuses)}); kept the "
                           f"{clean_code(kept.get(status_field))} entry", source=src,
                           heading=k[0] if isinstance(k, tuple) else None,
                           code=k[-1] if isinstance(k, tuple) else k)
                result.append(kept)
            else:
                result.append(items[0])
        return result

    # ----------------------------------------------------------- rules/log
    def _rules(self) -> dict[str, Rule]:
        src = self.release.rules
        out: dict[str, Rule] = {}
        if not src:
            self.issue("warning", "missing-source", "rules.json not found for this release")
            return out
        for row in self.snapshot.read_json(src):
            ref = clean_code(row.get("Rule Ref"))
            out[ref] = Rule(ref, clean_text(row.get("Rule Description"), keep_newlines=True),
                            int(row.get("display_sort_order") or 0))
        return out

    def _changes(self) -> list[ChangeEntry]:
        entries: list[ChangeEntry] = []
        logs = list(self.release.history)
        if self.release.changelog:
            logs.append((self.release.version, self.release.changelog))
        for version, path in logs:
            for row in self.snapshot.read_json(path):
                action = clean_text(row.get("Action"))
                group = clean_code(row.get("Group"))
                heading = clean_code(row.get("Heading")) or None
                comments = clean_text(row.get("Comments"))
                if heading and not HEADING_CODE.match(heading):
                    # some logs put the group title in the Heading column
                    comments = "; ".join(x for x in (heading, comments) if x)
                    heading = None
                listed = re.findall(r"\b[A-Z0-9]{2,4}_[A-Z0-9_]+\b", comments)
                if heading is None and listed and action.lower().startswith("headings"):
                    for h in dict.fromkeys(listed):
                        entries.append(ChangeEntry(version, re.sub(r"(?i)headings", "Heading", action),
                                                   group, h, ""))
                entries.append(ChangeEntry(version, action, group, heading, comments))
        return entries


# --------------------------------------------------------------- QA checks
def check_dictionary(d: Dictionary, ld: Loader) -> None:
    """Consistency checks of the release against the AGS4 rules and registers."""
    src = d.release.groups_and_headings
    issue = ld.issue
    occ = d.heading_occurrences()

    for g in d.groups.values():
        if not GROUP_CODE_RULE.match(g.code):
            issue("error", "rule-19", f"Group name {g.code!r} breaks Rule 19", source=src, group=g.code)
        if g.parent and g.parent not in d.groups:
            issue("error", "parent-missing", f"{g.code}: parent group {g.parent} is not in the release",
                  source=src, group=g.code)
        for c in g.children:
            if c not in d.groups:
                issue("error", "child-missing", f"{g.code}: child group {c} is not in the release",
                      source=src, group=g.code)
            elif d.groups[c].parent != g.code:
                issue("warning", "parent-child-mismatch",
                      f"{g.code} lists {c} as a child but {c}'s parent is {d.groups[c].parent}",
                      source=src, group=g.code)
        if not g.keys:
            issue("info", "no-key", f"{g.code} has no KEY headings", source=src, group=g.code)
        if g.parent in d.groups:
            child_keys = {h.code for h in g.keys}
            missing = [h.code for h in d.groups[g.parent].keys if h.code not in child_keys]
            # PROJ (and a few top-level groups) are implicit parents with one row per file
            if missing and d.groups[g.parent].parent is not None:
                issue("warning", "rule-10c",
                      f"{g.code} does not carry parent {g.parent}'s key heading(s) {missing} as keys",
                      source=src, group=g.code)
        codes = Counter(h.code for h in g.headings)
        for h, n in codes.items():
            if n > 1:
                issue("error", "duplicate-heading", f"{g.code}: heading {h} listed {n} times",
                      source=src, group=g.code, heading=h)
        orders = [h.order for h in g.headings]
        if sorted(orders) != list(range(1, len(orders) + 1)):
            issue("info", "heading-order", f"{g.code}: in_group_order is not 1..{len(orders)}",
                  source=src, group=g.code)

    for code, hs in occ.items():
        if not HEADING_CODE_RULE.match(code):
            issue("warning", "rule-19a", f"Heading name {code!r} breaks Rule 19a (max 9 chars, A-Z0-9_)",
                  source=src, heading=code)
        prefix = code.split("_")[0]
        if not any(h.is_home for h in hs) and prefix in d.groups:
            issue("warning", "rule-19b", f"{code} is used in {[h.group for h in hs]} but not in its "
                  f"own group {prefix}", source=src, heading=code)
        for attr in ("data_type", "unit"):
            vals = {getattr(h, attr) for h in hs}
            if len(vals) > 1:
                issue("warning", "heading-inconsistent", f"{code}: {attr} differs between groups: "
                      + ", ".join(f"{h.group}={getattr(h, attr)!r}" for h in hs), source=src, heading=code)
        descs = {h.description for h in hs}
        if len(descs) > 1:
            issue("info", "heading-inconsistent", f"{code}: description differs between groups "
                  f"({len(descs)} variants)", source=src, heading=code)

    generic = {k for k, v in d.data_types.items() if not v.defined_for}
    for h in d.headings():
        t = h.data_type
        m = NUMERIC_TYPE.match(t)
        if not t:
            issue("warning", "data-type", "Empty suggested_type", source=src, group=h.group, heading=h.code)
        elif (m and f"n{m.group(2)}" not in generic) or (not m and t not in generic):
            issue("warning", "data-type", f"Data type {t!r} is not defined in data_types.json for "
                  f"{d.release.family}", source=src, group=h.group, heading=h.code)
        if h.unit and h.unit not in d.units:
            issue("info", "unit", f"Suggested unit {h.unit!r} is not an accepted unit in UNIT.json for "
                  f"{d.release.family}", source=src, group=h.group, heading=h.code)

    pa_headings = {h.code for h in d.headings() if h.data_type == "PA"}
    for heading in d.abbreviations:
        if heading not in occ:
            issue("info", "abbreviation-orphan", f"Abbreviations listed for {heading}, which is not in "
                  f"release {d.version}", heading=heading)
        elif heading not in pa_headings:
            types = sorted({h.data_type for h in occ[heading]})
            issue("info", "abbreviation-type", f"Abbreviations listed for {heading}, whose data type is "
                  f"{types} rather than PA", heading=heading)

    known_groups = set(d.groups)
    for c in d.changes:
        if c.version == d.version and c.group and c.group not in known_groups \
                and "remov" not in c.action.lower():
            issue("info", "changelog", f"Changelog entry '{c.action}' refers to group {c.group}, "
                  f"which is not in the release", group=c.group, heading=c.heading)


def load_dictionary(snapshot: Snapshot, release: Release, settings: Settings | None = None) -> Dictionary:
    return Loader(snapshot, release, settings).load()
