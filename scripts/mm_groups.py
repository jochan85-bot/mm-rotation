"""MM-UNIVERSE-GROUPS-20261123 — 그룹(미국 기본·크립토·채권·해외지수·인버스) 원값 산출. 표시 계층: scores_latest.csv·기존 docs/data 파일은 바꾸지 않는다(새 파일만).
정의: MSCORE_V1_2_GROUPS.md. 새 종목(data/universe_groups.csv)의 1x 계열 — 롱은 exact 1x 키, 인버스는 INV_<키>(= 1x 일간 수익률 r 의 Π(1−r) 누적, 시작 100).
산출물: docs/data/raw/YYYY.json(연 분할) — 베이스 37종은 저장된 날짜 파일에서 복사(M 입력 3개), 새 종목은 mm_lib.compute 재사용(전체 열)."""
import json, math, numpy as np, pandas as pd
import mm_lib as L
DATA=L.DATA; RAWDIR=L.DOCS/"data"/"raw"
FIELDS=["sig","rsA","f1b","pop","c1_ma200","above200","close3","adtv","listed_days","badges","beta","r2","n_beta"]
def groups_def():
    p=DATA/"groups.json"; return json.load(open(p,encoding="utf-8")) if p.exists() else {"groups":[],"held":[]}
def load_universe():
    p=DATA/"universe_groups.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["ticker","group","type","issuer","proxy","grp","mult","pair","onex","index_name"])
def need_extra():
    """수신 대상 추가 티커: 새 3배 종목 + 롱 1x 키(합성·INV 제외) — 합성 키(IDX_·TPOR_1X)는 mm_proxy 가 만든다"""
    u=load_universe()
    if not len(u): return []
    syn=set(L.synthetic_keys()); s=set(u.ticker)
    for p in u.proxy.dropna():
        if not p.startswith("INV_") and p not in syn: s.add(p)
    return sorted(s)
def _hist(r):
    try: return json.loads(r) if isinstance(r,str) and r else []
    except Exception: return []
def inverse_keys():
    """현행 프록시 + 날짜별 이력(proxy_hist, 오너 R3 §1-3: 짝 롱이 그날 쓴 저장 1x 계열)에 나오는 INV_ 키 전부"""
    u=load_universe()
    if not len(u): return []
    s={p for p in u.proxy.dropna() if p.startswith("INV_")}
    if "proxy_hist" in u.columns:
        for h in u.proxy_hist: s|={p for _,p in _hist(h)}
    return sorted(s)
def uni_at(u, d):
    """날짜 d(문자열 YYYY-MM-DD 또는 Timestamp)의 유니버스 — 인버스 종목의 proxy 를 그날 짝 롱의 저장 1x 계열(INV_ 판)로 바꾼 사본. 이력이 없으면 현행 그대로.
    d 가 이력의 첫 날짜보다 앞이면 첫 계열(워밍업 포함 — 2020-01-02 이전은 첫 매핑)"""
    if "proxy_hist" not in u.columns: return u
    ds=str(d)[:10]; u2=u.copy(); px=[]
    for p,h in zip(u2.proxy,u2.proxy_hist):
        hh=_hist(h)
        if not hh: px.append(p); continue
        cur=hh[0][1]
        for d0,p0 in hh:
            if d0<=ds: cur=p0
        px.append(cur)
    u2["proxy"]=px; return u2
def build_inverse(raw_data_dir, log=print):
    """INV_<키>.csv — RAW 의 1x(<키>) 일간 수익률 r 의 부호를 뒤집은 −1x 누적 계열 Π(1−r)·100. 1x 기준선이 아니라 일간 곱(경로 의존) — 오너 결정 §1-3."""
    from pathlib import Path
    d=Path(raw_data_dir); out={}
    for k in inverse_keys():
        src=d/f"{k[4:]}.csv"
        if not src.exists(): out[k]="1x 원본 없음"; log(f"[mm_groups] {k}: 1x 원본 {src.name} 없음"); continue
        h=pd.read_csv(src,index_col=0); c=h["Close"].astype(float).values
        r=np.concatenate([[0.0],c[1:]/c[:-1]-1]); r=np.where(np.isfinite(r),r,0.0)
        lv=100.0*np.cumprod(1.0-r)
        o=pd.DataFrame(index=h.index); 
        for col in ("Open","High","Low","Close"): o[col]=lv
        o["Volume"]=0; o["Dividends"]=0.0; o["Stock Splits"]=0.0
        o.index.name=h.index.name or "Date"; o.to_csv(d/f"{k}.csv"); out[k]="ok"
    return out
