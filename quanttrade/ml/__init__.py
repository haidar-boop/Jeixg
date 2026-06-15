"""Machine-learning, deep-learning and reinforcement-learning toolkit.

Only numpy / pandas / scikit-learn are required to import this package. Deep
learning (TensorFlow) and transformer sentiment are optional and lazy-imported.
"""
from .base import ModelMetadata, PredictionModel
from .features import FeatureEngineer
from .models import (
    EnsembleModel,
    GradientBoostingModel,
    LinearRegressionModel,
    LogisticRegressionModel,
    RandomForestModel,
    RidgeModel,
)
from .reinforcement import QLearningAgent, TradingEnv
from .sentiment import SentimentAnalyzer, SentimentResult
from .trainer import ModelTrainer

__all__ = [
    "FeatureEngineer",
    "PredictionModel",
    "ModelMetadata",
    "RandomForestModel",
    "GradientBoostingModel",
    "LogisticRegressionModel",
    "LinearRegressionModel",
    "RidgeModel",
    "EnsembleModel",
    "ModelTrainer",
    "SentimentAnalyzer",
    "SentimentResult",
    "TradingEnv",
    "QLearningAgent",
]
