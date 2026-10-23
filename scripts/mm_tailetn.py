#!/usr/bin/env python3
"""1x 꼬리 보정(일반화) — 3배 상품 일간 수익률 ÷ 3 으로 빠진 최신 날짜를 잇는다 (MM-FEED-LAG-FIX-20261018 §2).

배경: 1x 가 공식 지수 레벨(MicroSectors JSON)인 18종 + 복합 1종은 공식 수치가 기준일보다 2거래일 늦게 나온다. 기존 꼬리(SG 인증서·구성종목 복제·
      관련 ETF·야후 지수)가 그 간격을 메우지만, 꼬리 소스 자체가 늦으면(2026-10-17 08:15: SG 인증서 4종, 3배 ETN 2종) 1x 최신 봉 < 기준일 → ⚠ → 순위에서 빠졌다.
      exact 1x ETF 도 ETF 봉이 늦거나 Close 가 NaN 이면 같은 모양으로 빠진다.
규칙(오너 지시):
  · 대상 = 순위 계산에 쓰는 모든 1x 시계열(proxy). 1x 최신 봉 < 기준일 T 이면, 빠진 거래일을 같은 proxy 를 쓰는 3배 상품의 일간 수익률 ÷ 3 으로 이어 붙인다.
    배수는 proxy_quality 의 실측 β 가 아니라 공시 배수 3 고정(MULT).
  · 3배 봉은 mm_nasdaq.apply_after_fetch 가 이미 야후 → 나스닥 폴백 순으로 채운 RAW 파일을 쓴다. 빠진 날짜를 덮는 3배 상품이 하나도 없으면 보정 불가(⚠ 유지).
  · 최대 MAX_GAP(3) 거래일. 초과하면 보정하지 않고 ⚠ 유지.
  · 보정 행은 RAW 파일의 src 열에 'tail_etn' 으로 기록한다(나머지 행은 빈 문자열). RAW 는 매 실행 clean_all 이 새로 쓰므로, 다음 실행에서 공식 레벨·꼬리 소스가
    그 날짜를 채우면 자동으로 보정 행이 사라진다(덮어씀).
  · 같은 proxy 를 쓰는 3배가 여럿이면(SPXL/UPRO, TNA/URTY, MIDU/UMDD) 필요한 날짜를 모두 가진 상품 중 20일 평균 거래대금이 큰 쪽 하나를 쓴다.
  · skip_proxies(펀드추종 1x, data/fund_track.json)는 보정 대상에서 뺀다 — 펀드 가격이 늦으면 보정 없이 ⚠(MM-FUNDTRACK-20261023).
점수 산식·피처 코드는 건드리지 않는다. 호출 위치: mm_daily.run — clean_all 직후, load_study 이전.
"""
import json
from pathlib import Path
import numpy as np, pandas as pd

MAX_GAP = 3
MULT = 3.0
SRC = "tail_etn"
ET = "America/New_York"


def _rd(p):
    h = pd.read_csv(p, index_col=0)
    h.index = pd.to_datetime(h.index, utc=True).tz_convert(ET)
    return h


def _days(idx):
    return pd.DatetimeIndex(idx).tz_localize(None).normalize()


def _close_by_day(h):
    s = pd.Series(h["Close"].values.astype(float), index=_days(h.index))
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s[s.notna() & (s > 0)]


def _adtv20(h):
    t = h.tail(20)
    try: return float((t["Close"].astype(float) * t["Volume"].astype(float)).mean())
    except Exception: return 0.0


