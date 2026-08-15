"""Unit tests for the internal training service.

Verifies the internal-token guard and the model→command mapping without a
running MongoDB or subprocess (routes are imported separately so module-level
Mongo wiring does not block unit tests).
"""

import sys
from pathlib import Path

import pytest

from fastapi import HTTPException

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

import api.training_service.main as training_module
from api.training_service.main import require_service_token, training_command

VALID = "super-secret-internal-token"


def _set_token(value):
    """The guard compares against the module constant, not live env."""
    training_module.SERVICE_TOKEN = value


def test_valid_token_passes():
    _set_token(VALID)
    require_service_token(VALID)


def test_missing_token_rejected():
    _set_token(VALID)
    with pytest.raises(HTTPException) as exc:
        require_service_token(None)
    assert exc.value.status_code == 403


def test_wrong_token_rejected():
    _set_token(VALID)
    with pytest.raises(HTTPException) as exc:
        require_service_token("wrong")
    assert exc.value.status_code == 403


def test_no_token_configured_rejects_everything():
    _set_token("")
    with pytest.raises(HTTPException):
        require_service_token("anything")


@pytest.mark.parametrize(
    ("model", "keyword"),
    [("pricing", "pricing"), ("cv", "cv")],
)
def test_training_command_maps_to_training_script(model, keyword):
    command = training_command(model)
    assert command[0] == sys.executable
    assert command[1] == "scripts/continuous_train.py"
    assert keyword in command


def test_training_command_rejects_unknown_model():
    with pytest.raises(HTTPException) as exc:
        training_command("llm")
    assert exc.value.status_code == 422