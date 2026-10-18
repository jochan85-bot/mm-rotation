#!/usr/bin/env python3
"""mm_rotation 일일 산출 — 수신 → 정제 → 적격 판정 → M-score → 저장 → 페이지 → push. 정상 시 텔레그램 0건, 실패 시 1건."""
import os, sys, signal, subprocess, traceback
import datetime as dt_mod
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import mm_lib as L, mm_site
def _timeout(sig,frm): raise TimeoutError("상한 5분 초과")
def is_manual():
    return os.environ.get("XPC_SERVICE_NAME","") not in ("com.mm.rotation_daily","com.mm.rotation_weekly") and os.environ.get("MM_AUTO")!="1"
def feed_check(T, prov, dropped, df, tail, now=None):
    """MM-FEED-LAG-FIX-20261018 §3: 산출 기준일 T 가 '직전 US 거래일'(마감 후 2시간 경과한 가장 최근 NYSE 거래일)이 아니면 경보 문구(사유 포함), 맞으면 None."""
    exp=L.prev_us_session(now)
    if pd.Timestamp(T).normalize()==exp: return None
    why=[]
    if prov: why.append(f"SPY 최신 봉 {prov['raw_last']} 미확정({prov['reason']}) → 직전 확정일 사용")
    if dropped: why.append(f"미확정 행 제거 {len(dropped)}종")
    w=df[df.table=="⚠"]
    if len(w): why.append(f"⚠ {len(w)}종: "+", ".join(w.ticker.head(8))+(" 외" if len(w)>8 else ""))
    try:
        import mm_tailetn; un=mm_tailetn.unresolved(tail)
        if un: why.append("1x 보정 불가: "+", ".join(f"{k}({v['status']})" for k,v in un.items()))
    except Exception: pass
    if not why: why.append("SPY 최신 봉이 기대 거래일보다 오래됨(수신 지연 추정)")
    return f"[mm_rotation] 미산출: 기준일 {pd.Timestamp(T).date()} ≠ 직전 US 거래일 {exp.date()} — "+"; ".join(why)
