# -*- coding: utf-8 -*-
"""0DTE 모의매매 화면 (2026-11-03 개편).

odte.render()가 이 모듈의 render(log, st, A)를 부른다. A = odte 모듈(상수·시간대).
여기서 예외가 나면 odte는 예전 화면(render_legacy)으로 되돌아간다.
"""
import html
import datetime as dt

E = html.escape


# ───────────────────────── 공통 조각 ─────────────────────────
def _pc(x, nd=0, sign=True):
    if x is None:
        return "—"
    return f"{x:+.{nd}f}%" if sign else f"{x:.{nd}f}%"


def _cls(x):
    return "up" if (x or 0) > 0 else ("dn" if (x or 0) < 0 else "")


def _money(x, sign=False):
    if x is None:
        return "—"
    return f"{'+' if sign and x > 0 else ''}{'-' if x < 0 else ''}${abs(x):,.0f}"


def book_rows(books, sizes, cap0):
    """사용 비율별 북 요약 → [(k, cap, pl, n, wins, skips, mdd)]"""
    out = []
    for f in sizes:
        k = str(int(round(f * 100)))
        bk = (books or {}).get(k) or dict(cap=cap0, trades=[])
        tl = bk.get("trades", [])
        real = [x for x in tl if x.get("res") != "SKIP_FUND" and x.get("nc", 1) > 0]
        sk = len(tl) - len(real)
        c = cap0; peak = cap0; mdd = 0.0
        for x in real:
            c += x.get("usd", 0.0); peak = max(peak, c); mdd = max(mdd, (peak - c) / peak * 100)
        wins = sum(1 for x in real if x.get("usd", 0) > 0)
        out.append((k, bk.get("cap", cap0), bk.get("cap", cap0) - cap0, len(real), wins, sk, mdd))
    return out


def books_html(books, sizes, cap0, note=""):
    rows = book_rows(books, sizes, cap0)
    mx = max([abs(r[2]) for r in rows] + [1])
    h = ""
    for k, cap, pl, n, w, sk, mdd in rows:
        if n == 0 and sk > 0:
            sub = f"계약값이 커서 못 삼 {sk}회"
        elif n == 0:
            sub = "아직 거래 없음"
        else:
            sub = f"{n}건 · 승률 {w / n * 100:.0f}% · 낙폭 {mdd:.0f}%" + (f" · 못 삼 {sk}" if sk else "")
        bw = abs(pl) / mx * 100
        h += (f'<div class="brow"><div class="bpill">{k}%</div>'
              f'<div class="bmid"><div class="bcap">${cap:,.0f}</div><div class="bsub">{sub}</div>'
              f'<div class="bbar"><i class="{_cls(pl)}" style="width:{bw:.0f}%"></i></div></div>'
              f'<div class="bpl {_cls(pl)}">{_money(pl, True)}</div></div>')
    return (f'<div class="card"><div class="ch"><span>계좌 ${cap0:,.0f} · 사용 비율별</span>'
            f'<span class="mut">{note}</span></div>{h}</div>')


def stat_tiles(trades):
    tl = [t for t in trades if t.get("pnl_pct") is not None]
    n = len(tl)
    w = sum(1 for t in tl if t["pnl_pct"] > 0)
    tot = sum(t["pnl_pct"] for t in tl)
    worst = min([t["pnl_pct"] for t in tl] + [0])
    loss = sum(t["pnl_pct"] for t in tl if t["pnl_pct"] < 0)
    return (f'<div class="tiles">'
            f'<div class="tile"><b>{n}</b><span>거래</span></div>'
            f'<div class="tile"><b>{(w / n * 100 if n else 0):.0f}%</b><span>승률</span></div>'
            f'<div class="tile"><b class="{_cls(tot)}">{tot:+.0f}%</b><span>합계</span></div>'
            f'<div class="tile"><b class="{_cls(worst)}">{worst:.0f}%</b><span>최악</span></div>'
            f'</div><div class="mut sm">손실 난 거래 합계 {loss:.0f}%</div>')


RES_KO = {"TAKE": "메움 즉시 청산", "LIMIT": "전일 종가 지정가", "TIMECUT": "11:30 미필 정리",
          "CUT": "14:00 마감", "EOD": "장 마감", "TRAIL": "트레일 청산", "TRAIL(1분)": "1분 트레일",
          "STOP(OR)": "OR 손절"}


def _res_ko(r):
    r = str(r or "")
    base = r.split("·")[0]
    tag = " · 소급" if ("소급" in r) else ""
    return RES_KO.get(base, base) + tag


