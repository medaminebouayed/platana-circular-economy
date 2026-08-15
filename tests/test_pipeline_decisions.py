"""Unit tests for the local + orchestrator refurb decision logic.

These verify the pipeline's 3-tier decision thresholds and that the local
pipeline stays aligned with the orchestrator's DecisionEngine when the margin
thresholds change (the two services must agree on RESALE_DIRECT / RECONDITION /
RECYCLE).
"""

import pytest

from models.pipeline import RefurbDecisionEngine


@pytest.mark.parametrize(
    ("profit", "expected"),
    [
        (50.0, "RESALE_DIRECT"),
        (49.99, "RECONDITION"),
        (20.0, "RECONDITION"),
        (19.99, "RECYCLE"),
        (0.0, "RECYCLE"),
        (-10.0, "RECYCLE"),
    ],
)
def test_engine_decision_boundaries(profit, expected):
    assert RefurbDecisionEngine.decide(profit) == expected


def test_engine_decision_exact_boundary_values_match_orchestrator():
    from api.orchestrator.main import DecisionEngine

    for profit in (49.99, 50.0, 20.0, 19.99, 0.0):
        assert RefurbDecisionEngine.decide(profit) == DecisionEngine.decide(profit)


def test_engine_refurb_cost_matches_orchestrator_table():
    from api.orchestrator.main import DecisionEngine

    for defect in ("screen_crack", "cosmetic_scratch", "back_glass_crack", "battery_weak", "no_defect"):
        assert RefurbDecisionEngine.REFURB_COSTS[defect] == DecisionEngine.REFURB_COSTS[defect]


def test_refurb_cost_sum_for_known_defects():
    engine = RefurbDecisionEngine.__new__(RefurbDecisionEngine)
    engine.refurb_costs = dict(RefurbDecisionEngine.REFURB_COSTS)
    assert engine.estimate_refurb_cost(["screen_crack", "cosmetic_scratch"]) == 135.0
    assert engine.estimate_refurb_cost(["no_defect"]) == 5.0
    assert engine.estimate_refurb_cost([]) == 0.0


def test_make_decision_recycle_avoids_genai_call():
    """RECYCLE branch must NOT touch the sheet generator."""
    engine = RefurbDecisionEngine.__new__(RefurbDecisionEngine)
    engine.refurb_costs = dict(RefurbDecisionEngine.REFURB_COSTS)
    engine.sheet_generator = None

    engine.predict_resale_price = lambda model, grade, year: 30.0
    result = engine.make_decision("iPhone 13", "C", ["screen_crack"], 2021)

    assert result["Décision Finale"] == "RECYCLE"
    assert result["Fiche Produit GenAI"] is None


def test_make_decision_resale_direct_skips_genai():
    engine = RefurbDecisionEngine.__new__(RefurbDecisionEngine)
    engine.refurb_costs = dict(RefurbDecisionEngine.REFURB_COSTS)
    engine.sheet_generator = None

    engine.predict_resale_price = lambda model, grade, year: 200.0
    result = engine.make_decision("Galaxy S21", "A", [], 2021)

    assert result["Décision Finale"] == "RESALE_DIRECT"
    assert result["Fiche Produit GenAI"] is None