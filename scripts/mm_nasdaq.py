#!/usr/bin/env python3
"""극저유동 ETN 3배 일봉 수신 — 나스닥 일별 기록 1차 · 야후 2차 (MM-WRAP-BT-20261011 §1).

배경: 거래가 거의 없는 ETN(XLCU·XLPU)의 야후 일봉은 거래 없는 날을 직전 가격 그대로 잇는 거래량 0 봉이라 실제 거래 기록과 날마다 다르고,
      일부 날짜는 봉 자체가 없어 '최신 확정 봉이 기준일과 다름'(⚠)으로 순위에서 빠졌다(2026-10-08). 나스닥 공식 시세(api.nasdaq.com)에는 일별 거래 기록이 있다.
대상: universe 의 ETN 중 **야후 수신분 20일 평균 거래량 < 1,000주**인 종목 전부(매 수신마다 야후 값으로 판정 — 상태 저장 없음).
적용: 수신 직후(clean_all 전) `.local/fetched/<티커>.csv` 를 나스닥 기록으로 **교체**하고 행마다 `src` 열을 둔다.
  - src=nasdaq : 나스닥 일별 기록(시가·고가·저가·종가·거래량 그대로, 수정종가=종가)
  - src=filled : 나스닥 기록 사이의 빈 거래일(거래 없음) — 직전 종가 그대로, 거래량 0. 마지막 나스닥 기록 **뒤**는 채우지 않는다(수신 지연을 '무거래'로 가리지 않음 → 신선도 ⚠ 유지).
  - src=yahoo  : 나스닥 수신 실패 시 야후 전체(2차). 이 경우 파일은 야후 값 그대로 + src=yahoo.
점수(M-score)는 1x 만 쓴다 — 3배 일봉은 거래대금·무거래·신선도·표본 배지와 β/R² 품질에만 쓰인다. 1x·점수 계산 코드는 건드리지 않는다.
사용: mm_daily/mm_weekly_scan 이 fetch_all 직후 apply_after_fetch() 호출. 단독 시험: python3 scripts/mm_nasdaq.py --dry"""
import json, sys, time, datetime, urllib.error, urllib.parse, urllib.request
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"; LOCAL = ROOT / ".local"; FETCHED = LOCAL / "fetched"
LOW_VOL_THRESHOLD = 1000          # 야후 수신분 20일 평균 거래량(주) 미만이면 나스닥 1차
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
URL = "https://api.nasdaq.com/api/quote/{t}/historical?assetclass=etf&fromdate={f}&limit=9999&todate={to}"
COLS = ["Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends", "Stock Splits", "Capital Gains"]


def etn_tickers():
    u = pd.read_csv(DATA / "universe.csv")
    return u[u["type"] == "ETN"].ticker.tolist()


def avg_volume20(h):
    return float(h["Volume"].tail(20).mean()) if len(h) else float("nan")


def select_low_volume(frames, tickers, threshold=LOW_VOL_THRESHOLD):
    """frames={티커: 야후 DataFrame(Volume 열)} → 20일 평균 거래량 < threshold 인 ETN 목록(정렬)."""
    out = []
    for t in tickers:
        h = frames.get(t)
        if h is None or len(h) == 0: continue
        if avg_volume20(h) < threshold: out.append(t)
    return sorted(out)


def parse_rows(rows):
    """나스닥 historical rows(dict 목록: date 'MM/DD/YYYY', open/high/low/close/volume 문자열) → DataFrame(날짜 인덱스, src=nasdaq)."""
    recs = []
    for r in rows:
        try:
            d = pd.Timestamp(datetime.datetime.strptime(r["date"], "%m/%d/%Y"))
            f = lambda k: float(str(r[k]).replace(",", "").replace("$", ""))
            recs.append((d, f("open"), f("high"), f("low"), f("close"), int(f("volume"))))
        except Exception:
            continue                                          # 형식이 다른 행은 버리고 건수를 호출측이 비교한다
    if not recs: return pd.DataFrame(columns=COLS + ["src"])
    df = pd.DataFrame(recs, columns=["d", "Open", "High", "Low", "Close", "Volume"]).drop_duplicates("d", keep="last").set_index("d").sort_index()
    df["Adj Close"] = df["Close"]; df["Dividends"] = 0.0; df["Stock Splits"] = 0.0; df["Capital Gains"] = 0.0
    df["src"] = "nasdaq"
    return df[COLS + ["src"]]


