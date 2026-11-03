# -*- coding: utf-8 -*-
# 과적합 점검 (2026-11-03). gapbt.py와 같은 폴더·같은 data.pkl로 실행: GAPBT_DATA=... python research/robust.py
"""과적합 점검: 부트스트랩 · Deflated Sharpe · PBO(CSCV) · FDR(BH). 보정 IV, 09:45."""
import itertools, math, random, statistics as stt
from gapbt import *
random.seed(7)
ALL = sorted(set(days("QQQ")) | set(days("SPY")))
V2 = dict()
VARIANTS = {"v2(최종)": V2,
 "현행 앱(QQQ·트레일·콜필터X)": dict(syms=("QQQ",), put_exit="trail", call_exit="trail", call_rv=None),
 "QQQ만 v2": dict(syms=("QQQ",)), "콜필터X": dict(call_rv=None), "콜스킵": dict(call_rv=-1),
 "rv<0.1": dict(call_rv=0.1), "rv<0.15": dict(call_rv=0.15), "rv<0.25": dict(call_rv=0.25), "rv<0.3": dict(call_rv=0.3),
 "풋 limit": dict(put_exit="limit"), "풋 trail": dict(put_exit="trail"), "콜 take": dict(call_exit="take"), "콜 trail": dict(call_exit="trail"),
 "풋 itm04": dict(put_k="itm04"), "풋 atm": dict(put_k="atm"), "풋 mid": dict(put_k="mid"), "풋 target": dict(put_k="target"), "풋 beyond": dict(put_k="beyond"),
 "타임컷 11:00": dict(timecut="11:00"), "타임컷 12:00": dict(timecut="12:00"), "타임컷 13:00": dict(timecut="13:00"), "타임컷 없음": dict(timecut=None),
 "커버≥0.3": dict(cover_lo=0.3), "커버≥0.5": dict(cover_lo=0.5), "커버≥0.6": dict(cover_lo=0.6),
 "갭0.1~": dict(gmin=0.1), "갭0.3~": dict(gmin=0.3), "갭~1.0": dict(gmax=1.0), "갭~2.5": dict(gmax=2.5),
 "VIX필터X": dict(vixf=False), "하루1건X": dict(one=False)}
def daily(kw):
    m = {d: 0.0 for d in ALL}
    for t in run(entry="09:45", **kw): m[t["d"]] += t["pnl"]
    return m, [t["pnl"] for t in run(entry="09:45", **kw)]
D = {}; TR = {}
for k, kw in VARIANTS.items(): D[k], TR[k] = daily(kw)
v2, base = TR["v2(최종)"], TR["현행 앱(QQQ·트레일·콜필터X)"]
def boot_sum(x, n=20000):
    s = [sum(random.choice(x) for _ in x) for _ in range(n)]; s.sort()
    return sum(1 for v in s if v <= 0) / n, s[int(n * .05)], s[int(n * .5)]
print("== 1) 부트스트랩 (거래 재표본 2만 회)")
for nm, x in (("v2", v2), ("현행", base)):
    p, q5, q50 = boot_sum(x); print(f"  {nm}: {len(x)}건 합 {sum(x):+.0f}% · 합≤0 확률 {p*100:.2f}% · 하위5% {q5:+.0f}% · 중앙 {q50:+.0f}%")
