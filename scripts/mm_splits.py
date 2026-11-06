"""[MM-SPLIT-GUARD-20261106] 1x 대용 ETF 액면분할 반영 시차 가드 (SOXX·ITA 2026-11-05 3:1 사고 수리).

사고: 야후가 분할 조정을 시간차로 반영해 1x 이력이 한동안 「조정 전 450 → 분할 후 131.9」(−70.7%) 또는 「조정된 157 → 미조정 453」(+188%)으로 어긋났고,
SOXL·DFEN 이 이상봉 ⚠ 으로 제외됐다(08:18·10:19 판). 14:10 에 야후가 전 이력을 맞추자 정상.

방침(오너 지시 2026-11-06): 이력을 직접 1/f 로 나누지 않는다(야후가 뒤늦게 조정하면 이중 조정). 대신
  ① 분할 이벤트(야후 `Stock Splits` 열 · 나스닥 분할 캘린더) 주변의 이상봉이 「분할 배율 × (3배 일간수익률÷3 기대 1x 수익률)」과 맞는지 본다.
     원 가격비 × f ≈ 1 만 보면 분할일 당일의 실제 등락(SOXX −12%)에 걸려 놓친다 → 기대 수익률은 3배 ETF 의 같은 날 수익률÷3 로 추정한다(오차 허용 TOL).
  ② 맞으면 그 봉부터 끝까지의 1x 행을 이번 실행의 RAW 에서 제외하고(원본 FETCHED 는 불변), 이어지는 mm_tailetn.fill 이 3배÷3 로 최대 3거래일을 메운다 = 「분할 반영 대기」.
  ③ 다음 실행에서 이력이 일관(이상봉 0)이면 아티팩트가 검출되지 않아 정상 경로로 복귀한다. 상태 저장 없음(매 실행 재판정).
표시 전용 정보는 .local/split_pending.json 에 기록한다. 점수 산식·적격 규칙은 불변."""
import json, re, urllib.request
from pathlib import Path
import numpy as np, pandas as pd

TOL = 0.05            # 원 가격비 ÷ (분할 배율 × 기대 1x 비율) − 1 허용 오차 (3배÷3 근사 오차 흡수)
GROSS = 0.25          # 이 이상 |일간수익률| 인 봉만 아티팩트 후보 (eligibility.yaml anomaly.one_x 와 같은 값)
LOOKBACK = 10         # 분할일 전후 이 달력일 안의 봉만 후보
NASDAQ_URL = "https://api.nasdaq.com/api/calendar/splits?date={d}"
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
MULT = 3.0


def parse_ratio(s):
    """'3:1' · '3 : 1' → 3.0 (분할 후 주식 수 배율 f) · '1 : 2'(역분할) → 0.5. 실패 → None."""
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*$", str(s or ""))
    if not m: return None
    a, b = float(m.group(1)), float(m.group(2))
    return a / b if a > 0 and b > 0 else None


def nasdaq_calendar(day, fetch=None, timeout=25):
    """나스닥 분할 캘린더(date=day 기준 이후 예정·최근 전체) → [{symbol,f,date(Timestamp),name,ratio}]. 실패 → [] (가드는 야후 Stock Splits 만으로도 동작)."""
    try:
        if fetch is None:
            req = urllib.request.Request(NASDAQ_URL.format(d=pd.Timestamp(day).strftime("%Y-%m-%d")), headers=UA)
            raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
        else:
            raw = fetch(day)
        rows = (json.loads(raw).get("data") or {}).get("rows") or []
    except Exception:
        return []
    out = []
    for r in rows:
        f = parse_ratio(r.get("ratio"));
        try: d = pd.Timestamp(pd.to_datetime(r.get("executionDate"), format="%m/%d/%Y"))
        except Exception: d = None
        if f and d is not None and r.get("symbol"):
            out.append(dict(symbol=str(r["symbol"]).upper(), f=f, date=d.normalize(), name=r.get("name"), ratio=r.get("ratio")))
    return out


def yf_split_events(h):
    """원본 이력 DataFrame 의 `Stock Splits` 열 → [(Timestamp, f)]"""
    if "Stock Splits" not in h.columns: return []
    s = pd.to_numeric(h["Stock Splits"], errors="coerce").fillna(0.0)
    idx = pd.DatetimeIndex(s.index).tz_localize(None).normalize() if getattr(s.index, "tz", None) is not None else pd.DatetimeIndex(s.index).normalize()
    return [(d, float(v)) for d, v in zip(idx, s.values) if v and v > 0 and v != 1.0]


