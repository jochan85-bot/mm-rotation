"""종목 페이지 가격 차트 데이터 — docs/data/charts/<티커>.json (유니버스 3배 상품 자체의 일봉 OHLC, 분할·병합 조정, 상장 첫 봉 ~ 기준일).
원천 = 일일 산출이 이미 받는 야후 일봉의 정제본 `.local/p0view/data/<티커>.csv`(clean_all 이후 — 미확정 봉 제외, 기준일까지).
야후 Open/High/Low/Close(auto_adjust=False)는 분할·병합만 조정되고 배당은 조정되지 않은 값이다. 지수·1배 대용으로 대체하지 않는다.
추가 수신 0 — 새 네트워크 경로는 분할 캘린더 조회 1회(mm_splits.nasdaq_calendar, 실패해도 계속)뿐이다.

형식(열 배열, 소수 5자리 유효숫자): {"t","v","d0","dt":[첫 봉 0, 이후 직전 봉과의 달력일 차],"o","h","l","c"}. 거래량은 싣지 않는다.
일일 갱신(mm_daily 말미 후단 훅, 점수·순위·기존 데이터 무접촉): 기존 파일의 마지막 봉 뒤 새 봉만 덧붙이고 마지막 RECHECK 봉을 원천과 다시 대조한다.
  · 대조 봉이 분할 배율만큼 일정하게 어긋남(야후가 이력을 다시 조정) → 그 종목 전체 재생성 + alerts 1줄
  · 새 봉이 분할 이벤트 ±10일 안에서 분할 배율로 설명되는 점프(조정 전 이력 + 분할 후 봉) → 그 종목 갱신 보류(기존 파일 유지) + alerts 1줄 = 침묵 오염 금지
  · 그 밖의 대조 불일치·날짜 삽입/삭제 → 원천으로 전체 재생성(로그 1줄)
실패는 종목 단위로 격리하고, 훅 전체 실패도 일일 발행을 막지 않는다(mm_daily 쪽 try/except).
표시 보정(시세 오류 봉): data/chart_overrides.yaml 목록을 종목 페이지가 그리기 직전에만 적용한다 — 이 모듈이 쓰는 차트 JSON 은 원천 그대로다.
  active_overrides()(원값 일치 확인) → mm_site 가 페이지에 싣고, pricechart.js 가 같은 규칙으로 적용한다(clip = clip_bar() 로 자름, set = 두 번째 소스 정상값으로 교체).
사용: python3 scripts/mm_charts.py --build | --update | --check | --scan   [--src DIR] [--out DIR] [--no-calendar]"""
import sys, json, math, argparse, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"; LOCAL = ROOT / ".local"
SRC = LOCAL / "p0view" / "data"
OUT = ROOT / "docs" / "data" / "charts"
VER = 1
RECHECK = 10          # 갱신 때 원천과 다시 대조하는 기존 마지막 봉 수
TOL = 2e-4            # 대조 허용 상대오차(반올림 5자리 유효숫자 흡수)
GROSS = 0.25          # 분할 아티팩트 후보 최소 |일간 변화| (mm_splits.GROSS 와 같은 값)
SPLIT_TOL = 0.05      # 원 비율 × 배율 ≈ 1 허용 오차
LOOKBACK = 10         # 분할일 ± 달력일


def q(x):
    """유효숫자 5자리(소수 최소 2자리)로 반올림 — 0.6425 → 0.6425, 56.0600014 → 56.06, 1234.567 → 1234.57"""
    x = float(x)
    if not math.isfinite(x) or x <= 0: return None
    d = max(2, min(8, 4 - int(math.floor(math.log10(x)))))
    return round(x, d)


def universe():
    return list(pd.read_csv(DATA / "universe.csv").ticker)


