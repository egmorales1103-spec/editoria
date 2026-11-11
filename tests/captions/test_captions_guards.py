"""captions: delivered versions are immutable and the builder uses the font family folder."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from editoria.captions import build_for_version
from editoria.captions import builder as builder_mod
from editoria.captions.fonts import caption_fonts_dir
from editoria.cli import app
from editoria.schemas import BrandProfile, StylePreset
from editoria.util import resources
from editoria.util.project import DELIVERED_MARKER, PLAN_FILE, ProjectContext

runner = CliRunner()


def _version(ctx: ProjectContext, fixtures_dir: Path) -> Path:
    vdir = ctx.version_dir("V1")
    vdir.mkdir(parents=True)
    shutil.copy2(fixtures_dir / "plan_fixture.yaml", vdir / PLAN_FILE)
    return vdir


def test_build_refuses_delivered_version(
    fixture_project: ProjectContext, fixtures_dir: Path
) -> None:
    vdir = _version(fixture_project, fixtures_dir)
    (vdir / DELIVERED_MARKER).write_text("V1", encoding="utf-8")
    with pytest.raises(PermissionError, match="entregada"):
        build_for_version(fixture_project, "V1")
    res = runner.invoke(app, ["captions", "build", "demo", "--version", "V1"], terminal_width=200)
    assert res.exit_code != 0 and "entregada" in res.output
    assert not (vdir / "subtitulos.ass").exists()


def _fake_fonts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *families: str) -> Path:
    root = tmp_path / "fuentes"
    for fam in families:
        (root / fam).mkdir(parents=True)
        (root / fam / f"{fam}-Regular.ttf").write_bytes(b"\0")
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(resources, "fonts_dir", lambda: root)
    return root


def test_caption_fonts_dir_prefers_style_font_then_brand_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    style = resources.load_style("A")
    brand = resources.load_brand("master-solution")
    root = _fake_fonts(tmp_path, monkeypatch, style.captions.font)
    assert caption_fonts_dir(style, brand) == root / style.captions.font

    other = StylePreset.model_validate(
        style.model_dump(by_alias=True) | {"captions": {**style.captions.model_dump(), "font": "X"}}
    )
    body = BrandProfile.model_validate(
        brand.model_dump(by_alias=True) | {"fonts": {**brand.fonts.model_dump(), "body": "Cuerpo"}}
    )
    root2 = _fake_fonts(tmp_path / "b", monkeypatch, "Cuerpo")
    assert caption_fonts_dir(other, body) == root2 / "Cuerpo"
    _fake_fonts(tmp_path / "c", monkeypatch)
    assert caption_fonts_dir(other, body) is None  # system fonts


def test_build_for_version_uses_the_family_folder(
    fixture_project: ProjectContext,
    fixtures_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _version(fixture_project, fixtures_dir)
    style = resources.load_style("A")
    root = _fake_fonts(tmp_path, monkeypatch, style.captions.font)
    seen: list[Path | None] = []
    real_init = builder_mod.AssCaptionBuilder.__init__

    def spy(
        self: builder_mod.AssCaptionBuilder, fonts_dir: Path | None = None, **kw: object
    ) -> None:
        seen.append(fonts_dir)
        real_init(self, fonts_dir=fonts_dir, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(builder_mod.AssCaptionBuilder, "__init__", spy)
    build_for_version(fixture_project, "V1")
    assert seen == [root / style.captions.font]
