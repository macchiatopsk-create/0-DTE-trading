#!/usr/bin/env python3
"""
recon · 라이브 앱이 기준 시각(09:35/09:45/10:30)을 놓친 날을 스펙대로 재구성해 원장에 넣는다.

  왜: GitHub 예약 실행이 몇 시간씩 밀려, 앱이 오후에야 깨어난 날은 '늦은 발견'/'갭필 후 발견'으로
      스킵만 찍혔다 (2026-08-27 ~ 10-01 전부). 그날 09:45에 깨어 있었다면 했을 거래를 5분봉으로 되짚는다.
  규칙: 라이브와 동일 — 갭 0.2~1.5% · VIX 개장|x|<5% · 커버 [0.40, 1.0) → 갭필 /
        커버<0.40 + VIX 확인 → 모멘텀. 판정·청산은 라이브와 같은 5분 폴링(봉 마감가) 기준.
  차이: 만기 지난 0DTE는 실시간 호가가 없어 옵션가를 BSM 모델가로 계산 → 모든 항목에 recon=True,
        청산 사유 뒤에 '·소급' 표시. 실시간 체결 기록과 구분해서 읽을 것.
  대상: 갭필 '즉시 진입' 3개 트랙(5m/15m/1h) + 모멘텀 + 통합 계좌. VWAP 대기 트랙은 재구성하지 않는다.
  멱등: 이미 거래가 있거나 라이브가 제때 판정한 날(VIX 스킵·관망 등)은 건드리지 않는다.
"""
import datetime as dt
import json
import math
import os

import pandas as pd
import yfinance as yf

import odte as A

RECON_FLOOR = dt.date(2026, 8, 27)     # 예약 실행이 밀리기 시작한 날. 그 전은 실시간 기록이 정상
RFR = 0.043
SPREAD = 2.2                           # 왕복 스프레드 마찰 (%)
LATE_REASONS = ("늦은 발견", "갭필 후 발견")
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
    return s.get("late") or r in LATE_REASONS


def _hm(t):
    return f"{t.hour:02d}:{t.minute:02d}"


def _hours(hm):
    return int(hm[:2]) + int(hm[3:5]) / 60


def _strike(ep, oside):
    """라이브 itm_opt 근사: 스팟 대비 0.8% ITM에 가장 가까운 $1 스트라이크."""
    return float(round(ep * 0.992)) if oside == "call" else float(round(ep * 1.008))


def _option_leg(oside, ep, t_in, exit_px, t_out, iv):
    """(strike, 진입 프리미엄, 청산 프리미엄(스프레드 반영), 손익%, 계약당 손익$) — 모델가."""
    K = _strike(ep, oside)
    fl = "c" if oside == "call" else "p"
    prem = bsm(fl, ep, K, max(16.0 - _hours(t_in), 0.05) / 24 / 365, iv)
    if prem <= 0.05:
        return None
    pex = bsm(fl, exit_px, K, max(16.0 - _hours(t_out), 0.02) / 24 / 365, iv)
    pct = max((pex - prem) / prem * 100 - SPREAD, -100.0)
    prem = round(prem, 2)
    ex = round(prem * (1 + pct / 100), 2)
    return K, prem, ex, round((ex / prem - 1) * 100, 1), round((ex - prem) * 100, 2)


