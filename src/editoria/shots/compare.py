"""``shots compare``: side-by-side sheet + background drift metrics. Recommends, never decides.

Background = canvas minus the dilated face box (P08). Metrics, original vs candidate, both
conformed to the canvas with the same transform:

- SSIM of the background: ffmpeg ``ssim`` filter over crops around the face box, area-weighted.
- Flicker: RMS of the extra frame-to-frame change of the mean background luma (0-255 levels).
- Colour difference: CIELAB distance (dE76) between the mean background colours.

They detect drift of the room, not identity, hands or lip-sync: those stay a human review (P24).
"""

from __future__ import annotations

import math
import re
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from editoria.schemas import Box, Canvas, FaceTrack, parse_fps, write_model
from editoria.shots import registry
from editoria.shots.errors import ShotError
from editoria.shots.media import (
    conform_filter,
    encode_silent,
    extract_frame,
    scaled_face,
    video_info,
)
from editoria.shots.models import CompareResult, Recommendation, ShotMeta
from editoria.util import ffmpeg
from editoria.util.geometry import base_transform
from editoria.util.project import ProjectContext

FACE_DILATE_PX = 80  # canvas px added around the face box before excluding it
MIN_REGION_PX = 16  # smaller strips are not worth an SSIM window

# Recommendation thresholds (documented in docs/modulos/tomas.md; tune per project if needed).
SSIM_STABLE = 0.90
SSIM_DRIFT = 0.75
DELTA_E_STABLE = 5.0
DELTA_E_DRIFT = 10.0
FLICKER_STABLE = 3.0
FLICKER_DRIFT = 8.0

_SSIM_ALL = re.compile(r"All:(\S+)")
THUMB_W = 360


def _face_union(face: FaceTrack | None, start: float, end: float) -> Box | None:
    """Union of the face samples around the segment (fallback: the whole-video union)."""
    if face is None:
        return None
    boxes = [s.box for s in face.samples if s.box is not None and start - 0.5 <= s.t <= end + 0.5]
    if not boxes:
        return face.union_box
    x1 = min(b.x for b in boxes)
    y1 = min(b.y for b in boxes)
    x2 = max(b.x2 for b in boxes)
    y2 = max(b.y2 for b in boxes)
    return Box(x=x1, y=y1, w=x2 - x1, h=y2 - y1)


def background_regions(canvas: Canvas, face_box: Box | None) -> list[tuple[int, int, int, int]]:
    """Rectangles (x, y, w, h) covering the canvas minus ``face_box`` (even-aligned)."""
    full = Box(x=0, y=0, w=canvas.width, h=canvas.height)
    if face_box is None:
        return [(0, 0, canvas.width, canvas.height)]
    x1, y1 = max(face_box.x, 0), max(face_box.y, 0)
    x2, y2 = min(face_box.x2, canvas.width), min(face_box.y2, canvas.height)
    cand = [
        Box(x=0, y=0, w=full.w, h=y1),  # above
        Box(x=0, y=y2, w=full.w, h=full.h - y2),  # below
        Box(x=0, y=y1, w=x1, h=y2 - y1),  # left
        Box(x=x2, y=y1, w=full.w - x2, h=y2 - y1),  # right
    ]
    out: list[tuple[int, int, int, int]] = []
    for b in cand:
        w, h = b.w - b.w % 2, b.h - b.h % 2
        if w >= MIN_REGION_PX and h >= MIN_REGION_PX:
            out.append((b.x - b.x % 2, b.y - b.y % 2, w, h))
    return out