# paired daily bootstrap v2 - base
diff = [D["v2(최종)"][d] - D["현행 앱(QQQ·트레일·콜필터X)"][d] for d in ALL]
bs = sorted(sum(random.choice(diff) for _ in diff) for _ in range(20000))
print(f"  v2-현행 (날짜 재표본): 차이 {sum(diff):+.0f}%p · v2가 못할 확률 {sum(1 for v in bs if v<=0)/len(bs)*100:.2f}% · 하위5% {bs[1000]:+.0f}%p")
print("== 2) Deflated Sharpe (거래당 SR, 시도 수 = 변형 %d개)" % len(VARIANTS))
def sr(x): return stt.mean(x) / stt.pstdev(x) if len(x) > 1 and stt.pstdev(x) > 0 else 0
srs = [sr(TR[k]) for k in VARIANTS]
N = len(srs); V = stt.pvariance(srs); g = 0.5772
nd = lambda p: stt.NormalDist().inv_cdf(p)
sr0 = math.sqrt(V) * ((1 - g) * nd(1 - 1 / N) + g * nd(1 - 1 / (N * math.e)))
x = v2; T = len(x); s = sr(x); m = stt.mean(x); sd = stt.pstdev(x)
sk = sum((v - m) ** 3 for v in x) / T / sd ** 3; ku = sum((v - m) ** 4 for v in x) / T / sd ** 4
dsr = stt.NormalDist().cdf((s - sr0) * math.sqrt(T - 1) / math.sqrt(1 - sk * s + (ku - 1) / 4 * s * s))
psr = stt.NormalDist().cdf((s - 0) * math.sqrt(T - 1) / math.sqrt(1 - sk * s + (ku - 1) / 4 * s * s))
print(f"  v2 거래당 SR {s:.2f} · 운으로 기대되는 최고 SR {sr0:.2f} · PSR(>0) {psr*100:.1f}% · DSR {dsr*100:.1f}%")
print("== 3) PBO (CSCV, 날짜 8블록, IS 4블록 고르기 70조합)")
ks = list(VARIANTS); blocks = [ALL[i::8] for i in range(8)]
blocks = [ALL[len(ALL)*i//8: len(ALL)*(i+1)//8] for i in range(8)]
lo = 0; tot = 0; ranks = []
for IS in itertools.combinations(range(8), 4):
    OS = [i for i in range(8) if i not in IS]
    isv = {k: sum(D[k][d] for i in IS for d in blocks[i]) for k in ks}
    osv = {k: sum(D[k][d] for i in OS for d in blocks[i]) for k in ks}
    best = max(ks, key=lambda k: isv[k])
    r = sorted(ks, key=lambda k: osv[k]).index(best) / (len(ks) - 1)   # 0=꼴찌 1=1등
    ranks.append(r); tot += 1; lo += r < 0.5
print(f"  IS 1등 변형이 OOS에서 중앙 아래로 떨어진 비율 PBO = {lo/tot*100:.0f}% · OOS 평균 순위 {stt.mean(ranks)*100:.0f}백분위")
print("== 4) FDR (각 변형 vs 현행 앱, 날짜 부트스트랩 단측 p → BH)")
pv = []
for k in ks:
    if k.startswith("현행"): continue
    dd = [D[k][d] - D["현행 앱(QQQ·트레일·콜필터X)"][d] for d in ALL]
    b = [sum(random.choice(dd) for _ in dd) for _ in range(4000)]
    pv.append((sum(1 for v in b if v <= 0) / len(b), k, sum(dd)))
pv.sort(); M = len(pv); passed = []
for i, (p, k, sdd) in enumerate(pv, 1):
    if p <= 0.05 * i / M: passed = pv[:i]
print(f"  {M}개 중 FDR 5%를 통과해 '현행보다 낫다'고 말할 수 있는 변형 {len(passed)}개")
for p, k, sdd in pv[:12]: print(f"   {'✓' if (p,k,sdd) in passed else ' '} {k:<14} p={p:.3f} 차이 {sdd:+.0f}%p")
print("== 5) 시간 분할: 전반(2~6월)에서 고른 1등을 후반(7~10월)에 적용")
h1 = [d for d in ALL if d < "2026-07-01"]; h2 = [d for d in ALL if d >= "2026-07-01"]
b1 = max(ks, key=lambda k: sum(D[k][d] for d in h1)); 
o2 = sorted(ks, key=lambda k: sum(D[k][d] for d in h2), reverse=True)
print(f"  전반 1등: {b1} → 후반 순위 {o2.index(b1)+1}/{len(ks)} (후반 합 {sum(D[b1][d] for d in h2):+.0f}%) · v2 후반 순위 {o2.index('v2(최종)')+1}/{len(ks)}")
