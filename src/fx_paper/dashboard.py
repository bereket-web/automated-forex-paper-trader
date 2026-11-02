"""Generate a dependency-light, self-contained HTML dashboard from run artifacts."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _svg_line(values: list[float], *, color: str, label: str, zero_line: bool = False) -> str:
    width, height, pad = 900, 250, 30
    if not values:
        return '<svg viewBox="0 0 900 250" role="img"><text x="30" y="120">No data yet — run a simulation.</text></svg>'
    low, high = min(values), max(values)
    if high == low:
        high = low + 1.0
    points = []
    for index, value in enumerate(values):
        x = pad + index * (width - 2 * pad) / max(1, len(values) - 1)
        y = height - pad - (value - low) * (height - 2 * pad) / (high - low)
        points.append(f"{x:.1f},{y:.1f}")
    zero = ""
    if zero_line and low < 0 < high:
        y0 = height - pad - (0 - low) * (height - 2 * pad) / (high - low)
        zero = f'<line x1="{pad}" x2="{width-pad}" y1="{y0:.1f}" y2="{y0:.1f}" stroke="#60718a" stroke-dasharray="5 5" />'
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(label)}">'
        f'<line x1="{pad}" x2="{width-pad}" y1="{height-pad}" y2="{height-pad}" stroke="#334155" />'
        f"{zero}<polyline fill=\"none\" stroke=\"{color}\" stroke-width=\"3\" points=\"{' '.join(points)}\" />"
        f'<text x="{pad}" y="18" fill="#9fb0c4" font-size="12">{low:.2%}</text>'
        f'<text x="{width-pad}" y="18" text-anchor="end" fill="#9fb0c4" font-size="12">{high:.2%}</text>'
        "</svg>"
    )


def _number(summary: dict[str, Any], name: str, suffix: str = "") -> str:
    value = summary.get(name)
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        return f"{value:,.2f}{suffix}"
    return html.escape(str(value))


def generate_dashboard(
    summary_path: str | Path,
    equity_path: str | Path,
    trades_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Create an offline-readable HTML dashboard from a completed simulation."""
    summary_file, equity_file, trades_file, output_file = map(Path, (summary_path, equity_path, trades_path, output_path))
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    equity_rows = _read_csv(equity_file)
    trade_rows = _read_csv(trades_file)
    equity = [float(row["equity_usd"]) for row in equity_rows if row.get("equity_usd")]
    drawdown = [float(row["drawdown_fraction"]) for row in equity_rows if row.get("drawdown_fraction")]
    trades_html = "".join(
        "<tr>" + "".join(
            f"<td>{html.escape(row.get(key, ''))}</td>"
            for key in ("entry_date", "exit_date", "side", "units_eur", "net_pnl_usd")
        ) + "</tr>"
        for row in reversed(trade_rows[-15:])
    ) or '<tr><td colspan="5">No completed paper trades.</td></tr>'
    warning = html.escape(str(summary.get("warning", "Paper-only research output.")))
    period = html.escape(f"{summary.get('period_start') or '—'} — {summary.get('period_end') or '—'}")
    sharpe = summary.get("descriptive_sharpe_ratio")
    sharpe_display = "—" if sharpe is None else f"{float(sharpe):.2f}"
    breaker_date = summary.get("drawdown_circuit_breaker_date")
    breaker_display = html.escape(str(breaker_date)[:10]) if breaker_date else "Not triggered"
    html_text = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FX Paper Trader — Performance</title><style>
:root{{color-scheme:dark;--bg:#0b1220;--panel:#111c2e;--line:#263751;--muted:#9fb0c4;--text:#edf4fb;--green:#39d3a3;--blue:#6aa9ff;--red:#ff7d83}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(ellipse at top,#16243a,var(--bg) 55%);color:var(--text);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1120px;margin:0 auto;padding:32px 20px 60px}}h1{{font-size:clamp(1.8rem,5vw,2.8rem);margin:0}}.subtitle,.muted{{color:var(--muted)}}.badge{{display:inline-block;border:1px solid #3e5d7a;border-radius:99px;padding:4px 10px;color:#b9d6ff;font-size:12px;letter-spacing:.08em;text-transform:uppercase}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:24px 0}}.card,.panel{{background:rgba(17,28,46,.94);border:1px solid var(--line);border-radius:14px;padding:18px}}.label{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em}}.value{{font-size:1.55rem;font-weight:700;margin-top:5px}}.panel{{margin:14px 0}}.charts{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}svg{{width:100%;height:auto;display:block}}table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}th,td{{padding:9px 8px;border-bottom:1px solid var(--line);text-align:left;font-size:13px}}th{{color:var(--muted);font-weight:600}}.table-wrap{{overflow:auto}}.notice{{border-left:3px solid #e4b55a;color:#e6d7b4;padding:12px 14px;background:#251e11;border-radius:4px}}@media(max-width:720px){{.charts{{grid-template-columns:1fr}}main{{padding:22px 14px 48px}}.card,.panel{{padding:14px}}}}
</style></head><body><main>
<span class="badge">SIMULATION ONLY · NO BROKER</span><h1>EUR/USD Paper Trader</h1>
<p class="subtitle">Walk-forward model: <strong>{html.escape(str(summary.get('model','—')))}</strong> · {period}</p>
<div class="grid">
<div class="card"><div class="label">Virtual equity</div><div class="value">${_number(summary,'ending_virtual_equity_usd')}</div></div>
<div class="card"><div class="label">Total return</div><div class="value">{_number(summary,'total_return_percent','%')}</div></div>
<div class="card"><div class="label">Max drawdown</div><div class="value">{_number(summary,'max_drawdown_percent','%')}</div></div>
<div class="card"><div class="label">Closed trades</div><div class="value">{_number(summary,'closed_trades')}</div></div>
<div class="card"><div class="label">Win rate</div><div class="value">{_number(summary,'win_rate_percent','%')}</div></div>
<div class="card"><div class="label">Descriptive Sharpe</div><div class="value">{sharpe_display}</div></div>
<div class="card"><div class="label">Simulated costs</div><div class="value">${_number(summary,'simulated_fees_usd')}</div></div>
<div class="card"><div class="label">Peak gross leverage</div><div class="value">{_number(summary,'peak_gross_leverage','×')}</div></div>
<div class="card"><div class="label">Drawdown breaker</div><div class="value">{breaker_display}</div></div>
</div>
<div class="charts"><section class="panel"><h2>Virtual equity</h2>{_svg_line(equity,color='#39d3a3',label='Virtual equity')}</section>
<section class="panel"><h2>Drawdown</h2>{_svg_line(drawdown,color='#ff7d83',label='Drawdown',zero_line=True)}</section></div>
<section class="panel"><h2>Recent paper trades</h2><div class="table-wrap"><table><thead><tr><th>Entry</th><th>Exit</th><th>Side</th><th>EUR units</th><th>Net P/L (USD)</th></tr></thead><tbody>{trades_html}</tbody></table></div></section>
<p class="notice">{warning}</p><p class="muted">Reference-rate closes, assumed spread/slippage, a one-close delayed fill and one-observation holding period. Results are historical simulation artifacts, not live prices, financial advice, or evidence of future profitability.</p>
</main></body></html>"""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(html_text, encoding="utf-8")
    return output_file
