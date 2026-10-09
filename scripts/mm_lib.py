"""mm_rotation 공용 — 데이터 수신·정제·적격 판정·M-score 산출. 점수 정의는 MSCORE_V1.md(불변), 피처·백분위는 p3 common / p4 SPEC import."""
import os, sys, json, math, time, hashlib, subprocess, urllib.request, urllib.parse, datetime as dt, warnings, traceback
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
ROOT=Path(__file__).resolve().parent.parent
DATA=ROOT/"data"; LOCAL=ROOT/".local"; RAW=LOCAL/"p0view"; FETCHED=LOCAL/"fetched"; DOCS=ROOT/"docs"; LOGS=LOCAL/"logs"
STUDY=Path.home()/"studies"/"mm_rotation_20261007"
MSCORE_DOC=STUDY/"MSCORE_V1_1.md"
MSCORE_SHA="2c2b8f73ebd37bd862aa7206591bb032d8e71c716576c9fa92ac16d01079c590"   # v1.1: 산식 불변, 1x 매핑표만 교체 (v1 sha 41e4f209f338ba7ebb09bc7905be081f99e6b5abfef3170b84494bb223a9c83a 는 MSCORE_V1.md 에 보존)
KST=dt.timezone(dt.timedelta(hours=9))
class FormulaMismatch(RuntimeError): pass
def now_kst(): return dt.datetime.now(KST)
def log(msg, name="daily"):
    LOGS.mkdir(parents=True,exist_ok=True)
    line=f"{now_kst().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line,flush=True)
    with open(LOGS/f"{name}.log","a") as f: f.write(line+"\n")
def check_formula():
    """매 실행 sha 대조 — 불일치 시 중단"""
    got=hashlib.sha256(open(MSCORE_DOC,"rb").read()).hexdigest()
    if got!=MSCORE_SHA: raise FormulaMismatch(f"MSCORE_V1.md sha 불일치: {got}")
# ---------- 알림 ----------
def tg_send(text):
    """텔레그램 1건 (토큰=키체인, chat_id=.local/config.json). 실패는 예외 대신 False."""
    try:
        cfg=json.load(open(LOCAL/"config.json")); chat=cfg["chat_id"]
        tok=subprocess.run(["/usr/bin/security","find-generic-password","-s","mactrader-telegram-bot-token","-a","mactrader","-w"],capture_output=True,text=True,timeout=20).stdout.strip()
        if not tok: return False
        body=urllib.parse.urlencode({"chat_id":chat,"text":text[:3900],"disable_web_page_preview":"true"}).encode()
        r=urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage",data=body),timeout=30)
        return r.status==200
    except Exception as e:
        log(f"tg_send 실패: {type(e).__name__}", "alerts"); return False
# ---------- 설정 ----------
def load_yaml_simple(p):
    out={}; cur=None
    for ln in open(p,encoding="utf-8"):
        if not ln.strip() or ln.lstrip().startswith("#"): continue
        ind=len(ln)-len(ln.lstrip()); k,_,v=ln.strip().partition(":"); v=v.strip()
        if ind==0:
            if v=="": cur=k; out[k]={}
            else: out[k]=_cast(v); cur=None
        elif cur is not None: out[cur][k]=_cast(v)
    return out
def _cast(v):
    try: return int(v)
    except ValueError:
        try: return float(v)
        except ValueError: return v
def load_status():
    p=DATA/"status.json"; return json.load(open(p,encoding="utf-8")) if p.exists() else {"excluded":{},"notes":{},"check_incomplete":{}}
def save_json(p,obj): json.dump(obj,open(p,"w",encoding="utf-8"),ensure_ascii=False,indent=1,default=str)
# ---------- 수신 ----------
def need_tickers():
    """study 의 45종(B+C+A+D) + 1x 대리 + SPY + 편입 신상품 (study common 이 45종 전부를 읽는다)"""
    u=pd.read_csv("%s/p0/universe_v2.csv"%STUDY); b=u[u.group.str[0].isin(list("ABCD"))]
    OVR={"WTIU":"XLE","TPOR":"IYT"}
    s=set(b.ticker)|{OVR.get(t,p) for t,p in zip(b.ticker,b.proxy_1x)}|{"SPY"}
    uni=pd.read_csv(DATA/"universe.csv"); s|=set(uni.ticker)|set(uni.proxy.dropna())
    import mm_proxy
    s-=set(mm_proxy.synthetic_keys(DATA))                         # 합성 키는 yfinance 티커가 아님
    s|=set(mm_proxy.full_fetch_tickers(DATA))                     # Yahoo 지수·splice 후반 ETF
    return sorted(s)