def _book(tr, rec, per, pct, cost):
    """라이브와 같은 형식으로 사이징별 북 갱신. 계약수는 그 시점 잔고 기준."""
    ent = {}
    for f in A.GAP_SIZES:
        k = str(int(f * 100))
        bk = tr["books"].setdefault(k, dict(cap=A.GAP_CAPITAL, trades=[]))
        nc = int((bk["cap"] * f) // cost)
        ent[k] = nc
        if nc < 1:
            bk["trades"].append(dict(d=rec["date"], nc=0, usd=0.0, pct=0.0, res="SKIP_FUND", recon=True))
            continue
        usd = round(per * nc, 2)
        bk["cap"] = round(bk["cap"] + usd, 2)
        bk["trades"].append(dict(d=rec["date"], nc=nc, usd=usd, pct=pct, res=rec["res"], recon=True))
    return ent


def _comb(log, rec, per, cost, strat):
    cb = A.comb_state(log)
    if cb.get("open_by") is not None:           # 실시간 포지션이 열려 있으면 통합 북은 건드리지 않는다
        return
    if any(t.get("date") == rec["date"] for t in cb["trades"]):
        return
    rec["comb"] = A.comb_contracts(cb, cost)
    A.comb_settle(cb, rec, per, strat)
    for bk in cb["books"].values():
        if bk["trades"] and bk["trades"][-1].get("d") == rec["date"]:
            bk["trades"][-1]["recon"] = True
    cb["trades"].sort(key=lambda t: t.get("date", ""))


def recon_gap(g, pc, sgn, t_ref):
    """갭필 한 건: 기준 시각 t_ref의 가격으로 진입, 이후 5분 폴링으로 관리.
    g: 당일 정규장 5분봉(인덱스=봉 시작). 반환 dict 또는 None(봉 부족)."""
    pre = g[g.index.time < t_ref]
    post = g[g.index.time >= t_ref]
    if len(pre) < 1 or len(post) < 1:
        return None
    o0 = float(g["Open"].iloc[0])
    ep = float(pre["Close"].iloc[-1])                         # 기준 시각 직전 봉 마감가 = 기준 시각 가격
    cov = ((o0 - ep) / (o0 - pc)) if sgn > 0 else ((ep - o0) / abs(o0 - pc))
    out = dict(ep=ep, cover=cov, res=None)
    if not (A.GAP_COVER_MIN <= cov < A.GAP_COVER_MAX):
        return out
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
            out.update(res=res, exit_px=cl, exit_at=_hm(tc), filled=filled, fill_t=fill_t)
            return out
    out.update(res="CUT", exit_px=float(post["Close"].iloc[-1]), exit_at=_hm(A.GAP_CUT),
               filled=filled, fill_t=fill_t)
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
    return px, closes, vopen, vclose, ivm


def main(market=None, now=None):
    log = A.load_log()
    px, closes, vopen, vclose, ivm = market or load_market()
    now = now or dt.datetime.now(A.NY).replace(tzinfo=None)
    dl = sorted(closes)
    prevc = {dl[i]: closes[dl[i - 1]] for i in range(1, len(dl))}
    vk = sorted(vclose)
    vchg = {vk[i]: (vopen[vk[i]] / vclose[vk[i - 1]] - 1) * 100 for i in range(1, len(vk)) if vk[i] in vopen}

    floor = RECON_FLOOR
    if os.environ.get("RECON_FROM"):
        floor = dt.date.fromisoformat(os.environ["RECON_FROM"])
    days = sorted({d.date() for d in px.index if d.date() >= floor})
    days = [d for d in days if d < now.date() or now.time() >= dt.time(16, 5)]     # 끝난 장만
    rep = [f"recon · 대상 {len(days)}일 ({days[0] if days else '-'} ~ {days[-1] if days else '-'})"]
    tracks = log.setdefault("gap_tracks", {})
    mtr = log.setdefault("mom_track", dict(open=None, trades=[], books={}, done={}, skips=[]))
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
        if not (A.GAP_MIN <= abs(gp) < A.GAP_MAX):
            continue
        vc = vchg.get(d)
        if vc is None:
            rep.append(f"  {d} 갭 {gp:+.2f}% · VIX 개장변화 없음 — 건너뜀")
            continue
        sgn = 1 if gp > 0 else -1
        iv = ivm.get(d) or (vopen.get(d, 16.0) * 1.15 / 100)
        vix_out = abs(vc) >= A.GAP_VIX_SKIP

        # ── 갭필: '즉시 진입' 3개 트랙 ──
        for tf in A.GAP_TFS:
            tk = f"{tf}|now"
            tr = tracks.setdefault(tk, dict(open=None, trades=[], books={}, done={}))
            if tr.get("open") or any(t.get("date") == dstr for t in tr["trades"]):
                continue
            sk = [s for s in tr.get("skips", []) if s.get("d") == dstr]
            if tr["done"].get(dstr) and not any(_is_late(s) for s in sk):
                continue                                   # 라이브가 제때 판정한 날
            t_ref = dt.datetime.strptime(A.GAP_TF_TIME[tf], "%H:%M").time()
            x = recon_gap(g, pc, sgn, t_ref)
            if x is None:
                continue
            keep = [s for s in tr.get("skips", []) if not (s.get("d") == dstr and _is_late(s))]

            def _skip(reason):
                tr["skips"] = keep + [dict(d=dstr, reason=reason, cover=round(x["cover"], 2),
                                           gap=round(gp, 3), at=A.GAP_TF_TIME[tf], recon=True)]
                tr["done"][dstr] = True
            if x["cover"] >= A.GAP_COVER_MAX:
                _skip("이미 메움(커버≥1.0)"); continue
            if x["res"] is None:                           # 커버 미달 — 라이브도 기록을 남기지 않는다
                if sk:
                    _skip(f"커버 {x['cover']:.2f} 미달")
                continue
            if vix_out:
                _skip(f"VIX변화 {vc:+.1f}%"); continue
            oside = "put" if sgn > 0 else "call"
            leg = _option_leg(oside, x["ep"], A.GAP_TF_TIME[tf], x["exit_px"], x["exit_at"], iv)
            if leg is None:
                continue
            K, prem, ex, pct, per = leg
            ux = ((x["ep"] - x["exit_px"]) / x["ep"] * 100) if sgn > 0 else ((x["exit_px"] - x["ep"]) / x["ep"] * 100)
            rec = dict(date=dstr, tf=tf, em="now", late=True, recon=True, comb=None,
                       dir=("숏" if sgn > 0 else "롱"), sgn=sgn, gap=round(gp, 3),
                       cover=round(x["cover"], 2), entry=round(x["ep"], 2), target=round(pc, 2),
                       room=round(abs(pc - x["ep"]) / x["ep"] * 100, 3),
                       at=A.GAP_TF_TIME[tf], found_at="recon", opt_side=oside, strike=K, premium=prem,
                       prem_src="소급(모델가)", iv=round(iv, 4), mfe=0.0, mfe_t=None, mfe_prem=-99.0, mfe_prem_t=None,
                       filled=bool(x["filled"]), fill_t=x["fill_t"], res=x["res"] + TAG,
                       exit=round(x["exit_px"], 2), exit_at=x["exit_at"], exit_premium=ex,
                       pnl_pct=pct, per_contract=per, ux=round(ux, 3))
            rec["contracts"] = _book(tr, rec, per, pct, prem * 100)
            if tk == A.COMB_FILL_KEY:
                _comb(log, rec, per, prem * 100, "갭필")
            tr["skips"] = keep
            tr["trades"].append(rec)
            tr["trades"].sort(key=lambda t: t.get("date", ""))
            tr["done"][dstr] = True
            added += 1
            rep.append(f"  {d} 갭필[{tk}] 갭{gp:+.2f}% 커버{x['cover']:.2f} → {oside.upper()} {K:.0f} "
                       f"@${prem:.2f} · {x['res']} {x['exit_at']} · {pct:+.1f}% (기초 {ux:+.3f}%)")

        # ── 모멘텀 ──
        if mtr.get("open") or any(t.get("date") == dstr for t in mtr["trades"]):
            continue
        if mtr["done"].get(dstr) not in (None, "late"):
            continue                                       # 실시간 진입·관망 판정이 이미 있는 날
        t945 = dt.time(9, 45)
        xg = recon_gap(g, pc, sgn, t945)
        if xg is None or xg["cover"] >= A.MOM_COVER_MAX or vix_out:
            continue
        mkeep = [s for s in mtr.get("skips", []) if not (s.get("d") == dstr and _is_late(s))]
        conf = (sgn > 0 and vc < 0) or (sgn < 0 and vc > 0)
        if not conf:
            mtr["skips"] = mkeep + [dict(d=dstr, reason="VIX역행", gap=round(gp, 3), vchg=round(vc, 2),
                                         cover=round(xg["cover"], 2), recon=True)]
            mtr["done"][dstr] = "veto"
            continue
        m = recon_mom(g, sgn, t945)
        oside = "call" if sgn > 0 else "put"
        leg = _option_leg(oside, m["ep"], "09:45", m["exit_px"], m["exit_at"], iv)
        if leg is None:
            continue
        K, prem, ex, pct, per = leg
        ux = ((m["exit_px"] - m["ep"]) / m["ep"] * 100) if sgn > 0 else ((m["ep"] - m["exit_px"]) / m["ep"] * 100)
        rec = dict(date=dstr, tf="mom", em="vix", recon=True, comb=None,
                   dir=("롱" if sgn > 0 else "숏"), sgn=sgn, gap=round(gp, 3), cover=round(xg["cover"], 2),
                   vchg=round(vc, 2), entry=round(m["ep"], 2), target="러너", room=None,
                   at="09:45", found_at="recon", opt_side=oside, strike=K, premium=prem,
                   prem_src="소급(모델가)", iv=round(iv, 4), or_stop=round(m["or_stop"], 2), ext=round(m["ep"], 2),
                   mfe=0.0, mfe_t=None, mfe_prem=-99.0, mfe_prem_t=None, filled=False, fill_t=None,
                   res=m["res"] + TAG, exit=round(m["exit_px"], 2), exit_at=m["exit_at"], exit_premium=ex,
                   pnl_pct=pct, per_contract=per, ux=round(ux, 3))
        rec["contracts"] = _book(mtr, rec, per, pct, prem * 100)
        _comb(log, rec, per, prem * 100, "모멘텀")
        mtr["skips"] = mkeep
        mtr["trades"].append(rec)
        mtr["trades"].sort(key=lambda t: t.get("date", ""))
        mtr["done"][dstr] = True
        added += 1
        rep.append(f"  {d} 모멘텀 갭{gp:+.2f}% 커버{xg['cover']:.2f} VIX{vc:+.1f}% → {oside.upper()} {K:.0f} "
                   f"@${prem:.2f} · {m['res']} {m['exit_at']} · {pct:+.1f}% (기초 {ux:+.3f}%)")

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