def trade_list(trades, uid, limit=40, show_tk=True):
    """기록 목록 — 행을 누르면 상세가 펼쳐진다."""
    h = ""
    for i, t in enumerate(reversed(trades[-limit:])):
        side = t.get("opt_side") or t.get("side") or "call"
        put = side == "put"
        tk = t.get("tk") or "QQQ"
        k = t.get("strike")
        pnl = t.get("pnl_pct")
        at = t.get("at") or t.get("entry_time") or ""
        ex = t.get("exit_at") or t.get("exit_time") or ""
        res = t.get("res") or t.get("reason") or ""
        mp = t.get("mfe_prem")
        mp = None if (mp is None or mp < -90) else mp
        ct = " · ".join(f"{a}% {b}계약" for a, b in sorted((t.get("contracts") or {}).items(),
                                                          key=lambda x: int(x[0])) if b)
        det = [("진입", f"{at} · 기초 {t.get('entry', t.get('entry_px', '—'))}"),
               ("청산", f"{ex} · {E(_res_ko(res))}"),
               ("옵션가", f"${t.get('premium', '—')} → ${t.get('exit_premium', t.get('eff_exit', '—'))}"),
               ("계약당", _money(t.get("per_contract", t.get("pnl_usd")), True))]
        if t.get("gap") is not None:
            det.append(("갭 · 커버", f"{t['gap']:+.2f}% · {t.get('cover', 0) or 0:.2f}"))
        if t.get("rv") is not None:
            det.append(("rv", f"{t['rv']:.2f}"))
        if t.get("target") not in (None, "러너"):
            det.append(("목표(전일 종가)", f"{t['target']}"))
        if t.get("fill_t"):
            det.append(("메운 시각", t["fill_t"]))
        if mp is not None:
            det.append(("옵션 최고", f"{mp:+.0f}% @ {t.get('mfe_prem_t') or ''}"))
        if t.get("pnl_q") is not None:
            det.append(("야후 호가(지연)", f"{t['pnl_q']:+.1f}% — 참고"))
        if ct:
            det.append(("비율별 계약", ct))
        dh = "".join(f'<div><span>{a}</span><b>{b}</b></div>' for a, b in det)
        tag = '<em>소급</em>' if (t.get("recon") or t.get("catchup")) else ""
        h += (f'<div class="trow" data-t="{uid}{i}">'
              f'<div class="ico {"p" if put else "c"}">{"↘" if put else "↗"}</div>'
              f'<div class="tmid"><div class="tt">{t.get("date", "")[5:].replace("-", "/")} · '
              f'{(tk + " ") if show_tk else ""}{(f"{k:.0f}" if isinstance(k, (int, float)) else "")}'
              f'{"P" if put else "C"} {tag}</div>'
              f'<div class="ts">{E(_res_ko(res))} · {at}→{ex}</div></div>'
              f'<div class="tpl {_cls(pnl)}">{_pc(pnl)}</div><div class="arr">›</div></div>'
              f'<div class="tdet" id="{uid}{i}">{dh}</div>')
    return h or '<div class="empty">아직 기록이 없습니다</div>'


def _pos_card(p, A, title="보유 중"):
    put = p.get("opt_side") == "put"
    tk = p.get("tk") or "QQQ"
    spot = p.get("now_spot") or p.get("spot_rt") or p.get("entry")
    prem_now = p.get("now_prem")
    live = None
    if prem_now and p.get("premium"):
        live = (prem_now / p["premium"] - 1) * 100 - A.RT_SPREAD
    prog = None
    try:
        tgt = float(p["target"]); ent = float(p["entry"])
        prog = max(0.0, min(1.0, (ent - spot) / (ent - tgt))) if ent != tgt else 1.0
    except Exception:
        pass
    rule = p.get("exit_rule") or "규칙대로 청산"
    fill = f'메움 {p["fill_t"]}' if p.get("filled") else "메우기 전 · 11:30까지 못 메우면 정리"
    bar = (f'<div class="prog"><div class="pbar"><i style="width:{prog * 100:.0f}%"></i></div>'
           f'<div class="plab"><span>진입 {p["entry"]}</span><span>지금 {spot}</span>'
           f'<span>목표 {p["target"]}</span></div></div>') if prog is not None else ""
    ct = " · ".join(f"{a}% {b}" for a, b in sorted((p.get("contracts") or {}).items(),
                                                   key=lambda x: int(x[0])) if b)
    return (f'<div class="card hero"><div class="ch"><span>{title}</span>'
            f'<span class="chip">{E(rule)}</span></div>'
            f'<div class="pos-h"><div><div class="big">{tk} {p["strike"]:.0f}{"P" if put else "C"}</div>'
            f'<div class="mut">{p.get("at", "")} 진입 · ${p["premium"]} · 갭 {p.get("gap", 0):+.2f}%</div></div>'
            f'<div class="big {_cls(live)}">{_pc(live, 1) if live is not None else "—"}</div></div>'
            f'{bar}<div class="mut sm">{fill}{(" · 계약 " + ct) if ct else ""}</div></div>')


