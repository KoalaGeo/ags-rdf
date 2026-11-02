"""Obtain a local snapshot of the AGS4 data dictionary JSON files.

The authoritative source is the ``AGS4/`` folder of the AGS Data Format Working
Group repository on GitLab (https://gitlab.com/AGS-DFWG-Web/ASG4). A snapshot can
be obtained in three ways:

* ``gitlab`` / ``gitlab:<ref>``: list the repository tree with the GitLab API and
  download every ``.json`` file under ``AGS4/`` pinned to the resolved commit.
  Each download is verified against the git blob SHA reported by the tree API.
* a local directory: a checkout of the repository, an extracted archive, or a
  previously fetched cache directory.
* a ``.zip`` archive as downloaded from GitLab ("Download source code"). GitLab
  stores the commit SHA in the zip comment, which is recorded for provenance.

Every snapshot records where it came from (``Snapshot.origin``), the commit SHA
and commit date when known, so generated RDF can cite exactly what it was built
from.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import re
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

log = logging.getLogger(__name__)

GITLAB_URL = "https://gitlab.com"
GITLAB_PROJECT = "AGS-DFWG-Web/ASG4"
DICTIONARY_ROOT = "AGS4"
MANIFEST_NAME = "ags-rdf-source.json"


class SourceError(RuntimeError):
    """Raised when a source snapshot cannot be obtained or read."""


class RateLimited(SourceError):
    """GitLab answered 429 Too Many Requests."""


def git_blob_sha(data: bytes) -> str:
    """The SHA-1 git uses to identify a blob with this content."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


@dataclass
class FileInfo:
    path: str
    blob_sha: str | None = None
    first_commit_date: str | None = None
    last_commit_date: str | None = None


@dataclass
class Snapshot:
    """A local copy of (at least) the ``AGS4/`` folder of the ASG4 repository."""

    root: Path
    origin: str
    project_url: str = f"{GITLAB_URL}/{GITLAB_PROJECT}"
    commit: str | None = None
    committed_date: str | None = None
    files: dict[str, FileInfo] = field(default_factory=dict)
    fetcher: Callable[[str], Path] | None = field(default=None, repr=False)

    # ------------------------------------------------------------------ files
    def exists(self, rel: str) -> bool:
        return (self.root / rel).is_file()

    def path(self, rel: str) -> Path:
        p = self.root / rel
        if not p.is_file() and self.fetcher is not None:
            return self.fetcher(rel)
        if not p.is_file():
            raise SourceError(f"{rel} is not present in the source snapshot at {self.root}")
        return p

    def list_files(self, under: str = DICTIONARY_ROOT) -> list[str]:
        base = self.root / under
        if not base.is_dir():
            return []
        return sorted(p.relative_to(self.root).as_posix() for p in base.rglob("*") if p.is_file())

    def find(self, pattern: str, under: str = DICTIONARY_ROOT) -> list[str]:
        """Files whose path (relative to the repo root) matches ``pattern`` (regex, case-insensitive)."""
        rx = re.compile(pattern, re.IGNORECASE)
        return [f for f in self.list_files(under) if rx.search(f)]

    def read_json(self, rel: str) -> Any:
        raw = self.path(rel).read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            log.warning("%s is not valid UTF-8; decoding as Windows-1252", rel)
            text = raw.decode("cp1252")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise SourceError(f"{rel} is not valid JSON: {e}") from e

    # ------------------------------------------------------------- provenance
    def url_for(self, rel: str) -> str:
        """A permanent (commit-pinned when possible) URL for a source file."""
        ref = self.commit or "master"
        return f"{self.project_url}/-/blob/{ref}/{quote(rel)}"

    def dates_for(self, rels: list[str]) -> tuple[dt.date, dt.date]:
        """(created, modified) dates for content derived from ``rels``.

        Uses per-file git history when the snapshot was fetched from GitLab,
        otherwise the snapshot commit date, otherwise file modification times.
        """
        firsts, lasts = [], []
        for r in rels:
            info = self.files.get(r)
            if info and info.first_commit_date:
                firsts.append(_to_date(info.first_commit_date))
            if info and info.last_commit_date:
                lasts.append(_to_date(info.last_commit_date))
        fallback = _to_date(self.committed_date) if self.committed_date else None
        if fallback is None:
            mtimes = [dt.datetime.fromtimestamp((self.root / r).stat().st_mtime, dt.UTC).date()
                      for r in rels if (self.root / r).is_file()]
            fallback = max(mtimes) if mtimes else dt.date.today()
        created = min(firsts) if firsts else fallback
        modified = max(lasts) if lasts else fallback
        return created, max(created, modified)

    def to_manifest(self) -> dict:
        return {
            "origin": self.origin,
            "project_url": self.project_url,
            "commit": self.commit,
            "committed_date": self.committed_date,
            "files": {k: vars(v) for k, v in sorted(self.files.items())},
        }

    def write_manifest(self) -> None:
        (self.root / MANIFEST_NAME).write_text(json.dumps(self.to_manifest(), indent=2) + "\n",
                                               encoding="utf-8", newline="\n")