def _ssim_regions(
    ref: Path, cand: Path, regions: list[tuple[int, int, int, int]], work: Path
) -> list[float]:
    """Mean SSIM (Y/U/V 'All') per region using ffmpeg's ssim filter on crops."""
    n = len(regions)
    split_r = "".join(f"[r{i}]" for i in range(n))
    split_c = "".join(f"[c{i}]" for i in range(n))
    chains = [f"[0:v]split={n}{split_r}", f"[1:v]split={n}{split_c}"]
    maps: list[str | Path] = []
    for i, (x, y, w, h) in enumerate(regions):
        crop = f"crop={w}:{h}:{x}:{y}"
        chains.append(f"[r{i}]{crop}[a{i}]")
        chains.append(f"[c{i}]{crop}[b{i}]")
        chains.append(f"[a{i}][b{i}]ssim=stats_file=ssim_{i}.log[o{i}]")
        maps += ["-map", f"[o{i}]"]
    ffmpeg.run(
        ["-i", ref, "-i", cand, "-filter_complex", ";".join(chains), *maps, "-f", "null", "-"],
        cwd=work,
    )
    means: list[float] = []
    for i in range(n):
        text = (work / f"ssim_{i}.log").read_text(encoding="utf-8", errors="replace")
        vals = []
        for m in _SSIM_ALL.finditer(text):
            try:
                v = float(m.group(1))
            except ValueError:
                continue
            if math.isfinite(v):
                vals.append(min(v, 1.0))
        if not vals:
            raise ShotError("ffmpeg no devolvió valores de SSIM; no se pudo medir el fondo.")
        means.append(sum(vals) / len(vals))
    return means


def _raw_frames(src: Path, dst: Path, w: int, h: int) -> np.ndarray:
    ffmpeg.run(
        ["-i", src, "-vf", f"scale={w}:{h}:flags=area", "-pix_fmt", "rgb24", "-f", "rawvideo", dst]
    )
    data = np.fromfile(dst, dtype=np.uint8)
    frame_size = w * h * 3
    n = data.size // frame_size
    if n < 2:
        raise ShotError(f"'{src.name}' tiene menos de 2 cuadros; no se puede comparar.")
    return data[: n * frame_size].reshape(n, h, w, 3)


