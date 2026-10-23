#!/usr/bin/env python3
"""거래량 극소 제외 종목의 복귀 조건 점검 (MM-FUNDTRACK-20261023 §3) — 보고 전용, 자동 복귀 없음.
대상 = data/thin_excluded.json 의 종목(유니버스 밖). 3배 일봉은 일일·주간 수신(야후 → 나스닥 폴백)이 계속 RAW(.local/p0view/data)에 쓴다.
복귀 조건(eligibility.yaml E7) = 3배 20일 평균 거래량(주) ≥ threshold 인 거래일이 return_days(20) 거래일 연속.
  · '거래일' = SPY 달력. 일별 값 = 그 날까지 최근 20 거래일의 평균 거래량. 달력 날짜에 봉이 없으면 거래량 0 (나스닥 기록 사이 빈 날은 수신 단계에서 filled·거래량 0 으로 이미 채워짐 — 마지막 봉 뒤 공백도 0 으로 센다: 수신 지연이 '정상 거래'로 가려지지 않게).
  · 상장 첫 봉 이전 날짜는 세지 않는다(첫 봉 이후 20거래일이 쌓여야 첫 평균이 생긴다).
주간 텔레그램에 1줄(`line()`): 제외 종목별 현재 평균·연속 일수, 조건 충족 시 '복귀 후보'. 복귀는 오너 결정 — universe.csv 에 행을 되돌리는 것."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mm_lib as L

WIN = 20


def _days(idx):
    return pd.DatetimeIndex(pd.to_datetime(idx, utc=True).tz_convert("America/New_York").tz_localize(None).normalize())


def calendar(raw_dir):
    spy = pd.read_csv(Path(raw_dir) / "SPY.csv", index_col=0)
    return sorted(set(_days(spy.index)))


def daily_avg20(h, cal):
    """RAW 프레임 h(Volume 열, tz-aware 인덱스) → cal(달력 날짜 리스트) 각 날의 trailing 20일 평균 거래량 Series (첫 봉 이후 20거래일 미만인 날은 NaN)."""
    v = pd.Series(h["Volume"].astype(float).values, index=_days(h.index))
    v = v[~v.index.duplicated(keep="last")].fillna(0.0)
    if not len(v): return pd.Series(dtype=float)
    first = v.index.min()
    days = [d for d in cal if d >= first]
    s = v.reindex(days).fillna(0.0)
    return s.rolling(WIN, min_periods=WIN).mean()


def streak(avg, threshold):
    """끝에서부터 연속으로 avg ≥ threshold 인 거래일 수 (NaN 에서 끊김)."""
    n = 0
    for x in avg.values[::-1]:
        if x == x and x >= threshold: n += 1
        else: break
    return n


def check(items=None, raw_dir=None, threshold=None, need=None):
    """[dict(ticker, avg20, streak, need, threshold, candidate, last_bar, note)] — 파일이 없거나 읽지 못하면 note 에 사유(후보 아님)."""
    items = L.thin_excluded() if items is None else items
    raw = Path(raw_dir or (L.RAW / "data"))
    cfg = L.load_yaml_simple(L.DATA / "eligibility.yaml").get("E7", {}) if threshold is None or need is None else {}
    thr = float(threshold if threshold is not None else cfg.get("threshold", 1000))
    nd = int(need if need is not None else cfg.get("return_days", 20))
    out = []
    try: cal = calendar(raw)
    except Exception as e:
        return [dict(ticker=x.get("ticker"), avg20=None, streak=0, need=nd, threshold=thr, candidate=False, last_bar="", note=f"SPY 달력 읽기 실패({type(e).__name__})") for x in items]
    for x in items:
        t = x.get("ticker"); r = dict(ticker=t, avg20=None, streak=0, need=nd, threshold=thr, candidate=False, last_bar="", note="")
        try:
            h = pd.read_csv(raw / f"{t}.csv", index_col=0)
            avg = daily_avg20(h, cal)
            r["last_bar"] = str(_days(h.index).max().date())
            if len(avg) and avg.iloc[-1] == avg.iloc[-1]: r["avg20"] = float(avg.iloc[-1])
            r["streak"] = streak(avg, thr) if len(avg) else 0
            r["candidate"] = r["streak"] >= nd
        except Exception as e:
            r["note"] = f"읽기 실패({type(e).__name__}: {str(e)[:60]})"
        out.append(r)
    return out


def line(res):
    """주간 텔레그램 1줄. 제외 종목이 없으면 None."""
    if not res: return None
    parts = []
    for r in res:
        a = "미산출" if r["avg20"] is None else f"{r['avg20']:,.0f}주"
        parts.append(f"{r['ticker']} 20일 평균 {a}(연속 {r['streak']}/{r['need']}일)" + (f" [{r['note']}]" if r["note"] else ""))
    cand = [r["ticker"] for r in res if r["candidate"]]
    thr = int(res[0]["threshold"])
    tail = ("복귀 후보: " + ", ".join(cand) + f" — 20일 평균 ≥{thr:,}주가 {res[0]['need']}거래일 연속(자동 복귀 없음, 오너 결정)") if cand else "복귀 후보: 없음"
    return "거래량 극소 제외 종목: " + " · ".join(parts) + " — " + tail


if __name__ == "__main__":
    print(line(check()) or "거래량 극소 제외 종목: 없음")
