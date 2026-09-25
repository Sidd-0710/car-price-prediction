"""FastAPI server for the used-car price model, and the AutoValue website.

    uvicorn main:app --reload
        website:  http://127.0.0.1:8000
        API docs: http://127.0.0.1:8000/docs
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from carprice.analysis import analyze
from carprice.insights import market_insights, model_performance
from carprice.predictor import UnknownCarError, get_predictor
from schema import AnalysisResponse, BatchRequest, BatchResponse, CarFeatures, PredictionResponse

WEB_DIR = Path(__file__).resolve().parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_predictor()  # load the model once at start-up (fails loudly if it is missing)
    yield


app = FastAPI(
    title="Car Price Prediction API",
    version="2.1",
    description="Estimates the resale price of a used car in India (in lakhs of rupees). "
    "The AutoValue website is served at `/`.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # Browsers refuse "*" together with credentials, and this API has no
    # cookies or logins, so credentials stay off.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")


@app.middleware("http")
async def revalidate_site_files(request, call_next):
    # Browsers check for a newer copy of the website files on every load
    # (cheap, thanks to ETags), so an update is never hidden behind a stale cache.
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def _to_response(result: dict, confidence: int) -> PredictionResponse:
    return PredictionResponse(
        prediction_price=result["price"],
        lower_price=result["lower"],
        upper_price=result["upper"],
        confidence_percent=confidence,
        matched_car=result["matched_car"],
        matched_variant=result["matched_variant"],
        warnings=result["warnings"],
    )


@app.get("/", include_in_schema=False)
def website():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api", tags=["status"])
def api_root():
    return {"success": True, "message": "Car Price Prediction API is running", "docs": "/docs"}


@app.get("/health", tags=["status"])
def health():
    info = get_predictor().model_info()
    return {"status": "ok", "model": info["model_name"], "trained_at": info["trained_at"]}


@app.get("/model-info", tags=["model"])
def model_info():
    """How the model was trained and how accurate it was on unseen cars."""
    return get_predictor().model_info()


@app.get("/cars", tags=["model"])
def list_cars():
    """Every 'Brand Model' the model was trained on."""
    names = get_predictor().car_names()
    return {"count": len(names), "cars": names}


@app.get("/catalog", tags=["model"])
def catalog():
    """Models grouped by brand, most common first."""
    return get_predictor().catalog()


@app.get("/catalog/details", tags=["model"])
def catalog_details():
    """Every brand and model with its number of listings, fuels, gearboxes and variant count."""
    return get_predictor().catalog_details()


@app.get("/catalog/variants", tags=["model"])
def catalog_variants(car: str):
    """The variants of one model (e.g. ?car=Maruti Suzuki Swift), most listed first, each with
    its usual fuel and gearbox and its median asking price."""
    try:
        return get_predictor().variants(car)
    except UnknownCarError as error:
        raise HTTPException(status_code=422, detail=str(error))


@app.post("/predict", response_model=PredictionResponse, tags=["predict"])
def predict(features: CarFeatures):
    predictor = get_predictor()
    try:
        # mode="json" turns the Enum fields into plain strings ("Petrol", ...)
        result = predictor.predict(features.model_dump(mode="json"))
    except UnknownCarError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return _to_response(result, predictor.model_info()["interval"]["confidence_percent"])


@app.post("/predict/batch", response_model=BatchResponse, tags=["predict"])
def predict_batch(request: BatchRequest):
    """Price several cars at once."""
    predictor = get_predictor()
    confidence = predictor.model_info()["interval"]["confidence_percent"]
    try:
        results = predictor.predict_many([car.model_dump(mode="json") for car in request.cars])
    except UnknownCarError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return BatchResponse(predictions=[_to_response(result, confidence) for result in results])


@app.post("/analyze", response_model=AnalysisResponse, tags=["predict"])
def analyze_car(features: CarFeatures):
    """The estimate plus price curves, price drivers, a 5-year forecast and similar
    real listings. This is what the website calls."""
    try:
        return analyze(get_predictor(), features.model_dump(mode="json"))
    except UnknownCarError as error:
        raise HTTPException(status_code=422, detail=str(error))


@app.get("/insights/market", tags=["insights"])
def insights_market():
    """Summary statistics of the used-car listings (for the Market page)."""
    try:
        return market_insights()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="The dataset file is missing (data/car_dataset_expanded.csv).")


@app.get("/insights/performance", tags=["insights"])
def insights_performance():
    """How the model was chosen and how accurate it is (for the Model page)."""
    return model_performance()
