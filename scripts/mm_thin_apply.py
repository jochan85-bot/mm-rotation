#!/usr/bin/env python3
"""MM-THIN-ETN-HIST-20261021 §1 일회성 적용 도구(감사용 보존) — 극저유동 ETN(XLCU·XLPU) 3배 이력 복구 + 날짜 파일의 해당 종목 표시 열만 갱신.
단계(각각 독립 실행): 
  --fetch   : 야후 재수신 → mm_nasdaq.build_history(상장일부터 나스닥 이력) → .local/fetched/<티커>.csv 교체
  --check   : 표시값 재계산 도구가 **구 이력(백업)** 으로 현재 날짜 파일 값을 재현하는지 검증(도구 정합성)
  --apply   : 2026-10-13 이후 날짜 파일 + data/scores_latest.csv 의 해당 두 종목 close3·adtv·listed_days·badges 만 갱신(점수·순위·모집단 불변 확인), 페이지 재생성은 별도(--pages)
  --pages   : index.html·guide.html·products.html·해당 종목 페이지 재생성(점수 무접촉)
표시 열 = close3·adtv·listed_days·badges. 다른 열·다른 종목 행은 바이트 단위로 보존한다(CSV 를 문자열 수준에서 해당 행의 해당 칸만 바꿈)."""
import sys, json, csv, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import mm_lib as L, mm_nasdaq as N
TICKERS = ["XLCU", "XLPU"]
FROM = pd.Timestamp("2026-10-13")
DISPLAY = ["close3", "adtv", "listed_days", "badges"]


def spy_dates(fetched):
    spy = pd.read_csv(Path(fetched) / "SPY.csv", index_col=0)
    return pd.DatetimeIndex(pd.to_datetime(spy.index, utc=True).tz_convert("America/New_York").tz_localize(None).normalize())


def load_h3(t, fetched):
    """clean_all 과 같은 처리(ET 정규화, SPY 달력에 없는 행 제거, Close NaN 마지막 행 제거) 후의 3배 일봉."""
    h = pd.read_csv(Path(fetched) / f"{t}.csv", index_col=0)
    h.index = pd.to_datetime(h.index, utc=True).tz_convert("America/New_York").tz_localize(None).normalize()
    sd = set(spy_dates(fetched))
    if len(h) >= 22 and pd.isna(h.iloc[-1]["Close"]): h = h.iloc[:-1]
    return h[h.index.isin(sd) | (h.index < min(sd))]


def display_values(h3, asof, row, cfg, fb):
    """mm_lib.compute 의 3배 표시 블록과 같은 식. row = 기존 날짜 파일 행(beta·r2·n_beta·badges 의 지수보정 N 사용)."""
    asof = pd.Timestamp(asof); h3a = h3[h3.index <= asof]
    d3 = h3a.index.max() if len(h3a) else None
    nobar = ((d3 is not None) and (d3 != asof)) or ((d3 is None) and fb is not None and asof >= fb)
    if nobar: h3a = L.with_nobar(h3a, asof)
    tail = h3a.tail(20)
    adtv = float((tail["Close"] * tail["Volume"]).mean() / 1e6); zero = int((tail["Volume"] == 0).sum()); close3 = float(h3a["Close"].iloc[-1]); vol20 = float(tail["Volume"].mean())
    beta = None if pd.isna(row["beta"]) else float(row["beta"]); r2 = None if pd.isna(row["r2"]) else float(row["r2"]); nb = int(row["n_beta"])
    tn = 0
    for b in str(row["badges"]).split(" · "):
        if b.startswith("지수보정"): tn = int(b[4:])
    bd = L.badges_for(len(h3a), adtv, zero, beta, r2, nb, cfg, tailn=tn, vol20=vol20)
    return dict(close3=close3, adtv=adtv, listed_days=len(h3a), badges=" · ".join(bd), zero=zero, vol20=vol20, nobar=bool(nobar))


def read_day_text(p):
    lines = Path(p).read_text(encoding="utf-8").split("\n")
    return lines[0], lines[1:]


def day_files():
    return [p for p in sorted(L.SCORES.glob("*.csv")) if pd.Timestamp(p.stem) >= FROM]


def fmt(col, v):
    if col == "listed_days": return str(int(v))
    if col == "badges": return v
    return repr(round(float(v), 6)).rstrip("0").rstrip(".") if False else ("%.6f" % float(v)).rstrip("0").rstrip(".") if float(v) == float(v) else ""


