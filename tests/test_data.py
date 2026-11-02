from __future__ import annotations

import pandas as pd
import pytest

from fx_paper.data import load_reference_csv


def test_loads_fred_csv_drops_missing_observations_and_sorts(tmp_path):
    path = tmp_path / "fred.csv"
    path.write_text(
        "observation_date,DEXUSEU\n2024-01-03,1.10\n2024-01-02,.\n2024-01-01,1.08\n",
        encoding="utf-8",
    )
    prices = load_reference_csv(path)
    assert list(prices.columns) == ["close"]
    assert list(prices["close"]) == [1.08, 1.10]
    assert prices.index.is_monotonic_increasing
    assert prices.index.name == "date"


def test_loads_generic_date_close_csv(tmp_path):
    path = tmp_path / "market.csv"
    path.write_text("date,close\n2024-01-01,1.2\n2024-01-02,1.3\n", encoding="utf-8")
    prices = load_reference_csv(path)
    assert prices.iloc[-1, 0] == pytest.approx(1.3)
    assert isinstance(prices.index, pd.DatetimeIndex)


def test_rejects_ambiguous_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("date,bid,ask\n2024-01-01,1.1,1.2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="single value column"):
        load_reference_csv(path)


def test_rejects_non_positive_rates(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("date,close\n2024-01-01,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="positive"):
        load_reference_csv(path)
