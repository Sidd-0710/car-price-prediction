"""Build one clean used-car dataset from four public listing sources (2025-2026).

    python build_dataset.py

Reads the raw downloads in data/raw/ (fetched from Kaggle's public API if missing),
maps every source onto the same columns, removes duplicates and bad rows, and
writes data/used_cars_india.csv plus data/build_report.json.
"""

import io
import json
import re
import urllib.request
import zipfile
from collections import Counter

import numpy as np
import pandas as pd

from .config import DATA_DIR

RAW_DIR = DATA_DIR / "raw"
OUTPUT_PATH = DATA_DIR / "used_cars_india.csv"
REPORT_PATH = DATA_DIR / "build_report.json"

# name -> (Kaggle dataset, platform, year the listings were collected)
SOURCES = {
    "cardekho_2026": ("sumangoudakaggle/second-hand-car-dataset-cardekho", "CarDekho", 2026),
    "cardekho_2025": ("pankajmaulekhi/indian-second-hand-cars-dataset", "CarDekho", 2025),
    "spinny_2025": ("abhiramasdf/indian-used-cars-dataset", "Spinny", 2025),
    "cars24_2025": ("sukhmansaran/used-cars-prices-cars-24", "Cars24", 2025),
}

COLUMNS = [
    "Source", "Platform", "Listing_Year", "Brand", "Model", "Variant", "Variant_Key", "Name", "Year",
    "Kms_Driven", "Fuel_Type", "Transmission", "Owner", "City", "Selling_Price",
]

# The first word(s) of a car name -> the brand's official spelling. Longest match wins.
BRAND_ALIASES = {
    "maruti suzuki": "Maruti Suzuki", "maruti": "Maruti Suzuki",
    "hyundai": "Hyundai", "honda": "Honda", "tata": "Tata", "mahindra": "Mahindra",
    "toyota": "Toyota", "kia": "Kia", "renault": "Renault", "ford": "Ford",
    "volkswagen": "Volkswagen", "skoda": "Skoda", "nissan": "Nissan",
    "mg": "MG", "mg motor": "MG", "mercedes-benz": "Mercedes-Benz", "mercedes benz": "Mercedes-Benz",
    "mercedes": "Mercedes-Benz", "bmw": "BMW", "audi": "Audi", "jeep": "Jeep", "datsun": "Datsun",
    "chevrolet": "Chevrolet", "fiat": "Fiat", "jaguar": "Jaguar", "land rover": "Land Rover",
    "landrover": "Land Rover", "ashok leyland": "Ashok Leyland", "volvo": "Volvo", "mini": "Mini", "porsche": "Porsche", "lexus": "Lexus", "citroen": "Citroen",
    "isuzu": "Isuzu", "mitsubishi": "Mitsubishi", "force motors": "Force Motors", "force": "Force Motors",
    "byd": "BYD", "maserati": "Maserati", "lamborghini": "Lamborghini", "ferrari": "Ferrari",
    "bentley": "Bentley", "rolls-royce": "Rolls-Royce", "rolls royce": "Rolls-Royce",
    "aston martin": "Aston Martin", "ssangyong": "Ssangyong", "mahindra ssangyong": "Mahindra",
    "mahindra renault": "Mahindra", "hindustan motors": "Hindustan Motors", "ambassador": "Hindustan Motors",
    "opel": "Opel", "premier": "Premier", "daewoo": "Daewoo", "tesla": "Tesla", "vinfast": "VinFast",
    "lotus": "Lotus", "mclaren": "McLaren", "ds": "DS", "pmv": "PMV",
}
_ALIASES_BY_LENGTH = sorted(BRAND_ALIASES, key=len, reverse=True)

# Different sources name some models differently (engine size, "New", old badges).
MODEL_ALIASES = {
    "wagon r 10": "wagon r",
    "wagon r 12": "wagon r",
    "new wagon r": "wagon r",
    "new i20": "i20",
    "new i20 n line": "i20 n line",
    "new santro": "santro",
    "new elantra": "elantra",
    "grand i10 prime": "grand i10",
    "alto k10": "alto k10",
    "redi go": "redigo",
    "swift dzire tour": "swift dzire",
    "dzire tour": "dzire",
    "xuv 300": "xuv300",
    "xuv 500": "xuv500",
    "xuv 700": "xuv700",
    "xuv 3xo": "xuv 3xo",
    "new santro 11": "santro",
    "santro 11": "santro",
    "elite i20 2018": "elite i20",
    "fluidic verna 4s": "verna",
    "fluidic verna": "verna",
    "new ertiga": "ertiga",
    "omni e": "omni",
    "estilo": "zen estilo",
    "xcent prime": "xcent",
}


