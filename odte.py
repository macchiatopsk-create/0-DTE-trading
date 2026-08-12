# -*- coding: utf-8 -*-
"""
0DTE Mock Trading — QQQ VWAP 밴드 전략 (모의매매 · 실거래 아님)

전략 (60일 백테스트 기반 · 밴드폭 넓을 때 승률 78%, CI 72.5~82.6):
  방향  : 10:00 ET 기준 EMA9 > EMA21  AND  갭 방향 일치
  게이트: 밴드폭(±1σ) >= 0.75%        ← 좁으면 진입 금지 (8월 붕괴 원인)
  진입  : 가격이 VWAP -1σ 터치 (롱) / +1σ (숏)
  익절  : 반대편 +1σ 도달
  손절  : -2σ 이탈
  마감  : 15:45 ET 강제청산

기록: 스트라이크 · 진입/청산 시각 · 프리미엄 · 손익률
주의: 모의매매입니다. 실거래 아님. 검증 전 참고용.
"""
import os, sys, json, math
import datetime as dt
from zoneinfo import ZoneInfo

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("필요: pip install yfinance pandas"); sys.exit(1)

NY = ZoneInfo("America/New_York")
BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "odte_log.json")
OUT = os.path.join(BASE, "index.html")

TICKER   = "QQQ"
BAND_MIN = 0.75      # 밴드폭 최소 % (게이트)
CUTOFF   = dt.time(15, 45)
VERSION  = "vwap-1.0"

# ───────────────────────── 데이터 ─────────────────────────
def load_log():
    try:
        with open(LOG, encoding="utf-8") as f:
            j = json.load(f)
        return j if isinstance(j, dict) else {"open": None, "trades": [], "days": {}}
    except Exception:
        return {"open": None, "trades": [], "days": {}}

def save_log(d):
    with open(LOG, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)

def ema(vals, n):
    k = 2.0 / (n + 1); e = None
    for v in vals:
        e = v if e is None else v * k + e * (1 - k)
    return e

def intraday():
    df = yf.Ticker(TICKER).history(period="3d", interval="5m")
    if df is None or df.empty:
        raise ValueError("5분봉 없음")
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    try:
        df.index = df.index.tz_convert(NY)
    except Exception:
        pass
    df = df[(df.index.time >= dt.time(9, 30)) & (df.index.time < dt.time(16, 0))]
    return df

def session_state(df):
    """오늘 세션의 VWAP/밴드/방향/밴드폭 계산."""
    days = sorted(set(df.index.date))
    if len(days) < 2:
        raise ValueError("전일 데이터 없음")
    today = days[-1]
    day = df[df.index.date == today]
    prev = df[df.index.date == days[-2]]
    if len(day) < 7:
        return None, today, len(day)

    H = [float(x) for x in day["High"]]; L = [float(x) for x in day["Low"]]
    C = [float(x) for x in day["Close"]]; V = [float(x) for x in day["Volume"]]
    O = [float(x) for x in day["Open"]]
    cpv = cv = cpv2 = 0.0
    for i in range(len(C)):
        tp = (H[i] + L[i] + C[i]) / 3
        cpv += tp * V[i]; cv += V[i]; cpv2 += tp * tp * V[i]
    vwap = cpv / cv if cv else C[-1]
    var = max(cpv2 / cv - vwap * vwap, 0.0) if cv else 0.0
    sd = math.sqrt(var)

    gap = (O[0] / float(prev["Close"].iloc[-1]) - 1) * 100
    hist = [float(x) for x in df["Close"]][-61:]
    e9, e21 = ema(hist, 9), ema(hist, 21)
    direction = 1 if e9 > e21 else -1
    if (direction > 0 and gap <= 0) or (direction < 0 and gap >= 0):
        direction = 0                      # 갭 방향 불일치 → 관망

    bw = (2 * sd / vwap * 100) if vwap else 0.0
    px = C[-1]
    dev = (px - vwap) / sd if sd > 1e-9 else 0.0
    return dict(px=px, vwap=vwap, sd=sd, bw=bw, dev=dev, gap=gap,
                direction=direction, e9=e9, e21=e21,
                band_lo=vwap - sd, band_hi=vwap + sd,
                stop_lo=vwap - 2 * sd, stop_hi=vwap + 2 * sd,
                ts=day.index[-1].strftime("%H:%M")), today, len(day)