def mult_adjust(df, cfg, uni):
    """§3-3 변동성 항 원값 = σ60(1x) × |배수|/3 (sigma_leverage_adjust: true 일 때만). 3배·−3배 변화 없음, 2배만 ×2/3."""
    if not str((cfg or {}).get("sigma_leverage_adjust","false")).lower() in ("true","1"): return df
    m=dict(zip(uni.ticker,uni.mult.abs()/3.0)); df=df.copy(); df["sig"]=[s*m.get(t,1.0) if s==s else s for t,s in zip(df.ticker,df.sig)]
    return df
def compute_new(S,asof,cfg,pq,uni,remeasure=False):
    """새 종목만의 compute — 반환 (df, pq 갱신분). M·순위·p_* 는 이 부분 모집단 기준이라 쓰지 않는다(브라우저가 켜진 그룹 모집단으로 다시 계산)."""
    df,upd=L.compute(S,asof,asof,cfg,{"excluded":{}},uni,pq,remeasure=remeasure)
    return mult_adjust(df,cfg,uni),upd
def _r(x,n=6):
    return None if x is None or (isinstance(x,float) and not math.isfinite(x)) else (round(float(x),n))
def new_row(r):
    """compute 행 → raw 행(FIELDS 순서). pop=1 : 순위 모집단(table 순위 ∧ 피처 있음), 아니면 0(원값은 채움 — 상장 전·⚠)."""
    if not int(getattr(r,"has_feats",0) or 0): return None
    pop=1 if (r.table=="순위") else 0
    g=lambda k,n=6: _r(getattr(r,k,None),n)
    li=getattr(r,"listed_days",None); 
    return [g("sig",12),g("rsA",12),g("f1b",12),pop,g("c1_ma200"),(int(r.above200) if getattr(r,"above200",None)==getattr(r,"above200",None) else None),
            g("close3",4),g("adtv",5),(int(li) if li==li and li is not None else None),
            (r.badges if isinstance(r.badges,str) else ""),g("beta",3),g("r2",4),(int(r.n_beta) if getattr(r,"n_beta",None)==getattr(r,"n_beta",None) and r.n_beta is not None else None)]
def base_rows(day_df):
    """저장된 날짜 파일(순위 모집단 행) → {ticker: [sig,rsA,f1b,1]}. 저장값은 6자리 반올림이라 서로 가까운 값이 동점으로 합쳐질 수 있다 —
    저장된 백분위(p_*)로 동점 순서를 복원하기 위해 값에 1e-8×p 를 더한다(다른 반올림 값 사이 간격 ≥1e-6 이라 순서는 안 뒤집히고, 같은 p 는 같은 값 유지)."""
    EPS=1e-8
    return {t:[_r(a+EPS*pa,12),_r(b+EPS*pb,12),_r(c+EPS*pc,12),1] for t,a,b,c,pa,pb,pc in zip(day_df.ticker,day_df.sig,day_df.rsA,day_df.f1b,day_df.p_sig,day_df.p_rsA,day_df.p_f1b)}
def inherit_pair_sigma(rows, u, base_set):
    """R3 §1-3·§2-1: 짝 롱이 기본 37종(저장 원값 보유)이면 인버스의 σ 원값 = 짝 롱의 저장 σ. σ(−1x)=σ(1x) 항등식이며, 재계산값은 그날 최근 봉 보정·수신 개정(예 2026-11-18 지수 보정분)으로
    저장값과 1e-4~7e-3 어긋날 수 있어 저장 계열을 그대로 쓴다는 오너 규칙(짝 롱이 쓰는 저장 1x 계열)을 값으로 구현한다. RS·MA 항은 −1x 계열에서 따로 계산(짝과 다름)."""
    if "pair" not in u.columns: return rows
    for t,pr in zip(u.ticker,u.pair):
        if isinstance(pr,str) and pr in base_set and t in rows and pr in rows and rows[t][0] is not None and rows[pr][0] is not None:
            rows[t][0]=rows[pr][0]
    return rows
def write_year(y, dates, rows_by_date):
    """rows_by_date: {date: {ticker: row}} → docs/data/raw/<y>.json  (d: 날짜 배열, t: 종목별 날짜 정렬 배열, 없는 날은 null)"""
    RAWDIR.mkdir(parents=True,exist_ok=True)
    tk=sorted({t for d in dates for t in rows_by_date.get(d,{})})
    obj={"y":y,"f":FIELDS,"d":dates,"t":{t:[rows_by_date.get(d,{}).get(t) for d in dates] for t in tk}}
    with open(RAWDIR/f"{y}.json","w",encoding="utf-8") as f: json.dump(obj,f,ensure_ascii=False,separators=(",",":"))
    return len(tk)
