"""Unit tests for the deterministic synthetic pricing dataset generator.

Used by `scripts/seed_pricing_catalog.py` to feed the product catalog and the
continuous-training snapshot, so determinism and schema are worth locking in.
"""

import tempfile
from pathlib import Path

import pandas as pd

from models.pricing.prepare_pricing_data import generate_market_dataset

EXPECTED_COLUMNS = {
    "brand", "model", "category", "grade", "original_price",
    "sale_price", "age_days", "date", "market_avg_price",
    "repair_cost", "defect_count", "exact_defects",
}


def test_deterministic_given_fixed_seed():
    with tempfile.TemporaryDirectory() as tmp:
        first = Path(tmp) / "a.csv"
        second = Path(tmp) / "b.csv"
        generate_market_dataset(first, rows=500)
        generate_market_dataset(second, rows=500)
        a = pd.read_csv(first)
        b = pd.read_csv(second)
        assert a.equals(b)


def test_schema_and_row_count(tmp_path):
    output = tmp_path / "dataset.csv"
    generate_market_dataset(output, rows=100)
    df = pd.read_csv(output)
    assert len(df) == 100
    assert EXPECTED_COLUMNS.issubset(df.columns)


def test_required_seed_fields_present():
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "c.csv"
        generate_market_dataset(output, rows=200)
        seed_schema = {"brand", "model", "category", "original_price", "sale_price"}
        assert seed_schema.issubset(set(pd.read_csv(output).columns))


def test_grade_distribution_is_sane():
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "d.csv"
        generate_market_dataset(output, rows=1000)
        df = pd.read_csv(output)
        assert set(df["grade"]) == {"A", "B", "C", "D"}


def test_price_is_positive_float():
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "e.csv"
        generate_market_dataset(output, rows=300)
        df = pd.read_csv(output)
        assert (df["sale_price"] > 0).all()
        assert (df["original_price"] > 0).all()