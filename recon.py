#!/usr/bin/env python3
"""
recon · 라이브 앱이 제때 판정하지 못한 날을 스펙대로 재구성해 원장에 넣는다 (이긴 날·진 날 전부).

  왜: GitHub 예약 실행이 몇 시간씩 밀려, 2026-08-27 ~ 10-01에는 앱이 매일 오후에야 깨어났다.
      그날 제시각에 깨어 있었다면 했을 거래를 5분봉으로 되짚어 '·소급' 표시와 함께 기록한다.
  대상:
    갭필   — 6개 트랙 전부(5m/15m/1h × 즉시/VWAP 대기). 갭 0.2~1.5% · VIX 개장|x|<5% · 커버 [0.40, 1.0)
    모멘텀 — 커버<0.40 + VIX 확인(갭업&VIX↓ / 갭다운&VIX↑), 09:45 진입
    통합   — 15분·즉시 갭필 + 모멘텀 (한 북)
    3층    — L1 VIX9D/VIX3M 전일 종가 백분위 ≥50 · L2 프리마켓 위치 >0.5 · L3 VWAP -1σ 터치(10:05~11:25)
  판정·청산은 라이브와 같은 5분 폴링(봉 마감가) 기준.
  차이: 만기 지난 0DTE는 실시간 호가가 없어 옵션가를 BSM 모델가로 계산 → 항목마다 recon=True, 청산 사유 뒤 '·소급'.
  멱등: 이미 거래가 있거나 라이브가 제때 판정한 날은 건드리지 않는다. 북은 매번 날짜순으로 다시 계산한다.
"""
import datetime as dt
import json
import math
import os

import pandas as pd
import yfinance as yf

import odte as A

GAP_FLOOR = dt.date(2026, 8, 19)       # 갭필 트랙 가동 첫날
MOM_FLOOR = dt.date(2026, 8, 25)       # 모멘텀·통합 가동 첫날
L3_FLOOR = dt.date(2026, 8, 27)        # 3층: 예약 실행이 밀리기 시작한 날 (그 전은 실시간 판정이 있음)
OUTAGE_START = dt.date(2026, 8, 27)    # 예약 실행이 밀리기 시작한 날
OUTAGE_END = dt.date(2026, 10, 1)      # 이 날까지는 앱이 오전에 깨어 있지 못했다. 이후는 first_poll 기록으로 판단
RFR = 0.043
SPREAD = 2.2                           # 왕복 스프레드 마찰 (%)
TAG = "·소급"


def _norm(d):
    d.index = pd.to_datetime(d.index).tz_localize(None) \
        if getattr(d.index, "tz", None) is None else pd.to_datetime(d.index).tz_convert(None)
    return d


def bsm(flag, S, K, tau, iv):
    if tau <= 0 or iv <= 0:
        return max(0.0, (S - K) if flag == "c" else (K - S))
    from statistics import NormalDist
    nd = NormalDist()
    d1 = (math.log(S / K) + (RFR + iv * iv / 2) * tau) / (iv * math.sqrt(tau))
    d2 = d1 - iv * math.sqrt(tau)
    if flag == "c":
        return S * nd.cdf(d1) - K * math.exp(-RFR * tau) * nd.cdf(d2)
    return K * math.exp(-RFR * tau) * nd.cdf(-d2) - S * nd.cdf(-d1)


def _is_late(s):
    r = str(s.get("reason", ""))
    return bool(s.get("late")) or r.startswith("늦은 발견") or r.startswith("갭필 후 발견")


def _hm(t):
    return f"{t.hour:02d}:{t.minute:02d}"


def _hours(hm):
    return int(hm[:2]) + int(hm[3:5]) / 60


def _tau(hm, floor=0.02):
    return max(16.0 - _hours(hm), floor) / 24 / 365


def _strike(ep, oside):
    """라이브 itm_opt 근사: 스팟 대비 0.8% ITM에 가장 가까운 $1 스트라이크."""
    return float(round(ep * 0.992)) if oside == "call" else float(round(ep * 1.008))


