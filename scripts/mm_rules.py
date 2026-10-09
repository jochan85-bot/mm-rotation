"""공시 문구 판정 규칙 — 주간 점검(mm_weekly_scan)과 픽스처 테스트(tests/)가 공유한다. 규칙 변경은 이 파일만."""
import re
TRIG=[
 ("조기상환·가속상환",True,re.compile(r"((send|sent|give|given|deliver\w*)\s+(a\s+)?notice of (early |accelerated )?redemption\s+to\s+(the\s+)?holders|(has|have) (elected|determined|decided) to (redeem|accelerate)|(intends?|intention|plans?) to (redeem|call) all\b|announces?( the)?( upcoming)? redemption of|(?<!give notice that we )(?<!give notice that BMO )(?<!give notice that it )will (redeem|accelerate)\s+(all|the (entire|outstanding))\b.{0,60}(ETNs|notes|securities)|(?<!right to )accelerat\w+ (the )?(redemption|maturity)\b(?! Measurement).{0,40}\b(on|effective|as of)\b)",re.I)),
 ("상장폐지·청산",True,re.compile(r"(will be (liquidated|delisted|closed|terminated)|(has|have) (decided|determined|approved)\b.{0,120}(liquidat|terminat|delist|clos(e|ing) down|closure and)|plan of liquidation|(last|final) day of trading|will cease (trading|operations))",re.I)),
 ("배수 변경",True,re.compile(r"(\b(chang|reduc|lower|modif)\w*\b.{0,100}(leverage|multiple|investment objective)\b.{0,120}\bfrom\s+\d(\.\d+)?\s*(x|%)\s+to\s+\d(\.\d+)?\s*(x|%)|\b\d(\.\d)?X\W{0,3}\s+in\s+(each|the)\s+(Fund|ETF|ETN)s?\W{0,2}s?\s+names?\s+(will|shall)\s+be\s+(replaced|changed)\s+(with|to)\s+\W{0,3}\d(\.\d)?X|\b\d{3}%(\s+or\s+-\d{3}%)?\s+will\s+be\s+(replaced|changed)\s+(with|to)\s+\d{3}%)",re.I)),
 ("지수 변경",True,re.compile(r"((underlying|benchmark|reference) index(es)?\b[^.]{0,60}\b(will|is to|are to|shall)\s+(be\s+)?(chang|replac)\w*|\b(chang|replac)\w*\s+(of\s+)?(the\s+|its\s+|each\s+\w+.s\s+)?(current\s+|existing\s+)?(underlying|benchmark)\s+index|\b(approved|announced|adopted)\s+(the\s+following\s+)?(chang|revision|modification)\w*\s+to\s+the\s+(Fund.s\s+)?investment (objective|strategy)\b[^.]{0,80}\b(underlying|benchmark) index|\bcurrent index\b.{0,40}\bnew index\b|will (track|seek).{0,80}\bnew (underlying )?index)",re.I)),
 ("역분할·액면분할",False,re.compile(r"((?<!effected a )(?<!effected an )(?<!completed a )(?<!implemented a )\b\d+[- ]for[- ]\d+\s+(reverse|forward)\s+(share\s+)?(split|stock split)|\b(will|to)\s+effect\s+a\s+(reverse|forward)\s+(share\s+|stock\s+)?split)",re.I)),
 ("금융비용·수수료 변경",False,re.compile(r"(((daily )?(investor|financing) (fee|charge)|annual fee|financing spread|fee rate)\b[^.]{0,100}(will (be )?(increas|decreas|chang)\w*\s+(from|to|by)\s+(approximately\s+)?\d|increase(d)? to\s+\d|reduc\w+ to\s+\d)|\bUpcoming\s+(increase|decrease|reduction)\s+to\s+the\s+(daily )?(financing spread|investor fee|fee rate)|\b(BMO|Bank of Montreal)\s+(increases|decreases|reduces|raises)\s+the\s+(daily )?(financing spread|investor fee|fee rate)|(financing spread|investor fee|fee rate)\b.{0,60}\b(will be|is being|are being)\s+(increas|decreas|reduc)\w+|\bbeginning on and including\s+[A-Z][a-z]+ \d{1,2}, \d{4}\s+\(the\s+\W?Fee Effective Date\W?\),?\s+\d+(\.\d+)?%\s+per annum)",re.I)),
 ("발행사 신용 등급",False,re.compile(r"(credit rating|downgrad\w+).{0,100}(Bank of Montreal|BMO)|(Bank of Montreal|BMO).{0,100}(credit rating|downgrad\w+)",re.I)),
]
LEAD=1500   # 문구 주변(±600자)에 티커가 없을 때 쓰는 대체 귀속 범위: 제목 + 문서 앞 LEAD자(보충서·가격공시서는 대상 상품을 앞머리에 나열한다)
def _hits(s,al): return [t for t,(names,tk) in al.items() if any(n in s for n in names) or (tk is not None and tk.search(s))]
def scan_text(txt,al,url,date,form,title):
    out=[]; lead=f"{title} {txt[:LEAD]}"
    for typ,strong,rx in TRIG:
        for m in rx.finditer(txt):
            w=txt[max(0,m.start()-600):m.end()+600]
            for t in (_hits(w,al) or _hits(lead,al)):
                out.append(dict(ticker=t,type=typ,strong=strong,url=url,date=date,form=form,title=title,snippet=w[500:900].strip()))
    # 중복 제거
    seen=set(); res=[]
    for o in out:
        k=(o["ticker"],o["type"],o["url"])
        if k not in seen: seen.add(k); res.append(o)
    return res

# 조치 매핑: 유형 -> (kind, 설명). strong=True 인 유형만 자동 조치 대상.
ACT_MAP={"조기상환·가속상환":("exclude","즉시 제외(E5) — 영구"),"상장폐지·청산":("exclude","즉시 제외(E5) — 영구"),
         "배수 변경":("exclude_revalidate","제외 후 3배 재확인(β·R², 20봉 이상) 시 복귀"),"지수 변경":("exclude_revalidate","제외 후 1x 매핑 재검증(β·R², 20봉 이상) 시 복귀")}

def decide(issues,excluded=()):
    """scan_text 결과 -> 조치 목록. mm_weekly_scan.main '조치 적용' 루프와 같은 결정(순서 의존 포함: 같은 티커의 첫 strong 만 제외).
    excluded: 이미 제외된 티커 집합/딕셔너리(status["excluded"]) — 복사해서 쓰므로 변경하지 않는다.
    반환: [dict(ticker,kind,type,act,revalidate,issue)] — kind 는 "exclude"|"exclude_revalidate"|"note"."""
    ex=set(excluded); acts=[]
    for o in issues:
        t=o["ticker"]; typ=o["type"]
        if o["strong"] and typ in ACT_MAP and t not in ex:
            kind,act=ACT_MAP[typ]; ex.add(t)
            acts.append(dict(ticker=t,kind=kind,type=typ,act=act,revalidate=(kind=="exclude_revalidate"),issue=o))
        elif not o["strong"]:
            acts.append(dict(ticker=t,kind="note",type=typ,act="비고만(제외 아님)",revalidate=False,issue=o))
    return acts
