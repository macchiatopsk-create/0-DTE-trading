# -*- coding: utf-8 -*-
"""갭필 백테스트 엔진 (2026-11-03). 데이터는 레포에 없음 — 로빈후드 MCP로 받은 5분봉/일봉/VIX를
load.py 형식의 data.pkl로 만든 뒤 같은 폴더에서 실행. 스펙: docs/인수인계-2026-11-02.md 6절."""
import pickle, math
from datetime import date
import os
D = pickle.load(open(os.environ.get("GAPBT_DATA", "data.pkl"), "rb"))
B, DL, VX = D["bars"], D["daily"], D["vix"]
IVM = {"QQQ":1.15, "SPY":1.0}
CAL = {"QQQ":2.1, "SPY":1.65}
R = 0.043
TOUCH = False
def ncdf(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
def bsm(side, S, K, hrs, iv):
    tau = max(hrs, 0.02)/24/365
    d1 = (math.log(S/K)+(R+iv*iv/2)*tau)/(iv*math.sqrt(tau)); d2 = d1-iv*math.sqrt(tau)
    if side=="call": return S*ncdf(d1)-K*math.exp(-R*tau)*ncdf(d2)
    return K*math.exp(-R*tau)*ncdf(-d2)-S*ncdf(-d1)
def hm(s): h,m = map(int,s.split(":")); return h*60+m
def fmt(m): return f"{m//60:02d}:{m%60:02d}"
def hrs_left(endmin): return (16*60-endmin)/60
def days(sym, lo="2026-02-24", hi="2026-10-30"):
    return [d for d in sorted(B[sym]) if lo<=d<=hi and len(B[sym][d])>=70]
def prevday(sym, d):
    ks = [k for k in sorted(DL[sym]) if k<d]; return ks[-1] if ks else None
def setup(sym, d, entry="09:45", cover_lo=0.40, cover_hi=1.0, gmin=0.2, gmax=1.5, vixf=True):
    bs = B[sym][d]; pd = prevday(sym, d)
    if pd is None or "09:30" not in bs: return None
    pc = DL[sym][pd][3]; ph, pl = DL[sym][pd][1], DL[sym][pd][2]
    op = bs["09:30"][0]; gap = (op/pc-1)*100
    if not (gmin <= abs(gap) < gmax): return None
    vchg = None
    if d in VX and pd in VX: vchg = (VX[d][0]/VX[pd][1]-1)*100
    if vixf and vchg is not None and abs(vchg) >= 5: return None
    eb = fmt(hm(entry)-5)
    if eb not in bs: return None
    ep = bs[eb][3]
    cover = (op-ep)/(op-pc)
    # 이미 메움: 진입 전 봉에서 전일 종가 터치
    pre = [bs[k] for k in sorted(bs) if hm(k) < hm(entry)]
    touched = any((b[2] <= pc) if gap>0 else (b[1] >= pc) for b in pre)
    if (TOUCH and touched) or cover >= cover_hi or cover < cover_lo: return None
    rv = abs(ep-pc)/(ph-pl)
    return dict(sym=sym, d=d, pc=pc, op=op, gap=gap, ep=ep, cover=cover, rv=rv, vchg=vchg,
                side=("put" if gap>0 else "call"), vix=VX.get(d,(None,))[0], entry=entry)
def strike_for(s, mode):
    ep, pc, side = s["ep"], s["pc"], s["side"]
    sg = 1 if side=="put" else -1   # put: ITM = 행사가 위
    if mode=="itm08": k = ep*(1+sg*0.008)
    elif mode=="itm04": k = ep*(1+sg*0.004)
    elif mode=="atm": k = ep
    elif mode=="mid": k = (ep+pc)/2
    elif mode=="target": k = pc
    elif mode=="beyond": k = pc - (ep-pc)*0.5   # 목표 너머: 남은 거리의 절반 더
    else: raise ValueError(mode)
    return float(round(k))
def sim(s, exit="take", strike="itm08", timecut="11:30", cut="14:00", cal=True, trail=0.0015):
    sym, d = s["sym"], s["d"]; bs = B[sym][d]
    iv = (s["vix"] or 18)/100*IVM[sym]*(CAL[sym] if cal else 1)
    K = strike_for(s, strike); side = s["side"]
    t0 = hm(s["entry"])
    prem0 = bsm(side, s["ep"], K, hrs_left(t0), iv)
    pc = s["pc"]; up = s["gap"]>0
    keys = [k for k in sorted(bs) if hm(k) >= t0]
    filled=False; ext=None; res=None; px=None; tend=None; fill_t=None
    for k in keys:
        o,h,l,c = bs[k]; end = hm(k)+5
        if not filled:
            hit = (l <= pc) if up else (h >= pc)
            if hit:
                filled=True; fill_t=fmt(end)
                if exit=="take": res,px,tend="TAKE",c,end; break
                if exit=="limit": res,px,tend="LIMIT",pc,end; break
                ext = l if up else h
                # 트레일: 같은 봉 종가로도 판정
                if (up and c > ext*(1+trail)) or ((not up) and c < ext*(1-trail)):
                    res,px,tend="TRAIL",c,end; break
                continue
            if timecut and end >= hm(timecut): res,px,tend="TIMECUT",c,end; break
        else:
            ext = min(ext,l) if up else max(ext,h)
            if (up and c > ext*(1+trail)) or ((not up) and c < ext*(1-trail)):
                res,px,tend="TRAIL",c,end; break
        if end >= hm(cut): res,px,tend="CUT",c,end; break
    if res is None: k=keys[-1]; res,px,tend="EOD",bs[k][3],hm(k)+5
    prem1 = bsm(side, px, K, hrs_left(tend), iv)
    pnl = max((prem1/prem0-1)*100-2.2, -100)
    return dict(s, res=res, pnl=pnl, K=K, prem0=prem0, fill_t=fill_t, exit_t=fmt(tend))
def stats(tr):
    p=[t["pnl"] for t in tr]
    if not p: return dict(n=0)
    w=sum(x for x in p if x>0); l=-sum(x for x in p if x<0)
    eq=0; pk=0; dd=0
    for x in p: eq+=x; pk=max(pk,eq); dd=max(dd,pk-eq)
    s2=sorted(p,reverse=True)[2:]; w2=sum(x for x in s2 if x>0)
    return dict(n=len(p), win=round(100*sum(x>0 for x in p)/len(p)), sum=round(sum(p)), loss=round(-l),
                worst=round(min(p)), pf=round(w/l,2) if l else 99, pf2=round(w2/l,2) if l else 99, dd=round(dd))

def run(entry="09:45", put_exit="take", call_exit="limit", put_k="itm08", call_k="itm08", call_rv=0.2,
        timecut="11:30", one=True, cal=True, lo="2026-02-24", hi="2026-10-30", syms=("QQQ","SPY"), **sk):
    out=[]
    alld = sorted(set(d for s in syms for d in days(s, lo, hi)))
    for d in alld:
        for sym in syms:
            if d not in B[sym] or len(B[sym][d])<70: continue
            s = setup(sym, d, entry=entry, **sk)
            if not s: continue
            if s["side"]=="call" and call_rv is not None and s["rv"] >= call_rv: continue
            if s["side"]=="call" and call_rv == -1: continue
            ex = put_exit if s["side"]=="put" else call_exit
            k = put_k if s["side"]=="put" else call_k
            out.append(sim(s, exit=ex, strike=k, timecut=timecut, cal=cal))
            if one: break
    return out
def half(tr):
    a=[t for t in tr if t["d"]<"2026-07-01"]; b=[t for t in tr if t["d"]>="2026-07-01"]
    return stats(a), stats(b)
def money(tr, stake=1000):
    return round(stake + sum(stake*t["pnl"]/100 for t in tr))