def _srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    c = rgb.astype(np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array(
        [[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
         [0.0193339, 0.1191920, 0.9503041]]
    )  # fmt: skip
    xyz = (m @ lin) / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def background_metrics(
    ref: np.ndarray, cand: np.ndarray, mask: np.ndarray
) -> tuple[float, float, int]:
    """(flicker, colour dE76, index of the most moving frame of ``ref``)."""
    n = min(len(ref), len(cand))
    ref, cand = ref[:n], cand[:n]
    weights = np.array([0.299, 0.587, 0.114])
    y_ref = (ref[:, mask, :].astype(np.float64) @ weights).mean(axis=1)
    y_cand = (cand[:, mask, :].astype(np.float64) @ weights).mean(axis=1)
    extra = np.diff(y_cand) - np.diff(y_ref)
    flicker = float(np.sqrt(np.mean(extra**2)))
    mean_ref = ref[:, mask, :].astype(np.float64).mean(axis=(0, 1))
    mean_cand = cand[:, mask, :].astype(np.float64).mean(axis=(0, 1))
    delta_e = float(np.linalg.norm(_srgb_to_lab(mean_ref) - _srgb_to_lab(mean_cand)))
    motion = np.abs(np.diff(ref.astype(np.int16), axis=0)).mean(axis=(1, 2, 3))
    return flicker, delta_e, int(np.argmax(motion)) + 1


def recommend(ssim: float, flicker: float, delta_e: float) -> tuple[Recommendation, list[str]]:
    """Map the metrics to a recommendation (a suggestion for the human reviewer)."""
    reasons: list[str] = []
    drift = False
    if ssim < SSIM_DRIFT:
        drift = True
        reasons.append(f"SSIM del fondo {ssim:.3f} < {SSIM_DRIFT}: el fondo cambió de forma.")
    if delta_e > DELTA_E_DRIFT:
        drift = True
        reasons.append(f"Diferencia de color {delta_e:.1f} > {DELTA_E_DRIFT:g}: color desplazado.")
    if flicker > FLICKER_DRIFT:
        drift = True
        reasons.append(f"Parpadeo del fondo {flicker:.1f} > {FLICKER_DRIFT:g}.")
    if drift:
        return "deriva", reasons
    stable = ssim >= SSIM_STABLE and delta_e <= DELTA_E_STABLE and flicker <= FLICKER_STABLE
    if stable:
        return "estable", ["Las tres métricas del fondo están dentro de lo esperado."]
    if ssim < SSIM_STABLE:
        reasons.append(f"SSIM del fondo {ssim:.3f} (zona gris, < {SSIM_STABLE}).")
    if delta_e > DELTA_E_STABLE:
        reasons.append(f"Diferencia de color {delta_e:.1f} (zona gris, > {DELTA_E_STABLE:g}).")
    if flicker > FLICKER_STABLE:
        reasons.append(f"Parpadeo del fondo {flicker:.1f} (zona gris, > {FLICKER_STABLE:g}).")
    return "revisar", reasons


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def _contact_sheet(
    ref: Path, cand: Path, times: list[tuple[str, float]], work: Path, out: Path, shot_id: str
) -> None:
    """2 rows (original / candidate) x 4 columns (start, middle, end, most motion)."""
    pad, label_h, side_w = 12, 34, 120
    thumbs: dict[tuple[int, int], Image.Image] = {}
    for col, (_, t) in enumerate(times):
        for row, video in enumerate((ref, cand)):
            png = work / f"hoja_{row}_{col}.png"
            extract_frame(video, t, png, width=THUMB_W)
            with Image.open(png) as im:
                thumbs[(row, col)] = im.convert("RGB").copy()
    th_w, th_h = thumbs[(0, 0)].size
    cols = len(times)
    width = side_w + cols * (th_w + pad) + pad
    height = label_h + 2 * (th_h + pad) + pad + label_h
    sheet = Image.new("RGB", (width, height), (24, 24, 28))
    draw = ImageDraw.Draw(sheet)
    font = _font(20)
    draw.text(
        (pad, 6), f"{shot_id}: original (arriba) vs candidato (abajo)", fill="white", font=font
    )
    for col, (name, t) in enumerate(times):
        x = side_w + pad + col * (th_w + pad)
        draw.text((x, label_h - 4), f"{name} · {t:.2f} s", fill=(200, 200, 200), font=font)
        for row in (0, 1):
            y = label_h + 24 + row * (th_h + pad)
            sheet.paste(thumbs[(row, col)], (x, y))
    for row, name in enumerate(("Original", "Candidato")):
        y = label_h + 24 + row * (th_h + pad) + th_h // 2
        draw.text((pad, y), name, fill="white", font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=90)


def _report_md(meta: ShotMeta, res: CompareResult, regions: int) -> str:
    label = {"estable": "ESTABLE", "revisar": "REVISAR", "deriva": "DERIVA"}[res.recommendation]
    lines = [
        f"# Comparativa {meta.id}",
        "",
        f"Segmento {meta.start:g}–{meta.end:g} s. Cambio pedido: {meta.change}",
        "",
        f"**Recomendación automática: {label}.** Es una sugerencia; la decisión es humana "
        f"(`editoria shots verdict`).",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| SSIM del fondo ({regions} recortes, 1.0 = idéntico) | {res.ssim_background:.3f} |",
        f"| SSIM del recorte más distinto | {res.ssim_background_min:.3f} |",
        f"| Parpadeo del fondo (niveles 0–255) | {res.flicker:.2f} |",
        f"| Diferencia de color (CIELAB dE76) | {res.color_delta_e:.2f} |",
        f"| Cuadro de mayor movimiento | {res.t_motion:.2f} s |",
        "",
        "Motivos:",
        "",
        *[f"- {r}" for r in res.reasons],
        "",
        "## Qué NO mide esto",
        "",
        "Las métricas miran solo el fondo (lienzo menos el rostro dilatado). No miden identidad, "
        "piel, manos, bordes ni sincronía labial. Revisá la hoja y el video lado a lado a "
        "velocidad normal y cuadro a cuadro; ante duda visible, se conserva el original.",
        "",
        "## Archivos",
        "",
        f"- Hoja: `{res.sheet}`",
        f"- Lado a lado: `{res.side_by_side}`",
        f"- Métricas: `{res.metrics_file}`",
        "",
    ]
    return "\n".join(lines)


def compare_shot(ctx: ProjectContext, shot_id: str, canvas: Canvas | None = None) -> CompareResult:
    """Compare the imported candidate with the original segment and write the sheet/metrics."""
    with ffmpeg.command_log(ctx.commands_log):
        return _compare_shot(ctx, shot_id, canvas or Canvas())


def _compare_shot(ctx: ProjectContext, shot_id: str, canvas: Canvas) -> CompareResult:
    sid = registry.normalize_id(shot_id)
    meta = registry.load_meta(ctx, sid)
    if meta.imported is None:
        raise ShotError(f"{sid} todavía no tiene resultado. Importalo con 'editoria shots import'.")
    cand = ctx.root / meta.imported.conformed
    seg = ctx.root / meta.pack_dir / "segmento.mp4"
    if not cand.is_file() or not seg.is_file():
        raise ShotError(f"Faltan archivos de {sid} (segmento o resultado conformado).")

    cdir = registry.comparison_dir(ctx, sid)
    cdir.mkdir(parents=True, exist_ok=True)
    work = cdir / "_trabajo"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    try:
        fps = parse_fps(meta.fps)
        seg_info = video_info(seg)
        face = ctx.load_face()
        face_frame = (face.frame_w, face.frame_h) if face else None
        union = _face_union(face, meta.start, meta.end)
        face_seg = scaled_face(seg_info, union, face_frame)

        # Original conformed with the SAME transform the candidate went through.
        ref = cdir / "referencia.mp4"
        ref_vf = conform_filter(seg_info, canvas, fps, face_seg)
        encode_silent(seg, ref, ref_vf, meta.duration, fps)

        face_canvas: Box | None = None
        if face_seg is not None:
            bt = base_transform(seg_info.width, seg_info.height, canvas, face_seg)
            face_canvas = bt.to_canvas(face_seg).dilate(FACE_DILATE_PX)
        regions = background_regions(canvas, face_canvas)

        ssims = _ssim_regions(ref, cand, regions, work)
        areas = [w * h for (_, _, w, h) in regions]
        ssim_bg = sum(s * a for s, a in zip(ssims, areas, strict=True)) / sum(areas)

        sw, sh = max(canvas.width // 10, 8), max(canvas.height // 10, 8)
        ref_raw = _raw_frames(ref, work / "ref.raw", sw, sh)
        cand_raw = _raw_frames(cand, work / "cand.raw", sw, sh)
        mask = np.ones((sh, sw), dtype=bool)
        if face_canvas is not None:
            x0, y0 = max(face_canvas.x, 0) // 10, max(face_canvas.y, 0) // 10
            x1 = min(-(-face_canvas.x2 // 10), sw)
            y1 = min(-(-face_canvas.y2 // 10), sh)
            mask[y0:y1, x0:x1] = False
        if not mask.any():
            raise ShotError("La caja de rostro cubre todo el lienzo; no hay fondo que medir.")
        flicker, delta_e, motion_idx = background_metrics(ref_raw, cand_raw, mask)

        dur = min(meta.duration, len(ref_raw) / float(fps), len(cand_raw) / float(fps))
        t_motion = min(motion_idx / float(fps), max(dur - 1 / float(fps), 0.0))
        times = [
            ("Inicio", 0.0),
            ("Medio", dur / 2),
            ("Fin", max(dur - 1.5 / float(fps), 0.0)),
            ("Mayor movimiento", t_motion),
        ]
        sheet = cdir / f"hoja_{sid}.jpg"
        _contact_sheet(ref, cand, times, work, sheet, sid)

        side = cdir / f"lado_a_lado_{sid}.mp4"
        ffmpeg.run(
            [
                "-i", ref, "-i", cand,
                "-filter_complex",
                "[0:v]scale=540:-2[a];[1:v]scale=540:-2[b];[a][b]hstack=inputs=2,format=yuv420p[v]",
                "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-movflags", "+faststart", side,
            ]
        )  # fmt: skip

        recommendation, reasons = recommend(ssim_bg, flicker, delta_e)
        metrics_file = cdir / "metricas.json"
        result = CompareResult(
            shot_id=sid,
            frames=min(len(ref_raw), len(cand_raw)),
            ssim_background=round(ssim_bg, 4),
            ssim_background_min=round(min(ssims), 4),
            flicker=round(flicker, 3),
            color_delta_e=round(delta_e, 3),
            t_motion=round(t_motion, 3),
            face_box_canvas=(
                [face_canvas.x, face_canvas.y, face_canvas.w, face_canvas.h]
                if face_canvas
                else None
            ),
            recommendation=recommendation,
            reasons=reasons,
            sheet=registry.rel(ctx, sheet),
            metrics_file=registry.rel(ctx, metrics_file),
            side_by_side=registry.rel(ctx, side),
        )
        write_model(metrics_file, result)
        (cdir / "informe.md").write_text(
            _report_md(meta, result, len(regions)), encoding="utf-8", newline="\n"
        )
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)
