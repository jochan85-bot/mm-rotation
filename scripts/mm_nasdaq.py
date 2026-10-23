#!/usr/bin/env python3
"""극저유동 ETN 3배 일봉 수신 — 나스닥 일별 기록 1차 · 야후 2차 (MM-WRAP-BT-20261011 §1).
[MM-THIN-ETN-HIST-20261021 §1] 이력 복구: ① 나스닥 조회 시작일 = min(야후 첫 봉, 상장일 product_info.first_bar) − 10일(종전: 야후 첫 봉 − 10일 → 야후가 이력을 최근 며칠분만 주면 나스닥도 그만큼만 받아 상장 거래일수·거래대금·무거래가 실제와 다르게 표시됨)
  ② 선정 기준 추가: 야후 이력이 상장일 대비 20봉 이상 짧은 3배 상품(기대 거래일 수 − 야후 봉 수 ≥ 20)도 나스닥 이력 수신 대상 — 극저유동(20일 평균 거래량 < 1,000주, 나스닥 이력 기준 재판정)이면 종전처럼 교체, 아니면 야후 값은 두고 그 앞 구간만 나스닥으로 보충
  ③ 교체본의 마지막 나스닥 기록 뒤에 야후의 실거래 봉(거래량 > 0)이 있으면 보조로 잇는다(src=yahoo).

배경: 거래가 거의 없는 ETN(XLCU·XLPU)의 야후 일봉은 거래 없는 날을 직전 가격 그대로 잇는 거래량 0 봉이라 실제 거래 기록과 날마다 다르고,
      일부 날짜는 봉 자체가 없어 '최신 확정 봉이 기준일과 다름'(⚠)으로 순위에서 빠졌다(2026-10-08). 나스닥 공식 시세(api.nasdaq.com)에는 일별 거래 기록이 있다.
대상: universe 의 ETN 중 **야후 수신분 20일 평균 거래량 < 1,000주**인 종목 전부(매 수신마다 야후 값으로 판정 — 상태 저장 없음).
적용: 수신 직후(clean_all 전) `.local/fetched/<티커>.csv` 를 나스닥 기록으로 **교체**하고 행마다 `src` 열을 둔다.
  - src=nasdaq : 나스닥 일별 기록(시가·고가·저가·종가·거래량 그대로, 수정종가=종가)
  - src=filled : 나스닥 기록 사이의 빈 거래일(거래 없음) — 직전 종가 그대로, 거래량 0. 마지막 나스닥 기록 **뒤**는 채우지 않는다(수신 지연을 '무거래'로 가리지 않음 → 신선도 ⚠ 유지).
  - src=yahoo  : 나스닥 수신 실패 시 야후 전체(2차). 이 경우 파일은 야후 값 그대로 + src=yahoo.
전 종목 폴백(MM-STALE-FIX-20261011 §2b): 위 극저유동 선정과 별개로, **개별 3배 상품 전부**에 대해 야후 최신 봉이 SPY 기준일보다 오래됐거나(봉 없음) 마지막 행 Close 가 NaN 이면
  그 빠진 날짜의 봉만 나스닥 기록으로 보충한다(야후 기존 행은 그대로, 행마다 src 열: 기존 yahoo · 보충분 nasdaq). 나스닥에도 없으면 그대로 두어 ⚠ 가 남는다(→ 같은 날 10:15 재실행 잡).
점수(M-score)는 1x 만 쓴다 — 3배 일봉은 거래대금·무거래·신선도·표본 배지와 β/R² 품질에만 쓰인다. 1x·점수 계산 코드는 건드리지 않는다.
사용: mm_daily/mm_weekly_scan 이 fetch_all 직후 apply_after_fetch() 호출. 단독 시험: python3 scripts/mm_nasdaq.py --dry"""
import json, sys, time, datetime, urllib.error, urllib.parse, urllib.request
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"; LOCAL = ROOT / ".local"; FETCHED = LOCAL / "fetched"
LOW_VOL_THRESHOLD = 1000          # 20일 평균 거래량(주) 미만이면 나스닥 1차 (eligibility.yaml E6 '거래량 극소 부적격' 과 같은 값)
SHORT_HIST_BARS = 20              # 야후 이력이 상장일 대비 이만큼 이상 짧으면 나스닥 이력 수신 대상 (MM-THIN-ETN-HIST §1)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
URL = "https://api.nasdaq.com/api/quote/{t}/historical?assetclass={ac}&fromdate={f}&limit=9999&todate={to}"
COLS = ["Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends", "Stock Splits", "Capital Gains"]


