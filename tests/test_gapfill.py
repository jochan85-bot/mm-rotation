"""MM-GAPFILL-20261024 단위 테스트 — 야후 중간 결손 봉(최근 260 NYSE 거래일)을 나스닥 일별 기록으로 보충(src=nasdaq_gap). 네트워크 0·텔레그램 0. python3 tests/test_gapfill.py"""
import sys, json, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np, pandas as pd
import mm_nasdaq as N, mm_lib as L
ok = 0; bad = []
def check(name, cond, detail=""):
    global ok
    if cond: ok += 1; print("PASS", name)
    else: bad.append(name); print("FAIL", name, detail)
L.log = lambda m, name="daily": None
SES = pd.DatetimeIndex(pd.bdate_range("2026-06-01", "2026-10-08"))          # 합성 거래일(휴장 없음 가정) — sessions 를 직접 주입
def frame(drop=(), nan=(), last=None, first=None):
    ix = [d for d in SES if (first is None or d >= pd.Timestamp(first)) and (last is None or d <= pd.Timestamp(last))]
    c = np.linspace(100, 120, len(ix))
    df = pd.DataFrame({"Open": c, "High": c + 1, "Low": c - 1, "Close": c, "Adj Close": c, "Volume": 1000.0, "Dividends": 0.0, "Stock Splits": 0.0}, index=pd.DatetimeIndex(ix))
    for d in nan: df.loc[pd.Timestamp(d), ["Close", "Adj Close"]] = np.nan
    df = df.drop([pd.Timestamp(d) for d in drop])
    df.index = df.index.tz_localize("America/New_York"); df.index.name = "Date"; return df
def nd_rows(dates, base=555.0):
    return [dict(date=pd.Timestamp(d).strftime("%m/%d/%Y"), open=f"${base}", high=f"${base+1}", low=f"${base-1}", close=f"${base+0.5}", volume="12,345") for d in dates]
class Opener:
    def __init__(s, dates, base=555.0, fail=False): s.rows = nd_rows(dates, base); s.calls = []; s.fail = fail
    def __call__(s, url):
        s.calls.append(url)
        if s.fail: raise RuntimeError("boom")
        return json.dumps({"data": {"tradesTable": {"rows": s.rows}}}).encode()
def setup(td, **frames):
    td = Path(td)
    for t, df in frames.items(): df.to_csv(td / f"{t}.csv")
    return td
def run(td, tickers, opener, sessions=SES):
    return N.fallback_mid_gaps(log=lambda m: None, opener=opener, fetched=td, tickers=tickers, sessions=sessions)
def rd(td, t): return pd.read_csv(Path(td) / f"{t}.csv", index_col=0)
dstr = lambda h: [str(i)[:10] for i in h.index]

# ── 1일 결손 보충
with tempfile.TemporaryDirectory() as td:
    setup(td, AAA=frame(drop=["2026-09-10"]))
    op = Opener(["2026-09-10"]); r = run(td, ["AAA"], op); h = rd(td, "AAA")
    check("중간 결손 1일: 나스닥으로 채움·결과 filled 1·unfilled 0", r["AAA"]["filled"] == [pd.Timestamp("2026-09-10")] and r["AAA"]["unfilled"] == [], r)
    row = h.loc[[i for i in h.index if str(i).startswith("2026-09-10")]]
    check("채운 행: src=nasdaq_gap·나스닥 값(종가 555.5·거래량 12345)", len(row) == 1 and row.iloc[0]["src"] == "nasdaq_gap" and abs(row.iloc[0]["Close"] - 555.5) < 1e-9 and row.iloc[0]["Volume"] == 12345, row.to_dict("records"))
    check("날짜 정렬·중복 없음·야후 행은 그대로", dstr(h) == sorted(dstr(h)) and len(set(dstr(h))) == len(h) == len(SES) and str(h.index[0]).endswith("-04:00"))
    check("다른 날짜 값 불변(야후 값 유지)", abs(h.iloc[0]["Close"] - 100.0) < 1e-9 and h.drop(row.index)["src"].fillna("").isin(["", "nan"]).all())
    n1 = len(op.calls); r2 = run(td, ["AAA"], op)
    check("멱등: 재실행 시 결손 없음·나스닥 호출 0", r2 == {} and len(op.calls) == n1)
# ── 2일 연속 결손
with tempfile.TemporaryDirectory() as td:
    setup(td, AAA=frame(drop=["2026-09-10", "2026-09-11"]))
    r = run(td, ["AAA"], Opener(["2026-09-10", "2026-09-11"])); h = rd(td, "AAA")
    check("중간 결손 2일: 둘 다 채움", [str(x.date()) for x in r["AAA"]["filled"]] == ["2026-09-10", "2026-09-11"] and r["AAA"]["unfilled"] == [] and len(h) == len(SES))
# ── Close NaN 행 교체
with tempfile.TemporaryDirectory() as td:
    setup(td, AAA=frame(nan=["2026-08-14"]))
    r = run(td, ["AAA"], Opener(["2026-08-14"])); h = rd(td, "AAA")
    row = h.loc[[i for i in h.index if str(i).startswith("2026-08-14")]]
    check("Close NaN 인 중간 행: 나스닥 값으로 교체(행 1개)", len(row) == 1 and abs(row.iloc[0]["Close"] - 555.5) < 1e-9 and row.iloc[0]["src"] == "nasdaq_gap" and len(h) == len(SES))