def detect(c1, c3, events, tol=TOL, gross=GROSS, lookback=LOOKBACK):
    """c1 = 1x Close(일 단위 Series), c3 = 같은 상품군 3배 Close, events = [(분할일, f)].
    반환 [{date, raw, g, f, split_date, err}] — 각 봉 d 의 원 비율 raw = c1[d]/c1[prev] 가
    g × (1 + r3/3) 와 tol 안으로 맞는 g ∈ {1/f, f} 가 있고 |raw−1| ≥ gross 이며 분할일 ±lookback 달력일 안인 봉."""
    out = []
    if not events or len(c1) < 3: return out
    dates = list(c1.index)
    for k in range(1, len(dates)):
        d, p = dates[k], dates[k - 1]
        raw = float(c1.iloc[k] / c1.iloc[k - 1])
        if abs(raw - 1.0) < gross: continue
        if d not in c3.index or p not in c3.index: continue
        exp = 1.0 + (float(c3.loc[d]) / float(c3.loc[p]) - 1.0) / MULT
        if not (exp > 0.05): continue
        best = None
        for sd, f in events:
            if abs((d - sd).days) > lookback: continue
            for g in (1.0 / f, f):
                err = abs(raw / (g * exp) - 1.0)
                if err <= tol and (best is None or err < best["err"]):
                    best = dict(date=d, raw=round(raw, 6), g=round(g, 6), f=f, split_date=sd, err=round(err, 5))
        if best: out.append(best)
    return out


def guard(T, uni, raw_dir, log=print, write=True, cal_events=None, info_path=None):
    """RAW 1x 시계열의 분할 아티팩트 봉부터 끝까지를 제외한다(RAW 만 — FETCHED 불변). 반환 {proxy: 정보}.
    mm_tailetn.fill 보다 먼저 호출해야 제외된 구간이 3배÷3 로 채워진다(최대 MAX_GAP=3거래일, 넘으면 fill 이 over_max ⚠ 유지)."""
    import mm_tailetn as TN
    raw_dir = Path(raw_dir); info = {}
    cal_events = cal_events or {}
    for px, grp in uni.groupby("proxy", sort=False):
        p = raw_dir / f"{px}.csv"
        if not p.exists(): continue
        try:
            h1 = TN._rd(p); c1 = TN._close_by_day(h1)
        except Exception as e:
            log(f"[mm_splits] {px}: 이력 읽기 실패(건너뜀): {type(e).__name__}"); continue
        ev = list(yf_split_events(h1)) + [(e["date"], e["f"]) for e in cal_events.get(px, [])]
        ev = sorted(set((pd.Timestamp(d).normalize(), round(f, 8)) for d, f in ev))
        if not ev: continue
        best3 = None
        for t3 in grp.ticker:
            q = raw_dir / f"{t3}.csv"
            if not q.exists(): continue
            try: h3 = TN._rd(q)
            except Exception: continue
            a = TN._adtv20(h3)
            if best3 is None or a > best3[0]: best3 = (a, t3, TN._close_by_day(h3))
        if best3 is None: continue
        arts = detect(c1[c1.index <= pd.Timestamp(T).normalize()], best3[2], ev)
        if not arts: continue
        k0 = arts[0]["date"]
        keep = TN._days(h1.index) < k0
        dropped = int((~keep).sum())
        rec = dict(status="split_pending", split=f"{arts[0]['f']:g}:1", split_date=str(arts[0]["split_date"].date()), artifact_dates=[str(a["date"].date()) for a in arts],
                   raw=[a["raw"] for a in arts], err=[a["err"] for a in arts], dropped_rows=dropped, via=best3[1], members=list(grp.ticker))
        if write:
            out = h1[keep].copy(); out.index.name = "Date"; out.to_csv(p)
        info[px] = rec
        log(f"[mm_splits] {px}: 분할 반영 대기 — {rec['split']} (분할일 {rec['split_date']}) 아티팩트 봉 {rec['artifact_dates']} (원 비율 {rec['raw']}, 3배({best3[1]})÷3 기대 대비 오차 {rec['err']}) → 해당 봉부터 {dropped}행 제외, 이후 3배÷3 보정")
    if info_path is not None and write:
        Path(info_path).write_text(json.dumps(dict(T=str(pd.Timestamp(T).date()), proxies=info), ensure_ascii=False, indent=1), encoding="utf-8")
    return info


def annotate(df, info):
    """분할 반영 대기 proxy 를 쓰는 종목의 reason 에 한 줄 표시 (점수·순위 불변)."""
    for px, rec in (info or {}).items():
        note = f" [분할 반영 대기: {px} {rec['split']} ({rec['split_date']}) → 3배÷3 보정]"
        m = df.ticker.isin(rec["members"])
        df.loc[m, "reason"] = df.loc[m, "reason"].fillna("").astype(str) + note
    return df
