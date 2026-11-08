from __future__ import annotations

import pandas as pd
import pytest

from fx_paper.data import fetch_ecb_reference_rate, load_reference_csv, parse_ecb_csv

ECB_CSV = (
    "KEY,TIME_PERIOD,OBS_VALUE\n"
    "EXR.D.USD.EUR.SP00.A,2024-01-03,1.10\n"
    "EXR.D.USD.EUR.SP00.A,2024-01-02,1.09\n"
    "EXR.D.GBP.EUR.SP00.A,2024-01-02,0.86\n"
)


def test_parse_ecb_series_filters_key_sorts_dates_and_keeps_usd_per_eur():
    prices = parse_ecb_csv(ECB_CSV)
    assert list(prices.columns) == ["close"]
    assert list(prices["close"]) == [1.09, 1.10]
    assert prices.index.is_monotonic_increasing
    assert prices.index.name == "date"


def test_parse_ecb_series_rejects_missing_requested_key():
    with pytest.raises(ValueError, match="no observations"):
        parse_ecb_csv("KEY,TIME_PERIOD,OBS_VALUE\nEXR.D.GBP.EUR.SP00.A,2024-01-02,0.86\n")


def test_loads_ecb_sdmx_csv_from_path(tmp_path):
    path = tmp_path / "ecb.csv"
    path.write_text(ECB_CSV, encoding="utf-8")
    prices = load_reference_csv(path)
    assert len(prices) == 2
    assert prices.iloc[-1, 0] == pytest.approx(1.10)


def test_fetches_and_caches_ecb_csv_atomically(tmp_path, monkeypatch):
    class FakeResponse:
        content = ECB_CSV.encode("utf-8")
        text = ECB_CSV

        @staticmethod
        def raise_for_status():
            return None

    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr("fx_paper.data.requests.get", fake_get)
    cache = tmp_path / "cache" / "ecb.csv"
    prices = fetch_ecb_reference_rate(cache)
    assert len(prices) == 2
    assert cache.read_text(encoding="utf-8") == ECB_CSV
    assert calls[0][1]["params"] == {"startPeriod": "1999-01-01", "format": "csvdata"}
    assert "data-api.ecb.europa.eu" in calls[0][0]

    monkeypatch.setattr(
        "fx_paper.data.requests.get",
        lambda *_args, **_kwargs: pytest.fail("cached fetch should not call the network"),
    )
    cached = fetch_ecb_reference_rate(cache)
    pd.testing.assert_frame_equal(cached, prices)


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