def thin_excluded_tickers():
    """data/thin_excluded.json — 거래량 극소로 유니버스에서 뺐지만 복귀 판정을 위해 3배 일봉 수신은 계속하는 ETN (MM-FUNDTRACK-20261023 §3)."""
    try: return [x["ticker"] for x in json.load(open(DATA / "thin_excluded.json", encoding="utf-8")).get("items", []) if x.get("ticker")]
    except Exception: return []


def etn_tickers():
    u = pd.read_csv(DATA / "universe.csv")
    return list(dict.fromkeys(u[u["type"] == "ETN"].ticker.tolist() + thin_excluded_tickers()))


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


def first_bars(path=None):
    """{티커: 상장일 Timestamp} — data/product_info.csv first_bar (없으면 빈 dict)."""
    try:
        p = pd.read_csv(path or (DATA / "product_info.csv"), usecols=["ticker", "first_bar"])
        return {a: pd.Timestamp(b) for a, b in zip(p.ticker, p.first_bar) if isinstance(b, str) and b[:2] == "20"}
    except Exception:
        return {}


def select_short_history(frames, tickers, calendar, target, fbs, min_short=SHORT_HIST_BARS):
    """야후 이력이 상장일 대비 min_short 봉 이상 짧은 티커 목록. 기대 거래일 수 = 달력(SPY) 중 [상장일, target], 야후 봉 수 = 상장일 이후 Close 유효 봉."""
    cal = pd.DatetimeIndex(calendar); out = []
    for t in tickers:
        h = frames.get(t); fb = fbs.get(t)
        if h is None or fb is None or len(h) == 0: continue
        d = _et_dates(h.index); ok = h["Close"].notna().values
        n_y = int(((d >= fb) & ok).sum())
        exp = int(((cal >= fb) & (cal <= target)).sum())
        if exp - n_y >= min_short: out.append(t)
    return sorted(out)


def history_start(yh, fb):
    """나스닥 조회 시작일(포함 여유 10일): min(야후 첫 봉, 상장일) − 10일."""
    first_y = _et_dates(yh.index).min()
    first = min(first_y, fb) if fb is not None else first_y
    return (first - pd.Timedelta(days=10)).date().isoformat()


def yahoo_tail(yh, after):
    """야후 봉 중 날짜 > after 이고 거래량 > 0(실거래)인 행 → DataFrame(naive 날짜 인덱스, COLS + src=yahoo). 거래량 0 봉은 거래 없는 날 직전가 연장일 수 있어 잇지 않는다."""
    d = _et_dates(yh.index); v = pd.to_numeric(yh["Volume"], errors="coerce").values; c = yh["Close"].notna().values
    m = (d > after) & (v > 0) & c
    if not m.any(): return pd.DataFrame(columns=COLS + ["src"])
    out = yh.loc[m, [x for x in COLS if x in yh.columns]].copy()
    for x in COLS:
        if x not in out.columns: out[x] = 0.0
    out.index = d[m]; out["src"] = "yahoo"
    return out[COLS + ["src"]]


