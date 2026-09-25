"""How the Streamlit app gets predictions.

Normally it calls the FastAPI server. If the server is not running it falls
back to loading the same model directly, so the app still works with one command.
Both backends return exactly the same shapes.
"""

import requests

from .config import METADATA_PATH, MODEL_PATH

MAX_BATCH = 60


class BackendError(Exception):
    """Something the user can act on (bad input, server down, ...)."""


def _tidy_detail(detail) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):  # FastAPI validation errors
        return "; ".join(
            f"{'.'.join(str(part) for part in item.get('loc', [])[1:])}: {item.get('msg', '')}" for item in detail
        )
    return str(detail)


class ApiBackend:
    mode = "api"

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def label(self) -> str:
        return f"FastAPI server at {self.base_url}"

    def _call(self, method: str, path: str, **kwargs):
        try:
            response = requests.request(method, f"{self.base_url}{path}", timeout=20, **kwargs)
        except requests.RequestException as error:
            raise BackendError(f"Could not reach the API at {self.base_url}. Is it running?") from error
        if response.status_code == 422:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise BackendError(_tidy_detail(detail))
        if not response.ok:
            raise BackendError(f"The API returned an error ({response.status_code}).")
        return response.json()

    @staticmethod
    def _normalise(body: dict) -> dict:
        return {
            "price": body["prediction_price"],
            "lower": body["lower_price"],
            "upper": body["upper_price"],
            "matched_car": body["matched_car"],
            "matched_variant": body.get("matched_variant"),
            "warnings": body["warnings"],
        }

    def predict(self, payload: dict) -> dict:
        return self._normalise(self._call("POST", "/predict", json=payload))

    def predict_many(self, payloads: list[dict]) -> list[dict]:
        results = []
        for start in range(0, len(payloads), MAX_BATCH):
            body = self._call("POST", "/predict/batch", json={"cars": payloads[start : start + MAX_BATCH]})
            results.extend(self._normalise(item) for item in body["predictions"])
        return results

    def catalog(self) -> dict[str, list[str]]:
        return self._call("GET", "/catalog")

    def variants(self, car: str) -> list[dict]:
        return self._call("GET", "/catalog/variants", params={"car": car}).get("variants", [])


class LocalBackend:
    mode = "local"

    def __init__(self):
        from .predictor import get_predictor

        self._predictor = get_predictor()

    def label(self) -> str:
        return "the model loaded directly (API server not running)"

    def predict(self, payload: dict) -> dict:
        from .predictor import UnknownCarError

        try:
            return self._predictor.predict(payload)
        except UnknownCarError as error:
            raise BackendError(str(error)) from error

    def predict_many(self, payloads: list[dict]) -> list[dict]:
        from .predictor import UnknownCarError

        try:
            return self._predictor.predict_many(payloads)
        except UnknownCarError as error:
            raise BackendError(str(error)) from error

    def catalog(self) -> dict[str, list[str]]:
        return self._predictor.catalog()

    def variants(self, car: str) -> list[dict]:
        return self._predictor.variants(car).get("variants", [])


def api_is_up(base_url: str) -> bool:
    try:
        return requests.get(f"{base_url.rstrip('/')}/health", timeout=1.5).ok
    except requests.RequestException:
        return False


def choose_backend(api_url: str):
    """The API if it answers, otherwise the local model. None if neither is available."""
    base_url = api_url.removesuffix("/predict").rstrip("/")
    if api_is_up(base_url):
        return ApiBackend(base_url)
    if MODEL_PATH.exists() and METADATA_PATH.exists():
        return LocalBackend()
    return None
