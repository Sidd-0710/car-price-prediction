"""The model pipeline and the candidate algorithms that get compared."""

from collections import Counter

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import (
    ExtraTreesRegressor,
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.model_selection import KFold
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler, TargetEncoder
from sklearn.tree import DecisionTreeRegressor

from .config import MIN_CATEGORY_COUNT, MIN_VARIANT_WORD_COUNT, RANDOM_STATE
from .data import CATEGORICAL_FEATURES, NUMERIC_FEATURES, PRICE_LEVEL_FEATURES, VARIANT_WORDS_FEATURE


# Domain knowledge given to the boosted trees: all else equal, a car is never worth
# MORE because it is older, has more kilometres or has had more owners.
MONOTONIC = {"numbers__Age": -1, "numbers__Kms_Driven": -1, "numbers__Log_Kms": -1, "numbers__Owner": -1}


class VariantWords(TransformerMixin, BaseEstimator):
    """One yes/no column per common word of the variant ("amt", "plus", "turbo"...),
    so the model can price a variant it has rarely seen from the words it shares."""

    def __init__(self, min_count: int = MIN_VARIANT_WORD_COUNT):
        self.min_count = min_count

    @staticmethod
    def _texts(X) -> list[str]:
        values = X.iloc[:, 0] if isinstance(X, pd.DataFrame) else X
        return ["" if value is None else str(value) for value in np.asarray(values).ravel()]

    def fit(self, X, y=None):
        counts = Counter(word for text in self._texts(X) for word in set(text.split()))
        self.vocabulary_ = sorted(word for word, count in counts.items() if count >= self.min_count)
        return self

    def transform(self, X):
        index = {word: i for i, word in enumerate(self.vocabulary_)}
        texts = self._texts(X)
        out = np.zeros((len(texts), len(index)))
        for row, text in enumerate(texts):
            for word in set(text.split()):
                column = index.get(word)
                if column is not None:
                    out[row, column] = 1.0
        return out

    def get_feature_names_out(self, input_features=None):
        return np.array([f"word_{word}" for word in self.vocabulary_], dtype=object)


def make_pipeline(estimator) -> TransformedTargetRegressor:
    """Encode -> scale -> model, all in ONE object so nothing can get out of sync.

    Prices are heavily skewed (a few very expensive cars), so the model learns
    log(price) and the result is converted back to lakhs automatically.

    Brand and Model are encoded two ways at once: one-hot (which car is it?)
    and target encoding (how expensive are cars like this, on average?). The
    exact variant ("Trim", e.g. Maruti Suzuki|Swift|vxi) gets a price level too,
    and the variant's words ("amt", "plus", "turbo"...) become yes/no columns, so
    the model can also price variants it has seen only a few times. Target
    encoding is cross-fitted inside scikit-learn, so it does not leak the answer
    while training.
    """
    preprocess = ColumnTransformer(
        [
            (
                "price_level",
                TargetEncoder(
                    target_type="continuous",
                    cv=KFold(5, shuffle=True, random_state=RANDOM_STATE),
                ),
                PRICE_LEVEL_FEATURES,
            ),
            (
                "categories",
                OneHotEncoder(
                    handle_unknown="infrequent_if_exist",
                    min_frequency=MIN_CATEGORY_COUNT,
                    sparse_output=False,
                ),
                CATEGORICAL_FEATURES,
            ),
            ("numbers", StandardScaler(), NUMERIC_FEATURES),
            ("variant_words", VariantWords(), [VARIANT_WORDS_FEATURE]),
        ],
        sparse_threshold=0,  # always a plain table of numbers, which every algorithm accepts
    )
    preprocess.set_output(transform="pandas")  # named columns, so constraints can refer to "numbers__Age"
    return TransformedTargetRegressor(
        regressor=Pipeline([("preprocess", preprocess), ("model", estimator)]),
        func=np.log1p,
        inverse_func=np.expm1,
    )


def apply_interval(prediction, low_q: float, high_q: float):
    """Turn a price prediction into a (lower, upper) range.

    `low_q` / `high_q` are percentiles of the model's past errors measured in
    log-price units (calculated during training), so the range is wider for
    expensive cars and narrower for cheap ones.
    """
    log_price = np.log1p(np.asarray(prediction, dtype=float))
    return np.expm1(log_price + low_q), np.expm1(log_price + high_q)


def candidate_models() -> dict:
    """Every algorithm we compare, from a do-nothing baseline to boosted trees."""
    return {
        "Baseline (median price)": DummyRegressor(strategy="median"),
        "Linear Regression": LinearRegression(),
        "Ridge Regression": Ridge(alpha=3.0),
        "K-Nearest Neighbours": KNeighborsRegressor(n_neighbors=7, weights="distance"),
        "Decision Tree": DecisionTreeRegressor(min_samples_leaf=3, random_state=RANDOM_STATE),
        "Random Forest": RandomForestRegressor(
            n_estimators=150, min_samples_leaf=2, max_features=0.5, n_jobs=-1, random_state=RANDOM_STATE
        ),
        "Extra Trees": ExtraTreesRegressor(
            n_estimators=150, min_samples_leaf=2, max_features=0.5, n_jobs=-1, random_state=RANDOM_STATE
        ),
        "Gradient Boosting": GradientBoostingRegressor(random_state=RANDOM_STATE),
        "Hist Gradient Boosting": HistGradientBoostingRegressor(random_state=RANDOM_STATE, monotonic_cst=MONOTONIC),
    }


# Settings tried when tuning the best models (name in candidate_models -> grid).
# Keys are pipeline parameter paths: regressor__model__<setting>.
SEARCH_SPACES = {
    "Ridge Regression": {
        "regressor__model__alpha": [0.01, 0.03, 0.1, 0.3, 1.0, 3.0],
    },
    "Random Forest": {
        "regressor__model__n_estimators": [60, 80, 100],
        "regressor__model__min_samples_leaf": [2, 3, 5],
        "regressor__model__max_features": [0.3, 0.5, 0.7],
    },
    "Extra Trees": {
        "regressor__model__n_estimators": [60, 80, 100],
        "regressor__model__min_samples_leaf": [2, 3, 5],
        "regressor__model__max_features": [0.3, 0.5, 0.7],
    },
    "Gradient Boosting": {
        "regressor__model__n_estimators": [200, 400],
        "regressor__model__learning_rate": [0.05, 0.1],
        "regressor__model__max_depth": [4, 5, 6],
        "regressor__model__subsample": [0.7, 1.0],
        "regressor__model__min_samples_leaf": [5, 10, 20],
    },
    "Hist Gradient Boosting": {
        "regressor__model__learning_rate": [0.03, 0.05, 0.1],
        "regressor__model__max_iter": [300, 600, 1000],
        "regressor__model__max_leaf_nodes": [31, 63, 127],
        "regressor__model__min_samples_leaf": [5, 10, 20],
        "regressor__model__l2_regularization": [0.0, 0.1, 1.0],
    },
}
