#!/usr/bin/env python3
"""
recon · 크론 드랍(8/27~9/8) 결번 구간 갭필 트랙 재구성
  라이브 규칙 그대로: 갭 0.2~1.5% · VIX개장|x|<5% · 커버>=0.40 · 트레일 0.15% · 11:30컷 · 14:00최종
  차이: 옵션 프리미엄은 만료 소멸로 실시간 호가가 없어 BSM 합성가 사용 → 각 항목에 recon=True 표시
  대상 트랙: GAP_TFS x GAP_ENTRIES 전부 (라이브와 동일 구조)
"""
import datetime as dt
import json
import math

import pandas as pd
import yfinance as yf

import odte as A

RECON_FROM = dt.date(2026, 8, 27)
RECON_TO = dt.date(2026, 9, 8)
RFR = 0.043
SPREAD = 2.2          # 왕복 스프레드 마찰 (%)


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


def main():
    log = A.load_log()
    px = yf.download("QQQ", period="30d", interval="5m",
                     auto_adjust=False, progress=False, prepost=False)
    if isinstance(px.columns, pd.MultiIndex):
        px.columns = px.columns.get_level_values(0)
    px.index = pd.to_datetime(px.index).tz_convert("America/New_York").tz_localize(None)

    dd = yf.download("QQQ", period="60d", interval="1d",
                     auto_adjust=False, progress=False)
    if isinstance(dd.columns, pd.MultiIndex):
        dd.columns = dd.columns.get_level_values(0)
    dd.index = pd.to_datetime(dd.index).tz_localize(None)
    closes = {k.date(): float(v) for k, v in dd["Close"].items()}
    dl = sorted(closes)
    prevc = {dl[i]: closes[dl[i - 1]] for i in range(1, len(dl))}

    v = _norm(yf.Ticker("^VIX").history(period="60d")[["Open", "Close"]].dropna())
    vopen = {k.date(): float(r) for k, r in v["Open"].items()}
    vchg = {}
    ks = sorted(vopen)
    vclose = {k.date(): float(r) for k, r in v["Close"].items()}
    for i in range(1, len(ks)):
        vchg[ks[i]] = (vopen[ks[i]] / vclose[ks[i - 1]] - 1) * 100
    try:
        vxn = _norm(yf.Ticker("^VXN").history(period="60d")[["Open"]].dropna())
        ivm = {k.date(): float(r) / 100 for k, r in vxn["Open"].items()}
    except Exception:
        ivm = {}

    days = sorted({d.date() for d in px.index
                   if RECON_FROM <= d.date() <= RECON_TO})
    rep = [f"recon · 대상 {len(days)}일 ({RECON_FROM} ~ {RECON_TO})"]
    tracks = log.setdefault("gap_tracks", {})
    added = 0

    for d in days:
        g = px[px.index.date == d]
        g = g[(g.index.time >= dt.time(9, 30)) & (g.index.time <= dt.time(15, 55))]
        if len(g) < 20:
            rep.append(f"  {d} 데이터 부족 ({len(g)}봉) — 건너뜀")
            continue
        pc = prevc.get(d)
        if pc is None:
            continue
        O0 = float(g["Open"].iloc[0])
        gap = O0 - pc
        gp = gap / pc * 100
        if not (A.GAP_MIN <= abs(gp) < A.GAP_MAX):
            rep.append(f"  {d} 갭 {gp:+.2f}% — 대상 밖")
            continue
        vc = vchg.get(d)
        if vc is not None and abs(vc) >= A.GAP_VIX_SKIP:
            rep.append(f"  {d} 갭 {gp:+.2f}% · VIX개장 {vc:+.1f}% — 스킵")
            continue
        sgn = 1 if gap > 0 else -1
        iv = ivm.get(d) or (vopen.get(d, 16.0) * 1.15 / 100)

        for tf, idx in A.GAP_TFS.items():
            if len(g) <= idx:
                continue
            ep = float(g["Close"].iloc[idx])
            t_ent = g.index[idx]
            cov = ((O0 - ep) / gap) if sgn > 0 else ((ep - O0) / abs(gap))
            tk = f"{tf}|now"
            tr = tracks.setdefault(tk, dict(open=None, trades=[], books={}, done={}))
            dstr = str(d)
            if tr["done"].get(dstr):
                continue
            if not (A.GAP_COVER_MIN <= cov < 1.0):
                tr["done"][dstr] = True
                tr.setdefault("skips", []).append(dict(
                    d=dstr, reason=("이미 필" if cov >= 1.0 else f"커버 {cov:.2f} 미달"),
                    cover=round(cov, 2), gap=round(gp, 3), at=str(t_ent.time())[:5],
                    recon=True))
                continue

            # ── 진입: ITM 옵션 (라이브 itm_opt 근사 = 0.5% ITM 라운드 스트라이크) ──
            oside = "put" if sgn > 0 else "call"
            K = round(ep * (1 - 0.005)) if oside == "call" else round(ep * (1 + 0.005))
            t0h = t_ent.hour + t_ent.minute / 60
            tau0 = max(16.0 - t0h, 0.05) / 24 / 365
            prem = bsm("c" if oside == "call" else "p", ep, K, tau0, iv)
            if prem <= 0.05:
                continue
            cost = prem * 100
            ent = {}
            for f in A.GAP_SIZES:
                kk = str(int(f * 100))
                bk = tr["books"].setdefault(kk, dict(cap=A.GAP_CAPITAL, trades=[]))
                ent[kk] = int((bk["cap"] * f) // cost)

            # ── 관리: 이후 봉으로 갭필·트레일·타임컷 진행 ──
            tail = g[g.index > t_ent]
            tgt = pc
            filled, fill_t, peak = False, None, ep
            res, exit_px, exit_t = None, None, None
            for t, r in tail.iterrows():
                hi, lo, cl = float(r["High"]), float(r["Low"]), float(r["Close"])
                if not filled:
                    if (lo <= tgt) if sgn > 0 else (hi >= tgt):
                        filled, fill_t, peak = True, str(t.time())[:5], tgt
                    elif t.time() >= A.GAP_TIMECUT:
                        res, exit_px, exit_t = "TIMECUT", cl, str(t.time())[:5]
                        break
                if filled:
                    peak = min(peak, lo) if sgn > 0 else max(peak, hi)
                    stop = peak * (1 + A.GAP_TRAIL / 100) if sgn > 0 \
                        else peak * (1 - A.GAP_TRAIL / 100)
                    if (hi >= stop) if sgn > 0 else (lo <= stop):
                        res, exit_px, exit_t = "TRAIL", stop, str(t.time())[:5]
                        break
                    if t.time() >= A.GAP_CUT:
                        res, exit_px, exit_t = "CUT", cl, str(t.time())[:5]
                        break
            if res is None:
                res = "CUT"
                exit_px = float(tail["Close"].iloc[-1]) if len(tail) else ep
                exit_t = str(tail.index[-1].time())[:5] if len(tail) else str(t_ent.time())[:5]

            hh = int(exit_t[:2]) + int(exit_t[3:5]) / 60
            tau1 = max(16.0 - hh, 0.02) / 24 / 365
            pex = bsm("c" if oside == "call" else "p", exit_px, K, tau1, iv)
            pl = max((pex - prem) / prem * 100 - SPREAD, -100.0)

            rec = dict(date=dstr, tf=tf, em="now", late=False, recon=True,
                       dir=("롱" if sgn < 0 else "숏"), sgn=sgn,
                       gap=round(gp, 3), cover=round(cov, 2), entry=round(ep, 2),
                       target=round(tgt, 2), at=str(t_ent.time())[:5],
                       found_at=str(t_ent.time())[:5],
                       opt_side=oside, strike=float(K), premium=round(prem, 2),
                       contracts=ent, prem_src="recon(BSM)",
                       filled=filled, fill_t=fill_t,
                       res=res, exit_px=round(exit_px, 2), exit_t=exit_t,
                       pl=round(pl, 1), exit_prem=round(pex, 2))
            for f in A.GAP_SIZES:
                kk = str(int(f * 100))
                bk = tr["books"][kk]
                n = ent[kk]
                if n:
                    bk["cap"] = round(bk["cap"] + n * prem * 100 * pl / 100, 2)
                bk["trades"].append(dict(d=dstr, n=n, pl=round(pl, 1), recon=True))
            tr["trades"].append(rec)
            tr["done"][dstr] = True
            added += 1
            if tf == "5m":
                rep.append(f"  {d} 갭{gp:+.2f}% 커버{cov:.2f} → {oside.upper()} {K} "
                           f"@${prem:.2f} · {res} {exit_t} · {pl:+.1f}%")

    A.save_log(log)
    rep.append(f"재구성 {added}건 추가 (트랙 합산) · recon=True 표시됨")
    return rep


if __name__ == "__main__":
    out = main()
    print("\n".join(out))
    json.dump({"at": dt.datetime.utcnow().isoformat(), "report": "\n".join(out)},
              open("recon_result.json", "w"), ensure_ascii=False, indent=1)
