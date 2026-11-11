#!/usr/bin/env python3
"""mm_rotation 일일 산출 — 수신 → 정제 → 적격 판정 → M-score → 저장 → 페이지 → push. 정상 시 텔레그램 0건, 실패 시 1건."""
import os, sys, signal, subprocess, traceback, argparse, shutil, tempfile
import datetime as dt_mod
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
try:
    import numpy as np, pandas as pd
    import mm_lib as L, mm_site
except BaseException as _e:      # MM-RESTORE-20261028 §4-2: import 단계 실패도 침묵 금지(mm_lib 비의존 경보)
    import mm_bootalert; mm_bootalert.fail('일일 산출', _e); raise
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
def published_T():
    """이번 실행 전 마지막으로 발행(저장)된 산출 기준일 — scores_latest.csv 의 date. 없으면 None."""
    p=L.DATA/"scores_latest.csv"
    try: return pd.Timestamp(str(pd.read_csv(p,usecols=["date"])["date"].iloc[0])).normalize()
    except Exception: return None
def stale_T_guard(prev_pub, T, regen):
    """직전 발행 기준일보다 오래된 T 의 자동 발행을 막는다(True=차단). --regen-from 명시(regen=True)만 예외."""
    return bool(prev_pub is not None and pd.Timestamp(T).normalize()<pd.Timestamp(prev_pub).normalize() and not regen)
def shrink_guard(n_old, n_new, regen):
    """이미 저장된 날짜 파일(N=n_old)보다 종목 수가 줄어드는(n_new<n_old) 덮어쓰기를 막는다(True=차단). --regen-from 명시만 예외."""
    return bool(n_old is not None and n_new<n_old and not regen)
def pass_msg(T, prev_pub, n):
    """발행 가드 통과 1줄 — 차단·예외 때만 남던 로그에 통과 사실을 남긴다(MM-PASSLOG-20261106, 표시 전용)."""
    return f"[발행 가드] 통과: T={pd.Timestamp(T).date()}, 직전 발행 T={pd.Timestamp(prev_pub).date() if prev_pub is not None else '없음'}, N={n}"
def _opt(name):
    """sys.argv 에서 '--name=값' 또는 '--name 값'."""
    for i,a in enumerate(sys.argv):
        if a.startswith(name+"="): return a.split("=",1)[1]
        if a==name and i+1<len(sys.argv): return sys.argv[i+1]
    return None
