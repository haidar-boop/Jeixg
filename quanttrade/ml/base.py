"""Base interfaces for prediction models."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd


@dataclass
class ModelMetadata:
    name: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metrics: dict[str, float] = field(default_factory=dict)
    feature_names: list[str] = field(default_factory=list)
    task: str = "classification"  # or "regression"


class PredictionModel(ABC):
    """Common interface for all ML/DL prediction models in the platform."""

    task: str = "classification"

    def __init__(self, name: str | None = None) -> None:
        self.metadata = ModelMetadata(name=name or self.__class__.__name__, task=self.task)

    @abstractmethod
    def fit(self, X: pd.DataFrame, y: pd.Series) -> "PredictionModel": ...

    @abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray: ...

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:  # pragma: no cover - optional
        raise NotImplementedError(f"{self.metadata.name} does not support probabilities")

    @abstractmethod
    def save(self, path: str) -> None: ...

    @classmethod
    @abstractmethod
    def load(cls, path: str) -> "PredictionModel": ...