def build_history(t, yh, fb, calendar, opener=None, ac_list=("etf", "stocks"), force_replace=False):
    """티커 1개의 나스닥 이력 수신·결합 → (DataFrame(fetched 형식, src 열), 모드 'replace'|'merge', 요약 문자열). 실패 시 예외.
    replace(극저유동 — 20일 평균 거래량 < LOW_VOL_THRESHOLD, 나스닥 이력 기준 또는 force_replace): 나스닥(+사이 빈 거래일 filled) + 마지막 나스닥 기록 뒤 야후 실거래 봉.
    merge: 야후 행은 그대로(src=yahoo), 야후 첫 봉 이전 구간만 나스닥(+filled)으로 보충."""
    start = history_start(yh, fb); nd = None; err = None
    for ac in ac_list:
        try:
            rows = fetch_nasdaq(t, start, opener=opener, ac=ac); nd = parse_rows(rows)
            if len(nd) == 0: raise ValueError("파싱된 행 0")
            if len(nd) < len(rows) * 0.9: raise ValueError(f"파싱 실패 다수 {len(rows) - len(nd)}/{len(rows)}")
            break
        except Exception as e:
            err = e; nd = None
    if nd is None: raise err or ValueError("나스닥 수신 실패")
    nd = fill_gaps(nd, calendar)
    vol20 = avg_volume20(nd)
    mode = "replace" if (force_replace or vol20 < LOW_VOL_THRESHOLD) else "merge"
    if mode == "replace":
        out = pd.concat([nd, yahoo_tail(yh, nd.index.max())]).sort_index()
    else:
        ydates = _et_dates(yh.index); first_y = ydates.min()
        y = yh.copy(); y.index = ydates
        if "src" not in y.columns: y["src"] = "yahoo"
        y = y[[x for x in COLS if x in y.columns] + ["src"]]
        for x in COLS:
            if x not in y.columns: y[x] = float("nan")
        y = y[COLS + ["src"]]
        out = pd.concat([nd[nd.index < first_y], y]).sort_index()
    out = to_fetched_format(out)
    return out, mode, f"{mode} {len(out)}봉 ({_et_dates(out.index).min().date()}~{_et_dates(out.index).max().date()}, 시작조회 {start}, 20일 평균 거래량 {vol20:.0f})"


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


def fetch_nasdaq(t, since, opener=None, retries=3, ac="etf"):
    """나스닥 일별 기록 → rows(list). 실패 시 예외."""
    url = URL.format(t=urllib.parse.quote(t), ac=ac, f=since, to=(datetime.date.today() + datetime.timedelta(days=1)).isoformat())
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


def three_x_tickers():
    return list(dict.fromkeys(pd.read_csv(DATA / "universe.csv").ticker.tolist() + thin_excluded_tickers()))


def _et_dates(index):
    return pd.to_datetime(index, utc=True).tz_convert("America/New_York").tz_localize(None).normalize()


