"""MM-FEED-LAG-FIX-20261018 단위 테스트 — 1x 꼬리 보정(3배÷3) · 미산출 감시 · 주간 선행 산출 · 실패 경보. 네트워크 0·텔레그램 0(모의)·실제 데이터 0. python3 tests/test_feedlag.py"""
import sys, tempfile, datetime as dt, runpy, io, contextlib, json, signal
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np, pandas as pd
import mm_lib as L, mm_daily as D, mm_tailetn as TE, mm_weekly_scan as W
ok = 0; bad = []
def check(name, cond, detail=""):
    global ok
    if cond: ok += 1; print("PASS", name)
    else: bad.append(name); print("FAIL", name, detail)
L.log = lambda m, name="daily": None
KST = dt.timezone(dt.timedelta(hours=9))
ET = "America/New_York"

def mk(dates, closes, vol=1_000_000.0, with_adj=True):
    h = pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes, "Volume": vol, "Dividends": 0.0, "Stock Splits": 0.0}, index=pd.DatetimeIndex(dates).tz_localize(ET))
    if with_adj: h["Adj Close"] = closes
    h.index.name = "Date"; return h
def setup(td, n_cal=40, lag=0, three_missing_last=0, members=("AAA",), px="ZZ1X", three_vol=None):
    """SPY 달력 n_cal 일, 1x 는 lag 일 늦게 끝남, 3배(members)는 끝에서 three_missing_last 일 빠짐. 3배 수익률 = 일정 +3%, 1x 일정 +1%(기준 시작 100)."""
    raw = Path(td); cal = pd.bdate_range("2026-08-03", periods=n_cal)
    mk(cal, np.full(len(cal), 400.0)).to_csv(raw / "SPY.csv")
    c1 = 100.0 * 1.01 ** np.arange(len(cal)); d1 = cal[:len(cal) - lag]
    mk(d1, c1[:len(d1)]).to_csv(raw / f"{px}.csv")
    for i, m in enumerate(members):
        c3 = 100.0 * 1.03 ** np.arange(len(cal)); d3 = cal[:len(cal) - three_missing_last]
        mk(d3, c3[:len(d3)], vol=(three_vol[i] if three_vol else 1_000_000.0)).to_csv(raw / f"{m}.csv")
    uni = pd.DataFrame({"ticker": list(members), "proxy": [px] * len(members)})
    return raw, cal, c1, uni
def rd(p): return TE._rd(p)

# ── §5 피드 지연 1·2·3일: 보정, 4일: 보정 안 함(⚠ 유지)
for lag in (1, 2, 3):
    with tempfile.TemporaryDirectory() as td:
        raw, cal, c1, uni = setup(td, lag=lag)
        info = TE.fill(cal[-1], uni, raw, log=lambda m: None, info_path=Path(td) / "info.json")
        h = rd(raw / "ZZ1X.csv"); c = TE._close_by_day(h)
        check(f"지연 {lag}일: 상태 filled·{lag}일", info["ZZ1X"]["status"] == "filled" and info["ZZ1X"]["days"] == lag, info)
        check(f"지연 {lag}일: 1x 최신 봉 = 기준일", c.index.max() == cal[-1])
        exp = c1[len(cal) - lag - 1]
        for k in range(lag): exp = exp * (1 + (1.03 / 1.0 - 1) / 3)            # 3배 +3%/일 → 1x +1%/일 (÷3)
        check(f"지연 {lag}일: 보정값 = 직전 1x × (1+r3/3)^N", abs(float(c.iloc[-1]) - exp) < 1e-6, (float(c.iloc[-1]), exp))
        check(f"지연 {lag}일: 보정 행 src=tail_etn · 기존 행 src 빈 문자열", list(h["src"].fillna("")).count("tail_etn") == lag and (h["src"].fillna("").iloc[:-lag] == "").all())
        check(f"지연 {lag}일: 보정 행 Volume 0·Open=High=Low=Close", (h["Volume"].iloc[-lag:] == 0).all() and (h["Open"].iloc[-lag:].values == h["Close"].iloc[-lag:].values).all())
        check(f"지연 {lag}일: info 파일 기록·days_for", TE.days_for(TE.load_info(Path(td) / "info.json"), "ZZ1X", cal[-1]) == lag and TE.days_for(info, "ZZ1X", cal[-lag - 1]) == 0)
