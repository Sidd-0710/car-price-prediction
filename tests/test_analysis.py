from carprice.analysis import analyze

from .conftest import needs_model

pytestmark = needs_model


def test_drivers_describe_real_alternatives(predictor, swift):
    drivers = {row["key"]: row for row in analyze(predictor, swift)["drivers"]}
    assert "fuel_petrol" not in drivers  # never "Petrol instead of Petrol"
    assert "fuel_electric" not in drivers  # a Swift is never sold as an electric car
    assert drivers["gearbox"]["label"] == "Automatic gearbox"
    assert {"platform_cars24", "platform_spinny"} <= set(drivers)
    assert "first_owner" not in drivers  # already the first owner
    assert drivers["older"]["delta"] < 0  # an older car is worth less


def test_drivers_are_sorted_by_size(predictor, swift):
    deltas = [abs(row["delta"]) for row in analyze(predictor, swift)["drivers"]]
    assert deltas == sorted(deltas, reverse=True)


def test_forecast_loses_value_over_time(predictor, swift):
    prices = [point["price"] for point in analyze(predictor, swift)["forecast"]["points"]]
    assert prices[-1] < prices[0]


def test_newer_than_the_data_still_forecasts(predictor, swift):
    """A car newer than the data's last year must still show depreciation, not a flat line."""
    result = analyze(predictor, {**swift, "Year": predictor.reference_year + 1})
    prices = [point["price"] for point in result["forecast"]["points"]]
    assert prices[-1] < prices[0]
    assert "newer" not in {row["key"] for row in result["drivers"]}
    assert result["estimate"]["warnings"]


def test_variant_comparison_uses_same_fuel_and_gearbox(predictor, swift):
    drivers = {row["key"]: row for row in analyze(predictor, swift)["drivers"]}
    assert "AMT" not in drivers.get("top_variant", {}).get("label", "")  # manual car compared with manual variants
    if "base_variant" in drivers and "top_variant" in drivers:
        assert drivers["base_variant"]["price"] < drivers["top_variant"]["price"]
