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
import math, math
from zoneinfo import ZoneInfo

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
except ImportError:
    print("필요: pip install yfinance pandas"); sys.exit(1)

NY = ZoneInfo("America/New_York")
BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "odte_log.json")
OUT = os.path.join(BASE, "index.html")

TICKER   = "QQQ"
SCORE_MIN = 3        # |DTE 점수| 이 값 이상일 때만 진입
# 청산은 프리미엄 %가 아니라 기초자산 트리거 (v10 검증 C안)
#   TP1: VWAP 도달 -> 가치 50% 청산 기록 / 러너: +1σ 전량 / 손절: 당일저점 / 14:30 시간청산
# (1계약이라 물리적 분할 불가 -> mock상 0.5*TP1가 + 0.5*최종가로 기록)
CUTOFF   = dt.time(14, 30)   # 세타 급가속 전 청산
MAX_PER_DAY = 1      # 방향 베팅이라 하루 1회
VERSION_NOTE = "3layer-itm-forward"
VERSION  = "itm-2.0"

# ── ITM 포워드 테스트 (2026-08-14 시작) ──
CAPITAL_START = 1000.0   # mock 자본. 로그의 trades에서 동적 집계 (헌법 7조)
DELTA_LO, DELTA_HI = 0.70, 0.80   # ITM 콜 델타 밴드
ENTRY_BAND_SIG = 1.0     # VWAP -1σ 터치 대기 (v10: 진입대기가 09:30 즉시진입보다 우수)

# ── 갭 전략 (별도 트랙, 포워드 테스트) ─────────────────────
# 근거: 1시간봉 2년 n=151 PF 1.58 (상위2제외 1.48, 반반 1.53/1.62)
#   갭 0.2~1.0% → 갭 메우는 방향. 09:30 즉시진입이 첫봉대기보다 우수.
# 미검증(표본 6~7): 되돌림 진입(R50/HOD)이 손절을 10→2건으로 줄임. 이번 포워드로 확인.
# ── 검증 스펙 (1시간봉 2년 n=87, 승률 62.1% PF 4.01, 대손실 0건) ──
GAP_MIN, GAP_MAX = 0.20, 1.50     # 갭 크기 (%)
GAP_COVER_MIN = 0.40              # 첫봉(09:30~10:30) 갭 커버율 하한
GAP_VIX_SKIP = 5.0                # 개장 VIX 변화 |x|>=5% 이면 스킵
GAP_TRAIL = 0.15                  # 갭필 후 트레일링 스탑 (%)
GAP_TIMECUT = dt.time(11, 30)     # 갭필 실패 시 강제청산 (핵심: 세타 방어)
GAP_CUT = dt.time(14, 0)          # 최종 마감
GAP_SIZES = [0.30, 0.40, 0.50, 0.60, 0.70]   # 병렬 비교할 사이징
GAP_CAPITAL = 2000.0              # 갭 트랙 mock 자본 (사이징별 각각 독립 운용)

# ── 매크로 유사일 브리핑 (참고용, 매매 신호 아님) ──────────
MACRO_FEATS = {"^TNX":"10Y","^TYX":"30Y","^FVX":"5Y","CL=F":"WTI","DX-Y.NYB":"DXY",
               "^VIX":"VIX","GC=F":"GOLD","HG=F":"COPPER","HYG":"HY","TLT":"TLT",
               "EURUSD=X":"EUR","JPY=X":"JPY","^N225":"NIKKEI","^GDAXI":"DAX",
               "ES=F":"ES","NQ=F":"NQ","RTY=F":"RTY"}
MACRO_TOPN = 12
# 갭업 → 풋, 갭다운 → 콜. 델타 0.70~0.80 ITM 1계약.

# ── VIX 기간구조 게이트 ────────────────────────────────────
# 전날 종가 ^VIX9D/^VIX3M 의 252일 rolling 백분위.
# 하위 20% = 콘탱고 과도 = 다음날 안 움직이는 날 -> 0DTE 방향베팅 금지.
# 근거(3년, look-ahead 없음): 하위20 큰날비율 11.9% vs 상위20 72.2%,
#   SPY 레인지 중앙값 0.676% vs 1.442%, 반반검증 통과(12.7/11.1 · 75.5/67.6).
VIX_GATE_ON   = True     # False 로 두면 표시만 하고 진입은 막지 않음
VIX_GATE_PCT  = 50.0     # v9 검증(501일): 이 백분위 이상에서만 엣지 확인됨
VIX_LOOKBACK  = 252
PM_GATE_ON    = True     # 프리마켓 위치 게이트 (v9: pos>0.5 롱만 PF 1.69)
PM_POS_MIN    = 0.5

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

def _grab_close(tk, tries=4):
    """레이트리밋 대응: 지수 백오프 재시도."""
    import time
    for i in range(tries):
        try:
            s = yf.Ticker(tk).history(period="2y")["Close"].dropna()
            if len(s) >= VIX_LOOKBACK + 5:
                return s
        except Exception:
            pass
        time.sleep(5 * (2 ** i))          # 5, 10, 20, 40초
    return None


def vix_gate():
    """전날 종가 기준 VIX 기간구조 백분위. 실패하면 ERR (게이트 미적용)."""
    try:
        a = _grab_close("^VIX9D")
        b = _grab_close("^VIX3M")
        if a is None or b is None:
            return dict(state="ERR", msg=f"수집실패 9D={a is not None} 3M={b is not None}",
                        pct=0.0, ratio=0.0, asof="-")
        if len(a) < VIX_LOOKBACK + 5 or len(b) < VIX_LOOKBACK + 5:
            return dict(state="ERR", msg=f"표본부족 VIX9D={len(a)} VIX3M={len(b)}",
                        pct=0.0, ratio=0.0, asof="-")
        for x in (a, b):
            try: x.index = x.index.tz_localize(None)
            except (TypeError, AttributeError): pass
        ts = (a / b.reindex(a.index).ffill()).dropna()
        w = ts.tail(VIX_LOOKBACK).values
        cur = float(w[-1])
        pct = float((w[:-1] < cur).sum()) / (len(w) - 1) * 100
        state = "LIVE" if pct >= VIX_GATE_PCT else "DEAD"
        return dict(ratio=round(cur, 4), pct=round(pct, 1), state=state,
                    asof=str(ts.index[-1].date()))
    except Exception as e:
        print(f"  VIX 게이트 조회 실패: {type(e).__name__}: {e}")
        return dict(state="ERR", msg=f"{type(e).__name__}: {e}"[:200],
                    pct=0.0, ratio=0.0, asof="-")