def run(push=True, fetch=True, manual=None, alert=None):
    if manual is None: manual=is_manual()
    if alert is None: alert="--no-alert" not in sys.argv
    L.check_formula()
    prev_pub=published_T()                                                  # MM-SPLIT-GUARD-20261106 §발행 가드: 이번 실행 전 마지막 발행 기준일
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
    regen_flag=any(a.startswith("--regen-from=") for a in sys.argv)
    if regen_flag:                                                          # 발행 가드의 유일한 예외 — 명시 사실과 사유를 로그에 남긴다
        L.log(f"[발행 가드 예외] --regen-from 명시: 인자={sys.argv[1:]} 사유={_opt('--regen-reason') or '(미기재)'}"); L.log(f"[발행 가드 예외] --regen-from 명시 사유={_opt('--regen-reason') or '(미기재)'}","alerts")
    if stale_T_guard(prev_pub,T,regen_flag):
        msg=f"[mm_rotation] 발행 가드: 산출 기준일 T={pd.Timestamp(T).date()} < 직전 발행 기준일 {prev_pub.date()} — 자동 발행 금지(점수 파일·페이지·push 무변경)" + (f"; 잠정 사유 {prov}" if prov else "")
        L.log(msg,"alerts")
        if alert: L.tg_send(msg)
        return None
    split_info={}
    try:                                                                    # MM-SPLIT-GUARD-20261106: 1x 대용 분할 반영 시차 — 아티팩트 봉부터 제외 → 아래 apply_tail_etn 이 3배÷3 로 보충
        import mm_splits
        _ev={}
        for e in mm_splits.nasdaq_calendar(pd.Timestamp(T)-pd.Timedelta(days=mm_splits.LOOKBACK),timeout=10): _ev.setdefault(e["symbol"],[]).append(e)
        split_info=mm_splits.guard(T,uni,L.RAW/"data",log=L.log,write=True,cal_events=_ev,info_path=L.LOCAL/"split_pending.json")
    except Exception as e: split_info={}; L.log(f"[mm_splits] 가드 단계 실패(가드 없이 계속): {type(e).__name__}: {str(e)[:200]}","alerts")
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
    if split_info:
        import mm_splits; df=mm_splits.annotate(df,split_info)               # 점수·순위 불변, reason 표시만
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
    n_new=int(((df.table=="순위")&df.M.notna()).sum()); n_old=L.existing_day_n(T)
    if shrink_guard(n_old,n_new,regen_flag):                                # MM-SPLIT-GUARD-20261106: 이미 발행된 날짜 파일보다 종목 수가 줄어드는 덮어쓰기 금지
        msg=f"[mm_rotation] 발행 가드: {pd.Timestamp(T).date()} 점수 파일을 N={n_old}→{n_new} 로 줄여 덮어쓰려 함 — 중단(파일·페이지·push 무변경, 제외 종목 {sorted(set(df[df.table!='순위'].ticker))[:8]})"
        L.log(msg,"alerts")
        if alert: L.tg_send(msg)
        return None
    L.log(pass_msg(T,prev_pub,n_new))                                       # MM-PASSLOG-20261106: 차단 2종(stale_T·shrink)을 모두 통과한 시점
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
    try:                                                                    # MM-PRICE-CHART-20261111: 종목 페이지 가격 차트 새 봉 덧붙임 — 후단 훅(점수·순위 산출 후, 읽기 원천 = RAW). 실패해도 발행 계속
        import mm_charts; mm_charts.daily_update(log=L.log)
    except Exception as e: L.log(f"[mm_charts] 가격 차트 갱신 실패(발행 계속): {type(e).__name__}: {str(e)[:200]}","alerts")
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
    if os.environ.get("MM_DRY_RUN_CHILD")=="1":                            # --dry-run 자식 프로세스: 어떤 경로로도 push 하지 않는다(부모는 origin 도 제거한 복사본에서 실행)
        L.log("push 건너뜀 (dry-run)"); return
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
def build_parser():
    p=argparse.ArgumentParser(prog="mm_daily.py",allow_abbrev=False,
        description="mm_rotation 일일 산출 — 수신 → 정제 → 분할 가드 → 보정 → 적격 판정 → M-score → 저장 → 페이지 → push. 정상 시 텔레그램 0건, 실패 시 1건. 인자 없이 실행하면 곧바로 일일 실행(launchd).")
    p.add_argument("--no-push",action="store_true",help="산출만 하고 git push 하지 않는다(작업트리는 갱신됨)")
    p.add_argument("--no-fetch",action="store_true",help="수신 생략 — 저장된 이력으로 재산출")
    p.add_argument("--no-alert",action="store_true",help="텔레그램 경보 생략(alerts.log 에는 남김)")
    p.add_argument("--only-if-warn",action="store_true",help="10:15 재실행 가드: ⚠·잠정·기준일 불일치·오늘 산출 없음일 때만 실행")
    p.add_argument("--rebuild-history",action="store_true",help="이력 재구축(5분 알람 해제)")
    p.add_argument("--regen-from",metavar="YYYY-MM-DD",help="이 날짜부터 날짜 파일 강제 재산출 — 발행 가드(과거 T·종목 수 축소 덮어쓰기 금지)의 유일한 예외")
    p.add_argument("--regen-reason",metavar="TEXT",help="--regen-from 사유(로그에 남음)")
    p.add_argument("--dry-run",action="store_true",help="산출만 — 저장소를 임시 복사본(origin 제거)에서 실행하므로 작업트리·발행·push·텔레그램 0. 결과 요약만 출력")
    return p
