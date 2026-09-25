import pytest

from carprice.config import METADATA_PATH, MODEL_PATH

needs_model = pytest.mark.skipif(
    not (MODEL_PATH.exists() and METADATA_PATH.exists()),
    reason="No trained model yet - run `python train.py` first",
)


@pytest.fixture(scope="session")
def predictor():
    from carprice.predictor import get_predictor

    return get_predictor()


@pytest.fixture
def swift():
    return {
        "Car_Name": "Maruti Suzuki Swift",
        "Variant": "VXI",
        "Year": 2019,
        "Kms_Driven": 50000,
        "Fuel_Type": "Petrol",
        "Transmission": "Manual",
        "Owner": 0,
        "Platform": "CarDekho",
    }
