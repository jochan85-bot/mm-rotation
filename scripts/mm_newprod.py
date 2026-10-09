"""신규 상품 분류 필터 (MM-PAGE-V2.3 §3). 주간 점검(mm_weekly_scan)과 tests/ 가 공유한다.
편입 조건: (a) 롱 +3배  (b) 주식 지수·섹터·테마  (c) 개별종목·인버스·채권·상품·암호화폐·VIX 제외  (d) 티커 실제 상장.
(d) 미충족(티커 없음)은 '발행 예정'(pipeline.json), 제외는 excluded_candidates.json 에 사유 기록 후 후보에서 삭제."""
import re, json, datetime as dt
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; DATA=ROOT/"data"
def norm(s): return re.sub(r"[^a-z0-9]+"," ",str(s or "").lower().replace("™","")).strip()
# 이름 접두 → 배수
LEV_PAT=[(r"\bUltraPro Short\b",-3.0),(r"\bUltraShort\b",-2.0),(r"\bQuadPro\b",4.0),(r"\bUltraPro\b",3.0),(r"\bUltra\b",2.0),
         (r"\bBear\s+3X\b|\b-3X\b|\bShort\s+3X\b",-3.0),(r"\bBull\s+3X\b|\b3X\b|\+3X\b",3.0),(r"\bBear\s+2X\b",-2.0),(r"\bBull\s+2X\b",2.0)]
def parse_leverage(name="", lev=""):
    """lev 문자열('3x','-3x','?') 우선, 없으면 이름으로 추정. 반환 float 또는 None"""
    m=re.fullmatch(r"\s*([+-]?)(\d(?:\.\d)?)\s*[xX]\s*",str(lev or ""))
    if m: return float(m.group(2))*(-1 if m.group(1)=="-" else 1)
    for rx,v in LEV_PAT:
        if re.search(rx,name or "",re.I): return v
    return None
# (c) 비주식 자산군
C_RULES=[("채권",re.compile(r"\b(Treasur\w*|Bonds?|T-?Notes?|Yield|Aggregate|Investment Grade|High Yield|Fixed Income)\b",re.I)),
         ("암호화폐",re.compile(r"\b(Bitcoin|Ether(eum)?|Crypto\w*|Solana|XRP|Digital Asset)\b",re.I)),
         ("VIX·변동성",re.compile(r"\b(VIX|Volatility|VSTOXX)\b",re.I)),
         ("원자재",re.compile(r"\b(Crude|WTI|Brent|Natural Gas|Gold(?! Miners| Mining| Producers)|Silver(?! Miners| Mining)|Copper|Platinum|Palladium|Commodit\w+|Wheat|Corn|Soybean|Uranium Futures)\b|K-1 Free",re.I)),
         ("통화",re.compile(r"\b(Dollar|Yen|Euro|Currency|Currencies|Sterling)\b",re.I))]
def classify(name="", ticker="", lev="", issuer="", overrides=None):
    """반환 dict(decision='include'|'exclude'|'unknown', rule, reason). ticker 가 없어도 (a)~(c) 판정은 한다."""
    key=norm(ticker) if ticker else norm(name)
    ov=(overrides or {}).get(key) or (overrides or {}).get(norm(name))
    if ov: return dict(decision="exclude",rule="override",reason=ov)
    L=parse_leverage(name,lev)
    if L is None: return dict(decision="unknown",rule="a",reason="배수 확인 불가 — 상품명·배수 미확인")
    if L<0: return dict(decision="exclude",rule="a",reason=f"인버스({L:g}배) — 롱 +3배 아님")
    if L!=3.0: return dict(decision="exclude",rule="a",reason=f"{L:g}배 — +3배 아님")
    nm=name or ""
    # 개별종목: Direxion 'Daily XXX Bull 3X' / ProShares 'UltraPro XXX' 의 XXX 가 1~5자 대문자 티커
    m=re.search(r"(?:Direxion Daily|ProShares UltraPro)\s+([A-Z]{1,5})\b(?:\s+(?:Bull|Bear)\s+\dX|\s*$|\s+(?:ETF|Shares))",nm)
    if m and m.group(1) not in ("QQQ","SPY","IWM","DJI","DOW","S","P","US","AI","ETF","EV"):
        return dict(decision="exclude",rule="c",reason=f"개별종목({m.group(1)})")
    for lab,rx in C_RULES:
        if rx.search(nm): return dict(decision="exclude",rule="c",reason=f"{lab} 상품 — 주식 지수·섹터·테마 아님")
    if not nm and ticker: return dict(decision="unknown",rule="b",reason="상품명 미확인(자산군 판정 불가)")
    return dict(decision="include",rule="b",reason="롱 +3배 주식 지수·섹터·테마")
def load_json(p,default):
    try: return json.load(open(p,encoding="utf-8"))
    except Exception: return default
def save_json(p,obj): json.dump(obj,open(p,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
def process(found, listed_names=None, today=None, data=DATA):
    """found: [(name_or_ticker, issuer, lev, url, filed_date, ticker_or_empty, name)] 을 분류해 파일 갱신.
    반환 dict(pipeline_added, listed_added, excluded_added, skipped). 파일: pipeline.json / excluded_candidates.json / new_products.json"""
    today=today or str(dt.date.today())
    P=load_json(data/"pipeline.json",{"items":[]}); X=load_json(data/"excluded_candidates.json",{"items":[]}); N=load_json(data/"new_products.json",{"candidates":[]})
    OV=load_json(data/"candidate_overrides.json",{}); OV={norm(k):v for k,v in OV.items() if not k.startswith("_")}
    xk={x["key"] for x in X["items"]}; pk={p["key"] for p in P["items"]}; nk={norm(c.get("ticker") or c.get("name")) for c in N["candidates"]}
    out=dict(pipeline_added=[],listed_added=[],excluded_added=[],skipped=0)
    for (label,issuer,lev,url,filed,ticker,name) in found:
        key=norm(ticker) if ticker else norm(name or label)
        if key in xk or key in pk or key in nk: out["skipped"]+=1; continue
        c=classify(name or label,ticker,lev,issuer,OV)
        if c["decision"]=="exclude":
            X["items"].append(dict(key=key,ticker=ticker,name=name or label,issuer=issuer,leverage=lev,rule=c["rule"],reason=c["reason"],found=today,source=url,filed=filed,owner_override=(c["rule"]=="override")))
            xk.add(key); out["excluded_added"].append(f"{ticker or name or label}: {c['reason']}")
        elif ticker:   # (d) 상장됨
            N["candidates"].append(dict(ticker=ticker,name=name,issuer=issuer,type="ETN" if "MicroSectors" in issuer or "BMO" in issuer else "ETF",leverage=lev,index="(발행사 문서 확인 필요)",found=filed or today,source=url,
                                        status=("공식 지수 확정 대기 — index_specs 추가 후 산출" if c["decision"]=="include" else "분류 미완("+c["reason"]+") — 확인 필요")))
            nk.add(key); out["listed_added"].append(ticker)
            P["items"]=[p for p in P["items"] if norm(p["name"])!=norm(name)]   # 발행 예정에서 졸업
        else:          # 티커 없음 → 발행 예정
            P["items"].append(dict(key=key,issuer=issuer,name=name or label,leverage=lev,filed=filed,url=url,found=today)); pk.add(key); out["pipeline_added"].append(name or label)
    save_json(data/"pipeline.json",P); save_json(data/"excluded_candidates.json",X); save_json(data/"new_products.json",N)
    return out
