"""MM-SPLIT-GUARD-20261106 D3 시험 — 분할 가드(SOXX·ITA 2026-11-05 3:1 재현) + 주간 분할 캘린더 알림
네트워크 0 · 텔레그램 0 · push 0 · 실제 데이터 0. 사용: python3 tests/test_split_guard.py"""
import sys, io, os, json, tempfile, contextlib, subprocess as _sp
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np, pandas as pd
import mm_lib as L
L.log = lambda m, name="daily": None
import mm_daily as D
import mm_splits as SP, mm_tailetn as TN, mm_splitwatch as SW
ok = 0; bad = []
def check(name, cond, detail=""):
    global ok
    if cond: ok += 1; print("PASS", name)
    else: bad.append(name); print("FAIL", name, detail)

P = pd.Timestamp
# ───────────────────────── (C) 분할 가드 ─────────────────────────
check("parse_ratio: 3:1 · 3 : 1 → 3.0 / 1 : 2 → 0.5 / 이상값 None", SP.parse_ratio("3:1") == 3.0 and SP.parse_ratio("3 : 1") == 3.0 and SP.parse_ratio("1 : 2") == 0.5 and SP.parse_ratio("x") is None and SP.parse_ratio(None) is None)
DAYS = pd.bdate_range("2026-10-26", "2026-11-05")                       # 10-26 … 11-05 (9일)
def ser(vals, days=DAYS): return pd.Series(vals, index=pd.DatetimeIndex(days))
# 실제 값(2026-11-05 실측): SOXX 원본(분할 조정 전) 170→…→450.41, 분할 후 131.9 / SOXL 66.68→40.87
soxx_adj = [163.94, 170.35, 173.98, 171.29, 157.17, 151.22, 155.00, 150.14, 131.90]      # 야후 최종(전 이력 ÷3)
soxx_raw = [v * 3 for v in soxx_adj[:-1]] + [131.90]                                      # 08:18형: 이력 미조정 + 11-05 만 조정 후
soxl = [80.0, 85.0, 90.0, 95.0, 77.05, 68.17, 73.12, 66.68, 40.87]
c3 = ser(soxl)
ev = [(P("2026-11-05"), 3.0)]
art = SP.detect(ser(soxx_raw), c3, ev)
check("08:18형(이력 미조정 450 → 131.9, 원 비율 0.293): 11-05 봉이 분할 아티팩트(g=1/3)", len(art) == 1 and art[0]["date"] == P("2026-11-05") and abs(art[0]["g"] - 1 / 3) < 1e-3 and art[0]["err"] < 0.02, art)
check("  └ 원 비율×f 만 보는 방식(±2%)이면 실제 등락 −12% 때문에 놓친다 = 3x 기대치 사용 근거", abs(131.90 / (150.14 * 3) * 3 - 1) > 0.02, 131.90 / 450.41 * 3)
# 10:19형: 10-30 까지 조정(157), 11-02~11-04 미조정(×3), 11-05 NaN 제거로 없음 → 11-02 봉 +188%
soxx_mix = [163.94, 170.35, 173.98, 171.29, 157.17, 151.22 * 3, 155.00 * 3, 150.14 * 3]
art2 = SP.detect(ser(soxx_mix, DAYS[:-1]), ser(soxl[:-1], DAYS[:-1]), ev)
check("10:19형(조정된 157 → 미조정 453, +188.6%): 11-02 봉이 아티팩트(g=3)", len(art2) == 1 and art2[0]["date"] == P("2026-11-02") and abs(art2[0]["g"] - 3.0) < 1e-3, art2)
check("14:10형(전 이력 일관): 아티팩트 0 → 정상 경로 복귀", SP.detect(ser(soxx_adj), c3, ev) == [])
check("분할 이벤트가 없으면(진짜 급락 −70%) 아티팩트로 오판하지 않는다", SP.detect(ser(soxx_raw), c3, []) == [])
check("분할 배율과 안 맞는 급락(원 비율 0.5, 3배 −3%)은 오판하지 않는다", SP.detect(ser([100, 100, 100, 100, 100, 100, 100, 100, 50]), ser([10, 10, 10, 10, 10, 10, 10, 10, 9.7]), ev) == [])
check("3배 봉이 없는 날은 판정 보류(오판 0)", SP.detect(ser(soxx_raw), c3.iloc[:-1], ev) == [])
# 통합: RAW 디렉터리 → guard → mm_tailetn.fill (3배÷3 보충)
def write_hist(path, closes, days, splits=None):
    h = pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes, "Adj Close": closes, "Volume": 1e6, "Dividends": 0.0, "Stock Splits": 0.0, "Capital Gains": 0.0}, index=pd.DatetimeIndex(days).tz_localize("America/New_York"))
    for d, f in (splits or {}).items(): h.loc[pd.Timestamp(d).tz_localize("America/New_York"), "Stock Splits"] = f
    h.index.name = "Date"; h.to_csv(path)
