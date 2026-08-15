"""Consistency tests across the CV config, training entrypoint, and model default.

Guards against parameters drifting between the YAML config and the code that
actually trains or runs the model (the production audit originally flagged
`num_defects` disagreements).
"""

import sys
from pathlib import Path

import pytest
import yaml

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

CONFIG = yaml.safe_load((repo_root / "configs" / "cv_config.yaml").read_text(encoding="utf-8"))


def test_train_entrypoint_uses_configured_defect_count():
    """models/cv/train.py hard-codes num_defects; it must match the YAML."""
    source = (repo_root / "models" / "cv" / "train.py").read_text(encoding="utf-8")
    configured = CONFIG["model"]["num_defects"]
    assert f"num_defects={configured}" in source


def test_config_defect_count_is_three():
    assert CONFIG["model"]["num_defects"] == 3


def test_inference_thresholds_defined_in_config():
    assert CONFIG["inference"]["confidence_threshold"] == 0.7
    assert CONFIG["inference"]["defect_threshold"] == 0.5