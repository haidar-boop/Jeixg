"""Fibonacci retracement and extension levels.

These are simple, stateless helpers that map standard Fibonacci ratios to
absolute price levels given a swing high and swing low. They work for both
up-moves and down-moves: the retracement levels are measured from the high
toward the low, so a ratio of ``0.0`` maps to ``high_price`` and ``1.0`` maps
to ``low_price``.
"""

from __future__ import annotations

__all__ = [
    "fibonacci_retracements",
    "fibonacci_extensions",
]

_RETRACEMENT_RATIOS = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)
_EXTENSION_RATIOS = (1.272, 1.414, 1.618, 2.0, 2.618)


def fibonacci_retracements(
    high_price: float,
    low_price: float,
) -> dict[float, float]:
    """Compute Fibonacci retracement price levels for a swing.

    The price range is ``high_price - low_price``. Each retracement level is
    measured down from the high, so ``ratio = 0.0`` returns ``high_price`` and
    ``ratio = 1.0`` returns ``low_price``.

    Parameters
    ----------
    high_price : float
        The swing high price.
    low_price : float
        The swing low price.

    Returns
    -------
    dict[float, float]
        Mapping of each ratio in ``(0.0, 0.236, 0.382, 0.5, 0.618, 0.786,
        1.0)`` to its corresponding price level.
    """
    price_range = high_price - low_price
    return {ratio: high_price - ratio * price_range for ratio in _RETRACEMENT_RATIOS}


def fibonacci_extensions(
    high_price: float,
    low_price: float,
) -> dict[float, float]:
    """Compute Fibonacci extension price levels for a swing.

    Extensions project beyond the swing low (for a measured down-move). Each
    level is ``high_price - ratio * (high_price - low_price)``, so ratios
    greater than ``1.0`` extend below ``low_price``.

    Parameters
    ----------
    high_price : float
        The swing high price.
    low_price : float
        The swing low price.

    Returns
    -------
    dict[float, float]
        Mapping of each ratio in ``(1.272, 1.414, 1.618, 2.0, 2.618)`` to its
        corresponding projected price level.
    """
    price_range = high_price - low_price
    return {ratio: high_price - ratio * price_range for ratio in _EXTENSION_RATIOS}