def write_meta():
    """docs/data/groups_meta.json = {groups:[{id,label,chip,default}], gt:{티커:그룹 id}} — 브라우저 엔진 설정(종목→그룹). 기본 37종 = base"""
    gd=groups_def(); u=load_universe(); b=pd.read_csv(DATA/"universe.csv")
    gt={t:"base" for t in b.ticker}; gt.update({t:g for t,g in zip(u.ticker,u.grp)})
    obj={"groups":gd["groups"],"gt":gt}
    with open(L.DOCS/"data"/"groups_meta.json","w",encoding="utf-8") as f: json.dump(obj,f,ensure_ascii=False,separators=(",",":"))
    return len(gt)
def write_raw_index():
    """docs/data/raw/index.json = {years, cal(전 연도 날짜 오름차순)} — 브라우저 엔진이 달력·필요 연도를 알기 위해 먼저 읽는다(작음)"""
    ys=sorted(int(p.stem) for p in RAWDIR.glob("[0-9][0-9][0-9][0-9].json")); cal=[]
    for y in ys: cal+=json.load(open(RAWDIR/f"{y}.json",encoding="utf-8"))["d"]
    with open(RAWDIR/"index.json","w",encoding="utf-8") as f: json.dump({"years":ys,"cal":cal},f,separators=(",",":"))
    return len(ys),len(cal)
def read_year(y):
    p=RAWDIR/f"{y}.json"
    if not p.exists(): return None
    o=json.load(open(p,encoding="utf-8")); rb={}
    for t,arr in o["t"].items():
        for d,row in zip(o["d"],arr):
            if row is not None: rb.setdefault(d,{})[t]=row
    return o["d"],rb

# ---------- 기준 구현(파이썬) — 브라우저 JS(docs/assets/groups.js)와 같은 알고리즘. 6-1·6-5 검증이 둘을 서로 대조한다 ----------
def _pct(x):
    from scipy.stats import rankdata
    n=len(x)
    return np.array([0.5]) if n==1 else (rankdata(x)-1)/(n-1)
def day_scores(rows, tickers):
    """rows: {ticker: raw row}, tickers: 켜진 그룹의 종목 집합 → DataFrame(ticker,p_sig,p_rsA,p_f1b,M,rank). 모집단 = pop==1 ∧ 원값 3개 있음."""
    t=[k for k in sorted(tickers) if k in rows and rows[k][3]==1 and None not in rows[k][:3]]
    if not t: return pd.DataFrame(columns=["ticker","p_sig","p_rsA","p_f1b","M","rank"])
    a=np.array([rows[k][:3] for k in t],float)
    p=np.column_stack([_pct(a[:,j]) for j in range(3)])
    M=p.mean(axis=1)*100  # (p1+p2+p3)/3*100 — L.compute 와 같은 식
    M=(p[:,0]+p[:,1]+p[:,2])/3*100
    df=pd.DataFrame(dict(ticker=t,p_sig=p[:,0],p_rsA=p[:,1],p_f1b=p[:,2],M=M))
    df["rank"]=df.M.round(6).rank(ascending=False,method="min"); return df
def series_scores(by, cal, tickers, idx_from=0):
    """by: {date: {ticker: row}}, cal: 거래일 오름차순 문자열. 반환 {date: DataFrame(ticker,M,rank,p_*,d_rank,r5,r20,r60,a5,a20,a60)}  — d_rank = 5거래일 전 순위 − 오늘 순위(없으면 '신규'), r60 등은 mm_lib.period_ranks 와 같은 규칙(창의 80% 미만이면 결측)"""
    day={d:day_scores(by.get(d,{}),tickers) for d in cal}; out={}
    for i in range(idx_from,len(cal)):
        d=cal[i]; df=day[d].copy()
        prev=day[cal[i-5]] if i>=5 else None
        dr=[]
        for t,rk in zip(df.ticker,df["rank"]):
            if prev is None: dr.append("신규"); continue
            q=prev[prev.ticker==t]; dr.append(str(int(q.iloc[0]["rank"]-rk)) if len(q) else "신규")
        df["d_rank"]=dr
        for N in (5,20,60):
            win=cal[max(0,i-N+1):i+1]; acc={}
            for w in win:
                x=day[w]
                for t,m in zip(x.ticker,x.M): acc.setdefault(t,[]).append(float(m))
            need=math.ceil(0.8*N); a=[float(np.mean(acc[t])) if len(acc.get(t,[]))>=need else np.nan for t in df.ticker]
            df[f"a{N}"]=a; s=pd.Series(a); df[f"r{N}"]=s.round(6).rank(ascending=False,method="min").values if s.notna().any() else np.nan
        out[d]=df
    return out