def read_src(t, src=None):
    """원천 CSV → (OHLC DataFrame[날짜 index, o,h,l,c 반올림], 분할 이벤트 [(날짜, f)], 정리 건수)"""
    p = Path(src or SRC) / f"{t}.csv"
    h = pd.read_csv(p, index_col=0)
    h.index = pd.to_datetime(h.index, utc=True).tz_convert("America/New_York").tz_localize(None).normalize()
    h = h[~h.index.duplicated(keep="last")].sort_index()
    ev = []
    if "Stock Splits" in h.columns:
        s = pd.to_numeric(h["Stock Splits"], errors="coerce").fillna(0.0)
        ev = [(d, float(v)) for d, v in s.items() if v > 0 and v != 1.0]
    c = pd.to_numeric(h["Close"], errors="coerce")
    h = h[c.notna() & (c > 0)]
    o, hi, lo, c = (pd.to_numeric(h[k], errors="coerce") for k in ("Open", "High", "Low", "Close"))
    fix = int(((o.isna()) | (o <= 0) | hi.isna() | (hi <= 0) | lo.isna() | (lo <= 0)).sum())
    o = o.where(o > 0, c); hi = hi.where(hi > 0, c); lo = lo.where(lo > 0, c)        # 빈 시가·고가·저가 → 종가(거래 1건 봉 등)
    hi2 = pd.concat([hi, o, c], axis=1).max(axis=1); lo2 = pd.concat([lo, o, c], axis=1).min(axis=1)   # 고가 ≥ max(시,종), 저가 ≤ min(시,종)
    fix += int(((hi2 != hi) | (lo2 != lo)).sum())
    df = pd.DataFrame({"o": o.map(q), "h": hi2.map(q), "l": lo2.map(q), "c": c.map(q)}, index=h.index)
    return df, ev, fix


def to_obj(t, df):
    d = list(df.index); dt = [0] + [int((d[i] - d[i - 1]).days) for i in range(1, len(d))]
    return {"t": t, "v": VER, "d0": str(d[0].date()), "dt": dt, "o": df.o.tolist(), "h": df.h.tolist(), "l": df.l.tolist(), "c": df.c.tolist()}


def from_obj(j):
    d = pd.Timestamp(j["d0"]) + pd.to_timedelta(np.cumsum(j["dt"]), unit="D")
    return pd.DataFrame({"o": j["o"], "h": j["h"], "l": j["l"], "c": j["c"]}, index=pd.DatetimeIndex(d))


