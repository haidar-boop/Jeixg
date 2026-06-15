"""Model training, evaluation, cross-validation and auto-selection.

All splits are *time-series aware* (no shuffling) to avoid leaking future
information into the training set -- the cardinal sin of financial ML.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import TimeSeriesSplit

from ..core.logging_config import get_logger
from .base import PredictionModel

logger = get_logger(__name__)


class ModelTrainer:
    """Trains and evaluates :class:`PredictionModel` instances."""

    def evaluate(self, model: PredictionModel, X: pd.DataFrame, y: pd.Series) -> dict:
        preds = model.predict(X)
        if model.task == "regression":
            rmse = float(np.sqrt(mean_squared_error(y, preds)))
            return {"rmse": rmse, "r2": float(r2_score(y, preds))}
        return {
            "accuracy": float(accuracy_score(y, preds)),
            "f1": float(f1_score(y, preds, average="weighted", zero_division=0)),
        }

    def train(self, model: PredictionModel, X: pd.DataFrame, y: pd.Series,
              test_size: float = 0.2) -> dict:
        """Chronological train/test split, fit on train, evaluate on test."""
        n = len(X)
        split = int(n * (1 - test_size))
        X_train, X_test = X.iloc[:split], X.iloc[split:]
        y_train, y_test = y.iloc[:split], y.iloc[split:]
        model.fit(X_train, y_train)
        metrics = self.evaluate(model, X_test, y_test) if len(X_test) else {}
        model.metadata.metrics = metrics
        logger.info("Trained %s -> %s", model.metadata.name, metrics)
        return metrics

    def cross_validate(self, model: PredictionModel, X: pd.DataFrame, y: pd.Series,
                       n_splits: int = 5) -> dict:
        tscv = TimeSeriesSplit(n_splits=n_splits)
        scores: list[float] = []
        key = "r2" if model.task == "regression" else "accuracy"
        for train_idx, test_idx in tscv.split(X):
            model.fit(X.iloc[train_idx], y.iloc[train_idx])
            scores.append(self.evaluate(model, X.iloc[test_idx], y.iloc[test_idx])[key])
        return {f"cv_{key}_mean": float(np.mean(scores)),
                f"cv_{key}_std": float(np.std(scores))}

    def auto_select(self, X: pd.DataFrame, y: pd.Series,
                    candidates: list[PredictionModel] | None = None) -> tuple[PredictionModel, dict]:
        """Train several candidates and return the best by validation score."""
        if candidates is None:
            from .models import (
                GradientBoostingModel,
                LogisticRegressionModel,
                RandomForestModel,
            )
            candidates = [RandomForestModel(), GradientBoostingModel(),
                          LogisticRegressionModel()]
        results: dict[str, dict] = {}
        best, best_score, best_name = None, -np.inf, ""
        metric_key = "r2" if candidates[0].task == "regression" else "f1"
        for model in candidates:
            metrics = self.train(model, X, y)
            results[model.metadata.name] = metrics
            score = metrics.get(metric_key, -np.inf)
            if score > best_score:
                best, best_score, best_name = model, score, model.metadata.name
        logger.info("Auto-selected %s (%s=%.4f)", best_name, metric_key, best_score)
        return best, results
