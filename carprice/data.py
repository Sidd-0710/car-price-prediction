"""Loading the dataset and turning cars into model features.

`build_features` is used both when training and when the API predicts, so the
model always receives exactly the same columns in exactly the same form.
The dataset itself is built from the raw sources by `carprice/sources.py`.
"""

import json

import numpy as np
import pandas as pd

from .config import BUILD_REPORT_PATH, DATA_PATH

OWNER_LABELS = {
    0: "First owner",
    1: "Second owner",
    2: "Third owner",
    3: "Fourth owner or more",
}

FUEL_TYPES = ["Petrol", "Diesel", "CNG", "Electric"]
TRANSMISSIONS = ["Manual", "Automatic"]
PLATFORMS = ["CarDekho", "Cars24", "Spinny"]

NUMERIC_FEATURES = ["Age", "Kms_Driven", "Log_Kms", "Kms_Per_Year", "Owner"]
CATEGORICAL_FEATURES = ["Brand", "Model", "Fuel_Type", "Transmission", "Platform"]
PRICE_LEVEL_FEATURES = ["Brand", "Model", "Trim"]  # target-encoded: "how expensive are cars like this?"
VARIANT_WORDS_FEATURE = "Variant_Key"  # words of the variant: "amt", "plus", "turbo"...
FEATURE_COLUMNS = NUMERIC_FEATURES + ["Brand", "Model", "Trim", "Variant_Key", "Fuel_Type", "Transmission", "Platform"]
TARGET = "Selling_Price"  # in lakhs of rupees (1 lakh = 100,000)


def load_clean(path=DATA_PATH) -> tuple[pd.DataFrame, dict]:
    """The cleaned listings, plus a summary of how they were built."""
    if not path.exists():
        raise FileNotFoundError(f"{path.name} not found. Build it first with:  python build_dataset.py")
    df = pd.read_csv(path, keep_default_na=False)
    build = json.loads(BUILD_REPORT_PATH.read_text()) if BUILD_REPORT_PATH.exists() else {}
    counts = build.get("counts", {})
    report = {
        "raw_rows": counts.get("rows_read", int(len(df))),
        "duplicate_rows_removed": counts.get("dropped_duplicates", 0),
        "other_rows_removed": sum(v for k, v in counts.items() if k.startswith("dropped_") and k != "dropped_duplicates"),
        "clean_rows": int(len(df)),
        "missing_values": int(df.drop(columns=["Variant", "Variant_Key", "City"]).replace("", np.nan).isna().sum().sum()),
        "reference_year": int(df["Listing_Year"].max()),
        "year_min": int(df["Year"].min()),
        "year_max": int(df["Year"].max()),
        "price_min_lakh": float(df[TARGET].min()),
        "price_max_lakh": float(df[TARGET].max()),
        "price_median_lakh": float(df[TARGET].median()),
        "brands": int(df["Brand"].nunique()),
        "models": int(df.groupby(["Brand", "Model"]).ngroups),
        "variants": int(df.groupby(["Brand", "Model", "Variant_Key"]).ngroups),
        "platforms": {k: int(v) for k, v in df["Platform"].value_counts().items()},
        "sources": build.get("sources", {}),
    }
    return df, report


def build_features(df: pd.DataFrame, reference_year: int | None = None) -> pd.DataFrame:
    """Columns the model is trained on.

    `df` needs Brand, Model, Variant_Key, Year, Kms_Driven, Fuel_Type, Transmission,
    Owner, Platform, and either a Listing_Year column (training data: the year the car
    was listed) or `reference_year` (predictions: "today" in the model's terms).
    """
    listing_year = df["Listing_Year"] if "Listing_Year" in df else reference_year
    age = (listing_year - df["Year"]).clip(lower=0)
    kms = df["Kms_Driven"].astype(float)
    variant = df["Variant_Key"].fillna("").astype(str)
    return pd.DataFrame(
        {
            "Age": age.astype(float),
            "Kms_Driven": kms,
            "Log_Kms": np.log1p(kms),
            "Kms_Per_Year": kms / age.clip(lower=1),
            "Owner": df["Owner"].astype(float),
            "Brand": df["Brand"],
            "Model": df["Model"],
            "Trim": df["Brand"] + "|" + df["Model"] + "|" + variant,
            "Variant_Key": variant,
            "Fuel_Type": df["Fuel_Type"],
            "Transmission": df["Transmission"],
            "Platform": df["Platform"],
        },
        index=df.index,
    )[FEATURE_COLUMNS]


def _mode(values: pd.Series) -> str:
    return values.value_counts().index[0]


def build_catalog(df: pd.DataFrame) -> dict:
    """Every brand, model and variant the model knows, with how many listings it
    learned from and the variant's usual fuel and gearbox (to pre-fill the form).

    {brand: {model: {"listings": n, "fuels": [...], "transmissions": [...],
                     "variants": [{"name", "key", "listings", "median_price", "years",
                                   "fuel", "transmission"}, ...]}}}
    """
    catalog = {}
    for brand in df["Brand"].value_counts().index:
        brand_rows = df[df["Brand"] == brand]
        catalog[brand] = {}
        for model in brand_rows["Model"].value_counts().index:
            rows = brand_rows[brand_rows["Model"] == model]
            variants = []
            for key, group in rows[rows["Variant_Key"] != ""].groupby("Variant_Key"):
                variants.append(
                    {
                        "name": _mode(group["Variant"]),
                        "key": key,
                        "listings": int(len(group)),
                        "median_price": round(float(group[TARGET].median()), 2),
                        # the years this variant was on sale (10th-90th percentile of listings)
                        "years": [int(group["Year"].quantile(0.1)), int(group["Year"].quantile(0.9))],
                        "fuel": _mode(group["Fuel_Type"]),
                        "transmission": _mode(group["Transmission"]),
                    }
                )
            variants.sort(key=lambda item: (-item["listings"], item["name"]))
            catalog[brand][model] = {
                "listings": int(len(rows)),
                "fuels": list(rows["Fuel_Type"].value_counts().index),
                "transmissions": list(rows["Transmission"].value_counts().index),
                "variants": variants,
            }
    return catalog
