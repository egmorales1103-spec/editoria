"""Captions (A2): word grouping, ASS with styles A/B/C, SRT/VTT/JSON exports."""

from editoria.captions.builder import (
    ASS_FILE,
    JSON_FILE,
    SRT_FILE,
    VTT_FILE,
    AssCaptionBuilder,
    build_for_version,
)
from editoria.captions.formats import parse_srt, read_events_json, to_srt, to_vtt
from editoria.captions.grouping import WordGroup, group_words
from editoria.captions.layout import face_avoid_boxes, stable_placement
from editoria.captions.style import editorial_style, is_distinct

__all__ = [
    "ASS_FILE",
    "JSON_FILE",
    "SRT_FILE",
    "VTT_FILE",
    "AssCaptionBuilder",
    "WordGroup",
    "build_for_version",
    "editorial_style",
    "face_avoid_boxes",
    "group_words",
    "is_distinct",
    "parse_srt",
    "read_events_json",
    "stable_placement",
    "to_srt",
    "to_vtt",
]