def _tick_tile(c, picked, today_done):
    tk = c.get("tk")
    ok = c.get("ok"); wait = c.get("wait")
    st = "진입" if picked else ("대기" if wait and not today_done else ("조건 충족" if ok else "스킵"))
    cl = "go" if picked else ("wait" if st == "대기" else ("ok" if ok else "no"))
    g = c.get("gap"); cv = c.get("cover"); rv = c.get("rv")
    side = c.get("side")
    sd = ("갭업 → 풋" if side == "put" else "갭다운 → 콜") if side else ""
    return (f'<div class="tk {cl}"><div class="tk-h"><div class="tk-ic">{tk[0]}</div>'
            f'<span class="tk-st">{st}</span></div>'
            f'<div class="tk-n">{tk}</div><div class="tk-s">{sd}</div>'
            f'<div class="tk-kv"><span>갭</span><b>{_pc(g, 2)}</b></div>'
            f'<div class="tk-kv"><span>커버</span><b>{"—" if cv is None else f"{cv:.2f}"}</b></div>'
            f'<div class="tk-kv"><span>rv</span><b>{"—" if rv is None else f"{rv:.2f}"}</b></div>'
            f'<div class="tk-w">{E(c.get("why") or "")}</div></div>')


# ───────────────────────── 탭: 갭필 ─────────────────────────
def gap_tab(log, A, now):
    tr = log.get(A.V2_KEY) or {}
    today = str(now.date())
    trades = tr.get("trades", [])
    day = (tr.get("days") or {}).get(today)
    live = tr.get("live") or {}
    pos = tr.get("open")
    # 오늘 판정 카드
    checks = (day and {"QQQ": day.get("QQQ"), "SPY": day.get("SPY")}) or \
             (live.get("checks") if live.get("d") == today else None)
    pick = (day or {}).get("pick")
    if checks:
        tiles = "".join(_tick_tile(dict(checks[t] or {}, tk=t), pick == t, day is not None)
                        for t in A.V2_TICKERS)
        why = (day or {}).get("why")
        decided = (f'{day.get("at")} 판정 · ' + (f"{pick} 진입" if pick else "진입 없음")) if day else \
            f'{live.get("at", "")} 기준 · 09:45에 판정'
        today_html = (f'<div class="card"><div class="ch"><span>오늘 판정</span><span class="mut">{decided}</span></div>'
                      f'<div class="tks">{tiles}</div>'
                      + (f'<div class="mut sm">{E(why)}</div>' if why else "")
                      + '<div class="mut sm">QQQ가 먼저 · QQQ가 안 걸리면 SPY · 하루 1건</div></div>')
    else:
        today_html = ('<div class="card"><div class="ch"><span>오늘 판정</span></div>'
                      '<div class="empty">장 전 · 09:45에 QQQ → SPY 순서로 판정합니다</div></div>')
    pos_html = _pos_card(pos, A) if (pos and pos.get("res") is None) else ""
    # 일자별 판정 기록
    jr = ""
    for d in sorted(tr.get("days") or {}, reverse=True)[:30]:
        v = tr["days"][d]
        pk = v.get("pick")
        tt = next((t for t in reversed(trades) if t.get("date") == d), None)
        rt = (f'<b class="{_cls(tt["pnl_pct"])}">{_pc(tt["pnl_pct"])}</b>' if tt else
              ('<b>보유</b>' if pk else '<b class="mut">—</b>'))
        q = (v.get("QQQ") or {}).get("why", ""); s = (v.get("SPY") or {}).get("why", "")
        jr += (f'<div class="jrow"><span class="jd">{d[5:].replace("-", "/")}</span>'
               f'<span class="jm">{"<i>" + pk + "</i> " if pk else ""}QQQ {E(q)}<br>SPY {E(s)}'
               f'{("<br>" + E(v["why"])) if v.get("why") else ""}</span>{rt}</div>')
    journal = (f'<details class="card fold"><summary>일자별 판정 기록 <span class="mut">왜 들어갔고 왜 안 들어갔는지</span></summary>'
               f'{jr or "<div class=empty>기록은 11/4부터 쌓입니다</div>"}</details>')
    rules = ('<details class="card fold"><summary>규칙 보기</summary><div class="rules">'
             '<p><b>진입</b> 09:45 · 갭 0.2~1.5% · VIX 개장변화 5% 미만 · 커버 0.40~1.0 · ITM 0.8% 0DTE</p>'
             '<p><b>방향</b> 갭업 → 풋 / 갭다운 → 콜(남은거리÷전일 폭 rv &lt; 0.20일 때만)</p>'
             '<p><b>청산</b> 풋은 메우는 순간 · 콜은 전일 종가 지정가 · 못 메우면 11:30 정리</p>'
             '<p><b>종목</b> QQQ 먼저, 안 걸리면 SPY · 하루 1건</p>'
             '<p class="mut">백테스트(로빈후드 5분봉 2/24~10/30, 보정 IV): 23건 +307% · 손실 합 -16 · 최악 -8</p>'
             '</div></details>')
    old = legacy_gap(log, A)
    return (today_html + pos_html
            + books_html(tr.get("books"), A.V2_SIZES, A.V2_CAPITAL, "각 비율 독립")
            + f'<div class="card"><div class="ch"><span>성과</span><span class="mut">11/4 시작 · 모델가</span></div>'
            + stat_tiles(trades) + '</div>'
            + f'<div class="card"><div class="ch"><span>거래 기록</span><span class="mut">누르면 상세</span></div>'
            + trade_list(trades, "v") + '</div>'
            + journal + rules + old)


