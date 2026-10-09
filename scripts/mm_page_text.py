#!/usr/bin/env python3
"""투자자용 종목 페이지 문구 생성 — data/products.yaml(사실 필드) → data/products_page.json.

표시층 전용(MM-PAGE-V3-DESIGN-20261010 §4). 매매·점수 계산과 무관하며 compute/판정 규칙을 건드리지 않는다.
- 구성 방식 한 줄 · 소개 2~3문단·4~6문장(V3.2 §8: 문단1 무엇을 따르나 / 문단2 지수 성격 / 문단3 구조·비용, '\n\n' 구분) · 구조 리스크 1~2줄 · ETN 비용 한 줄 = LLM(claude -p, mm_products_gen 과 같은 호출·금지어 검증)
- 상위 구성 5종 · 기본 정보 · 섹터 한 줄 = 코드가 products.yaml 에서 직접 뽑는다(LLM 미사용)
- 입력(products.yaml 의 해당 종목 사실 필드)이 바뀐 종목만 재생성하고 '마지막 수정일'을 그 날짜로 갱신한다. 안 바뀌면 호출 0.
- 소개(intro)와 construction/risk/fee 는 입력 해시가 따로다(hash = 필드용 pg3 공식, intro_hash = 소개용). --force 는 소개만, --force-fields 는 필드까지 재생성.
사용: python3 scripts/mm_page_text.py [--no-llm] [--only SOXL,BULZ] [--force] [--force-fields]
"""
import sys, os, re, json, hashlib, datetime, argparse, concurrent.futures as cf
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "products_page.json"
LOGDIR = ROOT / ".local" / "page_text_attempts"
PROMPT_VERSION = "pg4"          # intro(소개) 프롬프트·검증 버전. construction/risk/fee 는 FIELDS_VERSION 으로 따로 관리
FIELDS_VERSION = "pg3"          # construction/risk/fee 입력 해시 버전(V3.2 §8 은 intro 만 재생성 — 기존 해시와 동일하게 유지)
ISSUER_SHORT = {"Direxion": "Direxion", "ProShares": "ProShares"}
# ETN 상위 구성은 products.yaml 에 회사명만 있어(symbol 없음) 소개 문단1 의 대표 티커용으로만 코드가 매핑한다. 매핑 없는 이름은 제외.
NAME2TICKER = {
    "ADVANCED MICRO DEVICES": "AMD", "AMERICAN AIRLINES GROUP INC": "AAL", "BOOKING HOLDINGS INC": "BKNG", "BROADCOM INC": "AVGO",
    "CHEVRON CORP": "CVX", "CITIGROUP INC": "C", "CONOCOPHILLIPS": "COP", "EOG RESOURCES INC": "EOG", "EXXONMOBIL HOLDINGS CORP": "XOM",
    "GOLDMAN SACHS GROUP INC": "GS", "JPMORGAN CHASE & CO": "JPM", "MARATHON PETROLEUM CORP": "MPC", "MARVELL TECHNOLOGY INC": "MRVL",
    "META PLATFORMS INC-CLASS A": "META", "MICRON TECHNOLOGY INC": "MU", "MICROSOFT CORP": "MSFT", "MORGAN STANLEY": "MS",
    "NVIDIA CORP": "NVDA", "PALANTIR TECHNOLOGIES INC-A": "PLTR", "PHILLIPS 66": "PSX", "ROYAL CARIBBEAN CRUISES LTD": "RCL",
    "SLB LTD": "SLB", "SPACE EXPLORATION TECHN-CL A": "SPCX", "TAIWAN SEMICONDUCTOR-SP ADR": "TSM", "UBER TECHNOLOGIES INC": "UBER", "US BANCORP": "USB",
    "VALERO ENERGY CORP": "VLO", "WALT DISNEY CO/THE": "DIS",
}
NOT_STOCK = {"XTSLA"}           # 1x ETF 보유표의 현금성 항목 — 대표 구성 티커에서 제외


def _gen():
    import mm_products_gen as G          # call_llm·violations·MODEL 재사용(같은 금지어 목록)
    return G


def load_products():
    d = yaml.safe_load(open(DATA / "products.yaml", encoding="utf-8"))
    return d["products"]


def sector_line(p):
    """섹터/테마 한 줄 — 끝에 붙은 영문 지수명 괄호만 제거(한글이 든 괄호는 구성 설명이라 유지)."""
    s = str(p.get("sector_theme") or "").strip()
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", s)
    if m and not re.search(r"[가-힣]", m.group(2)):
        s = m.group(1).strip()
    return s


