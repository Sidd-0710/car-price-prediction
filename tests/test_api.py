import pytest
from fastapi.testclient import TestClient

from schema import MAX_BATCH

from .conftest import needs_model

pytestmark = needs_model


@pytest.fixture(scope="module")
def client():
    from main import app

    with TestClient(app) as test_client:
        yield test_client


def test_status_routes(client):
    assert client.get("/api").json()["success"] is True
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["model"]


def test_website_is_served(client):
    page = client.get("/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert "AutoValue" in page.text
    for asset in ("/assets/styles.css", "/assets/js/app.js", "/assets/js/charts.js", "/assets/favicon.svg"):
        response = client.get(asset)
        assert response.status_code == 200, asset
        assert response.headers["cache-control"] == "no-cache"


def test_analyze_returns_everything_the_page_needs(client, swift):
    response = client.post("/analyze", json=swift)
    assert response.status_code == 200
    body = response.json()
    estimate = body["estimate"]
    assert estimate["lower"] < estimate["price"] < estimate["upper"]
    assert body["car"]["matched_name"] == "Maruti Suzuki Swift VXI" and body["car"]["listings"] > 0
    assert body["car"]["variant_known"] and body["car"]["variant_listings"] > 0
    assert body["accuracy"]["median_ape"] > 0
    assert len(body["year_curve"]) > 10 and len(body["kms_curve"]) > 10
    assert body["drivers"] and all("label" in row for row in body["drivers"])
    assert [point["years"] for point in body["forecast"]["points"]] == [0, 1, 2, 3, 4, 5]
    assert body["forecast"]["points"][0]["price"] == estimate["price"]
    assert body["similar"] and all("Swift" in row["name"] for row in body["similar"])
    assert body["similar"][0]["same_variant"]
    assert {"base_variant", "top_variant"} & {row["key"] for row in body["drivers"]}


def test_analyze_agrees_with_predict(client, swift):
    analyzed = client.post("/analyze", json=swift).json()["estimate"]["price"]
    predicted = client.post("/predict", json=swift).json()["prediction_price"]
    assert analyzed == predicted


def test_analyze_unknown_car_is_422(client, swift):
    response = client.post("/analyze", json={**swift, "Car_Name": "Maruti Swfit"})
    assert response.status_code == 422
    assert "Maruti Suzuki Swift" in response.json()["detail"]


def test_insight_endpoints(client):
    market = client.get("/insights/market").json()
    assert market["kpis"]["listings"] > 3000
    assert len(market["depreciation"]) == 4 and market["popular_models"]
    assert {"typical_fuel", "typical_transmission"} <= set(market["popular_models"][0])
    performance = client.get("/insights/performance").json()
    assert performance["comparison"][0]["cv_mae"] == min(row["cv_mae"] for row in performance["comparison"])
    assert len(performance["test_points"]) == performance["data"]["test_rows"]
    details = client.get("/catalog/details").json()
    swift = next(row for row in details if (row["brand"], row["model"]) == ("Maruti Suzuki", "Swift"))
    assert swift["listings"] > 500 and "Petrol" in swift["fuels"] and swift["variants"] > 10


def test_predict_returns_price_and_range(client, swift):
    response = client.post("/predict", json=swift)
    assert response.status_code == 200
    body = response.json()
    assert body["lower_price"] < body["prediction_price"] < body["upper_price"]
    assert body["matched_car"] == "Maruti Suzuki Swift VXI"
    assert body["matched_variant"] == "VXI"
    assert body["confidence_percent"] == 80
    assert body["warnings"] == []


def test_unknown_car_is_422_with_suggestion(client, swift):
    response = client.post("/predict", json={**swift, "Car_Name": "Maruti Swfit"})
    assert response.status_code == 422
    assert "Maruti Suzuki Swift" in response.json()["detail"]


@pytest.mark.parametrize(
    "change",
    [
        {"Owner": 5},
        {"Year": 1800},
        {"Kms_Driven": -1},
        {"Kms_Driven": 5_000_000},
        {"Fuel_Type": "Steam"},
        {"Fuel_Type": "LPG"},
        {"Transmission": "Sideways"},
        {"Car_Name": ""},
        {"Platform": "OLX"},
        {"Variant": "x" * 61},
    ],
)
def test_bad_input_is_rejected(client, swift, change):
    assert client.post("/predict", json={**swift, **change}).status_code == 422


def test_missing_field_is_rejected(client, swift):
    swift.pop("Year")
    assert client.post("/predict", json=swift).status_code == 422


def test_variant_and_platform_are_optional(client, swift):
    minimal = {key: value for key, value in swift.items() if key not in ("Variant", "Platform")}
    body = client.post("/predict", json=minimal).json()
    assert body["prediction_price"] > 0 and body["matched_variant"] is None


def test_variants_endpoint(client):
    body = client.get("/catalog/variants", params={"car": "Maruti Suzuki Swift"}).json()
    assert body["car"] == "Maruti Suzuki Swift" and len(body["variants"]) > 10
    first = body["variants"][0]
    assert {"name", "listings", "fuel", "transmission", "median_price"} <= set(first)
    assert client.get("/catalog/variants", params={"car": "Maruti Swfit"}).status_code == 422


def test_batch(client, swift):
    cars = [{**swift, "Year": year} for year in (2010, 2015, 2020)]
    response = client.post("/predict/batch", json={"cars": cars})
    assert response.status_code == 200
    prices = [row["prediction_price"] for row in response.json()["predictions"]]
    assert prices == sorted(prices)  # newer is more expensive


def test_batch_limits(client, swift):
    assert client.post("/predict/batch", json={"cars": []}).status_code == 422
    too_many = [swift] * (MAX_BATCH + 1)
    assert client.post("/predict/batch", json={"cars": too_many}).status_code == 422


def test_catalog_endpoints(client):
    cars = client.get("/cars").json()
    assert cars["count"] == len(cars["cars"]) > 100
    catalog = client.get("/catalog").json()
    assert "Swift" in catalog["Maruti Suzuki"]


def test_model_info(client):
    info = client.get("/model-info").json()
    assert {"model_name", "test_metrics", "interval", "reference_year"} <= set(info)


def test_docs_are_generated(client):
    schema = client.get("/openapi.json").json()
    assert {"/predict", "/predict/batch", "/cars", "/catalog", "/model-info", "/health"} <= set(schema["paths"])
