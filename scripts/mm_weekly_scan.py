#!/usr/bin/env python3
"""mm_rotation 주간 공시 점검·신상품 확인 — 소스 접근 실패는 침묵하지 않고 '확인 실패: 소스명' 으로 기록·보고."""
import sys, re, json, html, time, signal, traceback, datetime as dt, urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import mm_lib as L
UA="mm-rotation research (jjoychan85@gmail.com)"
CIKS={"Direxion":["0001424958","0001450922"],"ProShares":["0001415311","0001174610"],"BMO":["0000927971"]}
FORMS={"497","497K","497J","497AD","485APOS","485BPOS","485BXT","8-A12B","FWP","424B2","424B3","424B5","8-K"}
LOOKBACK=8
def get(url,timeout=30,maxb=900_000):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*"})
    with urllib.request.urlopen(req,timeout=timeout) as r: return r.read(maxb).decode("utf-8","ignore")
def totext(h): return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",re.sub(r"<(script|style).*?</\1>"," ",h,flags=re.S))))
def aliases(uni,info):
    al={}
    for r in uni.itertuples():
        names=set()
        ln=info.loc[info.ticker==r.ticker,"yf_longName"]
        if len(ln) and isinstance(ln.iloc[0],str):
            n=ln.iloc[0].replace("™","").strip(); names.add(n)
            for pre in ("Direxion Daily ","ProShares ","MicroSectors "):
                if n.startswith(pre): names.add(n[len(pre):])
        names={x for x in names if len(x)>=12}
        al[r.ticker]=(names, re.compile(r"\b%s\b"%re.escape(r.ticker)) if len(r.ticker)>=4 else None)
    return al
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
def new_names_from_text(txt):
    names=set()
    for m in re.finditer(r"Direxion Daily ([A-Za-z0-9&\.\-\s/]{3,60}?) (Bull|Bear) (\d)X Shares",txt): 
        mid=m.group(1).strip()
        if re.fullmatch(r"[A-Z]{1,5}",mid): continue            # 개별종목 제외
        names.add((f"Direxion Daily {mid} {m.group(2)} {m.group(3)}X Shares","Direxion",f"{'-' if m.group(2)=='Bear' else ''}{m.group(3)}x"))
    for m in re.finditer(r"ProShares (UltraPro Short|UltraPro) ([A-Za-z0-9&\.\-\s]{2,40}?)(?= (is|are|seeks|ETF|and|\(|,|\.|Post))",txt):
        mid=re.sub(r"[\s\d\.]+$","",m.group(2).strip())
        if re.fullmatch(r"[A-Z]{1,5}",mid): continue
        names.add((f"ProShares {m.group(1)} {mid}","ProShares","-3x" if "Short" in m.group(1) else "3x"))
    return names