def top5(p):
    tc = p.get("top_constituents")
    if not isinstance(tc, dict):
        return {"items": [], "basis": ""}
    items = []
    for i in (tc.get("items") or [])[:5]:
        items.append({"name": str(i.get("symbol") or i.get("name") or ""), "w": i.get("weight_pct")})
    basis = str(tc.get("basis") or "")
    m = re.search(r"1x ETF ([A-Z0-9]+)", basis)
    if m:
        b = f"1x ETF {m.group(1)} 보유 기준"
    elif "ETF" in basis and "구성" not in basis:
        b = "구성 ETF 보유 기준"
    else:
        b = "지수 구성종목 기준"
    return {"items": items, "basis": b, "as_of": str(tc.get("as_of") or "").split(" ")[0]}


def facts_fields(p):
    """construction/risk/fee 용 사실 필드(pg3 와 동일 — 입력 해시가 바뀌지 않도록 손대지 않는다)."""
    c = p.get("construction") or {}
    t5 = top5(p)
    ws = [i["w"] for i in t5["items"] if isinstance(i.get("w"), (int, float))]
    f = {
        "유형": p["type"], "발행사": ISSUER_SHORT.get(p["issuer"].split()[0], p["issuer"]),
        "배수": p["leverage"], "섹터/테마": sector_line(p),
        "지수 가중방식": c.get("weighting"), "리밸런스": c.get("rebalance"), "지수 종목 수": c.get("n_constituents"),
        "상위 구성(비중%)": [f"{i['name']} {i['w']}" for i in t5["items"]], "상위 구성 기준": t5["basis"],
        "상위 5종 비중 합계(%)": round(sum(ws), 2) if len(ws) == 5 else None,
        "비용 요약": (p.get("fee") or {}).get("summary"),
        "구조 사실": [s.get("fact") for s in (p.get("structural_risk") or [])],
        "상장일": (p.get("inception") or {}).get("date"),
    }
    if c.get("selection_rule"): f["종목 선정 규칙"] = c["selection_rule"]
    if c.get("capping"): f["비중 상한 규칙"] = c["capping"]
    if c.get("description"): f["지수 설명"] = c["description"]
    ch = (p.get("fee") or {}).get("changes") or []
    if ch: f["금융비용 변경 이력"] = [f"{x.get('date')} {x.get('event')}" for x in ch]
    lt = (p.get("top_constituents") or {}).get("lookthrough")
    if lt: f["구성 ETF 상위 보유"] = {x["etf"]: [f"{i['symbol']} {i['weight_pct']}" for i in x["items"]] for x in lt}
    return f


def fee_single(p):
    """소개용 총보수 단일 값 문자열('0.75%'). ETF = 면제 후 net_pct(면제 전 gross 는 소개 입력에서 뺀다), ETN = 투자자 수수료 연 X% 한 값.
    ETN 은 summary 의 '투자자 수수료 … 연 X%' 첫 값(면제 후 값이 먼저 오는 표기) — 금융비용 등 부가 설명은 가져오지 않는다."""
    fee = p.get("fee") or {}
    if p["type"] == "ETF":
        return f"{fee['net_pct']:.2f}%" if fee.get("net_pct") is not None else None
    m = re.search(r"투자자 수수료[^+]*?연 (\d+(?:\.\d+)?)%", str(fee.get("summary") or ""))
    return f"{m.group(1)}%" if m else None


def rep_tickers(p, limit=5):
    """대표 구성 티커(최대 5개) — top_constituents.items 의 symbol, 없으면(ETN) NAME2TICKER 매핑, 구성 ETF 보유(look-through)가 있으면 그 symbol.
    공백 포함 코드·현금성 항목만 제외한다. 한 글자 티커(C·V 등)도 포함한다(V3.2 오너 지시 — 단어 경계 검사는 영문자·숫자·하이픈 인접 여부로 식별)."""
    tc = p.get("top_constituents") or {}
    ok = lambda s: bool(s) and " " not in s and s not in NOT_STOCK
    lt = tc.get("lookthrough")
    if lt:
        cols = [[i["symbol"] for i in x["items"] if ok(i.get("symbol"))] for x in lt]
    else:
        cols = [[(i.get("symbol") or NAME2TICKER.get(i.get("name"), "")) for i in (tc.get("items") or [])[:5]]]
        cols = [[s for s in cols[0] if ok(s)]]
    out = []
    for k in range(5):
        for col in cols:
            if k < len(col) and col[k] not in out and len(out) < limit: out.append(col[k])
    return out


