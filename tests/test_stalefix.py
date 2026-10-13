"""MM-STALE-FIX-20261011 단위 테스트 — 거래량 50% 규칙 SPY 한정 · 전 종목 나스닥 폴백 · 재실행 가드. 네트워크 0·실제 데이터 0. python3 tests/test_stalefix.py"""
import sys, json, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
import pandas as pd
import mm_nasdaq as N, mm_lib as L
ok = 0; bad = []
def check(name, cond, detail=""):
    global ok
    if cond: ok += 1; print("PASS", name)
    else: bad.append(name); print("FAIL", name, detail)
L.log = lambda m, name="daily": None                           # 실제 로그 파일 보호

def mk(dates, vol, close=1.0, last_close=None, last_vol=None):
    n = len(dates)
    h = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": close, "Adj Close": close, "Volume": float(vol), "Dividends": 0.0, "Stock Splits": 0.0, "Capital Gains": 0.0}, index=pd.to_datetime(dates).tz_localize("America/New_York"))
    h.index.name = "Date"
    if last_close is not None: h.iloc[-1, h.columns.get_loc("Close")] = last_close
    if last_vol is not None: h.iloc[-1, h.columns.get_loc("Volume")] = last_vol
    return h

# ---- (a) clean_all: 거래량 50% 규칙은 SPY 에만
dates = pd.bdate_range("2026-09-01", periods=30)
with tempfile.TemporaryDirectory() as td:
    td = Path(td); L.FETCHED = td / "fetched"; L.RAW = td / "raw"; L.FETCHED.mkdir()
    mk(dates, 1_000_000).to_csv(L.FETCHED / "SPY.csv")                          # 정상 SPY
    mk(dates, 100_000, last_vol=40_000).to_csv(L.FETCHED / "URTY.csv")          # 마지막 봉 거래량 40% — 개별 상품(규칙 미적용)
    mk(dates, 100_000, last_close=float("nan")).to_csv(L.FETCHED / "BAD.csv")    # Close NaN — 모든 종목 제거
    T, prov, dropped = L.clean_all(["SPY", "URTY", "BAD"])
    check("개별 상품: 거래량 40% 봉 유지(미삭제)", "URTY" not in dropped and T == dates[-1], dropped)
    check("개별 상품: Close NaN 봉은 여전히 제거", "BAD" in dropped and "NaN" in dropped["BAD"], dropped)
    check("SPY 정상이면 prov 없음", prov is None)
with tempfile.TemporaryDirectory() as td:
    td = Path(td); L.FETCHED = td / "fetched"; L.RAW = td / "raw"; L.FETCHED.mkdir()
    mk(dates, 1_000_000, last_vol=400_000).to_csv(L.FETCHED / "SPY.csv")        # SPY 마지막 봉 40%
    mk(dates, 100_000).to_csv(L.FETCHED / "URTY.csv")
    T, prov, dropped = L.clean_all(["SPY", "URTY"])
    check("SPY: 거래량 40% 봉도 확정(거래량 규칙 삭제 — MM-CONFIRM-FIX-20261013)", prov is None and T == dates[-1], (T, prov))

# ---- (b) 전 종목 나스닥 폴백
cal = pd.DatetimeIndex(pd.bdate_range("2026-09-14", periods=20))               # 마지막 = 2026-10-09
def payload(rows): return json.dumps({"data": {"tradesTable": {"rows": rows}}}).encode()
R09 = {"date": "10/09/2026", "open": "5", "high": "5.5", "low": "4.9", "close": "5.25", "volume": "1,234"}
R08 = {"date": "10/08/2026", "open": "5", "high": "5", "low": "5", "close": "5.0", "volume": "999"}
with tempfile.TemporaryDirectory() as td:
    td = Path(td); d_all = pd.bdate_range("2026-09-14", periods=20)
    mk(d_all[:-1], 50_000).to_csv(td / "AAA.csv")                               # 봉 없음: 10-09 누락
    mk(d_all, 50_000, last_close=float("nan")).to_csv(td / "BBB.csv")            # Close NaN
    mk(d_all, 50_000).to_csv(td / "CCC.csv")                                    # 정상 — 호출 0이어야 함
    mk(d_all[:-1], 50_000).to_csv(td / "DDD.csv")                               # 나스닥에도 없음
    calls = []
    def opener(url):
        calls.append(url)
        if "/DDD/" in url: return payload([R08])
        return payload([R09, R08])
    res = N.fallback_missing_bars(log=lambda *a: None, fetched=td, tickers=["AAA", "BBB", "CCC", "DDD", "ZZZ"], opener=opener, calendar=cal)
    a = pd.read_csv(td / "AAA.csv", index_col=0); b = pd.read_csv(td / "BBB.csv", index_col=0); c = pd.read_csv(td / "CCC.csv", index_col=0)
    check("봉 없음 → 10-09 만 나스닥 보충(Close·거래량), 기존 행 src=yahoo", len(a) == 20 and a.Close.iloc[-1] == 5.25 and a.Volume.iloc[-1] == 1234 and a.src.iloc[-1] == "nasdaq" and (a.src.iloc[:-1] == "yahoo").all(), a.tail(2))
    check("Close NaN → 그 행을 나스닥 값으로 교체(행 수 불변)", len(b) == 20 and b.Close.iloc[-1] == 5.25 and b.Close.notna().all() and b.src.iloc[-1] == "nasdaq", b.tail(2))
    check("정상 종목은 파일·호출 모두 무변경", "src" not in c.columns and not any("/CCC/" in u for u in calls))
    check("나스닥에도 없으면 파일 무변경·상태 '보충 불가' (⚠ 유지)", len(pd.read_csv(td / "DDD.csv", index_col=0)) == 19 and "보충 불가" in res["DDD"], res)
    check("파일 없는 티커(ZZZ) 건너뜀", "ZZZ" not in res)
    # 보충분 날짜 가드: 기준일 이후 기록은 받지 않는다
    FUT = {"date": "10/12/2026", "open": "9", "high": "9", "low": "9", "close": "9", "volume": "1"}
    mk(d_all[:-1], 50_000).to_csv(td / "EEE.csv")
    N.fallback_missing_bars(log=lambda *a: None, fetched=td, tickers=["EEE"], opener=lambda u: payload([FUT, R09]), calendar=cal)
    e = pd.read_csv(td / "EEE.csv", index_col=0)
    check("기준일 이후 기록(10-12)은 제외", len(e) == 20 and str(e.index[-1])[:10] == "2026-10-09", e.tail(2))
    # 나스닥 오류 → 예외 없이 상태만, 파일 무변경
    mk(d_all[:-1], 50_000).to_csv(td / "FFF.csv")
    def boom(url): raise OSError("차단")
    import time as _t; _sl = _t.sleep; N.time.sleep = lambda s: None
    r = N.fallback_missing_bars(log=lambda *a: None, fetched=td, tickers=["FFF"], opener=boom, calendar=cal)
    N.time.sleep = _sl
    check("나스닥 오류 → 보충 실패 상태·파일 무변경(예외 없음)", "보충 실패" in r["FFF"] and len(pd.read_csv(td / "FFF.csv", index_col=0)) == 19, r)
print(f"{ok} PASS, {len(bad)} FAIL"); sys.exit(1 if bad else 0)
