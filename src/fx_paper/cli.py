"""Command-line interface for ingestion and local-only paper simulation."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from fx_paper.dashboard import generate_dashboard
from fx_paper.data import fetch_ecb_reference_rate, load_reference_csv
from fx_paper.engine import PaperConfig, run_paper_simulation
from fx_paper.model import WalkForwardForecaster
from fx_paper.risk import RiskConfig

DEFAULT_CACHE = Path("data/cache/ECB_EXR_D_USD_EUR_SP00_A.csv")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fx-paper", description="Broker-free EUR/USD paper-trading research simulator")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="download or refresh ECB EXR.D.USD.EUR.SP00.A daily closes")
    ingest.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ingest.add_argument("--refresh", action="store_true")

    simulate = commands.add_parser("simulate", aliases=["paper"], help="run a walk-forward local paper simulation")
    simulate.add_argument("--data", type=Path, default=DEFAULT_CACHE, help="date/close CSV; defaults to the ECB USD-per-EUR cache")
    simulate.add_argument("--refresh", action="store_true", help="refresh ECB only when using the default cache")
    simulate.add_argument("--model", choices=("histgb", "zero"), default="histgb")
    simulate.add_argument("--min-train", type=int, default=300)
    simulate.add_argument("--lookback", type=int, default=1500)
    simulate.add_argument("--retrain-every", type=int, default=20)
    simulate.add_argument("--initial-cash", type=float, default=10_000.0)
    simulate.add_argument("--risk-fraction", type=float, default=0.0025)
    simulate.add_argument("--max-leverage", type=float, default=1.0)
    simulate.add_argument("--daily-loss-limit", type=float, default=0.02)
    simulate.add_argument("--max-drawdown-limit", type=float, default=0.05)
    simulate.add_argument("--spread-pips", type=float, default=1.2)
    simulate.add_argument("--slippage-pips", type=float, default=0.2)
    simulate.add_argument("--extra-edge-bps", type=float, default=2.0)
    simulate.add_argument("--max-bars", type=int, default=None, help="optional final-N-observation bound for a quick smoke run")
    simulate.add_argument("--output", type=Path, default=Path("results"))
    simulate.add_argument("--logs", type=Path, default=Path("logs"))
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "ingest":
        data = fetch_ecb_reference_rate(args.cache, refresh=args.refresh)
        print(json.dumps({"rows": len(data), "start": str(data.index.min().date()), "end": str(data.index.max().date()), "cache": str(args.cache)}, indent=2))
        print("Source: ECB EXR.D.USD.EUR.SP00.A daily USD-per-EUR reference rate; not executable bid/ask data.")
        return

    if args.data == DEFAULT_CACHE:
        prices = fetch_ecb_reference_rate(args.data, refresh=args.refresh)
    else:
        if not args.data.exists():
            raise SystemExit(f"input CSV not found: {args.data}")
        prices = load_reference_csv(args.data)
    if args.max_bars is not None:
        if args.max_bars < 3:
            raise SystemExit("--max-bars must be at least 3")
        prices = prices.iloc[-args.max_bars :]

    risk = RiskConfig(
        risk_fraction=args.risk_fraction,
        max_leverage=args.max_leverage,
        daily_loss_limit=args.daily_loss_limit,
        max_drawdown_limit=args.max_drawdown_limit,
    )
    config = PaperConfig(
        initial_cash=args.initial_cash,
        spread_pips=args.spread_pips,
        slippage_pips_per_side=args.slippage_pips,
        extra_edge_bps=args.extra_edge_bps,
        risk=risk,
    )
    forecaster = WalkForwardForecaster(
        model_kind=args.model,
        min_train=args.min_train,
        lookback=args.lookback,
        retrain_every=args.retrain_every,
    )
    result = run_paper_simulation(prices, forecaster=forecaster, config=config)
    args.output.mkdir(parents=True, exist_ok=True)
    result.equity.to_csv(args.output / "equity_curve.csv", index=False)
    result.trades.to_csv(args.output / "trades.csv", index=False)
    (args.output / "metrics.json").write_text(json.dumps(result.metrics, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    args.logs.mkdir(parents=True, exist_ok=True)
    with (args.logs / f"paper_{run_id}.jsonl").open("w", encoding="utf-8") as log:
        for event in result.events:
            log.write(json.dumps(event, allow_nan=False) + "\n")
    dashboard = generate_dashboard(
        args.output / "metrics.json",
        args.output / "equity_curve.csv",
        args.output / "trades.csv",
        args.output / "dashboard.html",
    )
    print(json.dumps(result.metrics, indent=2, allow_nan=False))
    print(f"Dashboard: {dashboard.resolve()}")
    print(f"Event log: {(args.logs / f'paper_{run_id}.jsonl').resolve()}")
    print("Paper-only simulation completed. No broker, live account, or real order was contacted.")


if __name__ == "__main__":
    main()
