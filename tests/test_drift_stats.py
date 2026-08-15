"""Unit tests for the admin drift/alerts counter (pure logic in main_service).

Exercises `assess_drift` without MongoDB by passing synthetic product dicts.
"""

from datetime import datetime, timezone

from api.main_service.main import assess_drift


def _review(grade_changed=False, defects_changed=False, error_eur=0.0,
            market_price=100.0, reviewed_at=None, product_id="p1"):
    return {
        "_id": product_id,
        "brand": "Apple",
        "model": "iPhone 13",
        "model_drift": {
            "pricing_error_eur": error_eur,
            "grade_changed": grade_changed,
            "defects_changed": defects_changed,
        },
        "admin_review": {"grade": "B", "market_price": market_price},
        "reviewed_at": reviewed_at or datetime.now(timezone.utc),
    }


def test_no_reviews_no_alert():
    stats = assess_drift([], max_faults=10, price_threshold_pct=15, window_days=30)
    assert stats["alert"] is False
    assert stats["evaluations"] == 0
    assert stats["grade_changes"] == 0
    assert stats["price_drifts"] == 0


def test_grade_changes_count_toward_alert():
    reviews = [_review(grade_changed=True) for _ in range(10)]
    stats = assess_drift(reviews, max_faults=10, price_threshold_pct=15, window_days=30)
    assert stats["grade_changes"] == 10
    assert stats["alert"] is True


def test_price_drift_threshold_is_exclusive_and_percentage_based():
    reviews = [_review(error_eur=15.0, market_price=100.0)]  # 15% is NOT above 15
    assert assess_drift(reviews, 10, 15, 30)["price_drifts"] == 0
    reviews = [_review(error_eur=15.01, market_price=100.0)]  # 15.01% is above
    assert assess_drift(reviews, 10, 15, 30)["price_drifts"] == 1


def test_missing_market_price_never_counts_as_price_drift():
    review = _review(error_eur=999.0)
    review["admin_review"]["market_price"] = None
    stats = assess_drift([review], 10, 15, 30)
    assert stats["price_drifts"] == 0


def test_recent_is_sorted_newest_first_and_limited_to_ten():
    reviews = [
        _review(product_id=f"p{i}", reviewed_at=datetime(2026, 1, i + 1, tzinfo=timezone.utc))
        for i in range(15)
    ]
    stats = assess_drift(reviews, 10, 15, 30)
    assert len(stats["recent"]) == 10
    assert stats["recent"][0]["id"] == "p14"
    assert stats["recent"][-1]["id"] == "p5"


def test_defect_changes_alone_do_not_trip_alert():
    reviews = [_review(defects_changed=True) for _ in range(20)]
    stats = assess_drift(reviews, 10, 15, 30)
    assert stats["defect_changes"] == 20
    assert stats["alert"] is False


def test_grade_drift_disabled_suppresses_alert():
    reviews = [_review(grade_changed=True) for _ in range(10)]
    stats = assess_drift(reviews, max_faults=10, price_threshold_pct=15,
                         window_days=30, grade_drift_enabled=False)
    assert stats["grade_changes"] == 10
    assert stats["alert"] is False


def test_price_drift_disabled_but_enabled_keeps_counting():
    reviews = [_review(grade_changed=True) for _ in range(5)]
    stats = assess_drift(reviews, max_faults=3, price_threshold_pct=15,
                         window_days=30, grade_drift_enabled=True)
    assert stats["alert"] is True
    stats_off = assess_drift(reviews, max_faults=3, price_threshold_pct=15,
                             window_days=30, grade_drift_enabled=False)
    assert stats_off["grade_changes"] == 5
    assert stats_off["alert"] is False