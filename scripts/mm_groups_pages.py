"""MM-UNIVERSE-GROUPS-20261123 — 신규 49종 종목 페이지 문구·구성 데이터 생성(LLM 호출 0, 발행사 문서로 확인된 사실만 템플릿으로 채운다).
산출: data/products_page_groups.json (items, build_product 입력) · data/holdings_groups.json (해외지수 롱 8종 = 1x ETF 상위 보유, yfinance funds_data).
인버스는 짝 롱 구성을 쓰고(페이지 빌더가 합침), 크립토·채권은 구성 대신 '기준 자산' 1줄. 소개·보수·구성 요약줄·구조 리스크는 data/intro_groups.json(MM-PRODUCT-INTRO-ENRICH-20261124)이 뒤에 덮어쓴다. 사용: python3 scripts/mm_groups_pages.py [수정일]"""
import json, sys, datetime as dt
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"; FETCHED = ROOT / ".local" / "fetched"
MINUS = "−"
SEC = {"crypto": "크립토", "bond": "채권", "intl": "해외지수", "inv": "인버스"}
ASSET = {"IDX_BITCOIN": "비트코인(단일 코인의 달러 가격)", "IDX_ETHEREUM": "이더리움(단일 코인의 달러 가격)"}


import re
def cix(x): return re.sub(r"\s*\(Bloomberg ticker [^)]*\)","",str(x))


def lev_txt(m): return f"{MINUS if m < 0 else ''}{abs(int(m))}배(일간)"


def first_bar(t):
    p = FETCHED / f"{t}.csv"
    try:
        s = pd.read_csv(p, usecols=[0]).iloc[0, 0]; return str(s)[:10]
    except Exception:
        return None


def construction(r, pair_sector):
    g, ix = r.grp, cix(r.index_name)
    if g == "inv": return f"짝 롱 상품 {r.pair}과 같은 지수 구성 · 지수 하락 시 상승({MINUS}3배, 지수 상승 시 하락)"
    if g == "crypto": return f"기준 자산: {ASSET.get(r.proxy, ix)} · 구성 종목 없음(지수 {ix})"
    if g == "bond": return f"기준 자산: {ix}(채권) · 개별 구성 종목을 담지 않는 지수"
    return f"지수 추종({ix}) · 구성 데이터는 1x ETF {r.onex} 상위 보유 기준"


def intro(r):
    m = int(r.mult); a = abs(m); ix = cix(r.index_name); g = r.grp; iss = str(r.issuer); typ = str(r.type)
    if g == "inv":
        p1 = f"발행사 {iss}의 이 상품은 {ix}의 일간 수익률의 {MINUS}{a}배를 따르는 인버스 상품이다. 지수가 하루 동안 오르면 같은 비율의 {a}배만큼 내리고, 내리면 {a}배만큼 오르도록 설계돼 있으며, 짝이 되는 롱 상품은 {r.pair}이다."
    elif g == "crypto":
        p1 = f"발행사 {iss}의 이 상품은 {ix}의 일간 수익률을 {a}배로 따른다. 이 지수는 {ASSET.get(r.proxy, '')}의 가격을 재는 지수이다."
    else:
        p1 = f"발행사 {iss}의 이 상품은 {ix}의 일간 수익률을 {a}배로 따른다."
    p2 = f"이 상품은 {typ}이며 매일 레버리지를 재설정하는 일간 목표 구조이다. 1일을 넘겨 보유하면 일별 수익률이 복리로 쌓여 지수 수익률의 {MINUS if m < 0 else ''}{a}배와 달라진다."
    return p1 + "\n\n" + p2


