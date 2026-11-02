"""Market-data ingestion for the public FRED EUR/USD reference-rate series."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXUSEU"


def load_reference_csv(path: str | Path) -> pd.DataFrame:
    """Load a date/close CSV, including FRED's observation_date,DEXUSEU format.

    The output is a clean DataFrame indexed by unique, ascending dates with one
    positive finite ``close`` column. This is a daily reference rate, not OHLC
    data or an executable quote stream.
    """
    source = Path(path)
    frame = pd.read_csv(source)
    if frame.empty:
        raise ValueError(f"no observations in {source}")
    normalized = {str(column).strip().lower(): column for column in frame.columns}
    date_col = next(
        (normalized[key] for key in ("date", "observation_date", "time", "timestamp") if key in normalized),
        None,
    )
    if date_col is None:
        raise ValueError("CSV needs a date, observation_date, time, or timestamp column")
    price_col = next(
        (normalized[key] for key in ("close", "dexuseu", "rate", "value") if key in normalized),
        None,
    )
    if price_col is None:
        remaining = [column for column in frame.columns if column != date_col]
        if len(remaining) != 1:
            raise ValueError("CSV needs a close, DEXUSEU, rate, or single value column")
        price_col = remaining[0]

    result = pd.DataFrame(
        {
            "date": pd.to_datetime(frame[date_col], errors="coerce", utc=True).dt.tz_localize(None),
            "close": pd.to_numeric(frame[price_col].replace(".", pd.NA), errors="coerce"),
        }
    ).dropna()
    result = result.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    result.index.name = "date"
    if result.empty:
        raise ValueError("CSV contains no valid dated price observations")
    if (result["close"] <= 0).any() or not np.isfinite(result["close"].to_numpy()).all():
        raise ValueError("close values must be positive and finite")
    return result.astype({"close": "float64"})


def fetch_fred_reference_rate(
    cache_path: str | Path = "data/cache/DEXUSEU.csv",
    *,
    refresh: bool = False,
    timeout: tuple[float, float] = (5.0, 30.0),
) -> pd.DataFrame:
    """Fetch FRED's public DEXUSEU CSV, or reuse the ignored local cache.

    No API key, broker connection, or account credential is used. Downloads are
    written atomically so an interrupted request cannot corrupt an old cache.
    """
    cache = Path(cache_path)
    if cache.exists() and not refresh:
        return load_reference_csv(cache)
    response = requests.get(
        FRED_CSV_URL,
        headers={"User-Agent": "fx-paper-research/0.1 (public daily data)"},
        timeout=timeout,
    )
    response.raise_for_status()
    cache.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{cache.name}.", dir=cache.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(response.content)
            output.flush()
            os.fsync(output.fileno())
        # Validate before replacing a previously good cache.
        load_reference_csv(temporary_name)
        os.replace(temporary_name, cache)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return load_reference_csv(cache)
