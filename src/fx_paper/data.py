"""Market-data ingestion for the ECB daily USD-per-EUR reference-rate series."""

from __future__ import annotations

import os
import tempfile
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ECB_CSV_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
ECB_SERIES_KEY = "EXR.D.USD.EUR.SP00.A"


def _validated_series(dates: pd.Series, values: pd.Series, *, source: str) -> pd.DataFrame:
    result = pd.DataFrame(
        {
            "date": pd.to_datetime(dates, errors="coerce", utc=True).dt.tz_localize(None),
            "close": pd.to_numeric(values, errors="coerce"),
        }
    ).dropna(subset=["date", "close"])
    result = result.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    result.index.name = "date"
    if result.empty:
        raise ValueError(f"{source} contains no valid dated rate observations")
    close = result["close"].to_numpy(dtype="float64")
    if (close <= 0).any() or not np.isfinite(close).all():
        raise ValueError("close values must be positive and finite")
    return result[["close"]].astype("float64")


def parse_ecb_csv(text: str) -> pd.DataFrame:
    """Parse the ECB SDMX CSV for EXR.D.USD.EUR.SP00.A into date/close rows."""
    raw = pd.read_csv(StringIO(text), na_values=[".", ""], keep_default_na=True)
    required = {"KEY", "TIME_PERIOD", "OBS_VALUE"}
    if not required.issubset(raw.columns):
        raise ValueError(f"Expected ECB CSV columns {sorted(required)}; got {list(raw.columns)}")
    selected = raw.loc[
        raw["KEY"].astype(str).str.strip() == ECB_SERIES_KEY,
        ["TIME_PERIOD", "OBS_VALUE"],
    ]
    if selected.empty:
        raise ValueError(f"ECB response contained no observations for {ECB_SERIES_KEY}")
    return _validated_series(selected["TIME_PERIOD"], selected["OBS_VALUE"], source="ECB series")


def load_reference_csv(path: str | Path) -> pd.DataFrame:
    """Load the ECB SDMX CSV or a generic date/close CSV into a clean series.

    The result has a unique ascending date index and one positive finite
    ``close`` column. Reference-rate closes are informational, not executable
    quotes or intraday OHLC data.
    """
    source = Path(path)
    frame = pd.read_csv(source, na_values=[".", ""], keep_default_na=True)
    if frame.empty:
        raise ValueError(f"no observations in {source}")
    ecb_columns = {"KEY", "TIME_PERIOD", "OBS_VALUE"}
    if ecb_columns.issubset(frame.columns):
        return parse_ecb_csv(source.read_text(encoding="utf-8"))

    normalized = {str(column).strip().lower(): column for column in frame.columns}
    date_col = next(
        (normalized[key] for key in ("date", "observation_date", "time", "timestamp") if key in normalized),
        None,
    )
    if date_col is None:
        raise ValueError("CSV needs a date, observation_date, time, or timestamp column")
    price_col = next(
        (normalized[key] for key in ("close", "rate", "value") if key in normalized),
        None,
    )
    if price_col is None:
        remaining = [column for column in frame.columns if column != date_col]
        if len(remaining) != 1:
            raise ValueError("CSV needs a close, rate, or single value column")
        price_col = remaining[0]
    return _validated_series(frame[date_col], frame[price_col], source=f"CSV {source}")


def fetch_ecb_reference_rate(
    cache_path: str | Path = "data/cache/ECB_EXR_D_USD_EUR_SP00_A.csv",
    *,
    refresh: bool = False,
    timeout: tuple[float, float] = (5.0, 45.0),
) -> pd.DataFrame:
    """Fetch ECB EXR.D.USD.EUR.SP00.A, or reuse its ignored local CSV cache.

    The unmodified source CSV is kept only in the local cache. Downloads are
    written atomically and validated before replacing an existing cache.
    """
    cache = Path(cache_path)
    if cache.exists() and not refresh:
        return parse_ecb_csv(cache.read_text(encoding="utf-8"))

    response = requests.get(
        ECB_CSV_URL,
        params={"startPeriod": "1999-01-01", "format": "csvdata"},
        headers={"Accept": "text/csv", "User-Agent": "automated-forex-paper-trader/0.2 (public research)"},
        timeout=timeout,
    )
    response.raise_for_status()
    content = response.content
    if not content:
        content = response.text.encode("utf-8")
    parse_ecb_csv(content.decode("utf-8-sig"))

    cache.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{cache.name}.", dir=cache.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        parse_ecb_csv(Path(temporary_name).read_text(encoding="utf-8-sig"))
        os.replace(temporary_name, cache)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return parse_ecb_csv(cache.read_text(encoding="utf-8-sig"))