def macro_match():
    """09:30 확정 매크로 지표의 개장 변화율을 z-score 벡터로 만들어
    과거 2년에서 유사일을 찾는다. 방향 예측이 아니라 '어떤 날들과 닮았나' 참고용."""
    try:
        def _nz(d):
            try: d.index = d.index.tz_localize(None)
            except (TypeError, AttributeError): pass
            d.index = pd.to_datetime(d.index).normalize()
            return d[~d.index.duplicated(keep="last")]
        cols = {}
        for tk, nm in MACRO_FEATS.items():
            try:
                d = _nz(yf.Ticker(tk).history(period="2y")[["Open", "Close"]].dropna())
                cols[nm] = (d["Open"] / d["Close"].shift(1) - 1) * 100
            except Exception:
                pass
        if len(cols) < 8: return None
        F = pd.DataFrame(cols)
        cov = F.notna().mean()
        F = F[[c for c in F.columns if cov[c] >= 0.90]]
        Z = ((F - F.mean()) / F.std()).fillna(0.0)

        q = _nz(yf.Ticker(TICKER).history(period="2y")[["Open", "High", "Low", "Close"]].dropna())
        tgt = pd.DataFrame({"ret": (q["Close"] / q["Open"] - 1) * 100,
                            "lo": (q["Low"] / q["Open"] - 1) * 100,
                            "hi": (q["High"] / q["Open"] - 1) * 100,
                            "gap": (q["Open"] / q["Close"].shift(1) - 1) * 100})
        df = Z.join(tgt, how="inner").dropna(subset=["ret", "lo", "hi", "gap"])
        if len(df) < 100: return None
        fc = [c for c in Z.columns if c in df.columns]
        today = df.index[-1]; hist = df.iloc[:-1].copy()
        v0 = df.loc[today, fc].values.astype(float)
        M = hist[fc].values.astype(float)
        hist["dist"] = np.sqrt(((M - v0) ** 2).sum(axis=1))
        hist = hist.sort_values("dist")
        top = hist.head(MACRO_TOPN)

        raw = F.loc[today]
        pcts = {c: float((hist[c] < df.loc[today, c]).mean() * 100) for c in fc}
        ext = sorted(fc, key=lambda c: -abs(pcts[c] - 50))[:4]
        return dict(
            date=str(today.date()), n_hist=len(hist), n_feat=len(fc),
            extremes=[dict(name=c, chg=round(float(raw[c]), 2), pct=round(pcts[c])) for c in ext],
            up=[dict(d=str(i.date()), dist=round(r["dist"], 2), gap=round(r["gap"], 2),
                     ret=round(r["ret"], 2), lo=round(r["lo"], 2), hi=round(r["hi"], 2))
                for i, r in top.iterrows() if r["ret"] > 0],
            dn=[dict(d=str(i.date()), dist=round(r["dist"], 2), gap=round(r["gap"], 2),
                     ret=round(r["ret"], 2), lo=round(r["lo"], 2), hi=round(r["hi"], 2))
                for i, r in top.iterrows() if r["ret"] <= 0],
            rng=round(float((top["hi"] - top["lo"]).mean()), 3),
            base_rng=round(float((hist["hi"] - hist["lo"]).mean()), 3),
            lo_avg=round(float(top["lo"].mean()), 3), hi_avg=round(float(top["hi"].mean()), 3),
            base_up=round(float((hist["ret"] > 0).mean() * 100), 1))
    except Exception as e:
        print(f"  매크로 매칭 실패: {e}")
        return None


def gap_signal(df, st):
    """당일 갭 신호. 09:30 시가 vs 전날 종가. 되돌림 진입 후보도 같이 계산."""
    try:
        d = df.copy()
        days = sorted(set(d.index.date))
        if len(days) < 2: return dict(state="ERR", msg=f"거래일 {len(days)}일뿐")
        today, prev = days[-1], days[-2]
        pcl = float(d[d.index.date == prev]["Close"].iloc[-1])
        rt = d[(d.index.date == today) & (d.index.time >= dt.time(9, 30))
               & (d.index.time < dt.time(16, 0))]
        if len(rt) < 1: return dict(state="ERR", msg=f"{today} 정규장 봉 없음")
        op = float(rt["Open"].iloc[0])
        gp = (op - pcl) / pcl * 100
        if not (GAP_MIN <= abs(gp) < GAP_MAX):
            return dict(state="NO_GAP", gap=round(gp, 3), prev_close=round(pcl, 2),
                        open=round(op, 2))
        now_t = dt.datetime.now(NY).time()
        sgn = 1 if gp > 0 else -1
        gapabs = abs(op - pcl)
        H = [float(x) for x in rt["High"]]; L = [float(x) for x in rt["Low"]]
        C = [float(x) for x in rt["Close"]]
        cur = C[-1]
        # 첫 1시간(09:30~10:30) 종가 기준 커버율 — 5분봉이면 12번째 봉
        idx1h = min(11, len(C) - 1)
        c1h = C[idx1h]
        cover = ((op - c1h) / (op - pcl)) if sgn > 0 else ((c1h - op) / abs(op - pcl))
        ready = now_t >= dt.time(10, 30)          # 첫봉 확정 여부
        # 갭필 도달 여부 + 도달 후 극점(트레일링용)
        gfilled = False; gext = None
        for i in range(idx1h, len(C)):
            if (L[i] <= pcl) if sgn > 0 else (H[i] >= pcl):
                gfilled = True
                gext = min(L[i:]) if sgn > 0 else max(H[i:])
                break
        # 되돌림 진입 후보: 눌림 후 50% 재회복 지점
        ext = min(L) if sgn > 0 else max(H)
        r50 = ext + (op - ext) * 0.5

        # VWAP 밴드 터치 추적 (역방향 밴드 = 되돌림 진입 자리)
        V = [float(x) for x in rt["Volume"]]
        T = [t.strftime("%H:%M") for t in rt.index]
        cpv = cv = cpv2 = 0.0; band_hit = None; band_px = None; band_t = None
        for i in range(len(C)):
            tp = (H[i] + L[i] + C[i]) / 3
            cpv += tp * V[i]; cv += V[i]; cpv2 += tp * tp * V[i]
            w = cpv / cv if cv else tp
            sd = math.sqrt(max(cpv2 / cv - w * w, 0.0)) if cv else 0.0
            if band_hit is None and sd > 1e-9 and i >= 1:
                lvl = w + sd if sgn > 0 else w - sd     # 갭업=숏이면 상단에서 진입
                if (H[i] >= lvl) if sgn > 0 else (L[i] <= lvl):
                    band_hit, band_px, band_t = i, round(lvl, 2), T[i]

        # MFE: 진입(시가) 기준 최대 유리 지점과 그 시각
        best = 0.0; best_t = None; best_px = None
        for i in range(len(C)):
            fav = (op - L[i]) if sgn > 0 else (H[i] - op)
            if fav > best:
                best = fav; best_t = T[i]; best_px = round(L[i] if sgn > 0 else H[i], 2)

        ok = ready and cover >= GAP_COVER_MIN
        trail_px = None
        if gfilled and gext is not None:
            trail_px = round(gext * (1 + GAP_TRAIL/100) if sgn > 0
                             else gext * (1 - GAP_TRAIL/100), 2)
        return dict(state=("ACTIVE" if ok else ("WAIT" if not ready else "LOW_COVER")),
                    gap=round(gp, 3), dir=("숏" if sgn > 0 else "롱"),
                    sgn=sgn, prev_close=round(pcl, 2), open=round(op, 2),
                    entry=round(c1h, 2), target=round(pcl, 2),
                    room=round(abs(pcl - c1h) / c1h * 100, 3),
                    cover=round(cover, 2), r50=round(r50, 2), cur=round(cur, 2),
                    filled=gfilled, trail=trail_px,
                    band_px=band_px, band_t=band_t,
                    band_room=(round(abs(pcl - band_px) / band_px * 100, 3) if band_px else None),
                    mfe=round(best / op * 100, 3), mfe_t=best_t, mfe_px=best_px)
    except Exception as e:
        import traceback
        print(f"  갭 신호 계산 실패: {e}")
        return dict(state="ERR", msg=f"{type(e).__name__}: {e}"[:180])


