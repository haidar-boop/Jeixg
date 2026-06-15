"""Concrete scikit-learn prediction models and an ensemble.

Each model wraps an sklearn estimator (with feature scaling where it helps) and
implements the :class:`PredictionModel` interface so the trainer, backtester and
strategies can treat them uniformly.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    GradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .base import PredictionModel


class _SklearnModel(PredictionModel):
    """Shared persistence/predict plumbing for sklearn-backed models."""

    def __init__(self, estimator, name: str | None = None, scale: bool = False) -> None:
        super().__init__(name=name)
        self._estimator = (
            Pipeline([("scaler", StandardScaler()), ("model", estimator)])
            if scale else estimator
        )

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "PredictionModel":
        self.metadata.feature_names = list(X.columns)
        self._estimator.fit(X.to_numpy(), np.asarray(y))
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self._estimator.predict(X.to_numpy())

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        if not hasattr(self._estimator, "predict_proba"):
            raise NotImplementedError
        return self._estimator.predict_proba(X.to_numpy())

    def save(self, path: str) -> None:
        import joblib
        joblib.dump({"estimator": self._estimator, "metadata": self.metadata}, path)

    @classmethod
    def load(cls, path: str) -> "PredictionModel":
        import joblib
        blob = joblib.load(path)
        obj = cls.__new__(cls)
        PredictionModel.__init__(obj, name=blob["metadata"].name)
        obj._estimator = blob["estimator"]
        obj.metadata = blob["metadata"]
        return obj


class RandomForestModel(_SklearnModel):
    task = "classification"

    def __init__(self, n_estimators: int = 200, max_depth: int | None = None,
                 random_state: int = 42, **kw) -> None:
        super().__init__(
            RandomForestClassifier(n_estimators=n_estimators, max_depth=max_depth,
                                   random_state=random_state, n_jobs=-1, **kw),
            name="RandomForest",
        )


class GradientBoostingModel(_SklearnModel):
    task = "classification"

    def __init__(self, n_estimators: int = 200, learning_rate: float = 0.05, **kw) -> None:
        super().__init__(
            GradientBoostingClassifier(n_estimators=n_estimators,
                                       learning_rate=learning_rate, **kw),
            name="GradientBoosting",
        )


class LogisticRegressionModel(_SklearnModel):
    task = "classification"

    def __init__(self, C: float = 1.0, max_iter: int = 1000, **kw) -> None:
        super().__init__(
            LogisticRegression(C=C, max_iter=max_iter, **kw),
            name="LogisticRegression", scale=True,
        )


class LinearRegressionModel(_SklearnModel):
    task = "regression"

    def __init__(self, **kw) -> None:
        super().__init__(LinearRegression(**kw), name="LinearRegression", scale=True)


class RidgeModel(_SklearnModel):
    task = "regression"

    def __init__(self, alpha: float = 1.0, **kw) -> None:
        super().__init__(Ridge(alpha=alpha, **kw), name="Ridge", scale=True)


class EnsembleModel(PredictionModel):
    """Soft-voting (classification) / averaging (regression) ensemble."""

    def __init__(self, models: list[PredictionModel], name: str = "Ensemble") -> None:
        super().__init__(name=name)
        if not models:
            raise ValueError("EnsembleModel requires at least one model")
        self.models = models
        self.task = models[0].task

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "PredictionModel":
        self.metadata.feature_names = list(X.columns)
        for m in self.models:
            m.fit(X, y)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.task == "regression":
            return np.mean([m.predict(X) for m in self.models], axis=0)
        try:
            proba = self.predict_proba(X)
            return proba.argmax(axis=1)
        except NotImplementedError:
            preds = np.array([m.predict(X) for m in self.models])
            # Majority vote.
            from scipy import stats
            return stats.mode(preds, axis=0, keepdims=False).mode

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        probas = []
        for m in self.models:
            probas.append(m.predict_proba(X))
        return np.mean(probas, axis=0)

    def save(self, path: str) -> None:
        import joblib
        joblib.dump(self, path)

    @classmethod
    def load(cls, path: str) -> "PredictionModel":
        import joblib
        return joblib.load(path)


CLASSIFIERS = {
    "random_forest": RandomForestModel,
    "gradient_boosting": GradientBoostingModel,
    "logistic": LogisticRegressionModel,
}
REGRESSORS = {
    "linear": LinearRegressionModel,
    "ridge": RidgeModel,
}