def _option_leg(oside, ep, t_in, exit_px, t_out, iv, spot_in=None):
    """(strike, 진입 프리미엄, 청산 프리미엄(스프레드 반영), 손익%, 계약당 손익$) — 모델가.
    spot_in: 진입 순간의 실제 기초가 (VWAP 대기 진입은 기준가 ep와 체결 순간 가격이 다르다)."""
    K = _strike(ep, oside)
    fl = "c" if oside == "call" else "p"
    prem = bsm(fl, ep if spot_in is None else spot_in, K, _tau(t_in, 0.05), iv)
    if prem <= 0.05:
        return None
    pex = bsm(fl, exit_px, K, _tau(t_out), iv)
    pct = max((pex - prem) / prem * 100 - SPREAD, -100.0)
    prem = round(prem, 2)
    ex = round(prem * (1 + pct / 100), 2)
    return K, prem, ex, round((ex / prem - 1) * 100, 1), round((ex - prem) * 100, 2)


def _missed(log, dstr, d, ref_hm, grace_min=4):
    """그날 앱이 기준 시각에 깨어 있지 못했는가."""
    if d < OUTAGE_START:
        return False                    # 예약 실행이 정상이던 때 — 실시간 판정이 있다 (늦은 발견 기록만 따로 재구성)
    if d <= OUTAGE_END:
        return True
    fp = (log.get("first_poll") or {}).get(dstr)
    if not fp:
        return True
    return _hours(fp) * 60 > _hours(ref_hm) * 60 + grace_min