def premarket_pos():
    """프리마켓(04:00~09:30) 레인지 내 09:30 시가 위치. v9 검증: >0.5 롱만 엣지."""
    try:
        df = yf.download(TICKER, period="2d", interval="1h", prepost=True,
                         auto_adjust=False, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()
        df.index = df.index.tz_convert(NY)
        _days = sorted(set(df.index.date))
        if len(_days) < 1: return None
        today = _days[-1]
        g = df[df.index.date == today]
        pm = g[(g.index.time >= dt.time(4, 0)) & (g.index.time < dt.time(9, 30))]
        rt = g[g.index.time >= dt.time(9, 30)]
        if len(pm) < 3 or len(rt) < 1: return None
        pmh, pml = float(pm["High"].max()), float(pm["Low"].min())
        if pmh <= pml:
            return None
        op = float(rt["Open"].iloc[0])
        pos = (op - pml) / (pmh - pml)
        return dict(pos=round(pos, 3), pm_hi=round(pmh, 2), pm_lo=round(pml, 2),
                    ok=pos > PM_POS_MIN)
    except Exception as e:
        print(f"  프리마켓 조회 실패: {e}")
        return None


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
    day_lo = min(L)
    px = C[-1]
    dev = (px - vwap) / sd if sd > 1e-9 else 0.0
    score = 0
    score += 1 if gap >= 0.3 else (-1 if gap <= -0.3 else 0)
    score += 1 if e9 > e21 else -1
    score += 1 if px > vwap else -1
    score += 1 if rsi > 60 else (-1 if rsi < 40 else 0)
    direction = 1 if score >= SCORE_MIN else (-1 if score <= -SCORE_MIN else 0)
    return dict(px=px, vwap=vwap, sd=sd, bw=bw, dev=dev, gap=gap, rsi=rsi, score=score, day_lo=day_lo,
                direction=direction, e9=e9, e21=e21,
                band_lo=vwap - sd, band_hi=vwap + sd,
                stop_lo=vwap - 2 * sd, stop_hi=vwap + 2 * sd,
                ts=day.index[-1].strftime("%H:%M")), today, len(day)

# ───────────────────────── 옵션 ─────────────────────────
def opt_premium(strike, side, expiry):
    """특정 스트라이크 현재 프리미엄(mid)."""
    try:
        ch = yf.Ticker(TICKER).option_chain(expiry)
        df = ch.calls if side == "call" else ch.puts
        r = df[df["strike"] == strike]
        if r.empty: return None
        b = float(r["bid"].iloc[0] or 0); a = float(r["ask"].iloc[0] or 0)
        if b > 0 and a > 0: return round((b + a) / 2, 2)
        return round(float(r["lastPrice"].iloc[0] or 0), 2)
    except Exception:
        return None


def itm_opt(spot, expiry, side="call", cap=None):
    """델타 0.70~0.80 ITM 콜/풋. 콜은 스팟보다 낮은 스트라이크, 풋은 높은 스트라이크."""
    try:
        tk = yf.Ticker(TICKER)
        ch = tk.option_chain(expiry)
        df = ch.calls if side == "call" else ch.puts
        itm = df[df["strike"] < spot].copy() if side == "call" else df[df["strike"] > spot].copy()
        if itm.empty: return None
        target = spot * (0.992 if side == "call" else 1.008)
        itm["dist"] = (itm["strike"] - target).abs()
        itm = itm.sort_values("dist")
        budget = cap if cap is not None else CAPITAL_START
        for _, r in itm.iterrows():
            b = float(r.get("bid") or 0); a = float(r.get("ask") or 0)
            prem = round((b + a) / 2, 2) if (b > 0 and a > 0) else round(float(r.get("lastPrice") or 0), 2)
            if prem <= 0 or prem * 100 > budget: continue
            return dict(strike=float(r["strike"]), premium=prem, side=side,
                        iv=round(float(r.get("impliedVolatility") or 0), 4),
                        symbol=str(r.get("contractSymbol") or ""))
        return None
    except Exception as e:
        print(f"  ITM {side} 조회 실패: {e}")
        return None


def itm_call(spot, expiry):
    """델타 0.70~0.80 최근접 ITM 콜. yfinance 체인의 ITM 콜에서 스팟-스트라이크 거리로 근사 선택
    (yfinance는 그리스 미제공 -> 거리 기반: 델타 0.75 ~= 스팟-0.7%~0.9% 아래 스트라이크)."""
    try:
        tk = yf.Ticker(TICKER)
        ch = tk.option_chain(expiry)
        calls = ch.calls
        itm = calls[calls["strike"] < spot].copy()
        if itm.empty:
            return None
        # 목표 스트라이크: 스팟의 -0.6% ~ -1.0% 구간 중심 (-0.8%)
        target = spot * 0.992
        itm["dist"] = (itm["strike"] - target).abs()
        itm = itm.sort_values("dist")
        for _, r in itm.iterrows():
            b = float(r.get("bid") or 0); a = float(r.get("ask") or 0)
            prem = round((b + a) / 2, 2) if (b > 0 and a > 0) else round(float(r.get("lastPrice") or 0), 2)
            if prem <= 0:
                continue
            if prem * 100 > CAPITAL_START:      # 자본 초과 계약은 스킵
                continue
            return dict(strike=float(r["strike"]), premium=prem,
                        iv=round(float(r.get("impliedVolatility") or 0), 4),
                        symbol=str(r.get("contractSymbol") or ""))
        return None
    except Exception as e:
        print(f"  ITM 콜 조회 실패: {e}")
        return None


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
    vg = vix_gate()
    pmv = premarket_pos()
    gsig = gap_signal(df, st)
    log["gap"] = gsig
    log["macro"] = macro_match()
    if gsig and gsig.get("state") == "ACTIVE":
        gopen = log.get("gap_open")
        if gopen is None and log.get("gap_track", {}).get(dstr) is None:
            oside = "put" if gsig["sgn"] > 0 else "call"
            gopt = itm_opt(gsig["entry"], today_expiry(today), oside, 1e9)
            if gopt is None:
                print("  [갭] 신호 있으나 ITM 옵션 데이터 없음")
            else:
                prem = gopt["premium"]; cost = prem * 100
                books = log.setdefault("gap_books", {})
                entries = {}
                for f in GAP_SIZES:
                    key = str(int(f * 100))
                    bk = books.setdefault(key, dict(cap=GAP_CAPITAL, trades=[]))
                    entries[key] = int((bk["cap"] * f) // cost)
                log.setdefault("gap_track", {})[dstr] = True
                log["gap_open"] = dict(date=dstr, dir=gsig["dir"], sgn=gsig["sgn"],
                    gap=gsig["gap"], cover=gsig["cover"], entry=gsig["entry"],
                    target=gsig["target"], room=gsig["room"], r50=gsig["r50"],
                    at=now.strftime("%H:%M"), opt_side=oside,
                    strike=gopt["strike"], premium=prem, contracts=entries,
                    band_px=None, band_t=None, band_room=None,
                    mfe=0.0, mfe_t=None, mfe_prem=-99.0, mfe_prem_t=None,
                    filled=False, fill_t=None, res=None)
                print(f"  [갭] 진입 {gsig['dir']} 커버{gsig['cover']:.2f} "
                      f"{oside.upper()} {gopt['strike']:.0f} @${prem} · 계약 {entries}")

        gopen = log.get("gap_open")
        if gopen and gopen.get("res") is None:
            sgn = gopen["sgn"]; cur = gsig["cur"]
            if gsig.get("mfe", 0) > gopen.get("mfe", 0):
                gopen["mfe"], gopen["mfe_t"] = gsig["mfe"], gsig["mfe_t"]
            if gopen.get("band_px") is None and gsig.get("band_px"):
                gopen["band_px"] = gsig["band_px"]; gopen["band_t"] = gsig["band_t"]
                gopen["band_room"] = gsig["band_room"]
            if not gopen["filled"] and gsig.get("filled"):
                gopen["filled"] = True; gopen["fill_t"] = now.strftime("%H:%M")
                print(f"  [갭] 갭필 도달 {gopen['fill_t']} — 트레일링 전환")
            gcur = opt_premium(gopen["strike"], gopen["opt_side"], today_expiry(today))
            if gcur and gcur > 0:
                _p = (gcur / gopen["premium"] - 1) * 100
                if _p > gopen.get("mfe_prem", -99):
                    gopen["mfe_prem"] = round(_p, 1); gopen["mfe_prem_t"] = now.strftime("%H:%M")
            log["gap_open"] = gopen

            res = None
            if not gopen["filled"] and now.time() >= GAP_TIMECUT:
                res = "TIMECUT"
            elif gopen["filled"] and gsig.get("trail"):
                tp = gsig["trail"]
                if (cur >= tp) if sgn > 0 else (cur <= tp):
                    res = "TRAIL"
            elif now.time() >= GAP_CUT:
                res = "CUT"
            if res:
                exit_prem = gcur if (gcur and gcur > 0) else gopen["premium"]
                pnl_pct = round((exit_prem / gopen["premium"] - 1) * 100, 1)
                per_ct = round((exit_prem - gopen["premium"]) * 100, 2)
                ux = ((gopen["entry"] - cur) / gopen["entry"] * 100) if sgn > 0 \
                     else ((cur - gopen["entry"]) / gopen["entry"] * 100)
                books = log.setdefault("gap_books", {})
                for key, nc in gopen["contracts"].items():
                    bk = books.setdefault(key, dict(cap=GAP_CAPITAL, trades=[]))
                    usd = round(per_ct * nc, 2)
                    bk["cap"] = round(bk["cap"] + usd, 2)
                    bk["trades"].append(dict(d=dstr, nc=nc, usd=usd, pct=pnl_pct, res=res))
                rec = dict(gopen); rec.update(res=res, exit=round(cur, 2),
                    exit_at=now.strftime("%H:%M"), exit_premium=exit_prem,
                    pnl_pct=pnl_pct, per_contract=per_ct, ux=round(ux, 3))
                log.setdefault("gap_trades", []).append(rec)
                log["gap_open"] = None
                print(f"  [갭] 청산 {res} 프리미엄 {gopen['premium']}→{exit_prem} "
                      f"({pnl_pct:+.1f}%) 기초 {ux:+.3f}%")
    log["vix"] = vg                      # early return 경로에서도 화면에 남도록 즉시 저장
    log["pm"] = pmv
    if vg:
        print(f"  VIX게이트 {vg['state']} · 백분위 {vg['pct']:.1f}% · 비율 {vg['ratio']:.4f} (기준일 {vg['asof']})")
    else:
        print("  VIX게이트: 조회 실패 — 미적용")

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
        # ── 기초자산 트리거 (v10 검증 C안) ──
        px = st["px"]; w = st["vwap"]; s_ = st["sd"]
        # 최대 유리 지점(MFE)과 그 시각 — 사후 최적 청산 분석용
        _mfe = (px / open_pos["entry_px"] - 1) * 100
        if _mfe > open_pos.get("mfe", -99):
            open_pos["mfe"] = round(_mfe, 3); open_pos["mfe_t"] = now.strftime("%H:%M")
        if cur_prem and cur_prem > 0:
            _pm = (cur_prem / open_pos["premium"] - 1) * 100
            if _pm > open_pos.get("mfe_prem", -99):
                open_pos["mfe_prem"] = round(_pm, 1); open_pos["mfe_prem_t"] = now.strftime("%H:%M")
        # TP1: VWAP 도달 -> 가치 50% 청산 기록 (1계약 mock)
        if not open_pos.get("tp1_prem") and px >= w and cur_prem and cur_prem > 0:
            open_pos["tp1_prem"] = cur_prem
            open_pos["tp1_time"] = now.strftime("%H:%M")
            log["open"] = open_pos
            print(f"  TP1 도달(VWAP {w:.2f}) · 프리미엄 ${cur_prem} 에서 50% 가치 청산 기록")
        # 러너 목표: +1σ / 손절: 당일저점 이탈 / 시간청산
        runner_hit = px >= w + s_ if s_ > 1e-9 else False
        stop_hit = px <= open_pos.get("stop_px", 0)
        if stop_hit:
            reason = "STOP(당일저점)" if not open_pos.get("tp1_prem") else "STOP_AFTER_TP1"
        elif open_pos.get("tp1_prem") and runner_hit:
            reason = "RUNNER(+1σ)"
        elif now.time() >= CUTOFF:
            reason = "CUTOFF(14:30)"
        if reason:
            exit_prem = cur_prem
            if exit_prem is None or exit_prem <= 0:
                exit_prem = open_pos["premium"]        # 조회 실패 시 보수적으로 본전 처리
            t1 = open_pos.get("tp1_prem")
            eff_exit = round(0.5 * t1 + 0.5 * exit_prem, 2) if t1 else exit_prem
            pnl_pct = (eff_exit / open_pos["premium"] - 1) * 100
            pnl_usd = round((eff_exit - open_pos["premium"]) * 100, 2)
            tr = dict(open_pos)
            tr.update(exit_time=now.strftime("%H:%M"), exit_px=round(px, 2),
                      exit_premium=exit_prem, eff_exit=eff_exit,
                      pnl_pct=round(pnl_pct, 1), pnl_usd=pnl_usd, reason=reason)
            log.setdefault("trades", []).append(tr)
            log["open"] = None
            print(f"  청산: {reason} 유효단가 {open_pos['premium']}→{eff_exit} ({pnl_pct:+.1f}% / ${pnl_usd:+.2f})")
            save_log(log); return log, st
        log["open"] = open_pos
        print("  보유 중 — 조건 미달")
        save_log(log); return log, st

    # ── 2) 신규 진입 체크 ──
    if now.time() >= CUTOFF:
        print("  15:45 이후 — 신규 진입 없음"); save_log(log); return log, st
    done_today = sum(1 for t in log.get("trades", []) if t.get("date") == dstr)
    if done_today >= MAX_PER_DAY:
        print(f"  오늘 {done_today}회 완료 (상한 {MAX_PER_DAY}) — 종료"); save_log(log); return log, st

    if VIX_GATE_ON and vg and vg["state"] == "DEAD":
        status = f"NO TRADE · VIX게이트 (백분위 {vg['pct']:.0f}% < {VIX_GATE_PCT:.0f})"
        print(f"  {status}")
    elif PM_GATE_ON and pmv and not pmv["ok"] and st["direction"] > 0:
        status = f"NO TRADE · 프리마켓 위치 {pmv['pos']:.2f} <= {PM_POS_MIN} (롱 엣지 없음)"
        print(f"  {status}")
    elif st["dev"] > -ENTRY_BAND_SIG:
        status = (f"WAIT · 3층 통과 (VIX {vg['pct']:.0f}% · PM {pmv['pos']:.2f}) "
                  f"· VWAP -1σ 터치 대기 (현재 {st['dev']:+.2f}σ)")
    else:
        cap = CAPITAL_START + sum(t.get("pnl_usd", 0) for t in log.get("trades", []))
        opt = itm_call(st["px"], today_expiry(today))
        if not opt:
            status = "진입 조건 충족 · ITM 콜 데이터 없음"
        elif opt["premium"] * 100 > cap:
            status = f"SKIP_FUND · 프리미엄 ${opt['premium']*100:.0f} > 잔고 ${cap:.0f}"
        else:
            log["open"] = dict(date=dstr, side="call", mfe=-99.0, mfe_t=None,
                               mfe_prem=-99.0, mfe_prem_t=None, strike=opt["strike"],
                               premium=opt["premium"], iv=opt["iv"], symbol=opt["symbol"],
                               entry_time=now.strftime("%H:%M"), entry_px=round(st["px"], 2),
                               score=st["score"], gap=round(st["gap"], 2), rsi=round(st["rsi"], 1),
                               stop_px=round(st.get("day_lo", st["px"]) * 0.9995, 2),
                               version=VERSION,
                               vix_pct=(vg["pct"] if vg else None),
                               vix_state=(vg["state"] if vg else None),
                               pm_pos=(pmv["pos"] if pmv else None))
            status = f"진입 · BUY CALL {opt['strike']:.0f} @ ${opt['premium']} (잔고 ${cap:.0f})"
            print(f"  {status}")
    log["days"][dstr] = dict(status=status, score=st["score"], rsi=round(st["rsi"], 1),
                             direction=st["direction"], gap=round(st["gap"], 2),
                             px=round(st["px"], 2), vwap=round(st["vwap"], 2),
                             at=now.strftime("%H:%M"),
                             vix_pct=(vg["pct"] if vg else None),
                             vix_state=(vg["state"] if vg else None),
                             pm_pos=(pmv["pos"] if pmv else None))
    print(f"  {status}")
    save_log(log); return log, st

# ───────────────────────── 화면 ─────────────────────────
def render(log, st):
    vg = log.get("vix"); pmv = log.get("pm"); op = log.get("open")
    trades = log.get("trades", [])
    itm = [t for t in trades if str(t.get("version","")).startswith("itm")]
    n = len(itm)
    wins = sum(1 for t in itm if t["pnl_pct"] > 0)
    wr = round(wins / n * 100, 1) if n else None
    tot_usd = round(sum(t.get("pnl_usd", 0) for t in itm), 2)
    bal = round(CAPITAL_START + tot_usd, 2)
    now = dt.datetime.now(NY).strftime("%Y-%m-%d %H:%M ET")

    # ── L1/L2/L3 게이트 판정 ──
    def lamp(state):  # go / nogo / stby
        return f'<span class="lamp {state}"></span>'
    if vg and vg.get("state") == "LIVE":
        l1, l1s = "go", f'GO&nbsp;&nbsp;&nbsp;· 백분위 {vg["pct"]:.0f}% · TS {vg["ratio"]:.3f}'
    elif vg and vg.get("state") == "DEAD":
        l1, l1s = "nogo", f'NO-GO · 백분위 {vg["pct"]:.0f}% &lt; 50 · 기준 {vg["asof"]}'
    else:
        l1, l1s = "stby", "STANDBY · 데이터 수집 실패 — 게이트 미적용"
    if pmv and pmv.get("ok"):
        l2, l2s = "go", f'GO&nbsp;&nbsp;&nbsp;· PM위치 {pmv["pos"]:.2f} &gt; 0.5 ({pmv["pm_lo"]}~{pmv["pm_hi"]})'
    elif pmv:
        l2, l2s = "nogo", f'NO-GO · PM위치 {pmv["pos"]:.2f} ≤ 0.5 — 롱 엣지 없음'
    else:
        l2, l2s = "stby", "STANDBY · 프리마켓 데이터 없음"
    if st is None:
        l3, l3s = "stby", "STANDBY · 장외 / 세션 준비 중"
    elif op:
        l3, l3s = "go", "ENGAGED · 포지션 보유 중"
    elif st["dev"] <= -ENTRY_BAND_SIG:
        l3, l3s = "go", f'GO&nbsp;&nbsp;&nbsp;· VWAP -1σ 터치 ({st["dev"]:+.2f}σ)'
    else:
        l3, l3s = "stby", f'STANDBY · -1σ 대기 (현재 {st["dev"]:+.2f}σ)'

    if op:
        verdict, vc = "POSITION ACTIVE", "go"
    elif l1 == "nogo" or l2 == "nogo":
        verdict, vc = "HOLD — NO ENTRY TODAY", "nogo"
    elif l1 == "go" and l2 == "go" and l3 == "go":
        verdict, vc = "ENTRY WINDOW OPEN", "go"
    else:
        verdict, vc = "STANDBY — MONITORING", "stby"

    gate = (f'<div class="panel"><div class="ph">MISSION STATUS · 3-LAYER GATE</div>'
            f'<div class="gr">{lamp(l1)}<span class="gl">L1 VOLATILITY</span><span class="gs">{l1s}</span></div>'
            f'<div class="gr">{lamp(l2)}<span class="gl">L2 DIRECTION</span><span class="gs">{l2s}</span></div>'
            f'<div class="gr">{lamp(l3)}<span class="gl">L3 TRIGGER</span><span class="gs">{l3s}</span></div>'
            f'<div class="verdict {vc}">▶ {verdict}</div></div>')

    # ── 포지션 패널 ──
    if op:
        t1 = op.get("tp1_prem")
        pos_html = (f'<div class="panel hot"><div class="ph">ACTIVE POSITION</div>'
                    f'<div class="big">ITM CALL {op["strike"]:.0f} <span class="dim">@ ${op["premium"]}</span></div>'
                    f'<div class="meta">진입 {op["entry_time"]} · 기초 {op["entry_px"]} · 손절(기초) {op.get("stop_px","-")}<br>'
                    f'{("TP1 완료 $" + str(t1) + " (" + str(op.get("tp1_time","")) + ") · 러너 +1σ 추적 중") if t1 else "TP1 대기 — VWAP 도달 시 50% 청산"}</div></div>')
    else:
        d = log.get("days", {}).get(str(dt.datetime.now(NY).date()), {})
        pos_html = (f'<div class="panel"><div class="ph">ACTIVE POSITION</div>'
                    f'<div class="big dim2">NONE</div>'
                    f'<div class="meta">{d.get("status", "세션 대기")}</div></div>')

    # ── 원장 ──
    rows = ""
    for t in reversed(itm[-40:]):
        c = "pos" if t["pnl_pct"] > 0 else "neg"
        mp = t.get("mfe_prem"); mp = None if (mp is None or mp < -90) else mp
        rows += (f'<tr><td>{t["date"][5:]}</td><td>C{t["strike"]:.0f}</td>'
                 f'<td>{t["entry_time"]}→{t["exit_time"]}</td>'
                 f'<td>${t["premium"]}→${t.get("eff_exit", t["exit_premium"])}</td>'
                 f'<td class="{c}">{t["pnl_pct"]:+.1f}%</td>'
                 f'<td class="{c}">${t.get("pnl_usd",0):+.0f}</td>'
                 f'<td class="pos">{f"{mp:+.0f}%" if mp is not None else "—"}'
                 f'<br><span class="rs">{t.get("mfe_prem_t","") or ""}</span></td>'
                 f'<td class="rs">{t["reason"]}</td></tr>')
    if not rows:
        rows = '<tr><td colspan="8" class="rs">NO OPERATIONS LOGGED — 3층 통과 시 자동 개시</td></tr>'

    # ── 갭 트랙 패널 ──
    gs = log.get("gap"); go = log.get("gap_open"); gts = log.get("gap_trades", [])
    books = log.get("gap_books", {})

    if gs is None:
        gstat, gcls, gdesc = "STANDBY", "stby", "장외 / 데이터 없음"
    elif gs.get("state") == "NO_GAP":
        gstat, gcls = "NO-GO", "nogo"
        gdesc = f'갭 {gs["gap"]:+.2f}% — 대상({GAP_MIN}~{GAP_MAX}%) 밖'
    elif gs.get("state") == "WAIT":
        gstat, gcls = "WAIT", "stby"
        gdesc = f'갭 {gs["gap"]:+.2f}% · 첫봉(10:30) 확정 대기'
    elif gs.get("state") == "ERR" or "sgn" not in gs:
        gstat, gcls = "STANDBY", "stby"
        gdesc = f'신호 계산 실패: {gs.get("msg", "사유 불명")}'
    elif gs.get("state") == "LOW_COVER":
        gstat, gcls = "NO-GO", "nogo"
        gdesc = f'갭 {gs["gap"]:+.2f}% · 커버 {gs["cover"]:.2f} &lt; {GAP_COVER_MIN} — 진입 안 함'
    else:
        gstat, gcls = "SIGNAL", "go"
        _a = "BUY PUT" if gs["sgn"] > 0 else "BUY CALL"
        gdesc = (f'갭 {gs["gap"]:+.2f}% · 커버 {gs["cover"]:.2f} · <b style="color:var(--amb)">{_a}</b>'
                 f'<br>타깃까지 {gs["room"]:.3f}%'
                 + (f' · 갭필 완료, 트레일 {gs.get("trail")}' if gs.get("filled") else ' · 갭필 대기'))

    if go:
        _a = "BUY PUT" if go["sgn"] > 0 else "BUY CALL"
        ct = " / ".join(f'{k}%:{v}계약' for k, v in sorted(go["contracts"].items(), key=lambda x: int(x[0])))
        gpos = (f'<div class="panel hot"><div class="ph">GAP · ACTIVE</div>'
                f'<div class="big">{_a} {go["strike"]:.0f} <span class="dim">@ ${go["premium"]}</span></div>'
                f'<div class="meta">진입 {go["at"]} · 커버 {go["cover"]:.2f} · 기초 {go["entry"]} → 타깃 {go["target"]}'
                f'<br>{ct}'
                f'<br>{"갭필 " + str(go["fill_t"]) + " · 트레일 추적" if go["filled"] else "갭필 대기 · 11:30 미달성 시 청산"}</div></div>')
    else:
        gpos = ('<div class="panel"><div class="ph">GAP · ACTIVE</div>'
                '<div class="big dim2">NONE</div>'
                f'<div class="meta">{gdesc}</div></div>')

    # 사이징 비교표
    srows = ""
    for f in GAP_SIZES:
        k = str(int(f * 100))
        bk = books.get(k, dict(cap=GAP_CAPITAL, trades=[]))
        cap = bk["cap"]; tr = bk["trades"]
        pl = cap - GAP_CAPITAL
        gw = sum(1 for t in tr if t["usd"] > 0)
        gwr_s = f"{gw/len(tr)*100:.0f}%" if tr else "—"
        peak = GAP_CAPITAL; mdd = 0.0; c = GAP_CAPITAL
        for t in tr:
            c += t["usd"]; peak = max(peak, c); mdd = max(mdd, (peak - c) / peak * 100)
        cls = "pos" if pl > 0 else ("neg" if pl < 0 else "")
        srows += (f'<tr><td><b>{k}%</b></td><td>${cap:,.0f}</td>'
                  f'<td class="{cls}">{pl:+,.0f}</td><td>{len(tr)}</td><td>{gwr_s}</td>'
                  f'<td class="rs">{mdd:.1f}%</td>'
                  f'<td class="rs">{tr[-1]["nc"] if tr else 0}</td></tr>')

    grows = ""
    for i, t in enumerate(reversed([x for x in gts if "cover" in x][-30:])):
        c = "pos" if (t.get("pnl_pct") or 0) > 0 else "neg"
        _a = "PUT" if t["sgn"] > 0 else "CALL"
        mf = t.get("mfe_prem"); mf = None if (mf is None or mf < -90) else mf
        ct = " · ".join(f'{k}%: {v}계약' for k, v in
                        sorted(t.get("contracts", {}).items(), key=lambda x: int(x[0])))
        bp = t.get("band_px")
        mfe_str = f"{mf:+.0f}% @ {t.get('mfe_prem_t') or ''}" if mf is not None else "—"
        band_str = f"{bp} ({t.get('band_t') or ''})" if bp else "미도달"
        det = (
          f'<div class="dgrid">'
          f'<div><span class="dk">갭 커버</span><span class="dv">{t["cover"]:.2f}</span></div>'
          f'<div><span class="dk">갭 크기</span><span class="dv">{t["gap"]:+.2f}%</span></div>'
          f'<div><span class="dk">진입 시각</span><span class="dv">{t["at"]}</span></div>'
          f'<div><span class="dk">진입가(기초)</span><span class="dv">{t["entry"]}</span></div>'
          f'<div><span class="dk">갭필 시각</span><span class="dv">{t.get("fill_t") or "미달성"}</span></div>'
          f'<div><span class="dk">타깃</span><span class="dv">{t["target"]}</span></div>'
          f'<div><span class="dk">청산 시각</span><span class="dv">{t.get("exit_at","")}</span></div>'
          f'<div><span class="dk">청산 사유</span><span class="dv">{t["res"]}</span></div>'
          f'<div><span class="dk">계약</span><span class="dv">{_a} {t["strike"]:.0f}</span></div>'
          f'<div><span class="dk">프리미엄</span><span class="dv">${t["premium"]}→${t.get("exit_premium","")}</span></div>'
          f'<div><span class="dk">옵션 손익</span><span class="dv {c}">{t.get("pnl_pct",0):+.1f}% '
          f'(${t.get("per_contract",0):+.0f}/계약)</span></div>'
          f'<div><span class="dk">기초 손익</span><span class="dv">{t.get("ux",0):+.3f}%</span></div>'
          f'<div><span class="dk">최고 지점</span><span class="dv pos">'
          f'{f"{mf:+.0f}% @ {t.get(chr(34)+chr(34)) or t.get("mfe_prem_t") or ""}" if mf is not None else "—"}</span></div>'
          f'<div><span class="dk">VWAP밴드 자리</span><span class="dv">'
          f'{f"{bp} ({t.get(chr(39)+chr(39)) or t.get(chr(34)+chr(34)) or t.get("band_t") or ""})" if bp else "미도달"}</span></div>'
          f'<div class="dfull"><span class="dk">사이징별 계약수</span><span class="dv">{ct or "—"}</span></div>'
          f'</div>')
        grows += (f'<tr class="crow" data-i="{i}"><td>{t["date"][5:]}</td>'
                  f'<td>{_a}</td><td>{t["gap"]:+.2f}%</td><td>{t["cover"]:.2f}</td>'
                  f'<td class="{c}">{t.get("pnl_pct",0):+.0f}%</td>'
                  f'<td class="rs">{t["res"]}</td><td class="rs">▾</td></tr>'
                  f'<tr class="drow" id="d{i}"><td colspan="7">{det}</td></tr>')
    if not grows:
        grows = '<tr><td colspan="7" class="rs">NO OPERATIONS — 갭 0.2~1.5% & 커버 40%+ 발생 시 개시</td></tr>'

    # ── 매크로 유사일 패널 ──
    mm = log.get("macro")
    if not mm:
        mac_html = ('<div class="panel"><div class="ph">MACRO PATTERN MATCH</div>'
                    '<div class="big dim2">NO DATA</div>'
                    '<div class="meta">매크로 지표 수집 실패 — 다음 실행에서 재시도</div></div>')
    else:
        nu, nd = len(mm["up"]), len(mm["dn"])
        tot = max(nu + nd, 1)
        upct = nu / tot * 100

        chips = ""
        for e in mm["extremes"]:
            hot = "hi" if e["pct"] >= 85 else ("lo" if e["pct"] <= 15 else "")
            chips += (f'<div class="chip {hot}"><div class="cn">{e["name"]}</div>'
                      f'<div class="cv">{e["chg"]:+.2f}%</div>'
                      f'<div class="cp">{e["pct"]:.0f}<span>%tile</span></div></div>')

        def _lst(lst, cls, arrow):
            r = ""
            for x in lst:
                r += (f'<div class="mrow"><span class="md">{x["d"][5:]}</span>'
                      f'<span class="mg">갭 {x["gap"]:+.2f}</span>'
                      f'<span class="mr {cls}">{arrow} {x["ret"]:+.2f}%</span></div>')
            return r or '<div class="mrow"><span class="rs">해당 없음</span></div>'

        mac_html = (
            f'<div class="panel"><div class="ph">오늘 매크로 · 가장 극단인 4개</div>'
            f'<div class="chips">{chips}</div>'
            f'<div class="meta" style="margin-top:10px">과거 {mm["n_hist"]}일 대비 백분위 '
            f'· 지표 {mm["n_feat"]}개로 유사일 검색</div></div>'

            f'<div class="panel hot"><div class="ph">오늘 예상 움직임 폭</div>'
            f'<div class="big">{mm["rng"]:.2f}%</div>'
            f'<div class="meta">유사일 평균 레인지 · 전체 평균 {mm["base_rng"]:.2f}%'
            f'<br>저점 {mm["lo_avg"]:+.2f}% · 고점 {mm["hi_avg"]:+.2f}% (09:30 기준)</div></div>'

            f'<div class="panel"><div class="ph">유사했던 {tot}일의 결말</div>'
            f'<div class="split"><div class="sbar">'
            f'<div class="sup" style="width:{upct:.0f}%"></div>'
            f'<div class="sdn" style="width:{100-upct:.0f}%"></div></div>'
            f'<div class="slab"><span class="pos">▲ {nu}일 상승</span>'
            f'<span class="neg">{nd}일 하락 ▼</span></div></div>'
            f'<div class="mgrid">'
            f'<div class="mcol"><div class="mh pos">▲ 올랐던 날</div>{_lst(mm["up"],"pos","▲")}</div>'
            f'<div class="mcol"><div class="mh neg">▼ 빠졌던 날</div>{_lst(mm["dn"],"neg","▼")}</div>'
            f'</div></div>')

    legacy = len(trades) - n
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OP ZERO-DAY</title>
<link rel="manifest" href="manifest.webmanifest">
<meta name="theme-color" content="#050807">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="ZERO-DAY">
<link rel="apple-touch-icon" href="icon-192.png">
<link rel="icon" href="icon-192.png" type="image/png">
<link href="https://fonts.googleapis.com/css2?family=Michroma&family=IBM+Plex+Mono:wght@400;500;600&family=Noto+Sans+KR:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--bg:#050807;--pn:#0a0f0c;--ln:#1c2822;--amb:#e8b04b;--ambd:#8a6c33;--tx:#cfe0d6;--mut:#5f7268;--red:#e84545;--grn:#49d17c}}
*{{margin:0;padding:0;box-sizing:border-box}}
html{{background:var(--bg)}}
body{{background:
  repeating-linear-gradient(0deg,rgba(255,255,255,.018) 0 1px,transparent 1px 3px),
  radial-gradient(1200px 500px at 50% -10%,rgba(232,176,75,.05),transparent),
  var(--bg);
  color:var(--tx);font-family:'IBM Plex Mono','Noto Sans KR',monospace;
  padding:0 14px 40px;max-width:640px;margin:0 auto;font-size:12px}}
.cls{{background:var(--red);color:#fff;font-size:9.5px;letter-spacing:.28em;text-align:center;
  padding:5px 4px;margin:0 -14px;font-weight:600;text-transform:uppercase}}
.cls.bt{{margin-top:26px}}
header{{display:flex;align-items:baseline;gap:12px;padding:16px 2px 12px;border-bottom:1px solid var(--ln)}}
.op{{font-family:'Michroma',monospace;font-size:15px;letter-spacing:.14em;color:var(--amb);
  text-shadow:0 0 12px rgba(232,176,75,.45)}}
.sub{{font-size:9px;letter-spacing:.2em;color:var(--mut);text-transform:uppercase}}
.ts{{margin-left:auto;font-size:10.5px;color:var(--ambd);text-align:right;line-height:1.6}}
.panel{{position:relative;background:var(--pn);border:1px solid var(--ln);padding:14px 16px;margin:14px 0}}
.panel::before,.panel::after{{content:"";position:absolute;width:12px;height:12px;border:1px solid var(--amb);opacity:.7}}
.panel::before{{top:-1px;left:-1px;border-right:0;border-bottom:0}}
.panel::after{{bottom:-1px;right:-1px;border-left:0;border-top:0}}
.panel.hot{{box-shadow:inset 0 0 30px rgba(232,176,75,.06)}}
.ph{{font-size:9px;letter-spacing:.24em;color:var(--ambd);text-transform:uppercase;margin-bottom:11px}}
.gr{{display:flex;align-items:baseline;gap:10px;padding:7px 0;border-bottom:1px dashed rgba(95,114,104,.25)}}
.gr:last-of-type{{border-bottom:none}}
.lamp{{width:9px;height:9px;border-radius:50%;flex:0 0 9px;position:relative;top:1px}}
.lamp.go{{background:var(--grn);box-shadow:0 0 9px var(--grn)}}
.lamp.nogo{{background:var(--red);box-shadow:0 0 9px var(--red)}}
.lamp.stby{{background:var(--ambd);box-shadow:0 0 7px rgba(232,176,75,.5)}}
.gl{{font-size:11px;letter-spacing:.1em;color:var(--tx);width:112px;flex:0 0 112px}}
.gs{{font-size:10.5px;color:var(--mut);line-height:1.55}}
.verdict{{margin-top:12px;padding:9px 12px;font-size:12px;letter-spacing:.14em;border:1px solid}}
.verdict.go{{color:var(--grn);border-color:rgba(73,209,124,.4);background:rgba(73,209,124,.06);text-shadow:0 0 10px rgba(73,209,124,.5)}}
.verdict.nogo{{color:var(--red);border-color:rgba(232,69,69,.4);background:rgba(232,69,69,.06)}}
.verdict.stby{{color:var(--amb);border-color:rgba(232,176,75,.35);background:rgba(232,176,75,.05)}}
.big{{font-size:19px;font-weight:600;letter-spacing:.03em;color:var(--amb);text-shadow:0 0 14px rgba(232,176,75,.35)}}
.big.dim2{{color:var(--mut);text-shadow:none}}
.dim{{color:var(--mut);font-weight:400;font-size:14px}}
.meta{{margin-top:8px;font-size:10.5px;color:var(--mut);line-height:1.8}}
.stats{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:14px 0}}
.st{{background:var(--pn);border:1px solid var(--ln);padding:10px 8px;text-align:center}}
.st .k{{font-size:8.5px;letter-spacing:.16em;color:var(--mut)}}
.st .v{{font-size:15px;font-weight:600;margin-top:5px;color:var(--tx)}}
.pos{{color:var(--grn)}}.neg{{color:var(--red)}}
table{{width:100%;border-collapse:collapse;background:var(--pn);border:1px solid var(--ln)}}
th{{font-size:8.5px;letter-spacing:.12em;color:var(--ambd);text-align:left;padding:8px 7px;
  border-bottom:1px solid var(--ln);text-transform:uppercase}}
td{{font-size:11px;padding:8px 7px;border-bottom:1px solid rgba(28,40,34,.6)}}
tr:last-child td{{border-bottom:none}}
.rs{{color:var(--mut);font-size:10px}}
.brief{{font-size:10.5px;color:var(--mut);line-height:1.9;margin-top:16px;padding:12px 14px;
  border:1px dashed var(--ln)}}
.tabs{{display:flex;gap:0;margin:14px 0 0;border-bottom:1px solid var(--ln)}}
.tab{{flex:1;padding:11px 8px;text-align:center;font-size:10.5px;letter-spacing:.14em;
  color:var(--mut);cursor:pointer;border:1px solid transparent;border-bottom:none;
  text-transform:uppercase;background:transparent;font-family:'IBM Plex Mono',monospace}}
.tab.on{{color:var(--amb);border-color:var(--ln);background:var(--pn);
  text-shadow:0 0 10px rgba(232,176,75,.4)}}
.track{{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;
  -webkit-overflow-scrolling:touch;scrollbar-width:none;margin:0 -14px;padding:0 14px;gap:28px}}
.track::-webkit-scrollbar{{display:none}}
.tabpane{{flex:0 0 100%;scroll-snap-align:start;min-width:0}}
.dots{{display:flex;justify-content:center;gap:7px;margin:16px 0 4px}}
.dot{{width:6px;height:6px;border-radius:50%;background:var(--ln);transition:all .25s}}
.dot.on{{background:var(--amb);width:20px;border-radius:3px;box-shadow:0 0 8px rgba(232,176,75,.5)}}
.chips{{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}}
.chip{{background:rgba(255,255,255,.02);border:1px solid var(--ln);padding:9px 6px;text-align:center}}
.chip.hi{{border-color:rgba(232,69,69,.45);background:rgba(232,69,69,.07)}}
.chip.lo{{border-color:rgba(73,209,124,.4);background:rgba(73,209,124,.06)}}
.chip .cn{{font-size:9px;letter-spacing:.1em;color:var(--mut)}}
.chip .cv{{font-size:13px;font-weight:600;margin:4px 0 2px;color:var(--tx)}}
.chip .cp{{font-size:10px;color:var(--ambd)}}
.chip .cp span{{font-size:8px;opacity:.7}}
.split{{margin:2px 0 14px}}
.sbar{{display:flex;height:9px;border:1px solid var(--ln);overflow:hidden}}
.sup{{background:var(--grn);opacity:.75}}
.sdn{{background:var(--red);opacity:.75}}
.slab{{display:flex;justify-content:space-between;font-size:10.5px;margin-top:6px}}
.ltab .crow{{cursor:pointer}}
.ltab .crow:active{{background:rgba(232,176,75,.06)}}
.ltab .drow{{display:none}}
.ltab .drow.on{{display:table-row}}
.ltab .drow td{{background:rgba(255,255,255,.02);padding:12px 10px}}
.dgrid{{display:grid;grid-template-columns:1fr 1fr;gap:8px 14px}}
.dgrid>div{{display:flex;justify-content:space-between;gap:8px;
  border-bottom:1px dashed rgba(95,114,104,.2);padding-bottom:5px}}
.dgrid .dfull{{grid-column:1/-1}}
.dk{{font-size:9.5px;color:var(--mut);letter-spacing:.06em}}
.dv{{font-size:11px;color:var(--tx);text-align:right}}
@media (max-width:520px){{.dgrid{{grid-template-columns:1fr}}}}
.mgrid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.mcol{{min-width:0}}
.mh{{font-size:10px;letter-spacing:.12em;padding:0 0 8px;text-transform:uppercase;
  border-bottom:1px dashed rgba(95,114,104,.3);margin-bottom:6px}}
.mrow{{display:flex;justify-content:space-between;align-items:baseline;gap:4px;
  padding:5px 0;font-size:11px;border-bottom:1px solid rgba(28,40,34,.5)}}
.mrow:last-child{{border-bottom:none}}
.md{{color:var(--tx);flex:0 0 auto}}
.mg{{color:var(--mut);font-size:9.5px}}
.mr{{font-weight:600;flex:0 0 auto}}
@media (max-width:520px){{.mgrid{{grid-template-columns:1fr;gap:16px}}
  .chips{{grid-template-columns:repeat(2,1fr)}}}}
.brief b{{color:var(--ambd)}}
@media (prefers-reduced-motion:no-preference){{
  .lamp.go,.verdict.go{{animation:pulse 2.6s ease-in-out infinite}}
  @keyframes pulse{{50%{{opacity:.72}}}}
}}
</style></head><body>
<div class="cls">Mock Simulation // Training Use Only // Not Investment Advice</div>
<header><div><div class="op">OP&nbsp;ZERO-DAY</div><div class="sub">QQQ 0DTE · 3-Layer System</div></div>
<div class="ts">{now}<br>SYS {VERSION} · UPLINK 15MIN</div></header>
<div class="tabs">
  <button class="tab on" data-i="0">3-LAYER · ITM</button>
  <button class="tab" data-i="1">GAP FILL</button>
  <button class="tab" data-i="2">MACRO</button>
</div>
<div class="track" id="track">
<div class="tabpane">
{gate}
{pos_html}
<div class="panel"><div class="ph">FUND LEDGER · MOCK ${CAPITAL_START:.0f}</div>
<div class="stats">
  <div class="st"><div class="k">BAL</div><div class="v">${bal:.0f}</div></div>
  <div class="st"><div class="k">P/L</div><div class="v {'pos' if tot_usd>0 else ('neg' if tot_usd<0 else '')}">${tot_usd:+.0f}</div></div>
  <div class="st"><div class="k">OPS</div><div class="v">{n}</div></div>
  <div class="st"><div class="k">WIN</div><div class="v">{f"{wr:.0f}%" if wr is not None else "—"}</div></div>
  <div class="st"><div class="k">LEGACY</div><div class="v dim2" style="color:var(--mut)">{legacy}</div></div>
</div>
<table><tr><th>DATE</th><th>CONTRACT</th><th>WINDOW</th><th>FILL</th><th>P/L%</th><th>P/L$</th><th>MFE·시각</th><th>EXIT</th></tr>{rows}</table>
</div>
<div class="brief">
<b>RULES OF ENGAGEMENT</b> — L1 VIX9D/VIX3M 백분위 ≥50 · L2 프리마켓 위치 &gt;0.5 · L3 VWAP -1σ 터치
→ <b>ITM CALL 매수(BUY)</b> Δ0.7~0.8 × 1계약<br>
집행 — <b>전부 매수(BUY)</b>. 롱 온리 · 숏은 엣지 없음 확인되어 봉인 · 옵션 매도(SELL) 전략 아님<br>
EXIT — TP1 VWAP(가치 50%) → 러너 +1σ · 손절 당일저점 · 14:30 ET 강제청산 · 1 op/day<br>
근거 — v9 501거래일: 승률 63.1% · PF 1.69 · 반반 1.63/1.76 (QQQ 전용, 숏 봉인)<br>
LEGACY {legacy}건은 구버전(vwap-1.x) 기록으로 본 통계에서 제외. 프리미엄은 지연 mid 기준.
</div>
</div>
<div class="tabpane">
<div class="panel"><div class="ph">GAP STATUS</div>
<div class="gr"><span class="lamp {gcls}"></span><span class="gl">GAP FILL</span>
<span class="gs">{gstat} · {gdesc}</span></div>
<div class="verdict {gcls}">▶ {gstat}</div></div>
{gpos}
<div class="panel"><div class="ph">사이징 비교 · 각 ${GAP_CAPITAL:.0f} 독립 운용</div>
<table><tr><th>사이징</th><th>잔고</th><th>P/L</th><th>거래</th><th>승률</th><th>MDD</th><th>최근계약</th></tr>{srows}</table>
</div>
<div class="panel"><div class="ph">GAP LEDGER · ITM 0DTE 매수</div>
<table class="ltab"><tr><th>DATE</th><th>TYPE</th><th>GAP</th><th>커버</th><th>P/L</th><th>EXIT</th><th></th></tr>{grows}</table>
</div>
<div class="brief">
<b>GAP FILL · FORWARD TEST</b> — 갭 0.2~1.5% & 첫봉(10:30) 커버 40%+ → 갭 메우는 방향 진입<br>
갭필 도달 → 트레일 0.15% · <b>11:30까지 갭필 실패 시 청산</b>(세타 방어) · 14:00 최종컷<br>
가격 손절 없음 — 사이징이 손실 상한. 30/40/50/60/70% 다섯 계좌 병렬 비교<br>
집행 — <b>전부 매수(BUY)</b>. 갭업 → <b>ITM PUT</b> / 갭다운 → <b>ITM CALL</b> (Δ0.7)<br>
백테스트 — 1시간봉 2년 n=87 · 승률 62.1% · PF 4.01 · 대손실(-50%↓) 0건<br>
사이징별: 30% MDD 26% / 40% MDD 38% / 50% MDD 48% / 최장 5연패 · 최악 1회 -13~31%<br>
※ 11:30 시간컷이 핵심입니다 — 갭필 실패한 날 6시간 끌면서 세타로 프리미엄이 전액 날아갔고,
   2시간에 끊자 대손실 4건이 0건이 됐습니다. MFE로 더 나은 청산 시점이 있었는지 계속 검증합니다.
</div>
</div>
<div class="tabpane">
{mac_html}
<div class="brief">
<b>참고용 · 매매 신호 아님</b><br>
09:30에 확정된 금리·유가·달러·VIX·금·환율·해외지수·선물 17개를 z-score로 묶어
과거 2년에서 가장 닮은 날을 찾습니다.<br>
방향 적중은 48~60%로 <b>동전 던지기와 구별되지 않습니다.</b> 그래서 확률 하나로 뭉개지 않고
올랐던 날과 빠졌던 날을 그대로 보여줍니다 — 형님이 그날들을 보고 판단하시라고.<br>
실제로 쓸모 있는 건 <b>레인지</b>입니다. 방향이 아니라 "오늘 얼마나 움직일 장인가"요.
</div>
</div>
</div>
<div class="dots"><i class="dot on"></i><i class="dot"></i><i class="dot"></i></div>
<div class="cls bt">Mock Simulation // Forward Test Since 2026-08-14 // OP Zero-Day</div>
<script>
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(function(){{}});
(function(){{
  var tr=document.getElementById('track');
  var tabs=[].slice.call(document.querySelectorAll('.tab'));
  var dots=[].slice.call(document.querySelectorAll('.dot'));
  var panes=[].slice.call(tr.children);
  function mark(i){{
    tabs.forEach(function(t,k){{t.classList.toggle('on',k===i)}});
    dots.forEach(function(d,k){{d.classList.toggle('on',k===i)}});
  }}
  tabs.forEach(function(b){{
    b.addEventListener('click',function(){{
      var i=+b.dataset.i;
      tr.scrollTo({{left:panes[i].offsetLeft-tr.offsetLeft,behavior:'smooth'}});
      mark(i);
    }});
  }});
  var tmr;
  tr.addEventListener('scroll',function(){{
    clearTimeout(tmr);
    tmr=setTimeout(function(){{
      var i=Math.round(tr.scrollLeft/tr.clientWidth);
      if(i<0)i=0; if(i>2)i=2;
      mark(i);
    }},90);
  }},{{passive:true}});
}})();
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