# ───────────────────────── 옵션 ─────────────────────────
def atm_option(spot, side, expiry):
    """0DTE ATM 옵션의 현재 프리미엄 (mid) · 스트라이크."""
    try:
        ch = yf.Ticker(TICKER).option_chain(expiry)
        tbl = ch.calls if side == "call" else ch.puts
        tbl = tbl.dropna(subset=["strike"])
        if tbl.empty: return None
        tbl = tbl.assign(_d=(tbl["strike"] - spot).abs()).sort_values("_d")
        r = tbl.iloc[0]
        bid = float(r.get("bid") or 0); ask = float(r.get("ask") or 0)
        last = float(r.get("lastPrice") or 0)
        mid = (bid + ask) / 2 if (bid > 0 and ask > 0) else last
        if mid <= 0: return None
        return dict(strike=float(r["strike"]), premium=round(mid, 2),
                    bid=bid, ask=ask, iv=round(float(r.get("impliedVolatility") or 0) * 100, 1),
                    symbol=str(r.get("contractSymbol", "")))
    except Exception as ex:
        print(f"  옵션 조회 실패: {ex}")
        return None

def today_expiry(d):
    return d.strftime("%Y-%m-%d")

# ───────────────────────── 로직 ─────────────────────────
def step():
    now = dt.datetime.now(NY)
    log = load_log()
    df = intraday()
    st, today, nbars = session_state(df)
    dstr = str(today)

    if st is None:
        print(f"  10:00 이전 (봉 {nbars}) — 대기")
        log["days"][dstr] = {"status": "WAIT_OPEN", "bars": nbars, "at": now.strftime("%H:%M")}
        save_log(log); return log, None

    open_pos = log.get("open")
    print(f"  {st['ts']} px={st['px']:.2f} vwap={st['vwap']:.2f} 밴드폭={st['bw']:.2f}% "
          f"편차={st['dev']:+.2f}σ 방향={st['direction']}")

    # ── 1) 보유 중이면 청산 체크 ──
    if open_pos and open_pos.get("date") == dstr:
        side = open_pos["side"]; reason = None
        if side == "call":
            if st["px"] >= st["band_hi"]: reason = "TARGET(+1σ)"
            elif st["px"] <= st["stop_lo"]: reason = "STOP(-2σ)"
        else:
            if st["px"] <= st["band_lo"]: reason = "TARGET(-1σ)"
            elif st["px"] >= st["stop_hi"]: reason = "STOP(+2σ)"
        if now.time() >= CUTOFF and reason is None:
            reason = "CUTOFF(15:45)"
        if reason:
            opt = atm_option(st["px"], side, today_expiry(today))
            exit_prem = None
            if opt:
                # 같은 스트라이크의 현재가를 다시 조회
                try:
                    ch = yf.Ticker(TICKER).option_chain(today_expiry(today))
                    tbl = ch.calls if side == "call" else ch.puts
                    row = tbl[tbl["strike"] == open_pos["strike"]]
                    if not row.empty:
                        r = row.iloc[0]
                        b = float(r.get("bid") or 0); a = float(r.get("ask") or 0)
                        exit_prem = round((b + a) / 2 if (b > 0 and a > 0) else float(r.get("lastPrice") or 0), 2)
                except Exception:
                    pass
            if exit_prem is None or exit_prem <= 0:
                exit_prem = open_pos["premium"]        # 조회 실패 시 보수적으로 본전 처리
            pnl_pct = (exit_prem / open_pos["premium"] - 1) * 100
            tr = dict(open_pos)
            tr.update(exit_time=now.strftime("%H:%M"), exit_px=round(st["px"], 2),
                      exit_premium=exit_prem, pnl_pct=round(pnl_pct, 1), reason=reason)
            log.setdefault("trades", []).append(tr)
            log["open"] = None
            print(f"  청산: {reason} 프리미엄 {open_pos['premium']}→{exit_prem} ({pnl_pct:+.1f}%)")
            save_log(log); return log, st
        print("  보유 중 — 조건 미달")
        save_log(log); return log, st

    # ── 2) 신규 진입 체크 ──
    if now.time() >= CUTOFF:
        print("  15:45 이후 — 신규 진입 없음"); save_log(log); return log, st
    if any(t.get("date") == dstr for t in log.get("trades", [])):
        print("  오늘 이미 1회 완료 — 종료"); save_log(log); return log, st

    if st["direction"] == 0:
        status = "NO TRADE · 방향 불일치(EMA vs 갭)"
    elif st["bw"] < BAND_MIN:
        status = f"NO TRADE · 밴드폭 {st['bw']:.2f}% < {BAND_MIN}%"
    elif st["direction"] > 0 and st["dev"] > -1.0:
        status = f"대기 · -1σ 터치 필요 (현재 {st['dev']:+.2f}σ)"
    elif st["direction"] < 0 and st["dev"] < 1.0:
        status = f"대기 · +1σ 터치 필요 (현재 {st['dev']:+.2f}σ)"
    else:
        side = "call" if st["direction"] > 0 else "put"
        opt = atm_option(st["px"], side, today_expiry(today))
        if not opt:
            status = "진입 조건 충족 · 옵션 데이터 없음"
        else:
            log["open"] = dict(date=dstr, side=side, strike=opt["strike"],
                               premium=opt["premium"], iv=opt["iv"], symbol=opt["symbol"],
                               entry_time=now.strftime("%H:%M"), entry_px=round(st["px"], 2),
                               entry_dev=round(st["dev"], 2), bw=round(st["bw"], 2),
                               target=round(st["band_hi"] if side == "call" else st["band_lo"], 2),
                               stop=round(st["stop_lo"] if side == "call" else st["stop_hi"], 2),
                               version=VERSION)
            status = f"진입 · {side.upper()} {opt['strike']:.0f} @ ${opt['premium']}"
            print(f"  {status}")
    log["days"][dstr] = dict(status=status, bw=round(st["bw"], 2), dev=round(st["dev"], 2),
                             direction=st["direction"], gap=round(st["gap"], 2),
                             px=round(st["px"], 2), vwap=round(st["vwap"], 2),
                             at=now.strftime("%H:%M"))
    print(f"  {status}")
    save_log(log); return log, st