def _to_date(s: str) -> dt.date:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).date()


# --------------------------------------------------------------------- GitLab
class GitLabClient:
    """Minimal, unauthenticated GitLab REST client (only what we need)."""

    def __init__(self, project: str = GITLAB_PROJECT, base_url: str = GITLAB_URL, session=None,
                 timeout: float = 60.0):
        import requests

        self.project = project
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", "ags-rdf (+https://github.com/KoalaGeo/ags-rdf)")
        token = os.environ.get("GITLAB_TOKEN")
        if token:  # optional: raises GitLab's API rate limits
            self.session.headers["PRIVATE-TOKEN"] = token
        self.timeout = timeout

    @property
    def api(self) -> str:
        return f"{self.base_url}/api/v4/projects/{quote(self.project, safe='')}"

    def _get(self, url: str, retries: int = 2, **params):
        for attempt in range(retries + 1):
            r = self.session.get(url, params=params, timeout=self.timeout)
            if r.status_code != 429:
                r.raise_for_status()
                return r
            wait = min(float(r.headers.get("Retry-After", 5) or 5), 15.0)
            if attempt < retries:
                log.info("GitLab rate limit; retrying in %.0fs", wait)
                time.sleep(wait)
        raise RateLimited("GitLab API rate limit reached; try again later, set GITLAB_TOKEN, "
                          "or use a local source")

    def resolve_commit(self, ref: str) -> tuple[str, str]:
        c = self._get(f"{self.api}/repository/commits/{quote(ref, safe='')}").json()
        return c["id"], c["committed_date"]

    def tree(self, path: str, ref: str) -> list[dict]:
        items, page = [], 1
        while True:
            r = self._get(f"{self.api}/repository/tree", path=path, ref=ref, recursive="true",
                          per_page=100, page=page)
            items.extend(r.json())
            nxt = r.headers.get("x-next-page")
            if not nxt:
                return items
            page = int(nxt)

    def raw(self, path: str, ref: str) -> bytes:
        return self._get(f"{self.base_url}/{self.project}/-/raw/{ref}/{quote(path)}").content

    def history(self, path: str, ref: str) -> tuple[str | None, str | None]:
        """(first, last) commit dates touching ``path`` (best effort)."""
        try:
            commits = self._get(f"{self.api}/repository/commits", retries=1, ref_name=ref, path=path,
                                per_page=100).json()
        except RateLimited:
            raise
        except Exception as e:  # noqa: BLE001 - history is optional provenance
            log.info("Could not read history for %s: %s", path, e)
            return None, None
        if not commits:
            return None, None
        return commits[-1]["committed_date"], commits[0]["committed_date"]


def fetch_gitlab(cache_dir: Path, ref: str = "master", project: str = GITLAB_PROJECT,
                 root: str = DICTIONARY_ROOT, include: str = r"\.json$", history: bool = True,
                 client: GitLabClient | None = None) -> Snapshot:
    """Scrape the JSON files under ``root`` from GitLab into ``cache_dir/<commit>/``."""
    client = client or GitLabClient(project)
    try:
        commit, committed = client.resolve_commit(ref)
    except Exception as e:  # noqa: BLE001 - offline or rate limited: use the newest cached snapshot
        cached = _newest_cached(Path(cache_dir))
        if cached is None:
            raise SourceError(f"Cannot reach GitLab ({e}) and no cached snapshot in {cache_dir}") from e
        log.warning("Cannot reach GitLab (%s); using cached snapshot %s", e, cached.commit)
        return cached
    target = Path(cache_dir) / commit
    manifest = target / MANIFEST_NAME
    if manifest.is_file():
        log.info("Using cached snapshot %s", target)
        snap = open_local(target)
    else:
        log.info("Fetching %s@%s (%s) from GitLab", project, ref, commit[:8])
        tree = client.tree(root, commit)
        rx = re.compile(include, re.IGNORECASE)
        snap = Snapshot(root=target, origin=f"{client.base_url}/{project}",
                        project_url=f"{client.base_url}/{project}", commit=commit,
                        committed_date=committed)
        for item in tree:
            if item["type"] != "blob" or not rx.search(item["name"]):
                continue
            data = client.raw(item["path"], commit)
            if git_blob_sha(data) != item["id"]:
                raise SourceError(f"Checksum mismatch downloading {item['path']}")
            dest = target / item["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            snap.files[item["path"]] = FileInfo(item["path"], item["id"])
        if history:
            try:
                for rel, info in snap.files.items():
                    info.first_commit_date, info.last_commit_date = client.history(rel, commit)
            except RateLimited as e:
                log.warning("Per-file commit dates unavailable (%s); dates fall back to the "
                            "snapshot commit date", e)
        snap.write_manifest()
        log.info("Fetched %d files", len(snap.files))

    def _lazy(rel: str) -> Path:  # fetch files outside the include filter (e.g. PDFs) on demand
        dest = target / rel
        if not dest.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(client.raw(rel, commit))
        return dest

    snap.fetcher = _lazy
    return snap


def _newest_cached(cache_dir: Path) -> Snapshot | None:
    snaps = [open_local(m.parent) for m in cache_dir.glob(f"*/{MANIFEST_NAME}")]
    snaps = [s for s in snaps if s.committed_date]
    return max(snaps, key=lambda s: s.committed_date) if snaps else None


# ---------------------------------------------------------------------- local
def open_local(path: Path, cache_dir: Path | None = None) -> Snapshot:
    """Open a local directory or GitLab ``.zip`` archive as a snapshot."""
    path = Path(path)
    if path.is_file() and path.suffix.lower() == ".zip":
        return _open_zip(path, Path(cache_dir or ".cache"))
    if not path.is_dir():
        raise SourceError(f"{path} is neither a directory nor a .zip archive")

    root = _find_repo_root(path)
    manifest = root / MANIFEST_NAME
    if manifest.is_file():
        m = json.loads(manifest.read_text(encoding="utf-8"))
        snap = Snapshot(root=root, origin=m.get("origin", str(root)),
                        project_url=m.get("project_url", f"{GITLAB_URL}/{GITLAB_PROJECT}"),
                        commit=m.get("commit"), committed_date=m.get("committed_date"),
                        files={k: FileInfo(**v) for k, v in m.get("files", {}).items()})
    else:
        snap = Snapshot(root=root, origin=str(path.resolve()), commit=_git_head(root))
    for rel in snap.list_files():
        snap.files.setdefault(rel, FileInfo(rel, git_blob_sha((root / rel).read_bytes())))
    return snap


def _find_repo_root(path: Path) -> Path:
    if (path / DICTIONARY_ROOT).is_dir():
        return path
    if path.name == DICTIONARY_ROOT:
        return path.parent
    children = [c for c in path.iterdir() if (c / DICTIONARY_ROOT).is_dir()]
    if len(children) == 1:  # e.g. an extracted archive: <dir>/ASG4-master/AGS4
        return children[0]
    raise SourceError(f"Could not find an '{DICTIONARY_ROOT}/' folder in {path}")


def _git_head(root: Path) -> str | None:
    head = root / ".git" / "HEAD"
    if not head.is_file():
        return None
    ref = head.read_text().strip()
    if ref.startswith("ref:"):
        p = root / ".git" / ref.split(" ", 1)[1]
        return p.read_text().strip() if p.is_file() else None
    return ref


def _open_zip(path: Path, cache_dir: Path) -> Snapshot:
    with zipfile.ZipFile(path) as zf:
        comment = zf.comment.decode("ascii", "ignore").strip()
        commit = comment if re.fullmatch(r"[0-9a-f]{40}", comment) else None
        key = commit or hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        target = cache_dir / f"zip-{key}"
        newest = max((zi.date_time for zi in zf.infolist()), default=None)
        if not target.is_dir():
            tmp = target.with_suffix(".tmp")
            shutil.rmtree(tmp, ignore_errors=True)
            for zi in zf.infolist():
                name = zi.filename
                if f"/{DICTIONARY_ROOT}/" not in f"/{name}" or zi.is_dir():
                    continue
                if ".." in Path(name).parts or name.startswith("/"):
                    raise SourceError(f"Unsafe path in archive: {name}")
                dest = tmp / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(zi))
            tmp.rename(target)
    snap = open_local(target)
    snap.origin = str(path.resolve())
    snap.commit = snap.commit or commit
    if newest and not snap.committed_date:
        # GitLab sets every entry's timestamp to the commit time
        snap.committed_date = dt.datetime(*newest, tzinfo=dt.UTC).isoformat()
    return snap


def load_snapshot(source: str, cache_dir: Path = Path(".cache"), history: bool = True) -> Snapshot:
    """Resolve a ``--source`` argument: ``gitlab``, ``gitlab:<ref>``, a directory or a .zip."""
    if source == "gitlab" or source.startswith("gitlab:"):
        ref = source.split(":", 1)[1] if ":" in source else "master"
        return fetch_gitlab(Path(cache_dir) / "gitlab", ref=ref, history=history)
    return open_local(Path(source), cache_dir=Path(cache_dir))