# ───────────────────────── 북 재계산 ─────────────────────────
def rebuild_books(trades, sizes, cap0, per_key="per_contract", skip_fund=True, contracts_key="contracts"):
    """거래를 날짜순으로 다시 돌려 사이징별 북을 만든다 (소급 거래가 중간에 끼어도 잔고·계약수가 시간순으로 맞게)."""
    books = {str(int(f * 100)): dict(cap=cap0, trades=[]) for f in sizes}
    for t in sorted(trades, key=lambda x: (x.get("date", ""), x.get("at") or x.get("entry_time") or "")):
        prem = t.get("premium")
        # per_key=None → 프리미엄 x 손익률 (3층 북의 기존 계산 방식)
        per = t.get(per_key) if per_key else (round(prem * t["pnl_pct"], 2) if prem and t.get("pnl_pct") is not None else None)
        if not prem or per is None:
            continue
        cost = prem * 100
        ent = {}
        for f in sizes:
            k = str(int(f * 100))
            bk = books[k]
            nc = int((bk["cap"] * f) // cost)
            ent[k] = nc
            row = dict(d=t["date"], nc=nc, usd=0.0, pct=0.0, res="SKIP_FUND")
            if nc >= 1:
                usd = round(per * nc, 2)
                bk["cap"] = round(bk["cap"] + usd, 2)
                row = dict(d=t["date"], nc=nc, usd=usd, pct=t.get("pnl_pct", 0.0),
                           res=t.get("res") or t.get("reason"))
            elif not skip_fund:
                continue
            if t.get("recon"):
                row["recon"] = True
            bk["trades"].append(row)
        t[contracts_key] = ent
    return books


# ───────────────────────── 갭필 / 모멘텀 ─────────────────────────
def _manage_gap(post, pc, sgn):
    """진입 이후 봉(post)으로 갭필·트레일·타임컷 — 라이브와 같은 5분 폴링."""
    filled, fill_t, ext = False, None, None
    for ts, r in post.iterrows():
        hi, lo, cl = float(r["High"]), float(r["Low"]), float(r["Close"])
        tc = (ts + pd.Timedelta(minutes=5)).time()            # 이 봉이 끝난 시각 = 폴링 시각
        if not filled and ((lo <= pc) if sgn > 0 else (hi >= pc)):
            filled, fill_t, ext = True, _hm(ts.time()), (lo if sgn > 0 else hi)
        elif filled:
            ext = min(ext, lo) if sgn > 0 else max(ext, hi)
        res = None
        if not filled and tc >= A.GAP_TIMECUT:
            res = "TIMECUT"
        elif filled:
            tp = ext * (1 + A.GAP_TRAIL / 100) if sgn > 0 else ext * (1 - A.GAP_TRAIL / 100)
            if (cl >= tp) if sgn > 0 else (cl <= tp):
                res = "TRAIL"
        if res is None and tc >= A.GAP_CUT:
            res = "CUT"
        if res:
            return dict(res=res, exit_px=cl, exit_at=_hm(tc), filled=filled, fill_t=fill_t)
    cl = float(post["Close"].iloc[-1]) if len(post) else None
    return dict(res="CUT", exit_px=cl, exit_at=_hm(A.GAP_CUT), filled=filled, fill_t=fill_t)


def recon_gap(g, pc, sgn, t_ref, em="now", idx=0):
    """갭필 한 건. g: 당일 정규장 5분봉(인덱스=봉 시작). 반환 dict(cover, [진입·청산]) 또는 None(봉 부족)."""
    pre = g[g.index.time < t_ref]
    if len(pre) < 1 or len(g[g.index.time >= t_ref]) < 1:
        return None
    o0 = float(g["Open"].iloc[0])
    ref_px = float(pre["Close"].iloc[-1])                     # 기준 시각 직전 봉 마감가 = 기준 시각 가격
    cov = ((o0 - ref_px) / (o0 - pc)) if sgn > 0 else ((ref_px - o0) / abs(o0 - pc))
    out = dict(cover=cov, res=None)
    if not (A.GAP_COVER_MIN <= cov < A.GAP_COVER_MAX):
        return out
    if em == "now":
        ep, spot, t_in = ref_px, ref_px, t_ref
    else:
        # VWAP 중간선 대기: 기준 봉부터 봉 고가(갭업)/저가(갭다운)가 누적 VWAP에 닿는 첫 봉 → 그 봉 마감 폴링에서 진입
        tpv = (g["High"] + g["Low"] + g["Close"]) / 3 * g["Volume"]
        vw = (tpv.cumsum() / g["Volume"].cumsum()).where(g["Volume"].cumsum() > 0, (g["High"] + g["Low"] + g["Close"]) / 3)
        ep = None
        for ts, r in g.iloc[idx:].iterrows():                  # 라이브와 같이 기준 봉(idx)부터 본다
            tc = (ts + pd.Timedelta(minutes=5)).time()
            if tc < t_ref:
                continue
            if tc >= A.GAP_TIMECUT:
                break
            if (float(r["High"]) >= float(vw[ts])) if sgn > 0 else (float(r["Low"]) <= float(vw[ts])):
                ep, spot, t_in = round(float(vw[ts]), 2), float(r["Close"]), tc
                break
        if ep is None:
            out["no_spot"] = True                              # 11:30까지 진입 자리 없음
            return out
    post = g[g.index.time >= t_in]
    if len(post) < 1:
        return None
    out.update(ep=ep, spot=spot, at=_hm(t_in))
    out.update(_manage_gap(post, pc, sgn))
    return out


def recon_mom(g, sgn, t_ref):
    """모멘텀 한 건: 09:45 가격으로 갭 방향 진입, OR 극점 손절 · 트레일 · 14:00 컷 (5분 폴링)."""
    pre = g[g.index.time < t_ref]
    post = g[g.index.time >= t_ref]
    if len(pre) < 1 or len(post) < 1:
        return None
    ep = float(pre["Close"].iloc[-1])
    or_stop = float(g["Low"].iloc[0]) if sgn > 0 else float(g["High"].iloc[0])
    ext = ep
    for ts, r in post.iterrows():
        hi, lo, cl = float(r["High"]), float(r["Low"]), float(r["Close"])
        tc = (ts + pd.Timedelta(minutes=5)).time()
        ext = max(ext, hi) if sgn > 0 else min(ext, lo)
        tpx = ext * (1 - A.MOM_TRAIL / 100) if sgn > 0 else ext * (1 + A.MOM_TRAIL / 100)
        res = None
        if (cl <= or_stop) if sgn > 0 else (cl >= or_stop):
            res = "STOP(OR)"
        elif (cl <= tpx) if sgn > 0 else (cl >= tpx):
            res = "TRAIL"
        elif tc >= A.GAP_CUT:
            res = "CUT"
        if res:
            return dict(ep=ep, or_stop=or_stop, res=res, exit_px=cl, exit_at=_hm(tc))
    return dict(ep=ep, or_stop=or_stop, res="CUT", exit_px=float(post["Close"].iloc[-1]), exit_at=_hm(A.GAP_CUT))


# ───────────────────────── 3층 ─────────────────────────
def recon_l3(px, d, iv):
    """3층 하루 재생 (L1·L2 통과한 날만 호출). 10:05부터 5분 폴링으로 VWAP -1σ 터치를 기다렸다가 ITM 콜.
    청산: TP1(VWAP 도달, 가치 50%) → 러너 +1σ / 손절 당일저점 / 11:30 컷. 반환 dict 또는 None(터치 없음)."""
    days = sorted({x.date() for x in px.index if x.date() <= d})[-3:]
    base = px[[x.date() in days for x in px.index]]
    base = base[(base.index.time >= dt.time(9, 30)) & (base.index.time < dt.time(16, 0))]
    today = base[base.index.date == d]
    pos = None
    for j in range(6, len(today)):
        ts = today.index[j]
        tc = (ts + pd.Timedelta(minutes=5)).time()
        try:
            st, _, _ = A.session_state(base[base.index <= ts])
        except ValueError:
            return None                                        # 전일 봉 없음
        if st is None:
            continue
        px_, w, s = st["px"], st["vwap"], st["sd"]
        if pos is None:
            if tc >= A.CUTOFF:
                return None
            if st["dev"] > -A.ENTRY_BAND_SIG:
                continue
            K = float(round(px_ * 0.992))
            prem = bsm("c", px_, K, _tau(_hm(tc), 0.05), iv)
            if prem <= 0.05:
                return None
            pos = dict(entry_time=_hm(tc), entry_px=round(px_, 2), strike=K, premium=round(prem, 2),
                       stop_px=round(st.get("day_lo", px_) * 0.9995, 2), score=st["score"],
                       gap=round(st["gap"], 2), rsi=round(st["rsi"], 1), dev=round(st["dev"], 2),
                       tp1_prem=None, tp1_time=None)
            continue
        cur = round(bsm("c", px_, pos["strike"], _tau(_hm(tc)), iv), 2)
        if not pos["tp1_prem"] and px_ >= w and cur > 0:
            pos["tp1_prem"], pos["tp1_time"] = cur, _hm(tc)
        reason = None
        if px_ <= pos["stop_px"]:
            reason = "STOP(당일저점)" if not pos["tp1_prem"] else "STOP_AFTER_TP1"
        elif pos["tp1_prem"] and s > 1e-9 and px_ >= w + s:
            reason = "RUNNER(+1σ)"
        elif tc >= A.CUTOFF:
            reason = f"CUTOFF({A.CUTOFF.strftime('%H:%M')})"
        if reason:
            t1 = pos["tp1_prem"]
            eff = 0.5 * t1 + 0.5 * cur if t1 else cur
            pct = max((eff / pos["premium"] - 1) * 100 - SPREAD, -100.0)
            eff = round(pos["premium"] * (1 + pct / 100), 2)
            pos.update(exit_time=_hm(tc), exit_px=round(px_, 2), exit_premium=cur, eff_exit=eff,
                       pnl_pct=round((eff / pos["premium"] - 1) * 100, 1),
                       pnl_usd=round((eff - pos["premium"]) * 100, 2), reason=reason)
            return pos
    return None


# ───────────────────────── 실시간 거래의 추정 손익 채우기 ─────────────────────────
def _spot(px, d, hm):
    """5분봉에서 d일 hm 시각의 기초가격 (봉 안에서는 시가→종가 선형)."""
    g = px[px.index.date == d]
    m = int(hm[:2]) * 60 + int(hm[3:5])
    best = None
    for ts, o, c in zip(g.index, g["Open"], g["Close"]):
        sm = ts.hour * 60 + ts.minute
        if sm <= m:
            best = (sm, float(o), float(c))
        else:
            break
    if best is None:
        return None
    frac = min(max((m - best[0]) / 5.0, 0.0), 1.0)
    return best[1] + (best[2] - best[1]) * frac


def fill_rt(log, px, iv_of):
    """야후 옵션 호가는 10~15분 지연이라, 실시간으로 찍힌 거래에도 '실시간 기초가 모델' 손익을 붙인다.
    앱이 진입·청산한 바로 그 시각의 기초가격으로 계산 (앱의 rt_premium과 같은 식). 이미 있으면 건드리지 않는다."""
    n = 0

    def one(t, side, t_in, t_out, tp1_time=None):
        nonlocal n
        if t.get("recon") or t.get("pnl_rt") is not None or not t_in or not t_out:
            return
        d = dt.date.fromisoformat(t["date"])
        s0, s1 = _spot(px, d, t_in), _spot(px, d, t_out)
        if s0 is None or s1 is None:
            return
        fl, K, iv = ("c" if side == "call" else "p"), float(t["strike"]), iv_of(d)
        p0 = round(bsm(fl, s0, K, _tau(t_in), iv), 2)
        p1 = round(bsm(fl, s1, K, _tau(t_out), iv), 2)
        if tp1_time and _spot(px, d, tp1_time) is not None:
            p1 = round(0.5 * bsm(fl, _spot(px, d, tp1_time), K, _tau(tp1_time), iv) + 0.5 * p1, 2)
        if p0 <= 0.05:
            return
        pct = max((p1 / p0 - 1) * 100 - SPREAD, -100.0)
        t.update(spot_rt=round(s0, 2), premium_rt=p0, exit_premium_rt=p1, pnl_rt=round(pct, 1),
                 per_contract_rt=round(p0 * pct, 2), rt_src="recon")
        n += 1
    for tr in list(log.get("gap_tracks", {}).values()) + [log.get("mom_track", {}), log.get("comb", {})]:
        for t in tr.get("trades", []):
            one(t, t.get("opt_side") or ("put" if t.get("sgn", 1) > 0 else "call"), t.get("at"), t.get("exit_at"))
    for t in log.get("trades", []):
        if str(t.get("version", "")).startswith("itm"):
            one(t, "call", t.get("entry_time"), t.get("exit_time"), t.get("tp1_time") if t.get("tp1_prem") else None)
    return n


# ───────────────────────── 데이터 ─────────────────────────
def load_market():
    px = yf.download("QQQ", period="60d", interval="5m", auto_adjust=False, progress=False, prepost=False)
    if isinstance(px.columns, pd.MultiIndex):
        px.columns = px.columns.get_level_values(0)
    px.index = pd.to_datetime(px.index).tz_convert("America/New_York").tz_localize(None)
    dd = yf.download("QQQ", period="6mo", interval="1d", auto_adjust=False, progress=False)
    if isinstance(dd.columns, pd.MultiIndex):
        dd.columns = dd.columns.get_level_values(0)
    dd.index = pd.to_datetime(dd.index).tz_localize(None)
    closes = {k.date(): float(v) for k, v in dd["Close"].items()}
    v = _norm(yf.Ticker("^VIX").history(period="6mo")[["Open", "Close"]].dropna())
    vopen = {k.date(): float(r) for k, r in v["Open"].items()}
    vclose = {k.date(): float(r) for k, r in v["Close"].items()}
    try:
        vxn = _norm(yf.Ticker("^VXN").history(period="6mo")[["Open"]].dropna())
        ivm = {k.date(): float(r) / 100 for k, r in vxn["Open"].items()}
    except Exception:
        ivm = {}
    # L1: VIX9D/VIX3M 전일 종가의 252일 백분위
    vix_pct = {}
    try:
        a = A._grab_close("^VIX9D"); b = A._grab_close("^VIX3M")
        for x in (a, b):
            try: x.index = x.index.tz_localize(None)
            except (TypeError, AttributeError): pass
        ts = (a / b.reindex(a.index).ffill()).dropna()
        for d in sorted({x.date() for x in px.index}):
            w = ts[ts.index.date < d].tail(A.VIX_LOOKBACK).values
            if len(w) >= A.VIX_LOOKBACK:
                vix_pct[d] = round(float((w[:-1] < w[-1]).sum()) / (len(w) - 1) * 100, 1)
    except Exception as e:
        print(f"L1(VIX9D/VIX3M) 조회 실패: {type(e).__name__}: {e}")
    # L2: 프리마켓(04:00~09:30) 레인지 안에서 09:30 시가의 위치 — 라이브 premarket_pos와 같은 방식
    pm_pos = {}
    try:
        h = yf.download("QQQ", period="60d", interval="1h", prepost=True, auto_adjust=False, progress=False)
        if isinstance(h.columns, pd.MultiIndex):
            h.columns = h.columns.get_level_values(0)
        h = h.dropna()
        h.index = pd.to_datetime(h.index).tz_convert("America/New_York").tz_localize(None)
        for d, g in h.groupby(h.index.date):
            pm = g[(g.index.time >= dt.time(4, 0)) & (g.index.time < dt.time(9, 30))]
            rt = g[g.index.time >= dt.time(9, 30)]
            if len(pm) < 3 or len(rt) < 1:
                continue
            pmh, pml = float(pm["High"].max()), float(pm["Low"].min())
            if pmh > pml:
                pm_pos[d] = round((float(rt["Open"].iloc[0]) - pml) / (pmh - pml), 3)
    except Exception as e:
        print(f"L2(프리마켓) 조회 실패: {type(e).__name__}: {e}")
    return dict(px=px, closes=closes, vopen=vopen, vclose=vclose, ivm=ivm, vix_pct=vix_pct, pm_pos=pm_pos)


# ───────────────────────── 본체 ─────────────────────────
def main(market=None, now=None):
    log = A.load_log()
    m = market or load_market()
    px, closes, vopen, vclose, ivm = m["px"], m["closes"], m["vopen"], m["vclose"], m.get("ivm") or {}
    vix_pct, pm_pos = m.get("vix_pct") or {}, m.get("pm_pos") or {}
    now = now or dt.datetime.now(A.NY).replace(tzinfo=None)
    dl = sorted(closes)
    prevc = {dl[i]: closes[dl[i - 1]] for i in range(1, len(dl))}
    vk = sorted(vclose)
    vchg = {vk[i]: (vopen[vk[i]] / vclose[vk[i - 1]] - 1) * 100 for i in range(1, len(vk)) if vk[i] in vopen}

    floor = min(GAP_FLOOR, MOM_FLOOR, L3_FLOOR)
    days = sorted({x.date() for x in px.index if x.date() >= floor})
    days = [d for d in days if d < now.date() or now.time() >= dt.time(16, 10)]    # 끝난 장만
    rep = [f"recon · 대상 {len(days)}일 ({days[0] if days else '-'} ~ {days[-1] if days else '-'})"]
    tracks = log.setdefault("gap_tracks", {})
    mtr = log.setdefault("mom_track", dict(open=None, trades=[], books={}, done={}, skips=[]))
    cb = A.comb_state(log)
    l3v = log.setdefault("l3_recon", {})
    added = 0

    for d in days:
        dstr = str(d)
        g = px[px.index.date == d]
        g = g[(g.index.time >= dt.time(9, 30)) & (g.index.time < dt.time(16, 0))]
        pc = prevc.get(d)
        if len(g) < 60 or pc is None:
            rep.append(f"  {d} 데이터 부족 ({len(g)}봉) — 건너뜀")
            continue
        o0 = float(g["Open"].iloc[0])
        gp = (o0 - pc) / pc * 100
        sgn = 1 if gp > 0 else -1
        vc = vchg.get(d)
        iv = ivm.get(d) or (vopen.get(d, 16.0) * 1.15 / 100)
        in_gap = A.GAP_MIN <= abs(gp) < A.GAP_MAX and vc is not None
        vix_out = vc is not None and abs(vc) >= A.GAP_VIX_SKIP

        # ── 갭필: 6개 트랙 ──
        for tf in (A.GAP_TFS if (in_gap and d >= GAP_FLOOR) else ()):
            for em in A.GAP_ENTRIES:
                tk = f"{tf}|{em}"
                tr = tracks.setdefault(tk, dict(open=None, trades=[], books={}, done={}))
                if tr.get("open") or any(t.get("date") == dstr for t in tr["trades"]):
                    continue
                sk = [s for s in tr.get("skips", []) if s.get("d") == dstr]
                late = any(_is_late(s) for s in sk)
                if tr["done"].get(dstr) and not late:
                    continue                                   # 라이브가 제때 판정한 날
                if not late and not _missed(log, dstr, d, A.GAP_TF_TIME[tf]):
                    continue                                   # 앱이 깨어 있었고 기록이 없다 = 조건 미달
                t_ref = dt.datetime.strptime(A.GAP_TF_TIME[tf], "%H:%M").time()
                x = recon_gap(g, pc, sgn, t_ref, em, A.GAP_TFS[tf])
                if x is None:
                    continue
                keep = [s for s in tr.get("skips", []) if not (s.get("d") == dstr and _is_late(s))]

                def _skip(reason):
                    tr["skips"] = keep + [dict(d=dstr, reason=reason, cover=round(x["cover"], 2),
                                               gap=round(gp, 3), at=A.GAP_TF_TIME[tf], recon=True)]
                    tr["done"][dstr] = True
                if x["cover"] >= A.GAP_COVER_MAX:
                    _skip("이미 메움(커버≥1.0)"); continue
                if x["cover"] < A.GAP_COVER_MIN:               # 커버 미달 — 라이브도 기록을 남기지 않는다
                    if sk:
                        _skip(f"커버 {x['cover']:.2f} 미달")
                    continue
                if vix_out:
                    _skip(f"VIX변화 {vc:+.1f}%"); continue
                if x.get("no_spot"):
                    _skip("11:30까지 진입 자리 없음"); continue
                oside = "put" if sgn > 0 else "call"
                leg = _option_leg(oside, x["ep"], x["at"], x["exit_px"], x["exit_at"], iv, spot_in=x["spot"])
                if leg is None:
                    continue
                K, prem, ex, pct, per = leg
                ux = ((x["ep"] - x["exit_px"]) / x["ep"] * 100) if sgn > 0 else ((x["exit_px"] - x["ep"]) / x["ep"] * 100)
                rec = dict(date=dstr, tf=tf, em=em, late=True, recon=True, comb=None,
                           dir=("숏" if sgn > 0 else "롱"), sgn=sgn, gap=round(gp, 3),
                           cover=round(x["cover"], 2), entry=round(x["ep"], 2), target=round(pc, 2),
                           room=round(abs(pc - x["ep"]) / x["ep"] * 100, 3),
                           at=x["at"], found_at="recon", opt_side=oside, strike=K, premium=prem,
                           prem_src="소급(모델가)", iv=round(iv, 4), mfe=0.0, mfe_t=None, mfe_prem=-99.0,
                           mfe_prem_t=None, filled=bool(x["filled"]), fill_t=x["fill_t"], res=x["res"] + TAG,
                           exit=round(x["exit_px"], 2), exit_at=x["exit_at"], exit_premium=ex,
                           pnl_pct=pct, per_contract=per, ux=round(ux, 3), contracts={})
                tr["skips"] = keep
                tr["trades"].append(rec)
                tr["done"][dstr] = True
                added += 1
                rep.append(f"  {d} 갭필[{tk}] 갭{gp:+.2f}% 커버{x['cover']:.2f} → {oside.upper()} {K:.0f} "
                           f"@${prem:.2f} {x['at']} · {x['res']} {x['exit_at']} · {pct:+.1f}% (기초 {ux:+.3f}%)")

        # ── 모멘텀 ──
        t945 = dt.time(9, 45)
        if (in_gap and not vix_out and d >= MOM_FLOOR and not mtr.get("open")
                and not any(t.get("date") == dstr for t in mtr["trades"])
                and mtr["done"].get(dstr) in (None, "late")
                and (mtr["done"].get(dstr) == "late" or _missed(log, dstr, d, "09:45"))):
            xg = recon_gap(g, pc, sgn, t945)
            if xg is not None and xg["cover"] < A.MOM_COVER_MAX:
                mkeep = [s for s in mtr.get("skips", []) if not (s.get("d") == dstr and _is_late(s))]
                conf = (sgn > 0 and vc < 0) or (sgn < 0 and vc > 0)
                mm = recon_mom(g, sgn, t945) if conf else None
                oside = "call" if sgn > 0 else "put"
                leg = _option_leg(oside, mm["ep"], "09:45", mm["exit_px"], mm["exit_at"], iv) if mm else None
                if not conf:
                    mtr["skips"] = mkeep + [dict(d=dstr, reason="VIX역행", gap=round(gp, 3), vchg=round(vc, 2),
                                                 cover=round(xg["cover"], 2), recon=True)]
                    mtr["done"][dstr] = "veto"
                elif leg is not None:
                    K, prem, ex, pct, per = leg
                    ux = ((mm["exit_px"] - mm["ep"]) / mm["ep"] * 100) if sgn > 0 else ((mm["ep"] - mm["exit_px"]) / mm["ep"] * 100)
                    rec = dict(date=dstr, tf="mom", em="vix", recon=True, comb=None,
                               dir=("롱" if sgn > 0 else "숏"), sgn=sgn, gap=round(gp, 3), cover=round(xg["cover"], 2),
                               vchg=round(vc, 2), entry=round(mm["ep"], 2), target="러너", room=None,
                               at="09:45", found_at="recon", opt_side=oside, strike=K, premium=prem,
                               prem_src="소급(모델가)", iv=round(iv, 4), or_stop=round(mm["or_stop"], 2),
                               ext=round(mm["ep"], 2), mfe=0.0, mfe_t=None, mfe_prem=-99.0, mfe_prem_t=None,
                               filled=False, fill_t=None, res=mm["res"] + TAG, exit=round(mm["exit_px"], 2),
                               exit_at=mm["exit_at"], exit_premium=ex, pnl_pct=pct, per_contract=per,
                               ux=round(ux, 3), contracts={})
                    mtr["skips"] = mkeep
                    mtr["trades"].append(rec)
                    mtr["done"][dstr] = True
                    added += 1
                    rep.append(f"  {d} 모멘텀 갭{gp:+.2f}% 커버{xg['cover']:.2f} VIX{vc:+.1f}% → {oside.upper()} {K:.0f} "
                               f"@${prem:.2f} · {mm['res']} {mm['exit_at']} · {pct:+.1f}% (기초 {ux:+.3f}%)")

        # ── 3층 ──
        l3_have = any(t.get("date") == dstr and str(t.get("version", "")).startswith("itm") for t in log.get("trades", []))
        if (d >= L3_FLOOR and not l3_have and not (l3v.get(dstr) or {}).get("final")
                and not (log.get("open") or {}).get("date") == dstr
                and _missed(log, dstr, d, "11:25", grace_min=0)):
            vp, pp = vix_pct.get(d), pm_pos.get(d)
            v = dict(vix_pct=vp, pm_pos=pp, gap=round(gp, 2))
            if vp is None or pp is None:
                v.update(res="보류 — " + ("L1 " if vp is None else "") + ("L2 " if pp is None else "") + "데이터 없음")
            elif vp < A.VIX_GATE_PCT:
                v.update(res=f"NO-GO · L1 백분위 {vp:.0f}% < {A.VIX_GATE_PCT:.0f}", final=True)
            elif pp <= A.PM_POS_MIN:
                v.update(res=f"NO-GO · L2 프리마켓 위치 {pp:.2f} ≤ {A.PM_POS_MIN}", final=True)
            else:
                p3 = recon_l3(px, d, iv)
                if p3 is None:
                    v.update(res="L1·L2 통과 · 11:30까지 VWAP -1σ 터치 없음", final=True)
                else:
                    rec = dict(date=dstr, side="call", recon=True, mfe=-99.0, mfe_t=None, mfe_prem=-99.0,
                               mfe_prem_t=None, iv=round(iv, 4), symbol="", version=A.VERSION,
                               vix_pct=vp, vix_state="LIVE", pm_pos=pp, contracts={}, **p3)
                    rec["reason"] = p3["reason"] + TAG
                    log.setdefault("trades", []).append(rec)
                    added += 1
                    v.update(res=f"진입 {p3['entry_time']} C{p3['strike']:.0f} → {p3['reason']} {p3['pnl_pct']:+.1f}%", final=True)
                    rep.append(f"  {d} 3층 L1 {vp:.0f}% · L2 {pp:.2f} → CALL {p3['strike']:.0f} @${p3['premium']:.2f} "
                               f"{p3['entry_time']} · {p3['reason']} {p3['exit_time']} · {p3['pnl_pct']:+.1f}%")
            l3v[dstr] = v

    n_rt = fill_rt(log, px, lambda d: ivm.get(d) or (vopen.get(d, 16.0) * 1.15 / 100))
    if n_rt:
        rep.append(f"실시간 거래 {n_rt}건에 '실시간 기초가 모델' 손익 추가")

    # ── 북을 날짜순으로 다시 계산 (소급 거래가 과거에 끼어들어도 잔고·계약수가 시간순으로 맞게) ──
    for tr in list(tracks.values()) + [mtr]:
        tr["trades"].sort(key=lambda t: t.get("date", ""))
        tr["books"] = rebuild_books(tr["trades"], A.GAP_SIZES, A.GAP_CAPITAL)
    if cb.get("open_by") is None:
        have = {t.get("date") for t in cb["trades"]}
        for src, strat in ((tracks.get(A.COMB_FILL_KEY, {}), "갭필"), (mtr, "모멘텀")):
            for t in src.get("trades", []):
                if t.get("recon") and t["date"] not in have and dt.date.fromisoformat(t["date"]) >= MOM_FLOOR:
                    r2 = dict(t); r2["strat"] = strat
                    cb["trades"].append(r2); have.add(t["date"])
        cb["trades"].sort(key=lambda t: t.get("date", ""))
        cb["books"] = rebuild_books(cb["trades"], A.GAP_SIZES, A.GAP_CAPITAL)
    itm = [t for t in log.get("trades", []) if str(t.get("version", "")).startswith("itm")]
    log["trades"].sort(key=lambda t: (t.get("date", ""), t.get("entry_time", "")))
    log["l3_books"] = rebuild_books(itm, A.L3_SIZES, A.CAPITAL_START, per_key=None, skip_fund=False)

    A.save_log(log)
    rep.append(f"재구성 {added}건 추가 · 전부 recon=True / '{TAG}' 표시 (옵션가는 모델가)")
    return rep


if __name__ == "__main__":
    out = main()
    print("\n".join(out))
    json.dump({"at": dt.datetime.utcnow().isoformat(), "report": "\n".join(out)},
              open("recon_result.json", "w"), ensure_ascii=False, indent=1)
    try:                                                   # 화면도 바로 갱신
        A.write_pwa()
        with open(A.OUT, "w", encoding="utf-8") as f:
            f.write(A.render(A.load_log(), None))
    except Exception as e:
        print(f"화면 갱신 실패(다음 odte 실행에서 갱신됨): {type(e).__name__}: {e}")
