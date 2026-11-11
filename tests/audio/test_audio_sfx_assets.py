"""scripts/gen_sfx.py and the bundled assets/sfx files."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from editoria.audio import CUES, list_sfx, resolve_sfx
from editoria.audio.wavio import AudioError, read_wav
from editoria.schemas import AssetManifest, read_model

REPO = Path(__file__).resolve().parents[2]
SFX = REPO / "assets" / "sfx"


@pytest.fixture(scope="module")
def gen() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_sfx", REPO / "scripts" / "gen_sfx.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def manifest() -> AssetManifest:
    return read_model(SFX / "manifest.yaml", AssetManifest)


@pytest.fixture(scope="module")
def generated(gen: ModuleType) -> dict[str, bytes]:
    out: dict[str, bytes] = gen.generate_all()
    return out


def test_generator_reproduces_manifest_hashes(
    generated: dict[str, bytes], manifest: AssetManifest
) -> None:
    assert len(generated) == 18
    for asset_id, data in generated.items():
        entry = manifest.get(asset_id)
        assert entry is not None, asset_id
        assert hashlib.sha256(data).hexdigest() == entry.sha256, asset_id


def test_files_on_disk_match_manifest(manifest: AssetManifest) -> None:
    for entry in manifest.assets:
        path = REPO / entry.path
        assert path.exists(), entry.id
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry.sha256, entry.id


def test_generator_is_deterministic_across_runs(
    gen: ModuleType, generated: dict[str, bytes]
) -> None:
    assert gen.generate_all() == generated


def test_generator_check_and_write(gen: ModuleType, tmp_path: Path) -> None:
    out = tmp_path / "sfx ñ"
    assert gen.main(["--out", str(out)]) == 0
    assert gen.main(["--out", str(out), "--check"]) == 0
    mine = (out / "manifest.yaml").read_text(encoding="utf-8")
    assert mine == (SFX / "manifest.yaml").read_text(encoding="utf-8")
    (out / "pop_1.wav").write_bytes(b"corrupto")
    assert gen.main(["--out", str(out), "--check"]) == 1


def test_manifest_entries_are_complete(manifest: AssetManifest) -> None:
    ids = {a.id for a in manifest.assets}
    assert ids == {f"{c}_{v}" for c in CUES for v in (1, 2, 3)}
    for a in manifest.assets:
        assert a.kind == "sfx"
        assert a.license == "CC0-1.0"
        assert a.author == "EditorIA contributors"
        assert len(a.sha256) == 64
        assert a.suggested_use
        assert "tendencia" not in a.suggested_use.lower()
        assert a.path == f"assets/sfx/{a.id}.wav"


def test_wav_format_peak_and_fades(manifest: AssetManifest) -> None:
    total = 0
    for a in manifest.assets:
        path = REPO / a.path
        total += path.stat().st_size
        x, sr = read_wav(path)
        assert sr == 48000 and x.shape[1] == 1, a.id
        peak_db = 20 * np.log10(np.abs(x).max())
        assert abs(peak_db - (-1.0)) < 0.02, (a.id, peak_db)
        assert abs(float(x[-1, 0])) < 1e-3, a.id  # faded tail
        assert abs(float(x[0, 0])) < 1e-2, a.id
        assert abs(float(x.mean())) < 1e-3, a.id  # no DC offset
        assert 0.05 < len(x) / sr < 1.5, a.id
        header = path.read_bytes()[:44]
        assert header[34:36] == (16).to_bytes(2, "little")  # 16 bits
    assert total < 2 * 1024 * 1024


def test_variants_differ() -> None:
    for cue in CUES:
        datas = [(REPO / f"assets/sfx/{cue}_{v}.wav").read_bytes() for v in (1, 2, 3)]
        assert len(set(datas)) == 3, cue


def test_list_and_resolve_sfx() -> None:
    rows = list_sfx()
    assert len(rows) == 18
    assert all(r.exists and r.hash_ok and r.license == "CC0-1.0" for r in rows)
    assert resolve_sfx("pop").name == "pop_1.wav"
    assert resolve_sfx("ding", 3).name == "ding_3.wav"
    with pytest.raises(AudioError, match="no existe"):
        resolve_sfx("trompeta")
    with pytest.raises(AudioError, match="Variantes disponibles"):
        resolve_sfx("pop", 9)