def synthetic_keys():
    import mm_proxy; return mm_proxy.synthetic_keys(DATA)
def build_synthetic(log=print):
    """합성(공식 지수 레벨 + 연장) 1x 계열 생성 — 수신 직후, clean_all 직전"""
    import mm_proxy
    fails=mm_proxy.fetch_recent(mm_proxy.tail_fetch_tickers(DATA),FETCHED/"tail")
    if fails: log(f"꼬리 소스 수신 실패 {fails}")
    return mm_proxy.build_all(DATA,FETCHED,LOCAL,log)
def proxy_info():
    p=LOCAL/"proxy_build_info.json"; return json.load(open(p,encoding="utf-8")) if p.exists() else {}
def fetch_all(tickers):
    import yfinance as yf
    FETCHED.mkdir(parents=True,exist_ok=True); fails=[]
    for t in tickers:
        ok=False
        for k in range(3):
            try:
                h=yf.Ticker(t).history(period="max",auto_adjust=False,actions=True)
                if len(h)>0: h.to_csv(FETCHED/f"{t}.csv"); ok=True; break
            except Exception as e: time.sleep(2*(k+1))
        if not ok: fails.append(t)
        time.sleep(0.15)
    return fails
def _read(t):
    p=FETCHED/f"{t}.csv"; h=pd.read_csv(p,index_col=0)
    h.index=pd.to_datetime(h.index,utc=True).tz_convert("America/New_York").tz_localize(None).normalize(); return h
def _write(t,h):
    (RAW/"data").mkdir(parents=True,exist_ok=True)
    h=h.copy(); h.index=h.index.tz_localize("America/New_York"); h.to_csv(RAW/"data"/f"{t}.csv")
def clean_all(tickers):
    """미확정 마지막 행 제거 + SPY 달력에 없는 행 제거. 반환 (T, provisional_info, dropped{ticker:reason})"""
    dropped={}
    SYNK=set(synthetic_keys())
    def conf(h,t=""):
        if len(h)<22: return True,""
        last=h.iloc[-1]
        if pd.isna(last["Close"]): return False,"Close 가 NaN(미확정)"
        if t.startswith("^") or t in SYNK: return True,""          # 지수 레벨·합성 계열은 거래량 개념 없음 — Close 유무만 본다
        med=h["Volume"].iloc[-21:-1].median()
        if med>=10000 and last["Volume"]<0.5*med: return False,"거래량이 직전 20봉 중앙값의 50% 미만(미확정)"   # 극저유동 ETN(중앙값<1만주)은 무거래일이 정상이라 제외
        return True,""
    spy=_read("SPY"); ok,why=conf(spy,"SPY"); spy_raw_last=spy.index.max(); prov=None
    if not ok:
        spy=spy.iloc[:-1]; prov={"raw_last":str(spy_raw_last.date()),"reason":why}
    _write("SPY",spy); T=spy.index.max(); sdates=set(spy.index)
    for t in tickers:
        if t=="SPY": continue
        h=_read(t); ok,why=conf(h,t)
        if not ok: h=h.iloc[:-1]; dropped[t]=why
        h=h[h.index.isin(sdates)|(h.index<spy.index.min())]
        _write(t,h)
    return T,prov,dropped
# ---------- 연구 모듈 로딩 (재구현 없음) ----------
_study=None
def load_study(T):
    global _study
    if _study is not None: return _study
    sys.path.insert(0,str(STUDY/"p2"/"sim"))
    import resim
    resim.P0=str(RAW)+"/"; resim.END=pd.Timestamp(T)
    sys.path.insert(0,str(STUDY/"p4"/"sim"))
    import p4lib
    assert p4lib.SPEC["S_A"]==("sig","rsA","f1b")
    _study=p4lib; return p4lib