def fallback_missing_bars(log=print, write=True, opener=None, fetched=None, tickers=None, calendar=None, target=None):
    """개별 3배 상품 전부: 야후 마지막 유효 봉(Close 非NaN) < 기준일(SPY 마지막 날짜)이면 빠진 날짜만 나스닥 기록으로 보충. 반환 {티커: 상태}."""
    fetched = Path(fetched or FETCHED); res = {}
    tickers = tickers or three_x_tickers()
    cal = calendar
    if cal is None and target is None:
        spy = pd.read_csv(fetched / "SPY.csv", index_col=0); cal = _et_dates(spy.index)
    target = pd.Timestamp(target).normalize() if target is not None else pd.DatetimeIndex(cal).max()
    for t in tickers:
        p = fetched / f"{t}.csv"
        if not p.exists(): continue
        h = pd.read_csv(p, index_col=0)
        if "src" in h.columns and (h["src"] == "nasdaq").any(): continue          # 극저유동 교체본 — 이미 나스닥 1차
        d = _et_dates(h.index); valid = h["Close"].notna().values
        if not valid.any(): continue
        last_valid = d[valid].max()
        if last_valid >= target: continue
        why = "봉 없음" if d.max() < target else "Close NaN"
        try:
            nd = None; err = None
            for ac in ("etf", "stocks"):                                          # ETN 은 분류가 다를 수 있어 etf → stocks 순
                try:
                    rows = fetch_nasdaq(t, (last_valid - pd.Timedelta(days=10)).date().isoformat(), opener=opener, ac=ac)
                    nd = parse_rows(rows)
                    if len(nd): break
                except Exception as e: err = e
            if nd is None or len(nd) == 0: raise err or ValueError("파싱된 행 0")
            add = nd[(nd.index > last_valid) & (nd.index <= target)]
            if len(add) == 0:
                res[t] = f"보충 불가({why}) — 나스닥에 {last_valid.date()} 이후 기록 없음"
                log(f"[mm_nasdaq] {t} 야후 {why}(마지막 유효 {last_valid.date()} < 기준일 {target.date()}) · 나스닥에도 기록 없음 → ⚠ 유지")
                try:
                    sys.path.insert(0, str(Path(__file__).resolve().parent)); import mm_lib; mm_lib.log(f"[mm_nasdaq] {t} {why} · 나스닥 보충 불가 → ⚠ 유지", "alerts")
                except Exception: pass
                continue
            keep = h[~(d > last_valid)].copy()                                    # Close NaN 행 포함 마지막 유효 봉 뒤는 버리고 나스닥 값으로
            if "src" not in keep.columns: keep["src"] = "yahoo"
            out = pd.concat([keep, _to_cols(add, keep.columns)])
            if write: out.to_csv(p)
            res[t] = f"야후 {why} → 나스닥 {len(add)}봉 보충 ({', '.join(str(x.date()) for x in add.index)})"
        except Exception as e:
            res[t] = f"보충 실패({why}): {type(e).__name__}: {str(e)[:150]}"
            log(f"[mm_nasdaq] {t} 나스닥 보충 실패 → ⚠ 유지: {type(e).__name__}: {str(e)[:200]}")
        time.sleep(0.3)
    for t, s_ in res.items(): log(f"[mm_nasdaq] {t}: {s_}")
    return res


def fallback_spy(log=print, write=True, opener=None, fetched=None, expected=None):
    """MM-FEED-LAG-FIX 후속 §1: 기준일 판정용 SPY 의 마지막 유효 봉(Close 非NaN)이 '직전 US 거래일'(expected)보다 오래됐으면(봉 없음·Close NaN) 나스닥 일별 기록으로 보충.
    나스닥에도 없으면 파일 무변경(→ clean_all 이 직전 확정일로 후퇴·잠정 처리, 경보는 일일 가드가 낸다). 반환 {'SPY': 상태} (보충 필요 없으면 {})."""
    fetched = Path(fetched or FETCHED)
    if not (fetched / "SPY.csv").exists(): return {}
    if expected is None:
        sys.path.insert(0, str(Path(__file__).resolve().parent)); import mm_lib; expected = mm_lib.prev_us_session()
    return fallback_missing_bars(log, write=write, opener=opener, fetched=fetched, tickers=["SPY"], target=expected)


def _to_cols(add, columns):
    """나스닥 보충분을 fetched 파일 인덱스 형식(ET tz)·열 순서로."""
    out = add.copy(); out.index = out.index.tz_localize("America/New_York"); out.index.name = "Date"
    for c in columns:
        if c not in out.columns: out[c] = float("nan")
    return out[list(columns)]


# ---------- 중간 결손 보충 (MM-GAPFILL-20261024) ----------
GAP_WINDOW = 260                  # 최근 NYSE 거래일 수 — 이 창 안에서 봉이 없거나 Close 가 NaN 인 날짜를 나스닥 일별 기록으로 채운다
GAP_SRC = "nasdaq_gap"