def _pf(trs):
    w = sum(t["pnl_pct"] for t in trs if t.get("pnl_pct", 0) > 0)
    l = -sum(t["pnl_pct"] for t in trs if t.get("pnl_pct", 0) < 0)
    return (w / l) if l else None


def legacy_gap(log, A):
    """이전 갭필(챔피언 15m|now와 비교 트랙들) — 접어두고 눌러야 보인다."""
    tracks = log.get("gap_tracks") or {}
    names = {"15m|now": "챔피언 · 15분 즉시 · 트레일", "15m|take": "15분 · 메운 순간 청산",
             "15m|1m": "15분 · 1분 확인 트레일", "15m|vwap": "15분 · VWAP 대기",
             "5m|now": "5분 즉시", "5m|vwap": "5분 · VWAP 대기", "1h|now": "1시간 즉시", "1h|vwap": "1시간 · VWAP 대기"}
    order = ["15m|now", "15m|take", "15m|1m", "15m|vwap", "5m|now", "5m|vwap", "1h|now", "1h|vwap"]
    rows = ""
    for k in order:
        tl = (tracks.get(k) or {}).get("trades", [])
        n = len(tl); w = sum(1 for t in tl if t.get("pnl_pct", 0) > 0)
        s = sum(t.get("pnl_pct", 0) for t in tl); pf = _pf(tl)
        op = (tracks.get(k) or {}).get("open")
        rows += (f'<div class="lrow"><span>{names.get(k, k)}{" <i>보유</i>" if op else ""}</span>'
                 f'<span>{n}건 · {(w / n * 100 if n else 0):.0f}%</span>'
                 f'<span class="{_cls(s)}">{s:+.0f}%</span><span>PF {"—" if pf is None else f"{pf:.2f}"}</span></div>')
    ch = tracks.get("15m|now") or {}
    cpos = ch.get("open")
    inner = ((_pos_card(cpos, A, "챔피언 보유 중") if (cpos and cpos.get("res") is None) else "")
             + f'<div class="sub">트랙 비교 <span class="mut">진입은 같고 청산·타이밍만 다름</span></div>{rows}'
             + books_html(ch.get("books"), A.GAP_SIZES, A.GAP_CAPITAL, "챔피언")
             + f'<div class="sub">챔피언 기록</div>' + trade_list(ch.get("trades", []), "o", show_tk=False))
    return (f'<details class="card fold old"><summary>이전 갭필 <span class="mut">챔피언 15분·트레일과 비교 트랙 '
            f'{sum(len((tracks.get(k) or {}).get("trades", [])) for k in order)}건</span></summary>{inner}</details>')


