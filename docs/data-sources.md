# Data source

The default input is the public Federal Reserve H.10 EUR/USD reference-rate series `DEXUSEU`, retrieved through FRED. It records U.S. dollars per euro at a daily New York noon reference time. It is not a bid/ask quote or intraday OHLC market feed. The source page warns that graph data are copyrighted; users should review current source terms before redistribution. This project caches downloaded observations locally and ignores the cache and row-level reports in Git.

The simulator models a configurable fixed spread and per-side slippage only to exercise its paper-order pipeline. Those values are assumptions, not live-market observations or broker data. Do not interpret their use as evidence that a trade could have been executed at those prices.
