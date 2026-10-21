"""MM-THIN-ETN-HIST-20261021 — 극저유동 ETN 3배 이력 복구(§1)·피드 중단 감시(§2)·거래량 극소 부적격(§5). 네트워크 0. python3 tests/test_thinhist.py"""
import sys, json, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
import pandas as pd, numpy as np
import mm_nasdaq as N, mm_lib as L, mm_feedwatch as FW, mm_site
ok = 0; bad = []
def check(name, cond, detail=""):
    global ok
    if cond: ok += 1; print("PASS", name)
    else: bad.append(name); print("FAIL", name, detail)
L.log = lambda m, name="daily": None
N.time.sleep = lambda s: None
COLS = N.COLS
def fr(dates, close=25.0, vol=100.0, src=None):
    h = pd.DataFrame({c: 0.0 for c in COLS}, index=pd.to_datetime([str(d)[:10] for d in dates]).tz_localize("America/New_York")); h.index.name = "Date"
    for c in ("Open", "High", "Low", "Close", "Adj Close"): h[c] = close
    h["Volume"] = vol
    if src: h["src"] = src
    return h
def payload(rows): return json.dumps({"data": {"tradesTable": {"rows": rows}}}).encode()
def nrows(dates, close=25.0, vol=100):
    return [{"date": pd.Timestamp(d).strftime("%m/%d/%Y"), "open": str(close), "high": str(close), "low": str(close), "close": str(close), "volume": f"{vol:,}"} for d in dates]
