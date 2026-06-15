"""Tests for the ML/feature/sentiment/RL modules."""
from quanttrade.ml import (
    FeatureEngineer,
    ModelTrainer,
    QLearningAgent,
    RandomForestModel,
    SentimentAnalyzer,
    TradingEnv,
)


def test_feature_engineering_no_nan(ohlcv):
    X, y = FeatureEngineer().build_dataset(ohlcv, horizon=5)
    assert len(X) == len(y)
    assert not X.isna().any().any()


def test_no_lookahead_label_alignment(ohlcv):
    # Labels are forward returns -> last `horizon` rows must be dropped.
    fe = FeatureEngineer()
    X, _ = fe.build_dataset(ohlcv, horizon=5)
    assert X.index.max() < ohlcv.index.max()


def test_model_train(ohlcv):
    X, y = FeatureEngineer().build_dataset(ohlcv, horizon=5)
    metrics = ModelTrainer().train(RandomForestModel(n_estimators=20), X, y)
    assert "accuracy" in metrics


def test_model_save_load(tmp_path, ohlcv):
    X, y = FeatureEngineer().build_dataset(ohlcv, horizon=5)
    model = RandomForestModel(n_estimators=20).fit(X, y)
    path = tmp_path / "model.joblib"
    model.save(str(path))
    loaded = RandomForestModel.load(str(path))
    assert list(loaded.predict(X.head(3))) == list(model.predict(X.head(3)))


def test_sentiment_polarity():
    sa = SentimentAnalyzer()
    assert sa.score("bullish surge, strong profit beat") > 0
    assert sa.score("bearish crash, huge loss and fraud") < 0
    assert sa.score("the meeting is at noon") == 0.0


def test_sentiment_negation():
    sa = SentimentAnalyzer()
    assert sa.score("not bullish") < 0


def test_rl_agent_learns(ohlcv):
    env = TradingEnv(ohlcv["close"])
    agent = QLearningAgent()
    history = agent.train(env, episodes=5)
    assert len(history) == 5