def gap_tickers():
    """중간 결손 점검 대상 = 유니버스 3배 상품 + 1x ETF(실제 티커만, 합성 키 제외) + 스플라이스 후반 ETF + SPY + 거래량 극소 제외 종목(3배)."""
    u = pd.read_csv(DATA / "universe.csv")
    out = list(u.ticker) + [p for p in u.proxy.dropna() if not str(p).startswith("IDX_") and not str(p).endswith("_1X")]
    try:
        sp = json.load(open(DATA / "proxy_specs.json", encoding="utf-8"))["specs"]
        out += [v["then"]["ticker"] for v in sp.values() if v.get("kind") == "splice"] + [v["ticker"] for v in sp.values() if v.get("kind") == "yahoo"]
    except Exception:
        pass
    out += ["SPY"] + thin_excluded_tickers()
    return list(dict.fromkeys(out))


def nyse_sessions(target, n=GAP_WINDOW):
    """target 이하 마지막 n 개 NYSE 거래일(naive Timestamp 인덱스, 오름차순)."""
    import pandas_market_calendars as pmc
    target = pd.Timestamp(target).normalize()
    sch = pmc.get_calendar("NYSE").schedule(start_date=(target - pd.Timedelta(days=int(n * 1.6) + 30)).date(), end_date=target.date())
    return pd.DatetimeIndex(sch.index).tz_localize(None).normalize()[-n:]


def find_mid_gaps(h, sessions):
    """h(fetched 프레임) 의 최근 창 중간 결손 날짜 — sessions 중 [첫 유효 봉, 마지막 유효 봉] 안에서 봉이 없거나 Close NaN 인 날. 마지막 유효 봉 뒤(꼬리)는 fallback_missing_bars 소관이라 제외."""
    d = _et_dates(h.index); valid = h["Close"].notna().values
    if not valid.any(): return []
    vd = set(d[valid]); lo, hi = min(vd), max(vd)
    return [x for x in pd.DatetimeIndex(sessions) if lo <= x <= hi and x not in vd]


def fallback_mid_gaps(log=print, write=True, opener=None, fetched=None, tickers=None, sessions=None, target=None):
    """야후 일봉의 '중간' 결손(최근 GAP_WINDOW 거래일 중 NYSE 거래일인데 봉이 없거나 Close NaN)을 나스닥 일별 기록으로 채운다(src=nasdaq_gap).
    나스닥에도 없으면 비워 둔다. 반환 {티커: {'filled': [날짜], 'unfilled': [날짜]}} — 결손이 있었던 티커만. 점수 산식·피처 코드는 건드리지 않는다."""
    fetched = Path(fetched or FETCHED); res = {}
    tickers = tickers or gap_tickers()
    if sessions is None:
        if target is None:
            spy = pd.read_csv(fetched / "SPY.csv", index_col=0); v = spy["Close"].notna().values
            target = _et_dates(spy.index)[v].max()
        sessions = nyse_sessions(target)
    for t in tickers:
        p = fetched / f"{t}.csv"
        if not p.exists(): continue
        try:
            h = pd.read_csv(p, index_col=0)
            gaps = find_mid_gaps(h, sessions)
            if not gaps: continue
            nd = None; err = None
            for ac in ("etf", "stocks"):
                try:
                    nd = parse_rows(fetch_nasdaq(t, (min(gaps) - pd.Timedelta(days=7)).date().isoformat(), opener=opener, ac=ac))
                    if len(nd) and nd.index.isin(gaps).any(): break
                except Exception as e: err = e
            add = nd[nd.index.isin(gaps)] if nd is not None and len(nd) else pd.DataFrame(columns=COLS + ["src"])
            got = [x for x in gaps if x in add.index]; miss = [x for x in gaps if x not in add.index]
            if len(add):
                add = add.copy(); add["src"] = GAP_SRC
                keep = h[~pd.Series(_et_dates(h.index)).isin(add.index).values].copy()          # 같은 날짜의 Close NaN 행은 나스닥 값으로 교체
                if "src" not in keep.columns: keep["src"] = ""
                keep.index = pd.to_datetime(keep.index, utc=True).tz_convert("America/New_York")
                out = pd.concat([keep, _to_cols(add, keep.columns)]).sort_index(); out.index.name = "Date"
                if write: out.to_csv(p)
            res[t] = dict(filled=got, unfilled=miss)
            if got: log(f"[mm_nasdaq] {t} 야후 중간 결손 {len(got)}봉 → 나스닥 보충({', '.join(str(x.date()) for x in got)})")
            if miss: log(f"[mm_nasdaq] {t} 야후 중간 결손 {len(miss)}봉 — 나스닥에도 없음({', '.join(str(x.date()) for x in miss)}){'' if err is None else ' · ' + type(err).__name__}")
        except Exception as e:
            log(f"[mm_nasdaq] {t} 중간 결손 점검 실패(건너뜀): {type(e).__name__}: {str(e)[:150]}")
        if t in res and res[t]["filled"]: time.sleep(0.3)
    return res