def dry_run(argv, keep=False):
    """MM-SPLIT-GUARD-20261106: live 트리를 건드리지 않는 산출. ROOT 를 임시 폴더로 복사(.git 포함) → origin 제거 → 복사본의 mm_daily.py 를 --no-push --no-alert + MM_TG_SUPPRESS=1 로 실행 → 요약. 발행 경로 없음."""
    tmp=Path(tempfile.mkdtemp(prefix="mm_dryrun_")); work=tmp/"mm_rotation"
    try:
        shutil.copytree(L.ROOT,work,ignore=shutil.ignore_patterns("__pycache__"),symlinks=True)
        subprocess.run(["git","-C",str(work),"remote","remove","origin"],capture_output=True,text=True,timeout=60)
        cmd=[sys.executable,str(work/"scripts"/"mm_daily.py")]+[a for a in argv if a!="--dry-run"]+["--no-push","--no-alert"]
        env=dict(os.environ,MM_DRY_RUN_CHILD="1",MM_TG_SUPPRESS="1")
        r=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=290)
        print("[dry-run] 자식 종료 코드",r.returncode,"· 복사본",work)
        print("\n".join((r.stdout or "").strip().splitlines()[-12:]))
        if r.returncode!=0: print((r.stderr or "")[-600:])
        try:
            sl=pd.read_csv(work/"data"/"scores_latest.csv"); print(f"[dry-run] 기준일 {sl['date'].iloc[0]} · 순위 {int((sl.table=='순위').sum())}/{len(sl)} · ⚠ {int((sl.table=='⚠').sum())}")
        except Exception as e: print("[dry-run] 결과 요약 실패",type(e).__name__)
        print("[dry-run] live 작업트리·저장소·텔레그램 무변경(발행 경로 없음)")
        return r.returncode
    finally:
        if not keep and os.environ.get("MM_DRY_RUN_KEEP")!="1": shutil.rmtree(tmp,ignore_errors=True)
def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    args=build_parser().parse_args(argv)           # -h/--help → 사용법만 출력하고 exit 0 · 모르는 인자 → exit 2 — 어느 경우에도 산출·push 는 시작하지 않는다
    if args.regen_from and not (args.regen_reason or "").strip():   # 오너 결정 2026-11-06 14:49: --regen-reason 필수 — 사유 미기재(공백 포함)는 산출 전에 거부
        build_parser().error("--regen-from 에는 --regen-reason \"사유\" 가 필요합니다(사유 미기재 시 거부 — 발행 가드 예외의 감사 기록)")
    # run() 이 sys.argv 를 직접 보므로 '--regen-from DATE' 형태도 '--regen-from=DATE' 로 정규화
    canon=[]; skip=False
    for i,a in enumerate(argv):
        if skip: skip=False; continue
        if a in ("--regen-from","--regen-reason") and i+1<len(argv): canon.append(f"{a}={argv[i+1]}"); skip=True
        else: canon.append(a)
    sys.argv=[sys.argv[0]]+canon
    if args.dry_run: return dry_run(canon)
    child=os.environ.get("MM_DRY_RUN_CHILD")=="1"
    push=(not args.no_push) and not child; fetch=not args.no_fetch
    manual=is_manual()
    if not args.rebuild_history:
        signal.signal(signal.SIGALRM,_timeout); signal.alarm(300)
    try:
        if args.only_if_warn:
            need,why=needs_retry(); L.log(f"[재실행 가드] {'재실행' if need else '불필요 — 종료'}: {why}")
            if not need: return 0
        df_=run(push,fetch,manual,alert=(not args.no_alert) and not child)
        if args.only_if_warn and df_ is not None:
            w=df_[df_.table=="⚠"]
            if len(w): L.log(f"[재실행 후에도 ⚠ {len(w)}종] "+"; ".join(f"{r.ticker}: {r.reason}" for r in w.itertuples()),"alerts")
        return 0
    except SystemExit: raise
    except BaseException as e:
        msg=f"[mm_rotation] 일일 산출 실패: {type(e).__name__}: {str(e)[:300]}"
        L.log(msg+"\n"+traceback.format_exc()[-1500:],"alerts")
        if not args.no_alert and not child: L.tg_send(msg)
        return 1
if __name__=="__main__":
    sys.exit(main())