def main(push=True):
    L.check_formula()
    today=dt.date.today(); since=today-dt.timedelta(days=LOOKBACK)
    uni=pd.read_csv(L.DATA/"universe.csv"); info=pd.read_csv(L.DATA/"product_info.csv"); status=L.load_status()
    np_path=L.DATA/"new_products.json"; newp=json.load(open(np_path,encoding="utf-8"))
    ok_src=[]; fail_src=[]; issues=[]; docs=0; found_names=set(); actions=[]
    fails=L.fetch_all(L.need_tickers()); L.log(f"주간 수신 실패={fails}","weekly")
    if fails: fail_src.append('yfinance 시세 수신 실패: '+','.join(fails))
    al=aliases(uni,info)
    known_names={n for names,_ in al.values() for n in names}
    u0=pd.read_csv("%s/p0/universe_v2.csv"%L.STUDY); known_tick=set(u0.ticker)|set(uni.ticker)|{c.get("ticker") for c in newp["candidates"]}
    known_names|={str(x).replace("™","") for x in u0.yf_longName.dropna()}
    issuer_fail={}
    # ---- EDGAR ----
    for iss,ciks in CIKS.items():
        for cik in ciks:
            src=f"SEC EDGAR {iss} CIK {cik}"
            try:
                sub=json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json",maxb=5_000_000)); time.sleep(0.2)
            except Exception as e:
                fail_src.append(f"{src} ({type(e).__name__})"); issuer_fail[iss]=issuer_fail.get(iss,0)+1; continue
            rec=sub["filings"]["recent"]; n_doc=0; name=sub.get("name","")
            for i,form in enumerate(rec["form"]):
                fd=dt.date.fromisoformat(rec["filingDate"][i])
                if fd<since: break
                if form not in FORMS: continue
                acc=rec["accessionNumber"][i].replace("-",""); doc=rec["primaryDocument"][i]; desc=rec.get("primaryDocDescription",[""]*len(rec["form"]))[i]
                if not doc.lower().endswith((".htm",".html",".txt")): continue
                url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}"
                if n_doc>=60: break
                try: txt=totext(get(url,maxb=700_000)); time.sleep(0.2)
                except Exception as e: fail_src.append(f"{src} 문서 {form} {fd} ({type(e).__name__})"); continue
                n_doc+=1; docs+=1
                if iss=="BMO" and "MicroSectors" not in txt[:60000]: continue
                title=f"{name} {form} {desc}".strip()
                issues+=scan_text(txt,al,url,str(fd),form,title)
                for nm,isr,lev in new_names_from_text(txt):
                    if nm.replace("™","") not in known_names: found_names.add((nm,isr,lev,url,str(fd)))
            ok_src.append(f"{src} ({n_doc}건 본문)")
    # ---- microsectors.com ----
    try:
        t=totext(get("https://microsectors.com/")); ok_src.append("microsectors.com")
        for m in re.finditer(r"\b([A-Z]{3,5})\s+([+\-−])(\d(?:\.\d)?)X\b",t):
            tk,sg,lv=m.group(1),m.group(2),float(m.group(3))
            if lv==3.0 and tk not in known_tick:
                found_names.add((tk,"BMO MicroSectors",("-" if sg in "-−" else "")+"3x","https://microsectors.com/",str(today)))
    except Exception as e: fail_src.append(f"microsectors.com ({type(e).__name__})")
    # ---- proshares.com 레버리지 목록 ----
    try:
        h=get("https://www.proshares.com/our-etfs/leveraged-and-inverse",maxb=1_500_000)
        if len(h)<5000: raise RuntimeError("본문 비정상(%d bytes)"%len(h))
        ok_src.append("proshares.com 레버리지 목록")
        for tk in set(re.findall(r"/our-etfs/leveraged-and-inverse/([a-z]{3,5})\b",h)):
            if tk.upper() not in known_tick: found_names.add((tk.upper(),"ProShares","?","https://www.proshares.com/our-etfs/leveraged-and-inverse",str(today)))
    except Exception as e: fail_src.append(f"proshares.com 레버리지 목록 ({type(e).__name__}: {str(e)[:60]})")
    # ---- BMO newsroom / Direxion press ----
    for nm,url in (("BMO newsroom","https://www.bmo.com/en-us/main/about-bmo/newsroom/"),("Direxion press releases (403 시 EDGAR 대체 — Direxion EDGAR 본문 점검은 별도 수행)","https://www.direxion.com/news")):
        try:
            h=get(url); 
            if len(h)<3000 or "Just a moment" in h: raise RuntimeError("차단/빈 응답")
            ok_src.append(nm)
        except Exception as e: fail_src.append(f"{nm} ({type(e).__name__}{': '+str(e)[:40] if not isinstance(e,urllib.error.HTTPError) else ' '+str(e.code)})" if False else f"{nm} ({type(e).__name__}: {str(e)[:50]})")
    # ---- 조치 적용 ----
    for iss,cnt in issuer_fail.items():
        if cnt>=len(CIKS[iss]):
            for r in uni[uni.issuer.str.contains(iss.split()[0])].itertuples(): status["check_incomplete"][r.ticker]=f"{iss} EDGAR 접근 실패 {today}"
    for iss in CIKS:
        if iss not in issuer_fail or issuer_fail[iss]<len(CIKS[iss]):
            for r in uni[uni.issuer.str.contains(iss.split()[0])].itertuples(): status["check_incomplete"].pop(r.ticker,None)
    act_map={"조기상환·가속상환":("exclude","즉시 제외(E5) — 영구"),"상장폐지·청산":("exclude","즉시 제외(E5) — 영구"),
             "배수 변경":("exclude_revalidate","제외 후 3배 재확인(β·R², 20봉 이상) 시 복귀"),"지수 변경":("exclude_revalidate","제외 후 1x 매핑 재검증(β·R², 20봉 이상) 시 복귀")}
    for o in issues:
        t=o["ticker"]; typ=o["type"]
        if o["strong"] and typ in act_map and t not in status["excluded"]:
            kind,act=act_map[typ]
            status["excluded"][t]=dict(type=typ,date=o["date"],title=o["title"],url=o["url"],action=act,revalidate=(kind=="exclude_revalidate"),since=o["date"],source="EDGAR "+o["form"])
            actions.append(f"{t}: {typ} → {act}")
        elif not o["strong"]:
            notes=status["notes"].setdefault(t,[]); msg=f"{o['date']} {typ} 공지({o['form']}) — {o['url']}"
            if msg not in notes: notes.append(msg); actions.append(f"{t}: {typ} 비고 추가")
    # ---- 복귀 재검증 ----
    try:
        T,S=L.init_from_raw(); pq=pd.read_csv(L.DATA/"proxy_quality.csv"); cfg=L.load_yaml_simple(L.DATA/"eligibility.yaml")
        for t,e in list(status["excluded"].items()):
            if not e.get("revalidate"): continue
            px=uni.loc[uni.ticker==t,"proxy"].iloc[0]; sd=pd.Timestamp(e["since"])
            h3=S.loadp(t); h1=S.loadp(px); a=h3[h3.index>sd]["Close"].pct_change(); b=h1[h1.index>sd]["Close"].pct_change()
            r=pd.concat([a,b],axis=1,keys=["a","b"]).dropna()
            if len(r)>=20:
                beta=float(np.polyfit(r.b,r.a,1)[0]); r2=float(r.corr().iloc[0,1]**2)
                if L.e4_ok(beta,r2,cfg):
                    del status["excluded"][t]; status["notes"].setdefault(t,[]).append(f"{today} 복귀: 공지 후 {len(r)}봉 β {beta:.2f} R² {r2:.2f}"); actions.append(f"{t}: 복귀(β {beta:.2f}, R² {r2:.2f}, {len(r)}봉)")
    except Exception as e: fail_src.append(f"복귀 재검증 ({type(e).__name__}: {str(e)[:60]})")
    # ---- 신규 편입 ----
    added=[]
    have={(c.get("ticker") or c.get("name")) for c in newp["candidates"]}
    for nm,isr,lev,url,fd in sorted(found_names):
        key=nm
        if key in have: continue
        is_tk=bool(re.fullmatch(r"[A-Z]{3,5}",nm))
        c=dict(ticker=nm if is_tk else "",name=nm if not is_tk else "",issuer=isr,type="ETN" if "MicroSectors" in isr else "ETF",leverage=lev,index="(발행사 문서 확인 필요)",found=fd,source=url,status=("대기(E1 미달 — 신규, 1x 매핑 미정)" if is_tk else "공시 단계(상장 전·티커 미정) — 상장 후 대기 표에 편입"))
        newp["candidates"].append(c); added.append(c); have.add(key)
    L.save_json(np_path,newp); L.save_json(L.DATA/"status.json",status)
    rep=dict(date=str(today),lookback_days=LOOKBACK,sources_ok=ok_src,sources_failed=fail_src,docs_scanned=docs,issues=issues,actions=actions,new_products=added)
    L.save_json(L.DATA/"issues"/f"{today}.json",rep)
    # ---- 재산출(E5 반영) + push ----
    import mm_daily
    df=mm_daily.run(push=push,fetch=False)
    # ---- 주간 텔레그램 1건 ----
    el=df[df.table=="적격"].sort_values(["rank","M"],ascending=[True,False]).head(10)
    lines=[f"[mm_rotation 주간] {today} 기준일 {df.date.iloc[0]}","적격 상위 10 (순위·티커·M·Δ5일):"]
    for r in el.itertuples(): lines.append(f"{int(r.rank)}. {r.ticker} {r.M:.1f} {('Δ'+str(r.d_rank)) if str(r.d_rank) not in ('','nan') else ''}")
    lines.append("신규 편입: "+(", ".join((c['ticker'] or c['name']) for c in added) if added else "없음"))
    lines.append("제외·조치: "+("; ".join(actions) if actions else "없음"))
    lines.append("확인 실패 소스: "+("; ".join(fail_src) if fail_src else "없음"))
    L.log("주간 점검 완료: "+json.dumps(dict(ok=len(ok_src),fail=len(fail_src),issues=len(issues),actions=len(actions),new=len(added)),ensure_ascii=False),"weekly")
    if "--no-alert" not in sys.argv: L.tg_send("\n".join(lines))
    else: print("\n".join(lines))
if __name__=="__main__":
    signal.signal(signal.SIGALRM,lambda *a:(_ for _ in ()).throw(TimeoutError("상한 15분 초과"))); signal.alarm(900)
    try: main(push="--no-push" not in sys.argv)
    except BaseException as e:
        msg=f"[mm_rotation] 주간 점검 실패: {type(e).__name__}: {str(e)[:300]}"
        L.log(msg+"\n"+traceback.format_exc()[-1500:],"alerts")
        if "--no-alert" not in sys.argv: L.tg_send(msg)
        sys.exit(1)
