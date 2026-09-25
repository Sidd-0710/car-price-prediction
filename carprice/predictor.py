"""Load the trained model and turn a request into a price estimate.

Used by the FastAPI server and (as a fallback) by the Streamlit app.
"""

import json
import warnings
from dataclasses import dataclass
from difflib import get_close_matches
from functools import lru_cache

import joblib
import pandas as pd
import sklearn

from .config import METADATA_PATH, MODEL_PATH
from .data import build_features
from .modeling import apply_interval
from .sources import BRAND_ALIASES, model_key, variant_key, variant_words

HIGH_KMS_WARNING = 300_000
LUXURY_PRICE_LAKH = 20  # above this, test-set accuracy was clearly lower
VARIANT_MATCH_THRESHOLD = 0.6  # share of words two variant names must have in common (Jaccard)


class ModelNotTrainedError(FileNotFoundError):
    """The trained model file is missing."""


class UnknownCarError(ValueError):
    """The car name could not be matched to anything the model has seen."""

    def __init__(self, message: str, suggestions: list[str] | None = None):
        super().__init__(message)
        self.suggestions = suggestions or []


@dataclass(frozen=True)
class ResolvedCar:
    brand: str
    model: str  # "Other" when only a brand was given
    variant_key: str  # "" when no variant was given
    variant_name: str | None  # the catalogue's name for the variant, if recognised
    model_known: bool
    variant_given: bool

    @property
    def matched_name(self) -> str:
        if not self.model_known:
            return self.brand
        return f"{self.brand} {self.model}" + (f" {self.variant_name}" if self.variant_name else "")


def _key(text: str) -> str:
    return " ".join(str(text).lower().split())


