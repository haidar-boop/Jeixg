"""Example: feature engineering + model auto-selection + evaluation.

    python examples/train_ml_model.py
"""
from datetime import datetime

from quanttrade.data import create_data_provider
from quanttrade.ml import (
    EnsembleModel,
    FeatureEngineer,
    GradientBoostingModel,
    LogisticRegressionModel,
    ModelTrainer,
    RandomForestModel,
)


def main() -> None:
    provider = create_data_provider("synthetic")
    df = provider.get_historical_bars("AAPL", datetime(2015, 1, 1), datetime(2023, 1, 1))

    # 1. Build a leak-free supervised dataset (features = past, label = forward return).
    fe = FeatureEngineer()
    X, y = fe.build_dataset(df, horizon=5)
    print(f"Dataset: {X.shape[0]} samples x {X.shape[1]} features")

    trainer = ModelTrainer()

    # 2. Auto-select the best single model.
    best, results = trainer.auto_select(X, y)
    print("\nCandidate metrics:")
    for name, metrics in results.items():
        print(f"  {name:20s}: {metrics}")
    print(f"Auto-selected: {best.metadata.name}")

    # 3. Build and evaluate an ensemble.
    ensemble = EnsembleModel([
        RandomForestModel(n_estimators=100),
        GradientBoostingModel(n_estimators=100),
        LogisticRegressionModel(),
    ])
    print("\nEnsemble:", trainer.train(ensemble, X, y))

    # 4. Time-series cross-validation of the ensemble.
    print("Ensemble CV:", trainer.cross_validate(ensemble, X, y, n_splits=5))


if __name__ == "__main__":
    main()
