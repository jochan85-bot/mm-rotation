"""MM-CONFIRM-FIX-20261013 단위 테스트 — 기준일 확정(마감 후 2시간+Close) · 재실행 가드(잠정). 네트워크 0·실제 데이터 0. python3 tests/test_confirm.py"""
import sys, tempfile, datetime as dt
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
import pandas as pd
import mm_lib as L, mm_daily as D
ok = 0; bad = []
def check(name, cond, detail=""):
    global ok
    if cond: ok += 1; print("PASS", name)
    else: bad.append(name); print("FAIL", name, detail)
L.log = lambda m, name="daily": None
def mk(dates, last_close=None, last_vol=None):
    h = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Adj Close": 1.0, "Volume": 1_000_000.0, "Dividends": 0.0, "Stock Splits": 0.0, "Capital Gains": 0.0}, index=pd.to_datetime(dates).tz_localize("America/New_York"))
    h.index.name = "Date"
    if last_close is not None: h.iloc[-1, h.columns.get_loc("Close")] = last_close
    if last_vol is not None: h.iloc[-1, h.columns.get_loc("Volume")] = last_vol
    return h
dates = pd.bdate_range("2026-09-01", "2026-10-12")                                # 마지막 = 10-12(월)
UTC = dt.timezone.utc; KST = dt.timezone(dt.timedelta(hours=9))
def run(now, **kw):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td); L.FETCHED = td / "f"; L.RAW = td / "r"; L.FETCHED.mkdir()
        mk(dates, **kw).to_csv(L.FETCHED / "SPY.csv"); mk(dates).to_csv(L.FETCHED / "URTY.csv")
        return L.clean_all(["SPY", "URTY"], now=now)
# 10-12 16:00 ET(EDT=UTC-4) = 20:00 UTC → +2h = 22:00 UTC = 10-13 07:00 KST
T, prov, dr = run(dt.datetime(2026, 10, 13, 8, 16, tzinfo=KST))
check("10-13 08:16 KST: 10-12 봉 확정·잠정 없음(거래량 무관)", prov is None and T == pd.Timestamp("2026-10-12"), (T, prov))
T, prov, dr = run(dt.datetime(2026, 10, 13, 8, 16, tzinfo=KST), last_vol=18_000)
check("거래량 1.8% 봉도 확정(거래량 규칙 없음)", prov is None and T == pd.Timestamp("2026-10-12"), (T, prov))
T, prov, dr = run(dt.datetime(2026, 10, 13, 6, 59, tzinfo=KST))
check("마감 후 2시간 미만(06:59 KST): 직전 확정일·잠정", prov is not None and T == pd.Timestamp("2026-10-09") and prov["raw_last"] == "2026-10-12", (T, prov))
T, prov, dr = run(dt.datetime(2026, 10, 13, 7, 0, tzinfo=KST))
check("정확히 +2h(07:00 KST): 확정", prov is None and T == pd.Timestamp("2026-10-12"), (T, prov))
T, prov, dr = run(dt.datetime(2026, 10, 12, 23, 0, tzinfo=KST))
check("장중(10-12 23:00 KST) 부분봉: 잠정", prov is not None and T == pd.Timestamp("2026-10-09"), (T, prov))
T, prov, dr = run(dt.datetime(2026, 10, 13, 8, 16, tzinfo=KST), last_close=float("nan"))
check("Close NaN: 시간이 충분해도 잠정", prov is not None and T == pd.Timestamp("2026-10-09"), (T, prov))
# EST(UTC-5) 구간: 11-02(월) 16:00 EST = 21:00 UTC → +2h = 23:00 UTC
check("EST 구간 +2h 경계(23:00 UTC 확정 / 22:59 미확정)", L.bar_settled(pd.Timestamp("2026-11-02"), dt.datetime(2026, 11, 2, 23, 0, tzinfo=UTC)) and not L.bar_settled(pd.Timestamp("2026-11-02"), dt.datetime(2026, 11, 2, 22, 59, tzinfo=UTC)))
# 가드
with tempfile.TemporaryDirectory() as td:
    td = Path(td); L.DATA = td
    now = dt.datetime.now(L.KST)
    def guard(cols):
        pd.DataFrame(cols).to_csv(td / "scores_latest.csv", index=False); return D.needs_retry(now)
    n, why = guard({"ticker": ["A", "B"], "table": ["순위", "순위"], "provisional": [0, 0]})
    check("가드: ⚠0·확정·오늘 산출 → 불필요", not n, why)
    n, why = guard({"ticker": ["A", "B"], "table": ["순위", "순위"], "provisional": [1, 1]})
    check("가드: 잠정 → 재실행", n and "잠정" in why, why)
    n, why = guard({"ticker": ["A", "B"], "table": ["순위", "⚠"], "provisional": [0, 0]})
    check("가드: ⚠ → 재실행(기존 동작 유지)", n and "⚠" in why, why)
    n, why = guard({"ticker": ["A"], "table": ["순위"]})
    check("가드: provisional 열 없는 구 파일도 오류 없이 처리", not n, why)
print(f"{ok} PASS, {len(bad)} FAIL"); sys.exit(1 if bad else 0)
