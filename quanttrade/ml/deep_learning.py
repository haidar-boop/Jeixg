"""Deep-learning models (optional TensorFlow/Keras backend).

These wrap Keras models behind the :class:`PredictionModel` interface. TensorFlow
is imported lazily so the rest of the platform runs without it; instantiating a
model without TF installed raises a clear, actionable ImportError.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import PredictionModel


def _require_tf():
    try:
        import tensorflow as tf  # noqa: F401
        from tensorflow import keras
    except ImportError as exc:  # pragma: no cover - optional
        raise ImportError(
            "Deep-learning models require TensorFlow. Run `pip install tensorflow`."
        ) from exc
    return keras


class MLPModel(PredictionModel):
    """Feed-forward neural network classifier/regressor."""

    def __init__(self, hidden=(64, 32), epochs: int = 30, task: str = "classification") -> None:
        super().__init__(name="MLP")
        self.task = task
        self.hidden = hidden
        self.epochs = epochs
        self._model = None

    def _build(self, n_features: int):
        keras = _require_tf()
        layers = [keras.layers.Input(shape=(n_features,))]
        for units in self.hidden:
            layers.append(keras.layers.Dense(units, activation="relu"))
        if self.task == "classification":
            layers.append(keras.layers.Dense(1, activation="sigmoid"))
            loss = "binary_crossentropy"
        else:
            layers.append(keras.layers.Dense(1))
            loss = "mse"
        model = keras.Sequential(layers)
        model.compile(optimizer="adam", loss=loss)
        return model

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "PredictionModel":
        self.metadata.feature_names = list(X.columns)
        self._model = self._build(X.shape[1])
        self._model.fit(X.to_numpy(), np.asarray(y), epochs=self.epochs, verbose=0)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        out = self._model.predict(X.to_numpy(), verbose=0).ravel()
        return (out > 0.5).astype(int) if self.task == "classification" else out

    def save(self, path: str) -> None:
        self._model.save(path)

    @classmethod
    def load(cls, path: str) -> "PredictionModel":  # pragma: no cover - optional
        keras = _require_tf()
        obj = cls()
        obj._model = keras.models.load_model(path)
        return obj


class LSTMModel(PredictionModel):
    """LSTM sequence model for time-series prediction."""

    def __init__(self, sequence_length: int = 20, units: int = 64,
                 epochs: int = 30, task: str = "classification") -> None:
        super().__init__(name="LSTM")
        self.task = task
        self.sequence_length = sequence_length
        self.units = units
        self.epochs = epochs
        self._model = None

    def _windows(self, X: np.ndarray) -> np.ndarray:
        seqs = [X[i - self.sequence_length:i] for i in range(self.sequence_length, len(X) + 1)]
        return np.asarray(seqs)

    def _build(self, n_features: int):
        keras = _require_tf()
        out_act = "sigmoid" if self.task == "classification" else None
        loss = "binary_crossentropy" if self.task == "classification" else "mse"
        model = keras.Sequential([
            keras.layers.Input(shape=(self.sequence_length, n_features)),
            keras.layers.LSTM(self.units),
            keras.layers.Dense(1, activation=out_act),
        ])
        model.compile(optimizer="adam", loss=loss)
        return model

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "PredictionModel":
        self.metadata.feature_names = list(X.columns)
        Xw = self._windows(X.to_numpy())
        yw = np.asarray(y)[self.sequence_length - 1:]
        self._model = self._build(X.shape[1])
        self._model.fit(Xw, yw, epochs=self.epochs, verbose=0)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        out = self._model.predict(self._windows(X.to_numpy()), verbose=0).ravel()
        return (out > 0.5).astype(int) if self.task == "classification" else out

    def save(self, path: str) -> None:
        self._model.save(path)

    @classmethod
    def load(cls, path: str) -> "PredictionModel":  # pragma: no cover - optional
        keras = _require_tf()
        obj = cls()
        obj._model = keras.models.load_model(path)
        return obj