# ───────────────────────── 탭: 모멘텀 ─────────────────────────
def mom_tab(log, A, now):
    mtr = log.get("mom_track") or {}
    ms = log.get("mom_sig") or {}
    today = str(now.date())
    st = ms.get("state") if ms.get("d") == today else None
    lab = {"GO": "진입 조건", "VETO": "VIX 역행 · 관망", "NO": "대상 아님", "WAIT": "대기", "ERR": "오류", "OFF": "갭 없음"}
    sig = (f'<div class="card"><div class="ch"><span>오늘 신호</span><span class="chip">{lab.get(st, "장 전")}</span></div>'
           f'<div class="mut">{E(ms.get("why") or "09:45에 판정 — 커버 0.40 미만 + VIX가 갭 방향을 확인하면 갭 방향으로 진입")}</div></div>')
    pos = mtr.get("open")
    ph = ""
    if pos and pos.get("res") is None:
        p2 = dict(pos); p2["target"] = pos.get("trail_px") or pos.get("entry")
        ph = (f'<div class="card hero"><div class="ch"><span>보유 중</span><span class="chip">트레일 0.30%</span></div>'
              f'<div class="big">QQQ {pos["strike"]:.0f}{"P" if pos.get("opt_side") == "put" else "C"}</div>'
              f'<div class="mut">{pos.get("at")} 진입 · ${pos["premium"]} · OR 손절 {pos.get("or_stop")} · 트레일 {pos.get("trail_px", "—")}</div></div>')
    tl = mtr.get("trades", [])
    return (sig + ph + books_html(mtr.get("books"), A.GAP_SIZES, A.GAP_CAPITAL, "보관 트랙")
            + f'<div class="card"><div class="ch"><span>성과</span></div>{stat_tiles(tl)}</div>'
            + f'<div class="card"><div class="ch"><span>거래 기록</span><span class="mut">누르면 상세</span></div>'
            + trade_list(tl, "m", show_tk=False) + '</div>')


# ───────────────────────── 탭: 3층 ─────────────────────────
def l3_tab(log, A, st, now):
    vg = log.get("vix") or {}; pmv = log.get("pm"); op = log.get("open")

    def lamp(c, name, txt):
        return f'<div class="gate"><i class="{c}"></i><b>{name}</b><span>{txt}</span></div>'
    if vg.get("state") == "LIVE":
        l1 = lamp("go", "L1 변동성", f'통과 · 백분위 {vg["pct"]:.0f}%')
    elif vg.get("state") == "DEAD":
        l1 = lamp("no", "L1 변동성", f'미달 · 백분위 {vg["pct"]:.0f}% &lt; 50')
    else:
        l1 = lamp("wait", "L1 변동성", "조회 실패")
    if pmv and pmv.get("ok"):
        l2 = lamp("go", "L2 프리마켓", f'통과 · 위치 {pmv["pos"]:.2f}')
    elif pmv:
        l2 = lamp("no", "L2 프리마켓", f'미달 · 위치 {pmv["pos"]:.2f} ≤ 0.5')
    else:
        l2 = lamp("wait", "L2 프리마켓", "데이터 없음")
    if op:
        l3 = lamp("go", "L3 트리거", "보유 중")
    elif st and st.get("dev") is not None and st["dev"] <= -A.ENTRY_BAND_SIG:
        l3 = lamp("go", "L3 트리거", f'VWAP -1σ 터치 ({st["dev"]:+.2f}σ)')
    elif st:
        l3 = lamp("wait", "L3 트리거", f'-1σ 대기 (지금 {st["dev"]:+.2f}σ)')
    else:
        l3 = lamp("wait", "L3 트리거", "장외")
    d = (log.get("days") or {}).get(str(now.date()), {})
    gate = (f'<div class="card"><div class="ch"><span>3층 게이트</span></div>{l1}{l2}{l3}'
            f'<div class="mut sm">{E(d.get("status", "세션 대기"))}</div></div>')
    ph = ""
    if op:
        ph = (f'<div class="card hero"><div class="ch"><span>보유 중</span></div>'
              f'<div class="big">QQQ {op["strike"]:.0f}C</div>'
              f'<div class="mut">{op.get("entry_time")} 진입 · ${op["premium"]} · 손절(기초) {op.get("stop_px", "—")}</div></div>')
    itm = [t for t in log.get("trades", []) if str(t.get("version", "")).startswith("itm")]
    return (gate + ph + books_html(log.get("l3_books"), A.L3_SIZES, A.CAPITAL_START, "보관 트랙")
            + f'<div class="card"><div class="ch"><span>성과</span></div>{stat_tiles(itm)}</div>'
            + f'<div class="card"><div class="ch"><span>거래 기록</span><span class="mut">누르면 상세</span></div>'
            + trade_list(itm, "l", show_tk=False) + '</div>')