def index_count(c):
    n = c.get("n_constituents")
    if isinstance(n, int): return n
    m = re.match(r"^\s*(\d[\d,]*)\s*(?:\(497K 서술\))?\s*$", str(n))
    return int(m.group(1).replace(",", "")) if m else n


def facts(p, issuer_uni=None):
    """소개(intro) 입력 사실 필드(V3.2 §8). 보수는 단일 값, 상장일·면제 전 보수·상위 비중은 넣지 않는다."""
    c = p.get("construction") or {}
    etn = p["type"] == "ETN"
    f = {"유형": p["type"], "발행사": issuer_uni or ISSUER_SHORT.get(p["issuer"].split()[0], p["issuer"]), "배수": p["leverage"], "섹터/테마": sector_line(p),
         "지수 가중방식": c.get("weighting"), "지수 종목 수": index_count(c), "대표 구성 티커": rep_tickers(p)}
    lt = (p.get("top_constituents") or {}).get("lookthrough")
    if lt: f["구성 ETF 티커"] = [x["etf"] for x in lt]
    for k, src in (("종목 선정 규칙", "selection_rule"), ("비중 상한 규칙", "capping"), ("지수 설명", "description")):
        if c.get(src) and not str(c[src]).startswith("[부재]"): f[k] = c[src]
    f["투자자 수수료(연)" if etn else "총보수(연)"] = fee_single(p)
    sf = " ".join(str(s.get("fact")) for s in (p.get("structural_risk") or []))
    if etn:
        if "무담보" in sf: f["발행사 신용"] = "ETN 은 발행사의 선순위 무담보 채무이며 발행사 신용위험에 노출된다"
        if "콜권" in sf and "조기상환" in sf: f["조기상환"] = "발행사 콜권이 있고 투자자 조기상환이 가능하다"
    else:
        f["일간 리셋"] = "매일 레버리지를 재설정해 지수 일간 수익률의 3배를 추종하는 것을 목표로 한다"
    return f


def basic_info(p, issuer_uni):
    fee = p.get("fee") or {}
    if p["type"] == "ETF" and fee.get("net_pct") is not None:
        g, n = fee.get("gross_pct"), fee.get("net_pct")
        fee_txt = f"연 {n:g}%" + (f" (면제 전 {g:g}%)" if g is not None and abs(g - n) > 1e-9 else "")
    else:
        fee_txt = None            # ETN 은 LLM 한 줄(투자자 수수료 + 금융비용)
    lev = re.match(r"\s*(\d+(?:\.\d+)?)x", str(p.get("leverage") or ""))
    return {"issuer": issuer_uni, "type": p["type"], "leverage": (lev.group(1) + "배(일간)") if lev else str(p.get("leverage")),
            "fee": fee_txt, "inception": (p.get("inception") or {}).get("date")}


PROMPT_FIELDS = """아래 [사실]은 3배 레버리지 ETF/ETN 한 종목의 발행사 공시 기반 사실 필드다. 투자자용 종목 페이지 문구를 JSON 한 개로 작성하라.

출력 형식(JSON 만, 코드펜스·설명 금지):
{{"construction": "...", "risk": ["..."], "fee": "..."}}

규칙(공통):
- [사실]에 없는 내용·수치·날짜는 절대 쓰지 말 것(추측·일반 상식·외부 지식·계산 금지). 숫자·날짜·이름은 입력 그대로.
- 전망·평가·권고·추측 표현 금지. 사용 금지 어휘: 추천, 유망, 전망, 기대, 매력, 우수, 좋은, 유리, 불리, 매수, 매도, 투자하, 예상, 권장, 적합, 가능성,
  안정적, '~할 것이다', '~로 보인다', '~일 것', '위험이 낮/적/크'. 서술문('~이다', '~한다', '~로 명시돼 있다', '~할 수 있다')으로만 쓴다.
- 공식 지수의 영문 명칭은 쓰지 말 것(섹터/테마의 한국어 표기로 지칭). 영문 약어는 [사실]에 나온 티커·종목명만 허용.
- 마크다운·불릿 금지.
- 금액(달러·억·조)과 시가총액 범위는 쓰지 말 것(단위 환산 오류 방지). 비율(%)·종목 수·날짜만 입력 그대로 쓴다.

필드별 규칙:
- construction: 한 줄(한 문장, 80자 안팎). '가중 방식 · 종목 수 · 리밸런스 주기' 순서로 가운뎃점(·)으로 잇는다. 예: "유동주식 시가총액 가중 · 30종목 · 분기 리밸런스". 사실에 없는 항목은 생략.
- risk: 1~2개(한 항목 한 문장). ETN 이면 첫 항목에 발행사 신용(무담보 채무)과 발행사 콜·조기상환 관련 사실, 그리고 [사실]에 '금융비용 변경 이력'이 있으면 마지막 항목에 그 변경(날짜·값 그대로) 1줄. ETF 이면 첫 항목에 일간 리셋·1일 초과 보유 시 지수 3배와 달라질 수 있다는 공시 문구 취지 1줄, 구조 사실에 지수(추종 목표) 변경 이력이 있으면 그 날짜와 함께 1줄.
- fee: ETN 만. 투자자 수수료와 금융비용(기준금리+스프레드, 상한·인상 여부)을 한 줄로. ETF 이면 빈 문자열 "".

[사실]
{facts}
"""

