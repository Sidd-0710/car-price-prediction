"""Guards against a retrain that quietly makes the model worse."""

import json

import pytest

from carprice.config import COMPARISON_PATH, METADATA_PATH

from .conftest import needs_model

pytestmark = needs_model


@pytest.fixture(scope="module")
def metadata():
    return json.loads(METADATA_PATH.read_text())


def test_test_set_accuracy_is_reasonable(metadata):
    scores = metadata["test_metrics"]
    assert scores["r2"] >= 0.70
    assert scores["median_ape"] <= 25  # typical error under 25%
    assert scores["within_20pct"] >= 55


def test_model_beats_the_do_nothing_baseline(metadata):
    rows = {row["model"]: row for row in metadata["comparison"]}
    baseline = rows["Baseline (median price)"]["cv_mae"]
    best = min(row["cv_mae"] for row in metadata["comparison"])
    assert best < baseline / 2


def test_price_range_is_honest(metadata):
    coverage = metadata["interval"]["test_coverage_percent"]
    assert 70 <= coverage <= 90  # the "80% range" really covers about 80%


def test_model_file_is_small_enough_to_commit(metadata):
    assert metadata["model_size_mb"] < 50


def test_comparison_table_was_saved():
    assert COMPARISON_PATH.exists()
