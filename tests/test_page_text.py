"""MM-PAGE-V3.2 §8 종목 소개(intro) 검증·파싱 단위 테스트 — 네트워크·LLM 없음. python3 tests/test_page_text.py"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import mm_page_text as M

ok = 0
bad = []


def check(name, cond, detail=""):
    global ok
    if cond: ok += 1; print("PASS", name)
    else: bad.append(name); print("FAIL", name, detail)


ETF_FIN = {"유형": "ETF", "발행사": "Direxion", "지수 종목 수": 30, "대표 구성 티커": ["INTC", "AMD", "MU", "NVDA", "AVGO"],
           "총보수(연)": "0.75%", "섹터/테마": "반도체"}
ETN_FIN = {"유형": "ETN", "발행사": "BMO MicroSectors", "지수 종목 수": 15, "대표 구성 티커": ["AMD", "PLTR", "META", "MSFT", "MU"],
           "투자자 수수료(연)": "0.95%", "섹터/테마": "FANG·혁신 성장주"}
ETF_OK = ("Direxion이 발행하는 이 ETF는 반도체 지수의 일간 수익률 3배를 추종하는 것을 목표로 한다. "
          "지수는 30개 종목으로 구성되며 대표 구성 티커는 INTC, AMD, MU, NVDA, AVGO이다.\n\n"
          "지수는 반도체 산업에 속한 기업에 노출된다.\n\n"
          "이 상품은 ETF이며 매일 레버리지를 재설정하는 일간 리셋 구조이다. 총보수는 연 0.75%이다.")
ETN_OK = ("BMO MicroSectors가 발행하는 이 ETN은 FANG·혁신 성장주 지수의 일간 수익률을 3배로 따른다. "
          "지수는 15개 종목을 담으며 대표 구성 티커는 AMD, PLTR, META, MSFT, MU이다.\n\n"
          "지수는 성장주 범주에 노출된다.\n\n"
          "이 상품은 ETN이며 일간 리셋 구조이다. 투자자 수수료는 연 0.95%이며 발행사의 무담보 채무로서 발행사 신용에 노출되고 발행사 콜권에 의한 조기상환이 가능하다.")


def V(text, fin, etn, inc="2010-03-11"):
    return M.validate_intro(text, fin, etn, inc, issuer_ok=(fin["발행사"],))


# ---- 문단·문장 파싱
check("문단 분리", M.paragraphs("가.\n\n나. 다.\n\n\n라.") == ["가.", "나. 다.", "라."])
check("소수점은 문장 경계 아님", len(M.sentences("총보수는 연 0.75%이다. 다음 문장이다.")) == 2)
check("US$10bn 마침표 없음", len(M.sentences("편입 하한은 US$10bn 이상이다.")) == 1)
check("마지막 문장 마침표 없이 끝나도 1문장", len(M.sentences("마침표 없는 문장")) == 1)

# ---- 합격
check("ETF 합격", V(ETF_OK, ETF_FIN, False) is None, V(ETF_OK, ETF_FIN, False))
check("ETN 합격", V(ETN_OK, ETN_FIN, True) is None, V(ETN_OK, ETN_FIN, True))

# ---- 불합격
r = V(ETF_OK.replace("총보수는 연 0.75%이다.", "총보수는 연 0.75%이고 운용보수 0.75%이다."), ETF_FIN, False)
check("보수 2회/운용보수 거절", r is not None and ("보수" in r), r)
r = V(ETF_OK.replace("총보수는 연 0.75%이다.", "총보수는 연 0.75%이며 다른 표기도 연 0.75%이다."), ETF_FIN, False)
check("보수 값 2회 출현 거절", r is not None and "출현 2회" in r, r)
r = V(ETF_OK.replace("총보수는 연 0.75%이다.", "총보수는 연 0.75%라고 설명돼 있다."), ETF_FIN, False)
check("인용 투 거절", r is not None and "인용 투" in r, r)
for w in ("명시돼 있다", "밝히고 있다", "알려져 있다"):
    r = V(ETF_OK.replace("노출된다.", f"노출된다고 {w}."), ETF_FIN, False)
    check(f"인용 투 거절: {w}", r is not None and "인용 투" in r, r)
r = V(ETF_OK.replace("일간 리셋 구조이다.", "일간 리셋 구조이며 상장일은 2010-03-11이다."), ETF_FIN, False)
check("상장일 문장 거절", r is not None and "상장일" in r, r)
r = V(ETF_OK + " 상장일은 2010-03-11이다.", ETF_FIN, False)
check("상장일 추가 시 거절(문장 수·날짜)", r is not None)
r = V(ETF_OK.replace("\n\n", " "), ETF_FIN, False)
check("문단 1개 거절", r is not None and "문단 수" in r, r)
r = V("가나다 ETF 일간 0.75% INTC AMD MU 1문장.\n\n둘째.\n\n셋째.\n\n넷째.", ETF_FIN, False)
check("문단 4개 거절", r is not None and "문단 수 4" in r, r)
r = V(ETF_OK.replace("지수는 반도체 산업에 속한 기업에 노출된다.", "지수는 반도체 산업에 속한 기업에 노출된다. 둘째 문장이다. 셋째 문장이다."), ETF_FIN, False)
check("문단당 3문장 거절", r is not None and "문장 수" in r, r)
r = V(ETF_OK.replace("지수는 30개 종목으로 구성되며", "지수는 30개 종목과 55개 하위 항목으로 구성되며"), ETF_FIN, False)
check("입력에 없는 숫자 거절", r is not None and "숫자" in r and "55" in r, r)
r = V(ETN_OK.replace("발행사의 무담보 채무로서 발행사 신용에 노출되고 발행사 콜권에 의한 조기상환이 가능하다", "무담보 채무로서 콜권에 의한 조기상환이 가능하다"), ETN_FIN, True)
check("ETN 발행사 신용 누락 거절", r is not None and "신용" in r, r)
r = V(ETN_OK.replace("조기상환이 가능하다", "상환이 가능하다"), ETN_FIN, True)
check("ETN 조기상환 누락 거절", r is not None and "조기상환" in r, r)
r = V(ETF_OK.replace("일간", "매일"), ETF_FIN, False)
check("일간 누락 거절", r is not None and "일간" in r, r)
r = V(ETF_OK.replace("ETF이며", "상품이며").replace("이 ETF는", "이 상품은"), ETF_FIN, False)
check("ETF 구분어 누락 거절", r is not None and "ETF" in r, r)
r = V(ETF_OK.replace("INTC, AMD, MU, NVDA, AVGO", "INTC, AMD"), ETF_FIN, False)
check("문단1 티커 2개 거절", r is not None and "티커" in r, r)
r = V(ETF_OK.replace("노출된다.", "노출된다. 유망하다."), ETF_FIN, False)
check("금지어 거절", r is not None, r)
r = V(ETF_OK.replace("지수는 반도체 산업에 속한 기업에 노출된다.", "지수는 반도체 소재, 장비, 설계, 패키징, 테스트 기업에 노출된다."), ETF_FIN, False)
check("세부 업종 4개 나열 거절", r is not None and "나열" in r, r)
r = V(ETF_OK.replace("지수는 반도체 산업에 속한 기업에 노출된다.", "지수는 NYSE Semiconductor Index를 따른다."), ETF_FIN, False)
check("영문 지수명 거절", r is not None and "영문" in r, r)
r = V(ETF_OK.replace("반도체 지수", "국내 반도체 지수"), ETF_FIN, False)
check("'국내' 거절", r is not None and "국내" in r, r)
r = V(ETF_OK.replace("INTC, AMD, MU, NVDA, AVGO", "INTC, AMD, MU, NVDA, ZZZZ"), ETF_FIN, False)
check("입력에 없는 티커 거절", r is not None and "ZZZZ" in r, r)

# ---- 입력 보강(facts)
P = M.load_products()
f = M.facts(P["SOXL"], "Direxion")
check("SOXL 보수 단일값", f.get("총보수(연)") == "0.75%" and "비용 요약" not in f and "상장일" not in f, f)
check("SOXL 입력에 면제 전 보수(0.91) 없음", "0.91" not in str(f), "")
fb = M.facts(P["BULZ"], "BMO MicroSectors")
check("BULZ 투자자 수수료 단일값·금융비용 없음", fb.get("투자자 수수료(연)") == "0.95%" and "금융비용" not in str(fb), fb)
check("BULZ 대표 티커 매핑", fb["대표 구성 티커"][:3] == ["AMD", "PLTR", "META"], fb["대표 구성 티커"])
check("SMHU 면제 후 값 0.70%", M.fee_single(P["SMHU"]) == "0.70%", M.fee_single(P["SMHU"]))
check("ETN 은 발행사 신용·조기상환 사실 포함", all(k in fb for k in ("발행사 신용", "조기상환")))
check("모든 상품 보수·티커 3개 이상", all(M.fee_single(p) and len(M.rep_tickers(p)) >= 3 for p in P.values()))

# ---- 해시: 필드 해시 보존·소개 해시는 상장일에 무관
h1 = M.intro_hash(P["SOXL"], "Direxion")
import copy
p2 = copy.deepcopy(P["SOXL"]); p2["inception"]["date"] = "1999-01-01"
check("소개 해시는 상장일 변경에 불변", M.intro_hash(p2, "Direxion") == h1)
p3 = copy.deepcopy(P["SOXL"]); p3["fee"]["net_pct"] = 0.5
check("소개 해시는 보수 변경에 반응", M.intro_hash(p3, "Direxion") != h1)
p4 = copy.deepcopy(P["SOXL"]); p4["fee"]["gross_pct"] = 5.0
check("소개 해시는 면제 전 보수에 불변", M.intro_hash(p4, "Direxion") == h1)

print(f"\n{ok} passed, {len(bad)} failed", bad if bad else "")
sys.exit(1 if bad else 0)
