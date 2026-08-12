# 0-DTE Trading Backtest

A strike-level 0DTE options backtester for **SPY** and **QQQ**.

It uses actual historical option **minute aggregates** for the exact same-day-expiry contract selected on each signal day. The report records:

- exact OCC option ticker
- call or put
- expiration and strike
- underlying trigger time and price
- option entry/exit time and modeled fill
- number of contracts
- TP / SL / time-exit reason
- option return, dollar P&L, and account equity
- full trade CSV and HTML equity report

## Default strategy

1. Build the 09:30–10:00 ET opening range.
2. After 10:00 ET:
   - first 5-minute close above OR high and above session VWAP → CALL
   - first 5-minute close below OR low and below session VWAP → PUT
3. Start at one strike OTM.
4. If one contract is too expensive for the account budget, move farther OTM, up to five strikes.
5. Enter on the first available option 1-minute bar after the underlying trigger.
6. Exit at:
   - +60% premium
   - −35% premium
   - 15:45 ET
7. One trade per ticker per day; no re-entry.

Default capital is **$1,000 per ticker**. All assumptions are editable in `config.json`.

## Data and fill realism

The free Massive Options Basic plan provides historical option minute aggregates. These bars are built from qualifying option trades. They are not historical executable bid/ask quotes.

The backtester therefore applies conservative configurable slippage to both entry and exit. If both stop and target appear inside the same minute bar, the stop is assumed to occur first.

For quote-accurate fills, replace minute aggregate fills with historical NBBO quote data.

## Setup

### 1. Create a Massive API key

Enable the free **Stocks Basic** and **Options Basic** products on the same Massive account.

### 2. Add the GitHub secret

Repository:

`Settings → Secrets and variables → Actions → New repository secret`

Add:

```text
Name: MASSIVE_API_KEY
Value: your Massive API key
```

### 3. Run

`Actions → 0DTE actual-options backtest → Run workflow`

Leave dates blank for the most recent 92 calendar days, or enter explicit dates.

### 4. Results

The workflow:

- commits `results/` to the repository
- uploads the report as an Actions artifact
- deploys `results/index.html` to GitHub Pages

Files:

```text
results/
  index.html
  summary.json
  SPY_trades.csv
  SPY_skipped.csv
  QQQ_trades.csv
  QQQ_skipped.csv
```

## Important configuration fields

```json
{
  "starting_capital": 1000.0,
  "take_profit_pct": 0.60,
  "stop_loss_pct": 0.35,
  "max_position_pct": 0.35,
  "first_otm_offset": 1,
  "max_otm_offset": 5,
  "option_slippage_pct": 0.02
}
```

## Next phase

This repository starts with an independent ORB + VWAP baseline so the option execution engine can be validated first.

After the baseline works, the next extension is to feed the prior-day Market Radar score into the strategy:

- score ≤ 45: calls only
- score 46–55: no trade
- score ≥ 56: puts only
- optional extreme-only variants at ≤25 and ≥76

That comparison will show whether the Market Radar filter improves the actual 0DTE option P&L, not merely the underlying direction hit rate.
