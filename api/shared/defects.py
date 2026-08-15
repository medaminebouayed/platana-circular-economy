"""Canonical defect vocabulary shared by admin review, pricing, and CV training."""

from __future__ import annotations

from typing import Iterable

# Unified catalog — pricing synthetic bank + CV classes + common Dify aliases.
CANONICAL_DEFECTS: list[dict] = [
    {"id": "no_defect", "label_key": "grading.defect.no_defect", "cv_class": "no_defect", "pricing_key": "no_defect"},
    {"id": "screen_crack", "label_key": "grading.defect.screen_crack", "cv_class": "screen_crack", "pricing_key": "screen_crack"},
    {"id": "cosmetic_scratch", "label_key": "grading.defect.cosmetic_scratch", "cv_class": "cosmetic_scratch", "pricing_key": "cosmetic_scratch"},
    {"id": "back_glass_crack", "label_key": "grading.defect.back_glass_crack", "cv_class": "screen_crack", "pricing_key": "screen_crack"},
    {"id": "battery_swollen", "label_key": "grading.defect.battery_weak", "cv_class": "no_defect", "pricing_key": "battery_swollen"},
    {"id": "battery_weak", "label_key": "grading.defect.battery_weak", "cv_class": "no_defect", "pricing_key": "battery_swollen"},
    {"id": "port_broken", "label_key": "grading.defect.missing_part", "cv_class": "no_defect", "pricing_key": "port_broken"},
    {"id": "microphone_dead", "label_key": "grading.defect.missing_part", "cv_class": "no_defect", "pricing_key": "microphone_dead"},
    {"id": "hinge_broken", "label_key": "grading.defect.dent", "cv_class": "no_defect", "pricing_key": "hinge_broken"},
    {"id": "no_power", "label_key": "grading.defect.water_damage", "cv_class": "no_defect", "pricing_key": "no_power"},
    {"id": "scratch", "label_key": "grading.defect.scratch", "cv_class": "cosmetic_scratch", "pricing_key": "cosmetic_scratch"},
    {"id": "dent", "label_key": "grading.defect.dent", "cv_class": "no_defect", "pricing_key": "cosmetic_scratch"},
    {"id": "crack", "label_key": "grading.defect.crack", "cv_class": "screen_crack", "pricing_key": "screen_crack"},
    {"id": "discoloration", "label_key": "grading.defect.discoloration", "cv_class": "cosmetic_scratch", "pricing_key": "cosmetic_scratch"},
    {"id": "missing_part", "label_key": "grading.defect.missing_part", "cv_class": "no_defect", "pricing_key": "port_broken"},
    {"id": "water_damage", "label_key": "grading.defect.water_damage", "cv_class": "no_defect", "pricing_key": "no_power"},
]

CANONICAL_IDS = {item["id"] for item in CANONICAL_DEFECTS}

_ALIAS_MAP: dict[str, str] = {}
for item in CANONICAL_DEFECTS:
    target = item["pricing_key"]
    _ALIAS_MAP[item["id"]] = target
    _ALIAS_MAP[item["id"].replace("_", " ")] = target
    _ALIAS_MAP[item["id"].replace("_", "-")] = target

# Free-form / Dify aliases → canonical id
_EXTRA_ALIASES = {
    "screen crack": "screen_crack",
    "cracked screen": "screen_crack",
    "écran fissuré": "screen_crack",
    "rayure": "cosmetic_scratch",
    "rayure cosmétique": "cosmetic_scratch",
    "scratch": "cosmetic_scratch",
    "good": "no_defect",
    "none": "no_defect",
    "aucun": "no_defect",
    "battery": "battery_swollen",
    "swollen battery": "battery_swollen",
}
_ALIAS_MAP.update(_EXTRA_ALIASES)


def normalize_defect(raw: str) -> str:
    """Map a raw defect string to a canonical defect id."""
    if not raw or not str(raw).strip():
        return "no_defect"
    key = str(raw).strip().lower().replace("-", "_")
    if key in _ALIAS_MAP:
        return _ALIAS_MAP[key]
    key_spaces = str(raw).strip().lower()
    if key_spaces in _ALIAS_MAP:
        return _ALIAS_MAP[key_spaces]
    if "crack" in key_spaces and "back" in key_spaces:
        return "back_glass_crack"
    if "crack" in key_spaces:
        return "screen_crack"
    if "scratch" in key_spaces or "rayure" in key_spaces:
        return "cosmetic_scratch"
    if "battery" in key_spaces:
        return "battery_swollen"
    if "water" in key_spaces:
        return "water_damage"
    if "dent" in key_spaces or "choc" in key_spaces:
        return "dent"
    if "good" in key_spaces or "no defect" in key_spaces:
        return "no_defect"
    return key if key in CANONICAL_IDS else key


def normalize_defect_list(raw_defects: Iterable[str] | None) -> list[str]:
    """Normalize and deduplicate defects; empty input → ['no_defect']."""
    if not raw_defects:
        return ["no_defect"]
    normalized: list[str] = []
    for raw in raw_defects:
        defect_id = normalize_defect(raw)
        if defect_id == "no_defect":
            continue
        if defect_id not in normalized:
            normalized.append(defect_id)
    return normalized or ["no_defect"]


def defects_to_exact_string(defects: Iterable[str]) -> str:
    """Comma-separated string for pricing `exact_defects` feature."""
    cleaned = [d for d in normalize_defect_list(list(defects)) if d != "no_defect"]
    return ",".join(cleaned) if cleaned else "no_defect"


def to_cv_defects(defects: Iterable[str]) -> list[str]:
    """Map canonical defects to CV multi-label classes."""
    cv_classes: list[str] = []
    id_to_cv = {item["id"]: item["cv_class"] for item in CANONICAL_DEFECTS}
    for defect_id in normalize_defect_list(list(defects)):
        cv = id_to_cv.get(defect_id, normalize_defect_name_legacy(defect_id))
        if cv and cv != "no_defect" and cv not in cv_classes:
            cv_classes.append(cv)
    return cv_classes or ["no_defect"]


def normalize_defect_name_legacy(d: str) -> str:
    """Backward-compatible mapper used by CV dataset (models/cv/dataset.py)."""
    d = d.lower()
    if "crack" in d:
        return "screen_crack"
    if "scratch" in d:
        return "cosmetic_scratch"
    if "oil" in d or "stain" in d:
        return "cosmetic_scratch"
    if "good" in d:
        return "no_defect"
    return d


def get_defect_catalog() -> list[dict]:
    """Return selectable defects for admin UI (excludes no_defect; deduped by pricing key)."""
    seen: set[str] = set()
    unique: list[dict] = []
    for item in CANONICAL_DEFECTS:
        if item["id"] == "no_defect" or item["pricing_key"] == "no_defect":
            continue
        key = item["pricing_key"]
        if key in seen:
            continue
        seen.add(key)
        unique.append({"id": key, "label_key": item["label_key"]})
    return unique
