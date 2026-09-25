"""Metrics and report figures for judging the model."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

BLUE = "#2b6cb0"
MINT = "#1f9a82"
GREY = "#8a94a6"
RED = "#d1495b"

PRICE_BANDS = [0, 2, 5, 10, 20, np.inf]
PRICE_BAND_LABELS = ["under 2 L", "2 to 5 L", "5 to 10 L", "10 to 20 L", "over 20 L"]


def regression_metrics(y_true, y_pred) -> dict:
    """All prices are in lakhs of rupees. Percent errors are in percent."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    ape = np.abs(y_pred - y_true) / y_true
    return {
        "r2": float(r2_score(y_true, y_pred)),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mape": float(ape.mean() * 100),
        "median_ape": float(np.median(ape) * 100),
        "within_10pct": float((ape <= 0.10).mean() * 100),
        "within_20pct": float((ape <= 0.20).mean() * 100),
        "r2_log": float(r2_score(np.log1p(y_true), np.log1p(y_pred))),
    }


def error_by_price_band(y_true, y_pred) -> list[dict]:
    frame = pd.DataFrame({"actual": np.asarray(y_true, float), "predicted": np.asarray(y_pred, float)})
    frame["band"] = pd.cut(frame["actual"], PRICE_BANDS, labels=PRICE_BAND_LABELS, right=False)
    rows = []
    for band, sub in frame.groupby("band", observed=True):
        ape = (sub["predicted"] - sub["actual"]).abs() / sub["actual"]
        rows.append(
            {
                "band": str(band),
                "cars": int(len(sub)),
                "mae": float((sub["predicted"] - sub["actual"]).abs().mean()),
                "median_ape": float(ape.median() * 100),
            }
        )
    return rows


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)


def plot_model_comparison(comparison: pd.DataFrame, path):
    """Cross-validated error and R2 for every algorithm tried."""
    data = comparison.sort_values("cv_mae", ascending=False)
    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    left.barh(data["model"], data["cv_mae"], xerr=data["cv_mae_std"], color=BLUE, alpha=0.9)
    left.set_xlabel("Cross-validated MAE (lakhs) - lower is better")
    right.barh(data["model"], data["cv_r2"].clip(lower=0), xerr=data["cv_r2_std"], color=MINT, alpha=0.9)
    right.set_xlabel("Cross-validated R2 - higher is better")
    for axis in (left, right):
        axis.grid(axis="x", alpha=0.25)
    fig.suptitle("Model comparison (5-fold cross-validation on the training set)")
    _save(fig, path)


def plot_actual_vs_predicted(y_true, y_pred, path):
    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.8))
    for axis, log in ((left, False), (right, True)):
        axis.scatter(y_true, y_pred, s=12, alpha=0.45, color=BLUE, edgecolor="none")
        top = float(max(np.max(y_true), np.max(y_pred))) * 1.05
        low = 0.15 if log else 0
        axis.plot([low, top], [low, top], color=RED, linewidth=1.2, label="perfect prediction")
        if log:
            axis.set_xscale("log")
            axis.set_yscale("log")
        axis.set_xlabel("Actual price (lakhs)")
        axis.set_ylabel("Predicted price (lakhs)")
        axis.grid(alpha=0.25)
    left.set_title("Actual vs predicted (normal scale)")
    right.set_title("Actual vs predicted (log scale, shows cheap cars)")
    left.legend(loc="upper left")
    _save(fig, path)


def plot_residuals(y_true, y_pred, path):
    y_true = np.asarray(y_true, float)
    y_pred = np.asarray(y_pred, float)
    percent_error = (y_pred - y_true) / y_true * 100
    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.6))
    left.hist(np.clip(percent_error, -100, 100), bins=50, color=BLUE, alpha=0.9)
    left.axvline(0, color=RED, linewidth=1.2)
    left.set_xlabel("Prediction error (% of actual price; clipped at +/-100)")
    left.set_ylabel("Number of test cars")
    left.set_title("How far off are the predictions?")
    right.scatter(y_pred, np.clip(percent_error, -100, 100), s=12, alpha=0.4, color=MINT, edgecolor="none")
    right.axhline(0, color=RED, linewidth=1.2)
    right.set_xscale("log")
    right.set_xlabel("Predicted price (lakhs, log scale)")
    right.set_ylabel("Error (%)")
    right.set_title("Errors across the price range")
    for axis in (left, right):
        axis.grid(alpha=0.25)
    _save(fig, path)


def plot_feature_importance(importance: pd.DataFrame, path):
    """`importance` has columns: feature, mean, std (rise in error when shuffled)."""
    data = importance.sort_values("mean")
    fig, axis = plt.subplots(figsize=(7.5, 4.6))
    axis.barh(data["feature"], data["mean"], xerr=data["std"], color=MINT, alpha=0.9)
    axis.set_xlabel("Increase in MAE (lakhs) when the feature is shuffled")
    axis.set_title("Which inputs matter most? (permutation importance, test set)")
    axis.grid(axis="x", alpha=0.25)
    _save(fig, path)


def plot_error_by_band(bands: list[dict], path):
    frame = pd.DataFrame(bands)
    fig, axis = plt.subplots(figsize=(7.5, 4.2))
    axis.bar(frame["band"], frame["median_ape"], color=BLUE, alpha=0.9)
    for index, row in frame.iterrows():
        axis.text(index, row["median_ape"] + 0.4, f"n={row['cars']}", ha="center", fontsize=9)
    axis.set_ylabel("Median error (% of actual price)")
    axis.set_title("Accuracy by price band (test set)")
    axis.grid(axis="y", alpha=0.25)
    _save(fig, path)
