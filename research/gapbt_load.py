import json, glob, pickle, collections
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
import sys
TR = (sys.argv[1] if len(sys.argv) > 1 else ".") + "/"   # 로빈후드 MCP 응답 JSON들이 있는 폴더 (레포에 커밋 금지)
bars = collections.defaultdict(lambda: collections.defaultdict(dict))  # sym -> date -> {hhmm: (o,h,l,c)}
daily = collections.defaultdict(dict)
for f in sorted(glob.glob(TR + "mcp-Robinhood-get_equity_historicals-*.txt")):
    d = json.load(open(f))
    for r in d["data"]["results"]:
        iv = r["interval"]
        for b in r["bars"]:
            if b.get("interpolated"): continue
            t = datetime.fromisoformat(b["begins_at"].replace("Z", "+00:00"))
            o,h,l,c = (float(b[k]) for k in ("open_price","high_price","low_price","close_price"))
            if iv == "day":
                daily[r["symbol"]][b["begins_at"][:10]] = (o,h,l,c)
            else:
                te = t.astimezone(ET)
                bars[r["symbol"]][te.date().isoformat()][te.strftime("%H:%M")] = (o,h,l,c)
vix = {}
for line in open("vix.txt"):
    dd, o, c = line.split(); vix[dd] = (float(o), float(c))
out = dict(bars={s:{d:dict(v) for d,v in dd.items()} for s,dd in bars.items()}, daily=dict(daily), vix=vix)
pickle.dump(out, open("data.pkl","wb"))
for s in out["bars"]:
    ds = sorted(out["bars"][s]); full=[d for d in ds if len(out["bars"][s][d])>=70]
    print(s, len(ds), "days", ds[0], ds[-1], "full", len(full))
for s in daily: print(s, "daily", len(daily[s]), min(daily[s]), max(daily[s]))
