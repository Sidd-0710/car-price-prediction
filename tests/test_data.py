import pandas as pd
import pytest

from carprice.data import FEATURE_COLUMNS, build_catalog, build_features, load_clean
from carprice.sources import _lakh, _owner, model_key, split_brand, variant_key


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Maruti Suzuki Swift Dzire", ("Maruti Suzuki", "Swift Dzire")),
        ("Maruti Swift", ("Maruti Suzuki", "Swift")),
        ("MARUTI Wagon R 1.0", ("Maruti Suzuki", "Wagon R 1.0")),
        ("Land Rover Range Rover Evoque", ("Land Rover", "Range Rover Evoque")),
        ("Landrover Discovery Sport", ("Land Rover", "Discovery Sport")),
        ("Mercedes-Benz E-Class", ("Mercedes-Benz", "E-Class")),
        ("KIA SELTOS", ("Kia", "SELTOS")),
    ],
)
def test_split_brand(name, expected):
    assert split_brand(name) == expected


def test_unknown_brand():
    assert split_brand("69+ photos")[0] is None


@pytest.mark.parametrize(
    "a, b",
    [
        ("Wagon R 1.0", "Wagon R"),
        ("New Wagon R", "Wagon R"),
        ("New i20", "i20"),
        ("Elite i20 2018", "Elite i20"),
        ("Fluidic Verna 4S", "Verna"),
    ],
)
def test_model_names_from_different_sources_match(a, b):
    assert model_key(a) == model_key(b)


def test_variant_spellings_match():
    same = ["ZXi Plus AMT", "zxi-plus-amt", "ZXI+ AMT", "AMT ZXI Plus", "ZXI Plus AMT Petrol Dual Tone"]
    keys = {variant_key(text, "Swift") for text in same}
    assert keys == {"amt plus zxi"}


def test_variant_ignores_model_words_and_years():
    assert variant_key("Swift VXI 2019 BSIV", "Swift") == "vxi"
    assert variant_key("Opt", "Swift") == "o"


@pytest.mark.parametrize(
    "value, owners",
    [("1st owner", 0), ("First Owner", 0), (1, 0), ("2nd owner", 1), ("Third Owner", 2), ("Fifth Owner", 3), ("7th owner", 3)],
)
def test_owner_is_previous_owners_capped(value, owners):
    assert _owner(value) == owners


@pytest.mark.parametrize("text, lakh", [("₹5.40 Lakh", 5.4), ("₹1.2 Crore", 120), ("₹47.50 Lakh Make Your Offer", 47.5)])
def test_price_parsing(text, lakh):
    assert _lakh(text) == pytest.approx(lakh)


def _cars():
    return pd.DataFrame(
        {
            "Brand": ["Maruti Suzuki", "Maruti Suzuki", "Hyundai"],
            "Model": ["Swift", "Swift", "Creta"],
            "Variant": ["VXI", "ZXI AMT", "SX"],
            "Variant_Key": ["vxi", "amt zxi", "sx"],
            "Year": [2019, 2027, 2022],
            "Kms_Driven": [40000, 1000, 20000],
            "Fuel_Type": ["Petrol", "Petrol", "Diesel"],
            "Transmission": ["Manual", "Automatic", "Manual"],
            "Owner": [0, 0, 1],
            "Platform": ["CarDekho", "Spinny", "Cars24"],
            "Selling_Price": [5.0, 7.5, 14.0],
            "Listing_Year": [2025, 2026, 2025],
        }
    )


def test_features_have_fixed_columns_and_never_negative_age():
    features = build_features(_cars())
    assert list(features.columns) == FEATURE_COLUMNS
    assert not features.isna().any().any()
    assert features["Age"].tolist() == [6, 0, 3]  # a car newer than its listing year is age 0
    assert features["Trim"].iloc[0] == "Maruti Suzuki|Swift|vxi"


def test_features_use_reference_year_when_predicting():
    cars = _cars().drop(columns=["Listing_Year"])
    assert build_features(cars, reference_year=2026)["Age"].tolist() == [7, 0, 4]


def test_catalog_lists_variants_with_their_usual_fuel_and_gearbox():
    catalog = build_catalog(_cars())
    swift = catalog["Maruti Suzuki"]["Swift"]
    assert swift["listings"] == 2
    zxi = next(variant for variant in swift["variants"] if variant["key"] == "amt zxi")
    assert (zxi["name"], zxi["transmission"]) == ("ZXI AMT", "Automatic")


def test_real_dataset_is_clean():
    df, report = load_clean()
    assert len(df) > 30_000
    assert report["missing_values"] == 0
    assert report["duplicate_rows_removed"] > 0
    assert not df.duplicated(["Brand", "Model", "Year", "Kms_Driven", "Fuel_Type", "Transmission", "Selling_Price"]).any()
    assert df["Selling_Price"].between(0.5, 500).all()
    assert df["Owner"].isin([0, 1, 2, 3]).all()
    assert set(df["Fuel_Type"]) == {"Petrol", "Diesel", "CNG", "Electric"}  # no LPG
    assert set(df["Platform"]) == {"CarDekho", "Cars24", "Spinny"}
    assert df["Year"].max() >= 2025  # recent cars are included
    assert (df["Variant_Key"] != "").mean() > 0.95  # nearly every listing has its variant