with tempfile.TemporaryDirectory() as td:
    raw, cal, c1, uni = setup(td, lag=4)
    before = (raw / "ZZ1X.csv").read_bytes()
    info = TE.fill(cal[-1], uni, raw, log=lambda m: None)
    check("지연 4일: over_max·파일 무변경(⚠ 유지)", info["ZZ1X"]["status"] == "over_max" and (raw / "ZZ1X.csv").read_bytes() == before, info)
    check("지연 4일: unresolved 에 잡힘·days_for 0", "ZZ1X" in TE.unresolved(info) and TE.days_for(info, "ZZ1X", cal[-1]) == 0)
# ── 3배 봉 없음: 마지막 날 3배 봉이 없으면 보정 안 함(all-or-nothing)
with tempfile.TemporaryDirectory() as td:
    raw, cal, c1, uni = setup(td, lag=2, three_missing_last=1)
    before = (raw / "ZZ1X.csv").read_bytes()
    info = TE.fill(cal[-1], uni, raw, log=lambda m: None)
    check("3배 봉 없음(마지막 날): no_3x·1x 파일 무변경", info["ZZ1X"]["status"] == "no_3x" and (raw / "ZZ1X.csv").read_bytes() == before, info)
with tempfile.TemporaryDirectory() as td:
    raw, cal, c1, uni = setup(td, lag=1)
    (raw / "AAA.csv").unlink()
    info = TE.fill(cal[-1], uni, raw, log=lambda m: None)
    check("3배 파일 자체가 없음: no_3x", info["ZZ1X"]["status"] == "no_3x", info)
# ── 정상(지연 0)·이미 최신이면 아무 일도 하지 않는다
with tempfile.TemporaryDirectory() as td:
    raw, cal, c1, uni = setup(td, lag=0)
    before = (raw / "ZZ1X.csv").read_bytes(); info = TE.fill(cal[-1], uni, raw, log=lambda m: None)
    check("지연 0: 보정 없음·파일 무변경", info == {} and (raw / "ZZ1X.csv").read_bytes() == before)
# ── 같은 proxy 3배 여럿: 거래대금 큰 쪽, 필요한 날짜를 모두 가진 쪽
with tempfile.TemporaryDirectory() as td:
    raw, cal, c1, uni = setup(td, lag=1, members=("AAA", "BBB"), three_vol=[1_000.0, 9_000_000.0])
    # BBB 는 수익률 +6%/일(÷3 = 2%)로 바꿔 어느 쪽이 쓰였는지 구분
    mk(cal, 100.0 * 1.06 ** np.arange(len(cal)), vol=9_000_000.0).to_csv(raw / "BBB.csv")
    info = TE.fill(cal[-1], uni, raw, log=lambda m: None)
    check("복수 3배: 거래대금 큰 BBB 선택", info["ZZ1X"]["via"] == "BBB", info)
with tempfile.TemporaryDirectory() as td:
    raw, cal, c1, uni = setup(td, lag=1, members=("AAA", "BBB"), three_vol=[1_000.0, 9_000_000.0])
    mk(cal[:-1], 100.0 * 1.06 ** np.arange(len(cal) - 1), vol=9_000_000.0).to_csv(raw / "BBB.csv")      # BBB 는 마지막 날 봉 없음
    info = TE.fill(cal[-1], uni, raw, log=lambda m: None)
    check("복수 3배: 마지막 날 봉이 없는 BBB 는 건너뛰고 AAA 사용", info["ZZ1X"]["status"] == "filled" and info["ZZ1X"]["via"] == "AAA", info)
# ── exact 1x ETF 봉이 늦을 때도 같은 방식(합성 키가 아닌 일반 ETF 파일)
with tempfile.TemporaryDirectory() as td:
    raw, cal, c1, uni = setup(td, lag=1, px="XLK", members=("TECL",))
    info = TE.fill(cal[-1], uni, raw, log=lambda m: None)
    check("exact 1x ETF 봉 지연: 3배÷3 보정", info["XLK"]["status"] == "filled" and info["XLK"]["via"] == "TECL" and TE._close_by_day(rd(raw / "XLK.csv")).index.max() == cal[-1], info)