def fill_gaps(df, calendar):
    """나스닥 기록 사이(첫~마지막 기록)의 빈 거래일을 직전 종가·거래량 0 봉(src=filled)으로 채운다. 마지막 기록 뒤는 채우지 않는다."""
    if len(df) == 0: return df
    cal = pd.DatetimeIndex(calendar)
    cal = cal[(cal >= df.index.min()) & (cal <= df.index.max())]
    miss = cal.difference(df.index)
    if len(miss) == 0: return df
    prev = df["Close"].reindex(df.index.union(miss)).ffill()
    add = pd.DataFrame({"Open": prev[miss], "High": prev[miss], "Low": prev[miss], "Close": prev[miss], "Adj Close": prev[miss], "Volume": 0,
                        "Dividends": 0.0, "Stock Splits": 0.0, "Capital Gains": 0.0, "src": "filled"}, index=miss)
    return pd.concat([df, add]).sort_index()


def fetch_nasdaq(t, since, opener=None, retries=3):
    """나스닥 일별 기록 → rows(list). 실패 시 예외."""
    url = URL.format(t=urllib.parse.quote(t), f=since, to=(datetime.date.today() + datetime.timedelta(days=1)).isoformat())
    last = None
    for k in range(retries):
        try:
            if opener: txt = opener(url)
            else:
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
                txt = urllib.request.urlopen(req, timeout=30).read()
            j = json.loads(txt)
            rows = ((j.get("data") or {}).get("tradesTable") or {}).get("rows")
            if not rows: raise ValueError("나스닥 응답에 rows 없음")
            return rows
        except Exception as e:
            last = e; time.sleep(2 * (k + 1))
    raise last


def to_fetched_format(df):
    """fetched csv 와 같은 인덱스 형식('YYYY-MM-DD 00:00:00-04:00' 등)·열 순서(+ src)로."""
    out = df.copy(); out.index = out.index.tz_localize("America/New_York"); out.index.name = "Date"
    return out[COLS + ["src"]]


def apply_after_fetch(log=print, write=True, opener=None, fetched=None, tickers=None, calendar=None):
    """수신 직후 호출. 반환 {선정 티커: 상태 문자열}. 어떤 실패도 예외로 올리지 않는다(야후 값 유지 + src=yahoo)."""
    fetched = Path(fetched or FETCHED); res = {}
    try:
        tickers = tickers or etn_tickers()
        frames = {}
        for t in tickers:
            p = fetched / f"{t}.csv"
            if p.exists():
                h = pd.read_csv(p, index_col=0)
                if "src" in h.columns and (h["src"] == "nasdaq").any():          # 직전 실행이 나스닥으로 바꾼 파일 — 야후 값으로 판정하려면 새로 받은 야후여야 한다
                    continue
                frames[t] = h
        sel = select_low_volume(frames, tickers)
        log(f"[mm_nasdaq] 극저유동 ETN(야후 20일 평균 거래량 < {LOW_VOL_THRESHOLD}) {sel}")
        cal = calendar
        if cal is None:
            spy = pd.read_csv(fetched / "SPY.csv", index_col=0)
            cal = pd.to_datetime(spy.index, utc=True).tz_convert("America/New_York").tz_localize(None).normalize()
        for t in sel:
            yh = frames[t]
            try:
                first = pd.to_datetime(yh.index, utc=True).tz_convert("America/New_York").tz_localize(None).min()
                rows = fetch_nasdaq(t, (first - pd.Timedelta(days=10)).date().isoformat(), opener=opener)
                nd = parse_rows(rows)
                if len(nd) == 0: raise ValueError("파싱된 행 0")
                if len(nd) < len(rows) * 0.9: raise ValueError(f"파싱 실패 다수 {len(rows) - len(nd)}/{len(rows)}")
                nd = fill_gaps(nd, cal)
                if write: to_fetched_format(nd).to_csv(fetched / f"{t}.csv")
                res[t] = f"nasdaq {len(nd)}봉 ({nd.index.min().date()}~{nd.index.max().date()}, filled {int((nd.src == 'filled').sum())})"
            except Exception as e:
                res[t] = f"yahoo(2차) — 나스닥 실패: {type(e).__name__}: {str(e)[:150]}"
                log(f"[mm_nasdaq] {t} 나스닥 수신 실패 → 야후 값 유지: {type(e).__name__}: {str(e)[:200]}")
                if write:
                    y = yh.copy(); y["src"] = "yahoo"; y.to_csv(fetched / f"{t}.csv")
                try:                                                                       # 실패를 눈에 띄게(경보 로그)
                    sys.path.insert(0, str(Path(__file__).resolve().parent)); import mm_lib; mm_lib.log(f"[mm_nasdaq] {t} 나스닥 수신 실패 → 야후 사용: {type(e).__name__}: {str(e)[:200]}", "alerts")
                except Exception: pass
            time.sleep(0.3)
        for t, s in res.items(): log(f"[mm_nasdaq] {t}: {s}")
    except Exception as e:
        log(f"[mm_nasdaq] 건너뜀(야후 값 유지): {type(e).__name__}: {str(e)[:200]}")
    return res


if __name__ == "__main__":
    print(json.dumps(apply_after_fetch(write="--dry" not in sys.argv), ensure_ascii=False, indent=1))