def alert_unfilled(res, state_path=None, send=True):
    """나스닥에도 없는 중간 결손을 경보 1줄로(종목·날짜) — 같은 (종목, 날짜)는 한 번만(상태 파일). send=False 면 alerts.log 만. 반환 새로 알린 [(티커, 날짜)]."""
    sp = Path(state_path or (LOCAL / "gap_alert_state.json"))
    try: seen = set(json.load(open(sp, encoding="utf-8")))
    except Exception: seen = set()
    new = [(t, str(x.date())) for t, v in sorted(res.items()) for x in v.get("unfilled", []) if f"{t}:{x.date()}" not in seen]
    if not new: return []
    by = {}
    for t, d in new: by.setdefault(t, []).append(d[5:])
    msg = "[mm_rotation] 야후 중간 결손 봉 보충 불가(나스닥에도 없음): " + ", ".join(f"{t}({' '.join(ds)})" for t, ds in by.items())
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent)); import mm_lib
        if send and "--no-alert" not in sys.argv: mm_lib.alert(msg)
        else: mm_lib.log(msg, "alerts")
    except Exception: pass
    try:
        sp.parent.mkdir(parents=True, exist_ok=True)
        json.dump(sorted(seen | {f"{t}:{d}" for t, d in new}), open(sp, "w", encoding="utf-8"))
    except Exception: pass
    return new


