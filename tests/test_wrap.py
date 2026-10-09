"""MM-WRAP-BT-20261011 §1 단위 테스트 — 나스닥 1차 수신(극저유동 ETN)·tg_send 재시도. 네트워크·발송 0. python3 tests/test_wrap.py"""
import sys, json, tempfile, urllib.error
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
import pandas as pd
import mm_nasdaq as N, mm_lib as L
ok = 0; bad = []
def check(name, cond, detail=""):
    global ok
    if cond: ok += 1; print("PASS", name)
    else: bad.append(name); print("FAIL", name, detail)

logs = []
L.log = lambda m, name="daily": logs.append((name, m))        # 테스트가 실제 로그 파일을 더럽히지 않게 처음부터 가린다
# ---- 선정: 야후 20일 평균 거래량 < 1000
fr = {"A": pd.DataFrame({"Volume": [0] * 20}), "B": pd.DataFrame({"Volume": [999] * 20}), "C": pd.DataFrame({"Volume": [1000] * 20}), "D": pd.DataFrame({"Volume": [3000] * 5 + [0] * 15})}
check("선정 <1,000주(경계 포함 안 함)", N.select_low_volume(fr, ["A", "B", "C", "D"]) == ["A", "B", "D"], N.select_low_volume(fr, ["A", "B", "C", "D"]))
# ---- 파싱
rows0 = [{"date": "10/08/2026", "close": "25.3906", "volume": "14", "open": "25.3906", "high": "25.3906", "low": "25.3906"},
        {"date": "10/06/2026", "close": "25.1223", "volume": "1,322", "open": "24.94", "high": "25.1223", "low": "24.94"},
        {"date": "bad", "close": "x"}]
rows = rows0[:2]
df = N.parse_rows(rows0)
check("파싱: 날짜순·쉼표 거래량·잘못된 행 버림", list(df.index.strftime("%Y-%m-%d")) == ["2026-10-06", "2026-10-08"] and int(df.Volume.iloc[0]) == 1322 and (df.src == "nasdaq").all(), df)
# ---- 빈 거래일 채움: 사이만, 뒤는 안 채움
cal = pd.to_datetime(["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"])
g = N.fill_gaps(df, cal)
check("사이 빈 거래일(10-07) filled·거래량 0·직전 종가", "2026-10-07" in g.index.strftime("%Y-%m-%d") and g.loc["2026-10-07", "src"] == "filled" and g.loc["2026-10-07", "Volume"] == 0 and g.loc["2026-10-07", "Close"] == 25.1223, g)
check("마지막 기록 뒤(10-09)는 채우지 않음(신선도 ⚠ 유지)", pd.Timestamp("2026-10-09") not in g.index and g.index.max() == pd.Timestamp("2026-10-08"))
# ---- apply_after_fetch (가짜 opener)
def mk(d, vol):
    h = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Adj Close": 1.0, "Volume": vol, "Dividends": 0.0, "Stock Splits": 0.0, "Capital Gains": 0.0}, index=pd.to_datetime(d).tz_localize("America/New_York"))
    h.index.name = "Date"; return h
with tempfile.TemporaryDirectory() as td:
    td = Path(td); dates = pd.bdate_range("2026-09-14", periods=20)
    mk(dates, 0).to_csv(td / "XLCU.csv"); mk(dates, 50000).to_csv(td / "FNGU.csv"); mk(dates, 0).to_csv(td / "SPY.csv")
    payload = json.dumps({"data": {"tradesTable": {"rows": rows}}}).encode()
    res = N.apply_after_fetch(log=lambda *a: None, fetched=td, tickers=["XLCU", "FNGU"], opener=lambda url: payload, calendar=cal)
    x = pd.read_csv(td / "XLCU.csv", index_col=0)
    check("저유동만 교체·src 열", list(res) == ["XLCU"] and set(x.src) <= {"nasdaq", "filled"} and "src" not in pd.read_csv(td / "FNGU.csv", index_col=0).columns, (res, x.tail(3)))
    check("교체본 마지막 봉 = 나스닥 10-08 종가", abs(x.Close.iloc[-1] - 25.3906) < 1e-9 and int(x.Volume.iloc[-1]) == 14)
    # 재호출(직전 실행이 나스닥으로 바꾼 파일) — 야후 값이 아니므로 다시 선정·재수신하지 않는다
    res2 = N.apply_after_fetch(log=lambda *a: None, fetched=td, tickers=["XLCU", "FNGU"], opener=lambda url: (_ for _ in ()).throw(AssertionError("재수신 금지")), calendar=cal)
    check("나스닥 파일은 같은 실행 흐름에서 재수신 안 함", res2 == {})
    # 나스닥 실패 → 야후 유지 + src=yahoo
    mk(dates, 0).to_csv(td / "XLCU.csv")
    def boom(url): raise urllib.error.URLError("net down")
    res3 = N.apply_after_fetch(log=lambda *a: None, fetched=td, tickers=["XLCU"], opener=boom, calendar=cal)
    y = pd.read_csv(td / "XLCU.csv", index_col=0)
    check("나스닥 실패 시 야후 값 유지 + src=yahoo(2차)", set(y.src) == {"yahoo"} and len(y) == 20 and res3["XLCU"].startswith("yahoo"), res3)
# ---- tg_send: 재시도·로그(발송 0)
import types
logs.clear(); calls = {"n": 0}; sleeps = []
orig = (L.log, L.time.sleep, L.subprocess.run, L.urllib.request.urlopen, L.json.load)
L.log = lambda m, name="daily": logs.append((name, m)); L.time.sleep = lambda s: sleeps.append(s)
L.subprocess.run = lambda *a, **k: types.SimpleNamespace(stdout="SECRET-TOKEN\n")
L.json.load = lambda f: {"chat_id": "1"}
class R: status = 200
def flaky(req, timeout=0):
    calls["n"] += 1
    if calls["n"] < 3: raise urllib.error.URLError("temporary failure in name resolution")
    return R()
L.urllib.request.urlopen = flaky
try:
    open(L.LOCAL / "config.json").close(); has_cfg = True
except Exception: has_cfg = False
if has_cfg:
    r = L.tg_send("x")
    check("tg_send: 2회 실패 후 3회째 성공, 30초 간격", r is True and calls["n"] == 3 and sleeps == [30, 30], (r, calls, sleeps))
    check("tg_send: 실패 로그에 예외 전문·토큰 가림", sum("실패" in m for _, m in logs) == 2 and all("URLError" in m and "Traceback" in m and "SECRET-TOKEN" not in m for _, m in logs if "실패" in m) and any("3/3 에서 성공" in m for _, m in logs), logs)
    calls["n"] = -10; logs.clear(); sleeps.clear()
    r = L.tg_send("x")
    check("tg_send: 3회 모두 실패하면 False", r is False and sleeps == [30, 30] and sum("실패" in m for _, m in logs) == 3, (r, sleeps))
else:
    print("SKIP tg_send(.local/config.json 없음)")
L.log, L.time.sleep, L.subprocess.run, L.urllib.request.urlopen, L.json.load = orig
print(f"{ok} PASS, {len(bad)} FAIL"); sys.exit(1 if bad else 0)
