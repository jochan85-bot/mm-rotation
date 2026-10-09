"""MM-NEWIDX-CHECK-20261011 단위 테스트 — 지수 이력 재구성 비율·사유·표. python3 tests/test_idxhist.py"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
import pandas as pd
import mm_idxhist as H
ok = 0; bad = []
def check(name, cond, detail=""):
    global ok
    if cond: ok += 1; print("PASS", name)
    else: bad.append(name); print("FAIL", name, detail)

dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2025-01-01", "2026-10-08")]
asof = "2026-10-08"
it = {"official_first": "2026-07-13", "ext": {"has": True}}
n, w = H.window_stats("2026-07-13", dates, asof)
win = dates[-252:]
check("창 = 기준일 포함 최근 252거래일", w == 252 and win[-1] == asof)
check("연장 일수 = 창 안에서 공식 첫 날짜 이전", n == sum(1 for d in win if d < "2026-07-13"), n)
check("비율 반올림·최소 1", H.window_pct(it, dates, asof) == round(100 * n / 252))
check("연장이 창에 없으면 0(사유 없음)", H.window_pct({"official_first": "2021-01-04", "ext": {"has": True}}, dates, asof) == 0 and H.reason({"official_first": "2021-01-04", "ext": {"has": True}}, dates, asof) == "")
check("연장 없는 종목(야후 지수)은 0", H.window_pct({"official_first": "1985-10-01", "ext": {"has": False}}, dates, asof) == 0)
check("1일만 걸치면 최소 1%", H.window_pct({"official_first": dates[-251], "ext": {"has": True}}, dates, asof) == 1)
check("문구(MM-BT-CHARTS-20261011: '재구성 N%' 로 단축)", H.reason(it, dates, asof).startswith("재구성 ") and H.reason(it, dates, asof).endswith("%") and "(" not in H.reason(it, dates, asof))
check("과거 날짜는 창이 달라 비율이 다름", H.window_pct(it, dates, "2026-07-31") != H.window_pct(it, dates, asof))
# 실제 정적 파일
items = H.load_history()
check("정적 기록 18종", len(items) == 18, len(items))
rows = H.table_rows(asof, dates, items)
check("공식 지수 레벨 경로 종목만(야후 지수 6 + 공시 레벨 12)", sum(r["kind"] == "yahoo_index" for r in rows) == 6 and sum(r["kind"] == "official_level" for r in rows) == 12)
check("모든 종목에 공식 첫 날짜·상장일", all(r["official_first"] and r["listed"] for r in rows))
check("연장 있는 종목은 방법·시작~끝 기록", all(r["ext_method"] != "—" and r["ext_start"] and r["ext_end"] and r["ext_end"] < r["official_first"] for r in rows if r["has_ext"]))
print(f"{ok} PASS, {len(bad)} FAIL"); sys.exit(1 if bad else 0)
