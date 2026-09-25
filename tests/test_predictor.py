import pytest

from carprice.predictor import UnknownCarError

from .conftest import needs_model

pytestmark = needs_model


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("Maruti Suzuki Swift", "Maruti Suzuki Swift"),
        ("Maruti Swift", "Maruti Suzuki Swift"),
        ("swift", "Maruti Suzuki Swift"),
        ("  MARUTI   swift ", "Maruti Suzuki Swift"),
        ("Maruti Swift Dzire", "Maruti Suzuki Swift Dzire"),
        ("hyundai creta", "Hyundai Creta"),
        ("innova crysta", "Toyota Innova Crysta"),
        ("Land Rover Range Rover Evoque", "Land Rover Range Rover Evoque"),
    ],
)
def test_resolve_understands_messy_names(predictor, typed, expected):
    car = predictor.resolve(typed)
    assert f"{car.brand} {car.model}" == expected


@pytest.mark.parametrize("typed", ["VXI", "vxi", " Vxi "])
def test_variant_is_matched_whatever_the_spelling(predictor, typed):
    car = predictor.resolve("Maruti Suzuki Swift", typed)
    assert (car.variant_key, car.variant_name) == ("vxi", "VXI")


def test_variant_can_be_part_of_the_name(predictor):
    car = predictor.resolve("Maruti Swift ZXI AMT")
    assert car.model == "Swift" and car.variant_name is not None and "ZXI" in car.variant_name


def test_close_variant_spelling_is_matched(predictor):
    car = predictor.resolve("Kia Seltos", "GTX Plus DCT Petrol")  # extra word "Petrol"
    assert car.variant_name == "GTX PLUS DCT"


def test_unknown_variant_is_allowed_but_flagged(predictor, swift):
    result = predictor.predict({**swift, "Variant": "Imaginary Edition"})
    assert result["price"] > 0 and result["matched_variant"] is None
    assert any("was not in the listings" in note for note in result["warnings"])


def test_brand_only_is_allowed_but_flagged(predictor, swift):
    result = predictor.predict({**swift, "Car_Name": "Maruti", "Variant": None})
    assert result["price"] > 0
    assert any("No model was given" in note for note in result["warnings"])


@pytest.mark.parametrize("bad", ["", "Tesla Model S Plaid", "Maruti Swfit", "swfit"])
def test_unknown_names_are_rejected(predictor, swift, bad):
    with pytest.raises(UnknownCarError):
        predictor.predict({**swift, "Car_Name": bad})


def test_typo_gets_a_suggestion(predictor):
    with pytest.raises(UnknownCarError) as error:
        predictor.resolve("Maruti Swfit")
    assert "Maruti Suzuki Swift" in error.value.suggestions


def test_range_surrounds_price(predictor, swift):
    result = predictor.predict(swift)
    assert 0 < result["lower"] < result["price"] < result["upper"]


def test_newer_cars_cost_more(predictor, swift):
    assert predictor.predict({**swift, "Year": 2023})["price"] > predictor.predict({**swift, "Year": 2014})["price"]


def test_more_kilometres_cost_less(predictor, swift):
    assert predictor.predict({**swift, "Kms_Driven": 160_000})["price"] < predictor.predict({**swift, "Kms_Driven": 10_000})["price"]


def test_luxury_costs_more_than_economy(predictor, swift):
    alto = predictor.predict({**swift, "Car_Name": "Maruti Alto 800", "Variant": None})["price"]
    bmw = predictor.predict({**swift, "Car_Name": "BMW 5 Series", "Variant": None, "Transmission": "Automatic"})["price"]
    assert bmw > 5 * alto


def test_top_variant_costs_more_than_base(predictor, swift):
    base = predictor.predict({**swift, "Variant": "LXI"})["price"]
    top = predictor.predict({**swift, "Variant": "ZXI PLUS"})["price"]
    assert top > base


def test_platform_effect_is_modest(predictor, swift):
    """Platforms price differently, but the same car should not differ by more than about 15%."""
    prices = [predictor.predict({**swift, "Platform": name})["price"] for name in ("CarDekho", "Cars24", "Spinny")]
    assert max(prices) / min(prices) < 1.15


def test_every_input_changes_the_answer(predictor, swift):
    base = predictor.predict(swift)["price"]
    assert predictor.predict({**swift, "Transmission": "Automatic"})["price"] != base
    assert predictor.predict({**swift, "Owner": 3})["price"] != base
    assert predictor.predict({**swift, "Variant": "ZXI"})["price"] != base
    assert predictor.predict({**swift, "Platform": "Cars24"})["price"] != base
    assert predictor.predict({**swift, "Car_Name": "Hyundai i20", "Variant": None})["price"] != base


def test_future_year_is_flagged(predictor, swift):
    result = predictor.predict({**swift, "Year": predictor.reference_year + 1})
    assert any(str(predictor.reference_year) in note for note in result["warnings"])


def test_batch_matches_single_predictions(predictor, swift):
    cars = [{**swift, "Year": year} for year in (2012, 2017, 2022)]
    assert [row["price"] for row in predictor.predict_many(cars)] == [predictor.predict(car)["price"] for car in cars]
