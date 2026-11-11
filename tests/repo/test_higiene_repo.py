"""Repository hygiene for a public repo: no third-party media, no personal data, licences present.

These tests look only at files tracked by git (``git ls-files``), because that is what gets
published. They never touch the network.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

from editoria.schemas import AssetManifest, BrandProfile, StylePreset, read_model

REPO = Path(__file__).resolve().parents[2]


def _load_no_media():
    spec = importlib.util.spec_from_file_location(
        "no_media", REPO / ".github" / "hooks" / "no_media.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


no_media = _load_no_media()


def tracked_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("No hay un repositorio git disponible.")
    names = [n.decode("utf-8") for n in out.split(b"\0") if n]
    return [n for n in names if (REPO / n).exists()]  # staged deletions are not files any more


def read_text(rel: str) -> str | None:
    try:
        return (REPO / rel).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None  # binary file


# ----------------------------------------------------------------------------- media
def test_no_media_outside_allowed_paths() -> None:
    offenders = [f for f in tracked_files() if no_media.is_forbidden(f)]
    assert not offenders, (
        "Medios versionados fuera de assets/sfx/, docs/img/ o templates/graphics/*/preview.png: "
        f"{offenders}"
    )


@pytest.mark.parametrize(
    ("path", "forbidden"),
    [
        ("video.mp4", True),
        ("docs/clip.MOV", True),
        ("referencias/R01.mp4", True),
        ("assets/emoji/E01.gif", True),
        ("docs/portada.jpg", True),
        ("tests/foto.png", True),
        ("templates/graphics/palabra_clave/otra.png", True),
        ("assets/sfx/pop_1.wav", False),
        ("docs/img/demo.png", False),
        ("templates/graphics/palabra_clave/preview.png", False),
        ("README.md", False),
        ("schemas/json/plan.schema.json", False),
    ],
)
def test_no_media_rules(path: str, forbidden: bool) -> None:
    assert no_media.is_forbidden(path) is forbidden


def test_no_media_hook_exit_codes() -> None:
    assert no_media.main(["README.md", "assets/sfx/pop_1.wav"]) == 0
    assert no_media.main(["README.md", "clip.mp4"]) == 1


def test_gitignore_covers_private_and_downloaded_paths() -> None:
    lines = {ln.strip() for ln in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()}
    for needed in (
        "proyectos/",
        ".env",
        "assets/fonts/",
        "assets/emoji/",
        ".dev/",
        "*.mp4",
        "*.gif",
    ):
        assert needed in lines, f".gitignore no cubre {needed}"


# ------------------------------------------------------------------ personal data
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
# International "+506 8888 8888" style, 8-digit local "8888-8888" and "(506) 888-8888".
PHONE_RES = [
    re.compile(r"(?<![\w.])\+\d{1,3}[\s.-]?\d{3,4}[\s.-]?\d{3,4}(?:[\s.-]?\d{2,4})?(?![\w.])"),
    re.compile(r"(?<![\w.:/-])[2-8]\d{3}[\s-]\d{4}(?![\w.:/-])"),
    re.compile(r"\(\d{3}\)\s?\d{3}[\s-]\d{4}"),
]
EMAIL_ALLOWED_DOMAINS = {"example.com", "example.org", "example.net", "users.noreply.github.com"}
EMAIL_ALLOWED_ADDRESSES = {"noreply@github.com"}
# This file holds sample strings for the detectors themselves.
PERSONAL_DATA_SKIP = {"uv.lock", ".secrets.baseline", "tests/repo/test_higiene_repo.py"}


def test_no_emails_outside_whitelist() -> None:
    found: list[str] = []
    for rel in tracked_files():
        if rel in PERSONAL_DATA_SKIP or (text := read_text(rel)) is None:
            continue
        for match in EMAIL_RE.finditer(text):
            addr = match.group(0).lower()
            if addr in EMAIL_ALLOWED_ADDRESSES or addr.rsplit("@", 1)[1] in EMAIL_ALLOWED_DOMAINS:
                continue
            found.append(f"{rel}: {match.group(0)}")
    assert not found, f"Correos fuera de la lista blanca: {found}"


def test_no_phone_numbers() -> None:
    found: list[str] = []
    for rel in tracked_files():
        if rel in PERSONAL_DATA_SKIP or (text := read_text(rel)) is None:
            continue
        for rx in PHONE_RES:
            for match in rx.finditer(text):
                found.append(f"{rel}: {match.group(0)!r}")
    assert not found, f"Posibles teléfonos: {found}"


def test_detectors_work() -> None:
    assert EMAIL_RE.search("escribime a alguien@empresa.cr")
    assert any(rx.search("llamá al +506 8888 8888") for rx in PHONE_RES)
    assert any(rx.search("whatsapp 8888-8888") for rx in PHONE_RES)
    assert not any(rx.search("fecha 2026-11-08 y fps 30000/1001, 1080 1920") for rx in PHONE_RES)


# ---------------------------------------------------------- excluded kit material
# Built from pieces so that this file does not contain the names it forbids.
EXCLUDED_NAMES = [
    "Mapa_Visual_" + "9_Referencias",
    "ABRIR_" + "CATALOGO",
    "06_Laminas_" + "Visuales",
    "02_Referencias_" + "Usuario",
    "Inventario_" + "Referencias",
    "original_" + "name",
]
# CLAUDE.md belongs to the lead and names the excluded kit files to warn about them.
EXCLUDED_NAMES_ALLOWED_FILES = {"CLAUDE.md"}


def test_no_excluded_kit_names_in_tracked_files() -> None:
    found: list[str] = []
    for rel in tracked_files():
        if rel in EXCLUDED_NAMES_ALLOWED_FILES:
            continue
        # file names count too
        found += [f"{rel} (nombre de archivo)" for n in EXCLUDED_NAMES if n.lower() in rel.lower()]
        text = read_text(rel)
        if text is None:
            continue
        low = text.lower()
        found += [f"{rel}: {n}" for n in EXCLUDED_NAMES if n.lower() in low]
    assert not found, f"Referencias a material excluido del kit: {found}"


def test_references_do_not_link_to_third_party_posts_or_name_creators() -> None:
    text = (REPO / "references" / "patrones.yaml").read_text(encoding="utf-8")
    assert "http" not in text, "patrones.yaml no debe tener enlaces"
    assert not re.search(r"(?<!\w)@\w", text), "patrones.yaml no debe nombrar cuentas"
    for rel in ("docs/referencias.md", "prompts/prompt-maestro.md"):
        body = (REPO / rel).read_text(encoding="utf-8").lower()
        assert "instagram.com" not in body and "tiktok.com/@" not in body


# ------------------------------------------------------------ community files
COMMUNITY_FILES = [
    "README.md",
    "README.en.md",
    "LICENSE",
    "LICENSE-docs",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "THIRD_PARTY.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    ".github/CODEOWNERS",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/bug.yml",
    ".github/ISSUE_TEMPLATE/plantilla-nueva.yml",
    ".github/ISSUE_TEMPLATE/estilo-nuevo.yml",
    ".github/workflows/ci.yml",
    ".pre-commit-config.yaml",
]


@pytest.mark.parametrize("rel", COMMUNITY_FILES)
def test_community_file_exists_and_is_tracked(rel: str) -> None:
    assert (REPO / rel).is_file(), f"Falta {rel}"
    assert (REPO / rel).stat().st_size > 0, f"{rel} está vacío"
    assert rel in tracked_files(), f"{rel} no está versionado"


def test_code_of_conduct_has_contact_placeholder_not_invented_email() -> None:
    text = (REPO / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8")
    assert "[completar: correo de contacto]" in text
    assert "Contributor Covenant" in text and "2.1" in text


def test_issue_forms_are_valid_yaml_with_body() -> None:
    for name in ("bug", "plantilla-nueva", "estilo-nuevo"):
        data = yaml.safe_load(
            (REPO / ".github" / "ISSUE_TEMPLATE" / f"{name}.yml").read_text("utf-8")
        )
        assert data["name"] and data["description"] and data["body"]


def test_ci_matrix_and_steps() -> None:
    ci = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text("utf-8"))
    matrix = ci["jobs"]["test"]["strategy"]["matrix"]
    assert set(matrix["os"]) == {"ubuntu-24.04", "windows-latest"}
    assert set(matrix["python"]) == {"3.11", "3.12"}
    runs = " ".join(str(s.get("run", "")) for s in ci["jobs"]["test"]["steps"])
    for needle in (
        "uv sync --all-extras",
        "playwright install",
        "editoria doctor",
        "ruff check",
        "ruff format --check",
        "mypy",
        'pytest -m "not slow and not network"',
    ):
        assert needle in runs, f"CI no ejecuta {needle}"
    assert "ffmpeg" in (REPO / ".github" / "workflows" / "ci.yml").read_text("utf-8").lower()


def test_pre_commit_hooks() -> None:
    cfg = yaml.safe_load((REPO / ".pre-commit-config.yaml").read_text("utf-8"))
    ids = {h["id"] for repo in cfg["repos"] for h in repo["hooks"]}
    assert {"ruff", "ruff-format", "detect-secrets", "check-added-large-files", "no-media"} <= ids
    big = next(h for r in cfg["repos"] for h in r["hooks"] if h["id"] == "check-added-large-files")
    assert "--maxkb=1024" in big["args"]


def test_third_party_lists_every_declared_dependency() -> None:
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text("utf-8"))
    names: list[str] = list(pyproject["project"]["dependencies"])
    for group in pyproject["project"].get("optional-dependencies", {}).values():
        names += group
    names += pyproject.get("dependency-groups", {}).get("dev", [])
    third_party = (REPO / "THIRD_PARTY.md").read_text(encoding="utf-8").lower()
    missing = []
    for spec in names:
        name = re.split(r"[<>=!~\[ ]", spec, maxsplit=1)[0].lower()
        if name not in third_party:
            missing.append(name)
    assert not missing, f"THIRD_PARTY.md no menciona: {missing}"
    for needle in ("ffmpeg", "chromium", "playwright", "noto", "inter", "whisper", "gpl"):
        assert needle in third_party, f"THIRD_PARTY.md debería mencionar {needle}"


# ----------------------------------------------------------------- manifests
def _manifest_paths() -> list[Path]:
    paths = [REPO / "assets" / "externos.yaml"]
    sfx = REPO / "assets" / "sfx" / "manifest.yaml"
    if sfx.exists():
        paths.append(sfx)
    return paths


@pytest.mark.parametrize("path", _manifest_paths(), ids=lambda p: str(p.relative_to(REPO)))
def test_every_asset_has_a_licence(path: Path) -> None:
    manifest = read_model(path, AssetManifest)
    assert manifest.assets, f"{path.name} no declara assets"
    ids = [a.id for a in manifest.assets]
    assert len(ids) == len(set(ids)), "ids duplicados"
    for asset in manifest.assets:
        assert asset.license.strip(), f"{asset.id}: falta la licencia"
        assert asset.path.strip(), f"{asset.id}: falta la ruta"


def test_external_manifest_content() -> None:
    manifest = read_model(REPO / "assets" / "externos.yaml", AssetManifest)
    emojis = {a.id: a for a in manifest.assets if a.kind == "emoji"}
    assert sorted(emojis) == [f"E0{i}" for i in range(1, 7)]
    font = manifest.get("font/Inter")
    assert font is not None and font.kind == "font" and "OFL" in font.license
    for asset in manifest.assets:
        assert re.fullmatch(r"[0-9a-f]{64}", asset.sha256), f"{asset.id}: sha256 inválido o vacío"
        assert asset.source_url.startswith("https://"), asset.id
        assert asset.license_url.startswith("https://"), asset.id
        assert asset.author.strip() and asset.attribution.strip(), asset.id
    for asset in emojis.values():
        assert asset.license == "CC-BY-4.0"
        assert asset.source_url.startswith("https://fonts.gstatic.com/s/e/notoemoji/")
        assert asset.path == f"assets/emoji/{asset.id}.gif"
        assert "Noto" in asset.attribution
    # downloaded files must never be tracked
    tracked = tracked_files()
    assert not [f for f in tracked if f.startswith(("assets/emoji/", "assets/fonts/"))]


def test_fetch_assets_script_rejects_unknown_hosts() -> None:
    spec = importlib.util.spec_from_file_location(
        "fetch_assets", REPO / "scripts" / "fetch_assets.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError):
        module.download("https://ejemplo.invalid/x.gif")
    with pytest.raises(ValueError):
        module.download("http://fonts.gstatic.com/x.gif")
    # every URL of the manifest is on the allow-list
    for entry in module.load_manifest().get("assets", []):
        host = entry["source_url"].split("/")[2]
        assert host in module.ALLOWED_HOSTS, entry["id"]


# -------------------------------------------------------- brands, styles, prompts
@pytest.mark.parametrize("path", sorted((REPO / "styles").glob("*.yaml")), ids=lambda p: p.name)
def test_styles_validate(path: Path) -> None:
    style = read_model(path, StylePreset)
    assert style.references and style.description
    assert all(re.fullmatch(r"[RW]\d{2}", r) for r in style.references)


@pytest.mark.parametrize(
    "path", sorted((REPO / "brands").glob("*/brand.yaml")), ids=lambda p: p.parent.name
)
def test_brands_validate(path: Path) -> None:
    brand = read_model(path, BrandProfile)
    assert brand.provisional is True or path.parent.name != "_plantilla"


def test_master_solution_brand_is_provisional_with_forbidden_claims() -> None:
    brand = read_model(REPO / "brands" / "master-solution" / "brand.yaml", BrandProfile)
    assert brand.provisional
    claims = " | ".join(brand.forbidden_claims).lower()
    for needle in ("reemplaza empleados", "dinero fácil", "negocio que funciona solo"):
        assert needle in claims
    assert len(brand.glossary) >= 20


def test_references_files() -> None:
    patrones = yaml.safe_load((REPO / "references" / "patrones.yaml").read_text("utf-8"))[
        "patrones"
    ]
    assert [p["id"] for p in patrones] == [f"R0{i}" for i in range(1, 10)]
    web = yaml.safe_load((REPO / "references" / "web.yaml").read_text("utf-8"))["referencias"]
    assert [w["id"] for w in web] == [f"W{i:02d}" for i in range(1, 26)]
    for w in web:
        assert set(w) >= {"id", "categoria", "url", "nota"} and w["url"].startswith("https://")
    # styles only cite references that exist
    known = {p["id"] for p in patrones} | {w["id"] for w in web}
    for path in (REPO / "styles").glob("*.yaml"):
        for ref in read_model(path, StylePreset).references:
            assert ref in known, f"{path.name}: referencia inexistente {ref}"


def test_prompts() -> None:
    generic = (REPO / "prompts" / "prompt-maestro.md").read_text(encoding="utf-8")
    ms = (REPO / "prompts" / "prompt-maestro.master-solution.md").read_text(encoding="utf-8")
    for placeholder in ("{{MARCA}}", "{{PUBLICO}}", "{{VOZ}}", "{{RESTRICCIONES}}"):
        assert placeholder in generic
        assert placeholder not in ms
    for text in (generic, ms):
        assert text.rstrip().endswith("FIN DEL PROMPT."), "hay texto posterior a FIN DEL PROMPT."
        assert "nueve videos" not in text.lower() and "9 videos" not in text.lower()
    body = generic.split("COPIAR DESDE AQUÍ", 1)[1]
    assert "Master Solution" not in body and "Costa Rica" not in body
    assert "Master Solution" in ms


def test_uso_con_chat_has_no_zip_or_nine_videos() -> None:
    text = (REPO / "docs" / "uso-con-chat.md").read_text(encoding="utf-8").lower()
    assert "zip" not in text and "nueve" not in text and "9 videos" not in text


def test_skills_and_agents_have_valid_frontmatter() -> None:
    def frontmatter(path: Path) -> dict:
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n"), path
        return yaml.safe_load(text.split("---\n", 2)[1])

    for skill in ("editar-video", "aplicar-feedback"):
        meta = frontmatter(REPO / ".claude" / "skills" / skill / "SKILL.md")
        assert meta["name"] == skill and len(meta["description"]) > 40
    assert (REPO / ".claude" / "skills" / "editar-video" / "references").is_dir()

    expected = {
        "director-creativo",
        "operador-tomas",
        "motion-designer",
        "disenador-sonido",
        "revisor-qc",
    }
    found = set()
    for path in (REPO / ".claude" / "agents").glob("*.md"):
        meta = frontmatter(path)
        assert meta["name"] == path.stem and meta["description"] and meta["tools"]
        found.add(path.stem)
    assert found == expected
    qc = frontmatter(REPO / ".claude" / "agents" / "revisor-qc.md")
    tools = {t.strip() for t in str(qc["tools"]).split(",")}
    assert tools.isdisjoint({"Write", "Edit", "MultiEdit", "NotebookEdit"}), (
        "revisor-qc debe ser solo lectura"
    )
