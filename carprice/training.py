"""Train, compare, tune, evaluate and save the car price model.

Run it from the project folder:

    python train.py            # full run: compare 9 algorithms, tune the best
    python train.py --quick    # skip tuning (fast check)
"""

import io
import json
import platform
import time
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.inspection import permutation_importance
from sklearn.model_selection import (
    KFold,
    RandomizedSearchCV,
    cross_val_predict,
    cross_validate,
    train_test_split,
)

from . import eda
from .config import (
    COMPARISON_PATH,
    CV_FOLDS,
    FIGURES_DIR,
    INTERVAL_HIGH_Q,
    INTERVAL_LOW_Q,
    METADATA_PATH,
    MODEL_PATH,
    MODELS_DIR,
    RANDOM_STATE,
    TEST_PREDICTIONS_PATH,
    TEST_SIZE,
)
from .data import FEATURE_COLUMNS, TARGET, build_catalog, build_features, load_clean
from .evaluate import (
    error_by_price_band,
    plot_actual_vs_predicted,
    plot_error_by_band,
    plot_feature_importance,
    plot_model_comparison,
    plot_residuals,
    regression_metrics,
)
from .modeling import SEARCH_SPACES, apply_interval, candidate_models, make_pipeline

TUNE_TOP_N = 3  # how many of the best algorithms get hyper-parameter tuning
TUNING_ITERATIONS = 20
MAX_MODEL_MB = 40  # the saved model must stay small enough to share on GitHub and load quickly


def _median_ape(estimator, X, y):
    """Scorer: negative median absolute percentage error (higher is better)."""
    return -float(np.median(np.abs(estimator.predict(X) - y) / y))


SCORING = {
    "r2": "r2",
    "mae": "neg_mean_absolute_error",
    "rmse": "neg_root_mean_squared_error",
    "medape": _median_ape,
}


def _log(message):
    print(message, flush=True)


def _cv_summary(pipeline, X, y, cv) -> dict:
    result = cross_validate(pipeline, X, y, cv=cv, scoring=SCORING, return_train_score=True)
    return {
        "cv_r2": float(result["test_r2"].mean()),
        "cv_r2_std": float(result["test_r2"].std()),
        "cv_mae": float(-result["test_mae"].mean()),
        "cv_mae_std": float(result["test_mae"].std()),
        "cv_rmse": float(-result["test_rmse"].mean()),
        "cv_medape": float(-result["test_medape"].mean() * 100),
        "train_r2": float(result["train_r2"].mean()),
    }


def _with_test_scores(row, pipeline, X_train, y_train, X_test, y_test):
    predictions = clone(pipeline).fit(X_train, y_train).predict(X_test)
    scores = regression_metrics(y_test, predictions)
    row.update(
        test_r2=scores["r2"],
        test_mae=scores["mae"],
        test_rmse=scores["rmse"],
        test_medape=scores["median_ape"],
    )
    return row


def _tune(name, X_train, y_train, cv):
    """Random search over the settings in SEARCH_SPACES; returns the best settings."""
    pipeline = make_pipeline(candidate_models()[name])
    if "regressor__model__n_jobs" in pipeline.get_params():
        pipeline.set_params(regressor__model__n_jobs=1)  # the search itself runs in parallel
    space = SEARCH_SPACES[name]
    grid_size = int(np.prod([len(values) for values in space.values()]))
    search = RandomizedSearchCV(
        pipeline,
        space,
        n_iter=min(TUNING_ITERATIONS, grid_size),
        cv=cv,
        scoring="neg_mean_absolute_error",
        n_jobs=-1,
        random_state=RANDOM_STATE,
        refit=False,
    )
    search.fit(X_train, y_train)
    return {key: value for key, value in search.best_params_.items() if key != "regressor__model__n_jobs"}


def _size_mb(model) -> float:
    buffer = io.BytesIO()
    joblib.dump(model, buffer, compress=3)
    return buffer.tell() / 1_000_000


def _build(name, params=None):
    pipeline = make_pipeline(candidate_models()[name])
    if params:
        pipeline.set_params(**params)
    return pipeline


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return None if np.isnan(value) else float(value)  # NaN is not valid JSON
    return value


