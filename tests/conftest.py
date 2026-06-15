"""Shared pytest fixtures."""
from __future__ import annotations

from datetime import datetime

import pytest

from quanttrade.data import create_data_provider


@pytest.fixture
def provider():
    return create_data_provider("synthetic")


@pytest.fixture
def ohlcv(provider):
    return provider.get_historical_bars("AAPL", datetime(2021, 1, 1), datetime(2023, 1, 1))


@pytest.fixture
def multi_data(provider):
    return {
        s: provider.get_historical_bars(s, datetime(2020, 1, 1), datetime(2023, 1, 1))
        for s in ["AAPL", "MSFT"]
    }
