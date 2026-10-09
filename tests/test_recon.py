"""MM-RECON-RULE-REV-20261011 단위·데이터 테스트 — 구성종목 복제 연장은 순위 제외 대신 ◐ 경고. python3 tests/test_recon.py"""
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

IT = H.load_history(); D = H.trading_dates()
check("◐ 대상 방법 = 구성종목 복제만", H.BLOCK_METHODS == ("구성종목 복제",))
check("AIQU·MNGU·FLYU·GDXU 는 ◐ 대상 방법, SMHU·XLCU·XLPU·BULZ·FNGU 는 아님", all(H.is_blocked_method(IT[t]) for t in ("AIQU", "MNGU", "FLYU", "GDXU")) and not any(H.is_blocked_method(IT[t]) for t in ("SMHU", "XLCU", "XLPU", "BULZ", "BNKU", "NRGU", "OILU", "FNGU", "TQQQ")))
ic = H.recon_icon(IT["AIQU"], D, "2026-10-08")
check("AIQU ◐ 60% · 공식 2026-05-15 · 해제 2027-05-17", ic and ic["pct"] == 60 and ic["of"] == "2026-05-15" and ic["rel"] == "2027-05-17", ic)
ic = H.recon_icon(IT["MNGU"], D, "2026-10-08")
check("MNGU ◐ 86% · 해제 2027-08-19", ic and ic["pct"] == 86 and ic["rel"] == "2027-08-19", ic)
check("탭 문구", H.recon_tip(H.recon_icon(IT["AIQU"], D, "2026-10-08")) == "되계산 비중 60% · 공식 지수 2026-05-15부터 · 해제 예정 2027-05-17")
check("관련 ETF 총수익 연장(SMHU·XLCU·XLPU)은 ◐ 없음·사유 없음", all(H.recon_icon(IT[t], D, "2026-10-08") is None and H.reason(IT[t], D, "2026-10-08") == "" for t in ("SMHU", "XLCU", "XLPU")))
check("GDXU 는 2021-03-01 에 ◐(48%), 2021-08-19 이후엔 없음 / FLYU 는 2022-08-01 에 ◐(25%)", H.recon_icon(IT["GDXU"], D, "2021-03-01")["pct"] == 48 and H.recon_icon(IT["GDXU"], D, "2021-08-19") is None and H.recon_icon(IT["FLYU"], D, "2022-08-01")["pct"] == 25)
check("현재(10-08) ◐ = AIQU·MNGU 뿐", sorted(t for t, it in IT.items() if H.recon_icon(it, D, "2026-10-08")) == ["AIQU", "MNGU"])
sd = ROOT / "docs" / "data" / "scores"
def tick(d): return set(pd.read_csv(sd / f"{d}.csv", skiprows=1).ticker)
check("순위 포함 복귀: AIQU·MNGU 가 상장 이후 날짜 파일에 있음", "AIQU" in tick("2026-06-02") and "AIQU" in tick("2026-10-08") and "MNGU" in tick("2026-08-27") and "MNGU" in tick("2026-10-08"))
check("GDXU(2020-12-03~2021-08-18)·FLYU(2022-06-22~2022-10-28)도 복귀", "GDXU" in tick("2020-12-03") and "GDXU" in tick("2021-08-18") and "FLYU" in tick("2022-06-22") and "FLYU" in tick("2022-10-28"))
latest = pd.read_csv(ROOT / "data" / "scores_latest.csv")
check("최신 N = 37 · 이력부족 상태 없음", int((latest.table == "순위").sum()) == 37 and not (latest.table == "이력부족").any())
check("AIQU·MNGU 최신 M-score·순위 산출", latest[latest.ticker.isin(["AIQU", "MNGU"])]["rank"].notna().all())
check("series 파일 복귀(AIQU·MNGU)", (ROOT / "docs" / "data" / "series" / "AIQU.json").exists() and (ROOT / "docs" / "data" / "series" / "MNGU.json").exists())
print(f"{ok} PASS, {len(bad)} FAIL"); sys.exit(1 if bad else 0)