uni = pd.DataFrame({"ticker": ["SOXL"], "proxy": ["SOXX"]})
with tempfile.TemporaryDirectory() as td:
    td = Path(td); write_hist(td / "SPY.csv", [1.0] * len(DAYS), DAYS)
    write_hist(td / "SOXX.csv", soxx_raw, DAYS, splits={"2026-11-05": 3.0}); write_hist(td / "SOXL.csv", soxl, DAYS)
    info = SP.guard(P("2026-11-05"), uni, td, log=lambda m: None, info_path=td / "split_pending.json")
    h = TN._rd(td / "SOXX.csv")
    check("guard: 아티팩트 봉부터 끝까지 제외(SOXX 마지막 봉 11-04), 상태 split_pending", info.get("SOXX", {}).get("status") == "split_pending" and TN._days(h.index).max() == P("2026-11-04") and info["SOXX"]["dropped_rows"] == 1, info)
    check("guard: split_pending.json 기록", json.loads((td / "split_pending.json").read_text())["proxies"]["SOXX"]["split"] == "3:1")
    fi = TN.fill(P("2026-11-05"), uni, td, log=lambda m: None, write=True, info_path=None)
    c1 = TN._close_by_day(TN._rd(td / "SOXX.csv"))
    exp = 150.14 * 3 * (1 + (40.87 / 66.68 - 1) / 3)
    check("fill: 제외된 11-05 를 3배÷3 로 1일 보충(status=filled, 값 = 450.42×(1+r3/3))", fi.get("SOXX", {}).get("status") == "filled" and fi["SOXX"]["days"] == 1 and abs(float(c1.loc[P("2026-11-05")]) - exp) < 0.01, (fi, float(c1.iloc[-1]), exp))
    check("  └ 보충 후 11-05 일간 수익률이 실제(−12.2%)와 1%p 안", abs(float(c1.loc[P("2026-11-05")] / c1.loc[P("2026-11-04")]) - 131.90 / 150.14) < 0.01)
    check("  └ 보충 후 이상봉(|r|>25%) 0건", (c1.pct_change().abs() > 0.25).sum() == 0)
    info2 = SP.guard(P("2026-11-05"), uni, td, log=lambda m: None, write=False)
    check("재실행(이제 이력 일관): 아티팩트 0 → 정상 경로", info2 == {}, info2)
# 간격 > MAX_GAP: 10:19형에서 11-02 부터 제외하면 11-02·03·04·05 = 4거래일 → fill 이 over_max(⚠ 유지) — 가드가 점수를 거짓으로 채우지 않는다
with tempfile.TemporaryDirectory() as td:
    td = Path(td); write_hist(td / "SPY.csv", [1.0] * len(DAYS), DAYS)
    write_hist(td / "SOXX.csv", soxx_mix + [131.90], DAYS, splits={"2026-11-05": 3.0}); write_hist(td / "SOXL.csv", soxl, DAYS)
    info = SP.guard(P("2026-11-05"), uni, td, log=lambda m: None)
    fi = TN.fill(P("2026-11-05"), uni, td, log=lambda m: None, write=True)
    check("제외 구간 > 3거래일이면 보충하지 않고 over_max(⚠ 유지·거짓 값 0)", info.get("SOXX", {}).get("status") == "split_pending" and fi.get("SOXX", {}).get("status") == "over_max", (info, fi))
# annotate
dfa = pd.DataFrame({"ticker": ["SOXL", "BULZ"], "reason": [np.nan, "기존 사유"]})
dfa = SP.annotate(dfa, {"SOXX": {"split": "3:1", "split_date": "2026-11-05", "members": ["SOXL"]}})
check("annotate: 대상 종목 reason 에만 「분할 반영 대기」 표시(NaN→빈칸 시작)", dfa.reason.iloc[0].strip().startswith("[분할 반영 대기: SOXX 3:1") and dfa.reason.iloc[1] == "기존 사유", dfa)

# ───────────────────────── (D) 주간 분할 캘린더 ─────────────────────────
NASDAQ = json.dumps({"data": {"rows": [{"symbol": "SOXX", "name": "iShares", "ratio": "3:1", "executionDate": "11/05/2026"}, {"symbol": "ITA", "name": "iShares", "ratio": "3 : 1", "executionDate": "11/05/2026"},
                                     {"symbol": "AAPL", "name": "Apple", "ratio": "4:1", "executionDate": "11/20/2026"}, {"symbol": "SNDK", "name": "x", "ratio": "8:1", "executionDate": "12/30/2026"}]}})
uni2 = pd.DataFrame({"ticker": ["SOXL", "DFEN", "BULZ"], "proxy": ["SOXX", "ITA", "IDX_X"]})
sent = []
with tempfile.TemporaryDirectory() as td:
    sp = Path(td) / "seen.json"
    msg = SW.run(alert=True, today="2026-11-04", fetch=lambda d: NASDAQ, uni=uni2, seen_path=sp, send=sent.append, use_yf=False)
    check("주간 알림: 유니버스 관련 SOXX·ITA 만(AAPL·SNDK 제외), 영향 상품 SOXL·DFEN 표기·1건 발송", msg and "SOXX 3:1" in msg and "ITA" in msg and "SOXL" in msg and "DFEN" in msg and "AAPL" not in msg and len(sent) == 1, (msg, sent))
    msg2 = SW.run(alert=True, today="2026-11-04", fetch=lambda d: NASDAQ, uni=uni2, seen_path=sp, send=sent.append, use_yf=False)
    check("같은 분할은 두 번 알리지 않는다", msg2 is None and len(sent) == 1)
    sp2 = Path(td) / "seen2.json"; sent2 = []
    msg3 = SW.run(alert=True, dry=True, today="2026-11-04", fetch=lambda d: NASDAQ, uni=uni2, seen_path=sp2, send=sent2.append, use_yf=False)
    check("--dry-run: 메시지만 반환·발송 0·seen 파일 미생성", msg3 and sent2 == [] and not sp2.exists())
    msg4 = SW.run(alert=True, today="2026-11-04", fetch=lambda d: "not json", uni=uni2, seen_path=Path(td) / "s3.json", send=sent2.append, use_yf=False)
    check("캘린더 수신 실패 → 알림 0·예외 0", msg4 is None and sent2 == [])
print(f"\n{ok} PASS / {len(bad)} FAIL"); sys.exit(0 if not bad else 1)
