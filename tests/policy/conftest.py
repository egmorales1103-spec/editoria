"""Local fixtures: licensed asset manifests and camera cuts for the fixture project."""

from __future__ import annotations

import pytest
from policy_helpers import external_manifest, sfx_manifest

from editoria.schemas import CutList, write_model
from editoria.util import resources
from editoria.util.project import CUTS_FILE, ProjectContext


@pytest.fixture
def licensed_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resources, "load_sfx_manifest", sfx_manifest)
    monkeypatch.setattr(resources, "load_external_manifest", external_manifest)


@pytest.fixture
def project(fixture_project: ProjectContext, licensed_assets: None) -> ProjectContext:
    """fixture_project + cortes.json (4.0 and 7.85 s) + licensed manifests."""
    write_model(fixture_project.analysis(CUTS_FILE), CutList(cuts=[4.0, 7.85]))
    return fixture_project