PROMPT_INTRO = r"""아래 [사실]은 3배 레버리지 ETF/ETN 한 종목의 발행사·지수 제공사 공시 기반 사실 필드다. 투자자용 종목 소개를 JSON 한 개로 작성하라.

출력 형식(JSON 만, 코드펜스·설명 금지):
{{"intro": "문단1\n\n문단2\n\n문단3"}}

형식: 문단 정확히 3개(문단 사이는 빈 줄 하나, 문자열 안에서는 \n\n), 문단당 1~2문장, 전체 4~6문장. 각 문장은 마침표로 끝낸다. 한 문장은 한 번의 서술로 끝내고 길게 이어 붙이지 않는다. 문단1 의 두 문장은 줄바꿈 없이 이어서 한 문단으로 쓴다(문단이 4개가 되면 안 된다).
- 문단1 (무엇을 따르나, 2문장): 첫 문장 = 이 상품이 어떤 지수·섹터를 일간 3배로 따르는지(발행사 표기는 [사실]의 '발행사' 그대로). 둘째 문장 = 지수의 구성 요지(종목 수·가중 방식)와 대표 구성 티커 3~5개를 [사실]의 '대표 구성 티커'에서 골라 그대로. '구성 ETF 티커'가 있으면 그 ETF 를 따르는 지수임을 쓰고, 티커는 그 ETF 가 담은 대표 보유 종목이라고 쓴다(지수 종목 수는 ETF 개수로 서술).
- 문단2 (지수 성격, 1~2문장): '지수 설명'·'종목 선정 규칙'·'비중 상한 규칙'·섹터/테마·종목 수에 적힌 범위 안에서 지수가 어떤 산업·요인에 노출되는지를 쓴다. 세부 하위업종·하위 부문 이름(예: 업스트림·다운스트림·소재·장비 같은 분류명)·기술 분류·개별 종목 목록은 아예 쓰지 않고 '하위 부문별 목표 비중이 있다' 정도로만 요약한다. 쉼표/가운뎃점으로 항목을 나열하지 않는다(한 문장에 쉼표로 이은 항목은 최대 2개). 선정 규칙이 길면 요지 한 구절로만 쓴다. 경기·금리·유가 같은 영향 요인은 [사실]에 직접 적혀 있을 때만 쓴다. [사실]에 없는 수식어(대형·성장·고성장·글로벌 등)와 [사실]에 직접 없는 배제·제외 서술(예: '비상장 제외')을 붙이지 않는다. 지수 움직임의 방향·수준은 쓰지 않는다.
- 문단3 (구조·비용, 정확히 2문장): 첫 문장은 반드시 '이 상품은 ETF이며' 또는 '이 상품은 ETN이며'로 시작하고, 그 안에 구분 + 매일 레버리지를 재설정하는 일간 리셋 구조. 둘째 문장 = ETF 이면 "총보수는 연 X%이다." 형태로 [사실]의 '총보수(연)' 값 하나만 한 번. ETN 이면 둘째 문장에서 '투자자 수수료는 연 X%'(값은 '투자자 수수료(연)' 하나만 한 번)를 쓰고, 이어서 같은 문장 또는 앞 문장에 발행사 신용(무담보 채무)에 노출된다는 점과 발행사 콜권에 의한 조기상환 가능을 담되, 문단3 전체가 2문장을 넘지 않게 한다. 다른 보수·금융비용·면제·운용보수·면제 전 수치는 쓰지 않는다. ETF 이면 ETN 관련 서술을 쓰지 않는다.

규칙:
- [사실]에 없는 내용·수치·날짜는 절대 쓰지 말 것(추측·일반 상식·외부 지식·계산 금지). 숫자·이름은 입력 그대로. 상장일·기준일 날짜는 쓰지 않는다.
- 단정형 서술('~이다', '~한다', '~에 노출된다')으로만 쓴다. '설명돼 있다', '명시돼 있다', '밝히고 있다', '알려져 있다', '~에 따르면' 같은 인용 투 금지.
- 전망·평가·권고·추측 금지. 사용 금지 어휘: 추천, 유망, 전망, 기대, 매력, 우수, 좋은, 유리, 불리, 매수, 매도, 투자하, 예상, 권장, 적합, 가능성, 안정적, '~할 것이다', '~로 보인다', '~일 것', '위험이 낮/적/크'.
- 지수의 영문 공식 명칭·지수 제공사 영문명(예: S&P, Dow Jones, S-Network 등)·영문 구·문장은 쓰지 말 것(섹터/테마의 한국어 표기로 지칭). 영문은 [사실]에 나온 티커와 발행사 표기만 허용. '투자하'로 시작하는 어휘(투자하는 등)는 쓰지 말 것.
- 미국 지수·미국 기업은 '미국'으로 쓰고 '국내'라고 쓰지 말 것(국내 = 한국으로 오해된다).
- 같은 사실을 두 번 쓰지 말 것. 마크다운·불릿 금지. 금액(달러·억·조)·시가총액 범위는 쓰지 말 것.

[사실]
{facts}
"""


