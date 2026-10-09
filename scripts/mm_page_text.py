#!/usr/bin/env python3
"""투자자용 종목 페이지 문구 생성 — data/products.yaml(사실 필드) → data/products_page.json.

표시층 전용(MM-PAGE-V3-DESIGN-20261010 §4). 매매·점수 계산과 무관하며 compute/판정 규칙을 건드리지 않는다.
- 구성 방식 한 줄 · 특징 3줄 · 구조 리스크 1~2줄 · ETN 비용 한 줄 = LLM(claude -p, mm_products_gen 과 같은 호출·금지어 검증)
- 상위 구성 5종 · 기본 정보 · 섹터 한 줄 = 코드가 products.yaml 에서 직접 뽑는다(LLM 미사용)
- 입력(products.yaml 의 해당 종목 사실 필드)이 바뀐 종목만 재생성하고 '마지막 수정일'을 그 날짜로 갱신한다. 안 바뀌면 호출 0.
사용: python3 scripts/mm_page_text.py [--no-llm] [--only SOXL,BULZ] [--force]
"""
import sys, os, re, json, hashlib, datetime, argparse, concurrent.futures as cf
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "products_page.json"
LOGDIR = ROOT / ".local" / "page_text_attempts"
PROMPT_VERSION = "pg2"
ISSUER_SHORT = {"Direxion": "Direxion", "ProShares": "ProShares"}


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


def facts(p):
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
    }
    if c.get("selection_rule"): f["종목 선정 규칙"] = c["selection_rule"]
    if c.get("capping"): f["비중 상한 규칙"] = c["capping"]
    if c.get("description"): f["지수 설명"] = c["description"]
    ch = (p.get("fee") or {}).get("changes") or []
    if ch: f["금융비용 변경 이력"] = [f"{x.get('date')} {x.get('event')}" for x in ch]
    lt = (p.get("top_constituents") or {}).get("lookthrough")
    if lt: f["구성 ETF 상위 보유"] = {x["etf"]: [f"{i['symbol']} {i['weight_pct']}" for i in x["items"]] for x in lt}
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