def model_key(model) -> str:
    """Key used to decide that two model names are the same car."""
    key = _key(model)
    key = re.sub(r"^new ", "", key)
    key = re.sub(r" (19|20)\d\d$", "", key)
    return MODEL_ALIASES.get(key, key)

# Variant words that carry no information beyond other columns (fuel, year, colour).
VARIANT_NOISE = {
    "petrol", "diesel", "cng", "bsiv", "bsvi", "bsiii", "bs4", "bs6", "bs", "dual", "tone",
    "dt", "mt", "manual", "edition", "new", "bsii",
}
VARIANT_SYNONYMS = {"opt": "o", "option": "o", "optional": "o", "automatic": "at", "auto": "at", "plus": "plus"}

LPG_AND_RARE_FUELS = {"LPG"}  # removed on request: too rare, and not offered in the app
FUEL_MAP = {
    "petrol": "Petrol", "diesel": "Diesel", "cng": "CNG", "petrol+cng": "CNG", "petrol + cng": "CNG",
    "electric": "Electric", "hybrid": "Hybrid", "petrol+hybrid": "Hybrid", "lpg": "LPG",
}
MIN_FUEL_ROWS = 80  # fuels with fewer listings than this are dropped

MIN_PRICE_LAKH, MAX_PRICE_LAKH = 0.5, 500
MAX_KMS = 500_000
MIN_YEAR = 2000


# ------------------------------------------------------------------ download
def ensure_downloaded() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for name, (dataset, _, _) in SOURCES.items():
        target = RAW_DIR / f"{name}.zip"
        if target.exists():
            continue
        print(f"Downloading {dataset} ...", flush=True)
        url = f"https://www.kaggle.com/api/v1/datasets/download/{dataset}"
        with urllib.request.urlopen(url, timeout=120) as response:
            target.write_bytes(response.read())


def _read_member(archive: zipfile.ZipFile, suffix: str) -> pd.DataFrame:
    member = next(name for name in archive.namelist() if name.endswith(suffix))
    return pd.read_csv(io.BytesIO(archive.read(member)))


# ------------------------------------------------------------- normalising
def _key(text) -> str:
    """'Wagon R 1.0' -> 'wagon r 10' (lowercase, dots removed, single spaces)."""
    text = str(text).lower().replace(".", "")
    return " ".join(re.sub(r"[^a-z0-9+]+", " ", text).split())


def split_brand(text: str) -> tuple[str | None, str]:
    """'Maruti Suzuki Swift Dzire' -> ('Maruti Suzuki', 'Swift Dzire')."""
    clean = " ".join(str(text).split())
    lower = clean.lower()
    for alias in _ALIASES_BY_LENGTH:
        if lower == alias or lower.startswith(alias + " "):
            return BRAND_ALIASES[alias], clean[len(alias):].strip()
    return None, clean


def variant_words(variant, model: str = "") -> list[str]:
    """Meaningful words of a variant: 'ZXi Plus AMT', 'zxi-plus-amt' and 'ZXI+ AMT' give the same words."""
    words = _key(variant).replace("+", " plus ").split()
    model_words = set(_key(model).split())
    out = []
    for word in words:
        word = VARIANT_SYNONYMS.get(word, word)
        if word in VARIANT_NOISE or word in model_words or re.fullmatch(r"(19|20)\d\d", word):
            continue
        if word not in out:
            out.append(word)
    return out[:6]


def variant_key(variant, model: str = "") -> str:
    """Order-free key, so 'amt vxi' and 'vxi amt' count as one variant."""
    return " ".join(sorted(variant_words(variant, model)))


def _owner(value) -> float:
    """Number of PREVIOUS owners, capped at 3: '1st owner'/'First Owner'/1 -> 0."""
    text = str(value).lower()
    words = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
    for word, number in words.items():
        if word in text:
            return min(number - 1, 3)
    digits = re.search(r"\d+", text)
    return min(int(digits.group()) - 1, 3) if digits else np.nan