def risks(r):
    m = int(r.mult); a = abs(m); out = []
    out.append(f"매일 레버리지를 재설정하는 일간 목표 상품이라 1일을 넘는 보유 수익률은 지수 수익률의 {MINUS if m < 0 else ''}{a}배와 달라진다(변동성이 큰 장세일수록 차이가 커진다).")
    if str(r.type) == "ETN": out.append(f"ETN은 {r.issuer} 발행 무담보 채무라 발행사 신용위험에 노출되며 발행사 조기상환 가능성이 있다.")
    else: out.append("파생상품으로 지수 노출을 만들기 때문에 거래상대방 위험과 롤·금융 비용이 수익률에 반영된다.")
    if r.grp == "inv": out.append("지수가 오르면 손실이 나는 구조라 상승 추세가 이어지는 구간에서는 손실이 빠르게 커지며, 장기 보유할수록 복리 효과로 불리해진다.")
    if r.grp == "crypto": out.append("기초 지수가 24시간 거래되는 암호화폐 가격이라 미국 장 마감 시각과 지수 기준 시각이 달라 일간 추종 오차가 생길 수 있고, 이 사이트의 대용 품질(β·R²)은 '근사'로 표시될 수 있다.")
    if r.grp == "bond" and str(r.proxy) in ("HYG", "LQD"): out.append("1x 계열을 iShares ETF 종가(배당 미반영)로 쓰므로 총수익 지수와 차이가 날 수 있다(대용 품질 '근사').")
    return out


def build(modified=None, log=print):
    u = pd.read_csv(DATA / "universe_groups.csv").fillna("")
    modified = modified or dt.date.today().isoformat(); items = {}
    for r in u.itertuples():
        pg_sec = SEC.get(r.grp, "")
        sector = f"{pg_sec} · {cix(r.index_name)}"
        items[r.ticker] = {
            "modified": modified, "sector": sector,
            "basic": {"issuer": str(r.issuer), "type": str(r.type), "leverage": lev_txt(r.mult), "fee": None, "inception": first_bar(r.ticker)},
            "text": {"construction": construction(r, sector), "intro": intro(r), "risk": risks(r), "fee": ""},
        }
    try:                                                          # MM-PRODUCT-INTRO-ENRICH-20261124: 사람 검토 소개·보수 보강분을 다시 덮어쓴다
        import mm_groups_intro; mm_groups_intro.apply_items(items)
    except Exception as e: log(f"[groups_pages] 소개 보강분 적용 실패: {type(e).__name__}: {e}")
    json.dump({"meta": {"block": "MM-UNIVERSE-GROUPS-20261123-R3", "generated": modified, "count": len(items), "note": "템플릿 생성(LLM 0) — 사실은 발행사 1차 문서(docs 열)로 확인한 지수명·배수·발행사·유형뿐, 보수는 미수록"}, "items": items},
              open(DATA / "products_page_groups.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 해외지수 롱 8종 구성: 1x ETF 상위 보유
    H = {}
    try:
        import yfinance as yf
        for r in u[(u.grp == "intl")].itertuples():
            try:
                th = yf.Ticker(r.onex).funds_data.top_holdings
                its = [{"n": str(n), "w": round(float(w) * 100, 3)} for n, w in zip(th["Name"], th["Holding Percent"])] if th is not None and len(th) else []
                if its: H[r.ticker] = {"basis": f"1x ETF {r.onex} 보유(상위)", "as_of": modified, "fetched": modified, "total": len(its), "scope": f"상위 {len(its)}종", "source": {"name": "Yahoo Finance 펀드 보유(상위)", "url": f"https://finance.yahoo.com/quote/{r.onex}/holdings"}, "items": its}
                else: log(f"[groups_pages] {r.ticker}({r.onex}) 보유 데이터 없음")
            except Exception as e: log(f"[groups_pages] {r.ticker} 보유 수신 실패: {type(e).__name__}")
    except Exception as e: log(f"[groups_pages] yfinance 불가: {e}")
    try:
        import mm_groups_intro; mm_groups_intro.apply_holdings(H)
    except Exception as e: log(f"[groups_pages] 구성 요약줄 적용 실패: {type(e).__name__}: {e}")
    json.dump({"generated": modified, "items": H}, open(DATA / "holdings_groups.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return len(items), len(H)


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else None))