MONTHS = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"])}


def iso_dates(s):
    """'August 25, 2021' → '2021-08-25' (LLM 이 '2021년 8월 25일'로 옮겨 쓰는 숫자를 입력과 맞추려는 정규화)"""
    return re.sub(r"\b(" + "|".join(MONTHS) + r")\.? (\d{1,2}), (\d{4})\b", lambda m: f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}", str(s))


def _nums(s):
    """숫자 토큰 집합(선행 0 제거 — '08'과 '8'을 같게 본다). '100%'·'300%' 는 공시의 목표 비율 표기라 따로 허용."""
    return set(str(float(x)).rstrip("0").rstrip(".") if "." in x else str(int(x)) for x in re.findall(r"\d+(?:\.\d+)?", str(s).replace(",", "")))


def _num_check(texts, fin_text):
    """입력에 없는 숫자 토큰 목록('100%'·'300%' 공시 표기 제외, 영문 월 이름이 입력에 있으면 월 번호 허용)."""
    allowed = _nums(fin_text) | {"1", "3"}
    if re.search("|".join(MONTHS), fin_text):
        allowed |= {str(i) for i in range(1, 13)}
    out_txt = re.sub(r"\b(100|300)%", "", " ".join(texts))
    return sorted(n for n in _nums(out_txt) if n not in allowed)


def validate_fields(out, fin_text, is_etn, has_changes):
    """construction/risk/fee 검증(신규 상품 경로용). 통과하면 None, 아니면 사유 문자열."""
    if not isinstance(out, dict): return "JSON 객체 아님"
    for k in ("construction", "risk", "fee"):
        if k not in out: return f"키 누락 {k}"
    if not isinstance(out["risk"], list) or not (1 <= len(out["risk"]) <= 2): return "risk 1~2개 아님"
    texts = [out["construction"], out["fee"]] + out["risk"]
    if any((not isinstance(x, str)) for x in texts): return "문자열 아닌 값"
    if not out["construction"].strip() or any(not x.strip() for x in out["risk"]): return "빈 항목"
    if is_etn and not out["fee"].strip(): return "ETN fee 비어 있음"
    v = _gen().violations(" ".join(texts))
    if v: return "금지어 " + ",".join(v)
    bad = _num_check(texts, fin_text)
    if bad: return "입력에 없는 숫자 " + ",".join(bad)
    if has_changes and not any(re.search(r"\d{4}-\d{2}-\d{2}", r) for r in out["risk"]): return "금융비용 변경 이력 미반영"
    return None


