"""Unit tests for canonical defect normalization."""

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "api"))

from shared.defects import (
    normalize_defect,
    normalize_defect_list,
    defects_to_exact_string,
    to_cv_defects,
    get_defect_catalog,
)


def test_normalize_free_form_crack():
    assert normalize_defect("Cracked screen") == "screen_crack"
    assert normalize_defect("écran fissuré") == "screen_crack"


def test_normalize_scratch_aliases():
    assert normalize_defect("scratch") == "cosmetic_scratch"
    assert normalize_defect("rayure cosmétique") == "cosmetic_scratch"


def test_empty_defects_become_no_defect():
    assert normalize_defect_list([]) == ["no_defect"]
    assert normalize_defect_list(None) == ["no_defect"]


def test_deduplicate_defects():
    assert normalize_defect_list(["scratch", "cosmetic_scratch", "crack"]) == [
        "cosmetic_scratch",
        "screen_crack",
    ]


def test_exact_defects_string():
    assert defects_to_exact_string(["screen_crack", "battery_swollen"]) == "screen_crack,battery_swollen"
    assert defects_to_exact_string([]) == "no_defect"


def test_cv_defect_mapping():
    assert to_cv_defects(["screen_crack", "port_broken"]) == ["screen_crack"]


def test_catalog_excludes_no_defect():
    ids = {item["id"] for item in get_defect_catalog()}
    assert "no_defect" not in ids
    assert "screen_crack" in ids