def run(push=True, fetch=True, manual=None, alert=None):
    if manual is None: manual=is_manual()
    if alert is None: alert="--no-alert" not in sys.argv
    L.check_formula()
    cfg=L.load_yaml_simple(L.DATA/"eligibility.yaml"); uni=pd.read_csv(L.DATA/"universe.csv"); status=L.load_status()
    need=L.need_tickers(); fails=[]
    if fetch:
        fails=L.fetch_all(need); L.log(f"수신 완료 실패={fails}")
        try:
            import mm_nasdaq; mm_nasdaq.apply_after_fetch(L.log)                 # 극저유동 ETN 3배 일봉: 나스닥 1차·야후 2차(MM-WRAP-BT §1)
        except Exception as e: L.log(f"[mm_nasdaq] 건너뜀: {type(e).__name__}: {str(e)[:150]}")
        binfo=L.build_synthetic(L.log); L.log(f"합성 1x 생성 {sum('error' not in v for v in binfo.values())}/{len(binfo)}")
        fails=fails+[k for k,v in binfo.items() if "error" in v]
    T,prov,dropped=L.clean_all(need+L.synthetic_keys()); L.log(f"기준일 T={T.date()} 잠정={prov} 미확정 행 제거={len(dropped)}종")
    try: tail=L.apply_tail_etn(T,log=L.log)                                   # 1x 최신 봉 < 기준일 → 3배 일간수익률÷3 으로 보정(최대 3일, MM-FEED-LAG-FIX-20261018 §2)
    except Exception as e: tail={}; L.log(f"[mm_tailetn] 보정 단계 실패(보정 없이 계속): {type(e).__name__}: {str(e)[:200]}","alerts")
    S=L.load_study(T)
    pq=pd.read_csv(L.DATA/"proxy_quality.csv")
    df,upd=L.compute(S,T,T,cfg,status,uni,pq,remeasure=True)
    for t in fails:
        df.loc[df.ticker==t,"reason"]=df.loc[df.ticker==t,"reason"].astype(str)+" [수신 실패: 직전 저장 데이터 사용]"
    if upd:
        for t,v in upd.items(): pq=pq[pq.ticker!=t]; pq=pd.concat([pq,pd.DataFrame([v])],ignore_index=True)
        pq.to_csv(L.DATA/"proxy_quality.csv",index=False); L.log(f"E4 재측정 갱신: {list(upd)}")
        df,_=L.compute(S,T,T,cfg,status,uni,pq,remeasure=False)           # 갱신된 품질 값으로 배지 재계산
    spy=S.loadp("SPY"); cal=[d for d in spy.index if d<=T]; pos={d:i for i,d in enumerate(cal)}
    # 소급·이력 보충: 2020-01-02 ~ T 중 파일이 없거나 규칙 버전이 다른 날짜(T 제외)를 산출 — 윈도우 선행분(약 64거래일)은 기록 없이 메모리로만
    first=L.RETRO_START
    regen_from=pd.Timestamp(next((a.split("=",1)[1] for a in sys.argv if a.startswith("--regen-from=")),"2262-01-01"))   # 규칙 변경 시 이 날짜부터 날짜 파일 강제 재산출
    def stale_day(d):
        h=L.day_header(L.day_path(d)); return h is None or h[2]!=L.RULE_VER or d>=regen_from
    todo=[d for d in cal if first<=d<T and stale_day(d)]
    if todo:
        i0=pos[todo[0]]; warm=[d for d in cal[max(0,i0-64):i0] if stale_day(d) or d<first]
        L.log(f"날짜별 파일 산출 {len(todo)}일 (워밍업 {len(warm)}일)")
        L.fill_days(S,cfg,uni,pq,cal,warm+todo,write_from=todo[0],log=L.log)
    def _load(d):
        return L.read_day(d)
    df=L.finish_day(df,T,cal,pos,_load)
    df["provisional"]=int(prov is not None); df["backfill"]=0
    L.write_day(T,df); df.to_csv(L.DATA/"scores_latest.csv",index=False)
    idx=L.rebuild_index(); L.log(f"index.json {idx['count']}일 ({idx['first']}~{idx['last']})")
    an=L.scan_anomalies(S,uni,cfg); an.to_csv(L.DATA/"anomalies.csv",index=False)
    import json
    np_path=L.DATA/"new_products.json"
    newp=json.load(open(np_path,encoding="utf-8")).get("candidates",[]) if np_path.exists() else []
    pipe_path=L.DATA/"pipeline.json"
    pipe=json.load(open(pipe_path,encoding="utf-8")).get("items",[]) if pipe_path.exists() else []
    meta=dict(asof=str(T.date()),generated=L.now_kst().strftime("%Y-%m-%d %H:%M"),provisional=prov,new_products=newp,pipeline=pipe,dropped=dropped,manual=manual,anomalies=an)
    p0=pd.read_csv(L.DATA/"product_info.csv")
    mm_site.build_all(df,uni,meta,p0,[])
    n_el=int((df.table=="순위").sum()); L.log(f"산출 완료 순위 {n_el}/{len(df)} 제외 {(df.table=='제외').sum()} ⚠ {(df.table=='⚠').sum()} 배지 종목 {(df.badges.fillna('')!='').sum()} 이상봉 {len(an)}건")
    if push: git_push(T)
    check_and_alert(T,prov,dropped,df,tail,alert=alert)                    # 미산출 감시(§3): 기준일 ≠ 직전 US 거래일이면 경보 1건
    return df
def check_and_alert(T, prov, dropped, df, tail, alert=True, now=None):
    """feed_check 결과가 있으면 alerts.log + (alert=True 면) 텔레그램 1건. 확인 자체가 실패해도 산출을 깨지 않는다. 반환 = 경보 문구 또는 None."""
    try: msg=feed_check(T,prov,dropped,df,tail,now=now)
    except Exception as e: msg=None; L.log(f"[미산출 감시] 기준일 확인 실패(무시): {type(e).__name__}: {str(e)[:150]}","alerts")
    if msg:
        if alert: L.alert(msg)
        else: L.log(msg,"alerts")
    return msg
def git_push(T):
    def g(*a): return subprocess.run(["git","-C",str(L.ROOT),*a],capture_output=True,text=True,timeout=120)
    g("add","-A")
    if g("status","--porcelain").stdout.strip():
        r=g("commit","-m",f"Auto: M-score {T.date()}"); 
        if r.returncode!=0: raise RuntimeError("git commit 실패: "+r.stderr[-200:])
    r=g("push","origin","main")
    if r.returncode!=0: raise RuntimeError("git push 실패: "+r.stderr[-300:])
    L.log("push 완료")