QUOTE_RE = re.compile(r"설명돼|설명되|명시돼|명시되|밝히|알려져|알려진|기재돼|기재되|서술돼|서술되|언급돼|언급되|공시돼|공시되|따르면|의하면|라고 한다|라고 하며")
EN_PHRASE_RE = re.compile(r"\b[A-Za-z][A-Za-z&.'-]*(?: [A-Za-z][A-Za-z&.'-]*)+\b")      # 영문 2단어 이상 연속(지수 공식명·영문 구)
_ITEM = r"[^,，、·.\s]+(?: [^,，、·.\s]+)?"
LIST_RE = re.compile(rf"(?:{_ITEM}\s*[,，、·]\s*){{3,}}{_ITEM}")      # 항목 4개 이상 연속 나열
SENT_END = re.compile(r"(?<=[.])(?:\s+|$)")


def paragraphs(text):
    return [x.strip() for x in re.split(r"\n\s*\n", str(text).strip()) if x.strip()]


def sentences(par):
    """마침표 분리 — 소수점('0.75%')·'US$10bn' 처럼 마침표 뒤가 공백/끝이 아닌 경우는 문장 경계가 아니다."""
    return [x for x in SENT_END.split(par.strip()) if x.strip()]


def pct_count(text, val):
    """text 안에서 보수 값(val='0.75%')과 같은 크기의 퍼센트 표기 출현 횟수."""
    v = float(val.rstrip("%"))
    return sum(1 for m in re.finditer(r"(?<![\d.])(\d+(?:\.\d+)?)\s*%", text) if abs(float(m.group(1)) - v) < 1e-9)


def validate_intro(intro, fin, is_etn, inception=None, issuer_ok=()):
    """소개(intro) 검증(V3.2 §8). 통과하면 None, 아니면 사유 문자열. fin = 입력 사실 dict(facts() 의 날짜 정규화본)."""
    if not isinstance(intro, str) or not intro.strip(): return "intro 비어 있음/문자열 아님"
    pars = paragraphs(intro)
    if not (2 <= len(pars) <= 3): return f"문단 수 {len(pars)} (2~3 아님)"
    per = [len(sentences(x)) for x in pars]
    for i, n in enumerate(per, 1):
        if not (1 <= n <= 2): return f"문단{i} 문장 수 {n} (1~2 아님)"
    if not (4 <= sum(per) <= 6): return f"전체 문장 수 {sum(per)} (4~6 아님)"
    if "\n" in "".join(pars): return "문단 내부 줄바꿈"
    if re.search(r"[*#`]|^\s*[-•]", intro, re.M): return "마크다운/불릿"
    v = _gen().violations(intro)
    if v: return "금지어 " + ",".join(v)
    q = sorted(set(m.group(0) for m in QUOTE_RE.finditer(intro)))
    if q: return "인용 투 " + ",".join(q)
    if "상장일" in intro or re.search(r"\d{4}-\d{2}-\d{2}", intro) or (inception and str(inception) in intro): return "상장일/날짜 포함"
    fin_text = json.dumps(fin, ensure_ascii=False)
    bad = _num_check([intro], fin_text)
    if bad: return "입력에 없는 숫자 " + ",".join(bad)
    # 보수: 단일 값이 정확히 1번
    fee = fin.get("투자자 수수료(연)" if is_etn else "총보수(연)")
    if fee:
        n = pct_count(intro, fee)
        if n != 1: return f"보수 {fee} 출현 {n}회 (정확히 1회 아님)"
    if "금융비용" in intro or "면제" in intro or "운용보수" in intro: return "금융비용/면제/운용보수 서술(보수 단일 값 규칙 위반)"
    # 구분어·일간 리셋·ETN 신용/조기상환
    typ = "ETN" if is_etn else "ETF"
    if typ not in intro: return f"{typ} 구분 단어 없음"
    if not is_etn and "ETN" in intro: return "ETF 소개에 ETN 단어 포함"
    if "일간" not in intro: return "일간 리셋 언급 없음"
    if any("3배" in q for q in pars[1:]): return "문단1 밖에서 '3배' 재서술(같은 사실 반복 — 3배 추종은 문단1에서만)"
    if is_etn:
        if "발행사" not in intro or "신용" not in intro: return "ETN 발행사 신용 언급 없음"
        if "조기상환" not in intro: return "ETN 조기상환 언급 없음"
    # 문단1 티커 3개 이상
    tk = [t for t in (fin.get("대표 구성 티커") or [])]
    hit = sorted(t for t in set(tk) | set(fin.get("구성 ETF 티커") or []) if re.search(rf"(?<![A-Za-z0-9-]){re.escape(t)}(?![A-Za-z0-9-])", pars[0]))
    need = min(3, len(set(tk)))
    if len(hit) < need: return f"문단1 티커 {len(hit)}개 (3개 이상 필요)"
    # 입력 밖 영문 약어/티커 금지
    allowed_caps = set(tk) | set(fin.get("구성 ETF 티커") or []) | {"ETF", "ETN", "AI", "LED", "OLED", "IT", "REIT", "KRX"} | set(re.findall(r"\b[A-Z][A-Z0-9]{1,}\b", fin_text))
    caps = sorted(set(re.findall(r"(?<![A-Za-z])[A-Z]{2,6}(?![A-Za-z])", intro)) - allowed_caps)
    if caps: return "입력에 없는 영문 약어/티커 " + ",".join(caps)
    # 영문 지수 공식명·구
    for m in EN_PHRASE_RE.finditer(intro):
        if m.group(0) not in issuer_ok: return "영문 구/지수명 " + m.group(0)
    if "국내" in intro: return "'국내' 사용(미국 지수는 '미국'으로 표기)"
    # 세부 하위업종 나열: 문단2 안에서 짧은 항목(두 단어 이하) 4개 이상이 쉼표/가운뎃점으로 연달아 나열
    if len(pars) > 1 and LIST_RE.search(pars[1]): return "문단2 세부 항목 나열(4개 이상 연속)"
    return None