CAL = pd.bdate_range("2026-09-10", "2026-10-20")            # 달력(SPY 대용) — 정확한 NYSE 휴장 반영은 불필요
FB = {"XLCU": pd.Timestamp("2026-09-11"), "XLPU": pd.Timestamp("2026-09-11")}
TGT = CAL.max()
# 1) 이력 길이 점검: 야후 3봉 vs 기대 거래일 수 → 선정 / 11봉(부족 < 20) 비선정 / 상장일 없음 비선정 / 충분 비선정
exp = int(((CAL >= FB["XLPU"]) & (CAL <= TGT)).sum())
fr_ok = {"XLPU": fr(CAL[-3:]), "XLCU": fr(CAL[-5:]), "NOFB": fr(CAL[-3:]), "FULL": fr(CAL[CAL >= FB["XLPU"]])}
sel = N.select_short_history(fr_ok, ["XLPU", "XLCU", "NOFB", "FULL"], CAL, TGT, FB)
check("야후 3봉(기대 %d) → 짧음 선정" % exp, "XLPU" in sel, sel)
check("야후 5봉(기대 %d, 부족 %d ≥ 20) → 선정" % (exp, exp - 5), "XLCU" in sel, sel)
check("상장일 미상 티커 비선정", "NOFB" not in sel, sel)
check("야후 이력 충분 → 비선정", "FULL" not in sel, sel)
fr_ok2 = {"XLCU": fr(CAL[-(exp - 19):])}                    # 부족 19봉 → 경계 미만 비선정
check("부족 19봉(경계 미만) 비선정", N.select_short_history(fr_ok2, ["XLCU"], CAL, TGT, FB) == [], N.select_short_history(fr_ok2, ["XLCU"], CAL, TGT, FB))
fr_ok3 = {"XLCU": fr(CAL[-(exp - 20):])}                    # 부족 정확히 20봉 → 선정
check("부족 20봉(경계) 선정", N.select_short_history(fr_ok3, ["XLCU"], CAL, TGT, FB) == ["XLCU"])
# 1b) product_info 상장일 정정(나스닥 실측 첫 거래일 2026-09-10)
fbm = N.first_bars()
check("product_info first_bar: XLCU·XLPU = 2026-09-10 (나스닥 실측)", fbm.get("XLCU") == pd.Timestamp("2026-09-10") and fbm.get("XLPU") == pd.Timestamp("2026-09-10") and L.first_bar("XLCU") == pd.Timestamp("2026-09-10"), (fbm.get("XLCU"), fbm.get("XLPU")))
# 2) 조회 시작일 = min(야후 첫 봉, 상장일) − 10일
yh = fr(CAL[-3:])
check("시작일: 야후 첫 봉(10-16경)보다 상장일(09-11) − 10일이 이르다", N.history_start(yh, FB["XLPU"]) == "2026-09-01", N.history_start(yh, FB["XLPU"]))
check("시작일: 상장일 없으면 야후 첫 봉 − 10일", N.history_start(yh, None) == (pd.Timestamp(CAL[-3]) - pd.Timedelta(days=10)).date().isoformat())
# 3) build_history: replace(극저유동) — 나스닥 전 구간 + 사이 빈 거래일 filled + 마지막 기록 뒤 야후 실거래 봉만
nd_dates = [d for d in CAL if d not in (pd.Timestamp("2026-09-16"), CAL[-1], CAL[-2])]      # 09-16 은 기록 없음(filled), 마지막 2일 나스닥 지연
urls = []
def opener(u): urls.append(u); return payload(nrows(nd_dates, 25.0, 50))
yh = fr([CAL[-2], CAL[-1]], close=26.0, vol=3000.0)                       # 야후: 나스닥 마지막 기록 뒤 2일 실거래(거래량>0)
yh.loc[yh.index[0], "Volume"] = 0.0                                       # 첫 행은 거래량 0(직전가 연장 의심) → 잇지 않는다
out, mode, summ = N.build_history("XLPU", yh, FB["XLPU"], CAL, opener=opener)
o = out.copy(); o.index = N._et_dates(o.index)
check("replace 모드(20일 평균 거래량 < 1,000)", mode == "replace", summ)
check("요청 URL fromdate = 2026-09-01(상장일 − 10일)", "fromdate=2026-09-01" in urls[0], urls[0])
check("나스닥 첫 기록(상장 직후)부터 포함", o.index.min() == CAL[0] and o.src.iloc[0] == "nasdaq")
check("사이 빈 거래일(09-16)은 filled·거래량 0·직전 종가", o.loc["2026-09-16", "src"] == "filled" and o.loc["2026-09-16", "Volume"] == 0 and o.loc["2026-09-16", "Close"] == 25.0)
check("마지막 나스닥 기록 뒤 야후: 거래량>0 인 봉만(src=yahoo) — 거래량 0 은 제외", list(o.index[-1:]) == [CAL[-1]] and o.src.iloc[-1] == "yahoo" and (CAL[-2] not in o.index), o.tail(3))
# 4) merge 모드: 20일 평균 거래량 ≥ 1,000 → 야후 행 그대로, 야후 첫 봉 이전만 나스닥
yh2 = fr(CAL[-3:], close=30.0, vol=5000.0, src=None)
out2, mode2, _ = N.build_history("XLPU", yh2, FB["XLPU"], CAL, opener=lambda u: payload(nrows(CAL[:-3], 25.0, 5000)))
o2 = out2.copy(); o2.index = N._et_dates(o2.index)
check("merge 모드(평균 거래량 ≥ 1,000)", mode2 == "merge", mode2)
check("merge: 야후 3봉은 값 그대로(종가 30)·src=yahoo", (o2.loc[CAL[-3:], "Close"] == 30.0).all() and (o2.loc[CAL[-3:], "src"] == "yahoo").all())
check("merge: 야후 첫 봉 이전은 나스닥(종가 25)", (o2.loc[CAL[:-3], "Close"] == 25.0).all() and len(o2) == len(CAL))
# 5) 나스닥 실패 → 예외(호출측이 야후 유지) · 응답 형식 오류 다수 → 예외
try: N.build_history("XLPU", yh, FB["XLPU"], CAL, opener=lambda u: (_ for _ in ()).throw(ValueError("boom"))); check("나스닥 실패 → 예외 전파", False)
except Exception: check("나스닥 실패 → 예외 전파", True)
# 6) apply_after_fetch 통합(합성 fetched): XLPU(야후 3봉) 선정 → 상장일부터 전 구간으로 교체, 재실행 멱등(src=nasdaq 파일은 건너뜀)
with tempfile.TemporaryDirectory() as td:
    td = Path(td); F = td / "f"; F.mkdir()
    fr(CAL, close=400.0, vol=1e6).to_csv(F / "SPY.csv")
    fr(CAL[-3:], close=29.0, vol=2000.0).to_csv(F / "XLPU.csv")
    fr(CAL[-3:], close=29.0, vol=2000.0).to_csv(F / "OTHER.csv")
    res = N.apply_after_fetch(log=lambda *a: None, fetched=F, opener=lambda u: payload(nrows(CAL[:-1], 25.0, 40)), tickers=["XLPU"], calendar=CAL, three_x=["XLPU", "OTHER"], first_bar_map=FB)
    a = pd.read_csv(F / "XLPU.csv", index_col=0)
    check("apply: XLPU 교체(나스닥 이력, 야후 3봉 → 전 구간)", len(a) >= len(CAL) - 1 and "nasdaq" in set(a.src), (len(a), set(a.src)))
    check("apply: 상장일 없는 OTHER 는 선정 안 됨(파일 무변경)", "src" not in pd.read_csv(F / "OTHER.csv", index_col=0).columns)
    before = (F / "XLPU.csv").read_text()
    res2 = N.apply_after_fetch(log=lambda *a: None, fetched=F, opener=lambda u: (_ for _ in ()).throw(AssertionError("재호출 금지")), tickers=["XLPU"], calendar=CAL, three_x=["XLPU", "OTHER"], first_bar_map=FB)
    check("apply: 재실행 멱등(나스닥 교체본은 건너뜀·네트워크 0)", (F / "XLPU.csv").read_text() == before)
