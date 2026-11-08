# Data source and reuse notes

## ECB daily USD-per-EUR reference rate

The default input is the European Central Bank's daily euro foreign exchange reference rate for the U.S. dollar, series `EXR.D.USD.EUR.SP00.A`. EUR is the base currency and the published value is U.S. dollars per one euro; the project does not invert the observations.

- [ECB Statistics Exchange Rates series](https://data.ecb.europa.eu/data/datasets/EXR/EXR.D.USD.EUR.SP00.A)
- [ECB SDMX CSV endpoint](https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?startPeriod=1999-01-01&format=csvdata)
- The local cache is `data/cache/ECB_EXR_D_USD_EUR_SP00_A.csv` and is excluded from Git.

The ECB's [reuse policy for ESCB statistics](https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html) permits reuse of publicly available statistics with source attribution, provided the statistics and metadata are not modified; third-party data may have separate terms. The repository includes only aggregate calculations derived from the series, not the source CSV or row-level simulation outputs. Derived returns and paper-trading metrics are explicitly identified as calculations based on ECB data.

Suggested attribution: “Source: European Central Bank (ECB), daily euro foreign exchange reference rate for USD, series EXR.D.USD.EUR.SP00.A; retrieved 2026-11-08. Derived calculations by Automated Forex Paper Trader.”

## Important interpretation

ECB reference rates are informational. The ECB strongly discourages their use for transaction purposes. They are not executable broker bid/ask prices and contain no intraday high/low path, spread, fill, liquidity, or financing information. The simulator adds fixed assumed spread and slippage only to exercise a paper-order pipeline; those values are not observed or calibrated market costs.

All public results are paper simulations. No broker adapter, real account, live order path, or credentials are included.
