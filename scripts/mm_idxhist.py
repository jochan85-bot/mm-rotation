#!/usr/bin/env python3
"""공식 지수 레벨 18종의 1x 이력 출처 — 표시용 데이터·계산 (MM-NEWIDX-CHECK-20261011). 읽기·표시만: compute·점수·순위 무관.

정적 사실 = data/index_history.json (이 스크립트 `--build` 로 data/product_info.csv · data/proxy_specs.json · data/ext/*.csv · .local/official/*.json · 수신 지수 파일에서 산출).
  - official_first : 공식 지수 수치의 첫 날짜(MicroSectors 공시 JSON 의 첫 행, 야후 지수는 야후 이력 첫 날)
  - ext            : 공식 첫 날짜 **이전**을 이어 붙인 연장(관련 지수·SG 인증서·구성종목 복제·관련 ETF 총수익) — 방법·시작~끝
  - tail           : 공식 수치가 최신 기준일보다 뒤처질 때 꼬리 며칠을 다른 소스 수익률로 이은 것(연장 비중에는 세지 않고 별도 표기)
동적 값 = window_pct(): 기준일 포함 최근 252거래일 중 공식 첫 날짜 이전(연장)에 속한 날의 비율(%). 거래일 목록 = docs/data/index.json.
사용: python3 scripts/mm_idxhist.py --build   |   python3 scripts/mm_idxhist.py [기준일]  (표 출력)"""
import json, sys, datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"; DOCS = ROOT / "docs"; LOCAL = ROOT / ".local"
WINDOW = 252
HIST_FILE = DATA / "index_history.json"
REASON_FMT = "지수 이력 일부 재구성({pct}%)"


def load_history(path=HIST_FILE):
    try: return json.load(open(path, encoding="utf-8")).get("items", {})
    except Exception: return {}


def trading_dates():
    try: return [x["d"] for x in json.load(open(DOCS / "data" / "index.json", encoding="utf-8"))["dates"]]
    except Exception: return []


def window_stats(official_first, dates, asof):
    """(연장 일수, 창 일수) — 창 = asof 이하 거래일 중 마지막 WINDOW 개. 연장 = 공식 첫 날짜 이전. dates 는 오름차순 'YYYY-MM-DD'."""
    win = [d for d in dates if d <= asof][-WINDOW:]
    if not win or not official_first: return 0, len(win)
    return sum(1 for d in win if d < official_first), len(win)


def window_pct(item, dates, asof):
    """연장이 창에 1일이라도 들어가면 올림 없이 반올림한 % (최소 1), 없으면 0."""
    if not item or not (item.get("ext") or {}).get("has"): return 0
    n, w = window_stats(item["official_first"], dates, asof)
    if n == 0 or w == 0: return 0
    return max(1, round(100 * n / w))


def reason(item, dates, asof):
    p = window_pct(item, dates, asof)
    return REASON_FMT.format(pct=p) if p else ""


def table_rows(asof, dates=None, items=None):
    dates = dates if dates is not None else trading_dates(); items = items if items is not None else load_history()
    rows = []
    for t, it in items.items():
        n, w = window_stats(it["official_first"], dates, asof) if (it.get("ext") or {}).get("has") else (0, min(WINDOW, len([d for d in dates if d <= asof])))
        e = it.get("ext") or {}
        rows.append(dict(ticker=t, kind=it["level_kind"], official_first=it["official_first"], has_ext=bool(e.get("has")), ext_method=e.get("method", "—"), ext_detail=e.get("detail", ""),
                         ext_start=e.get("start", ""), ext_end=e.get("end", ""), tail_days=(it.get("tail") or {}).get("days", 0), tail_src=(it.get("tail") or {}).get("src", ""),
                         window_ext_days=n, window_days=w, window_pct=window_pct(it, dates, asof), listed=it.get("listed", ""), first_bar=it.get("first_bar", "")))
    return rows


def build():
    """정적 사실 data/index_history.json 생성(수신 파일·캐시가 있는 환경에서)."""
    import pandas as pd, yaml
    specs = json.load(open(DATA / "proxy_specs.json", encoding="utf-8"))["specs"]
    pi = pd.read_csv(DATA / "product_info.csv").set_index("ticker")
    inc = {t: (p.get("inception") or {}).get("date") for t, p in yaml.safe_load(open(DATA / "products.yaml", encoding="utf-8"))["products"].items()}
    try: binfo = json.load(open(LOCAL / "proxy_build_info.json", encoding="utf-8"))
    except Exception: binfo = {}
    METHOD = {"^NYFANG": "관련 지수(가격수익)", "SG": "SG 인증서", "복제": "구성종목 복제", "총수익": "관련 ETF 총수익"}
    out = {}
    for key, sp in specs.items():
        if sp["kind"] not in ("yahoo", "official"): continue
        for t in dict.fromkeys(sp["products"]):
            r = pi.loc[t]; it = dict(key=key, first_bar=str(r.first_bar), listed=inc.get(t) or str(r.first_bar), index_name=str(r.index_name))
            if sp["kind"] == "yahoo":
                d = pd.read_csv(LOCAL / "fetched" / f"{sp['ticker']}.csv", index_col=0, usecols=[0])
                it.update(level_kind="yahoo_index", official_first=str(d.index[0])[:10], ext=dict(has=False))
            else:
                off = json.load(open(LOCAL / "official" / f"{sp['symbol']}.json"))
                first = pd.Timestamp(off[0][0], unit="ms").date().isoformat()
                pre = pd.read_csv(DATA.parent / sp["pre"], index_col=0); pre.index = pd.to_datetime(pre.index.astype(str).str[:10])
                pre = pre[pre.index < pd.Timestamp(first)]
                note = str(r.onex_extension); m = next((v for k, v in METHOD.items() if k in note), "기타")
                it.update(level_kind="official_level", official_first=first, ext=dict(has=bool(len(pre)), method=m, detail=note.lstrip("~ ").split(" ", 1)[-1] if note.startswith("~") else note,
                          start=str(pre.index.min().date()) if len(pre) else "", end=str(pre.index.max().date()) if len(pre) else ""))
                bi = binfo.get(key, {})
                it["tail"] = dict(days=int(bi.get("tail_days", 0)), src=bi.get("tail_src") or "", official_last=bi.get("official_last", ""))
            out[t] = it
    json.dump({"generated": datetime.date.today().isoformat(), "window": WINDOW, "items": dict(sorted(out.items()))}, open(HIST_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return len(out)


if __name__ == "__main__":
    if "--build" in sys.argv: print(build(), "종 기록 →", HIST_FILE)
    else:
        asof = next((a for a in sys.argv[1:] if not a.startswith("-")), trading_dates()[-1])
        for r in table_rows(asof): print(r)