# ───────────────────────── 화면 ─────────────────────────
def render(log, st):
    trades = log.get("trades", [])
    n = len(trades)
    wins = sum(1 for t in trades if t["pnl_pct"] > 0)
    wr = round(wins / n * 100, 1) if n else None
    avg = round(sum(t["pnl_pct"] for t in trades) / n, 1) if n else None
    tot = round(sum(t["pnl_pct"] for t in trades), 1) if n else 0
    now = dt.datetime.now(NY).strftime("%Y-%m-%d %H:%M ET")
    op = log.get("open")

    if op:
        cur = (f'<div class="live"><div class="k">보유 중</div>'
               f'<div class="v">{op["side"].upper()} {op["strike"]:.0f} @ ${op["premium"]}</div>'
               f'<div class="s">진입 {op["entry_time"]} · 기초 {op["entry_px"]} ({op["entry_dev"]}σ) '
               f'· 목표 {op["target"]} · 손절 {op["stop"]}</div></div>')
    elif st:
        d = log.get("days", {}).get(str(dt.datetime.now(NY).date()), {})
        cur = (f'<div class="live idle"><div class="k">오늘 상태</div>'
               f'<div class="v">{d.get("status", "대기")}</div>'
               f'<div class="s">기초 {st["px"]:.2f} · VWAP {st["vwap"]:.2f} · 밴드폭 {st["bw"]:.2f}% '
               f'· 편차 {st["dev"]:+.2f}σ · 갭 {st["gap"]:+.2f}%</div></div>')
    else:
        cur = '<div class="live idle"><div class="k">오늘 상태</div><div class="v">장 시작 대기</div></div>'

    rows = ""
    for t in reversed(trades[-40:]):
        c = "#34c77b" if t["pnl_pct"] > 0 else "#e95656"
        rows += (f'<tr><td>{t["date"][5:]}</td><td>{t["side"].upper()} {t["strike"]:.0f}</td>'
                 f'<td>{t["entry_time"]}→{t["exit_time"]}</td>'
                 f'<td>${t["premium"]}→${t["exit_premium"]}</td>'
                 f'<td style="color:{c}">{t["pnl_pct"]:+.1f}%</td><td class="rs">{t["reason"]}</td></tr>')
    if not rows:
        rows = '<tr><td colspan="6" class="rs">기록 없음 — 조건 충족 시 자동 진입</td></tr>'

    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>0DTE Mock · QQQ</title>
