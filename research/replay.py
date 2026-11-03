"""가짜 yfinance + 가짜 시각으로 odte.step()을 하루 동안 5분마다 돌린다. 사용: python replay.py LOG_IN LOG_OUT 날짜..."""
import sys, os, json, shutil, pickle, math, types, datetime as _dt
from zoneinfo import ZoneInfo
import pandas as pd
NY = ZoneInfo("America/New_York")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
D = pickle.load(open(os.environ.get("GAPBT_DATA", "data.pkl"), "rb"))
B, VX = D["bars"], D["vix"]
NOW = [None]

class FakeDT(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        n = NOW[0]
        return n if tz is None else n.astimezone(tz)
shim = types.ModuleType("dtshim")
shim.datetime, shim.date, shim.time, shim.timedelta, shim.timezone = FakeDT, _dt.date, _dt.time, _dt.timedelta, _dt.timezone

def frame(sym, period):
    now = NOW[0]; today = now.date().isoformat()
    ds = sorted(d for d in B[sym] if d <= today)
    n = 3 if period in ("3d", "1d") else 60
    if period == "1d": n = 1
    rows = []
    for d in ds[-n:]:
        for hm, (o, h, l, c) in sorted(B[sym][d].items()):
            t = _dt.datetime.fromisoformat(f"{d}T{hm}").replace(tzinfo=NY)
            if t + _dt.timedelta(minutes=5) <= now:
                rows.append((t, o, h, l, c, 1000.0))
    df = pd.DataFrame(rows, columns=["t", "Open", "High", "Low", "Close", "Volume"]).set_index("t")
    return df

def ncdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))
def bsm(cp, S, K, tau, iv, r=0.043):
    d1 = (math.log(S / K) + (r + iv * iv / 2) * tau) / (iv * math.sqrt(tau)); d2 = d1 - iv * math.sqrt(tau)
    return S * ncdf(d1) - K * math.exp(-r * tau) * ncdf(d2) if cp == "c" else K * math.exp(-r * tau) * ncdf(-d2) - S * ncdf(-d1)

class Ticker:
    def __init__(self, sym): self.sym = sym
    def history(self, period="1d", interval="1d", **kw):
        if self.sym in B and interval == "5m":
            return frame(self.sym, period)
        if self.sym == "^VIX" and interval == "1d":
            today = NOW[0].date().isoformat()
            ks = sorted(k for k in VX if k <= today)[-5:]
            rows = [(pd.Timestamp(k).tz_localize(NY), VX[k][0], (VX[k][1] if k < today else VX[k][0])) for k in ks]
            return pd.DataFrame(rows, columns=["t", "Open", "Close"]).set_index("t")
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    def option_chain(self, expiry):
        df = frame(self.sym, "1d"); S = float(df["Close"].iloc[-1])
        now = NOW[0]; h = max(16 - (now.hour + now.minute / 60), 0.02); tau = h / 24 / 365
        vix = VX.get(now.date().isoformat(), (18, 18))[0] / 100 * (1.15 if self.sym == "QQQ" else 1.0)
        ks = [float(k) for k in range(int(S * 0.96), int(S * 1.04) + 1)]
        mk = lambda cp: pd.DataFrame([dict(strike=k, bid=round(bsm(cp, S, k, tau, vix), 2), ask=round(bsm(cp, S, k, tau, vix), 2),
                                           lastPrice=round(bsm(cp, S, k, tau, vix), 2), impliedVolatility=vix,
                                           contractSymbol=f"{self.sym}{k}") for k in ks])
        return types.SimpleNamespace(calls=mk("c"), puts=mk("p"))
fake_yf = types.SimpleNamespace(Ticker=Ticker, download=lambda *a, **k: pd.DataFrame())

import odte
odte.yf = fake_yf; odte.dt = shim
odte.vix_gate = lambda: dict(state="ERR", msg="replay", pct=0.0, ratio=0.0, asof="-")
odte.premarket_pos = lambda: None
odte.macro_match = lambda: None

def run_day(d, quiet=True):
    import io, contextlib
    t = _dt.datetime.fromisoformat(f"{d}T09:20:15").replace(tzinfo=NY)
    end = _dt.datetime.fromisoformat(f"{d}T16:00:15").replace(tzinfo=NY)
    buf = io.StringIO()
    while t <= end:
        NOW[0] = t
        with contextlib.redirect_stdout(buf):
            try: odte.step()
            except Exception as e: print("STEP ERR", type(e).__name__, e)
        t += _dt.timedelta(minutes=5)
    out = buf.getvalue()
    return [l for l in out.splitlines() if ("갭v2" in l or "실패" in l or "ERR" in l or "Traceback" in l or "Error" in l)]

if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    shutil.copy(src, dst)
    odte.LOG = dst; odte.OUT = dst.replace(".json", ".html")
    for d in sys.argv[3:]:
        lines = run_day(d)
        print(d, *[" " + l for l in lines[:12]], sep="\n")
    log = odte.load_log(); tr = log.get("gap_v2", {})
    for t in tr.get("trades", []):
        print(f"  거래 {t['date']} {t['tk']} {t['opt_side']} K{t['strike']:.0f} {t['at']}→{t['exit_at']} {t['res']} {t['pnl_pct']:+.1f}%  rv={t['rv']} cover={t['cover']}")
    for d, v in tr.get("days", {}).items():
        print("  일지", d, v.get("pick"), v.get("why",""), "| QQQ:", v["QQQ"]["why"], "| SPY:", v["SPY"]["why"])
    NOW[0] = _dt.datetime.fromisoformat(f"{sys.argv[-1]}T16:30:00").replace(tzinfo=NY)
    open(odte.OUT, "w").write(odte.render(log, None))
