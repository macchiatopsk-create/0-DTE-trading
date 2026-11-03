# -*- coding: utf-8 -*-
"""로빈후드 실가 원장 (2026-11-03~).

로빈후드는 만기 0DTE 옵션의 실제 5분봉을 약 1주일만 보관한다. 매일 장 마감 후 그날 값을 받아
'계산된 숫자만' realprice.json에 남긴다 (공개 레포 — 봉 원자료·옵션 가격 원값은 커밋하지 않는다).

사용:
  python research/realprice.py iv  DATE TK S K CALL PUT MODEL_IV [--kind atm|itm] [--hours 6.25]
      S = 09:40 5분봉 종가(09:45 판정가), CALL/PUT = 같은 시각 옵션 5분봉 종가, MODEL_IV = 앱 모델 IV
  python research/realprice.py trade DATE TRACK TK SIDE K ENTRY_REAL EXIT_REAL MODEL_PNL
      ENTRY_REAL/EXIT_REAL = 앱 진입·청산 시각의 실제 옵션 5분봉 종가
  python research/realprice.py summary
"""
import json, math, os, sys, statistics

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "realprice.json")
SPREAD = 2.2


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bsm(cp, S, K, h, iv, r=0.043):
    t = max(h, 0.02) / 24 / 365
    d1 = (math.log(S / K) + (r + iv * iv / 2) * t) / (iv * math.sqrt(t)); d2 = d1 - iv * math.sqrt(t)
    return S * ncdf(d1) - K * math.exp(-r * t) * ncdf(d2) if cp == "c" else K * math.exp(-r * t) * ncdf(-d2) - S * ncdf(-d1)


def implied(cp, S, K, h, px):
    lo, hi = 0.01, 5.0
    for _ in range(100):
        m = (lo + hi) / 2
        if bsm(cp, S, K, h, m) > px:
            hi = m
        else:
            lo = m
    return (lo + hi) / 2


def load():
    try:
        return json.load(open(PATH, encoding="utf-8"))
    except Exception:
        return {"note": "로빈후드 만기 0DTE 실가에서 계산한 값만 기록 (원자료 없음). iv: 09:45 실제 IV ÷ 앱 모델 IV.",
                "iv": [], "trades": []}


def save(j):
    json.dump(j, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def add_iv(d, tk, S, K, c, p, model, kind="atm", hours=6.25):
    a, b = implied("c", S, K, hours, c), implied("p", S, K, hours, p)
    r = (a + b) / 2
    j = load()
    j["iv"] = [x for x in j["iv"] if not (x["d"] == d and x["tk"] == tk and x.get("kind", "atm") == kind)]
    j["iv"].append(dict(d=d, tk=tk, kind=kind, K=K, real_iv=round(r, 4), model_iv=round(model, 4),
                        ratio=round(r / model, 3)))
    j["iv"].sort(key=lambda x: (x["d"], x["tk"], x.get("kind", "atm")))
    save(j)
    print(f"{d} {tk} {kind}: 실제 IV {r:.3f} · 모델 {model:.3f} · 배율 {r / model:.2f}")


def add_trade(d, track, tk, side, K, e, x, model_pnl):
    real = max((x / e - 1) * 100 - SPREAD, -100)
    j = load()
    j["trades"] = [t for t in j["trades"] if not (t["d"] == d and t["track"] == track)]
    j["trades"].append(dict(d=d, track=track, tk=tk, side=side, K=K, real_pnl=round(real, 1),
                            model_pnl=round(model_pnl, 1), gap=round(real - model_pnl, 1)))
    j["trades"].sort(key=lambda t: (t["d"], t["track"]))
    save(j)
    print(f"{d} {track} {tk} {side} K{K}: 실가 {real:+.1f}% · 모델 {model_pnl:+.1f}%")


def summary():
    j = load()
    for tk in ("QQQ", "SPY"):
        for kind in ("atm", "itm"):
            rs = [x["ratio"] for x in j["iv"] if x["tk"] == tk and x.get("kind", "atm") == kind]
            if rs:
                print(f"{tk} {kind}: {len(rs)}일 · 배율 평균 {statistics.mean(rs):.2f} · 중앙 {statistics.median(rs):.2f} · 범위 {min(rs):.2f}~{max(rs):.2f}")
    for t in j["trades"][-10:]:
        print(f"  {t['d']} {t['track']} {t['tk']} {t['side']}: 실가 {t['real_pnl']:+.1f}% vs 모델 {t['model_pnl']:+.1f}%")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "summary":
        summary()
    elif a[0] == "iv":
        kind = a[a.index("--kind") + 1] if "--kind" in a else "atm"
        hours = float(a[a.index("--hours") + 1]) if "--hours" in a else 6.25
        d, tk = a[1], a[2]
        S, K, c, p, m = map(float, a[3:8])
        add_iv(d, tk, S, K, c, p, m, kind, hours)
    elif a[0] == "trade":
        d, track, tk, side = a[1:5]
        K, e, x, mp = map(float, a[5:9])
        add_trade(d, track, tk, side, K, e, x, mp)