# ───────────────────────── 탭: 매크로 ─────────────────────────
def macro_tab(log):
    mm = log.get("macro")
    if not mm:
        return '<div class="card"><div class="empty">매크로 유사일 데이터 없음 (장중 갱신)</div></div>'
    chips = "".join(f'<span class="chip">{E(x["name"])} {x["chg"]:+.2f}% · {x["pct"]}백분위</span>'
                    for x in mm.get("extremes", []))
    nu, nd = len(mm.get("up", [])), len(mm.get("dn", []))
    tot = max(nu + nd, 1)

    def lst(xs, cl):
        return "".join(f'<div class="jrow"><span class="jd">{x["d"][2:].replace("-", "/")}</span>'
                       f'<span class="jm">갭 {x["gap"]:+.2f}%</span><b class="{cl}">{x["ret"]:+.2f}%</b></div>'
                       for x in xs) or '<div class="empty">없음</div>'
    return (f'<div class="card"><div class="ch"><span>오늘 매크로 · 가장 극단인 4개</span></div>'
            f'<div class="chips">{chips}</div><div class="mut sm">과거 {mm["n_hist"]}일 · 지표 {mm["n_feat"]}개로 유사일 검색 · 참고용</div></div>'
            f'<div class="card"><div class="ch"><span>유사일 평균 움직임 폭</span></div>'
            f'<div class="big">{mm["rng"]:.2f}%</div><div class="mut">전체 평균 {mm["base_rng"]:.2f}% · '
            f'저점 {mm["lo_avg"]:+.2f}% · 고점 {mm["hi_avg"]:+.2f}%</div></div>'
            f'<div class="card"><div class="ch"><span>유사했던 {nu + nd}일의 결말</span></div>'
            f'<div class="split"><i class="up" style="width:{nu / tot * 100:.0f}%"></i><i class="dn" style="width:{nd / tot * 100:.0f}%"></i></div>'
            f'<div class="plab"><span class="up">상승 {nu}일</span><span class="dn">하락 {nd}일</span></div>'
            f'<div class="sub">올랐던 날</div>{lst(mm.get("up", []), "up")}'
            f'<div class="sub">빠졌던 날</div>{lst(mm.get("dn", []), "dn")}</div>')


