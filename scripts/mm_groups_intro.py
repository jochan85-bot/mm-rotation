"""MM-PRODUCT-INTRO-ENRICH-20261124 — 신규 49종 소개·보수·구성 요약줄·구조 리스크 보강분(data/intro_groups.json)을 페이지 데이터에 덮어쓴다.
intro_groups.json = 발행사 1차 문서(ProShares·Direxion 497K, BMO 424B2)와 짝 롱 상품 소개의 검증된 사실로 쓴 문구(LLM 호출 0, 점수·순위 같은 매일 바뀌는 값 없음).
mm_groups_pages.build() 가 끝에 apply_items/apply_holdings 를 불러 다시 생성해도 이 보강분이 유지된다. 단독 실행: python3 scripts/mm_groups_intro.py (멱등)."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SRC = DATA / "intro_groups.json"


def _load():
    try:
        return json.load(open(SRC, encoding="utf-8"))
    except Exception:
        return None


def apply_items(items):
    """items = products_page_groups.json 의 items(dict). 소개·구성 방식·보수·구조 리스크를 덮어쓴다. 반환 = 보강한 종목 수."""
    d = _load()
    if not d: return 0
    mod = d["meta"]["generated"]; n = 0
    for t, e in d["items"].items():
        it = items.get(t)
        if not it: continue
        tx = it.setdefault("text", {}); b = it.setdefault("basic", {})
        tx["intro"] = e["intro"]
        if e.get("construction"): tx["construction"] = e["construction"]
        b["fee"] = e.get("fee_basic"); tx["fee"] = e.get("fee_text") or ""
        risk = list(tx.get("risk", []))
        for r in e.get("risk_add", []):
            if r not in risk: risk.append(r)
        tx["risk"] = risk; it["modified"] = mod; n += 1
    return n


def apply_holdings(H):
    """H = holdings_groups.json 의 items(dict). 구성 요약줄(lines)이 있는 종목(크립토·채권 롱)을 채운다."""
    d = _load(); n = 0
    if not d: return 0
    for t, e in d["items"].items():
        h = e.get("hold")
        if not h: continue
        H[t] = {"basis": h["basis"], "as_of": d["meta"]["generated"], "fetched": d["meta"]["generated"], "total": 0, "scope": "", "lines": list(h["lines"]),
                "source": dict(h["source"]), "items": []}
        n += 1
    return n


def main():
    pj = DATA / "products_page_groups.json"; hj = DATA / "holdings_groups.json"
    P = json.load(open(pj, encoding="utf-8")); n = apply_items(P["items"]); P["meta"]["intro_block"] = "MM-PRODUCT-INTRO-ENRICH-20261124"
    json.dump(P, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    Hd = json.load(open(hj, encoding="utf-8")); m = apply_holdings(Hd["items"])
    json.dump(Hd, open(hj, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return n, m


if __name__ == "__main__":
    print(main())