# 7) 거래량 극소 배지(§5): 경계 1,000 미만만, 맨 앞, 다른 배지와 병기, 점수 무관
cfg = L.load_yaml_simple(L.DATA / "eligibility.yaml")
check("eligibility.yaml E6 값 1000", cfg["E6"]["threshold"] == 1000, cfg.get("E6"))
check("vol20 186.6 → 배지 맨 앞 + 저유동 병기", L.badges_for(29, 0.0045, 1, 2.58, 0.55, 18, cfg, vol20=186.6)[:2] == ["거래량극소", "표본부족"] and "저유동" in L.badges_for(29, 0.0045, 1, 2.58, 0.55, 18, cfg, vol20=186.6))
check("vol20 999.9 → 배지", "거래량극소" in L.badges_for(300, 5.0, 0, 3.0, 0.97, 400, cfg, vol20=999.9))
check("vol20 1000 → 배지 없음(< 만)", "거래량극소" not in L.badges_for(300, 5.0, 0, 3.0, 0.97, 400, cfg, vol20=1000.0))
check("vol20 NaN·None → 배지 없음(기존 동작)", "거래량극소" not in L.badges_for(300, 5.0, 0, 3.0, 0.97, 400, cfg, vol20=float("nan")) and "거래량극소" not in L.badges_for(300, 5.0, 0, 3.0, 0.97, 400, cfg))
check("기존 호출(vol20 없음) 배지 불변", L.badges_for(12, 0.004, 1, 2.5, 0.55, 18, cfg) == ["표본부족", "신규", "저유동", "무거래1"])
# 8) ! 사유 문구(Python) — 맨 앞, 기존 사유 병기
r = {"badges": "거래량극소 · 표본부족 · 신규 · 저유동 · 무거래1", "listed_days": 29, "adtv": 0.0045, "n_beta": 18}
check("_why_text: '거래량 극소 부적격' 이 맨 앞 + 기존 사유 병기", mm_site._why_text(r) == "거래량 극소 부적격 · 표본 18 · 신규 29일 · $0.00M · 무거래 1일", mm_site._why_text(r))
check("_why_text: 배지 없는 행은 기존 문구 그대로", mm_site._why_text({"badges": "신규", "listed_days": 46, "adtv": 1.0, "n_beta": 90}) == "신규 46일")
js = (ROOT / "docs" / "assets" / "index.js").read_text(encoding="utf-8")
check("index.js why(): 거래량극소 → '거래량 극소 부적격' 을 배지 루프보다 앞에 push", js.index("거래량 극소 부적격") < js.index("b.forEach(function (x) {"), "")
# 9) 가이드 5절 아이콘 표 1행
import mm_guide
g = (ROOT / "docs" / "guide.html").read_text(encoding="utf-8")
check("가이드 5절 표에 '거래량 극소 부적격' 행(기준·뜻)", "거래량 극소 부적격</td><td>최근 20일 평균 거래량(3배 상품) 1,000주 미만" in g and "무한매수 주문 체결이 어려움" in g)
# 10) 피드 중단 감시(§2)
with tempfile.TemporaryDirectory() as td:
    raw = Path(td); cal = pd.bdate_range("2026-08-03", "2026-10-02")
    fr(cal, 400.0).to_csv(raw / "SPY.csv")
    uni = pd.DataFrame({"ticker": ["A3", "B3", "C3", "D3", "E3"], "proxy": ["A1", "B1", "C1", "D1", "E1"]})
    fr(cal[:-19]).to_csv(raw / "A3.csv"); fr(cal).to_csv(raw / "A1.csv")                  # 3배 19거래일 없음 → 의심 아님
    fr(cal[:-20]).to_csv(raw / "B3.csv"); fr(cal).to_csv(raw / "B1.csv")                  # 3배 20거래일 없음 → ①
    fr(cal[:-10]).to_csv(raw / "C3.csv"); fr(cal[:-10]).to_csv(raw / "C1.csv")            # 1x·3배 모두 10거래일 정체 → ②
    fr(cal[:-10]).to_csv(raw / "D3.csv"); fr(cal[:-9]).to_csv(raw / "D1.csv")             # 1x 9거래일 → 의심 아님
    fr(cal[:-9]).to_csv(raw / "E3.csv"); fr(cal[:-30]).to_csv(raw / "E1.csv")             # 3배 9거래일·1x 오래됨 → 의심 아님(둘 다 10 미만이 아니라 3배 쪽이 9)
    s = dict(FW.suspects(uni=uni, raw_dir=raw))
    check("① 3배 20거래일 없음 → 의심, 19거래일 → 아님", "B3" in s and "A3" not in s, s)
    check("② 1x·3배 모두 10거래일 정체 → 의심, 한쪽 9거래일 → 아님", "C3" in s and "D3" not in s and "E3" not in s, s)
    ln = FW.line(FW.suspects(uni=uni, raw_dir=raw))
    check("주간 1줄 형식 '피드 중단 의심: 티커(사유)'", ln.startswith("피드 중단 의심: ") and "B3(" in ln and "C3(" in ln, ln)
    check("의심 없으면 줄 없음", FW.line([]) is None)
    check("읽기 실패 파일은 건너뜀(감시가 주간 점검을 깨지 않음)", dict(FW.suspects(uni=pd.DataFrame({"ticker": ["ZZ3"], "proxy": ["ZZ1"]}), raw_dir=raw)) == {})
src = (ROOT / "scripts" / "mm_weekly_scan.py").read_text(encoding="utf-8")
check("주간 스캔에 피드 감시 줄 배선(의심 있을 때만)", "mm_feedwatch" in src and "lines.append(_fw)" in src)
print(f"\n{ok} PASS, {len(bad)} FAIL"); sys.exit(1 if bad else 0)
