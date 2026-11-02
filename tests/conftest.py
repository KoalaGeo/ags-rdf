import os
import shutil
from pathlib import Path

import pytest

from ags_rdf.builders.common import BuildContext
from ags_rdf.config import Settings
from ags_rdf.loader import load_dictionary
from ags_rdf.releases import discover_releases
from ags_rdf.sources import open_local

FIXTURE = Path(__file__).parent / "fixtures" / "asg4-mini"


@pytest.fixture
def mini_copy(tmp_path) -> Path:
    """A writable copy of the mini source (for tests that modify it)."""
    dst = tmp_path / "ASG4"
    shutil.copytree(FIXTURE, dst)
    return dst


@pytest.fixture(scope="session")
def snapshot():
    return open_local(FIXTURE)


@pytest.fixture(scope="session")
def release(snapshot):
    return discover_releases(snapshot)["4.2.0"]


@pytest.fixture(scope="session")
def dictionary(snapshot, release):
    return load_dictionary(snapshot, release)


@pytest.fixture(scope="session")
def ctx(dictionary, snapshot):
    return BuildContext(dictionary, snapshot, Settings())


@pytest.fixture(scope="session")
def shapes(ctx):
    from ags_rdf.builders.shapes import ShapesBuilder

    return ShapesBuilder(ctx).build()


@pytest.fixture(scope="session")
def ontology(ctx):
    from ags_rdf.builders.ontology import OntologyBuilder

    return OntologyBuilder(ctx).build()


@pytest.fixture(scope="session")
def vocabs(ctx):
    from ags_rdf.builders.vocabularies import VocabularyBuilder

    return VocabularyBuilder(ctx).build_all()


@pytest.fixture(scope="session")
def built(tmp_path_factory, snapshot, release):
    from ags_rdf.build import build_release

    out = tmp_path_factory.mktemp("dist")
    return build_release(snapshot, release, out, Settings())


@pytest.fixture(scope="session")
def real_source():
    """The full AGS source: AGS_RDF_SOURCE=<dir|zip|gitlab>. Skipped when unset."""
    src = os.environ.get("AGS_RDF_SOURCE")
    if not src:
        pytest.skip("set AGS_RDF_SOURCE to a checkout/zip of the ASG4 repo (or 'gitlab') to run")
    from ags_rdf.sources import load_snapshot

    return load_snapshot(src, Path(os.environ.get("AGS_RDF_CACHE", ".cache")), history=False)
