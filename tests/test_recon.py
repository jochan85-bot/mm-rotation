"""MM-RECON-RULE-20261011 단위·데이터 테스트 — 구성종목 복제 연장 점수 창 규칙. python3 tests/test_recon.py"""
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

IT = H.load_history()
check("차단 방법 = 구성종목 복제만", H.BLOCK_METHODS == ("구성종목 복제",))
check("AIQU·MNGU·FLYU·GDXU 는 복제(차단 방법), SMHU·XLCU·XLPU·BULZ·FNGU 는 허용", all(H.is_blocked_method(IT[t]) for t in ("AIQU", "MNGU", "FLYU", "GDXU")) and not any(H.is_blocked_method(IT[t]) for t in ("SMHU", "XLCU", "XLPU", "BULZ", "BNKU", "NRGU", "OILU", "FNGU", "TQQQ")))
check("창 첫 날이 공식 첫 날짜 이전이면 차단", H.recon_blocked(IT["AIQU"], "2026-05-14") and H.recon_blocked(IT["AIQU"], "2025-10-07"))
check("창 첫 날이 공식 첫 날짜 이후(포함)면 허용", not H.recon_blocked(IT["AIQU"], "2026-05-15") and not H.recon_blocked(IT["AIQU"], "2026-06-01"))
check("허용 방법은 창에 연장이 있어도 차단 아님", not H.recon_blocked(IT["SMHU"], "2025-10-07"))
e = H.eligible_date("2026-05-15"); n = len(__import__("pandas_market_calendars").get_calendar("NYSE").schedule("2026-05-15", e))
check("산출 가능 예정일 = 공식 첫 날짜를 1번째로 세어 252번째 NYSE 거래일", n == 252, (e, n))
check("AIQU·MNGU 복귀 예정일", H.eligible_date(IT["AIQU"]["official_first"]) == "2027-05-17" and H.eligible_date(IT["MNGU"]["official_first"]) == "2027-08-19")
check("상태 문구", H.recon_reason(IT["AIQU"]) == "지수 이력 부족(공식 2026-05-15부터, 산출 가능 예정 2027-05-17)", H.recon_reason(IT["AIQU"]))
check("재구성 N% 사유는 허용 유형에만(AIQU·MNGU 사유 0, SMHU 있음)", H.window_pct(IT["AIQU"], H.trading_dates(), "2026-10-08") == 0 and H.window_pct(IT["SMHU"], H.trading_dates(), "2026-10-08") > 0)
# ---- 산출물(날짜 파일·상태) 정합
sd = ROOT / "docs" / "data" / "scores"
def tick(d): return set(pd.read_csv(sd / f"{d}.csv", skiprows=1).ticker)
check("AIQU 상장 이후 날짜 파일에 AIQU 없음 / 상장 전(5/14)에는 원래 없음", "AIQU" not in tick("2026-06-02") and "AIQU" not in tick("2026-10-08"))
check("MNGU 상장 이후 날짜 파일에 MNGU 없음", "MNGU" not in tick("2026-08-27") and "MNGU" not in tick("2026-10-08"))
check("복제 구간이 창에 없는 종목은 유지(FLYU 2023, GDXU 2022)", "FLYU" in tick("2023-06-01") and "GDXU" in tick("2022-06-01"))
check("GDXU 는 창에 복제가 있던 2021-08-18 까지만 빠짐, 2021-08-19 부터 복귀", "GDXU" not in tick("2021-08-18") and "GDXU" in tick("2021-08-19"), (("GDXU" in tick("2021-08-18")), ("GDXU" in tick("2021-08-19"))))
latest = pd.read_csv(ROOT / "data" / "scores_latest.csv")
st = latest[latest.table == "이력부족"]
check("최신 상태: 이력부족 = AIQU·MNGU 만, M 미산출·순위 없음", sorted(st.ticker) == ["AIQU", "MNGU"] and st.M.isna().all() and st["rank"].isna().all(), st[["ticker", "M", "rank"]])
check("최신 N = 35 (순위 대상)", int((latest.table == "순위").sum()) == 35)
check("series 파일: 이력 없는 종목(AIQU·MNGU)은 없음", not (ROOT / "docs" / "data" / "series" / "AIQU.json").exists() and not (ROOT / "docs" / "data" / "series" / "MNGU.json").exists())
print(f"{ok} PASS, {len(bad)} FAIL"); sys.exit(1 if bad else 0)
