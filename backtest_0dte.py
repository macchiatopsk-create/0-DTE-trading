#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
0DTE options backtester using actual historical option minute aggregates.

Data:
- Massive/Polygon-compatible REST API
- Underlying minute aggregates
- Same-day-expiry option minute aggregates

Default strategy:
- 30-minute opening range (09:30-10:00 ET)
- First 5-minute close above OR high + above session VWAP => buy CALL
- First 5-minute close below OR low + below session VWAP => buy PUT
- Enter on first available option 1-minute bar after the trigger
- Budget-aware strike: starts 1 strike OTM, then moves farther OTM until affordable
- Exit: +60% take-profit, -35% stop, or 15:45 ET
- One trade per ticker per day, no re-entry

Important:
Minute aggregates are based on qualifying trades, not historical bid/ask quotes.
Fills are therefore modeled conservatively with configurable slippage.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import pandas as pd
import requests
from zoneinfo import ZoneInfo


NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
API_BASE = "https://api.massive.com"
DEFAULT_CONFIG = "config.json"


@dataclass
class Config:
    underlyings: list[str]
    starting_capital: float
    lookback_calendar_days: int
    opening_range_minutes: int
    entry_cutoff: str
    time_exit: str
    take_profit_pct: float
    stop_loss_pct: float
    option_slippage_pct: float
    commission_per_contract_each_side: float
    max_position_pct: float
    max_contracts: int
    first_otm_offset: int
    max_otm_offset: int
    min_option_price: float
    min_entry_bar_volume: int
    api_min_interval_seconds: float
    cache_dir: str
    output_dir: str

    @classmethod
    def from_file(cls, path: str | Path) -> "Config":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**raw)


@dataclass
class Trigger:
    trading_date: str
    underlying: str
    direction: str
    trigger_time: str
    decision_ts_ms: int
    underlying_price: float
    or_high: float
    or_low: float
    vwap: float
    breakout_strength_pct: float


@dataclass
class Trade:
    trading_date: str
    underlying: str
    direction: str
    option_ticker: str
    expiration: str
    strike: float
    strike_offset: int
    trigger_time: str
    underlying_entry_price: float
    or_high: float
    or_low: float
    vwap: float
    option_entry_time: str
    option_entry_raw: float
    option_entry_fill: float
    contracts: int
    capital_before: float
    invested: float
    stop_price: float
    target_price: float
    option_exit_time: str
    option_exit_raw: float
    option_exit_fill: float
    exit_reason: str
    gross_pnl: float
    fees: float
    net_pnl: float
    trade_return_pct: float
    account_return_pct: float
    capital_after: float
    max_favorable_pct: float
    max_adverse_pct: float


