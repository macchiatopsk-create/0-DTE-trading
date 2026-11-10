# -*- coding: utf-8 -*-
"""앱 원장(odte_log.json)의 거래를 로빈후드 실제 옵션가로 고친다 (형님 요청 2026-11-10: "실제 호가 확인하면 그대로 고쳐줘").

사용: python research/apply_real.py 날짜 트랙 진입가 청산가
  트랙: v2 | mom | l3 | gap:15m|now (gap_tracks 키)
  진입가·청산가 = 앱 진입·청산 시각 직전 5분봉의 실제 옵션 종가 (research/realprice.py와 같은 기준)

- 모델 값은 model_premium / model_exit_premium / model_pnl_pct / model_per_contract로 남긴다 (처음 한 번만).
- 손익% = (청산/진입 - 1) × 100 - 왕복 스프레드 2.2 (모델과 같은 마찰).
- 북은 recon.py와 같은 방식(rebuild_books)으로 그 트랙 전체를 날짜순으로 다시 계산한다.
- 장중에는 쓰지 말 것 (앱이 5분마다 원장을 쓴다). 장 마감 후 실가 원장 작업에서 실행.
"""
import json, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import odte as A   # noqa: E402
import recon      # noqa: E402


def patch(log, date, track, e, x):
    if track == "v2":
        tr = log[A.V2_KEY]; trades = tr["trades"]
    elif track == "mom":
        tr = log["mom_track"]; trades = tr["trades"]
    elif track == "l3":
        tr = None; trades = log["trades"]
    elif track.startswith("gap:"):
        tr = log["gap_tracks"][track[4:]]; trades = tr["trades"]
    else:
        raise SystemExit(f"모르는 트랙: {track}")
    hit = [t for t in trades if t.get("date") == date]
    if not hit:
        raise SystemExit(f"{date} {track} 거래 없음")
    t = hit[0]
    if "model_premium" not in t:
        t["model_premium"] = t.get("premium")
        t["model_exit_premium"] = t.get("exit_premium", t.get("eff_exit"))
        t["model_pnl_pct"] = t.get("pnl_pct")
        t["model_per_contract"] = t.get("per_contract", t.get("pnl_usd"))
    pnl = round(max((x / e - 1) * 100 - A.RT_SPREAD, -100.0), 1)
    t.update(premium=e, exit_premium=x, pnl_pct=pnl, price_src="실가(로빈후드)")
    per = round(e * pnl, 2)                      # 계약당 $ = 진입가×100 × 손익%/100
    if track == "l3":
        t["eff_exit"] = x
        t["pnl_usd"] = per
        itm = [z for z in trades if str(z.get("version", "")).startswith("itm")]
        log["l3_books"] = recon.rebuild_books(itm, A.L3_SIZES, A.CAPITAL_START, per_key=None, skip_fund=False)
    else:
        t["per_contract"] = per
        trades.sort(key=lambda z: z.get("date", ""))
        sizes, cap0 = (A.V2_SIZES, A.V2_CAPITAL) if track == "v2" else (A.GAP_SIZES, A.GAP_CAPITAL)
        tr["books"] = recon.rebuild_books(trades, sizes, cap0)
    print(f"{date} {track}: 모델 {t['model_premium']}→{t['model_exit_premium']} {t['model_pnl_pct']:+.1f}% "
          f"→ 실가 {e}→{x} {pnl:+.1f}%")
    return t


if __name__ == "__main__":
    d, track, e, x = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
    log = A.load_log()
    patch(log, d, track, e, x)
    A.save_log(log)