def _lakh(value) -> float:
    """'₹5.40 Lakh' -> 5.4, '₹1.2 Crore' -> 120."""
    match = re.search(r"([\d.,]+)\s*(Lakh|Crore|Cr)", str(value))
    if not match:
        return np.nan
    number = float(match.group(1).replace(",", ""))
    return number * 100 if match.group(2).startswith("Cr") else number


def _number(value) -> float:
    digits = re.sub(r"[^\d]", "", str(value))
    return float(digits) if digits else np.nan


def _year(value) -> float:
    match = re.search(r"(19|20)\d\d", str(value))
    return float(match.group()) if match else np.nan


# ------------------------------------------------------------------ loaders
def load_cardekho_2026() -> pd.DataFrame:
    rows = []
    with zipfile.ZipFile(RAW_DIR / "cardekho_2026.zip") as archive:
        for member in archive.namelist():
            if not member.endswith(".json"):
                continue
            city = member.split("/")[0]
            for line in archive.read(member).decode("utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    record["_city"] = city
                    rows.append(record)
    raw = pd.DataFrame(rows)
    raw["_listing"] = raw["url"].str.split("?").str[0]
    raw = raw.drop_duplicates("_listing")  # the same listing appears under several cities

    brand_model = raw["car_name"].map(split_brand)
    slug = raw["url"].str.extract(r"used-car-details/used-(.+?)-cars-")[0].fillna("")
    variants = []
    for (brand, model), text in zip(brand_model, slug):
        # slug is "<brand>-<model>-<variant>"; remove the brand and model words from the front
        words = text.lower().split("-")
        skip = len(_key(model).split()) + (1 if brand else 0)
        if brand == "Maruti Suzuki" and words[:1] == ["maruti"]:
            skip = len(_key(model).split()) + 1
        variants.append(" ".join(words[skip:]))
    year = raw["Year of Manufacture"].map(_year).fillna(raw["Registration Year"].map(_year))
    return pd.DataFrame(
        {
            "Brand": brand_model.str[0],
            "Model": brand_model.str[1],
            "Variant": variants,
            "Year": year,
            "Kms_Driven": raw["Kms Driven"].map(_number),
            "Fuel_Type": raw["Fuel Type"],
            "Transmission": raw["Transmission"],
            "Owner": raw["Ownership"].map(_owner),
            "City": raw["_city"],
            "Selling_Price": raw["Price"].map(_lakh),
        }
    )


def load_cardekho_2025(model_names: dict[str, set[str]]) -> pd.DataFrame:
    with zipfile.ZipFile(RAW_DIR / "cardekho_2025.zip") as archive:
        raw = _read_member(archive, "car_details.csv")
    raw.columns = [column.strip() for column in raw.columns]
    raw = raw.drop_duplicates()
    brands, models, variants = [], [], []
    for name in raw["vehical_name"]:
        text = re.sub(r"^\s*(19|20)\d\d\s+", "", str(name))  # "2020 Maruti Wagon R VXI" -> "Maruti Wagon R VXI"
        brand, rest = split_brand(text)
        words = rest.split()
        known = model_names.get(brand, set())
        cut = 1
        for size in range(min(4, len(words)), 0, -1):  # longest known model name first
            if model_key(" ".join(words[:size])) in known:
                cut = size
                break
        brands.append(brand)
        models.append(" ".join(words[:cut]))
        variants.append(" ".join(words[cut:]))
    return pd.DataFrame(
        {
            "Brand": brands,
            "Model": models,
            "Variant": variants,
            "Year": raw["Year of Manufacture"].map(_year).fillna(raw["Registration Year"].map(_year)),
            "Kms_Driven": raw["Kms Driven"].map(_number),
            "Fuel_Type": raw["Fuel Type"],
            "Transmission": raw["Transmission"],
            "Owner": raw["Ownership"].map(_owner),
            "City": raw["RTO"],
            "Selling_Price": raw["vehical_price"].map(_lakh),
        }
    )


def load_spinny_2025() -> pd.DataFrame:
    with zipfile.ZipFile(RAW_DIR / "spinny_2025.zip") as archive:
        raw = _read_member(archive, "all_car_details.csv").drop_duplicates()
    brand = raw["make"].map(lambda text: split_brand(text)[0] or text)
    return pd.DataFrame(
        {
            "Brand": brand,
            "Model": raw["model"],
            "Variant": raw["variant"],
            "Year": raw["make_year"].astype(float),
            "Kms_Driven": raw["mileage"].astype(float),
            "Fuel_Type": raw["fuel_type"],
            "Transmission": raw["transmission"],
            "Owner": raw["no_of_owners"].map(_owner),
            "City": raw["city"],
            "Selling_Price": raw["price"] / 100_000,
        }
    )


def load_cars24_2025() -> pd.DataFrame:
    with zipfile.ZipFile(RAW_DIR / "cars24_2025.zip") as archive:
        raw = _read_member(archive, "Cars24.csv").drop_duplicates()
    brand_model = raw["Car Model"].map(split_brand)
    return pd.DataFrame(
        {
            "Brand": brand_model.str[0],
            "Model": brand_model.str[1],
            "Variant": raw["Car Variant"],
            "Year": raw["Year"].astype(float),
            "Kms_Driven": raw["KM Driven"].astype(float),
            "Fuel_Type": raw["Fuel Type"],
            "Transmission": raw["Transmission Type"].replace({"Auto": "Automatic"}),
            "Owner": raw["Ownership"].map(_owner),
            "City": raw["Location"].astype(str).str.split().str[-1],
            "Selling_Price": raw["Price(in Lakhs)"],
        }
    )


# ------------------------------------------------------------------- build
def _canonical_models(frame: pd.DataFrame) -> pd.Series:
    """One spelling per (brand, model): CarDekho's if it has one, otherwise the most common."""
    keys = frame["Model"].map(model_key)
    best = {}
    ranked = frame.assign(_key=keys, _pref=(frame["Source"] != "cardekho_2026").astype(int))
    for (brand, key), group in ranked.groupby(["Brand", "_key"]):
        preferred = group[group["_pref"] == group["_pref"].min()]["Model"]
        name = Counter(preferred).most_common(1)[0][0]
        best[(brand, key)] = re.sub(r"\s+(19|20)\d\d$", "", name)  # "Elite i20 2018" -> "Elite i20"
    return pd.Series([best[(brand, key)] for brand, key in zip(frame["Brand"], keys)], index=frame.index)


def _readable_variant(text: str) -> str:
    """'ZXI Plus AMT Petrol Dual Tone BSVI' -> 'ZXI PLUS AMT' (keeps '1.2', drops fuel and emission words)."""
    words = [word for word in str(text).upper().split() if _key(word) not in VARIANT_NOISE]
    return " ".join(words)


def _display_variants(frame: pd.DataFrame) -> pd.Series:
    """A readable name per variant: the most common spelling from the sources that
    write variants as text (e.g. '2.5 G2 8 STR'); URL-only variants fall back to their words."""
    text_rows = frame["Source"] != "cardekho_2026"
    readable = frame["Variant"].map(_readable_variant).where(text_rows)
    fallback = [" ".join(variant_words(variant, model)).upper() for variant, model in zip(frame["Variant"], frame["Model"])]
    keys = list(zip(frame["Brand"], frame["Model"], frame["Variant_Key"]))
    best = {}
    for key, name in zip(keys, readable):
        if isinstance(name, str) and name:
            best.setdefault(key, Counter())[name] += 1
    return pd.Series(
        [best[key].most_common(1)[0][0] if key in best else fallback[i] for i, key in enumerate(keys)],
        index=frame.index,
    )


def build() -> tuple[pd.DataFrame, dict]:
    ensure_downloaded()
    report = {"sources": {}}
    frames = {}
    for name, loader in (("cardekho_2026", load_cardekho_2026), ("spinny_2025", load_spinny_2025), ("cars24_2025", load_cars24_2025)):
        frames[name] = loader()

    known_models: dict[str, set[str]] = {}
    for frame in frames.values():
        for brand, model in zip(frame["Brand"], frame["Model"]):
            known_models.setdefault(brand, set()).add(model_key(model))
    frames["cardekho_2025"] = load_cardekho_2025(known_models)

    parts = []
    for name, frame in frames.items():
        _, platform, listing_year = SOURCES[name]
        report["sources"][name] = {"dataset": SOURCES[name][0], "platform": platform, "collected": listing_year, "rows_read": int(len(frame))}
        parts.append(frame.assign(Source=name, Platform=platform, Listing_Year=listing_year))
    df = pd.concat(parts, ignore_index=True)
    counts = {"rows_read": int(len(df))}

    # --- tidy categories
    df["Fuel_Type"] = df["Fuel_Type"].astype(str).str.strip().str.lower().map(FUEL_MAP)
    df["Transmission"] = df["Transmission"].astype(str).str.strip().str.title().replace({"Auto": "Automatic", "Amt": "Automatic"})
    df["City"] = df["City"].astype(str).str.replace("-", " ").str.title()
    df["Variant"] = df["Variant"].fillna("").astype(str)

    # --- drop unusable rows, counting why
    def drop(mask, reason):
        nonlocal df
        counts[reason] = int(mask.sum())
        df = df[~mask]

    drop(df["Brand"].isna() | (df["Model"].astype(str).str.strip() == ""), "dropped_unknown_brand_or_model")
    drop(df[["Year", "Kms_Driven", "Selling_Price", "Owner"]].isna().any(axis=1) | df["Fuel_Type"].isna(), "dropped_missing_values")
    drop(~df["Transmission"].isin(["Manual", "Automatic"]), "dropped_unknown_transmission")
    drop(df["Fuel_Type"].isin(LPG_AND_RARE_FUELS), "dropped_lpg")
    drop((df["Selling_Price"] < MIN_PRICE_LAKH) | (df["Selling_Price"] > MAX_PRICE_LAKH), "dropped_price_outliers")
    drop((df["Kms_Driven"] > MAX_KMS) | (df["Kms_Driven"] < 0), "dropped_kms_outliers")
    drop((df["Year"] < MIN_YEAR) | (df["Year"] > df["Listing_Year"]), "dropped_impossible_years")
    rare_fuels = [fuel for fuel, n in df["Fuel_Type"].value_counts().items() if n < MIN_FUEL_ROWS]
    drop(df["Fuel_Type"].isin(rare_fuels), "dropped_rare_fuels")
    report["rare_fuels_dropped"] = rare_fuels

    # --- one spelling for every model, then clean variants
    df["Model"] = _canonical_models(df)
    df["Variant_Key"] = [variant_key(variant, model) for variant, model in zip(df["Variant"], df["Model"])]
    df["Variant"] = _display_variants(df)
    df["Name"] = (df["Brand"] + " " + df["Model"] + " " + df["Variant"]).str.strip()
    df["Year"] = df["Year"].astype(int)
    df["Kms_Driven"] = df["Kms_Driven"].astype(int)
    df["Owner"] = df["Owner"].astype(int)
    df["Selling_Price"] = df["Selling_Price"].round(2)

    # --- duplicates: the same car listed twice (within or across sources)
    before = len(df)
    df = df.drop_duplicates(["Brand", "Model", "Year", "Kms_Driven", "Fuel_Type", "Transmission", "Selling_Price"])
    counts["dropped_duplicates"] = int(before - len(df))

    df = df[COLUMNS].sort_values(["Brand", "Model", "Year"]).reset_index(drop=True)
    counts["rows_kept"] = int(len(df))
    report["counts"] = counts
    report["summary"] = {
        "brands": int(df["Brand"].nunique()),
        "models": int(df.groupby(["Brand", "Model"]).ngroups),
        "variants": int(df.groupby(["Brand", "Model", "Variant_Key"]).ngroups),
        "rows_with_variant": int((df["Variant_Key"] != "").sum()),
        "year_min": int(df["Year"].min()),
        "year_max": int(df["Year"].max()),
        "rows_by_year_2020_on": {int(k): int(v) for k, v in df.loc[df["Year"] >= 2020, "Year"].value_counts().sort_index().items()},
        "rows_by_platform": {k: int(v) for k, v in df["Platform"].value_counts().items()},
        "rows_by_fuel": {k: int(v) for k, v in df["Fuel_Type"].value_counts().items()},
        "price_median_lakh": float(df["Selling_Price"].median()),
    }
    return df, report


def main():
    df, report = build()
    df.to_csv(OUTPUT_PATH, index=False)
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"\nWrote {len(df):,} rows to {OUTPUT_PATH.relative_to(DATA_DIR.parent)}")
