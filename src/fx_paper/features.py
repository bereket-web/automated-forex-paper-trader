"""Causal features aligned to a delayed paper fill and a one-bar holding period."""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "return_lag_0",
    "return_lag_1",
    "return_lag_2",
    "return_lag_5",
    "return_lag_10",
    "return_lag_21",
    "return_mean_5",
    "return_mean_21",
    "return_mean_63",
    "volatility_5",
    "volatility_21",
    "volatility_63",
    "price_vs_sma_21",
    "price_vs_sma_63",
    "weekday_sin",
    "weekday_cos",
]


def make_feature_target(prices: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Return features known at each close and the next tradable-bar return.

    A signal is formed at close *t*, filled at close *t+1*, and held until close
    *t+2*. Therefore row *t* predicts log(close[t+2] / close[t+1]), not the
    already-moving return from the signal close to the fill close. Target rows
    remain NaN until their outcomes are fully observed.
    """
    if "close" not in prices.columns:
        raise ValueError("prices must contain a 'close' column")
    if not prices.index.is_monotonic_increasing or prices.index.has_duplicates:
        raise ValueError("price dates must be strictly increasing and unique")
    close = pd.to_numeric(prices["close"], errors="coerce")
    if close.isna().any() or not np.isfinite(close.to_numpy()).all() or (close <= 0).any():
        raise ValueError("close values must be finite and positive")

    log_return = np.log(close).diff()
    features = pd.DataFrame(index=prices.index)
    for lag in (0, 1, 2, 5, 10, 21):
        features[f"return_lag_{lag}"] = log_return.shift(lag)
    for window in (5, 21, 63):
        features[f"return_mean_{window}"] = log_return.rolling(window, min_periods=window).mean()
        features[f"volatility_{window}"] = log_return.rolling(window, min_periods=window).std(ddof=0)
    features["price_vs_sma_21"] = close / close.rolling(21, min_periods=21).mean() - 1.0
    features["price_vs_sma_63"] = close / close.rolling(63, min_periods=63).mean() - 1.0
    weekday = pd.DatetimeIndex(prices.index).dayofweek.to_numpy()
    features["weekday_sin"] = np.sin(2 * np.pi * weekday / 5.0)
    features["weekday_cos"] = np.cos(2 * np.pi * weekday / 5.0)
    target = np.log(close.shift(-2) / close.shift(-1)).rename("next_tradable_log_return")
    return features[FEATURE_COLUMNS], target
