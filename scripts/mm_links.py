#!/usr/bin/env python3
"""구성 종목 링크 대상 선택 — 기업개요 탭(overview) 우선, 데이터가 없으면 종합 페이지로 대체하고 이유를 남긴다 (MM-CLOSE-FINAL-20261010 §1).
규칙·실측 근거: data/link_rules.yaml. 이 모듈은 holdings.json 항목에 lk('o'=기업개요 / 't'=종합)·lw(대체 이유)를 채운다. 네이버 코드(nv)가 없는 항목은 건드리지 않는다(검색 링크).
사용: python3 scripts/mm_links.py [--dry]    (네트워크: api.stock.naver.com, 고유 코드당 최대 2회, 캐시 .local/naver_overview_cache.json 30일)"""
import json, os, sys, time, datetime, threading, urllib.error, urllib.parse, urllib.request, concurrent.futures as cf
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"; LOCAL = ROOT / ".local"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
API = "https://api.stock.naver.com/stock/{code}/{ep}"
REASONS = {"etf": "네이버가 ETF 로 분류(기업개요 탭 없음)", "empty": "기업개요 응답이 비어 있음", "err409": "기업개요 API 409", "unchecked": "기업개요 확인 못 함(네트워크) — 종합으로 대체"}


def _get_json(code, ep, timeout=20):
    req = urllib.request.Request(API.format(code=urllib.parse.quote(code), ep=ep), headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def judge(basic, overview, code=None):
    """(lk, 이유코드) — basic·overview 는 API JSON(또는 HTTPError 를 뜻하는 정수 코드). 순수 함수(단위 테스트 대상)."""
    if isinstance(basic, int) or isinstance(overview, int):
        return "t", "err409" if 409 in (basic, overview) else "unchecked"
    if (basic or {}).get("stockEndType") != "stock": return "t", "etf"
    if not str((overview or {}).get("summary") or "").strip(): return "t", "empty"
    return "o", None


def check_code(code, opener=_get_json):
    def call(ep):
        try: return opener(code, ep)
        except urllib.error.HTTPError as e: return e.code
        except Exception: return None
    b = call("basic")
    if b is None: return {"lk": "t", "lw": "unchecked", "at": None}
    o = call("overview") if not isinstance(b, int) and b.get("stockEndType") == "stock" else {}
    if o is None: return {"lk": "t", "lw": "unchecked", "at": None}
    lk, lw = judge(b, o, code)
    return {"lk": lk, "lw": lw, "at": datetime.date.today().isoformat()}


def apply_overview(entries, workers=3, sleep=0.25, budget_s=900, cache_path=None, opener=_get_json, log=print):
    """entries = {종목: {items:[{nv,...}]}} 의 모든 항목에 lk·lw 를 채운다(제자리). 반환 통계."""
    cache_path = cache_path or LOCAL / "naver_overview_cache.json"
    try: cache = json.load(open(cache_path, encoding="utf-8"))
    except Exception: cache = {}
    codes = sorted({x["nv"] for e in entries.values() for x in e.get("items", []) if x.get("nv")})
    today = datetime.date.today()
    fresh = lambda c: c and c.get("at") and (today - datetime.date.fromisoformat(c["at"])).days < 30
    todo = [c for c in codes if not fresh(cache.get(c))]
    deadline = time.time() + budget_s; lock = threading.Lock(); done = [0]

    def work(code):
        if time.time() > deadline: return code, None
        time.sleep(sleep)
        return code, check_code(code, opener)
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for code, r in ex.map(work, todo):
            if r is not None and r["at"]:
                with lock: cache[code] = r
            done[0] += 1
            if done[0] % 200 == 0: log(f"  overview {done[0]}/{len(todo)}")
    try:
        tmp = str(cache_path) + ".tmp"; json.dump(cache, open(tmp, "w", encoding="utf-8"), ensure_ascii=False); os.replace(tmp, cache_path)
    except Exception as e: log(f"  캐시 저장 실패 {e}")
    stats = {"codes": len(codes), "queried": len(todo), "o": 0, "t": 0, "reasons": {}, "unchecked": 0}
    for e in entries.values():
        for x in e.get("items", []):
            nv = x.get("nv")
            if not nv: x.pop("lk", None); x.pop("lw", None); continue
            c = cache.get(nv)
            if not c: x["lk"], x["lw"] = "t", "unchecked"; stats["unchecked"] += 1; continue
            x["lk"] = c["lk"]
            if c["lw"]: x["lw"] = c["lw"]
            else: x.pop("lw", None)
            stats[c["lk"]] += 1
            if c["lw"]: stats["reasons"][c["lw"]] = stats["reasons"].get(c["lw"], 0) + 1
    return stats


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import mm_holdings
    p = DATA / "holdings.json"
    h = json.load(open(p, encoding="utf-8"))
    st = apply_overview(h["items"])
    print(json.dumps(st, ensure_ascii=False))
    if "--dry" not in sys.argv:
        mm_holdings.dump(h, p); print("saved", p)