def run(quick: bool = False) -> dict:
    started = time.perf_counter()
    MODELS_DIR.mkdir(exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    _log("1/7  Loading and cleaning the data")
    df, data_report = load_clean()
    reference_year = data_report["reference_year"]
    X = build_features(df)
    y = df[TARGET]
    _log(
        f"     {data_report['raw_rows']} raw rows -> {data_report['clean_rows']} clean rows "
        f"({data_report['duplicate_rows_removed']} duplicates removed)"
    )

    _log("2/7  Splitting: 80% to learn from, 20% locked away for the final test")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )
    cv = KFold(CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)

    _log(f"3/7  Comparing algorithms with {CV_FOLDS}-fold cross-validation")
    rows = []
    for name in candidate_models():
        began = time.perf_counter()
        pipeline = _build(name)
        row = {"model": name, "tuned": False, "params": {}}
        row.update(_cv_summary(pipeline, X_train, y_train, cv))
        _with_test_scores(row, pipeline, X_train, y_train, X_test, y_test)
        row["seconds"] = time.perf_counter() - began
        rows.append(row)
        _log(f"     {name:26s} CV MAE {row['cv_mae']:.3f}  R2 {row['cv_r2']:.3f}")

    if not quick:
        ranked = sorted(
            (row for row in rows if row["model"] in SEARCH_SPACES), key=lambda row: row["cv_mae"]
        )
        _log(f"4/7  Tuning the {TUNE_TOP_N} best tunable algorithms")
        for base in ranked[:TUNE_TOP_N]:
            began = time.perf_counter()
            params = _tune(base["model"], X_train, y_train, cv)
            pipeline = _build(base["model"], params)
            row = {"model": f"{base['model']} (tuned)", "tuned": True, "params": params}
            row.update(_cv_summary(pipeline, X_train, y_train, cv))
            _with_test_scores(row, pipeline, X_train, y_train, X_test, y_test)
            row["seconds"] = time.perf_counter() - began
            rows.append(row)
            _log(f"     {row['model']:26s} CV MAE {row['cv_mae']:.3f}  R2 {row['cv_r2']:.3f}")
    else:
        _log("4/7  Skipping tuning (--quick)")

    comparison = pd.DataFrame(rows).sort_values("cv_mae").reset_index(drop=True)
    comparison["size_mb"] = np.nan
    # Winner: the most accurate model (lowest CV error) whose saved file is at most
    # MAX_MODEL_MB. Big tree ensembles can pass 100 MB; if so the next one is tried.
    final_model = None
    for index, candidate in comparison.iterrows():
        pipeline = _build(candidate["model"].replace(" (tuned)", ""), candidate["params"] or None)
        fitted_all = clone(pipeline).fit(X, y)  # deployed model learns from every cleaned row
        size = _size_mb(fitted_all)
        comparison.loc[index, "size_mb"] = round(size, 1)
        if size <= MAX_MODEL_MB:
            winner, best, final_model = candidate, pipeline, fitted_all
            break
        _log(f"     {candidate['model']} is {size:.0f} MB (over {MAX_MODEL_MB} MB), trying the next best")
    _log(f"     Winner: {winner['model']} ({comparison.loc[winner.name, 'size_mb']} MB)")

    _log("5/7  Final exam on the untouched test set")
    fitted = clone(best).fit(X_train, y_train)
    test_pred = fitted.predict(X_test)
    test_metrics = regression_metrics(y_test, test_pred)
    bands = error_by_price_band(y_test, test_pred)
    _log(
        f"     R2 {test_metrics['r2']:.3f}   MAE {test_metrics['mae']:.3f} lakh   "
        f"typical error {test_metrics['median_ape']:.1f}%"
    )

    _log("6/7  Calibrating the price range and measuring feature importance")
    oof = cross_val_predict(clone(best), X_train, y_train, cv=cv)
    log_errors = np.log1p(y_train.to_numpy()) - np.log1p(oof)
    low_q, high_q = (float(q) for q in np.quantile(log_errors, [INTERVAL_LOW_Q, INTERVAL_HIGH_Q]))
    lower, upper = apply_interval(test_pred, low_q, high_q)
    coverage = float(((y_test.to_numpy() >= lower) & (y_test.to_numpy() <= upper)).mean() * 100)
    _log(f"     80% price range covers {coverage:.1f}% of test cars")

    importance = permutation_importance(
        fitted,
        X_test,
        y_test,
        scoring="neg_mean_absolute_error",
        n_repeats=3 if quick else 10,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    importance_table = pd.DataFrame(
        {
            "feature": FEATURE_COLUMNS,
            "mean": importance.importances_mean,
            "std": importance.importances_std,
        }
    ).sort_values("mean", ascending=False)

    _log("7/7  Saving the model, tables and figures")
    joblib.dump(final_model, MODEL_PATH, compress=3)

    test_table = df.loc[X_test.index, ["Name", "Platform", "Year", "Kms_Driven", "Fuel_Type", "Transmission"]].copy()
    test_table["actual"] = y_test.to_numpy()
    test_table["predicted"] = test_pred
    test_table["lower"] = lower
    test_table["upper"] = upper
    test_table.to_csv(TEST_PREDICTIONS_PATH, index=False)
    comparison.drop(columns=["params"]).to_csv(COMPARISON_PATH, index=False)

    plot_model_comparison(comparison, FIGURES_DIR / "model_comparison.png")
    plot_actual_vs_predicted(y_test, test_pred, FIGURES_DIR / "actual_vs_predicted.png")
    plot_residuals(y_test, test_pred, FIGURES_DIR / "residuals.png")
    plot_feature_importance(importance_table, FIGURES_DIR / "feature_importance.png")
    plot_error_by_band(bands, FIGURES_DIR / "error_by_price_band.png")
    eda_figures = eda.make_figures(df)

    metadata = {
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "training_seconds": round(time.perf_counter() - started, 1),
        "quick_run": quick,
        "versions": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "model_name": winner["model"],
        "model_params": winner["params"],
        "model_size_mb": round(MODEL_PATH.stat().st_size / 1_000_000, 2),
        "reference_year": reference_year,
        "feature_columns": FEATURE_COLUMNS,
        "data": {**data_report, "train_rows": int(len(X_train)), "test_rows": int(len(X_test))},
        "eda": eda.summary(df),
        "eda_figures": eda_figures,
        "cv_folds": CV_FOLDS,
        "comparison": comparison.to_dict(orient="records"),
        "test_metrics": test_metrics,
        "error_by_price_band": bands,
        "feature_importance": importance_table.to_dict(orient="records"),
        "interval": {
            "confidence_percent": round((INTERVAL_HIGH_Q - INTERVAL_LOW_Q) * 100),
            "low_q": low_q,
            "high_q": high_q,
            "test_coverage_percent": coverage,
        },
        "catalog": build_catalog(df),
    }
    METADATA_PATH.write_text(json.dumps(_json_safe(metadata), indent=2))
    _log(f"Done in {metadata['training_seconds']} s. Model: {MODEL_PATH.name} ({metadata['model_size_mb']} MB)")
    return metadata
