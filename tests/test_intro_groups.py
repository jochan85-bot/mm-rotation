"""MM-PRODUCT-INTRO-ENRICH-20261124 — 신규 49종 소개·보수·구성 요약줄 회귀 시험(데이터·렌더 결과만 읽는다, 네트워크·쓰기 0)."""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import mm_page_text as P
ok = fail = 0
def chk(name, cond, why=""):
    global ok, fail
    if cond: ok += 1; print("PASS", name)
    else: fail += 1; print("FAIL", name, why)
D = ROOT / "data"
g = json.load(open(D / "products_page_groups.json", encoding="utf-8"))["items"]
b = json.load(open(D / "products_page.json", encoding="utf-8"))["items"]
src = json.load(open(D / "intro_groups.json", encoding="utf-8"))["items"]
hold = json.load(open(D / "holdings_groups.json", encoding="utf-8"))["items"]
uni = [l.split(",")[0] for l in open(D / "universe_groups.csv", encoding="utf-8").read().splitlines()[1:]]
FORB = re.compile(r"추천|유망|전망|기대|매력|우수|좋은|유리|불리|매수|매도|투자하|할 것이|할 것으로|일 것|것으로 (보|예|판단|추정)|로 보인|보입니다|듯하|예상|권장|바람직|적합|가능성|유력|안정적|위험이 (낮|적|크)|리스크가 (낮|적|크)")
chk("49종 전부 소개 보강본과 일치", set(uni) == set(src) == set(g) and all(g[t]["text"]["intro"] == src[t]["intro"] for t in uni))
sents = {}
for t in uni:
    it = g[t]; i = it["text"]["intro"]; ps = P.paragraphs(i); per = [len(P.sentences(p)) for p in ps]
    chk(f"{t} 3문단·5~7문장", len(ps) == 3 and 5 <= sum(per) <= 7 and max(per) <= 2, per)
    chk(f"{t} 금지어 0", not FORB.search(i) and not re.search(r"\d{4}-\d{2}-\d{2}|상장일", i))
    fee = it["basic"].get("fee") or it["text"].get("fee")
    chk(f"{t} 보수 값 존재", bool(fee) and fee.strip() not in ("", "—"), fee)
    typ = it["basic"]["type"]
    chk(f"{t} 구분어", typ in i and ("일간" in i) and (typ != "ETN" or all(k in i for k in ("발행사", "신용", "조기상환"))) and (typ != "ETF" or "ETN" not in i))
    chk(f"{t} 3배는 문단1에서만", not any("3배" in p for p in ps[1:]))
    for p in ps:
        for s in P.sentences(p): sents.setdefault(s.strip(), set()).add(t)
for t, v in b.items():
    for p in P.paragraphs(v["text"]["intro"]):
        for s in P.sentences(p):
            if s.strip() in sents: sents[s.strip()].add("기존:" + t)
dup = {s[:40]: sorted(v) for s, v in sents.items() if len(v) > 1}
chk("종목 간 동일 문장 0건(기존 37 포함)", not dup, dup)
for t in ("BITU", "ETHT", "TMF", "TYD", "HYGU", "LQDU"):
    chk(f"{t} 구성 요약줄", bool(hold.get(t, {}).get("lines")) and not hold[t].get("items"))
# 렌더 결과: 확인하지 못했다 안내·'—' 보수 없음
for t in uni:
    h = (ROOT / "docs" / "products" / f"{t}.html").read_text(encoding="utf-8")
    chk(f"{t} 페이지 구성 영역 정상", "구성 종목 데이터를 확인하지 못했습니다" not in h and "<h2>구성</h2>" in h)
    m = re.search(r"<th[^>]*>보수</th>.*?</tr><tr>(?:<td>[^<]*</td>){3}<td>([^<]*)</td><td>[^<]*</td></tr>", h, re.S)
    chk(f"{t} 페이지 보수 표시", bool(m) and m.group(1).strip() not in ("", "—"), m.group(1) if m else None)
print(f"\n{ok} PASS, {fail} FAIL"); sys.exit(1 if fail else 0)
