# -*- coding: utf-8 -*-
"""
0DTE Mock Trading — QQQ VWAP 밴드 전략 (모의매매 · 실거래 아님)

전략 v2 (방향 신호 즉시 진입 — 밴드 대기 폐지):
  판단  : 10:00 ET · DTE 점수 = 갭 + EMA9/21 + VWAP위치 + RSI (각 ±1, 합 -4~+4)
  진입  : 점수 >= +3 → CALL / 점수 <= -3 → PUT (즉시 ATM 매수)
  익절  : 프리미엄 +40%
  손절  : 프리미엄 -30%
  마감  : 14:30 ET 강제청산 (세타 급가속 구간 회피)
  백테스트: 강한 롱 71.4% 상승 / 강한 숏 66.7% 하락 (QQQ 60일, 기초자산 기준)

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
SCORE_MIN = 3        # |DTE 점수| 이 값 이상일 때만 진입
TP_PCT   = 40.0      # 프리미엄 익절 %
SL_PCT   = -30.0     # 프리미엄 손절 %
CUTOFF   = dt.time(14, 30)   # 세타 급가속 전 청산
MAX_PER_DAY = 1      # 방향 베팅이라 하루 1회
VERSION_NOTE = "direction-v2"
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
    # RSI(14) on 5m closes
    g = l = 0.0
    for i in range(len(hist) - 14, len(hist)):
        d2 = hist[i] - hist[i-1]
        if d2 > 0: g += d2
        else: l -= d2
    rsi = 100.0 if l == 0 else 100 - 100 / (1 + (g/14) / (l/14))

    bw = (2 * sd / vwap * 100) if vwap else 0.0
    px = C[-1]
    dev = (px - vwap) / sd if sd > 1e-9 else 0.0
    score = 0
    score += 1 if gap >= 0.3 else (-1 if gap <= -0.3 else 0)
    score += 1 if e9 > e21 else -1
    score += 1 if px > vwap else -1
    score += 1 if rsi > 60 else (-1 if rsi < 40 else 0)
    direction = 1 if score >= SCORE_MIN else (-1 if score <= -SCORE_MIN else 0)
    return dict(px=px, vwap=vwap, sd=sd, bw=bw, dev=dev, gap=gap, rsi=rsi, score=score,
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
        # 현재 프리미엄 조회 후 손익 기준으로 청산 판단
        cur_prem = None
        try:
            ch = yf.Ticker(TICKER).option_chain(today_expiry(today))
            tbl = ch.calls if side == "call" else ch.puts
            row = tbl[tbl["strike"] == open_pos["strike"]]
            if not row.empty:
                r = row.iloc[0]
                b = float(r.get("bid") or 0); a = float(r.get("ask") or 0)
                cur_prem = round((b + a) / 2 if (b > 0 and a > 0) else float(r.get("lastPrice") or 0), 2)
        except Exception:
            pass
        if cur_prem and cur_prem > 0:
            chg = (cur_prem / open_pos["premium"] - 1) * 100
            if chg >= TP_PCT: reason = f"TARGET(+{TP_PCT:.0f}%)"
            elif chg <= SL_PCT: reason = f"STOP({SL_PCT:.0f}%)"
        if now.time() >= CUTOFF and reason is None:
            reason = "CUTOFF(14:30)"
        if reason:
            exit_prem = cur_prem
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
    done_today = sum(1 for t in log.get("trades", []) if t.get("date") == dstr)
    if done_today >= MAX_PER_DAY:
        print(f"  오늘 {done_today}회 완료 (상한 {MAX_PER_DAY}) — 종료"); save_log(log); return log, st

    if st["direction"] == 0:
        status = f"NO TRADE · 점수 {st['score']:+d} (|{SCORE_MIN}| 미만)"
    else:
        side = "call" if st["direction"] > 0 else "put"
        opt = atm_option(st["px"], side, today_expiry(today))
        if not opt:
            status = "진입 조건 충족 · 옵션 데이터 없음"
        else:
            log["open"] = dict(date=dstr, side=side, strike=opt["strike"],
                               premium=opt["premium"], iv=opt["iv"], symbol=opt["symbol"],
                               entry_time=now.strftime("%H:%M"), entry_px=round(st["px"], 2),
                               score=st["score"], gap=round(st["gap"], 2), rsi=round(st["rsi"], 1),
                               target=round(opt["premium"] * (1 + TP_PCT/100), 2),
                               stop=round(opt["premium"] * (1 + SL_PCT/100), 2),
                               version=VERSION)
            status = f"진입 · {side.upper()} {opt['strike']:.0f} @ ${opt['premium']}"
            print(f"  {status}")
    log["days"][dstr] = dict(status=status, score=st["score"], rsi=round(st["rsi"], 1),
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
               f'<div class="s">진입 {op["entry_time"]} · 점수 {op.get("score", 0):+d} · 기초 {op["entry_px"]} '
               f'· 익절 ${op["target"]} · 손절 ${op["stop"]}</div></div>')
    elif st:
        d = log.get("days", {}).get(str(dt.datetime.now(NY).date()), {})
        cur = (f'<div class="live idle"><div class="k">오늘 상태</div>'
               f'<div class="v">{d.get("status", "대기")}</div>'
               f'<div class="s">점수 {st["score"]:+d} · 기초 {st["px"]:.2f} · VWAP {st["vwap"]:.2f} '
               f'· RSI {st["rsi"]:.0f} · 갭 {st["gap"]:+.2f}%</div></div>')
    else:
        cur = '<div class="live idle"><div class="k">오늘 상태</div><div class="v">장 시작 대기</div></div>'

    # 일별 요약
    byday = {}
    for t in trades:
        d = t["date"]
        b = byday.setdefault(d, {"n":0,"w":0,"pnl":0.0,"items":[]})
        b["n"] += 1; b["pnl"] += t["pnl_pct"]
        if t["pnl_pct"] > 0: b["w"] += 1
        b["items"].append(t)
    daily = ""
    for d in sorted(byday, reverse=True)[:20]:
        b = byday[d]
        c = "#34c77b" if b["pnl"] > 0 else "#e95656"
        det = " · ".join(f'{t["side"][0].upper()}{t["strike"]:.0f} {t["pnl_pct"]:+.0f}%' for t in b["items"])
        daily += (f'<div class="dayrow"><span class="dd">{d[5:]}</span>'
                  f'<span class="dn">{b["w"]}/{b["n"]}</span>'
                  f'<span class="dp" style="color:{c}">{b["pnl"]:+.1f}%</span>'
                  f'<div class="dx">{det}</div></div>')
    if not daily:
        daily = '<div class="dayrow"><span class="dx">아직 거래 없음</span></div>'

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
<link rel="apple-touch-icon" href="icon-192.png">
<link rel="icon" href="icon-192.png" type="image/png">
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
.sec{{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.16em;color:var(--m);text-transform:uppercase;margin:20px 0 8px}}
.days{{background:var(--s);border:1px solid var(--b)}}
.dayrow{{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px;padding:10px 12px;border-bottom:1px solid var(--b)}}
.dayrow:last-child{{border-bottom:none}}
.dd{{font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--t);width:44px}}
.dn{{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--m)}}
.dp{{font-family:'IBM Plex Mono',monospace;font-size:13px;font-weight:600;margin-left:auto}}
.dx{{flex-basis:100%;font-family:'IBM Plex Mono',monospace;font-size:10.5px;color:var(--d)}}
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
<div class="sec">일별 성적</div>
<div class="days">{daily}</div>
<div class="sec">전체 기록</div>
<table><tr><th>날짜</th><th>포지션</th><th>시각</th><th>프리미엄</th><th>손익</th><th>청산</th></tr>{rows}</table>
<div class="rule">
<b>전략 {VERSION_NOTE}</b> — 10:00 ET 점수(갭·EMA9/21·VWAP·RSI, -4~+4) ·
|점수|≥{SCORE_MIN} 이면 ATM 즉시 진입 · 익절 +{TP_PCT:.0f}% · 손절 {SL_PCT:.0f}% · 마감 14:30 ET · 하루 1회<br>
백테스트(60일·기초자산): 강한 롱 71.4% 상승 / 강한 숏 66.7% 하락 — 옵션 손익은 별개이며 이 기록으로 검증 중<br>
<b>모의매매입니다. 실거래 아니며 투자조언이 아닙니다.</b> 프리미엄은 15분 지연 mid 기준이라 실제 체결가와 다릅니다.
</div>
<script>
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(function(){{}});
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
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    with open(os.path.join(BASE, "manifest.webmanifest"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    # 설치 요건 충족용 최소 서비스워커 (네트워크 우선, 오프라인 시 캐시)
    sw = """self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => self.clients.claim());
self.addEventListener('fetch', e => {
  e.respondWith(
    fetch(e.request).then(r => {
      const c = r.clone();
      caches.open('odte-v1').then(k => k.put(e.request, c)).catch(()=>{});
      return r;
    }).catch(() => caches.match(e.request))
  );
});"""
    with open(os.path.join(BASE, "sw.js"), "w", encoding="utf-8") as f:
        f.write(sw)

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