def _json_from(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    a, b = t.find("{"), t.rfind("}")
    return json.loads(t[a:b + 1])


def input_hash(p, issuer_uni):
    """construction/risk/fee 입력 해시 — pg3 공식 그대로(저장된 기존 해시와 일치해야 필드가 재생성되지 않는다)."""
    blob = json.dumps([FIELDS_VERSION, facts_fields(p), top5(p), basic_info(p, issuer_uni), (p.get("inception") or {}).get("date")], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def intro_hash(p, issuer_uni):
    """소개 입력 해시 — facts()(상장일·면제 전 보수 제외)만 반영."""
    blob = json.dumps([PROMPT_VERSION, facts(p, issuer_uni)], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _norm_facts(f):
    return json.loads(iso_dates(json.dumps(f, ensure_ascii=False)))


def _retry(prompt_fn, check, label, t, stats):
    """공통 재시도 루프(최대 5회). 반환 (out, 시도수, attempts)."""
    G = _gen()
    attempts, prompt = [], prompt_fn(None)
    for n in range(1, 6):
        try:
            out = _json_from(G.call_llm(prompt))
        except Exception as e:
            attempts.append({"n": n, "error": str(e)[:200]}); stats["errors"] += 1; continue
        why = check(out)
        attempts.append({"n": n, "out": out, "invalid": why})
        if why is None: return out, n, attempts
        stats["invalid"] += 1
        prompt = prompt_fn(why)
    return None, len(attempts), attempts


def gen_intro(t, p, issuer_uni, stats):
    fin = _norm_facts(facts(p, issuer_uni))
    base = PROMPT_INTRO.format(facts=json.dumps(fin, ensure_ascii=False, indent=1))
    pf = lambda why: base if why is None else base + f"\n[직전 출력이 검증에서 거절됨: {why}. 같은 실수를 반복하지 말고 형식·규칙대로 다시 작성하라.]"
    def check(out):
        if not isinstance(out, dict) or "intro" not in out: return "intro 키 누락"
        return validate_intro(out["intro"], fin, p["type"] == "ETN", (p.get("inception") or {}).get("date"), issuer_ok=(fin["발행사"],))
    out, n, att = _retry(pf, check, "intro", t, stats)
    LOGDIR.mkdir(parents=True, exist_ok=True)
    json.dump({"ticker": t, "kind": "intro", "attempts": att}, open(LOGDIR / f"{t}.intro.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return (out["intro"].strip() if out else None), n


def gen_fields(t, p, issuer_uni, stats):
    """construction/risk/fee — 신규 상품(기존 문구 없음)이거나 입력 해시가 바뀐 종목만."""
    fin = _norm_facts(facts_fields(p))
    fin_text = json.dumps(fin, ensure_ascii=False)
    base = PROMPT_FIELDS.format(facts=json.dumps(fin, ensure_ascii=False, indent=1))
    has_changes = bool(fin.get("금융비용 변경 이력"))
    pf = lambda why: base if why is None else base + f"\n[직전 출력이 검증에서 거절됨: {why}. 같은 실수를 반복하지 말고 규칙대로 다시 작성하라. risk 는 1~2개, [사실]에 없는 숫자는 쓰지 말 것.]"
    out, n, att = _retry(pf, lambda o: validate_fields(o, fin_text, p["type"] == "ETN", has_changes), "fields", t, stats)
    LOGDIR.mkdir(parents=True, exist_ok=True)
    json.dump({"ticker": t, "kind": "fields", "attempts": att}, open(LOGDIR / f"{t}.fields.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out, n


def ensure(use_llm=True, only=None, force=False, force_fields=False, today=None, issuers=None, log=print):
    """products.yaml 에서 바뀐 종목만 재생성. 반환 stats. LLM 실패 시 기존 문구 유지(+ failed 목록).
    소개(intro)와 construction/risk/fee 는 입력 해시가 따로다 — 소개만 바뀌면 intro 만 새로 쓰고 나머지 필드는 그대로 둔다.
    force = 소개 전부 재생성, force_fields = construction/risk/fee 까지 재생성."""
    today = today or datetime.date.today().isoformat()
    prods = load_products()
    cur = json.load(open(OUT, encoding="utf-8")) if OUT.exists() else {"meta": {}, "items": {}}
    items = cur.get("items", {})
    if issuers is None:
        import pandas as pd
        issuers = dict(pd.read_csv(DATA / "universe.csv")[["ticker", "issuer"]].values)
    stats = {"changed": [], "kept": 0, "failed": [], "errors": 0, "invalid": 0}
    todo = []
    for t, p in prods.items():
        if only and t not in only: continue
        iu = issuers.get(t, p["issuer"].split()[0])
        old = items.get(t) or {}
        h, ih = input_hash(p, iu), intro_hash(p, iu)
        need_fields = force_fields or not old.get("text") or old.get("hash") != h
        need_intro = force or force_fields or need_fields or old.get("intro_hash") != ih
        if not (need_fields or need_intro):
            stats["kept"] += 1
            continue
        todo.append((t, p, iu, h, ih, need_fields, need_intro))
    if todo and not use_llm:
        stats["failed"] = [x[0] for x in todo]
        log(f"[page_text] LLM 미실행: 재생성 필요 {len(todo)}종 {stats['failed']}")
    elif todo:
        def work(t, p, iu, need_fields, need_intro):
            fields, intro, n1, n2 = None, None, 0, 0
            if need_fields:
                fields, n1 = gen_fields(t, p, iu, stats)
                if fields is None: return None, None, n1, n2
            if need_intro:
                intro, n2 = gen_intro(t, p, iu, stats)
                if intro is None: return fields, None, n1, n2
            return fields, intro, n1, n2
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(work, t, p, iu, nf, ni): (t, p, iu, h, ih, nf, ni) for t, p, iu, h, ih, nf, ni in todo}
            for f in cf.as_completed(futs):
                t, p, iu, h, ih, nf, ni = futs[f]
                fields, intro, n1, n2 = f.result()
                if (nf and fields is None) or (ni and intro is None):
                    stats["failed"].append(t); log(f"[page_text] {t} 생성 실패(기존 유지) 시도 fields={n1} intro={n2}"); continue
                it = items.setdefault(t, {"text": {}})
                txt = dict(it.get("text") or {})
                if nf: txt.update({k: fields[k] for k in ("construction", "risk", "fee")}); it["hash"] = h
                if ni: txt["intro"] = intro; it["intro_hash"] = ih
                it["text"] = {k: txt[k] for k in ("construction", "intro", "risk", "fee")}
                it["modified"] = today
                stats["changed"].append(t); log(f"[page_text] {t} 생성 완료 시도 fields={n1} intro={n2}")
    # 코드가 직접 뽑는 값(상위 구성·기본 정보·섹터)은 매번 현재 products.yaml 로 갱신 — 입력 해시에 포함돼 있어 바뀌면 위에서 재생성됨
    for t, p in prods.items():
        if t in items:
            iu = issuers.get(t, p["issuer"].split()[0])
            items[t]["sector"] = sector_line(p); items[t]["top5"] = top5(p); items[t]["basic"] = basic_info(p, iu)
    meta = {"prompt_version": PROMPT_VERSION, "model": _gen().MODEL, "count": len(items), "generated": today}
    json.dump({"meta": meta, "items": items}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true"); ap.add_argument("--force", action="store_true"); ap.add_argument("--force-fields", action="store_true"); ap.add_argument("--only", default="")
    a = ap.parse_args()
    s = ensure(use_llm=not a.no_llm, only=set(filter(None, a.only.split(","))) or None, force=a.force, force_fields=a.force_fields)
    print(json.dumps(s, ensure_ascii=False))
    sys.exit(1 if s["failed"] else 0)