KEY={"sig":"s60","rsA":"f2a","f1b":"f1b"}
# ---------- E4 대리 품질 ----------
def measure_proxy(S,t,px,asof,window_days=365,min_n=60):
    h3=S.loadp(t); h1=S.loadp(px)
    a=h3[h3.index<=asof]["Close"].pct_change(); b=h1[h1.index<=asof]["Close"].pct_change()
    r=pd.concat([a,b],axis=1,keys=["a","b"]).dropna(); r=r[r.index>asof-pd.Timedelta(days=window_days)]
    if len(r)<min_n: return None,None,len(r)
    beta=float(np.polyfit(r.b,r.a,1)[0]); r2=float(r.corr().iloc[0,1]**2); return beta,r2,len(r)
def e4_ok(beta,r2,cfg): 
    return beta is not None and cfg["E4"]["beta_min"]<=abs(beta)<=cfg["E4"]["beta_max"] and r2>=cfg["E4"]["r2_min"]
# ---------- 산출 ----------
def compute(S,asof,T,cfg,status,uni,pq,remeasure=False):
    """asof(Timestamp) 기준 전 종목 표 (적격/대기/제외/⚠) + M-score. pq: DataFrame(ticker→측정값) — remeasure 시 갱신 반환"""
    asof=pd.Timestamp(asof); rows=[]; pq_upd={}
    for r in uni.itertuples():
        t=r.ticker; px=r.proxy; reasons=[]; tab="적격"
        rec=dict(date=str(asof.date()),ticker=t,group=r.group,type=r.type,issuer=r.issuer,proxy=px,approx=int(r.approx))
        _s=lambda v:(v if isinstance(v,str) else "")
        rec.update(proxy_disp=_s(getattr(r,"proxy_disp","")),proxy_tip=_s(getattr(r,"proxy_tip","")),vstate=_s(getattr(r,"vstate","")))
        _pi=proxy_info().get(px,{})
        rec["proxy_tail"]=(f"공식 레벨 {_pi['official_last']}까지 + {_pi['tail_days']}일 연장({_pi['tail_src']})" if _pi.get("tail_days") else "")+(" · 공식 레벨 캐시 사용" if _pi.get("official_from_cache") else "")
        try:
            h3=S.loadp(t); h1=S.loadp(px)
        except Exception as e:
            rec.update(table="⚠",reason=f"데이터 없음({type(e).__name__})"); rows.append(rec); continue
        h3a=h3[h3.index<=asof]; h1a=h1[h1.index<=asof]
        d3=h3a.index.max() if len(h3a) else None; d1=h1a.index.max() if len(h1a) else None
        rec.update(d3=str(d3.date()) if d3 is not None else "",d1=str(d1.date()) if d1 is not None else "",listed_days=len(h3a))
        stale=(d3!=asof) or (d1!=asof)
        # 지표
        if len(h3a):
            tail=h3a.tail(20); adtv=float((tail["Close"]*tail["Volume"]).mean()/1e6); zero=int((tail["Volume"]==0).sum()); close3=float(h3a["Close"].iloc[-1])
        else: adtv=zero=close3=np.nan
        rec.update(adtv=adtv,zero_vol=zero,close3=close3)
        feats_ok=False
        if d1 is not None and len(h1a)>=260:
            f=S.feat1x(px); k=h1.index.get_loc(d1)
            v={n:f[KEY[n]][k] for n in ("sig","rsA","f1b")}
            if not any(np.isnan(x) for x in v.values()):
                c1=h1a["Close"].values.astype(float); ma200=c1[-200:].mean()
                rec.update(sig=v["sig"],rsA=v["rsA"],f1b=v["f1b"],c1_ma200=c1[-1]/ma200-1,above200=int(c1[-1]>ma200)); feats_ok=True
        # E1~E4
        if rec["listed_days"]<cfg["E1"]["threshold"]: reasons.append(f"E1 상장 {rec['listed_days']}거래일<{cfg['E1']['threshold']}")
        if not (adtv>=cfg["E2"]["threshold"]): reasons.append(f"E2 20일 평균 거래대금 ${adtv:.2f}M<${cfg['E2']['threshold']}M" if not np.isnan(adtv) else "E2 거래대금 산출 불가")
        if not (zero<=cfg["E3"]["threshold"]): reasons.append(f"E3 최근 20봉 무거래 {zero}봉>{cfg['E3']['threshold']}")
        prow=pq[pq.ticker==t]
        beta=r2=None; nb=0; ok4=False; mdate=""
        if len(prow):
            p=prow.iloc[0]; beta=None if pd.isna(p.beta) else float(p.beta); r2=None if pd.isna(p.r2) else float(p.r2); nb=int(p.n); mdate=str(p.measured); ok4=bool(p.ok)
        if remeasure:
            stale_meas=(not mdate) or (asof-pd.Timestamp(mdate)).days>365
            insufficient=(not ok4) and nb<60
            if (stale_meas or insufficient) and rec["listed_days"]>=cfg["E1"]["threshold"] and adtv>=cfg["E2"]["threshold"]:
                b2,q2,n2=measure_proxy(S,t,px,asof)
                if n2>=60 or stale_meas:
                    beta,r2,nb=b2,q2,n2; ok4=e4_ok(beta,r2,cfg); mdate=str(asof.date())
                    pq_upd[t]=dict(ticker=t,proxy=px,beta=beta,r2=r2,n=nb,measured=mdate,ok=int(ok4),source="mm_daily 재측정(trailing 365d)")
        if not ok4:
            reasons.append("E4 1x 대리 품질 미달"+(f"(β {beta:.2f}, R² {r2:.2f}, n={nb})" if beta is not None else f"(표본 {nb}<60)"))
        rec.update(beta=beta,r2=r2,n_beta=nb,proxy_measured=mdate)
        ex=status.get("excluded",{}).get(t)
        if stale:
            tab="⚠"; reasons=[f"최신 확정 봉이 기준일({asof.date()})과 다름: 3배 {rec['d3'] or '없음'} / 1x {rec['d1'] or '없음'}"]+reasons
        elif ex: tab="제외"; reasons=[f"E5 {ex.get('type','')} {ex.get('date','')}"]+reasons
        elif reasons: tab="대기"
        if not feats_ok and tab in ("적격","대기"):
            reasons.append("피처 산출 불가(1x 이력 부족)"); tab="대기" if tab=="적격" else tab
        rec.update(table=tab,reason="; ".join(reasons),has_feats=int(feats_ok)); rows.append(rec)
    df=pd.DataFrame(rows)
    # pct / M-score : 적격 집합 기준, 비적격은 적격 집합에 1개 추가했을 때 백분위
    el=df[(df.table=="적격")&(df.has_feats==1)]
    for n in ("sig","rsA","f1b"): df["p_"+n]=np.nan
    df["M"]=np.nan
    if len(el):
        for n in ("sig","rsA","f1b"):
            df.loc[el.index,"p_"+n]=S.pct_rank(el[n].values)
        for i,r in df[(df.has_feats==1)&(df.table!="적격")].iterrows():
            for n in ("sig","rsA","f1b"):
                arr=np.append(el[n].values,r[n]); df.loc[i,"p_"+n]=S.pct_rank(arr)[-1]
    sel=df.has_feats==1
    df.loc[sel,"M"]=(df.loc[sel,"p_sig"]+df.loc[sel,"p_rsA"]+df.loc[sel,"p_f1b"])/3*100
    # 순위(적격만, 경쟁 순위 — 동점 동일 번호)
    df["rank"]=np.nan
    e=df[(df.table=="적격")&sel]
    if len(e):
        m=e.M.round(6); df.loc[e.index,"rank"]=m.rank(ascending=False,method="min")
    return df,pq_upd

def init_from_raw():
    """주간 점검 등: 저장된 RAW 데이터만으로 연구 모듈 로딩 (T = SPY 마지막 확정 봉)"""
    T,prov,dropped=clean_all(need_tickers()+synthetic_keys()); return T, load_study(T)