def compute_all(fetched, cfg, fbs):
    H = {t: load_h3(t, fetched) for t in TICKERS}; out = {}
    for p in day_files():
        hdr, body = read_day_text(p); rdr = list(csv.reader(io.StringIO("\n".join(body))))
        cols = rdr[0]; ix = {c: i for i, c in enumerate(cols)}
        for r in rdr[1:]:
            if r and r[ix["ticker"]] in TICKERS:
                row = {c: (r[ix[c]] if r[ix[c]] != "" else np.nan) for c in cols}
                for c in ("beta", "r2", "n_beta"): row[c] = float(row[c]) if row[c] == row[c] else np.nan
                out[(p.stem, r[ix["ticker"]])] = (display_values(H[r[ix["ticker"]]], pd.Timestamp(p.stem), row, cfg, fbs.get(r[ix["ticker"]])), {c: r[ix[c]] for c in DISPLAY})
    return out


def main():
    a = sys.argv[1:]; cfg = L.load_yaml_simple(L.DATA / "eligibility.yaml"); fbs = N.first_bars()
    if "--fetch" in a:
        import yfinance as yf
        cal = spy_dates(L.FETCHED)
        for t in TICKERS:
            yh = yf.Ticker(t).history(period="max", auto_adjust=False, actions=True)
            out, mode, summ = N.build_history(t, yh, fbs.get(t), cal, force_replace=True)
            out.to_csv(L.FETCHED / f"{t}.csv"); print(t, "야후", len(yh), "봉 →", summ)
    if "--check" in a:                                              # 도구 검증: 구 이력(백업)으로 현재 파일 값 재현
        res = compute_all(L.LOCAL / "bak" / "fetched_pre_thin_20261021", cfg, fbs); bad = 0
        for (d, t), (v, cur) in sorted(res.items()):
            def eq(a, b, tol=1e-5):
                a = float(a) if a != "" else float("nan")
                return (a != a and b != b) or (a == a and b == b and abs(a - b) < tol)
            ok = (eq(cur["close3"], v["close3"]) and eq(cur["adtv"], v["adtv"]) and cur["listed_days"] == str(v["listed_days"]) and cur["badges"].replace("거래량극소 · ", "") == v["badges"].replace("거래량극소 · ", ""))
            print(("OK  " if ok else "DIFF"), d, t, "현재", cur, "재현", {k: (round(x, 6) if isinstance(x, float) else x) for k, x in v.items() if k in DISPLAY})
            bad += (not ok)
        print("검증: 불일치", bad, "/", len(res))
    if "--apply" in a:
        res = compute_all(L.FETCHED, cfg, fbs); changed = {}
        for p in day_files():
            txt = p.read_text(encoding="utf-8"); lines = txt.split("\n"); hdr = lines[0]
            rdr = csv.reader(io.StringIO("\n".join(lines[1:]))); rows = list(rdr); cols = rows[0]; ix = {c: i for i, c in enumerate(cols)}; mod = 0
            for r in rows[1:]:
                if r and r[ix["ticker"]] in TICKERS:
                    v, cur = res[(p.stem, r[ix["ticker"]])]
                    for c in DISPLAY:
                        new = fmt(c, v[c])
                        if r[ix[c]] != new:
                            r[ix[c]] = new; mod += 1
            if mod:
                buf = io.StringIO(); w = csv.writer(buf, lineterminator="\n"); [w.writerow(r) for r in rows]
                p.write_text(hdr + "\n" + buf.getvalue(), encoding="utf-8"); changed[p.name] = mod
        print("변경 파일", len(changed), changed)
        # scores_latest.csv (최신 날짜 행)
        sl = pd.read_csv(L.DATA / "scores_latest.csv"); asof = str(sl.date.iloc[0])
        for t in TICKERS:
            v, _ = res[(asof, t)]
            m = sl.ticker == t
            for c, k in (("close3", "close3"), ("adtv", "adtv"), ("listed_days", "listed_days"), ("badges", "badges"), ("zero_vol", "zero")):
                if c in sl.columns: sl.loc[m, c] = v[k]
        sl.to_csv(L.DATA / "scores_latest.csv", index=False); print("scores_latest 갱신", asof)
        L.rebuild_index()
    if "--pages" in a:
        import mm_site
        df = pd.read_csv(L.DATA / "scores_latest.csv"); uni = pd.read_csv(L.DATA / "universe.csv"); p0 = pd.read_csv(L.DATA / "product_info.csv")
        meta = dict(asof=str(df.date.iloc[0]), generated="", provisional=None, new_products=[], pipeline=[], dropped=[], manual=False, anomalies=pd.read_csv(L.DATA / "anomalies.csv"))
        cur = (L.DOCS / "guide.html").read_text(encoding="utf-8"); import re
        m = re.search(r"산출 (\d{4}-\d\d-\d\d \d\d:\d\d) KST", cur); meta["generated"] = m.group(1) if m else ""
        (L.DOCS / "index.html").write_text(mm_site.build_index(df, meta), encoding="utf-8")
        mm_site.rebuild_guide_only()
        print("pages 재생성: index.html · guide.html")


if __name__ == "__main__":
    main()
