"""Tests for the guarded continuous-training entrypoint helpers.

`active_version` reads a JSON pointer file (latest.json / latest_training.json)
that selects which immutable artifact is promoted; these tests lock the parsing
and fallback behavior without launching any training run.
"""

import json
import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from scripts.continuous_train import active_version


def test_active_version_reads_pointer(tmp_path):
    (tmp_path / "latest.json").write_text(json.dumps({"version_id": "pricing-20260813T000000Z-v3"}), encoding="utf-8")
    assert active_version(tmp_path) == "pricing-20260813T000000Z-v3"


def test_active_version_supports_custom_pointer_name(tmp_path):
    (tmp_path / "latest_training.json").write_text(json.dumps({"version_id": "cv-v12"}), encoding="utf-8")
    assert active_version(tmp_path, "latest_training.json") == "cv-v12"


def test_active_version_returns_none_when_missing(tmp_path):
    assert active_version(tmp_path) is None


def test_active_version_returns_none_on_invalid_json(tmp_path):
    (tmp_path / "latest.json").write_text("not json", encoding="utf-8")
    assert active_version(tmp_path) is None


def test_active_version_returns_none_when_key_missing(tmp_path):
    (tmp_path / "latest.json").write_text(json.dumps({"other": 1}), encoding="utf-8")
    assert active_version(tmp_path) is None