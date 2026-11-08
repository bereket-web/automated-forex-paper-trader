# Automated Forex Paper Trader

A local-only research system that turns a walk-forward EUR/USD return forecast into cost-aware **simulated** orders, checks each order against conservative risk limits, tracks a virtual account, and produces an offline performance dashboard.

> **Paper simulation only. No live-money trading.** This project has no broker adapter, broker URL, account credentials, real order submission, or unattended broker loop. A run never contacts a trading account. Nothing here is financial advice, and a historical simulation does not establish a profitable strategy.

## Why this project is cautious

The portfolio's [Forex Prediction Engine (Project 09)](https://github.com/bereket-web/forex-prediction-engine) evaluates the same ECB USD-per-EUR reference-rate series and found that neither its supervised models beat the zero-change forecast baseline on pooled out-of-sample forecast error. Project 10 therefore compares its paper strategy with an explicit no-trade baseline, requires a signal to clear modeled costs plus an edge buffer, caps gross leverage at 1x, and defaults to a 0.25% per-trade stress-risk budget.

The latest ECB full-history replay was weak: the model-driven paper account ended at $9,745.15 from $10,000 (-2.55%), with a 5.08% maximum close-based drawdown; its 5% breaker latched in 2004. The zero-return baseline did not trade and remained flat. These are assumption-sensitive historical simulation results, not evidence of an edge. See the full [ECB replay evaluation](docs/evaluation.md).

## What it demonstrates

- **Market data:** retrieves or reuses the ECB daily euro foreign exchange reference rate for USD, series `EXR.D.USD.EUR.SP00.A`, quoted as USD per EUR. It also accepts a local date/close CSV. ECB reference rates are informational, not executable bid/ask or intraday OHLC data.
- **Prediction:** a compact scikit-learn histogram-gradient-boosting regressor refit on an expanding/rolling past-only window, plus a zero-return baseline. Labels are eligible only after their exit close is observed.
- **Strategy:** long / short / no-trade decisions require predicted return to clear assumed round-trip spread and slippage plus a configurable buffer.
- **Execution:** local-only paper orders are scheduled at a signal close and filled at the next observed close. A trade exits at the following observed close, so the forecast target begins after the delayed entry.
- **Risk:** virtual USD 10,000 starting balance; 0.25% default stress-move budget; position sizing uses a volatility stress move; no more than 1x gross leverage; 2% daily loss block; 5% peak-to-trough drawdown circuit breaker. Since the close-only source has no intraday stop data, a stress move is a sizing assumption—not a guaranteed stop order.
- **Audit trail and dashboard:** paper trades, equity, and decision/order/fill/block/closure events are written locally. A self-contained responsive HTML dashboard shows virtual equity, drawdown, trade statistics, modeled fees, and recent paper trades.

## Quick start

Python 3.10+ is required. Install the project and test extras:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest
ruff check .
```

Or use the checked-in `uv.lock`:

```bash
uv sync --extra test
uv run pytest
uv run ruff check .
```

Fetch or refresh the ECB series and run the full walk-forward paper replay:

```bash
uv run fx-paper ingest --refresh
uv run fx-paper simulate --model histgb --refresh
```

Run the explicit zero-return baseline (normally no trades):

```bash
uv run fx-paper simulate --model zero
```

You can provide your own CSV with `date,close` columns:

```bash
uv run fx-paper simulate --data /path/to/daily_close.csv --model histgb
```

The default output files are `results/metrics.json`, `results/equity_curve.csv`, `results/trades.csv`, and `results/dashboard.html`; detailed JSONL decision and paper-order events are written to `logs/`. These source and row-level outputs are ignored by Git and remain local. `--refresh` refreshes the ECB cache; `--max-bars 1200` can bound a quick smoke run. Use `fx-paper simulate --help` for configurable modeling, costs, and risk limits.

Open `results/dashboard.html` locally in a browser. No account, API key, broker token, or `.env` file is needed.

## Evaluation and interpretation

The current full-history replay uses 7,131 ECB observations from 1999-01-04 through 2026-11-06. With the default HistGradientBoosting model, the simulation closed 813 paper trades, recorded a 0.942 profit factor and -0.12 descriptive Sharpe, and ended at $9,745.15 (-2.55%). Its close-based drawdown reached -5.08%; the 5% breaker latched on 2004-07-05. The no-trade zero-return baseline remained at $10,000 with no trades or fees.

The simulation uses fixed assumed transaction costs: 1.2 pips full spread plus 0.2 pips slippage per side. Costs are not measured from market data. The full-period result is not an untouched independent validation and should not be used to tune a strategy and then claim independent performance. The close-based drawdown breaker may be exceeded before the next daily observation. See [Evaluation](docs/evaluation.md) for the full metrics, setup, and caveats.

## Data provenance

The default series is the [ECB daily USD-per-EUR reference rate](https://data.ecb.europa.eu/data/datasets/EXR/EXR.D.USD.EUR.SP00.A), `EXR.D.USD.EUR.SP00.A`, retrieved through the ECB SDMX API. The local unmodified CSV cache is excluded from version control. The public repository includes only aggregate derived metrics, not source observations or row-level trades. See [Data Source Notes](docs/data-sources.md) for the ECB reuse and attribution policy.

## Architecture

![Paper trader architecture](docs/architecture.png)

The paper ledger is deliberately the terminal execution boundary. No broker client, live endpoint, authentication secret, or path from a forecast to a real account is included.

## Limitations

ECB reference rates are informational, not executable market prices. The simulator assumes fixed spread and slippage, uses one-observation holds, and omits intraday high/low paths, actual fills, gaps, financing, swaps, liquidity, market impact, broker rejections, outages, taxes, and changing spreads. Its assumed costs are not empirically calibrated. Risk limits are simulation controls, not a guarantee against loss. Forecasts may be wrong, unstable, or worthless out of sample; a paper result is not evidence of future profitability.

## License

The software is MIT-licensed. That license does not grant rights beyond those in the ECB's data reuse policy; see [Data Source Notes](docs/data-sources.md).
