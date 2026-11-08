# ECB paper-replay evaluation

## Main result

The full-history replay used the ECB daily USD-per-EUR reference-rate series `EXR.D.USD.EUR.SP00.A`, with 7,131 observations from 1999-01-04 through 2026-11-06. It began with virtual cash of $10,000 and used the project's default paper-only assumptions.

| Strategy | Ending virtual equity | Return | Maximum drawdown | Closed paper trades | Profit factor | Descriptive Sharpe |
|---|---:|---:|---:|---:|---:|---:|
| Walk-forward HistGradientBoosting | $9,745.15 | -2.55% | -5.08% | 813 | 0.942 | -0.12 |
| Zero-return baseline | $10,000.00 | 0.00% | 0.00% | 0 | — | — |

For the model-driven replay, modeled fees were $259.21 and the completed-trade win rate was 50.9%. The 5% drawdown circuit breaker latched on 2004-07-05; the observed close-based drawdown reached 5.08%. Since the breaker is checked at daily closes, a loss can cross the threshold before the simulator can block subsequent entries. No new positions were opened after it latched.

These results are weak and assumption-sensitive. They are not evidence of a predictive or tradable edge, and the zero-return baseline is a no-trade control rather than a comparable investment strategy.

## Replay setup

- **Data:** ECB daily USD-per-EUR reference rate; 7,131 published observations, 1999-01-04 to 2026-11-06. The raw ECB CSV remains in the ignored local cache and is not included in the repository.
- **Forecast:** past-only `HistGradientBoostingRegressor`, at least 300 matured training examples, rolling lookback up to 1,500 observations, refit every 20 observations; 339 model refits.
- **Timing:** a signal is generated after a daily close, a paper order fills at the next observed close, and the position exits at the following observed close.
- **Costs:** assumed 1.2-pip full spread and 0.2-pip slippage per side, plus a 2-basis-point edge buffer. These costs are fixed simulator inputs, not observed ECB or broker prices.
- **Risk controls:** virtual $10,000 starting cash, default 0.25% stress-risk budget, no more than 1x gross leverage, 2% daily-loss block, and 5% drawdown circuit breaker.
- **Baseline:** the zero-return predictor emits no trades, so it remains at virtual $10,000 with no modeled fees.

The replay is chronological and model fits use past information only, but it is a full-history experiment—not a pre-registered untouched validation period. No strategy parameters were selected from an independent holdout in this report.

## Limits and safety

ECB rates are informational reference values, not executable bid/ask or OHLC market data; the ECB discourages their use for transactions. The simulator does not model real fills, intraday paths, variable spreads, market impact, liquidity, financing, swaps, outages, or broker rejection. Daily-close risk checks can overshoot their configured threshold. The results are historical simulation artifacts, not financial advice or a guarantee about future returns.

This repository remains paper-only: it has no live broker adapter, real account connection, trading credential, or live-money order path. Row-level paper trades, equity curves, logs, and source observations stay local and are excluded from Git; this public report contains aggregate derived metrics only. See [Data Source Notes](data-sources.md) for attribution and reuse details.