def dump(obj, path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    tmp = path.with_suffix(".json.tmp"); tmp.write_text(s, encoding="utf-8"); tmp.replace(path)
    return len(s.encode("utf-8"))


def artifacts(c, events, start=None):
    """분할 이벤트 ±LOOKBACK 일 안의 봉 중 원 비율 r 이 |r−1| ≥ GROSS 이고 r×f 또는 r÷f 가 1 ± SPLIT_TOL 인 봉 = 분할 미반영(또는 이중 반영) 의심.
    start 가 있으면 그 날짜 이후 봉만 본다. 반환 [{date, r, f}]"""
    out = []
    if not events or len(c) < 2: return out
    r = (c / c.shift(1)).dropna()
    if start is not None: r = r[r.index > start]
    for d, x in r.items():
        if abs(x - 1.0) < GROSS: continue
        for sd, f in events:
            if abs((d - pd.Timestamp(sd)).days) > LOOKBACK: continue
            if abs(x * f - 1.0) <= SPLIT_TOL or abs(x / f - 1.0) <= SPLIT_TOL:
                out.append(dict(date=str(d.date()), r=round(float(x), 5), f=f)); break
    return out


def split_ratio(old, new):
    """대조 구간의 종가 비율 old/new 가 일정(±1%)하고 1 이 아니면 그 비율, 아니면 None"""
    k = (old / new).dropna()
    if not len(k): return None
    m = float(k.median())
    if abs(m - 1.0) < 0.02 or (k / m - 1.0).abs().max() > 0.01: return None
    return m


def update_one(t, src=None, out=None, cal_events=None, full=False):
    """한 종목 갱신. 반환 dict(status, added, bars, bytes, note). status ∈ new·rebuilt·appended·same·held."""
    out = Path(out or OUT); path = out / f"{t}.json"
    df, ev, fix = read_src(t, src)
    ev = sorted(set((pd.Timestamp(d).normalize(), round(float(f), 8)) for d, f in list(ev) + list((cal_events or {}).get(t, []))))
    old = None
    if path.exists() and not full:
        try:
            j = json.loads(path.read_text(encoding="utf-8"))
            if j.get("v") == VER and j.get("t") == t: old = from_obj(j)
        except Exception:
            old = None
    if old is None:                                                     # 최초 생성 또는 형식 변경 → 전체(분할 미반영 봉이 있으면 쓰지 않는다)
        a = artifacts(df.c, ev)
        if a: return dict(status="held", added=0, bars=len(df), bytes=0, note=f"분할 미반영 의심 {a[:3]} — 파일 미작성")
        return dict(status="new" if not path.exists() else "rebuilt", added=len(df), bars=len(df), bytes=dump(to_obj(t, df), path), note=f"정리 {fix}봉" if fix else "")
    last = old.index[-1]
    tail_old = old.iloc[-RECHECK:]
    head_src = df[df.index <= last]
    same_dates = head_src.index.equals(old.index)
    chk = df.reindex(tail_old.index)
    rel = ((chk[["o", "h", "l", "c"]] - tail_old[["o", "h", "l", "c"]]).abs() / tail_old[["o", "h", "l", "c"]]).max(axis=1)
    bad = rel.isna() | (rel > TOL)
    new = df[df.index > last]
    if bad.any():
        f = split_ratio(tail_old.c, chk.c)
        a = artifacts(df.c, ev)
        if a: return dict(status="held", added=0, bars=len(old), bytes=path.stat().st_size, note=f"대조 불일치 + 분할 미반영 의심 {a[:3]} — 기존 파일 유지")
        why = (f"이력 재조정 감지(기존/원천 종가 비 {f:.4g}) — 전체 재생성" if f else f"마지막 {RECHECK}봉 대조 불일치 {int(bad.sum())}봉(최대 상대차 {float(rel.max()):.3g}) — 원천으로 전체 재생성")
        return dict(status="rebuilt", added=len(new), bars=len(df), bytes=dump(to_obj(t, df), path), note=why, split=bool(f))
    if not same_dates:
        return dict(status="rebuilt", added=len(new), bars=len(df), bytes=dump(to_obj(t, df), path), note="날짜 구성 변경(봉 삽입·삭제) — 원천으로 전체 재생성")
    if not len(new):
        return dict(status="same", added=0, bars=len(old), bytes=path.stat().st_size, note="")
    a = artifacts(pd.concat([old.c, new.c]), ev, start=last)
    if a: return dict(status="held", added=0, bars=len(old), bytes=path.stat().st_size, note=f"새 봉 분할 미반영 의심 {a[:3]} — 갱신 보류(기존 파일 유지)")
    merged = pd.concat([old, new])
    return dict(status="appended", added=len(new), bars=len(merged), bytes=dump(to_obj(t, merged), path), note="")


OVR = DATA / "chart_overrides.yaml"
OVR_FIELDS = {"low": "l", "high": "h"}                                  # mode clip(기본): 고가·저가를 시가·종가 범위로 자름
SET_FIELDS = {"open": "o", "high": "h", "low": "l", "close": "c"}       # mode set: 두 번째 시세 소스로 확인한 정상값으로 교체(MM-CHART-WRAP-20261112)


def load_overrides(path=None):
    """표시 보정 목록(data/chart_overrides.yaml) → [{ticker,date,field,mode,original,corrected,reason}]. 파일 없음·형식 오류 → []"""
    p = Path(path or OVR)
    if not p.exists(): return []
    import yaml
    d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out = []
    for x in d.get("overrides") or []:
        if not isinstance(x, dict): continue
        mode = x.get("mode", "clip")
        if x.get("field") not in {"clip": OVR_FIELDS, "set": SET_FIELDS}.get(mode, {}): continue
        out.append(dict(ticker=str(x["ticker"]), date=str(x["date"]), field=x["field"], mode=mode, original=float(x["original"]),
                        corrected=float(x["corrected"]), reason=str(x.get("reason", ""))))
    return out


def clip_bar(o, h, l, c, field):
    """보정 규칙 1봉: low → min(시가, 종가) 아래면 거기로, high → max(시가, 종가) 위면 거기로. 시가·종가 불변. 반환 (h, l)"""
    if field == "low" and l < min(o, c): l = min(o, c)
    if field == "high" and h > max(o, c): h = max(o, c)
    return h, l


def active_overrides(t, j=None, ovs=None, out=None):
    """한 종목에 지금 적용할 보정 [{d, f}] — 해당 날짜 봉이 있고 그 필드의 현재 값이 original 과 같을 때(상대 TOL)만.
    j = 차트 JSON(dict, 없으면 out/<t>.json 을 읽음). 반환 (적용 목록, 미적용 사유 목록)."""
    ovs = load_overrides() if ovs is None else ovs
    mine = [x for x in ovs if x["ticker"] == t]
    if not mine: return [], []
    if j is None:
        p = Path(out or OUT) / f"{t}.json"
        if not p.exists(): return [], [f"{t} 차트 파일 없음"]
        j = json.loads(p.read_text(encoding="utf-8"))
    df = from_obj(j); act, skip = [], []
    for x in mine:
        d = pd.Timestamp(x["date"]); k = SET_FIELDS[x["field"]]
        if d not in df.index: skip.append(f"{t} {x['date']} 봉 없음"); continue
        v = float(df.at[d, k])
        if abs(v - x["original"]) > TOL * max(abs(x["original"]), 1e-9): skip.append(f"{t} {x['date']} {x['field']} 현재 값 {v} ≠ 원값 {x['original']}"); continue
        act.append({"d": x["date"], "f": k, "v": x["corrected"]} if x.get("mode") == "set" else {"d": x["date"], "f": k})
    return act, skip


def apply_overrides(df, act):
    """보정 적용 사본(df = from_obj 결과). act = active_overrides 의 적용 목록. 원본 df 는 바꾸지 않는다.
    set(값 교체)을 먼저, clip(범위 자름)을 나중에 적용한다 — pricechart.js fix() 와 같은 순서."""
    df = df.copy()
    for x in act:
        d = pd.Timestamp(x["d"])
        if "v" in x and d in df.index: df.at[d, x["f"]] = float(x["v"])
    for x in act:
        if "v" in x: continue
        d = pd.Timestamp(x["d"])
        if d not in df.index: continue
        r = df.loc[d]; h, l = clip_bar(r.o, r.h, r.l, r.c, "low" if x["f"] == "l" else "high")
        df.at[d, "h"] = h; df.at[d, "l"] = l
    return df


def range_outliers(df, k=20, mult=10.0, min_win=10):
    """시세 오류 봉 후보(목록만 — 자동 보정 없음): 그 봉의 고저폭(고가−저가)이 앞뒤 k봉(그 봉 제외, 이력 끝에서는 있는 만큼) 고저폭 중앙값의 mult 배 초과.
    비교 봉 < min_win → 판정 제외. 중앙값 0 → 0 아닌 고저폭의 중앙값으로 대신(note='nz'), 비교 봉 고저폭이 전부 0 이고 그 봉 폭 > 0 → note='분모0'(배수 inf).
    반환 [{date,o,h,l,c,rng,med,mult,note}]"""
    import statistics
    R = (df.h - df.l).tolist(); out = []
    for i, (d, r) in enumerate(df.iterrows()):
        win = R[max(0, i - k):i] + R[i + 1:i + 1 + k]
        if len(win) < min_win: continue
        m = statistics.median(win); note = ""
        if m == 0:
            nz = [x for x in win if x > 0]
            if not nz:
                if R[i] > 0: out.append(dict(date=str(d.date()), o=r.o, h=r.h, l=r.l, c=r.c, rng=R[i], med=0.0, mult=float("inf"), note="분모0"))
                continue
            m = statistics.median(nz); note = "nz"
        if R[i] > mult * m:
            out.append(dict(date=str(d.date()), o=r.o, h=r.h, l=r.l, c=r.c, rng=round(R[i], 6), med=round(m, 6), mult=round(R[i] / m, 2), note=note))
    return out


def calendar_events(timeout=10):
    """나스닥 분할 캘린더(최근 LOOKBACK 일 이후) → {심볼: [(날짜, f)]}. 실패 → {}"""
    try:
        import mm_splits
        out = {}
        for e in mm_splits.nasdaq_calendar(pd.Timestamp.now().normalize() - pd.Timedelta(days=LOOKBACK), timeout=timeout):
            out.setdefault(e["symbol"], []).append((e["date"], e["f"]))
        return out
    except Exception:
        return {}


def prune(tickers, out=None):
    out = Path(out or OUT); gone = []
    if out.exists():
        for f in out.glob("*.json"):
            if f.stem not in set(tickers): f.unlink(); gone.append(f.stem)
    return gone


def daily_update(log=print, tickers=None, src=None, out=None, cal=True, full=False):
    """일일 산출 말미 훅 — 종목별 실패 격리. 반환 {티커: 결과}. 보류·재조정·실패는 alerts 로그(텔레그램 없음)."""
    t0 = time.time(); tickers = list(tickers or universe())
    ev = calendar_events() if cal else {}
    res = {}
    for t in tickers:
        try: res[t] = update_one(t, src=src, out=out, cal_events=ev, full=full)
        except Exception as e: res[t] = dict(status="error", added=0, bars=0, bytes=0, note=f"{type(e).__name__}: {str(e)[:150]}")
    gone = prune(tickers, out)
    cnt = {}
    for r in res.values(): cnt[r["status"]] = cnt.get(r["status"], 0) + 1
    tot = sum(r["bytes"] for r in res.values())
    log(f"[mm_charts] 가격 차트 {len(tickers)}종 " + " ".join(f"{k}={v}" for k, v in sorted(cnt.items())) + f" · 추가 {sum(r['added'] for r in res.values() if r['status'] == 'appended')}봉 · 합계 {tot / 1e6:.2f}MB · {time.time() - t0:.2f}s" + (f" · 정리 {gone}" if gone else ""))
    for t, r in res.items():
        if r["status"] in ("held", "error") or r.get("split"):
            try: log(f"[mm_charts] {t}: {r['status']} — {r['note']}", "alerts")
            except TypeError: log(f"[mm_charts] {t}: {r['status']} — {r['note']}")
        elif r["status"] == "rebuilt":
            log(f"[mm_charts] {t}: {r['note']}")
    try:                                                                # 표시 보정 목록이 현재 데이터와 맞는지(안 맞는 항목은 페이지에서 적용되지 않는다)
        ovs = load_overrides(); skip = []
        for t in sorted(set(x["ticker"] for x in ovs) & set(tickers)): skip += active_overrides(t, ovs=ovs, out=out)[1]
        for s in skip:
            try: log(f"[mm_charts] 표시 보정 미적용: {s}", "alerts")
            except TypeError: log(f"[mm_charts] 표시 보정 미적용: {s}")
    except Exception as e:
        log(f"[mm_charts] 표시 보정 목록 확인 실패: {type(e).__name__}: {str(e)[:150]}")
    return res


def check(src=None, out=None):
    """현재 파일 ↔ 원천 대조 요약(쓰기 0)"""
    out = Path(out or OUT); rows = []
    for t in universe():
        df, ev, fix = read_src(t, src)
        p = out / f"{t}.json"
        j = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        o = from_obj(j) if j else None
        rows.append(dict(t=t, bars=len(o) if o is not None else 0, first=str(o.index[0].date()) if o is not None else "", last=str(o.index[-1].date()) if o is not None else "",
                         src_first=str(df.index[0].date()), src_last=str(df.index[-1].date()), kb=round(p.stat().st_size / 1024, 1) if p.exists() else 0,
                         equal=bool(o is not None and o.index.equals(df.index) and np.allclose(o.values, df.values, rtol=TOL)), splits=len(ev), art=artifacts(df.c, ev)))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="mm_charts.py")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--build", action="store_true", help="전 종목 전체 생성(기존 파일 무시)")
    g.add_argument("--update", action="store_true", help="일일 갱신과 같은 경로(새 봉 덧붙임 + 마지막 봉 재대조)")
    g.add_argument("--check", action="store_true", help="파일 ↔ 원천 대조표만 출력(쓰기 0)")
    g.add_argument("--scan", action="store_true", help="시세 오류 봉 후보 목록(고저폭 > 앞뒤 20봉 중앙값 × 10)만 출력(쓰기 0, 보정 0)")
    ap.add_argument("--src"); ap.add_argument("--out"); ap.add_argument("--no-calendar", action="store_true")
    a = ap.parse_args()
    if a.scan:
        for t in universe():
            p = Path(a.out or OUT) / f"{t}.json"
            if p.exists():
                for x in range_outliers(from_obj(json.loads(p.read_text(encoding="utf-8")))): print(t, x)
    elif a.check:
        pd.set_option("display.width", 200); print(check(a.src, a.out).to_string())
    else:
        daily_update(log=lambda m, *k: print(m), src=a.src, out=a.out, cal=not a.no_calendar, full=a.build)
