"""Request and response shapes for the API. FastAPI turns these into the /docs page."""

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

MAX_YEAR = date.today().year + 1
MAX_BATCH = 60


class FuelType(str, Enum):
    petrol = "Petrol"
    diesel = "Diesel"
    cng = "CNG"
    electric = "Electric"


class PlatformName(str, Enum):
    cardekho = "CarDekho"
    cars24 = "Cars24"
    spinny = "Spinny"


class TransmissionType(str, Enum):
    manual = "Manual"
    automatic = "Automatic"


class CarFeatures(BaseModel):
    Car_Name: str = Field(
        ...,
        min_length=1,
        max_length=80,
        examples=["Maruti Suzuki Swift"],
        description="Brand and model, e.g. 'Maruti Suzuki Swift'. A model on its own ('swift') also works, "
        "and a variant can be added at the end ('Maruti Swift VXI AMT'). See GET /cars for every name.",
    )
    Variant: str | None = Field(
        None,
        max_length=60,
        examples=["VXI"],
        description="Variant / trim, e.g. 'VXI', 'ZXI Plus AMT'. Optional: leave it out if you are not sure. "
        "See GET /catalog/variants?car=... for the variants of a model.",
    )
    Year: int = Field(..., ge=1990, le=MAX_YEAR, examples=[2015], description="Registration year")
    Kms_Driven: int = Field(..., ge=0, le=1_000_000, examples=[50000], description="Odometer reading in km")
    Fuel_Type: FuelType = Field(..., examples=["Petrol"])
    Transmission: TransmissionType = Field(..., examples=["Manual"])
    Owner: Literal[0, 1, 2, 3] = Field(
        ...,
        examples=[0],
        description="Number of previous owners: 0 = first owner, 3 = three or more previous owners",
    )
    Platform: PlatformName = Field(
        PlatformName.cardekho,
        examples=["CarDekho"],
        description="Where the car is listed. CarDekho is an open marketplace (owners and dealers); "
        "Cars24 and Spinny are online dealers that buy and resell cars. Each has its own price level.",
    )


class PredictionResponse(BaseModel):
    prediction_price: float = Field(description="Estimated selling price in lakhs of rupees (1 lakh = 100,000)")
    lower_price: float = Field(description="Bottom of the likely price range, in lakhs")
    upper_price: float = Field(description="Top of the likely price range, in lakhs")
    confidence_percent: int = Field(description="How often the true price fell inside the range on unseen test cars")
    matched_car: str = Field(description="The brand, model and variant the name was understood as")
    matched_variant: str | None = Field(None, description="The variant it was matched to, if any")
    warnings: list[str] = Field(default_factory=list, description="Reasons to treat this estimate with extra care")


class BatchRequest(BaseModel):
    cars: list[CarFeatures] = Field(..., min_length=1, max_length=MAX_BATCH)


class BatchResponse(BaseModel):
    predictions: list[PredictionResponse]


# ---------------------------------------------------------- /analyze
class Estimate(BaseModel):
    price: float = Field(description="Estimated price, in lakhs")
    lower: float
    upper: float
    confidence_percent: int
    matched_car: str
    matched_variant: str | None
    warnings: list[str]


class MatchedCar(BaseModel):
    brand: str
    model: str
    variant: str | None = Field(description="The catalogue name of the variant, if recognised")
    matched_name: str
    model_known: bool
    variant_known: bool
    listings: int = Field(description="How many listings of this model the model learned from")
    variant_listings: int = Field(description="How many listings of this exact variant it learned from")


class BandAccuracy(BaseModel):
    band: str
    median_ape: float = Field(description="Typical error (%) for test cars in this price band")
    cars: int


class CurvePoint(BaseModel):
    x: int
    price: float
    lower: float
    upper: float


class PriceDriver(BaseModel):
    key: str
    label: str = Field(examples=["Diesel instead of Petrol"])
    price: float
    delta: float = Field(description="Change from the estimate, in lakhs")
    percent: float


class ForecastPoint(BaseModel):
    years: int = Field(description="Years from now")
    price: float
    kms: int
    percent: float = Field(description="Change from today's estimate, in %")


class Forecast(BaseModel):
    annual_kms: int = Field(description="Kilometres per year assumed for the future")
    points: list[ForecastPoint]


class Listing(BaseModel):
    name: str
    year: int
    kms: int
    fuel: str
    transmission: str
    owner: str
    platform: str
    city: str
    same_variant: bool
    price: float


class AnalysisResponse(BaseModel):
    estimate: Estimate
    car: MatchedCar
    accuracy: BandAccuracy | None
    year_curve: list[CurvePoint] = Field(description="Estimated price for each registration year")
    kms_curve: list[CurvePoint] = Field(description="Estimated price for 0 to 200,000 km")
    drivers: list[PriceDriver] = Field(description="How the price changes if one detail is different, biggest first")
    forecast: Forecast = Field(description="Estimated value over the next 5 years")
    similar: list[Listing] = Field(description="Real listings of similar cars")
    reference_year: int = Field(description="Year of the newest listings the model learned from")
