"""MM-CLOSE-FINAL-20261010 §1 — 링크 대상(기업개요/종합) 선택 단위 테스트(네트워크 없음). python3 tests/test_links.py"""
import sys, json, tempfile, urllib.error
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
import mm_links as K
ok = 0; bad = []
def check(name, cond, detail=""):
    global ok
    if cond: ok += 1; print("PASS", name)
    else: bad.append(name); print("FAIL", name, detail)

STOCK = {"stockEndType": "stock"}; ETF = {"stockEndType": "etf"}; OV = {"summary": "회사 소개"}
check("주식 + 개요 있음 → o", K.judge(STOCK, OV) == ("o", None))
check("ETF → t(etf)", K.judge(ETF, OV) == ("t", "etf"))
check("개요 summary 비어 있음 → t(empty)", K.judge(STOCK, {"summary": "  "}) == ("t", "empty") and K.judge(STOCK, {}) == ("t", "empty"))
check("409 → t(err409)", K.judge(STOCK, 409) == ("t", "err409") and K.judge(409, None) == ("t", "err409"))

def opener(table):
    def f(code, ep):
        v = table[(code, ep)]
        if isinstance(v, int): raise urllib.error.HTTPError("u", v, "x", {}, None)
        if v is None: raise OSError("net")
        return v
    return f
T = {("A.O", "basic"): STOCK, ("A.O", "overview"): OV, ("GDX", "basic"): ETF, ("E.K", "basic"): STOCK, ("E.K", "overview"): {"summary": ""},
     ("X", "basic"): 409, ("N.O", "basic"): None}
check("check_code 주식", K.check_code("A.O", opener(T))["lk"] == "o")
r = K.check_code("GDX", opener(T)); check("check_code ETF 는 개요 호출 없이 종합", r["lk"] == "t" and r["lw"] == "etf")
check("check_code 개요 비어 있음", K.check_code("E.K", opener(T))["lw"] == "empty")
check("check_code 409", K.check_code("X", opener(T))["lw"] == "err409")
r = K.check_code("N.O", opener(T)); check("네트워크 실패는 종합+unchecked, 캐시 안 함(at=None)", r["lk"] == "t" and r["lw"] == "unchecked" and r["at"] is None)
# apply_overview: 코드 없는 항목은 lk 없음, 같은 코드는 한 번만 조회
calls = []
def counting(code, ep): calls.append((code, ep)); return opener(T)(code, ep)
entries = {"P": {"items": [{"t": "A", "nv": "A.O"}, {"t": "G", "nv": "GDX"}, {"t": None, "n": "X"}, {"t": "A", "nv": "A.O", "lk": "x"}]}}
with tempfile.TemporaryDirectory() as d:
    st = K.apply_overview(entries, workers=1, sleep=0, cache_path=Path(d) / "c.json", opener=counting, log=lambda *a: None)
    it = entries["P"]["items"]
    check("lk/lw 채움", it[0]["lk"] == "o" and "lw" not in it[0] and it[1]["lk"] == "t" and it[1]["lw"] == "etf")
    check("코드 없는 항목은 건드리지 않음", "lk" not in it[2])
    check("고유 코드당 1회 조회(basic+overview)", sorted(set(calls)) == sorted(calls) and len(calls) == 3, calls)
    n = len(calls); K.apply_overview(entries, workers=1, sleep=0, cache_path=Path(d) / "c.json", opener=counting, log=lambda *a: None)
    check("캐시 적중 시 재조회 0", len(calls) == n)
    check("통계", st["o"] == 2 and st["t"] == 1 and st["reasons"] == {"etf": 1}, st)
print(f"{ok} PASS, {len(bad)} FAIL"); sys.exit(1 if bad else 0)