# ── 재실행: RAW 가 새로 쓰이면(공식 값이 들어오면) 보정 행이 사라진다
with tempfile.TemporaryDirectory() as td:
    raw, cal, c1, uni = setup(td, lag=1)
    TE.fill(cal[-1], uni, raw, log=lambda m: None)
    setup(td, lag=0)                                                                  # 다음 실행: 1x 가 정식으로 도착해 RAW 가 다시 쓰임
    info = TE.fill(cal[-1], uni, raw, log=lambda m: None)
    h = rd(raw / "ZZ1X.csv")
    check("다음 실행: 정식 값이 들어오면 보정 행 없음", info == {} and "src" not in h.columns or not (h.get("src", pd.Series(dtype=object)).fillna("") == "tail_etn").any())
# ── 배지·사유 표시
check("badges_for: tailn=2 → 지수보정2 (순위 불변·표시)", L.badges_for(500, 5.0, 0, 3.0, 0.99, 252, {"E1": {"threshold": 252}, "E2": {"threshold": 0.3}, "E4": {"beta_min": 2.7, "beta_max": 3.3, "r2_min": 0.85}}, tailn=2) == ["지수보정2"])
check("badges_for: tailn=0 이면 배지 없음", L.badges_for(500, 5.0, 0, 3.0, 0.99, 252, {"E1": {"threshold": 252}, "E2": {"threshold": 0.3}, "E4": {"beta_min": 2.7, "beta_max": 3.3, "r2_min": 0.85}}) == [])
import mm_site
check("Python ! 사유: 지수보정1 → '지수 1일 보정'", mm_site._why_text({"badges": "저유동 · 지수보정1", "listed_days": 100, "adtv": 0.12, "n_beta": 100}) == "$0.12M · 지수 1일 보정")
js = (ROOT / "docs/assets/index.js").read_text(encoding="utf-8")
check("JS why(): 지수보정 N → '지수 N일 보정' 처리 존재", "x.indexOf('지수보정') === 0" in js and "'일 보정'" in js)
TE_info = {"X": dict(status="filled", dates=["2026-10-15", "2026-10-16"], via="T3")}
check("days_for: asof 이전 날짜만 센다", TE.days_for(TE_info, "X", "2026-10-15") == 1 and TE.days_for(TE_info, "X", "2026-10-16") == 2 and TE.days_for(TE_info, "X", "2026-10-14") == 0)
# ── 직전 US 거래일
def ps(y, m, d, hh, mm_): return L.prev_us_session(dt.datetime(y, m, d, hh, mm_, tzinfo=KST))
check("토 08:15 KST → 금요일", ps(2026, 10, 17, 8, 15) == pd.Timestamp("2026-10-16"))
check("화 08:15 KST → 월요일", ps(2026, 10, 20, 8, 15) == pd.Timestamp("2026-10-19"))
check("노동절(월 09-07) 다음 화 08:15 KST → 직전 금요일 09-04", ps(2026, 9, 8, 8, 15) == pd.Timestamp("2026-09-04"))
check("일요일 → 금요일", ps(2026, 10, 18, 9, 38) == pd.Timestamp("2026-10-16"))
check("마감 후 2시간 경계(월 10-19 16:00 EDT +2h = 화 07:00 KST): 06:59 → 직전 금요일, 07:00 → 월요일", ps(2026, 10, 20, 6, 59) == pd.Timestamp("2026-10-16") and ps(2026, 10, 20, 7, 0) == pd.Timestamp("2026-10-19"))
ET_TZ = dt.timezone(dt.timedelta(hours=-5))
check("조기폐장(2026-11-27 13:00 ET): +2h=15:00 ET 이전은 직전, 이후는 당일", L.prev_us_session(dt.datetime(2026, 11, 27, 14, 59, tzinfo=ET_TZ)) == pd.Timestamp("2026-11-25") and L.prev_us_session(dt.datetime(2026, 11, 27, 15, 0, tzinfo=ET_TZ)) == pd.Timestamp("2026-11-27"))
# ── 미산출 감시: 기준일 ≠ 직전 US 거래일 → 경보 1건(사유 포함), 맞으면 0건
sent = []
L.tg_send = lambda text, retries=3, wait=30: (sent.append(text), True)[1]
now_sat = dt.datetime(2026, 10, 17, 8, 15, tzinfo=KST)
df_w = pd.DataFrame({"ticker": ["BULZ", "BNKU"], "table": ["⚠", "⚠"], "reason": ["x", "y"]})
sent.clear(); m = D.check_and_alert(pd.Timestamp("2026-10-15"), {"raw_last": "2026-10-16", "reason": "Close 가 NaN(미확정)"}, {"SPY": "x"}, df_w, {"IDX_SOLFANGT": {"status": "over_max"}}, alert=True, now=now_sat)
check("기준일 10-15 ≠ 직전 거래일 10-16: 경보 1건", len(sent) == 1 and m == sent[0] and "10-15" in m and "10-16" in m, sent)
check("경보 사유: 잠정·미확정 행·⚠ 종목·보정 불가", "미확정" in m and "⚠ 2종" in m and "BULZ" in m and "보정 불가" in m and "over_max" in m, m)
sent.clear(); m = D.check_and_alert(pd.Timestamp("2026-10-16"), None, {}, df_w.iloc[0:0], {}, alert=True, now=now_sat)
check("기준일 = 직전 거래일: 경보 0건", sent == [] and m is None)
sent.clear(); m = D.check_and_alert(pd.Timestamp("2026-10-15"), None, {}, df_w.iloc[0:0], {}, alert=True, now=now_sat)
check("사유가 없어도 수신 지연 추정 문구로 경보", len(sent) == 1 and "수신 지연" in sent[0], sent)
sent.clear(); m = D.check_and_alert(pd.Timestamp("2026-10-15"), None, {}, df_w.iloc[0:0], {}, alert=False, now=now_sat)
check("--no-alert: 텔레그램 0건(로그만)", sent == [] and m is not None)
# L.alert = alerts.log + 텔레그램
logged = []
L.log = lambda m, name="daily": logged.append((name, m))
sent.clear(); L.alert("테스트 경보")
check("L.alert: alerts 로그 1줄 + 텔레그램 1건", ("alerts", "테스트 경보") in logged and sent == ["테스트 경보"])
L.tg_send = lambda text, retries=3, wait=30: False
logged.clear(); r = L.alert("텔레그램 실패 시에도 로그")
check("L.alert: 텔레그램 실패해도 alerts 로그는 남는다·False 반환", ("alerts", "텔레그램 실패 시에도 로그") in logged and r is False)
L.log = lambda m, name="daily": None
L.tg_send = lambda text, retries=3, wait=30: (sent.append(text), True)[1]
# ── 재실행 가드(needs_retry)에 기준일 확인 추가 · 기존 3조건 유지
with tempfile.TemporaryDirectory() as td:
    td = Path(td); L.DATA = td; now = dt.datetime.now(L.KST)
    def guard(date_):
        pd.DataFrame({"date": [date_] * 2, "ticker": ["A", "B"], "table": ["순위", "순위"], "provisional": [0, 0]}).to_csv(td / "scores_latest.csv", index=False)
        return D.needs_retry(now)
    exp = L.prev_us_session(now).date().isoformat()
    n_, why_ = guard(exp); check("가드: 기준일 = 직전 거래일 → 재실행 불필요", not n_, why_)
    n_, why_ = guard("2020-01-02"); check("가드: 기준일 ≠ 직전 거래일 → 재실행", n_ and "직전 US 거래일" in why_, why_)
    ok_, got, exp_, why = D.basis_check(now)
    check("basis_check: 불일치 사유 문구", (not ok_) and "직전 US 거래일" in why and str(got.date()) == "2020-01-02", (ok_, why))
    pd.DataFrame({"date": [exp] * 2, "ticker": ["A", "B"]}).to_csv(td / "scores_latest.csv", index=False)
    check("basis_check: 일치 → True", D.basis_check(now)[0])
    (td / "scores_latest.csv").unlink(); check("basis_check: 파일 없음 → False", not D.basis_check(now)[0])
