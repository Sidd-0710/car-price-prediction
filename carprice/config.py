"""Paths and constants shared by training, the API and the UI."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"
REPORTS_DIR = ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"

DATA_PATH = DATA_DIR / "used_cars_india.csv"  # built by: python build_dataset.py
BUILD_REPORT_PATH = DATA_DIR / "build_report.json"
MODEL_PATH = MODELS_DIR / "car_price_model.joblib"
METADATA_PATH = MODELS_DIR / "metadata.json"
COMPARISON_PATH = REPORTS_DIR / "model_comparison.csv"
TEST_PREDICTIONS_PATH = REPORTS_DIR / "test_predictions.csv"

RANDOM_STATE = 42
TEST_SIZE = 0.2
CV_FOLDS = 5

# Categories seen fewer than this many times are grouped into one "rare" bucket
# by the one-hot encoder, so the model can still handle cars it has barely seen.
MIN_CATEGORY_COUNT = 30
# Variant words (like "amt", "plus", "turbo") used as features must appear this often.
MIN_VARIANT_WORD_COUNT = 40

# The 80% prediction interval shown to users (10th to 90th percentile).
INTERVAL_LOW_Q = 0.10
INTERVAL_HIGH_Q = 0.90
