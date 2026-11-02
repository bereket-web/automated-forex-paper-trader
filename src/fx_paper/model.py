"""Walk-forward return forecasters with strict as-of label availability."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor


class WalkForwardForecaster:
    """Refit a compact regressor at a fixed cadence using only matured labels."""

    def __init__(
        self,
        *,
        model_kind: str = "histgb",
        min_train: int = 300,
        lookback: int = 1_500,
        retrain_every: int = 20,
        seed: int = 42,
    ) -> None:
        if model_kind not in {"histgb", "zero"}:
            raise ValueError("model_kind must be 'histgb' or 'zero'")
        if min_train < 20 or lookback < min_train or retrain_every < 1:
            raise ValueError("invalid training window or refit cadence")
        self.model_kind = model_kind
        self.min_train = min_train
        self.lookback = lookback
        self.retrain_every = retrain_every
        self.seed = seed
        self.model: HistGradientBoostingRegressor | None = None
        self.last_fit_index: int | None = None
        self.fit_count = 0

    def predict_asof(self, index: int, features: pd.DataFrame, target: pd.Series) -> float | None:
        """Predict at row ``index``; labels ending after that close are excluded.

        The row-j target exits at j+2. At close i, only labels j <= i-2 are
        mature. The model is refit every ``retrain_every`` signal observations.
        """
        if self.model_kind == "zero":
            return 0.0
        if index < 1 or index >= len(features):
            return None
        needs_fit = self.model is None or self.last_fit_index is None or index - self.last_fit_index >= self.retrain_every
        if needs_fit:
            train_end_exclusive = max(0, index - 1)  # includes j=i-2; excludes j=i-1 and j=i
            train_start = max(0, train_end_exclusive - self.lookback)
            x_train = features.iloc[train_start:train_end_exclusive]
            y_train = target.iloc[train_start:train_end_exclusive]
            valid = x_train.notna().all(axis=1) & y_train.notna()
            x_train = x_train.loc[valid]
            y_train = y_train.loc[valid]
            if len(y_train) < self.min_train:
                return None
            self.model = HistGradientBoostingRegressor(
                learning_rate=0.04,
                max_iter=80,
                max_leaf_nodes=7,
                min_samples_leaf=20,
                l2_regularization=1.0,
                random_state=self.seed,
            )
            self.model.fit(x_train, y_train)
            self.last_fit_index = index
            self.fit_count += 1
        row = features.iloc[[index]]
        if row.isna().any(axis=None):
            return None
        assert self.model is not None
        prediction = float(self.model.predict(row)[0])
        return prediction if np.isfinite(prediction) else None