<link rel="manifest" href="manifest.webmanifest">
<meta name="theme-color" content="#06090d">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="0DTE">
<link rel="apple-touch-icon" href="icon.svg">
<link rel="icon" href="icon.svg" type="image/svg+xml">
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@600;700&family=IBM+Plex+Mono:wght@400;600&family=Noto+Sans+KR:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--bg:#06090d;--s:#0b1017;--b:#1a2230;--t:#e6edf5;--m:#6d7a8c;--d:#424c5c;--g:#dba642;--up:#34c77b;--dn:#e95656}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--t);font-family:'Noto Sans KR',sans-serif;padding:20px 16px 50px;max-width:620px;margin:0 auto}}
header{{display:flex;align-items:baseline;gap:10px;padding-bottom:14px;border-bottom:1px solid var(--b)}}
h1{{font-family:'Poppins',sans-serif;font-size:21px;font-weight:700}}
.eb{{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.18em;color:var(--g)}}
.ts{{margin-left:auto;font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--d)}}
.live{{background:var(--s);border:1px solid var(--b);border-left:4px solid var(--g);padding:16px;margin:16px 0}}
.live.idle{{border-left-color:var(--d)}}
.live .k{{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.16em;color:var(--m);text-transform:uppercase}}
.live .v{{font-family:'Poppins',sans-serif;font-size:20px;font-weight:600;margin:6px 0 4px}}
.live .s{{font-family:'IBM Plex Mono',monospace;font-size:11.5px;color:var(--m);line-height:1.7}}
.stats{{display:flex;gap:10px;margin-bottom:16px}}
.st{{flex:1;background:var(--s);border:1px solid var(--b);padding:12px}}
.st .k{{font-family:'IBM Plex Mono',monospace;font-size:9.5px;letter-spacing:.14em;color:var(--m)}}
.st .v{{font-family:'IBM Plex Mono',monospace;font-size:19px;font-weight:600;margin-top:4px}}
table{{width:100%;border-collapse:collapse;background:var(--s);border:1px solid var(--b)}}
th{{font-family:'IBM Plex Mono',monospace;font-size:9.5px;letter-spacing:.1em;color:var(--m);text-align:left;padding:9px 8px;border-bottom:1px solid var(--b);text-transform:uppercase}}
td{{font-family:'IBM Plex Mono',monospace;font-size:11.5px;padding:9px 8px;border-bottom:1px solid var(--b)}}
tr:last-child td{{border-bottom:none}}
.rs{{color:var(--d);font-size:10.5px}}
.rule{{font-size:11.5px;color:var(--d);line-height:1.9;margin-top:16px;padding-top:14px;border-top:1px solid var(--b)}}
</style></head><body>
<header><div><div class="eb">0DTE MOCK</div><h1>QQQ VWAP 밴드</h1></div><div class="ts">{now}</div></header>
{cur}
<div class="stats">
  <div class="st"><div class="k">TRADES</div><div class="v">{n}</div></div>
  <div class="st"><div class="k">WIN RATE</div><div class="v">{f"{wr}%" if wr is not None else "—"}</div></div>
  <div class="st"><div class="k">AVG</div><div class="v" style="color:{'#34c77b' if (avg or 0)>0 else '#e95656'}">{f"{avg:+.1f}%" if avg is not None else "—"}</div></div>
  <div class="st"><div class="k">TOTAL</div><div class="v" style="color:{'#34c77b' if tot>0 else '#e95656'}">{tot:+.0f}%</div></div>
