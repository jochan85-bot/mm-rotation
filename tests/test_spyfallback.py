"""MM-FEED-LAG-FIX 후속 §1 — 기준일 판정용 SPY 나스닥 폴백. 네트워크 0. python3 tests/test_spyfallback.py"""
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
L.log = lambda m, name="daily": None
N.time.sleep = lambda s: None
def mk(dates, last_close=None):
    n = len(dates)
    h = pd.DataFrame({"Open": 400.0, "High": 400.0, "Low": 400.0, "Close": 400.0, "Adj Close": 400.0, "Volume": 1e6, "Dividends": 0.0, "Stock Splits": 0.0, "Capital Gains": 0.0}, index=pd.to_datetime([d.strftime("%Y-%m-%d 00:00:00-04:00") for d in dates], utc=False) if False else [d.strftime("%Y-%m-%d 00:00:00-04:00") for d in dates])
    h.index.name = "Date"
    if last_close is not None: h.iloc[-1, h.columns.get_loc("Close")] = last_close
    return h
def payload(rows): return json.dumps({"data": {"tradesTable": {"rows": rows}}}).encode()
R16 = {"date": "10/16/2026", "open": "700", "high": "705", "low": "699", "close": "702.5", "volume": "5,000,000"}
R15 = {"date": "10/15/2026", "open": "400", "high": "400", "low": "400", "close": "400", "volume": "1"}
d_all = pd.bdate_range("2026-09-17", "2026-10-16")
EXP = pd.Timestamp("2026-10-16")
# 1) 야후 NaN → 나스닥으로 교체, clean_all 이 10-16 을 확정 기준일로
with tempfile.TemporaryDirectory() as td:
    td = Path(td); L.FETCHED = td / "fetched"; L.RAW = td / "raw"; L.FETCHED.mkdir()
    mk(d_all, last_close=float("nan")).to_csv(L.FETCHED / "SPY.csv")
    res = N.fallback_spy(log=lambda *a: None, fetched=L.FETCHED, opener=lambda u: payload([R16, R15]), expected=EXP)
    s = pd.read_csv(L.FETCHED / "SPY.csv", index_col=0)
    check("야후 Close NaN → 나스닥 값으로 교체(행 수 불변, src=nasdaq)", len(s) == len(d_all) and s.Close.iloc[-1] == 702.5 and s.src.iloc[-1] == "nasdaq" and "보충" in res["SPY"], (res, s.tail(2)))
    T, prov, dropped = L.clean_all(["SPY"], now=pd.Timestamp("2026-10-17 12:00", tz="UTC"))
    check("교체 후 기준일 = 직전 거래일·잠정 없음", T == EXP and prov is None, (T, prov))
# 2) 봉 자체 없음 → 나스닥 보충
with tempfile.TemporaryDirectory() as td:
    td = Path(td); L.FETCHED = td / "fetched"; L.RAW = td / "raw"; L.FETCHED.mkdir()
    mk(d_all[:-1]).to_csv(L.FETCHED / "SPY.csv")
    N.fallback_spy(log=lambda *a: None, fetched=L.FETCHED, opener=lambda u: payload([R16, R15]), expected=EXP)
    s = pd.read_csv(L.FETCHED / "SPY.csv", index_col=0)
    check("SPY 봉 없음 → 10-16 한 봉 보충", len(s) == len(d_all) and str(s.index[-1])[:10] == "2026-10-16", s.tail(2))
# 3) 둘 다 없음(나스닥 기록도 없음) → 파일 무변경, clean_all 은 직전 확정일로 후퇴·잠정
with tempfile.TemporaryDirectory() as td:
    td = Path(td); L.FETCHED = td / "fetched"; L.RAW = td / "raw"; L.FETCHED.mkdir()
    mk(d_all, last_close=float("nan")).to_csv(L.FETCHED / "SPY.csv")
    res = N.fallback_spy(log=lambda *a: None, fetched=L.FETCHED, opener=lambda u: payload([R15]), expected=EXP)
    s = pd.read_csv(L.FETCHED / "SPY.csv", index_col=0)
    check("나스닥에도 없으면 파일 무변경·'보충 불가'", s.Close.isna().iloc[-1] and "보충 불가" in res["SPY"], res)
    T, prov, dropped = L.clean_all(["SPY"], now=pd.Timestamp("2026-10-17 12:00", tz="UTC"))
    check("직전 확정일로 후퇴·잠정 표시(마지막 확정 10-15)", T == pd.Timestamp("2026-10-15") and prov is not None, (T, prov))
# 4) 나스닥 오류 → 예외 없이 상태, 파일 무변경
with tempfile.TemporaryDirectory() as td:
    td = Path(td); L.FETCHED = td / "fetched"; L.RAW = td / "raw"; L.FETCHED.mkdir()
    mk(d_all, last_close=float("nan")).to_csv(L.FETCHED / "SPY.csv")
    def boom(u): raise OSError("차단")
    res = N.fallback_spy(log=lambda *a: None, fetched=L.FETCHED, opener=boom, expected=EXP)
    check("나스닥 오류 → '보충 실패'·파일 무변경", "보충 실패" in res["SPY"] and pd.read_csv(L.FETCHED / "SPY.csv", index_col=0).Close.isna().iloc[-1], res)
# 5) 정상 SPY → 호출 0
with tempfile.TemporaryDirectory() as td:
    td = Path(td); L.FETCHED = td / "fetched"; L.FETCHED.mkdir(); mk(d_all).to_csv(L.FETCHED / "SPY.csv"); calls = []
    res = N.fallback_spy(log=lambda *a: None, fetched=L.FETCHED, opener=lambda u: calls.append(u), expected=EXP)
    check("정상이면 나스닥 호출 0·결과 {}", not calls and res == {}, (calls, res))
# 6) apply_after_fetch 배선: SPY 폴백이 3배 폴백보다 먼저(3배 기준일이 보충된 SPY 날짜)
with tempfile.TemporaryDirectory() as td:
    td = Path(td); L.FETCHED = td / "fetched"; L.FETCHED.mkdir()
    mk(d_all, last_close=float("nan")).to_csv(td / "SPY.csv"); mk(d_all[:-1]).to_csv(td / "AAA.csv")
    res = N.apply_after_fetch(log=lambda *a: None, write=True, opener=lambda u: payload([R16, R15]), fetched=td, tickers=[], three_x=["AAA"], expected=EXP)
    a = pd.read_csv(td / "AAA.csv", index_col=0); s = pd.read_csv(td / "SPY.csv", index_col=0)
    check("apply_after_fetch: SPY 보충 후 3배(AAA)도 10-16 까지 보충", str(s.index[-1])[:10] == "2026-10-16" and s.Close.iloc[-1] == 702.5 and str(a.index[-1])[:10] == "2026-10-16" and "SPY(SPY 폴백)" in res, (res, a.tail(1)))
print(f"{ok} PASS, {len(bad)} FAIL"); sys.exit(1 if bad else 0)