# ───────────────────────── 페이지 ─────────────────────────
CSS = """
:root{--bg0:#0b0816;--bg1:#171032;--card:rgba(255,255,255,.045);--line:rgba(196,181,253,.14);
--tx:#efeaff;--mut:#9b93b8;--vi:#a78bfa;--vi2:#7c3aed;--up:#4ade80;--dn:#fb7185;--wait:#fbbf24}
*{margin:0;padding:0;box-sizing:border-box}
html{background:var(--bg0)}
body{min-height:100vh;color:var(--tx);font:15px/1.5 'Pretendard','Noto Sans KR',system-ui,-apple-system,sans-serif;
background:radial-gradient(900px 520px at 85% -10%,rgba(124,58,237,.35),transparent 60%),
radial-gradient(700px 480px at -10% 20%,rgba(167,139,250,.14),transparent 60%),
linear-gradient(180deg,var(--bg1),var(--bg0) 55%);background-attachment:fixed;-webkit-font-smoothing:antialiased}
.wrap{max-width:560px;margin:0 auto;padding:18px 16px 60px}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}
.av{width:38px;height:38px;border-radius:50%;background:linear-gradient(135deg,var(--vi),var(--vi2));
display:grid;place-items:center;font-weight:700;font-size:13px;box-shadow:0 0 0 3px rgba(167,139,250,.18)}
.pill{padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:var(--card);font-size:12px;color:var(--mut)}
.pill b{color:var(--tx);font-weight:600}
h1{font-size:28px;line-height:1.2;font-weight:700;letter-spacing:-.02em}
h1 span{display:block;color:var(--mut);font-size:15px;font-weight:500;margin-bottom:6px;letter-spacing:0}
.headline{margin:4px 0 18px}
.tabs{display:flex;gap:8px;overflow-x:auto;margin:0 -16px 16px;padding:0 16px;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tab{flex:0 0 auto;padding:10px 18px;border-radius:999px;border:1px solid var(--line);background:var(--card);
color:var(--mut);font:600 14px/1 inherit;cursor:pointer}
.tab.on{background:linear-gradient(135deg,#8b5cf6,#6d28d9);color:#fff;border-color:transparent;box-shadow:0 6px 20px rgba(124,58,237,.35)}
.pane{display:none}.pane.on{display:block}
.card{background:var(--card);border:1px solid var(--line);border-radius:22px;padding:16px;margin-bottom:12px;
backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
.card.hero{background:linear-gradient(160deg,rgba(139,92,246,.28),rgba(255,255,255,.04));border-color:rgba(167,139,250,.35)}
.ch{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:12px;font-weight:600;font-size:14px}
.mut{color:var(--mut);font-weight:400;font-size:12.5px}
.sm{margin-top:10px;font-size:12px}
.chip{display:inline-block;padding:4px 10px;border-radius:999px;background:rgba(167,139,250,.16);color:#ddd6fe;font-size:12px;font-weight:500;margin:0 6px 6px 0}
.chips{margin-bottom:4px}
.big{font-size:26px;font-weight:700;letter-spacing:-.01em}
.up{color:var(--up)}.dn{color:var(--dn)}
.empty{color:var(--mut);font-size:13px;padding:10px 2px}
.tks{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.tk{border-radius:18px;padding:12px;background:rgba(255,255,255,.035);border:1px solid var(--line)}
.tk.go{background:linear-gradient(160deg,rgba(139,92,246,.35),rgba(255,255,255,.03));border-color:rgba(167,139,250,.5)}
.tk-h{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.tk-ic{width:30px;height:30px;border-radius:10px;background:rgba(167,139,250,.18);display:grid;place-items:center;font-weight:700;font-size:13px}
.tk-st{font-size:11.5px;padding:3px 9px;border-radius:999px;background:rgba(255,255,255,.07);color:var(--mut)}
.tk.go .tk-st{background:#8b5cf6;color:#fff}.tk.ok .tk-st{color:var(--up)}.tk.wait .tk-st{color:var(--wait)}
.tk-n{font-weight:700;font-size:17px}.tk-s{color:var(--mut);font-size:12px;margin-bottom:8px;min-height:18px}
.tk-kv{display:flex;justify-content:space-between;font-size:13px;padding:2px 0}.tk-kv span{color:var(--mut)}
.tk-w{margin-top:8px;font-size:12px;color:#d4ccf0;line-height:1.4}
.pos-h{display:flex;justify-content:space-between;align-items:flex-end;gap:8px}
.prog{margin-top:14px}.pbar{height:8px;border-radius:99px;background:rgba(255,255,255,.08);overflow:hidden}
.pbar i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#8b5cf6,#c4b5fd)}
.plab{display:flex;justify-content:space-between;font-size:11.5px;color:var(--mut);margin-top:6px}
.brow{display:flex;align-items:center;gap:12px;padding:10px 0;border-top:1px solid rgba(255,255,255,.05)}
.brow:first-of-type{border-top:0}
.bpill{flex:0 0 52px;text-align:center;padding:8px 0;border-radius:14px;background:rgba(167,139,250,.14);font-weight:700;font-size:14px}
.bmid{flex:1;min-width:0}.bcap{font-weight:600}.bsub{font-size:12px;color:var(--mut)}
.bbar{height:4px;border-radius:9px;background:rgba(255,255,255,.06);margin-top:6px;overflow:hidden}
.bbar i{display:block;height:100%;background:var(--vi)}.bbar i.up{background:var(--up)}.bbar i.dn{background:var(--dn)}
.bpl{font-weight:700;min-width:70px;text-align:right}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.tile{background:rgba(255,255,255,.04);border-radius:16px;padding:10px 6px;text-align:center}
.tile b{display:block;font-size:18px}.tile span{font-size:11px;color:var(--mut)}
.trow{display:flex;align-items:center;gap:12px;padding:11px 12px;margin:0 -4px 8px;border-radius:16px;
background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.05);cursor:pointer}
.trow:active{background:rgba(167,139,250,.12)}
.ico{flex:0 0 34px;height:34px;border-radius:12px;display:grid;place-items:center;font-weight:700}
.ico.p{background:rgba(251,113,133,.14);color:var(--dn)}.ico.c{background:rgba(74,222,128,.13);color:var(--up)}
.tmid{flex:1;min-width:0}.tt{font-weight:600;font-size:14px}.tt em{font-style:normal;font-size:11px;color:var(--wait);margin-left:4px}
.ts{font-size:12px;color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tpl{font-weight:700}.arr{color:var(--mut);font-size:18px;transition:transform .2s}
.trow.on .arr{transform:rotate(90deg)}
.tdet{display:none;grid-template-columns:1fr 1fr;gap:8px 12px;padding:4px 10px 14px;font-size:12.5px}
.tdet.on{display:grid}.tdet span{display:block;color:var(--mut);font-size:11px}.tdet b{font-weight:500}
.fold summary{list-style:none;cursor:pointer;font-weight:600;font-size:14px;display:flex;justify-content:space-between;align-items:center;gap:8px}
.fold summary::-webkit-details-marker{display:none}
.fold summary:after{content:'›';color:var(--mut);font-size:20px;transition:transform .2s}
.fold[open] summary:after{transform:rotate(90deg)}
.fold[open] summary{margin-bottom:12px}
.fold.old{background:rgba(255,255,255,.025)}
.fold .card{background:rgba(255,255,255,.03)}
.jrow{display:flex;gap:12px;align-items:flex-start;padding:9px 0;border-top:1px solid rgba(255,255,255,.05);font-size:12.5px}
.jd{flex:0 0 42px;color:var(--mut)}.jm{flex:1;color:#d4ccf0;line-height:1.45}.jm i{font-style:normal;color:var(--vi);font-weight:700}
.lrow{display:grid;grid-template-columns:1fr auto auto auto;gap:10px;font-size:12.5px;padding:8px 0;border-top:1px solid rgba(255,255,255,.05)}
.lrow i{font-style:normal;color:var(--wait)}
.sub{font-weight:600;font-size:13px;margin:14px 0 8px}
.rules p{font-size:13px;margin-bottom:8px;color:#d4ccf0}.rules b{color:var(--tx);margin-right:6px}
.gate{display:flex;align-items:center;gap:10px;padding:9px 0;border-top:1px solid rgba(255,255,255,.05);font-size:13px}
.gate:first-of-type{border-top:0}.gate i{width:10px;height:10px;border-radius:50%;background:var(--mut)}
.gate i.go{background:var(--up)}.gate i.no{background:var(--dn)}.gate i.wait{background:var(--wait)}
.gate b{flex:0 0 92px}.gate span{color:var(--mut)}
.split{display:flex;height:10px;border-radius:99px;overflow:hidden;margin:4px 0}
.split i.up{background:var(--up)}.split i.dn{background:var(--dn)}
.foot{text-align:center;color:var(--mut);font-size:11.5px;margin-top:22px;line-height:1.7}
"""

