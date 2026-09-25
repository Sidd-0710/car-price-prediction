"""Exploratory data analysis: figures for the report and a few headline numbers."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import FIGURES_DIR
from .data import TARGET
from .evaluate import BLUE, GREY, MINT, RED


def _save(fig, name):
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / name, dpi=150, facecolor="white")
    plt.close(fig)


def summary(df: pd.DataFrame) -> dict:
    """Numbers quoted in the README and shown in the UI."""
    age = df["Listing_Year"] - df["Year"]
    return {
        "correlation_age_price": float(np.corrcoef(age, np.log(df[TARGET]))[0, 1]),
        "median_price_by_fuel": df.groupby("Fuel_Type")[TARGET].median().round(2).to_dict(),
        "median_price_by_transmission": df.groupby("Transmission")[TARGET].median().round(2).to_dict(),
        "median_price_by_owner": df.groupby("Owner")[TARGET].median().round(2).to_dict(),
        "median_price_by_platform": df.groupby("Platform")[TARGET].median().round(2).to_dict(),
        "top_brands": df["Brand"].value_counts().head(10).to_dict(),
    }


def make_figures(df: pd.DataFrame) -> list[str]:
    """Write the EDA charts to reports/figures and return their file names."""
    snapshot = int(df["Listing_Year"].max())
    age = (df["Listing_Year"] - df["Year"]).clip(lower=0)
    names = []

    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.2))
    left.hist(df[TARGET], bins=60, color=BLUE, alpha=0.9)
    left.set_title("Selling price is heavily skewed")
    left.set_xlabel("Selling price (lakhs)")
    left.set_ylabel("Cars")
    right.hist(np.log1p(df[TARGET]), bins=60, color=MINT, alpha=0.9)
    right.set_title("After log transform it is much more balanced")
    right.set_xlabel("log(1 + price)")
    _save(fig, "eda_price_distribution.png")
    names.append("eda_price_distribution.png")

    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.6))
    left.scatter(age, df[TARGET], s=8, alpha=0.3, color=BLUE, edgecolor="none")
    left.set_yscale("log")
    left.set_xlabel("Age in years when listed")
    left.set_ylabel("Selling price (lakhs, log scale)")
    left.set_title("Older cars are cheaper")
    right.scatter(df["Kms_Driven"], df[TARGET], s=8, alpha=0.3, color=MINT, edgecolor="none")
    right.set_yscale("log")
    right.set_xscale("log")
    right.set_xlabel("Kilometres driven (log scale)")
    right.set_title("More kilometres, lower price")
    for axis in (left, right):
        axis.grid(alpha=0.25)
    _save(fig, "eda_price_vs_age_kms.png")
    names.append("eda_price_vs_age_kms.png")

    brands = df.groupby("Brand")[TARGET].agg(["median", "size"])
    brands = brands[brands["size"] >= 30].sort_values("median")
    fig, axis = plt.subplots(figsize=(8, 5.6))
    axis.barh(brands.index, brands["median"], color=BLUE, alpha=0.9)
    axis.set_xlabel("Median selling price (lakhs)")
    axis.set_title("Median price by brand (brands with 30+ listings)")
    axis.grid(axis="x", alpha=0.25)
    _save(fig, "eda_price_by_brand.png")
    names.append("eda_price_by_brand.png")

    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2))
    for axis, column, title in (
        (axes[0], "Fuel_Type", "Fuel type"),
        (axes[1], "Transmission", "Transmission"),
        (axes[2], "Owner", "Previous owners"),
    ):
        groups = [(str(key), sub[TARGET].values) for key, sub in df.groupby(column)]
        axis.boxplot([values for _, values in groups], tick_labels=[label for label, _ in groups], showfliers=False)
        axis.set_title(f"Price by {title.lower()}")
        axis.set_ylabel("Selling price (lakhs)")
        axis.grid(axis="y", alpha=0.25)
    _save(fig, "eda_price_by_category.png")
    names.append("eda_price_by_category.png")

    numeric = pd.DataFrame(
        {
            "Price": df[TARGET],
            "Age": age,
            "Kms driven": df["Kms_Driven"],
            "Owner": df["Owner"],
        }
    )
    correlation = numeric.corr(method="spearman")
    fig, axis = plt.subplots(figsize=(5.6, 4.6))
    image = axis.imshow(correlation, cmap="RdBu_r", vmin=-1, vmax=1)
    axis.set_xticks(range(len(correlation)), correlation.columns, rotation=30, ha="right")
    axis.set_yticks(range(len(correlation)), correlation.columns)
    for i in range(len(correlation)):
        for j in range(len(correlation)):
            axis.text(j, i, f"{correlation.iloc[i, j]:.2f}", ha="center", va="center", fontsize=9)
    axis.set_title("Rank correlation between numeric columns")
    fig.colorbar(image, ax=axis, fraction=0.046)
    _save(fig, "eda_correlation.png")
    names.append("eda_correlation.png")

    counts = df["Year"].value_counts().sort_index()
    fig, axis = plt.subplots(figsize=(8, 3.8))
    axis.bar(counts.index, counts.values, color=GREY, alpha=0.9)
    axis.set_xlabel("Registration year")
    axis.set_ylabel("Listings")
    axis.set_title(f"Listings by registration year (collected 2025-{snapshot})")
    _save(fig, "eda_listings_by_year.png")
    names.append("eda_listings_by_year.png")

    return names
