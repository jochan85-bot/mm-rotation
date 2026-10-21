#!/usr/bin/env python3
"""피드 중단 의심 감시 (MM-THIN-ETN-HIST-20261021 §2) — 표시·알림 전용. 순위·점수·제외 판정에 쓰이지 않는다(제외는 공시 규칙 `mm_rules` 로만).
의심 조건(기준일 = SPY 마지막 봉, 거래일 = SPY 달력):
  ① 3배 봉이 기준일 이전 마지막 봉 뒤로 20거래일 이상 없음(= 20거래일 연속 nobar)
  ② 1x(점수 입력)·3배 피드가 모두 마지막 봉 뒤로 10거래일 이상 멈춤
거래 없는 날은 나스닥 기록 사이 빈 거래일로 채워진 봉(src=filled)이 있어 중간 공백은 세지 않는다 — 마지막 봉 '뒤'의 공백만 센다.
주간 텔레그램에 `피드 중단 의심: 티커(사유)` 1줄(의심이 있을 때만). 사용: mm_weekly_scan 이 주간 산출 뒤 suspects() 호출."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mm_lib as L
N3 = 20            # 3배 봉 연속 부재 거래일
N_BOTH = 10        # 1x·3배 모두 정체 거래일


def _last_date(path):
    h = pd.read_csv(path, index_col=0)
    d = pd.to_datetime(h.index, utc=True).tz_convert("America/New_York").tz_localize(None).normalize()
    ok = h["Close"].notna().values if "Close" in h.columns else [True] * len(d)
    d = d[ok]
    return d.max() if len(d) else None


def suspects(uni=None, raw_dir=None, n3=N3, n_both=N_BOTH):
    """[(티커, 사유 문자열)] — RAW(.local/p0view/data) 의 마지막 봉 날짜로 판정. 파일이 없거나 읽기 실패한 티커는 '읽기 실패' 로 올리지 않고 건너뛴다(감시가 주간 점검을 깨지 않는다)."""
    raw = Path(raw_dir or (L.RAW / "data"))
    uni = uni if uni is not None else pd.read_csv(L.DATA / "universe.csv")
    spy = pd.read_csv(raw / "SPY.csv", index_col=0)
    cal = pd.DatetimeIndex(pd.to_datetime(spy.index, utc=True).tz_convert("America/New_York").tz_localize(None).normalize()).sort_values()
    out = []
    for r in uni.itertuples():
        try:
            d3 = _last_date(raw / f"{r.ticker}.csv")
            d1 = _last_date(raw / f"{r.proxy}.csv") if (raw / f"{r.proxy}.csv").exists() else None
        except Exception:
            continue
        if d3 is None: continue
        k3 = int((cal > d3).sum()); k1 = int((cal > d1).sum()) if d1 is not None else None
        if k3 >= n3:
            out.append((r.ticker, f"3배 봉 {k3}거래일 없음(마지막 {d3.date()})"))
        elif k1 is not None and k1 >= n_both and k3 >= n_both:
            out.append((r.ticker, f"1x {k1}·3배 {k3}거래일 정체(마지막 1x {d1.date()}·3배 {d3.date()})"))
    return out


def line(sus):
    """주간 텔레그램 1줄. 의심이 없으면 None."""
    if not sus: return None
    return "피드 중단 의심: " + ", ".join(f"{t}({why})" for t, why in sus)


if __name__ == "__main__":
    s = suspects(); print(line(s) or "피드 중단 의심: 없음")