def apply_after_fetch(log=print, write=True, opener=None, fetched=None, tickers=None, calendar=None, three_x=None, expected=None, first_bar_map=None, gap_fill=None):
    """수신 직후 호출. 반환 {선정 티커: 상태 문자열}. 어떤 실패도 예외로 올리지 않는다(야후 값 유지 + src=yahoo)."""
    fetched = Path(fetched or FETCHED); res = {}
    try:                                                                           # SPY 기준일 폴백 (MM-FEED-LAG-FIX 후속 §1) — 3배 폴백이 SPY 마지막 날짜를 목표로 삼으므로 가장 먼저
        if expected is not None or calendar is None:         # calendar 만 직접 준 호출(합성 환경)은 직전 US 거래일을 알 수 없으므로 건너뜀
            res.update({f"{k}(SPY 폴백)": v for k, v in fallback_spy(log, write=write, opener=opener, fetched=fetched, expected=expected).items()})
    except Exception as e:
        log(f"[mm_nasdaq] SPY 폴백 건너뜀: {type(e).__name__}: {str(e)[:200]}")
    try:
        tickers = tickers or etn_tickers()
        three = three_x if three_x is not None else three_x_tickers()
        frames = {}
        for t in dict.fromkeys(list(tickers) + list(three)):
            p = fetched / f"{t}.csv"
            if p.exists():
                h = pd.read_csv(p, index_col=0)
                if "src" in h.columns and (h["src"] == "nasdaq").any():          # 직전 실행이 나스닥으로 바꾼 파일 — 야후 값으로 판정하려면 새로 받은 야후여야 한다
                    continue
                frames[t] = h
        sel = select_low_volume({t: frames[t] for t in tickers if t in frames}, tickers)
        log(f"[mm_nasdaq] 극저유동 ETN(야후 20일 평균 거래량 < {LOW_VOL_THRESHOLD}) {sel}")
        cal = calendar
        if cal is None:
            spy = pd.read_csv(fetched / "SPY.csv", index_col=0)
            cal = pd.to_datetime(spy.index, utc=True).tz_convert("America/New_York").tz_localize(None).normalize()
        fbs = first_bars() if first_bar_map is None else first_bar_map
        short = []
        try:                                                                       # 야후 이력이 상장일 대비 짧은 3배 상품 (MM-THIN-ETN-HIST §1)
            short = select_short_history({t: frames[t] for t in three if t in frames}, three, cal, pd.DatetimeIndex(cal).max(), fbs)
        except Exception as e:
            log(f"[mm_nasdaq] 이력 길이 점검 건너뜀: {type(e).__name__}: {str(e)[:150]}")
        log(f"[mm_nasdaq] 야후 이력 짧음(상장일 대비 ≥ {SHORT_HIST_BARS}봉) {short}")
        for t in sorted(set(sel) | set(short)):
            yh = frames[t]
            try:
                out, mode, summ = build_history(t, yh, fbs.get(t), cal, opener=opener, force_replace=(t in sel))
                if write: out.to_csv(fetched / f"{t}.csv")
                res[t] = ("nasdaq " if mode == "replace" else "nasdaq-보충 ") + summ
            except Exception as e:
                res[t] = f"yahoo(2차) — 나스닥 실패: {type(e).__name__}: {str(e)[:150]}"
                log(f"[mm_nasdaq] {t} 나스닥 수신 실패 → 야후 값 유지: {type(e).__name__}: {str(e)[:200]}")
                if write:
                    y = yh.copy(); y["src"] = "yahoo"; y.to_csv(fetched / f"{t}.csv")
                try:                                                                       # 실패를 눈에 띄게(경보 로그)
                    sys.path.insert(0, str(Path(__file__).resolve().parent)); import mm_lib; mm_lib.log(f"[mm_nasdaq] {t} 나스닥 수신 실패 → 야후 사용: {type(e).__name__}: {str(e)[:200]}", "alerts")
                except Exception: pass
            time.sleep(0.3)
        for t, s_ in res.items(): log(f"[mm_nasdaq] {t}: {s_}")
    except Exception as e:
        log(f"[mm_nasdaq] 건너뜀(야후 값 유지): {type(e).__name__}: {str(e)[:200]}")
    try:                                                                           # 전 종목 폴백 (MM-STALE-FIX-20261011 §2b)
        res.update({f"{k}(폴백)": v for k, v in fallback_missing_bars(log, write=write, opener=opener, fetched=fetched, tickers=three_x, calendar=calendar).items()})
    except Exception as e:
        log(f"[mm_nasdaq] 폴백 건너뜀: {type(e).__name__}: {str(e)[:200]}")
    if gap_fill is None: gap_fill = (fetched == FETCHED)                           # 합성 환경(테스트)에서는 명시했을 때만
    if gap_fill:
        try:                                                                       # 중간 결손 보충 (MM-GAPFILL-20261024) — 1x ETF·3배·SPY 모두
            g = fallback_mid_gaps(log, write=write, opener=opener, fetched=fetched)
            for t, v in g.items():
                res[f"{t}(중간결손)"] = f"나스닥 보충 {len(v['filled'])}봉" + (f" · 나스닥에도 없음 {len(v['unfilled'])}봉" if v["unfilled"] else "")
            alert_unfilled(g)
        except Exception as e:
            log(f"[mm_nasdaq] 중간 결손 보충 건너뜀: {type(e).__name__}: {str(e)[:200]}")
    return res


if __name__ == "__main__":
    print(json.dumps(apply_after_fetch(write="--dry" not in sys.argv), ensure_ascii=False, indent=1))