class MassiveClient:
    def __init__(self, api_key: str, min_interval_seconds: float, cache_dir: str | Path):
        if not api_key:
            raise ValueError("MASSIVE_API_KEY is missing")
        self.api_key = api_key
        self.min_interval = max(0.0, float(min_interval_seconds))
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self._last_call = 0.0

    def _cache_path(self, endpoint: str, params: dict[str, Any]) -> Path:
        key = endpoint + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_call
        wait = self.min_interval - elapsed
        if wait > 0:
            time.sleep(wait)

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(params or {})
        params["apiKey"] = self.api_key
        cache_path = self._cache_path(endpoint, params)
        if cache_path.exists():
            try:
                return json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:
                cache_path.unlink(missing_ok=True)

        self._wait()
        url = API_BASE + endpoint
        response = self.session.get(url, params=params, timeout=60)
        self._last_call = time.monotonic()

        if response.status_code in {429, 500, 502, 503, 504}:
            retry_after = float(response.headers.get("Retry-After", "15"))
            time.sleep(max(retry_after, self.min_interval, 15.0))
            response = self.session.get(url, params=params, timeout=60)
            self._last_call = time.monotonic()

        if response.status_code == 403:
            raise RuntimeError(
                f"API access denied for {endpoint}. "
                "Confirm the Massive Stocks Basic and Options Basic entitlements are enabled."
            )
        response.raise_for_status()
        payload = response.json()
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def aggregate_bars(
        self,
        ticker: str,
        multiplier: int,
        timespan: str,
        start_date: str,
        end_date: str,
        limit: int = 50000,
    ) -> pd.DataFrame:
        safe_ticker = quote(ticker, safe=":")
        endpoint = (
            f"/v2/aggs/ticker/{safe_ticker}/range/"
            f"{multiplier}/{timespan}/{start_date}/{end_date}"
        )
        payload = self.get(
            endpoint,
            {"adjusted": "true", "sort": "asc", "limit": limit},
        )
        rows = payload.get("results") or []
        if not rows:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "vwap"])
        frame = pd.DataFrame(rows).rename(
            columns={"t": "timestamp", "o": "open", "h": "high", "l": "low",
                     "c": "close", "v": "volume", "vw": "vwap"}
        )
        for col in ["open", "high", "low", "close", "volume", "vwap", "timestamp"]:
            if col not in frame:
                frame[col] = None
        frame["dt_utc"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
        frame["dt_et"] = frame["dt_utc"].dt.tz_convert(NY)
        frame["date"] = frame["dt_et"].dt.strftime("%Y-%m-%d")
        frame["time"] = frame["dt_et"].dt.strftime("%H:%M")
        return frame[["timestamp", "dt_utc", "dt_et", "date", "time",
                      "open", "high", "low", "close", "volume", "vwap"]]


def parse_hhmm(value: str) -> int:
    hh, mm = value.split(":")
    return int(hh) * 60 + int(mm)


def minute_of_day(series: pd.Series) -> pd.Series:
    return series.dt.hour * 60 + series.dt.minute


def regular_session(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    mins = minute_of_day(frame["dt_et"])
    return frame[(mins >= 570) & (mins < 960)].copy()


def resample_to_5m(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    f = frame.set_index("dt_et").sort_index()
    out = (
        f.resample("5min", label="left", closed="left")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )
    out["date"] = out["dt_et"].dt.strftime("%Y-%m-%d")
    out["time"] = out["dt_et"].dt.strftime("%H:%M")
    return out


def add_session_vwap(frame: pd.DataFrame) -> pd.DataFrame:
    f = frame.copy()
    typical = (f["high"] + f["low"] + f["close"]) / 3.0
    vol = f["volume"].fillna(0).astype(float)
    cumulative_volume = vol.cumsum()
    cumulative_pv = (typical * vol).cumsum()
    fallback = f["close"].expanding().mean()
    f["session_vwap"] = (cumulative_pv / cumulative_volume.replace(0, math.nan)).fillna(fallback)
    return f


def find_opening_range_trigger(
    day_1m: pd.DataFrame,
    ticker: str,
    opening_range_minutes: int,
    entry_cutoff: str,
) -> Trigger | None:
    day = regular_session(day_1m)
    if day.empty:
        return None
    day = add_session_vwap(day)
    bars = resample_to_5m(day)
    if bars.empty:
        return None

    open_min = 570
    or_end = open_min + opening_range_minutes
    cutoff_min = parse_hhmm(entry_cutoff)
    bar_min = minute_of_day(bars["dt_et"])
    or_bars = bars[(bar_min >= open_min) & (bar_min < or_end)]
    if or_bars.empty:
        return None

    or_high = float(or_bars["high"].max())
    or_low = float(or_bars["low"].min())
    vwap_by_ts = day.set_index("dt_et")["session_vwap"].sort_index()

    candidates = bars[(bar_min >= or_end) & (bar_min <= cutoff_min)].copy()
    for _, bar in candidates.iterrows():
        decision_time = bar["dt_et"] + pd.Timedelta(minutes=5)
        available_vwap = vwap_by_ts.loc[:decision_time]
        if available_vwap.empty:
            continue
        vwap = float(available_vwap.iloc[-1])
        close = float(bar["close"])
        if close > or_high and close > vwap:
            return Trigger(
                trading_date=str(bar["date"]), underlying=ticker, direction="CALL",
                trigger_time=decision_time.strftime("%H:%M"),
                decision_ts_ms=int(decision_time.tz_convert(UTC).timestamp() * 1000),
                underlying_price=close, or_high=or_high, or_low=or_low, vwap=vwap,
                breakout_strength_pct=(close / or_high - 1.0) * 100.0,
            )
        if close < or_low and close < vwap:
            return Trigger(
                trading_date=str(bar["date"]), underlying=ticker, direction="PUT",
                trigger_time=decision_time.strftime("%H:%M"),
                decision_ts_ms=int(decision_time.tz_convert(UTC).timestamp() * 1000),
                underlying_price=close, or_high=or_high, or_low=or_low, vwap=vwap,
                breakout_strength_pct=(or_low / close - 1.0) * 100.0,
            )
    return None


def occ_option_ticker(underlying: str, expiration: str, right: str, strike: float) -> str:
    exp = datetime.strptime(expiration, "%Y-%m-%d").strftime("%y%m%d")
    strike_code = f"{int(round(strike * 1000)):08d}"
    cp = "C" if right.upper() == "CALL" else "P"
    return f"O:{underlying.upper()}{exp}{cp}{strike_code}"


def candidate_strikes(spot: float, direction: str, first_otm: int, max_otm: int) -> list[tuple[float, int]]:
    if direction == "CALL":
        anchor = math.ceil(spot)
        return [(float(anchor + (offset - 1)), offset) for offset in range(first_otm, max_otm + 1)]
    anchor = math.floor(spot)
    return [(float(anchor - (offset - 1)), offset) for offset in range(first_otm, max_otm + 1)]


def first_bar_at_or_after(frame: pd.DataFrame, ts_ms: int) -> pd.Series | None:
    if frame.empty:
        return None
    subset = frame[frame["timestamp"] >= ts_ms]
    return None if subset.empty else subset.iloc[0]


def choose_contract(
    client: MassiveClient,
    cfg: Config,
    trigger: Trigger,
    capital: float,
) -> tuple[str, float, int, pd.DataFrame, pd.Series, int] | None:
    max_cash = capital * cfg.max_position_pct
    for strike, offset in candidate_strikes(
        trigger.underlying_price, trigger.direction, cfg.first_otm_offset, cfg.max_otm_offset
    ):
        option_ticker = occ_option_ticker(
            trigger.underlying, trigger.trading_date, trigger.direction, strike
        )
        bars = client.aggregate_bars(
            option_ticker, 1, "minute", trigger.trading_date, trigger.trading_date
        )
        bars = regular_session(bars)
        entry_bar = first_bar_at_or_after(bars, trigger.decision_ts_ms)
        if entry_bar is None:
            continue
        raw_price = float(entry_bar["open"] if pd.notna(entry_bar["open"]) else entry_bar["close"])
        if raw_price < cfg.min_option_price:
            continue
        if int(entry_bar.get("volume", 0) or 0) < cfg.min_entry_bar_volume:
            continue
        fill = raw_price * (1.0 + cfg.option_slippage_pct)
        cost_per_contract = fill * 100.0 + 2.0 * cfg.commission_per_contract_each_side
        contracts = min(cfg.max_contracts, int(max_cash // cost_per_contract))
        if contracts >= 1:
            return option_ticker, strike, offset, bars, entry_bar, contracts
    return None


def simulate_trade(
    cfg: Config,
    trigger: Trigger,
    capital: float,
    option_ticker: str,
    strike: float,
    strike_offset: int,
    option_bars: pd.DataFrame,
    entry_bar: pd.Series,
    contracts: int,
) -> Trade:
    raw_entry = float(entry_bar["open"] if pd.notna(entry_bar["open"]) else entry_bar["close"])
    entry_fill = raw_entry * (1.0 + cfg.option_slippage_pct)
    stop = entry_fill * (1.0 - cfg.stop_loss_pct)
    target = entry_fill * (1.0 + cfg.take_profit_pct)

    entry_ts = int(entry_bar["timestamp"])
    exit_cutoff = parse_hhmm(cfg.time_exit)
    scan = option_bars[option_bars["timestamp"] >= entry_ts].copy()
    scan = scan[minute_of_day(scan["dt_et"]) <= exit_cutoff]

    exit_reason = "TIME"
    exit_raw = float(scan.iloc[-1]["close"]) if not scan.empty else raw_entry
    exit_time = scan.iloc[-1]["dt_et"] if not scan.empty else entry_bar["dt_et"]
    max_high = raw_entry
    min_low = raw_entry

    for _, bar in scan.iterrows():
        high = float(bar["high"])
        low = float(bar["low"])
        max_high = max(max_high, high)
        min_low = min(min_low, low)
        stop_hit = low <= stop
        target_hit = high >= target
        if stop_hit and target_hit:
            exit_reason, exit_raw, exit_time = "STOP_SAME_BAR", stop, bar["dt_et"]
            break
        if stop_hit:
            exit_reason, exit_raw, exit_time = "STOP", stop, bar["dt_et"]
            break
        if target_hit:
            exit_reason, exit_raw, exit_time = "TARGET", target, bar["dt_et"]
            break

    exit_fill = max(0.01, exit_raw * (1.0 - cfg.option_slippage_pct))
    gross = (exit_fill - entry_fill) * 100.0 * contracts
    fees = 2.0 * cfg.commission_per_contract_each_side * contracts
    net = gross - fees
    invested = entry_fill * 100.0 * contracts + cfg.commission_per_contract_each_side * contracts
    capital_after = max(0.0, capital + net)

    return Trade(
        trading_date=trigger.trading_date, underlying=trigger.underlying,
        direction=trigger.direction, option_ticker=option_ticker,
        expiration=trigger.trading_date, strike=strike, strike_offset=strike_offset,
        trigger_time=trigger.trigger_time,
        underlying_entry_price=round(trigger.underlying_price, 4),
        or_high=round(trigger.or_high, 4), or_low=round(trigger.or_low, 4),
        vwap=round(trigger.vwap, 4),
        option_entry_time=pd.Timestamp(entry_bar["dt_et"]).strftime("%H:%M"),
        option_entry_raw=round(raw_entry, 4), option_entry_fill=round(entry_fill, 4),
        contracts=contracts, capital_before=round(capital, 2), invested=round(invested, 2),
        stop_price=round(stop, 4), target_price=round(target, 4),
        option_exit_time=pd.Timestamp(exit_time).strftime("%H:%M"),
        option_exit_raw=round(exit_raw, 4), option_exit_fill=round(exit_fill, 4),
        exit_reason=exit_reason, gross_pnl=round(gross, 2), fees=round(fees, 2),
        net_pnl=round(net, 2),
        trade_return_pct=round((exit_fill / entry_fill - 1.0) * 100.0, 2),
        account_return_pct=round(net / capital * 100.0, 2) if capital else 0.0,
        capital_after=round(capital_after, 2),
        max_favorable_pct=round((max_high / entry_fill - 1.0) * 100.0, 2),
        max_adverse_pct=round((min_low / entry_fill - 1.0) * 100.0, 2),
    )


def run_ticker_backtest(
    client: MassiveClient,
    cfg: Config,
    ticker: str,
    start_date: str,
    end_date: str,
) -> tuple[list[Trade], list[dict[str, Any]]]:
    print(f"[{ticker}] loading underlying minute bars {start_date} -> {end_date}")
    underlying = regular_session(
        client.aggregate_bars(ticker, 1, "minute", start_date, end_date)
    )
    trades: list[Trade] = []
    skipped: list[dict[str, Any]] = []
    capital = cfg.starting_capital

    for trading_date, day in underlying.groupby("date", sort=True):
        trigger = find_opening_range_trigger(
            day, ticker, cfg.opening_range_minutes, cfg.entry_cutoff
        )
        if trigger is None:
            skipped.append({"date": trading_date, "underlying": ticker, "reason": "NO_TRIGGER"})
            continue
        chosen = choose_contract(client, cfg, trigger, capital)
        if chosen is None:
            skipped.append({
                "date": trading_date, "underlying": ticker,
                "reason": "NO_AFFORDABLE_LIQUID_CONTRACT",
                "direction": trigger.direction, "trigger_time": trigger.trigger_time,
                "spot": trigger.underlying_price,
            })
            continue
        option_ticker, strike, offset, option_bars, entry_bar, contracts = chosen
        trade = simulate_trade(
            cfg, trigger, capital, option_ticker, strike, offset,
            option_bars, entry_bar, contracts
        )
        trades.append(trade)
        capital = trade.capital_after
        print(
            f"  {trade.trading_date} {trade.direction} {trade.option_ticker} "
            f"x{trade.contracts} {trade.option_entry_fill:.2f}->{trade.option_exit_fill:.2f} "
            f"{trade.exit_reason} PnL {trade.net_pnl:+.2f} Equity {capital:.2f}"
        )
        if capital < 50:
            print(f"[{ticker}] capital too low; stopping early")
            break
    return trades, skipped


def max_drawdown(equity: Iterable[float]) -> tuple[float, float]:
    peak = -math.inf
    worst_dollars = 0.0
    worst_pct = 0.0
    for value in equity:
        peak = max(peak, value)
        dd = value - peak
        dd_pct = (dd / peak * 100.0) if peak > 0 else 0.0
        worst_dollars = min(worst_dollars, dd)
        worst_pct = min(worst_pct, dd_pct)
    return round(worst_dollars, 2), round(worst_pct, 2)


def summarize(trades: list[Trade], starting_capital: float) -> dict[str, Any]:
    final = trades[-1].capital_after if trades else starting_capital
    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl < 0]
    gross_profit = sum(t.net_pnl for t in wins)
    gross_loss = abs(sum(t.net_pnl for t in losses))
    dd_dollars, dd_pct = max_drawdown([starting_capital] + [t.capital_after for t in trades])
    return {
        "starting_capital": round(starting_capital, 2),
        "final_capital": round(final, 2),
        "net_pnl": round(final - starting_capital, 2),
        "total_return_pct": round((final / starting_capital - 1.0) * 100.0, 2),
        "trades": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(trades) * 100.0, 2) if trades else None,
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else None,
        "average_trade_pnl": round(sum(t.net_pnl for t in trades) / len(trades), 2) if trades else None,
        "average_trade_return_pct": round(sum(t.trade_return_pct for t in trades) / len(trades), 2) if trades else None,
        "max_drawdown_dollars": dd_dollars, "max_drawdown_pct": dd_pct,
        "best_trade": max((t.net_pnl for t in trades), default=None),
        "worst_trade": min((t.net_pnl for t in trades), default=None),
        "target_exits": sum(t.exit_reason == "TARGET" for t in trades),
        "stop_exits": sum(t.exit_reason.startswith("STOP") for t in trades),
        "time_exits": sum(t.exit_reason == "TIME" for t in trades),
    }


def equity_svg(trades: list[Trade], starting_capital: float, width: int = 900, height: int = 220) -> str:
    values = [starting_capital] + [t.capital_after for t in trades]
    if len(values) < 2:
        return "<div class='empty'>No completed trades.</div>"
    lo, hi = min(values), max(values)
    pad = max((hi - lo) * 0.1, 1.0)
    lo -= pad
    hi += pad
    points = []
    for i, value in enumerate(values):
        x = i * width / (len(values) - 1)
        y = height - (value - lo) / (hi - lo) * height
        points.append(f"{x:.1f},{y:.1f}")
    baseline = height - (starting_capital - lo) / (hi - lo) * height
    return (
        f"<svg viewBox='0 0 {width} {height}' class='equity'>"
        f"<line x1='0' y1='{baseline:.1f}' x2='{width}' y2='{baseline:.1f}' "
        "stroke='#334155' stroke-dasharray='6 6'/>"
        f"<polyline points='{' '.join(points)}' fill='none' stroke='#38bdf8' stroke-width='3'/>"
        "</svg>"
    )


def make_report(
    cfg: Config,
    period: dict[str, str],
    all_trades: dict[str, list[Trade]],
    all_skipped: dict[str, list[dict[str, Any]]],
    all_summary: dict[str, dict[str, Any]],
) -> str:
    sections = []
    for ticker in cfg.underlyings:
        trades = all_trades[ticker]
        summary = all_summary[ticker]
        rows = []
        for t in trades:
            rows.append(
                "<tr>"
                f"<td>{html.escape(t.trading_date)}</td><td>{html.escape(t.direction)}</td>"
                f"<td class='mono'>{html.escape(t.option_ticker)}</td><td>{t.strike:.0f}</td>"
                f"<td>{t.trigger_time}</td><td>{t.option_entry_time}</td>"
                f"<td>${t.option_entry_fill:.2f}</td><td>{t.contracts}</td>"
                f"<td>{t.option_exit_time}</td><td>${t.option_exit_fill:.2f}</td>"
                f"<td>{html.escape(t.exit_reason)}</td>"
                f"<td class='{'pos' if t.net_pnl >= 0 else 'neg'}'>${t.net_pnl:+.2f}</td>"
                f"<td>{t.trade_return_pct:+.1f}%</td><td>${t.capital_after:.2f}</td></tr>"
            )
        cards = "".join(
            f"<div class='card'><span>{html.escape(k.replace('_', ' ').title())}</span>"
            f"<strong>{'—' if v is None else v}</strong></div>"
            for k, v in summary.items()
        )
        sections.append(
            f"<section><h2>{ticker}</h2><div class='cards'>{cards}</div>"
            f"{equity_svg(trades, cfg.starting_capital)}"
            "<div class='table-wrap'><table><thead><tr>"
            "<th>Date</th><th>Side</th><th>Contract</th><th>Strike</th><th>Trigger</th>"
            "<th>Entry</th><th>Premium</th><th>Qty</th><th>Exit</th><th>Exit premium</th>"
            "<th>Reason</th><th>P&amp;L</th><th>Option return</th><th>Equity</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
            f"<p class='muted'>Skipped sessions: {len(all_skipped[ticker])}</p></section>"
        )

    config_pre = html.escape(json.dumps(asdict(cfg), ensure_ascii=False, indent=2))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>0DTE Actual-Contract Backtest</title><style>
:root{{--bg:#071019;--panel:#0d1722;--border:#223246;--text:#e5eef8;--muted:#8191a5;--pos:#34d399;--neg:#fb7185;}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,system-ui,sans-serif}}
main{{max-width:1400px;margin:auto;padding:28px}}h1{{font-size:32px;margin-bottom:6px}}h2{{margin-top:46px}}
.muted{{color:var(--muted)}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin:18px 0}}
.card{{background:var(--panel);border:1px solid var(--border);padding:14px;border-radius:10px}}
.card span{{display:block;color:var(--muted);font-size:12px;text-transform:uppercase}}.card strong{{font-size:20px}}
.equity{{width:100%;height:220px;background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:12px}}
.table-wrap{{overflow:auto;margin-top:16px;border:1px solid var(--border)}}table{{width:100%;border-collapse:collapse;white-space:nowrap}}
th,td{{padding:9px 11px;border-bottom:1px solid var(--border);text-align:right;font-size:12px}}th{{color:var(--muted);position:sticky;top:0;background:var(--panel)}}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2),th:nth-child(3),td:nth-child(3){{text-align:left}}
.mono{{font-family:ui-monospace,monospace}}.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}
pre{{background:var(--panel);border:1px solid var(--border);padding:16px;overflow:auto}}
.notice{{border-left:4px solid #f59e0b;background:#1c1609;padding:14px 16px}}
</style></head><body><main><h1>0DTE Actual-Contract Backtest</h1>
<p class="muted">{period['start']} through {period['end']} · starting capital ${cfg.starting_capital:,.2f} per ticker</p>
<div class="notice"><b>Fill model:</b> actual option minute trade aggregates, not historical bid/ask quotes.
Entry and exit slippage are modeled at {cfg.option_slippage_pct*100:.1f}% each side.
Same-minute stop/target ambiguity is resolved pessimistically as a stop.</div>
{''.join(sections)}<h2>Configuration</h2><pre>{config_pre}</pre></main></body></html>"""


def resolve_period(cfg: Config, start: str | None, end: str | None) -> tuple[str, str]:
    end_date = datetime.strptime(end, "%Y-%m-%d").date() if end else datetime.now(NY).date() - timedelta(days=1)
    start_date = datetime.strptime(start, "%Y-%m-%d").date() if start else end_date - timedelta(days=cfg.lookback_calendar_days)
    if start_date >= end_date:
        raise ValueError("start date must be before end date")
    return start_date.isoformat(), end_date.isoformat()


def write_outputs(
    cfg: Config,
    period: dict[str, str],
    all_trades: dict[str, list[Trade]],
    all_skipped: dict[str, list[dict[str, Any]]],
) -> None:
    out = Path(cfg.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summaries: dict[str, dict[str, Any]] = {}
    for ticker, trades in all_trades.items():
        summaries[ticker] = summarize(trades, cfg.starting_capital)
        pd.DataFrame([asdict(t) for t in trades]).to_csv(out / f"{ticker}_trades.csv", index=False)
        pd.DataFrame(all_skipped[ticker]).to_csv(out / f"{ticker}_skipped.csv", index=False)
    payload = {
        "generated_at_et": datetime.now(NY).isoformat(), "period": period,
        "fill_model": {
            "source": "actual qualifying-trade minute aggregates", "quotes_used": False,
            "entry_slippage_pct": cfg.option_slippage_pct * 100,
            "exit_slippage_pct": cfg.option_slippage_pct * 100,
        },
        "summary": summaries, "config": asdict(cfg),
    }
    (out / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "index.html").write_text(
        make_report(cfg, period, all_trades, all_skipped, summaries), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest actual 0DTE option contracts")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--start", help="YYYY-MM-DD")
    parser.add_argument("--end", help="YYYY-MM-DD")
    args = parser.parse_args()
    cfg = Config.from_file(args.config)
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if not api_key:
        print("ERROR: add MASSIVE_API_KEY as a GitHub Actions secret or environment variable.", file=sys.stderr)
        return 2
    start_date, end_date = resolve_period(cfg, args.start, args.end)
    client = MassiveClient(api_key, cfg.api_min_interval_seconds, cfg.cache_dir)
    all_trades: dict[str, list[Trade]] = {}
    all_skipped: dict[str, list[dict[str, Any]]] = {}
    for ticker in cfg.underlyings:
        trades, skipped = run_ticker_backtest(client, cfg, ticker, start_date, end_date)
        all_trades[ticker] = trades
        all_skipped[ticker] = skipped
    write_outputs(cfg, {"start": start_date, "end": end_date}, all_trades, all_skipped)
    print(f"Report written to {Path(cfg.output_dir) / 'index.html'}")
    for ticker, trades in all_trades.items():
        print(ticker, summarize(trades, cfg.starting_capital))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
