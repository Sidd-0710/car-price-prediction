"""Everything the website shows for one car, from a single batch of predictions.

Besides the estimate itself this answers the questions people actually ask:
  - how does the price change with age and kilometres?  (curves)
  - which details matter for MY car?                    (price drivers)
  - should I sell now or later?                         (forecast)
  - what do real cars like mine sell for?               (similar listings)
"""

from datetime import date

from .data import PLATFORMS
from .evaluate import PRICE_BAND_LABELS, PRICE_BANDS
from .insights import similar_listings

CURVE_YEARS = 20
KMS_CURVE = list(range(0, 200_001, 10_000))
FORECAST_YEARS = 5
DRIVER_KMS = 20_000
DEFAULT_ANNUAL_KMS = 10_000
MIN_VARIANT_LISTINGS = 5  # variants compared in "base / top variant" must have this many listings
MAX_VARIANTS_COMPARED = 15


def _annual_kms(year: int, kms: int) -> int:
    """How many km a year this car has been driven (rounded, kept in a sensible range)."""
    age_today = max(date.today().year - year, 1)
    if kms <= 0:
        return DEFAULT_ANNUAL_KMS
    return int(round(min(max(kms / age_today, 3_000), 40_000), -3))


def _band_error(price: float, bands: list[dict]) -> dict | None:
    for low, high, label in zip(PRICE_BANDS, PRICE_BANDS[1:], PRICE_BAND_LABELS):
        if low <= price < high:
            match = next((band for band in bands if band["band"] == label), None)
            if match:
                return {"band": label, "median_ape": round(match["median_ape"], 1), "cars": match["cars"]}
    return None