def basis_check(now=None):
    """scores_latest.csv 기준일이 직전 US 거래일(마감 후 2시간 경과한 가장 최근 NYSE 거래일 — 토요일 실행이면 금요일)인지. 반환 (정상여부, 기준일 또는 None, 직전 거래일, 사유). MM-FEED-LAG-FIX-20261018 §3"""
    exp=L.prev_us_session(now); p=L.DATA/"scores_latest.csv"
    if not p.exists(): return False,None,exp,"scores_latest.csv 없음"
    d=pd.read_csv(p,usecols=["date"])
    if not len(d): return False,None,exp,"scores_latest.csv 비어 있음"
    got=pd.Timestamp(str(d["date"].iloc[0])).normalize()
    return got==exp,got,exp,("" if got==exp else f"기준일 {got.date()} ≠ 직전 US 거래일 {exp.date()}")
def needs_retry(now=None):
    """10:15 재실행 가드(MM-STALE-FIX-20261011 §2c): 최신 산출에 ⚠ 가 있거나, 잠정 기준일이거나(MM-CONFIRM-FIX-20261013 §2), 오늘(KST) 산출 자체가 없으면 True. 그 외엔 아무것도 하지 않는다."""
    p=L.DATA/"scores_latest.csv"
    if not p.exists(): return True,"scores_latest.csv 없음"
    now=now or L.now_kst()
    mt=dt_mod.datetime.fromtimestamp(p.stat().st_mtime,L.KST)
    if mt.date()!=now.date(): return True,f"오늘 산출 없음(마지막 {mt:%Y-%m-%d %H:%M})"
    d=pd.read_csv(p); w=d[d.table=="⚠"]
    if len(w): return True,f"⚠ {len(w)}종: {','.join(w.ticker)}"
    if "provisional" in d.columns and int(d["provisional"].fillna(0).max())==1: return True,"잠정 기준일(MM-CONFIRM-FIX-20261013 §2)"
    if "date" in d.columns and len(d):                                           # MM-FEED-LAG-FIX-20261018 §3: 기준일이 직전 US 거래일이 아니면 재실행
        try:
            exp=L.prev_us_session(now); got=pd.Timestamp(str(d["date"].iloc[0])).normalize()
            if got!=exp: return True,f"기준일 {got.date()} ≠ 직전 US 거래일 {exp.date()}"
        except Exception as e: L.log(f"[재실행 가드] 기준일 확인 실패(무시): {type(e).__name__}: {str(e)[:100]}","alerts")
    return False,"⚠ 0 · 확정 기준일 · 오늘 산출 있음"
if __name__=="__main__":
    # MM-FEED-LAG-FIX-20261018 §3: 가드·산출·push 전부 한 try 안 — 예외·타임아웃·push 실패는 종료 코드와 무관하게 alerts.log + 텔레그램(L.alert)
    push="--no-push" not in sys.argv; fetch="--no-fetch" not in sys.argv
    manual=is_manual()
    if "--rebuild-history" not in sys.argv:
        signal.signal(signal.SIGALRM,_timeout); signal.alarm(300)
    try:
        if "--only-if-warn" in sys.argv:
            need,why=needs_retry(); L.log(f"[재실행 가드] {'재실행' if need else '불필요 — 종료'}: {why}")
            if not need: sys.exit(0)
        df_=run(push,fetch,manual)
        if "--only-if-warn" in sys.argv:
            w=df_[df_.table=="⚠"]
            if len(w): L.log(f"[재실행 후에도 ⚠ {len(w)}종] "+"; ".join(f"{r.ticker}: {r.reason}" for r in w.itertuples()),"alerts")
    except SystemExit: raise
    except BaseException as e:
        msg=f"[mm_rotation] 일일 산출 실패: {type(e).__name__}: {str(e)[:300]}"
        L.log(msg+"\n"+traceback.format_exc()[-1500:],"alerts")
        if "--no-alert" not in sys.argv: L.tg_send(msg)
        sys.exit(1)