class Predictor:
    def __init__(self, model_path=MODEL_PATH, metadata_path=METADATA_PATH):
        if not model_path.exists() or not metadata_path.exists():
            raise ModelNotTrainedError("No trained model found. Train one first with:  python train.py")
        self.metadata = json.loads(metadata_path.read_text())
        trained_with = self.metadata["versions"]["scikit_learn"]
        self.version_note = None
        if trained_with != sklearn.__version__:
            self.version_note = (
                f"Model was trained with scikit-learn {trained_with} but "
                f"{sklearn.__version__} is installed. If predictions look wrong, re-run: python train.py"
            )
            warnings.warn(self.version_note)
        self.model = joblib.load(model_path)

        self.reference_year = self.metadata["reference_year"]
        self.year_min = self.metadata["data"]["year_min"]
        interval = self.metadata["interval"]
        self._low_q, self._high_q = interval["low_q"], interval["high_q"]

        # {brand: {model: {"listings", "fuels", "transmissions", "variants": [...]}}}
        self._catalog = self.metadata["catalog"]
        # "maruti", "maruti suzuki", "landrover"... -> the brand's name in the catalogue
        self._brands = {alias: brand for alias, brand in BRAND_ALIASES.items() if brand in self._catalog}
        self._brands.update({_key(brand): brand for brand in self._catalog})
        self._models = {brand: {model_key(model): model for model in models} for brand, models in self._catalog.items()}
        self._brand_of_model = {}
        for brand, models in self._catalog.items():
            for model, info in models.items():
                self._brand_of_model.setdefault(model_key(model), []).append((info["listings"], brand, model))
        self._variants = {
            (brand, model): {variant["key"]: variant for variant in info["variants"]}
            for brand, models in self._catalog.items()
            for model, info in models.items()
        }

    # ------------------------------------------------------------ catalogue
    def catalog(self) -> dict[str, list[str]]:
        """{brand: [models, most listed first]}"""
        return {brand: list(models) for brand, models in self._catalog.items()}

    def catalog_details(self) -> list[dict]:
        return [
            {
                "brand": brand,
                "model": model,
                "listings": info["listings"],
                "fuels": info["fuels"],
                "transmissions": info["transmissions"],
                "variants": len(info["variants"]),
            }
            for brand, models in self._catalog.items()
            for model, info in models.items()
        ]

    def model_details(self, brand: str, model: str) -> dict:
        return self._catalog[brand][model]

    def variants(self, car_name: str) -> dict:
        car = self.resolve(car_name)
        if not car.model_known:
            return {"car": car.brand, "variants": []}
        return {"car": f"{car.brand} {car.model}", **self.model_details(car.brand, car.model)}

    def car_names(self) -> list[str]:
        return sorted((f"{brand} {model}" for brand, models in self._catalog.items() for model in models), key=str.lower)

    def model_info(self) -> dict:
        m = self.metadata
        return {
            "model_name": m["model_name"],
            "trained_at": m["trained_at"],
            "training_rows": m["data"]["train_rows"] + m["data"]["test_rows"],
            "reference_year": self.reference_year,
            "test_metrics": m["test_metrics"],
            "interval": m["interval"],
            "versions": m["versions"],
            "version_warning": self.version_note,
        }

    # ------------------------------------------------------------- matching
    @staticmethod
    def _find_model(tokens: list[str], models: dict[str, str]):
        """The longest run of words (up to 4) that is a known model name; returns (model, words used)."""
        for width in (4, 3, 2, 1):
            for start in range(len(tokens) - width + 1):
                key = model_key(" ".join(tokens[start : start + width]))
                if key in models:
                    return models[key], start + width
        return None, 0

    def _match_variant(self, brand: str, model: str, text: str) -> tuple[str, str | None]:
        """(variant key, catalogue name or None). Exact key first, then the closest by shared words."""
        key = variant_key(text, model)
        known = self._variants.get((brand, model), {})
        if not key:
            return "", None
        if key in known:
            return key, known[key]["name"]
        words = set(key.split())
        best, best_score = None, 0.0
        for candidate_key, info in known.items():
            other = set(candidate_key.split())
            score = len(words & other) / len(words | other)
            if score > best_score or (score == best_score and best and info["listings"] > known[best]["listings"]):
                best, best_score = candidate_key, score
        if best and best_score >= VARIANT_MATCH_THRESHOLD:
            return best, known[best]["name"]
        return key, None  # unseen variant: its words still inform the model

    def resolve(self, car_name: str, variant: str | None = None) -> ResolvedCar:
        tokens = _key(car_name).split()
        if not tokens:
            raise UnknownCarError("Car_Name is empty.")

        brand, rest = None, tokens
        for width in (3, 2, 1):
            if len(tokens) >= width and " ".join(tokens[:width]) in self._brands:
                brand, rest = self._brands[" ".join(tokens[:width])], tokens[width:]
                break

        if brand is not None:
            if not rest:  # just a brand, e.g. "Maruti": allowed, estimate is rougher
                return ResolvedCar(brand, "Other", "", None, model_known=False, variant_given=False)
            model, used = self._find_model(rest, self._models[brand])
            if model is None:
                close = get_close_matches(model_key(" ".join(rest[:2])), list(self._models[brand]), n=3, cutoff=0.6)
                options = [f"{brand} {self._models[brand][key]}" for key in close] or [
                    f"{brand} {name}" for name in list(self._catalog[brand])[:5]
                ]
                raise UnknownCarError(f"Unknown model '{' '.join(rest)}' for {brand}. Did you mean: {options}?", options)
            leftover = " ".join(rest[used:])
        else:
            model_name, used = self._find_model(tokens, {key: key for key in self._brand_of_model})
            if model_name is None:
                close = get_close_matches(tokens[0], list(self._brand_of_model), n=3, cutoff=0.7)
                options = [f"{max(self._brand_of_model[key])[1]} {max(self._brand_of_model[key])[2]}" for key in close]
                hint = f" Did you mean: {options}?" if options else ""
                raise UnknownCarError(f"Unknown car '{car_name}'.{hint}", options)
            _, brand, model = max(self._brand_of_model[model_name])
            leftover = " ".join(tokens[used:])

        variant_text = variant if variant else leftover  # "Maruti Swift VXI AMT" works too
        key, name = self._match_variant(brand, model, variant_text)
        return ResolvedCar(brand, model, key, name, model_known=True, variant_given=bool(variant_text.strip()))

    # ---------------------------------------------------------- prediction
    def _warnings(self, car: ResolvedCar, payload: dict, price: float) -> list[str]:
        notes = []
        if payload["Fuel_Type"] == "Electric":
            notes.append("Electric cars are still rare second-hand (a few hundred listings), so this estimate is less certain than usual.")
        if price > LUXURY_PRICE_LAKH:
            notes.append(f"Cars above ₹{LUXURY_PRICE_LAKH} lakh vary more: on test cars, the likely range held only about 2 times in 3.")
        year, kms = payload["Year"], payload["Kms_Driven"]
        if year > self.reference_year:
            notes.append(f"The newest listings the model learned from are from {self.reference_year}; a {year} car is priced like a new {self.reference_year} one.")
        if year < self.year_min:
            notes.append(f"Cars older than {self.year_min} are outside the training data.")
        if kms > HIGH_KMS_WARNING:
            notes.append(f"{kms:,} km is far above typical listings, so the estimate is less reliable.")
        if not car.model_known:
            notes.append("No model was given, so the estimate only uses the brand and the other details.")
        elif car.variant_given and car.variant_name is None:
            words = " ".join(variant_words(payload.get("Variant") or "", car.model)).upper() or "that variant"
            notes.append(f"Variant '{words}' was not in the listings, so the estimate uses the model's typical variant, adjusted for its words.")
        if car.model_known:
            info = self._catalog[car.brand][car.model]
            if payload["Fuel_Type"] not in info["fuels"]:
                notes.append(f"No {payload['Fuel_Type'].lower()} {car.model} was in the listings, so this combination is a guess.")
        return notes

    def predict_many(self, payloads: list[dict]) -> list[dict]:
        """Each payload: Car_Name, Variant (optional), Year, Kms_Driven, Fuel_Type,
        Transmission, Owner, Platform - plain strings and numbers."""
        cars = [self.resolve(payload["Car_Name"], payload.get("Variant")) for payload in payloads]
        frame = pd.DataFrame(
            [
                {
                    "Brand": car.brand,
                    "Model": car.model,
                    "Variant_Key": car.variant_key,
                    "Year": payload["Year"],
                    "Kms_Driven": payload["Kms_Driven"],
                    "Fuel_Type": payload["Fuel_Type"],
                    "Transmission": payload["Transmission"],
                    "Owner": payload["Owner"],
                    "Platform": payload.get("Platform") or "CarDekho",
                }
                for car, payload in zip(cars, payloads)
            ]
        )
        prices = self.model.predict(build_features(frame, self.reference_year))
        lower, upper = apply_interval(prices, self._low_q, self._high_q)
        return [
            {
                "price": round(float(price), 2),
                "lower": round(float(low), 2),
                "upper": round(float(high), 2),
                "matched_car": car.matched_name,
                "matched_variant": car.variant_name,
                "warnings": self._warnings(car, payload, float(price)),
            }
            for price, low, high, car, payload in zip(prices, lower, upper, cars, payloads)
        ]

    def predict(self, payload: dict) -> dict:
        return self.predict_many([payload])[0]


@lru_cache(maxsize=1)
def get_predictor() -> Predictor:
    return Predictor()