PROMPT = """아래 [사실]은 3배 레버리지 ETF/ETN 한 종목의 발행사 공시 기반 사실 필드다. 투자자용 종목 페이지 문구를 JSON 한 개로 작성하라.

출력 형식(JSON 만, 코드펜스·설명 금지):
{{"construction": "...", "features": ["...", "...", "..."], "risk": ["..."], "fee": "..."}}

규칙(공통):
- [사실]에 없는 내용·수치·날짜는 절대 쓰지 말 것(추측·일반 상식·외부 지식·계산 금지). 숫자·날짜·이름은 입력 그대로.
- 전망·평가·권고·추측 표현 금지. 사용 금지 어휘: 추천, 유망, 전망, 기대, 매력, 우수, 좋은, 유리, 불리, 매수, 매도, 투자하, 예상, 권장, 적합, 가능성,
  안정적, '~할 것이다', '~로 보인다', '~일 것', '위험이 낮/적/크'. 서술문('~이다', '~한다', '~로 명시돼 있다', '~할 수 있다')으로만 쓴다.
- 공식 지수의 영문 명칭은 쓰지 말 것(섹터/테마의 한국어 표기로 지칭). 영문 약어는 [사실]에 나온 티커·종목명만 허용.
- 한 항목은 한 문장, 80자 안팎. 마크다운·불릿 금지.

필드별 규칙:
- construction: 한 줄. '가중 방식 · 종목 수 · 리밸런스 주기' 순서로 가운뎃점(·)으로 잇는다. 예: "유동주식 시가총액 가중 · 30종목 · 분기 리밸런스". 사실에 없는 항목은 생략.
- features: 정확히 3개.
  [0] 무엇을 따르는 상품인지(발행사·ETF/ETN·섹터/테마·일간 3배).
  [1] 어떤 성격의 움직임인지 — 지수의 구성 특성 사실만(종목 수, 가중 방식, 상위 5종 비중 합계, 섹터 편중 서술 등). 움직임의 방향·수준은 쓰지 않는다.
  [2] 주의점 — 지수·구성 쪽에서 투자자가 알아둘 사실 하나(종목 수가 적어 집중돼 있다는 사실, 상위 5종 비중 합계의 크기, 비중 상한·편중 규칙, 구성 변경 방식, 특정 업종 편중 서술 등). 상위 구성 종목의 이름·비중 나열은 표에 따로 있으므로 반복하지 말 것. 구조 리스크(일간 리셋·발행사 신용 등)는 risk 에 쓰므로 반복하지 말 것.
- risk: 1~2개. ETN 이면 첫 항목에 발행사 신용(무담보 채무)과 발행사 콜·조기상환 관련 사실, 그리고 [사실]에 '금융비용 변경 이력'이 있으면 마지막 항목에 그 변경(날짜·값 그대로) 1줄. ETF 이면 첫 항목에 일간 리셋·1일 초과 보유 시 지수 3배와 달라질 수 있다는 공시 문구 취지 1줄, 구조 사실에 지수(추종 목표) 변경 이력이 있으면 그 날짜와 함께 1줄.
- fee: ETN 만. 투자자 수수료와 금융비용(기준금리+스프레드, 상한·인상 여부)을 한 줄로. ETF 이면 빈 문자열 "".

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


def validate(out, fin_text, is_etn, has_changes):
    """구조·금지어·수치 출처 검증. 통과하면 None, 아니면 사유 문자열."""
    if not isinstance(out, dict): return "JSON 객체 아님"
    for k in ("construction", "features", "risk", "fee"):
        if k not in out: return f"키 누락 {k}"
    if not isinstance(out["features"], list) or len(out["features"]) != 3: return "features 3개 아님"
    if not isinstance(out["risk"], list) or not (1 <= len(out["risk"]) <= 2): return "risk 1~2개 아님"
    texts = [out["construction"], out["fee"]] + out["features"] + out["risk"]
    if any((not isinstance(x, str)) for x in texts): return "문자열 아닌 값"
    if not out["construction"].strip() or any(not x.strip() for x in out["features"] + out["risk"]): return "빈 항목"
    if is_etn and not out["fee"].strip(): return "ETN fee 비어 있음"
    G = _gen()
    v = G.violations(" ".join(texts))
    if v: return "금지어 " + ",".join(v)
    allowed = _nums(fin_text) | {"1", "3"}
    if re.search("|".join(MONTHS), fin_text):                      # 입력에 영문 월 이름이 있으면 '3·6·12월' 같은 월 번호 표기는 허용
        allowed |= {str(i) for i in range(1, 13)}
    out_txt = re.sub(r"\b(100|300)%", "", " ".join(texts))
    bad = sorted(n for n in _nums(out_txt) if n not in allowed)
    if bad: return "입력에 없는 숫자 " + ",".join(bad)
    if has_changes and not any(re.search(r"\d{4}-\d{2}-\d{2}", r) for r in out["risk"]): return "금융비용 변경 이력 미반영"
    return None


def _json_from(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    a, b = t.find("{"), t.rfind("}")
    return json.loads(t[a:b + 1])


def input_hash(p, issuer_uni):
    blob = json.dumps([PROMPT_VERSION, facts(p), top5(p), basic_info(p, issuer_uni), (p.get("inception") or {}).get("date")], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def gen_one(t, p, issuer_uni, stats):
    G = _gen()
    fin = json.loads(iso_dates(json.dumps(facts(p), ensure_ascii=False)))
    fin_text = json.dumps(fin, ensure_ascii=False)
    base_prompt = PROMPT.format(facts=json.dumps(fin, ensure_ascii=False, indent=1))
    prompt = base_prompt
    has_changes = bool(fin.get("금융비용 변경 이력"))
    attempts = []
    LOGDIR.mkdir(parents=True, exist_ok=True)
    for n in range(1, 6):
        try:
            raw = G.call_llm(prompt)
            out = _json_from(raw)
        except Exception as e:
            attempts.append({"n": n, "error": str(e)[:200]}); stats["errors"] += 1; continue
        why = validate(out, fin_text, p["type"] == "ETN", has_changes)
        attempts.append({"n": n, "out": out, "invalid": why})
        if why is not None:
            prompt = base_prompt + f"\n[직전 출력이 검증에서 거절됨: {why}. 같은 실수를 반복하지 말고 규칙대로 다시 작성하라. features 는 정확히 3개, risk 는 1~2개, [사실]에 없는 숫자는 쓰지 말 것.]"
        if why is None:
            json.dump({"ticker": t, "attempts": attempts}, open(LOGDIR / f"{t}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            return out, n
        stats["invalid"] += 1
    json.dump({"ticker": t, "attempts": attempts}, open(LOGDIR / f"{t}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return None, len(attempts)


def ensure(use_llm=True, only=None, force=False, today=None, issuers=None, log=print):
    """products.yaml 에서 바뀐 종목만 재생성. 반환 stats. LLM 실패 시 기존 문구 유지(+ failed 목록)."""
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
        h = input_hash(p, iu)
        old = items.get(t)
        if old and old.get("hash") == h and not force and old.get("text"):
            stats["kept"] += 1
            continue
        todo.append((t, p, iu, h))
    if todo and not use_llm:
        stats["failed"] = [x[0] for x in todo]
        log(f"[page_text] LLM 미실행: 재생성 필요 {len(todo)}종 {stats['failed']}")
    elif todo:
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(gen_one, t, p, iu, stats): (t, p, iu, h) for t, p, iu, h in todo}
            for f in cf.as_completed(futs):
                t, p, iu, h = futs[f]
                out, n = f.result()
                if out is None:
                    stats["failed"].append(t); log(f"[page_text] {t} 생성 실패(기존 유지) 시도 {n}"); continue
                items[t] = {"hash": h, "modified": today, "text": {k: out[k] for k in ("construction", "features", "risk", "fee")}}
                stats["changed"].append(t); log(f"[page_text] {t} 생성 완료 시도 {n}")
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
    ap.add_argument("--no-llm", action="store_true"); ap.add_argument("--force", action="store_true"); ap.add_argument("--only", default="")
    a = ap.parse_args()
    s = ensure(use_llm=not a.no_llm, only=set(filter(None, a.only.split(","))) or None, force=a.force)
    print(json.dumps(s, ensure_ascii=False))
    sys.exit(1 if s["failed"] else 0)
