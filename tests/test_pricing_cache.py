from api.shared.schemas import PricingRequest
from api.pricing_service.main import build_pricing_cache_key


def _request(**overrides):
    values = {
        "grade": "C",
        "category": "smartphone",
        "brand": "Apple",
        "model": "iPhone 13",
        "original_price": 799.0,
        "age_days": 730,
        "repair_cost": 65.0,
        "defects": ["cosmetic_scratch", "screen_crack"],
    }
    values.update(overrides)
    return PricingRequest(**values)


def test_cache_key_is_independent_of_defect_order():
    first = build_pricing_cache_key(_request(), "model-and-features-v1")
    reordered = build_pricing_cache_key(
        _request(defects=["screen_crack", "cosmetic_scratch"]), "model-and-features-v1"
    )
    assert first == reordered


def test_cache_key_changes_for_any_price_relevant_input():
    key = build_pricing_cache_key(_request(), "model-and-features-v1")
    assert key != build_pricing_cache_key(_request(repair_cost=66.0), "model-and-features-v1")
    assert key != build_pricing_cache_key(_request(age_days=731), "model-and-features-v1")
    assert key != build_pricing_cache_key(_request(), "retrained-model-v2")
