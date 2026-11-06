"""[MM-SPLIT-GUARD-20261106] 주 1회 분할 캘린더 점검 — 유니버스 3배 상품과 1배 대용 ETF 의 향후 30일(과거 10일 포함) 액면분할 예정을 알린다.
원천: 나스닥 분할 캘린더(1차) + yfinance Calendars(보조). 2026-11-06 실측: SOXX·ITA 3:1(11-05)은 나스닥 캘린더에 10-20 이전부터 있었고 yfinance 캘린더(10-01~12-31, 1,515건)에는 없었다.
같은 (종목·날짜·비율)은 한 번만 알린다(.local/split_watch_seen.json). 알림 대상이 없어도 로그 1줄. 점수·순위·페이지 무영향 — 알림 전용.
사용: mm_weekly_scan.py 끝에서 자동 호출 / 단독: python3 mm_splitwatch.py [--no-alert] [--dry-run]"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd
import mm_lib as L, mm_splits as SP

AHEAD = 30
BACK = 10


def collect(today, fetch=None, use_yf=True):
    ev = SP.nasdaq_calendar(pd.Timestamp(today) - pd.Timedelta(days=BACK), fetch=fetch)
    if not use_yf: return ev
    try:                                         # 보조: yfinance 분할 캘린더(ETF 누락이 있음) — 실패는 무시
        import yfinance as yf
        c = yf.Calendars(start=(pd.Timestamp(today) - pd.Timedelta(days=BACK)).date(), end=(pd.Timestamp(today) + pd.Timedelta(days=AHEAD)).date())
        for off in range(0, 1500, 100):
            df = c.get_splits_calendar(limit=100, offset=off)
            if df is None or not len(df): break
            for sym, r in df.iterrows():
                f = float(r["Share Worth"]) / float(r["Old Share Worth"]) if float(r["Old Share Worth"]) else None
                if f: ev.append(dict(symbol=str(sym).upper(), f=f, date=pd.Timestamp(r["Payable On"]).tz_localize(None).normalize(), name=r.get("Company"), ratio=f"{r['Share Worth']}:{r['Old Share Worth']}"))
    except Exception:
        pass
    return ev


def run(alert=True, dry=False, today=None, fetch=None, uni=None, seen_path=None, send=None, use_yf=True):
    today = pd.Timestamp(today or L.now_kst().date()).normalize()
    uni = uni if uni is not None else pd.read_csv(L.DATA / "universe.csv")
    use = {}                                     # 감시 심볼 → 영향 3배 상품
    for r in uni.itertuples():
        use.setdefault(r.ticker, set()).add(r.ticker)
        use.setdefault(r.proxy, set()).add(r.ticker)
    lo, hi = today - pd.Timedelta(days=BACK), today + pd.Timedelta(days=AHEAD)
    hits = {}
    for e in collect(today, fetch=fetch, use_yf=use_yf):
        if e["symbol"] in use and lo <= e["date"] <= hi:
            hits[(e["symbol"], str(e["date"].date()), round(e["f"], 6))] = e
    sp = Path(seen_path or (L.LOCAL / "split_watch_seen.json"))
    seen = set(json.loads(sp.read_text()) if sp.exists() else [])
    new = [(k, e) for k, e in sorted(hits.items(), key=lambda kv: kv[0][1]) if "|".join(map(str, k)) not in seen]
    L.log(f"[mm_splitwatch] 감시 {len(use)}심볼 · 향후 {AHEAD}일(과거 {BACK}일 포함) 분할 {len(hits)}건 · 신규 {len(new)}건" + "".join(f" · {k[0]} {e.get('ratio')} {k[1]}" for k, e in new))
    msg = None
    if new:
        lines = [f"· {k[0]} {e.get('ratio')} 분할 {k[1]} — 영향: {', '.join(sorted(use[k[0]] - {k[0]})) or '자신'}" for k, e in new]
        msg = "[mm_rotation] 분할 예정 알림 (향후 30일). 분할일 전후 야후 이력 조정 시차로 해당 1배 대용의 점수가 하루 안팎 「분할 반영 대기」로 표시될 수 있습니다.\n" + "\n".join(lines)
        if alert and not dry:
            (send or L.tg_send)(msg)
        if not dry:
            sp.write_text(json.dumps(sorted(seen | {"|".join(map(str, k)) for k, _ in new}), ensure_ascii=False))
    return msg


if __name__ == "__main__":
    run(alert="--no-alert" not in sys.argv, dry="--dry-run" in sys.argv)