</div>
<table><tr><th>날짜</th><th>포지션</th><th>시각</th><th>프리미엄</th><th>손익</th><th>청산</th></tr>{rows}</table>
<div class="rule">
<b>전략 {VERSION}</b> — 방향: EMA9&gt;21 + 갭 일치 · 게이트: 밴드폭 ≥{BAND_MIN}% ·
진입: VWAP ∓1σ 터치 · 익절: 반대편 1σ · 손절: 2σ · 마감: 15:45 ET · 하루 1회<br>
백테스트(60일) 기준선: 밴드폭 넓은 구간 승률 78% (CI 72.5~82.6)<br>
<b>모의매매입니다. 실거래 아니며 투자조언이 아닙니다.</b> 프리미엄은 15분 지연 mid 기준이라 실제 체결가와 다릅니다.
</div>
<script>
(function(){{
  var f=new Intl.DateTimeFormat("en-US",{{timeZone:"America/New_York",hour:"2-digit",minute:"2-digit",weekday:"short",hour12:false}});
  function live(){{var o={{}};f.formatToParts(new Date()).forEach(function(p){{o[p.type]=p.value}});
    if(o.weekday==="Sat"||o.weekday==="Sun")return false;
    var m=parseInt(o.hour,10)*60+parseInt(o.minute,10);return m>=570&&m<=960;}}
  if(live()) setTimeout(function(){{location.reload()}},300000);
}})();
</script>
</body></html>"""

def write_pwa():
    """홈 화면 설치용 매니페스트 + 아이콘 (SMC 대시보드와 동일 방식)."""
    icon = ("""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192">
<rect width="192" height="192" rx="34" fill="#06090d"/>
<circle cx="96" cy="96" r="62" fill="none" stroke="#dba642" stroke-width="6"/>
<path d="M34 118 L70 92 L104 108 L158 62" fill="none" stroke="#34c77b" stroke-width="9"
      stroke-linecap="round" stroke-linejoin="round"/>
<line x1="34" y1="96" x2="158" y2="96" stroke="#2a3648" stroke-width="3" stroke-dasharray="7 7"/>
<text x="96" y="166" text-anchor="middle" fill="#dba642"
      font-family="monospace" font-size="26" font-weight="bold">0DTE</text></svg>""")
    with open(os.path.join(BASE, "icon.svg"), "w", encoding="utf-8") as f:
        f.write(icon)
    manifest = {
        "name": "0DTE Mock · QQQ", "short_name": "0DTE",
        "start_url": ".", "scope": ".", "display": "standalone",
        "background_color": "#06090d", "theme_color": "#06090d",
        "description": "QQQ VWAP 밴드 0DTE 모의매매",
        "icons": [{"src": "icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}],
    }
    with open(os.path.join(BASE, "manifest.webmanifest"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

def main():
    print(f"0DTE Mock — {dt.datetime.now(NY).strftime('%Y-%m-%d %H:%M ET')}")
    log, st = None, None
    try:
        log, st = step()
    except Exception as ex:
        print(f"  오류: {type(ex).__name__}: {ex}")
        log = load_log()
    write_pwa()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(log, st))
    print(f"  생성: {OUT} · 누적 {len(log.get('trades', []))}건")

if __name__ == "__main__":
    main()
