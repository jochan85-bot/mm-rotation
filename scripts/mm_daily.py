#!/usr/bin/env python3
"""mm_rotation 일일 산출 — 수신 → 정제 → 적격 판정 → M-score → 저장 → 페이지 → push. 정상 시 텔레그램 0건, 실패 시 1건."""
import os, sys, signal, subprocess, traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import mm_lib as L, mm_site
def _timeout(sig,frm): raise TimeoutError("상한 5분 초과")
HIST_DAYS=62
def _ver_ok(path):
    try: return "rule_ver" in open(path,encoding="utf-8").readline() and pd.read_csv(path,usecols=["rule_ver"]).rule_ver.iloc[0]==L.RULE_VER
    except Exception: return False
def is_manual():
    return os.environ.get("XPC_SERVICE_NAME","") not in ("com.mm.rotation_daily","com.mm.rotation_weekly") and os.environ.get("MM_AUTO")!="1"
def run(push=True, fetch=True, manual=None):
    if manual is None: manual=is_manual()
    L.check_formula()
    cfg=L.load_yaml_simple(L.DATA/"eligibility.yaml"); uni=pd.read_csv(L.DATA/"universe.csv"); status=L.load_status()
    need=L.need_tickers(); fails=[]
    if fetch:
        fails=L.fetch_all(need); L.log(f"수신 완료 실패={fails}")
        binfo=L.build_synthetic(L.log); L.log(f"합성 1x 생성 {sum('error' not in v for v in binfo.values())}/{len(binfo)}")
        fails=fails+[k for k,v in binfo.items() if "error" in v]
    T,prov,dropped=L.clean_all(need+L.synthetic_keys()); L.log(f"기준일 T={T.date()} 잠정={prov} 미확정 행 제거={len(dropped)}종")
    S=L.load_study(T)
    pq=pd.read_csv(L.DATA/"proxy_quality.csv")
    df,upd=L.compute(S,T,T,cfg,status,uni,pq,remeasure=True)
    for t in fails:
        df.loc[df.ticker==t,"reason"]=df.loc[df.ticker==t,"reason"].astype(str)+" [수신 실패: 직전 저장 데이터 사용]"
    if upd:
        for t,v in upd.items(): pq=pq[pq.ticker!=t]; pq=pd.concat([pq,pd.DataFrame([v])],ignore_index=True)
        pq.to_csv(L.DATA/"proxy_quality.csv",index=False); L.log(f"E4 재측정 갱신: {list(upd)}")
        df,_=L.compute(S,T,T,cfg,status,uni,pq,remeasure=False)           # 갱신된 품질 값으로 배지 재계산
    spy=S.loadp("SPY"); dates=[d for d in spy.index if d<=T][-HIST_DAYS:]
    (L.DATA/"scores").mkdir(exist_ok=True)
    for d in dates[:-1]:                       # 이력 보충(없거나 규칙 버전이 다른 날짜만; E4·E5 는 현재 상태 적용)
        p=L.DATA/"scores"/f"{d.date()}.csv"
        if not p.exists() or not _ver_ok(p):
            h,_=L.compute(S,d,T,cfg,status,uni,pq,remeasure=False); h["backfill"]=1; h.to_csv(p,index=False)
    prev=None
    if len(dates)>=6:
        pp=L.DATA/"scores"/f"{dates[-6].date()}.csv"
        if pp.exists(): prev=pd.read_csv(pp)
    drk=[]
    for r in df.itertuples():
        if r.table!="순위" or pd.isna(r.rank): drk.append(""); continue
        if prev is None: drk.append("신규"); continue
        q=prev[(prev.ticker==r.ticker)&(prev.table=="순위")]
        drk.append(str(int(q.iloc[0]["rank"]-r.rank)) if len(q) and not pd.isna(q.iloc[0]["rank"]) else "신규")
    df["d_rank"]=drk; df["provisional"]=int(prov is not None); df["backfill"]=0
    df=L.period_ranks(df,dates,lambda d: pd.read_csv(L.DATA/"scores"/f"{d.date()}.csv") if (L.DATA/"scores"/f"{d.date()}.csv").exists() else None)
    df.to_csv(L.DATA/"scores"/f"{T.date()}.csv",index=False); df.to_csv(L.DATA/"scores_latest.csv",index=False)
    an=L.scan_anomalies(S,uni,cfg); an.to_csv(L.DATA/"anomalies.csv",index=False)
    import json
    np_path=L.DATA/"new_products.json"
    newp=json.load(open(np_path,encoding="utf-8")).get("candidates",[]) if np_path.exists() else []
    pipe_path=L.DATA/"pipeline.json"
    pipe=json.load(open(pipe_path,encoding="utf-8")).get("items",[]) if pipe_path.exists() else []
    meta=dict(asof=str(T.date()),generated=L.now_kst().strftime("%Y-%m-%d %H:%M"),provisional=prov,new_products=newp,pipeline=pipe,dropped=dropped,manual=manual,anomalies=an)
    p0=pd.read_csv(L.DATA/"product_info.csv")
    files=sorted((L.DATA/"scores").glob("*.csv")); files=[f for f in files if f.stem<=str(T.date())]
    mm_site.build_all(df,uni,meta,p0,files)
    n_el=int((df.table=="순위").sum()); L.log(f"산출 완료 순위 {n_el}/{len(df)} 제외 {(df.table=='제외').sum()} ⚠ {(df.table=='⚠').sum()} 배지 종목 {(df.badges.fillna('')!='').sum()} 이상봉 {len(an)}건")
    if push: git_push(T)
    return df
def git_push(T):
    def g(*a): return subprocess.run(["git","-C",str(L.ROOT),*a],capture_output=True,text=True,timeout=120)
    g("add","-A")
    if g("status","--porcelain").stdout.strip():
        r=g("commit","-m",f"Auto: M-score {T.date()}"); 
        if r.returncode!=0: raise RuntimeError("git commit 실패: "+r.stderr[-200:])
    r=g("push","origin","main")
    if r.returncode!=0: raise RuntimeError("git push 실패: "+r.stderr[-300:])
    L.log("push 완료")
if __name__=="__main__":
    push="--no-push" not in sys.argv; fetch="--no-fetch" not in sys.argv
    # launchd 가 띄운 실행이면 XPC_SERVICE_NAME 이 라벨과 같다 -> 자동 산출. 그 외(수동)는 페이지 상단에 '수동 산출' 표기(§5)
    manual=is_manual()
    if "--rebuild-history" not in sys.argv:
        signal.signal(signal.SIGALRM,_timeout); signal.alarm(300)
    try:
        run(push,fetch,manual)
    except BaseException as e:
        msg=f"[mm_rotation] 일일 산출 실패: {type(e).__name__}: {str(e)[:300]}"
        L.log(msg+"\n"+traceback.format_exc()[-1500:],"alerts")
        if "--no-alert" not in sys.argv: L.tg_send(msg)
        sys.exit(1)