# ── 주간 잡 선행 산출
calls = []
class FakeD:
    def __init__(self, ok): self.ok = ok
    def basis_check(self, now=None): return self.ok, None, pd.Timestamp("2026-10-16"), ("" if self.ok else "기준일 2026-10-15 ≠ 직전 US 거래일 2026-10-16")
    def run(self, push=True, fetch=True, manual=None): calls.append(("run", push, fetch))
real_daily = sys.modules["mm_daily"]
sys.modules["mm_daily"] = FakeD(False); calls.clear()
r = W.pre_daily_if_stale(push=False)
check("주간 선행 산출: 기준일 불일치 → 일일 산출 1회(fetch=True)", r is True and calls == [("run", False, True)], calls)
sys.modules["mm_daily"] = FakeD(True); calls.clear()
r = W.pre_daily_if_stale(push=False)
check("주간 선행 산출: 기준일 정상(금요일) → 실행 안 함", r is False and calls == [])
class FakeBad(FakeD):
    def run(self, push=True, fetch=True, manual=None): raise RuntimeError("push 실패 모의")
sys.modules["mm_daily"] = FakeBad(False); sent.clear()
r = W.pre_daily_if_stale(push=False)
check("주간 선행 산출 실패: 텔레그램 경보 1건 후 계속(예외 전파 없음)", r is True and len(sent) == 1 and "선행 일일 산출 실패" in sent[0] and "push 실패 모의" in sent[0], sent)
sys.modules["mm_daily"] = real_daily
# ── 세 잡 공통: 실패(예외·타임아웃·push 실패)는 종료 코드와 무관하게 alerts + 텔레그램
def run_main(script, exc, argv):
    sent.clear(); logged2 = []
    L.log = lambda m, name="daily": logged2.append((name, m))
    orig_cf = L.check_formula
    def boom(*a, **k): raise exc
    L.check_formula = boom
    old_argv = sys.argv; sys.argv = [script] + argv; code = None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            try: runpy.run_path(str(ROOT / "scripts" / script), run_name="__main__")
            except SystemExit as e: code = e.code
    finally:
        signal.alarm(0); sys.argv = old_argv; L.check_formula = orig_cf; L.log = lambda m, name="daily": None
    return code, list(sent), logged2
