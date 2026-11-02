import json
import zipfile

import pytest

from ags_rdf.releases import discover_registers, discover_releases, select_releases, version_key
from ags_rdf.sources import (FileInfo, GitLabClient, SourceError, fetch_gitlab, git_blob_sha,
                             open_local)


def test_git_blob_sha_matches_git():
    # `printf 'hello\n' | git hash-object --stdin`
    assert git_blob_sha(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_open_local_directory(snapshot):
    assert snapshot.exists("AGS4/AGS4_2/4_2_0/groupsandheadings4-2-0.json")
    assert all(isinstance(v, FileInfo) and v.blob_sha for v in snapshot.files.values())
    assert snapshot.url_for("AGS4/UNIT.json").endswith("/-/blob/master/AGS4/UNIT.json")


def test_open_zip_records_commit_from_comment(tmp_path, mini_copy):
    sha = "710b1f08097264e6508be1397282aece79278fc4"
    zpath = tmp_path / "ASG4-master.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        for p in mini_copy.rglob("*"):
            if p.is_file():
                zf.write(p, "ASG4-master/" + p.relative_to(mini_copy).as_posix())
        zf.comment = sha.encode()
    snap = open_local(zpath, cache_dir=tmp_path / "cache")
    assert snap.commit == sha
    assert snap.committed_date
    assert snap.url_for("AGS4/UNIT.json") == \
        f"https://gitlab.com/AGS-DFWG-Web/ASG4/-/blob/{sha}/AGS4/UNIT.json"
    assert "4.2.0" in discover_releases(snap)


def test_zip_rejects_path_traversal(tmp_path):
    zpath = tmp_path / "evil.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("x/AGS4/../../evil.json", "{}")
    with pytest.raises(SourceError):
        open_local(zpath, cache_dir=tmp_path / "cache")


class FakeResponse:
    def __init__(self, payload=None, content=b"", status=200, headers=None):
        self._payload, self.content, self.status_code = payload, content, status
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    """Serves the mini fixture as if it were the GitLab API."""

    def __init__(self, root, corrupt: str | None = None):
        self.root, self.corrupt, self.headers = root, corrupt, {}

    def get(self, url, params=None, timeout=None):
        params = params or {}
        if url.endswith("/repository/commits/master"):
            return FakeResponse({"id": "a" * 40, "committed_date": "2026-01-02T03:04:05Z"})
        if url.endswith("/repository/tree"):
            items = [{"type": "blob", "name": p.name, "path": p.relative_to(self.root).as_posix(),
                      "id": git_blob_sha(p.read_bytes())}
                     for p in sorted((self.root / "AGS4").rglob("*")) if p.is_file()]
            return FakeResponse(items)
        if url.endswith("/repository/commits"):
            return FakeResponse([{"committed_date": "2026-01-01T00:00:00Z"},
                                 {"committed_date": "2020-01-01T00:00:00Z"}])
        if "/-/raw/" in url:
            rel = url.split("/-/raw/", 1)[1].split("/", 1)[1]
            data = (self.root / rel).read_bytes()
            if self.corrupt and rel.endswith(self.corrupt):
                data += b" "
            return FakeResponse(content=data)
        raise AssertionError(url)


def test_fetch_gitlab_downloads_and_verifies(tmp_path, mini_copy):
    client = GitLabClient(session=FakeSession(mini_copy))
    snap = fetch_gitlab(tmp_path / "cache", client=client)
    assert snap.commit == "a" * 40
    assert snap.exists("AGS4/abbr4.json")
    manifest = json.loads((snap.root / "ags-rdf-source.json").read_text())
    info = manifest["files"]["AGS4/abbr4.json"]
    assert info["first_commit_date"].startswith("2020") and info["last_commit_date"].startswith("2026")
    created, modified = snap.dates_for(["AGS4/abbr4.json"])
    assert (created.year, modified.year) == (2020, 2026)
    # cached on the second call
    assert fetch_gitlab(tmp_path / "cache", client=client).root == snap.root


def test_fetch_gitlab_rejects_checksum_mismatch(tmp_path, mini_copy):
    client = GitLabClient(session=FakeSession(mini_copy, corrupt="UNIT.json"))
    with pytest.raises(SourceError, match="Checksum"):
        fetch_gitlab(tmp_path / "cache", client=client, history=False)


def test_discover_releases_and_registers(snapshot, mini_copy):
    rels = discover_releases(snapshot)
    r = rels["4.2.0"]
    assert r.family == "4.2"
    assert r.group_notes.endswith("group_notes.json")
    assert r.changelog.endswith("Changelog.JSON")
    assert r.rules == "AGS4/AGS4_2/rules.json"  # found in the parent folder
    regs = discover_registers(snapshot)
    assert regs.abbreviations == "AGS4/abbr4.json" and regs.contaminant_codes == "AGS4/AGS4_1/ELRG.json"

    # drafts such as groupsandheadings4-2CPT.JSON are not releases; new releases are picked up
    (mini_copy / "AGS4/AGS4_2/groupsandheadings4-2CPT.JSON").write_text("[]")
    new = mini_copy / "AGS4/AGS4_2/4_2_1/groupsandheadings4-2-1.json"
    new.parent.mkdir()
    new.write_text("[]")
    assert list(discover_releases(open_local(mini_copy))) == ["4.2.0", "4.2.1"]


def test_select_releases(snapshot):
    rels = discover_releases(snapshot)
    assert [r.version for r in select_releases(rels, None)] == ["4.2.0"]
    assert [r.version for r in select_releases(rels, ["all"])] == ["4.2.0"]
    with pytest.raises(KeyError):
        select_releases(rels, ["9.9"])
    assert sorted(["4.1.1", "4.0.4", "4.2.0", "4.1"], key=version_key) == ["4.0.4", "4.1", "4.1.1", "4.2.0"]


def test_fetch_gitlab_falls_back_to_cache_when_offline(tmp_path, mini_copy):
    fetch_gitlab(tmp_path / "cache", client=GitLabClient(session=FakeSession(mini_copy)), history=False)

    class Offline(FakeSession):
        def get(self, url, params=None, timeout=None):
            raise ConnectionError("no network")

    snap = fetch_gitlab(tmp_path / "cache", client=GitLabClient(session=Offline(mini_copy)))
    assert snap.commit == "a" * 40 and snap.exists("AGS4/UNIT.json")
    with pytest.raises(SourceError, match="no cached snapshot"):
        fetch_gitlab(tmp_path / "empty", client=GitLabClient(session=Offline(mini_copy)))
