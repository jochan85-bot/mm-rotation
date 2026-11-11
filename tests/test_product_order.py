"""MM-PRICE-CHART-POS-20261111 — 종목 페이지 섹션 순서 시험(읽기만, live 쓰기 0).
docs/products/<티커>.html 전 종목(유니버스와 같은 수)에서 body 최상위 요소 순서가
  h1 → 소개 제목 → 가격 차트 블록(가격 머리글·봉 주기 버튼·기간 버튼·차트·하단 문구) → 소개 글 상자 → M-score 차트 → 구성 → 기본 정보 → 구조 리스크
인지, 가격 차트 블록이 페이지마다 정확히 1번인지 확인한다. python3 tests/test_product_order.py"""
import sys, csv
from html.parser import HTMLParser
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
VOID = {"br", "img", "input", "meta", "link", "hr", "source", "wbr"}

P = F = 0
def ok(name, cond, info=""):
    global P, F
    if cond: P += 1; print("PASS", name)
    else: F += 1; print("FAIL", name, info)


class Top(HTMLParser):
    """body 최상위 요소 → 라벨(태그.클래스#id, 제목·문구는 앞 글자)"""
    def __init__(s):
        super().__init__(convert_charrefs=True); s.depth = 0; s.inbody = False; s.seq = []; s.cur = None
    def handle_starttag(s, tag, a):
        a = dict(a)
        if tag == "body": s.inbody = True; return
        if not s.inbody: return
        if s.depth == 0:
            s.cur = [tag + "".join("." + c for c in (a.get("class") or "").split()) + ("#" + a["id"] if a.get("id") else ""), "", []]; s.seq.append(s.cur)
        elif a.get("id") and s.cur is not None: s.cur[2].append(a["id"])
        if tag not in VOID: s.depth += 1
    def handle_endtag(s, tag):
        if not s.inbody or tag == "body" or tag in VOID: return
        s.depth -= 1
        if s.depth == 0: s.cur = None
    def handle_data(s, d):
        if s.cur is not None and len(s.cur[1]) < 40: s.cur[1] += d


def labels(html):
    p = Top(); p.feed(html); out = []
    for tag, text, ids in p.seq:
        lab = tag + ("{" + ",".join(ids) + "}" if ids else "")
        if tag in ("h2", "div.pcap") or tag.startswith("div.chartnote"): lab += ":" + text.strip()[:8]
        out.append(lab)
    return out


BLOCK = ["div.pcap:가격", "div.pbar", "div.pbar.rng", "div.chartbox{pchart,preadout}"]
uni = [r["ticker"] for r in csv.DictReader(open(ROOT / "data" / "universe.csv", encoding="utf-8"))]
pages = sorted((ROOT / "docs" / "products").glob("*.html"))
ok(f"종목 페이지 수 = 유니버스 수({len(uni)})", sorted(p.stem for p in pages) == sorted(uni), f"{len(pages)}")
bad = []
for f in pages:
    s = labels(f.read_text(encoding="utf-8"))
    starts = [i for i in range(len(s) - 4) if s[i:i + 4] == BLOCK]
    why = None
    if len(starts) != 1: why = f"가격 차트 블록 {len(starts)}개"
    else:
        i = starts[0]; h2 = [x for x in s if x.startswith("h2:")]
        if s[i + 4] != "div.chartnote:분할 조정 가격": why = f"하단 문구 자리 {s[i + 4]}"
        elif s[i - 1] != "h2:소개": why = f"블록 앞 {s[i - 1]}"
        elif s[i + 5] != "div.intro": why = f"블록 뒤 {s[i + 5]}"
        elif s[i + 6:i + 8] != ["div.rangebar", "div.chartbox{chart,creadout}"]: why = f"설명 상자 뒤 {s[i + 6:i + 8]}"
        elif s[i + 8] != "h2:구성": why = f"M-score 차트 뒤 {s[i + 8]}"
        elif h2 != ["h2:소개", "h2:구성", "h2:기본 정보", "h2:구조 리스크"]: why = f"절 순서 {h2}"
        elif s[:2] != ["nav.top", "h1"]: why = f"머리 {s[:2]}"
    if why: bad.append((f.stem, why))
ok(f"{len(pages)}종 전부: 소개 제목 → 가격 차트 블록 → 설명 상자 → M-score 차트 → 구성 → 기본 정보 → 구조 리스크", not bad, bad[:5])

print(f"{P} PASS / {F} FAIL")
sys.exit(1 if F else 0)