# ── 일부만 나스닥에 있음: 있는 것만 채우고 없는 날짜는 unfilled
with tempfile.TemporaryDirectory() as td:
    setup(td, AAA=frame(drop=["2026-09-10", "2026-09-11"]))
    r = run(td, ["AAA"], Opener(["2026-09-10"])); h = rd(td, "AAA")
    check("나스닥에 한 날짜만 있음: 1봉 채움·1봉 unfilled(비워 둠)", [str(x.date()) for x in r["AAA"]["filled"]] == ["2026-09-10"] and [str(x.date()) for x in r["AAA"]["unfilled"]] == ["2026-09-11"] and len(h) == len(SES) - 1)
# ── 나스닥 부재 → 비워 두고 경보 1줄(종목·날짜)
with tempfile.TemporaryDirectory() as td:
    setup(td, AAA=frame(drop=["2026-09-10"]), BBB=frame(drop=["2026-07-03", "2026-07-06"]))
    before = (Path(td) / "AAA.csv").read_bytes()
    res = run(td, ["AAA", "BBB"], Opener([]))
    check("나스닥에도 없음: 파일 무변경·unfilled 로 보고", (Path(td) / "AAA.csv").read_bytes() == before and res["AAA"]["unfilled"] == [pd.Timestamp("2026-09-10")] and len(res["BBB"]["unfilled"]) == 2, res)
    sent = []
    import mm_lib; orig = mm_lib.alert; mm_lib.alert = lambda m, **k: sent.append(m) or True
    st = Path(td) / "state.json"; argv = sys.argv; sys.argv = ["x"]
    new = N.alert_unfilled(res, state_path=st); new2 = N.alert_unfilled(res, state_path=st); mm_lib.alert = orig; sys.argv = argv
    check("경보 1줄: 종목·날짜 포함, 한 번에 1건", len(sent) == 1 and "AAA(09-10)" in sent[0] and "BBB(07-03 07-06)" in sent[0] and "나스닥에도 없음" in sent[0], sent)
    check("같은 (종목, 날짜)는 다시 알리지 않음(상태 파일)", new2 == [] and len(sent) == 1 and len(new) == 3)
    sent2 = []; mm_lib.alert = lambda m, **k: sent2.append(m) or True; sys.argv = ["x", "--no-alert"]
    N.alert_unfilled(res, state_path=Path(td) / "state2.json"); mm_lib.alert = orig; sys.argv = argv
    check("--no-alert: 텔레그램(alert) 호출 0", sent2 == [])
# ── 나스닥 호출 실패 → 예외 없이 unfilled
with tempfile.TemporaryDirectory() as td:
    setup(td, AAA=frame(drop=["2026-09-10"]))
    import time; osl = time.sleep; time.sleep = lambda s: None
    res = run(td, ["AAA"], Opener([], fail=True)); time.sleep = osl
    check("나스닥 호출 실패: 예외 없음·unfilled", res["AAA"]["unfilled"] == [pd.Timestamp("2026-09-10")])
# ── 범위: 창 밖·첫 봉 이전·마지막 봉 뒤(꼬리)는 대상 아님
with tempfile.TemporaryDirectory() as td:
    ses_short = SES[-30:]                                                       # 창 = 최근 30 거래일
    setup(td, OLD=frame(drop=["2026-06-10"]), NEW=frame(first="2026-09-01"), TAIL=frame(last="2026-10-05"))
    op = Opener(["2026-06-10"])
    res = N.fallback_mid_gaps(log=lambda m: None, opener=op, fetched=Path(td), tickers=["OLD", "NEW", "TAIL"], sessions=ses_short)
    check("창 밖 결손(OLD 06-10)·상장 전(NEW)·꼬리(TAIL 마지막 봉 뒤)는 건드리지 않음 — 나스닥 호출 0", res == {} and op.calls == [])
    check("find_mid_gaps: 꼬리·첫 봉 이전 제외, 중간만", N.find_mid_gaps(frame(last="2026-10-05"), SES) == [] and N.find_mid_gaps(frame(first="2026-09-01"), SES) == [] and len(N.find_mid_gaps(frame(drop=["2026-09-10"]), SES)) == 1)
# ── 파일 없음·결손 없음
with tempfile.TemporaryDirectory() as td:
    setup(td, AAA=frame())
    op = Opener([]); res = run(td, ["AAA", "ZZZ"], op)
    check("결손 없음·파일 없는 티커: 나스닥 호출 0·결과 {}", res == {} and op.calls == [])
# ── 배선: apply_after_fetch 가 합성 환경에서는 건너뛰고(gap_fill=None→FETCHED 일 때만) 실환경에서 호출
src = (ROOT / "scripts" / "mm_nasdaq.py").read_text(encoding="utf-8")
check("apply_after_fetch 배선: gap_fill 기본은 실제 FETCHED 일 때만", "gap_fill = (fetched == FETCHED)" in src and "fallback_mid_gaps(log, write=write, opener=opener, fetched=fetched)" in src)
tk = N.gap_tickers()
check("점검 대상: 3배 상품·1x ETF(QQQ·DIA·IWM·IJH·SMH)·SPY 포함, 합성 키(IDX_·TPOR_1X) 제외", {"TQQQ", "SOXL", "QQQ", "DIA", "IWM", "IJH", "SMH", "SPY", "IYT"} <= set(tk) and not any(x.startswith("IDX_") or x.endswith("_1X") for x in tk), tk)
check("GAP_WINDOW=260·src 라벨 nasdaq_gap", N.GAP_WINDOW == 260 and N.GAP_SRC == "nasdaq_gap")
ses = N.nyse_sessions("2026-10-22")
check("nyse_sessions: 260개·마지막=기준일·휴장일(2026-09-07 노동절) 제외", len(ses) == 260 and ses[-1] == pd.Timestamp("2026-10-22") and pd.Timestamp("2026-09-07") not in ses)
print(f"{ok} PASS, {len(bad)} FAIL"); sys.exit(1 if bad else 0)