def analyze(predictor, car: dict) -> dict:
    """`car` holds plain values: Car_Name, Variant, Year, Kms_Driven, Fuel_Type, Transmission, Owner, Platform."""
    resolved = predictor.resolve(car["Car_Name"], car.get("Variant"))  # raises UnknownCarError early
    reference = predictor.reference_year
    year, kms = car["Year"], car["Kms_Driven"]
    effective_year = min(year, reference)  # the model has no listings newer than its reference year
    platform = car.get("Platform") or "CarDekho"
    info = predictor.model_details(resolved.brand, resolved.model) if resolved.model_known else None

    scenarios: list[tuple[str, object, str, dict]] = []

    def scenario(group, key, label="", **changes):
        scenarios.append((group, key, label, {**car, **changes}))

    scenario("estimate", "now")
    for curve_year in range(max(1995, reference - CURVE_YEARS), reference + 1):
        scenario("year", curve_year, Year=curve_year)
    for curve_kms in KMS_CURVE:
        scenario("kms", curve_kms, Kms_Driven=curve_kms)

    # --- price drivers: the same car with ONE detail changed
    if effective_year < reference:
        scenario("driver", "newer", "1 year newer", Year=effective_year + 1)
    scenario("driver", "older", "1 year older", Year=effective_year - 1)
    scenario("driver", "more_kms", f"{DRIVER_KMS:,} km more", Kms_Driven=kms + DRIVER_KMS)
    if kms >= DRIVER_KMS:
        scenario("driver", "fewer_kms", f"{DRIVER_KMS:,} km fewer", Kms_Driven=kms - DRIVER_KMS)
    fuels = info["fuels"] if info else ["Petrol", "Diesel", "CNG"]
    for fuel in fuels:  # only fuels this model is really sold with
        if fuel != car["Fuel_Type"]:
            scenario("driver", f"fuel_{fuel.lower()}", f"{fuel} instead of {car['Fuel_Type']}", Fuel_Type=fuel)
    other_gearbox = "Automatic" if car["Transmission"] == "Manual" else "Manual"
    if not info or other_gearbox in info["transmissions"]:
        scenario("driver", "gearbox", f"{other_gearbox} gearbox", Transmission=other_gearbox)
    if car["Owner"] > 0:
        scenario("driver", "first_owner", "First owner", Owner=0)
    if car["Owner"] < 3:
        scenario("driver", "extra_owner", "One more previous owner", Owner=car["Owner"] + 1)
    for other in PLATFORMS:
        if other != platform:
            scenario("driver", f"platform_{other.lower()}", f"Listed on {other} instead of {platform}", Platform=other)

    # candidates for "base variant" / "top variant": common variants with the same fuel and gearbox
    comparable = []
    if info:
        comparable = [
            variant
            for variant in info["variants"]
            if variant["listings"] >= MIN_VARIANT_LISTINGS
            and variant["fuel"] == car["Fuel_Type"]
            and variant["transmission"] == car["Transmission"]
            and variant["years"][0] - 2 <= effective_year <= variant["years"][1] + 2  # sold around then
        ][:MAX_VARIANTS_COMPARED]
        for variant in comparable:
            scenario("variant", variant["key"], variant["name"], Variant=variant["name"], Car_Name=f"{resolved.brand} {resolved.model}")

    annual_kms = _annual_kms(year, kms)
    for years_ahead in range(1, FORECAST_YEARS + 1):
        scenario("forecast", years_ahead, Year=effective_year - years_ahead, Kms_Driven=kms + years_ahead * annual_kms)

    results = predictor.predict_many([payload for *_, payload in scenarios])
    estimate = results[0]
    price = estimate["price"]

    def points(group):
        return [
            {"x": key, "price": result["price"], "lower": result["lower"], "upper": result["upper"]}
            for (name, key, _, _), result in zip(scenarios, results)
            if name == group
        ]

    def driver(key, label, result):
        return {
            "key": key,
            "label": label,
            "price": result["price"],
            "delta": round(result["price"] - price, 2),
            "percent": round((result["price"] - price) / price * 100, 1),
        }

    drivers = [driver(key, label, result) for (name, key, label, _), result in zip(scenarios, results) if name == "driver"]

    variant_prices = [(result["price"], key, label) for (name, key, label, _), result in zip(scenarios, results) if name == "variant"]
    if len(variant_prices) >= 2:
        cheapest, priciest = min(variant_prices), max(variant_prices)
        by_key = {key: result for (name, key, _, _), result in zip(scenarios, results) if name == "variant"}
        if cheapest[1] != resolved.variant_key:
            drivers.append(driver("base_variant", f"Base variant ({cheapest[2]})", by_key[cheapest[1]]))
        if priciest[1] != resolved.variant_key:
            drivers.append(driver("top_variant", f"Top variant ({priciest[2]})", by_key[priciest[1]]))
    drivers.sort(key=lambda row: abs(row["delta"]), reverse=True)

    forecast = [{"years": 0, "price": price, "kms": kms, "percent": 0.0}]
    for point in points("forecast"):
        forecast.append(
            {
                "years": point["x"],
                "price": point["price"],
                "kms": kms + point["x"] * annual_kms,
                "percent": round((point["price"] - price) / price * 100, 1),
            }
        )

    variant_info = next((v for v in info["variants"] if v["key"] == resolved.variant_key), None) if info else None
    return {
        "estimate": {**estimate, "confidence_percent": predictor.metadata["interval"]["confidence_percent"]},
        "car": {
            "brand": resolved.brand,
            "model": resolved.model,
            "variant": resolved.variant_name,
            "matched_name": resolved.matched_name,
            "model_known": resolved.model_known,
            "variant_known": resolved.variant_name is not None,
            "listings": info["listings"] if info else 0,
            "variant_listings": variant_info["listings"] if variant_info else 0,
        },
        "accuracy": _band_error(price, predictor.metadata["error_by_price_band"]),
        "year_curve": points("year"),
        "kms_curve": points("kms"),
        "drivers": drivers,
        "forecast": {"annual_kms": annual_kms, "points": forecast},
        "similar": similar_listings(resolved.brand, resolved.model, resolved.variant_key, year, kms),
        "reference_year": reference,
    }
