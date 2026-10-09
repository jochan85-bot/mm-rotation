"""공시 문구 판정 규칙 — 주간 점검(mm_weekly_scan)과 픽스처 테스트(tests/)가 공유한다. 규칙 변경은 이 파일만."""
import re
TRIG=[
 ("조기상환·가속상환",True,re.compile(r"(notice of (an )?(early|accelerated) redemption|(has|have) (elected|determined|decided) to (redeem|accelerate)|will (redeem|accelerate)\b.{0,60}(ETNs|notes)|accelerat\w+ (the )?(redemption|maturity)\b.{0,40}(on|effective|as of))",re.I)),
 ("상장폐지·청산",True,re.compile(r"(will be (liquidated|delisted|closed|terminated)|(has|have) (decided|determined|approved)\b.{0,120}(liquidat|terminat|clos(e|ing)|delist)|plan of liquidation|(last|final) day of trading|will cease (trading|operations))",re.I)),
 ("배수 변경",True,re.compile(r"(chang|reduc|lower|modif)\w*\b.{0,100}(leverage|multiple|investment objective)\b.{0,120}\bfrom\s+\d(\.\d+)?\s*(x|%)\s+to\s+\d(\.\d+)?\s*(x|%)",re.I)),
 ("지수 변경",True,re.compile(r"((chang|replac)\w*\b.{0,80}(underlying index|benchmark index|the index)\b.{0,120}\bto\b|will (track|seek).{0,80}\bnew (underlying )?index)",re.I)),
 ("역분할·액면분할",False,re.compile(r"\b\d+[- ]for[- ]\d+\s+(reverse|forward)\s+(share\s+)?(split|stock split)",re.I)),
 ("금융비용·수수료 변경",False,re.compile(r"((daily )?(investor|financing) (fee|charge)|annual fee)\b.{0,100}(will (increase|decrease|change)|increase(d)? to|reduc\w+ to)",re.I)),
 ("발행사 신용 등급",False,re.compile(r"(credit rating|downgrad\w+).{0,100}(Bank of Montreal|BMO)|(Bank of Montreal|BMO).{0,100}(credit rating|downgrad\w+)",re.I)),
]
def scan_text(txt,al,url,date,form,title):
    out=[]
    for typ,strong,rx in TRIG:
        for m in rx.finditer(txt):
            w=txt[max(0,m.start()-600):m.end()+600]
            for t,(names,tk) in al.items():
                hit=any(n in w for n in names) or (tk is not None and tk.search(w))
                if hit: out.append(dict(ticker=t,type=typ,strong=strong,url=url,date=date,form=form,title=title,snippet=w[500:900].strip()))
    # 중복 제거
    seen=set(); res=[]
    for o in out:
        k=(o["ticker"],o["type"],o["url"])
        if k not in seen: seen.add(k); res.append(o)
    return res

# 조치 매핑: 유형 -> (kind, 설명). strong=True 인 유형만 자동 조치 대상.
ACT_MAP={"조기상환·가속상환":("exclude","즉시 제외(E5) — 영구"),"상장폐지·청산":("exclude","즉시 제외(E5) — 영구"),
         "배수 변경":("exclude_revalidate","제외 후 3배 재확인(β·R², 20봉 이상) 시 복귀"),"지수 변경":("exclude_revalidate","제외 후 1x 매핑 재검증(β·R², 20봉 이상) 시 복귀")}
