#!/usr/bin/env python3
"""mm_rotation 주간 공시 점검·신상품 확인 — 소스 접근 실패는 침묵하지 않고 '확인 실패: 소스명' 으로 기록·보고."""
import sys, re, json, html, time, signal, traceback, datetime as dt, urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import mm_lib as L
UA="mm-rotation research (jjoychan85@gmail.com)"
CIKS={"Direxion":["0001424958"],"ProShares":["0001415311","0001174610"],"BMO":["0000927971"]}
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
from mm_rules import TRIG, ACT_MAP, scan_text
import mm_newprod
PRO_LEV={"UltraPro Short":"-3x","UltraShort":"-2x","QuadPro":"4x","UltraPro":"3x","Ultra":"2x"}
def new_names_from_text(txt):
    """공시 본문에서 상품명 후보 추출 -> {(상품명, 발행사, 배수문자열)}. 분류(주식 지수 여부·개별종목 등)는 mm_newprod.classify 가 한다."""
    names=set()
    for m in re.finditer(r"Direxion Daily ([A-Za-z0-9&\.\-\s/]{3,60}?) (Bull|Bear) (\d)X Shares",txt):
        mid=m.group(1).strip()
        names.add((f"Direxion Daily {mid} {m.group(2)} {m.group(3)}X Shares","Direxion",f"{'-' if m.group(2)=='Bear' else ''}{m.group(3)}x"))
    for m in re.finditer(r"ProShares (UltraPro Short|QuadPro|UltraShort|UltraPro|Ultra) ([A-Za-z0-9&\.\-\s]{2,40}?)(?= (?:is|are|seeks|ETF|and|\(|,|\.|Post|[2-9]\.|Amendment)|\s+\d{2,}\b|$)",txt):
        mid=re.sub(r"[\s\.]+$","",m.group(2).strip())
        if len(mid)<2: continue
        names.add((f"ProShares {m.group(1)} {mid}","ProShares",PRO_LEV[m.group(1)]))
    return names