JS = """
(function(){
  var tabs=[].slice.call(document.querySelectorAll('.tab')),panes=[].slice.call(document.querySelectorAll('.pane'));
  function show(i){tabs.forEach(function(t,k){t.classList.toggle('on',k===i)});panes.forEach(function(p,k){p.classList.toggle('on',k===i)});
    try{localStorage.setItem('odte_tab',i)}catch(e){}}
  tabs.forEach(function(t,i){t.addEventListener('click',function(){show(i)})});
  try{var s=+localStorage.getItem('odte_tab');if(s>=0&&s<tabs.length)show(s)}catch(e){}
  document.querySelectorAll('.trow').forEach(function(r){r.addEventListener('click',function(){
    var d=document.getElementById(r.getAttribute('data-t'));if(d){d.classList.toggle('on');r.classList.toggle('on')}})});
  setTimeout(function(){location.reload()},150000);
})();
"""

WD = "월화수목금토일"


def render(log, st, A):
    now = dt.datetime.now(A.NY)
    tr = log.get(A.V2_KEY) or {}
    today = str(now.date())
    pos = tr.get("open")
    day = (tr.get("days") or {}).get(today)
    done_today = next((t for t in reversed(tr.get("trades", [])) if t.get("date") == today), None)
    if pos and pos.get("res") is None:
        head = f'{pos.get("tk", "QQQ")} {"풋" if pos.get("opt_side") == "put" else "콜"} 보유 중'
    elif done_today:
        head = f'오늘 거래 끝 · {done_today["pnl_pct"]:+.1f}%'
    elif day:
        head = "오늘은 진입 없음"
    elif now.weekday() < 5 and now.time() < dt.time(9, 45):
        head = "09:45 판정 대기"
    elif now.weekday() >= 5:
        head = "주말 · 월요일 09:45 판정"
    else:
        head = "판정 기록 없음"
    tabs = [("갭필", gap_tab(log, A, now)), ("모멘텀", mom_tab(log, A, now)),
            ("3층", l3_tab(log, A, st, now)), ("매크로", macro_tab(log))]
    tb = "".join(f'<button class="tab{" on" if i == 0 else ""}">{n}</button>' for i, (n, _) in enumerate(tabs))
    pn = "".join(f'<section class="pane{" on" if i == 0 else ""}">{h}</section>' for i, (_, h) in enumerate(tabs))
    lp = log.get("last_poll", "")
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>0DTE 갭필</title>
<link rel="manifest" href="manifest.webmanifest">
<meta name="theme-color" content="#171032">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="0DTE">
<link rel="apple-touch-icon" href="icon-192.png">
<link rel="icon" href="icon-192.png" type="image/png">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<style>{CSS}</style></head><body><div class="wrap">
<div class="top"><div class="av">0D</div><div class="pill"><b>모의매매</b> · 실거래 아님</div></div>
<div class="headline"><h1><span>{now.month}월 {now.day}일 {WD[now.weekday()]}요일 · {now.strftime('%H:%M')} ET</span>{E(head)}</h1></div>
<nav class="tabs">{tb}</nav>
{pn}
<div class="foot">마지막 실행 {E(str(lp)[:16].replace('T', ' '))} ET · 손익은 모델가(BSM)<br>모의매매 · 투자 권유 아님</div>
</div><script>{JS}</script></body></html>"""
