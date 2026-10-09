#!/usr/bin/env python3
"""종목 페이지 '구성' 표 데이터 — data/holdings.json (MM-PAGE-V3.1 §7). 표시층 전용, 점수·판정 무관.
- ETF: 1x ETF 의 yfinance funds_data.top_holdings(제공처가 공개하는 상위 최대 10종). 지수 구성과 동일하다고 가정(기존 products.yaml 의 기준과 같음).
- ETN: 발행사 지수 구성종목 표(data/index_specs.yaml 의 index.constituents) 전체.
사용: python3 scripts/mm_holdings.py   (네트워크: yfinance, 1x ETF 약 23개)"""
import json, re, sys, datetime
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main():
    prods = yaml.safe_load(open(DATA / "products.yaml", encoding="utf-8"))["products"]
    ix = yaml.safe_load(open(DATA / "index_specs.yaml", encoding="utf-8"))["products"]
    out, cache, today = {}, {}, datetime.date.today().isoformat()
    import yfinance as yf
    for t, p in prods.items():
        tc = p.get("top_constituents") or {}
        if p["type"] == "ETN":
            c = ((ix.get(t) or {}).get("index") or {}).get("constituents") or {}
            items = [{"n": str(i["name"]), "w": i["weight_pct"]} for i in c.get("items", []) if i.get("name") is not None and i.get("weight_pct") is not None]
            if items:
                out[t] = {"basis": "지수 구성종목", "as_of": str(c.get("as_of", "")).split(" ")[0], "scope": "전체", "items": items}
            continue
        m = re.search(r"1x ETF ([A-Z0-9]+)", str(tc.get("basis", "")))
        if not m: continue
        etf = m.group(1)
        if etf not in cache:
            try:
                th = yf.Ticker(etf).funds_data.top_holdings
                cache[etf] = [{"n": str(s), "w": round(float(w) * 100, 2)} for s, w in zip(th.index, th["Holding Percent"]) if w == w]
            except Exception as e:
                print("실패", etf, type(e).__name__, str(e)[:80]); cache[etf] = []
        if cache[etf]:
            out[t] = {"basis": f"1x ETF {etf} 보유", "as_of": today, "scope": f"상위 {len(cache[etf])}종(제공처 공개 범위)", "items": cache[etf]}
    json.dump({"generated": today, "items": out}, open(DATA / "holdings.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(len(out), "종", {t: len(v["items"]) for t, v in out.items()})


if __name__ == "__main__":
    main()