def fill(T, uni, raw_dir, log=print, write=True, max_gap=MAX_GAP, info_path=None, skip_proxies=()):
    """RAW(raw_dir/*.csv)의 1x 시계열을 T 까지 보정한다. 반환 {proxy: {status, ...}} — 보정이 필요했던 proxy 만 담긴다.
    status: filled(보정함) / over_max(빠진 거래일 > max_gap, ⚠ 유지) / no_3x(빠진 날짜를 덮는 3배 봉 없음, ⚠ 유지) / no_calendar"""
    T = pd.Timestamp(T).normalize(); raw_dir = Path(raw_dir); info = {}
    try:
        cal = sorted(d for d in set(_days(_rd(raw_dir / "SPY.csv").index)) if d <= T)
    except Exception as e:
        log(f"[mm_tailetn] SPY 달력을 읽지 못해 건너뜀: {type(e).__name__}: {e}")
        return info
    skip = set(skip_proxies or ())                                      # 펀드추종(펀드 가격 직접) 1x — 꼬리 보정 대상 아님(MM-FUNDTRACK-20261023 §1): 펀드 봉이 늦으면 보정 없이 ⚠
    for px, grp in uni.groupby("proxy", sort=False):
        if px in skip: continue
        p = raw_dir / f"{px}.csv"
        if not p.exists(): continue
        h1 = _rd(p); c1 = _close_by_day(h1)
        if len(c1) == 0: continue
        last1 = c1.index.max()
        if last1 >= T: continue
        missing = [d for d in cal if d > last1]
        if not missing: continue
        rec = dict(status="", missing=[str(d.date()) for d in missing], last1=str(last1.date()), members=list(grp.ticker))
        if len(missing) > max_gap:
            rec["status"] = "over_max"; info[px] = rec
            log(f"[mm_tailetn] {px}: 1x 최신 {last1.date()} → 기준일 {T.date()} 사이 {len(missing)}거래일 > {max_gap} — 보정 안 함(⚠ 유지)")
            continue
        need = [last1] + missing; best = None
        for t3 in grp.ticker:
            q = raw_dir / f"{t3}.csv"
            if not q.exists(): continue
            h3 = _rd(q); c3 = _close_by_day(h3)
            if all(d in c3.index for d in need):
                a = _adtv20(h3)
                if best is None or a > best[0]: best = (a, t3, c3)
        if best is None:
            rec["status"] = "no_3x"; info[px] = rec
            log(f"[mm_tailetn] {px}: 빠진 날짜 {rec['missing']} 를 덮는 3배 봉이 없음({list(grp.ticker)}) — 보정 안 함(⚠ 유지)")
            continue
        _, via, c3 = best
        val = float(c1.loc[last1]); rows = []; rets = []; prev = last1
        for d in missing:
            r3 = float(c3.loc[d] / c3.loc[prev] - 1.0); rets.append(round(r3, 6))
            val = val * (1.0 + r3 / MULT)
            if not (val > 0):
                rec["status"] = "no_3x"; rec["note"] = "보정값이 0 이하"; info[px] = rec; rows = None; break
            rows.append((d, val)); prev = d
        if rows is None: continue
        add = pd.DataFrame(index=[pd.Timestamp(d).tz_localize(ET) for d, _ in rows], columns=h1.columns, dtype=object)
        for c in ("Open", "High", "Low", "Close", "Adj Close"):
            if c in add.columns: add[c] = [v for _, v in rows]
        for c in ("Volume", "Dividends", "Stock Splits", "Capital Gains"):
            if c in add.columns: add[c] = 0.0
        out = h1.copy()
        if "src" not in out.columns: out["src"] = ""
        out["src"] = out["src"].fillna("").astype(object)
        add["src"] = SRC
        for c in out.columns:
            if c not in add.columns: add[c] = np.nan
        out = pd.concat([out, add[out.columns]])
        out.index.name = "Date"
        if write: out.to_csv(p)
        rec.update(status="filled", days=len(rows), dates=[str(d.date()) for d, _ in rows], via=via, mult=MULT, r3=rets, values=[round(v, 6) for _, v in rows])
        info[px] = rec
        log(f"[mm_tailetn] {px}: 1x 최신 {last1.date()} → 3배({via})÷{int(MULT)} 로 {len(rows)}일 보정 ({', '.join(rec['dates'])})")
    if info_path is not None and write:
        Path(info_path).write_text(json.dumps(dict(T=str(T.date()), proxies=info), ensure_ascii=False, indent=1), encoding="utf-8")
    return info


def load_info(path):
    try: return json.load(open(path, encoding="utf-8")).get("proxies", {})
    except Exception: return {}


def days_for(info, proxy, asof):
    """asof 이하 날짜 중 이 proxy 의 보정 일수(없으면 0)."""
    r = (info or {}).get(proxy) or {}
    if r.get("status") != "filled": return 0
    a = str(pd.Timestamp(asof).date())
    return sum(1 for d in r.get("dates", []) if d <= a)


def unresolved(info):
    """보정하지 못한 proxy(over_max/no_3x) 목록 — 경보 사유용."""
    return {k: v for k, v in (info or {}).items() if v.get("status") != "filled"}