code, s_, lg = run_main("mm_daily.py", RuntimeError("산출 예외 모의"), ["--no-push"])
check("일일 잡 예외: 텔레그램 1건·alerts 로그·종료 코드 1", code == 1 and len(s_) == 1 and "일일 산출 실패" in s_[0] and any(n == "alerts" for n, _ in lg), (code, s_))
code, s_, lg = run_main("mm_daily.py", TimeoutError("상한 5분 초과"), ["--no-push"])
check("일일 잡 타임아웃: 텔레그램 1건", code == 1 and len(s_) == 1 and "TimeoutError" in s_[0], (code, s_))
code, s_, lg = run_main("mm_daily.py", RuntimeError("git push 실패: 모의"), ["--no-push"])
check("일일 잡 push 실패: 텔레그램 1건", code == 1 and len(s_) == 1 and "git push 실패" in s_[0], (code, s_))
code, s_, lg = run_main("mm_daily.py", RuntimeError("가드 예외 모의"), ["--only-if-warn", "--no-push"])
check("10:15 재실행 경로 예외도 경보(가드 내부 포함)", code == 1 and len(s_) == 1, (code, s_))
code, s_, lg = run_main("mm_weekly_scan.py", RuntimeError("주간 예외 모의"), ["--no-push"])
check("주간 잡 예외: 텔레그램 1건·종료 코드 1", code == 1 and len(s_) == 1 and "주간 점검 실패" in s_[0], (code, s_))
code, s_, lg = run_main("mm_daily.py", RuntimeError("x"), ["--no-push", "--no-alert"])
check("--no-alert: 텔레그램 0건(로그만)", code == 1 and s_ == [] and any(n == "alerts" for n, _ in lg))
print(f"{ok} PASS, {len(bad)} FAIL"); sys.exit(1 if bad else 0)
