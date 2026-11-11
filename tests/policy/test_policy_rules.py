"""Each linter rule with a positive (violating) and a negative (clean) case."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from policy_helpers import external_manifest, sfx_manifest

from editoria.policy import LintContext, has_errors, lint_with
from editoria.schemas import (
    CaptionsSpec,
    EditorialTitle,
    EditPlan,
    Emphasis,
    GraphicItem,
    MusicSpec,
    SfxCue,
    VideoInterval,
    Word,
)
from editoria.util import resources


def base_plan(**over: Any) -> EditPlan:
    data: dict[str, Any] = dict(
        version="V1",
        style="A",
        brand="master-solution",
        video=[
            VideoInterval(id="v01", in_=0.0, out=2.6, method="original"),
            VideoInterval(id="v02", in_=2.6, out=4.0, method="reframe", zoom=1.1, anchor="face"),
            VideoInterval(id="v03", in_=4.0, out=12.0, method="original"),
        ],
        captions=CaptionsSpec(style="A", emphasis=[Emphasis(word=4)]),
        graphics=[
            GraphicItem(
                id="g01", template="palabra_clave", in_=0.3, out=2.0, params={"texto": "Automatizá"}
            )
        ],
        sfx=[SfxCue(cue="pop", at=0.3, ref="g01"), SfxCue(cue="whoosh", at=2.58, ref="v02")],
    )
    data.update(over)
    return EditPlan(**data)


def ctx(**over: Any) -> LintContext:
    words = [
        Word(text=t, start=i * 0.4, end=i * 0.4 + 0.35, prob=0.9)
        for i, t in enumerate(["Hoy", "te", "muestro", "cómo", "automatizar", "tus", "procesos"])
    ]
    data: dict[str, Any] = dict(
        duration=12.0,
        fps=30.0,
        source_size=(1080, 1920),
        style=resources.load_style("A"),
        brand=resources.load_brand("master-solution"),
        project_brand="master-solution",
        registry={},
        sfx_manifest=sfx_manifest(),
        external_manifest=external_manifest(),
        cuts=[4.0, 7.85],
        words=words,
    )
    data.update(over)
    return LintContext(**data)


def ids(plan: EditPlan, lc: LintContext | None = None) -> set[tuple[str, str]]:
    return {(f.id, f.severity) for f in lint_with(plan, lc or ctx())}


def test_clean_plan_has_no_findings() -> None:
    findings = lint_with(base_plan(), ctx())
    assert findings == [], findings


# ---- SCHEMA ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.graphics.append(
            GraphicItem(id="g01", template="palabra_clave", in_=5, out=6, params={"texto": "x"})
        ),
        lambda p: p.graphics.append(
            GraphicItem(id="g02", template="no_existe", in_=5, out=6, params={})
        ),
        lambda p: p.graphics.append(
            GraphicItem(id="g02", template="checklist", in_=5, out=6, params={"items": []})
        ),
        lambda p: p.graphics.append(GraphicItem(id="e01", emoji="E99", in_=5, out=6)),
        lambda p: p.captions.emphasis.append(Emphasis(word=999)),
        lambda p: p.video.__setitem__(
            1, VideoInterval(id="v02", in_=2.6, out=4.0, method="reframe", zoom=None)
        ),
    ],
)
def test_schema_errors(mutate: Callable[[EditPlan], None]) -> None:
    plan = base_plan()
    mutate(plan)
    assert ("SCHEMA", "ERROR") in ids(plan)


def test_schema_missing_style_is_error() -> None:
    assert ("SCHEMA", "ERROR") in ids(base_plan(), ctx(load_errors=[("style", "no existe")]))


# ---- P04 ---------------------------------------------------------------------------------
def test_p04_overlap_and_out_of_range() -> None:
    overlap = base_plan(
        video=[
            VideoInterval(id="v01", in_=0.0, out=3.0, method="original"),
            VideoInterval(id="v02", in_=2.5, out=4.0, method="original"),
        ]
    )
    assert ("P04", "ERROR") in ids(overlap)
    beyond = base_plan(video=[VideoInterval(id="v01", in_=0.0, out=12.5, method="original")])
    assert ("P04", "ERROR") in ids(beyond)
    late_sfx = base_plan(sfx=[SfxCue(cue="pop", at=12.2)])
    assert ("P04", "ERROR") in ids(late_sfx)
    late_graphic = base_plan(
        graphics=[
            GraphicItem(id="g01", template="palabra_clave", in_=11, out=13, params={"texto": "a"})
        ]
    )
    assert ("P04", "ERROR") in ids(late_graphic)


def test_p04_reframe_across_cut_warns() -> None:
    plan = base_plan(
        video=[VideoInterval(id="v01", in_=3.0, out=5.0, method="reframe", zoom=1.1)], sfx=[]
    )
    assert ("P04", "WARN") in ids(plan)


def test_p04_clean_and_frame_tolerance() -> None:
    plan = base_plan(video=[VideoInterval(id="v01", in_=0.0, out=12.02, method="original")])
    assert not any(r == "P04" for r, _ in ids(plan))


def test_p04_unknown_duration_warns() -> None:
    assert ("P04", "WARN") in ids(base_plan(), ctx(duration=None))


# ---- P05 ---------------------------------------------------------------------------------
def _generated_plan() -> EditPlan:
    return base_plan(
        video=[
            VideoInterval(id="v01", in_=0.0, out=8.5, method="original"),
            VideoInterval(id="v02", in_=8.5, out=10.5, method="generated", shot="G01"),
        ],
        sfx=[SfxCue(cue="pop", at=0.3, ref="g01")],
    )


@pytest.mark.parametrize("verdict", ["pendiente", "reintentar", "descartado"])
def test_p05_not_accepted_is_error(verdict: str) -> None:
    lc = ctx(registry={"G01": {"id": "G01", "veredicto": verdict}})
    assert ("P05", "ERROR") in ids(_generated_plan(), lc)


def test_p05_missing_registry_or_row() -> None:
    assert ("P05", "ERROR") in ids(_generated_plan(), ctx(registry=None))
    assert ("P05", "ERROR") in ids(_generated_plan(), ctx(registry={}))


def test_p05_accepted_is_clean() -> None:
    lc = ctx(registry={"G01": {"id": "G01", "veredicto": "aceptado"}})
    assert not any(r == "P05" for r, _ in ids(_generated_plan(), lc))


# ---- P07 ---------------------------------------------------------------------------------
def _zoom_plan(zoom: float) -> EditPlan:
    return base_plan(
        video=[VideoInterval(id="v01", in_=0.5, out=3.5, method="reframe", zoom=zoom)], sfx=[]
    )


def test_p07_style_max_warns_native_limit_errors() -> None:
    assert ("P07", "WARN") in ids(_zoom_plan(1.2))
    assert ("P07", "ERROR") in ids(_zoom_plan(1.3))
    # 720x1280 source is already upscaled 1.5x: any reframe exceeds native detail.
    assert ("P07", "ERROR") in ids(_zoom_plan(1.05), ctx(source_size=(720, 1280)))


def test_p07_within_limits_is_clean() -> None:
    assert not any(r == "P07" for r, _ in ids(_zoom_plan(1.1)))
    # A 4K source has spare native pixels.
    assert not any(r == "P07" for r, _ in ids(_zoom_plan(1.1), ctx(source_size=(2160, 3840))))


# ---- P13 ---------------------------------------------------------------------------------
def _titles_plan(text: str = "3 claves") -> EditPlan:
    return base_plan(
        captions=CaptionsSpec(
            style="A", editorial_titles=[EditorialTitle(text=text, in_=5.0, out=7.0)]
        )
    )


def test_p13_same_style_is_error() -> None:
    style = resources.load_style("A")
    same = style.model_copy(update={"editorial_titles": style.captions})
    assert ("P13", "ERROR") in ids(_titles_plan(), ctx(style=same))


def test_p13_distinct_style_is_clean() -> None:
    assert not any(r == "P13" for r, _ in ids(_titles_plan("Tres claves")))


def test_p13_title_repeating_speech_warns() -> None:
    plan = base_plan(
        captions=CaptionsSpec(
            style="A",
            editorial_titles=[EditorialTitle(text="cómo automatizar", in_=1.0, out=2.0)],
        )
    )
    assert ("P13", "WARN") in ids(plan)


# ---- P14 ---------------------------------------------------------------------------------
def _graphic(template: str, params: dict[str, Any]) -> EditPlan:
    return base_plan(
        graphics=[GraphicItem(id="g01", template=template, in_=0.3, out=2.0, params=params)]
    )


def test_p14_dato_grafico_requires_data_source() -> None:
    plan = _graphic("dato_grafico", {"tipo": "barras", "valores": [40, 75]})
    found = lint_with(plan, ctx())
    assert ("P14", "ERROR") in {(f.id, f.severity) for f in found}
    assert not any(f.id == "SCHEMA" for f in found)


def test_p14_dato_grafico_with_source_is_clean() -> None:
    plan = _graphic(
        "dato_grafico", {"tipo": "barras", "valores": [40, 75], "data_source": "ejemplo"}
    )
    assert not any(r == "P14" for r, _ in ids(plan))


def test_p14_figures_in_other_templates_warn() -> None:
    assert ("P14", "WARN") in ids(_graphic("palabra_clave", {"texto": "Ahorrá 40%"}))
    assert not any(r == "P14" for r, _ in ids(_graphic("palabra_clave", {"texto": "Ahorrá"})))
    with_source = _graphic("palabra_clave", {"texto": "Ahorrá 40%", "data_source": "real"})
    assert not any(r == "P14" for r, _ in ids(with_source))


# ---- P16 ---------------------------------------------------------------------------------
def test_p16_template_not_allowed() -> None:
    plan = _graphic("chat_burbujas", {"mensajes": [{"lado": "izq", "texto": "hola"}]})
    assert ("P16", "ERROR") in ids(plan)  # style A does not allow chat_burbujas


def test_p16_too_many_simultaneous() -> None:
    plan = base_plan(
        graphics=[
            GraphicItem(id="g01", template="palabra_clave", in_=0.3, out=3, params={"texto": "a"}),
            GraphicItem(id="e01", emoji="E01", in_=1.0, out=2.0),
        ]
    )
    assert ("P16", "ERROR") in ids(plan)


def test_p16_sfx_density_spacing_and_cue() -> None:
    dense = base_plan(sfx=[SfxCue(cue="pop", at=t) for t in (0.5, 3.0, 5.5)])
    assert ("P16", "ERROR") in ids(dense)  # 3 in 10 s, style A allows 2
    close = base_plan(sfx=[SfxCue(cue="pop", at=0.5), SfxCue(cue="click", at=1.0)])
    assert ("P16", "ERROR") in ids(close)  # spacing 0.5 < 2.0
    banned = base_plan(sfx=[SfxCue(cue="teclado", at=0.5)])
    assert ("P16", "ERROR") in ids(banned)


def test_p16_clean_density() -> None:
    plan = base_plan(sfx=[SfxCue(cue="pop", at=0.5), SfxCue(cue="ding", at=11.0)])
    assert not any(r == "P16" for r, _ in ids(plan))


# ---- P17 ---------------------------------------------------------------------------------
def test_p17_unlicensed_assets() -> None:
    from editoria.schemas import AssetManifest

    empty = ctx(sfx_manifest=AssetManifest(), external_manifest=AssetManifest())
    plan = base_plan(
        graphics=[GraphicItem(id="e01", emoji="E01", in_=5, out=6)],
        music=MusicSpec(path="m.mp3", asset_id="musica_1"),
    )
    found = [f for f in lint_with(plan, empty) if f.id == "P17"]
    assert {f.element for f in found} == {"sfx[0]", "sfx[1]", "e01", "music"}
    assert all(f.severity == "ERROR" for f in found)


def test_p17_licensed_assets_are_clean() -> None:
    plan = base_plan(
        graphics=[GraphicItem(id="e01", emoji="E01", in_=5, out=6)],
        music=MusicSpec(path="m.mp3", asset_id="musica_1"),
    )
    assert not any(r == "P17" for r, _ in ids(plan))


# ---- BRAND -------------------------------------------------------------------------------
def test_brand_forbidden_claim_in_graphic_and_title() -> None:
    plan = _graphic("titulo_gancho", {"texto": "La IA reemplaza empleados"})
    assert ("BRAND", "ERROR") in ids(plan)
    titled = _titles_plan("Dinero fácil con IA")
    assert ("BRAND", "ERROR") in ids(titled)


def test_brand_clean_and_mismatch_warns() -> None:
    assert not any(r == "BRAND" for r, _ in ids(_graphic("titulo_gancho", {"texto": "Tu equipo"})))
    assert ("BRAND", "WARN") in ids(base_plan(), ctx(project_brand="otra-marca"))


def test_has_errors() -> None:
    assert not has_errors(lint_with(base_plan(), ctx()))
    assert has_errors(lint_with(_zoom_plan(1.4), ctx()))
