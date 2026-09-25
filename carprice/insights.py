"""Numbers for the website's Market and Model pages, and similar real listings."""

import json
from functools import lru_cache

import pandas as pd

from .config import METADATA_PATH, TEST_PREDICTIONS_PATH
from .data import OWNER_LABELS, TARGET, load_clean


@lru_cache(maxsize=1)
def dataset() -> pd.DataFrame:
    return load_clean()[0]


def _median_rows(df: pd.DataFrame, column: str, labels: dict | None = None, order: list | None = None) -> list[dict]:
    stats = df.groupby(column)[TARGET].agg(median="median", count="size")
    keys = order if order is not None else list(stats.sort_values("median", ascending=False).index)
    return [
        {
            "label": (labels or {}).get(key, str(key)),
            "median": round(float(stats.loc[key, "median"]), 2),
            "count": int(stats.loc[key, "count"]),
        }
        for key in keys
        if key in stats.index
    ]


@lru_cache(maxsize=1)
def market_insights() -> dict:
    df = dataset()
    reference = int(df["Listing_Year"].max())
    prices = df[TARGET]

    bin_width, last_bin = 1, 25
    histogram = []
    for start in range(0, last_bin, bin_width):
        in_bin = prices[(prices >= start) & (prices < start + bin_width)]
        histogram.append({"from": start, "to": start + bin_width, "count": int(len(in_bin))})

    by_year = df.groupby("Year")[TARGET].agg(median="median", count="size")
    by_year = by_year[by_year["count"] >= 5]

    brands = df.groupby("Brand")[TARGET].agg(median="median", count="size")
    brands = brands[brands["count"] >= 30].sort_values("median", ascending=False)

    top_brands = list(df["Brand"].value_counts().head(4).index)
    aged = df.assign(Age=(df["Listing_Year"] - df["Year"]).clip(lower=0))
    depreciation = {}
    for brand in top_brands:
        rows = aged[(aged["Brand"] == brand) & (aged["Age"] <= 14)].groupby("Age")[TARGET].agg(median="median", count="size")
        rows = rows[rows["count"] >= 5]
        depreciation[brand] = [{"age": int(age), "median": round(float(row["median"]), 2), "count": int(row["count"])} for age, row in rows.iterrows()]

    popular = (
        df.groupby(["Brand", "Model"])
        .agg(
            count=(TARGET, "size"),
            median=(TARGET, "median"),
            year=("Year", "median"),
            kms=("Kms_Driven", "median"),
            fuel=("Fuel_Type", lambda values: values.mode().iloc[0]),
            transmission=("Transmission", lambda values: values.mode().iloc[0]),
        )
        .sort_values("count", ascending=False)
        .head(15)
        .reset_index()
    )

    return {
        "reference_year": reference,
        "kpis": {
            "listings": int(len(df)),
            "brands": int(df["Brand"].nunique()),
            "models": int(df.groupby(["Brand", "Model"]).ngroups),
            "median_price": round(float(prices.median()), 2),
            "year_min": int(df["Year"].min()),
            "year_max": int(df["Year"].max()),
            "cars_2024_on": int((df["Year"] >= 2024).sum()),
            "variants": int(df.groupby(["Brand", "Model", "Variant_Key"]).ngroups),
            "median_kms": int(df["Kms_Driven"].median()),
        },
        "histogram": {"bins": histogram, "above": int((prices >= last_bin).sum()), "cap": last_bin},
        "by_year": [{"year": int(year), "median": round(float(row["median"]), 2), "count": int(row["count"])} for year, row in by_year.iterrows()],
        "brands": [{"brand": brand, "median": round(float(row["median"]), 2), "count": int(row["count"])} for brand, row in brands.iterrows()],
        "depreciation": depreciation,
        "by_fuel": _median_rows(df, "Fuel_Type"),
        "by_transmission": _median_rows(df, "Transmission"),
        "by_owner": _median_rows(df, "Owner", labels=OWNER_LABELS, order=[0, 1, 2, 3]),
        "by_platform": _median_rows(df, "Platform"),
        "popular_models": [
            {
                "brand": row["Brand"],
                "model": row["Model"],
                "count": int(row["count"]),
                "median": round(float(row["median"]), 2),
                "typical_year": int(row["year"]),
                "typical_kms": int(row["kms"]),
                "typical_fuel": row["fuel"],
                "typical_transmission": row["transmission"],
            }
            for _, row in popular.iterrows()
        ],
    }


@lru_cache(maxsize=1)
def model_performance() -> dict:
    meta = json.loads(METADATA_PATH.read_text())
    test_points = []
    if TEST_PREDICTIONS_PATH.exists():
        test = pd.read_csv(TEST_PREDICTIONS_PATH)
        test_points = [
            {"name": row.Name, "platform": row.Platform, "year": int(row.Year), "actual": round(float(row.actual), 2), "predicted": round(float(row.predicted), 2)}
            for row in test.itertuples()
        ]
    return {
        "model_name": meta["model_name"],
        "trained_at": meta["trained_at"],
        "cv_folds": meta["cv_folds"],
        "data": meta["data"],
        "test_metrics": meta["test_metrics"],
        "interval": meta["interval"],
        "comparison": [
            {key: row[key] for key in ("model", "tuned", "cv_mae", "cv_mae_std", "cv_r2", "cv_medape", "train_r2", "test_mae", "test_r2")}
            for row in sorted(meta["comparison"], key=lambda row: row["cv_mae"])
        ],
        "feature_importance": meta["feature_importance"],
        "error_by_price_band": meta["error_by_price_band"],
        "test_points": test_points,
        "versions": meta["versions"],
    }


def similar_listings(brand: str, model: str, variant_key: str, year: int, kms: int, limit: int = 6) -> list[dict]:
    """Real listings of the same car: the same variant first, then closest in year and kilometres."""
    try:
        df = dataset()
    except FileNotFoundError:
        return []
    pool = df[df["Brand"] == brand]
    same_model = pool[pool["Model"] == model]
    if len(same_model) >= 3:
        pool = same_model
    if pool.empty:
        return []
    distance = (pool["Year"] - year).abs() + (pool["Kms_Driven"] - kms).abs() / 25_000
    other_variant = (pool["Variant_Key"] != variant_key).astype(int) if variant_key else 0
    closest = pool.assign(_distance=distance + other_variant * 1.5).sort_values(["_distance", TARGET]).head(limit)
    return [
        {
            "name": row.Name,
            "year": int(row.Year),
            "kms": int(row.Kms_Driven),
            "fuel": row.Fuel_Type,
            "transmission": row.Transmission,
            "owner": OWNER_LABELS[int(row.Owner)],
            "platform": row.Platform,
            "city": row.City,
            "same_variant": bool(variant_key) and row.Variant_Key == variant_key,
            "price": round(float(row.Selling_Price), 2),
        }
        for row in closest.itertuples()
    ]