def main(push=True):
    L.check_formula()
    today=dt.date.today(); since=today-dt.timedelta(days=LOOKBACK)
    uni=pd.read_csv(L.DATA/"universe.csv"); info=pd.read_csv(L.DATA/"product_info.csv"); status=L.load_status()
    np_path=L.DATA/"new_products.json"; newp=json.load(open(np_path,encoding="utf-8"))
    ok_src=[]; fail_src=[]; issues=[]; docs=0; found_names=set(); actions=[]; web_fail=[]; subst_src=[]
    fails=L.fetch_all(L.need_tickers()); L.log(f"주간 수신 실패={fails}","weekly")
    if fails: fail_src.append('yfinance 시세 수신 실패: '+','.join(fails))
    al=aliases(uni,info)
    known_names={n for names,_ in al.values() for n in names}
    u0=pd.read_csv("%s/p0/universe_v2.csv"%L.STUDY); known_tick=set(u0.ticker)|set(uni.ticker)|{c.get("ticker") for c in newp["candidates"]}|{x.get("ticker") for x in mm_newprod.load_json(L.DATA/"excluded_candidates.json",{"items":[]})["items"] if x.get("ticker")}
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
    except Exception as e: web_fail.append((f"microsectors.com ({type(e).__name__})","BMO"))
    # ---- proshares.com 레버리지 목록 ----
    try:
        h=get("https://www.proshares.com/our-etfs/leveraged-and-inverse",maxb=1_500_000)
        if len(h)<5000: raise RuntimeError("본문 비정상(%d bytes)"%len(h))
        ok_src.append("proshares.com 레버리지 목록")
        for tk in set(re.findall(r"/our-etfs/leveraged-and-inverse/([a-z]{3,5})\b",h)):
            if tk.upper() not in known_tick: found_names.add((tk.upper(),"ProShares","?","https://www.proshares.com/our-etfs/leveraged-and-inverse",str(today)))
    except Exception as e: web_fail.append((f"proshares.com 레버리지 목록 ({type(e).__name__}: {str(e)[:60]})","ProShares"))
    # ---- BMO newsroom / Direxion press ----
    for nm,url,iss in (("BMO newsroom","https://www.bmo.com/en-us/main/about-bmo/newsroom/","BMO"),("Direxion press releases","https://www.direxion.com/news","Direxion")):
        try:
            h=get(url)
            if len(h)<3000 or "Just a moment" in h: raise RuntimeError("차단/빈 응답")
            ok_src.append(nm)
        except Exception as e:
            code=f" {e.code}" if isinstance(e,urllib.error.HTTPError) else ""
            web_fail.append((f"{nm} ({type(e).__name__}{code}: {str(e)[:50]})",iss))
    # 웹 소스 실패는 발행사 EDGAR 가 정상이면 '대체 확인(EDGAR)', EDGAR 까지 실패해야 '확인 실패'
    for disp,iss in web_fail:
        if issuer_fail.get(iss,0)<len(CIKS[iss]): subst_src.append(f"{disp} → 대체 확인(EDGAR {iss})")
        else: fail_src.append(f"{disp} + EDGAR {iss} 접근 실패")
    # ---- 조치 적용 ----
    for iss,cnt in issuer_fail.items():
        if cnt>=len(CIKS[iss]):
            for r in uni[uni.issuer.str.contains(iss.split()[0])].itertuples(): status["check_incomplete"][r.ticker]=f"{iss} EDGAR 접근 실패 {today}"
    for iss in CIKS:
        if iss not in issuer_fail or issuer_fail[iss]<len(CIKS[iss]):
            for r in uni[uni.issuer.str.contains(iss.split()[0])].itertuples(): status["check_incomplete"].pop(r.ticker,None)
    act_map=ACT_MAP
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
    # ---- 신규 상품 분류(§3): 제외 사유 기록 / 발행 예정 / 상장 후보 ----
    def _yf_name(tk):
        try:
            import yfinance as yf; i=yf.Ticker(tk).info; return i.get("longName") or i.get("shortName") or ""
        except Exception: return ""
    found=[]
    for nm,isr,lev,url,fd in sorted(found_names):
        is_tk=bool(re.fullmatch(r"[A-Z]{3,5}",nm)); name=_yf_name(nm) if is_tk else nm
        if is_tk and lev in ("?","") and name:
            _L=mm_newprod.parse_leverage(name); lev=f"{_L:g}x" if _L else "?"
        found.append((nm,isr,lev,url,fd,nm if is_tk else "",name))
    np_res=mm_newprod.process(found,today=str(today))
    added=np_res["listed_added"]+np_res["pipeline_added"]
    L.save_json(L.DATA/"status.json",status)
    rep=dict(date=str(today),lookback_days=LOOKBACK,sources_ok=ok_src,sources_failed=fail_src,sources_substituted=subst_src,docs_scanned=docs,issues=issues,actions=actions,new_products=np_res)
    L.save_json(L.DATA/"issues"/f"{today}.json",rep)
    # ---- 종목 페이지 구성 데이터 주간 갱신(MM-PAGE-V3.2 §6) — 실패해도 주간 점검은 계속, log 만 남긴다 ----
    try:
        import mm_holdings
        hs=mm_holdings.refresh(log=lambda m:L.log(m,"weekly"),budget_s=300)
        L.log("구성 종목 갱신: "+json.dumps(dict(n=hs["n"],stale=hs["stale"],fails=hs["fails"]),ensure_ascii=False),"weekly")
    except Exception as e: L.log(f"구성 종목 갱신 실패(무시하고 계속): {type(e).__name__}: {str(e)[:200]}","weekly")
    # ---- 재산출(E5 반영) + push ----
    import mm_daily
    df=mm_daily.run(push=push,fetch=False,manual=None)
    # ---- 주간 텔레그램 1건 ----
    el=df[df.table=="순위"].sort_values(["rank","M"],ascending=[True,False]).head(10)
    lines=[f"[mm_rotation 주간] {today} 기준일 {df.date.iloc[0]}","순위 상위 10 (순위·티커·M·Δ5일):"]
    for r in el.itertuples(): lines.append(f"{int(r.rank)}. {r.ticker} {r.M:.1f} {('Δ'+str(r.d_rank)) if str(r.d_rank) not in ('','nan') else ''}"+(f" [{r.badges}]" if isinstance(r.badges,str) and r.badges else ""))
    lines.append("신규 편입(상장·분류 통과): "+(", ".join(np_res["listed_added"]) if np_res["listed_added"] else "없음"))
    lines.append("발행 예정 추가: "+(", ".join(np_res["pipeline_added"]) if np_res["pipeline_added"] else "없음"))
    lines.append("신규 제외(규칙): "+(f"{len(np_res['excluded_added'])}건 — "+"; ".join(np_res["excluded_added"]) if np_res["excluded_added"] else "없음"))
    lines.append("제외·조치: "+("; ".join(actions) if actions else "없음"))
    lines.append("대체 확인(EDGAR): "+("; ".join(subst_src) if subst_src else "없음"))
    lines.append("확인 실패 소스: "+("; ".join(fail_src) if fail_src else "없음"))
    L.log("주간 점검 완료: "+json.dumps(dict(ok=len(ok_src),fail=len(fail_src),issues=len(issues),actions=len(actions),new=len(added),subst=len(subst_src)),ensure_ascii=False),"weekly")
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
