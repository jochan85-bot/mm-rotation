"""MM-PAGE-V2.3 단위 테스트 — 배지 판정·이상 봉 가드·E3 무거래 2봉·기간 평균 순위·신규 상품 분류. python3 tests/test_v23.py"""
import sys, tempfile, json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT/"scripts"))
import numpy as np, pandas as pd
from scipy.stats import rankdata
import mm_lib as L, mm_newprod as NP, mm_site
cfg=L.load_yaml_simple(ROOT/"data"/"eligibility.yaml")
ok=0; bad=[]
def check(name,cond,detail=""):
    global ok
    if cond: ok+=1; print("PASS",name)
    else: bad.append(name); print("FAIL",name,detail)
# ---- 1. 배지 ----
B=lambda **k: L.badges_for(k.get("ld",500),k.get("adtv",50.0),k.get("zero",0),k.get("beta",3.0),k.get("r2",0.99),k.get("nb",252),cfg)
check("배지 없음",B()==[],B())
check("표본부족 n<60 (MNGU 류)",B(nb=28,beta=3.07,r2=0.993)==["표본부족"],B(nb=28))
check("근사: β 밖",B(beta=3.5)==["근사"] and B(beta=2.5)==["근사"])
check("근사: R²<0.85",B(r2=0.80)==["근사"])
check("신규 listed<252",B(ld=251)==["신규"] and B(ld=252)==[])
check("저유동 <$0.3M (V2.3-FOLLOWUP §1)",B(adtv=0.29)==["저유동"] and B(adtv=0.3)==[] and B(adtv=0.9)==[])
check("무거래N (V=0 2봉)",B(zero=2)==["무거래2"] and B(zero=1)==["무거래1"] and B(zero=0)==[])
check("복합 배지 순서",B(nb=18,ld=18,adtv=0.2,zero=3)==["표본부족","신규","저유동","무거래3"])
# ---- 2. compute 합성 시나리오 ----
rng=np.random.default_rng(7); N=420
idx=pd.bdate_range(end="2026-10-08",periods=N)
def series(vol=0.01,start=100.0,seed=0,volm=1e6):
    r=np.random.default_rng(seed).normal(0.0004,vol,N); c=start*np.cumprod(1+r)
    return pd.DataFrame({"Close":c,"Volume":np.full(N,volm)},index=idx)
class Stub:
    def __init__(s,data): s.d=data; s.F={}
    def loadp(s,k): return s.d[k]
    def pct_rank(s,x):
        n=len(x); return np.array([0.5]) if n==1 else (rankdata(x)-1)/(n-1)
    def feat1x(s,px):
        if px in s.F: return s.F[px]
        c=s.d[px]["Close"].values.astype(float); r=np.r_[np.nan,c[1:]/c[:-1]-1]
        s60=pd.Series(r).rolling(60).std().values*np.sqrt(252); sc=pd.Series(c)
        ma50=sc.rolling(50).mean().values; ma200=sc.rolling(200).mean().values
        f2a=np.full(len(c),np.nan)
        for k in range(252,len(c)): f2a[k]=c[k-21]/c[k-252]-1
        s.F[px]=dict(s60=s60,f2a=f2a,f1b=ma50/ma200-1); return s.F[px]
def mk(extra=None):
    d={}; tick=["AAA","BBB","CCC","DDD","EEE"]
    for i,t in enumerate(tick):
        d["X"+t]=series(0.01+0.002*i,seed=i)                       # 1x
        d[t]=series(0.03+0.006*i,seed=10+i)                        # 3x
    if extra: extra(d)
    uni=pd.DataFrame(dict(ticker=tick,group="A",type="ETF",issuer="Z",proxy=["X"+t for t in tick],proxy_disp="",proxy_tip="",leverage="3x"))
    pq=pd.DataFrame([dict(ticker=t,proxy="X"+t,beta=3.0,r2=0.99,n=252,measured="2026-10-08",ok=1) for t in tick])
    return Stub(d),uni,pq
asof=pd.Timestamp("2026-10-08"); st={"excluded":{}}
S,uni,pq=mk(); df,_=L.compute(S,asof,asof,cfg,st,uni,pq)
check("기준 시나리오: 5종 전부 순위",(df.table=="순위").all() and df["rank"].notna().all(),df[["ticker","table","reason"]].to_string())
# 1x 이상 봉: 최근 60봉 안(+30%)
def inj1(d):
    x=d["XCCC"].copy(); x.iloc[-30:,x.columns.get_loc("Close")]*=1.30; d["XCCC"]=x
S,uni,pq=mk(inj1); df,_=L.compute(S,asof,asof,cfg,st,uni,pq); r=df[df.ticker=="CCC"].iloc[0]
check("1x 이상 봉(+30%, 60봉 내) → ⚠·순위 제외",r.table=="⚠" and pd.isna(r["rank"]) and pd.isna(r.M) and "1x 이상 봉" in r.reason,r.reason)
check("이상 봉 사유에 날짜 표기",str(idx[-30].date()) in r.reason,r.reason)
# 60봉 밖이면 영향 없음
def inj1b(d):
    x=d["XCCC"].copy(); x.iloc[-100:,x.columns.get_loc("Close")]*=1.30; d["XCCC"]=x
S,uni,pq=mk(inj1b); df,_=L.compute(S,asof,asof,cfg,st,uni,pq); check("60봉 밖 이상 봉은 순위 유지",df[df.ticker=="CCC"].iloc[0].table=="순위")
# 임계 이하(24%)는 통과
def inj1c(d):
    x=d["XCCC"].copy(); x.iloc[-30:,x.columns.get_loc("Close")]*=1.20; d["XCCC"]=x
S,uni,pq=mk(inj1c); df,_=L.compute(S,asof,asof,cfg,st,uni,pq); check("20% 점프(임계 25% 미만)는 가드 미발동",df[df.ticker=="CCC"].iloc[0].table=="순위")
# 3배 이상 봉(기준일 봉 -80%)
def inj3(d):
    x=d["DDD"].copy(); x.iloc[-1,x.columns.get_loc("Close")]*=0.2; d["DDD"]=x
S,uni,pq=mk(inj3); df,_=L.compute(S,asof,asof,cfg,st,uni,pq); r=df[df.ticker=="DDD"].iloc[0]
check("3배 이상 봉(-80%, 기준일) → ⚠",r.table=="⚠" and "3배 이상 봉" in r.reason,r.reason)
# 3배 과거 이상 봉은 순위 유지(점수에 안 들어감) — anomalies.csv 목록에는 오름
def inj3b(d):
    x=d["DDD"].copy(); x.iloc[-50:,x.columns.get_loc("Close")]*=3.0; d["DDD"]=x
S,uni,pq=mk(inj3b); df,_=L.compute(S,asof,asof,cfg,st,uni,pq); an=L.scan_anomalies(S,uni,cfg)
check("3배 과거 이상 봉은 기준일 아니면 순위 유지·목록에 기록",df[df.ticker=="DDD"].iloc[0].table=="순위" and ((an.series=="3x")&(an.ticker=="DDD")).any(),an.to_string())
# E3: 무거래 2봉 → 배지만, 순위 유지
def inj_v(d):
    x=d["BBB"].copy(); x.iloc[-5:-3,x.columns.get_loc("Volume")]=0; d["BBB"]=x
S,uni,pq=mk(inj_v); df,_=L.compute(S,asof,asof,cfg,st,uni,pq); r=df[df.ticker=="BBB"].iloc[0]
check("E3 V=0 2봉 → 배지 '무거래2'·순위 유지",r.table=="순위" and r.badges=="무거래2" and pd.notna(r["rank"]),str(r.badges))
# E5 제외
S,uni,pq=mk(); df,_=L.compute(S,asof,asof,cfg,{"excluded":{"EEE":{"type":"조기상환","date":"2026-10-01"}}},uni,pq)
check("E5 제외 종목은 모집단 밖(순위 NaN)·나머지 4종 백분위 모집단 4",df[df.ticker=="EEE"].iloc[0].table=="제외" and pd.isna(df[df.ticker=="EEE"].iloc[0]["rank"]) and (df[df.table=="순위"].p_sig.max()==1.0) and len(df[df.table=="순위"])==4)
# 최신 봉 불일치 → ⚠
def inj_stale(d): d["AAA"]=d["AAA"].iloc[:-2]
S,uni,pq=mk(inj_stale); df,_=L.compute(S,asof,asof,cfg,st,uni,pq); check("3배 최신 봉 불일치 → ⚠",df[df.ticker=="AAA"].iloc[0].table=="⚠")
# ---- 3. 기간 평균 순위 ----
dates=list(idx[-60:]); T=dates[-1]
def day(vals,table="순위"): return pd.DataFrame(dict(ticker=list(vals),table=table,M=list(vals.values())))
today=pd.DataFrame(dict(ticker=["A","B","C"],table="순위",M=[50.0,60.0,70.0]))
hist={d:day({"A":10.0,"B":90.0,"C":50.0}) for d in dates[:-1]}
hist[dates[-2]]=day({"A":10.0,"B":90.0})                      # C 결측 1일
out=L.period_ranks(today.copy(),dates,lambda d:hist.get(d))
check("5일 평균: A=(10×4+50)/5",abs(out.loc[0,"a5"]-(10*4+50)/5)<1e-9,str(out.loc[0,"a5"]))
check("5일 순위: B(84)=1, C(55)=2, A(18)=3",out.set_index("ticker").r5.to_dict()=={"A":3.0,"B":1.0,"C":2.0},str(out.set_index("ticker").r5.to_dict()))
check("결측일 제외 평균(C 5일 = 4일 평균)",out.loc[2,"n5"]==4 and abs(out.loc[2,"a5"]-(50+50+50+70)/4)<1e-9,str((out.loc[2,'n5'],out.loc[2,'a5'])))
# 80% 미만 → 결측
hist2={d:(day({"A":10.0,"B":90.0}) if i<20 else day({"A":10.0,"B":90.0,"C":50.0})) for i,d in enumerate(dates[:-1])}   # C 는 마지막 40일만 존재 (60일 창의 41/60=68%)
o2=L.period_ranks(today.copy(),dates,lambda d:hist2.get(d)); c=o2[o2.ticker=="C"].iloc[0]
check("60일: 창의 80% 미만이면 '—'(결측)·순위 NaN",pd.isna(c.a60) and pd.isna(c.r60) and c.n60==40 and not pd.isna(c.r20),str((c.n60,c.a60)))
check("5일/20일 순위는 모집단 안 순위 (동점 동순위)",set(o2.r20.dropna())<= {1.0,2.0,3.0})
# ---- 4. 신규 상품 분류 ----
tests=[("ProShares UltraPro Magnificent 7","", "3x","include"),("ProShares UltraPro Gold K-1 Free ETF","","3x","exclude"),("ProShares UltraPro Gold Miners","","3x","include"),
       ("","DULL","-3x","exclude"),("","WTID","-3x","exclude"),("Direxion Daily TSLA Bull 3X Shares","","3x","exclude"),("ProShares QuadPro QQQ","","4x","exclude"),
       ("ProShares UltraPro 20+ Year Treasury","","3x","exclude"),("Direxion Daily Semiconductor Bull 3X Shares","","3x","include"),("ProShares UltraPro Bitcoin","","3x","exclude"),("Direxion Daily VIX Bull 3X Shares","","3x","exclude")]
for nm,tk,lv,exp in tests:
    c=NP.classify(nm,tk,lv); check(f"분류 {nm or tk} {lv} → {exp}",c["decision"]==exp,str(c))
ov={NP.norm("proshares ultrapro gold miners"):"오너 지시"}
check("오너 오버라이드가 규칙보다 우선(골드 광산)",NP.classify("ProShares UltraPro Gold Miners","","3x",overrides=ov)["decision"]=="exclude")
with tempfile.TemporaryDirectory() as td:
    td=Path(td); json.dump({"items":[]},open(td/"pipeline.json","w")); json.dump({"items":[]},open(td/"excluded_candidates.json","w")); json.dump({"candidates":[]},open(td/"new_products.json","w")); json.dump({},open(td/"candidate_overrides.json","w"))
    U="https://example.invalid/f.htm"
    found=[("ProShares UltraPro Magnificent 7","ProShares","3x",U,"2026-02-06","","ProShares UltraPro Magnificent 7"),("DULL","BMO MicroSectors","-3x",U,"2026-10-09","DULL",""),("ABCD","BMO MicroSectors","3x",U,"2026-10-09","ABCD","Solactive Foo Index 3x")]
    r1=NP.process(found,today="2026-10-09",data=td); r2=NP.process(found,today="2026-10-16",data=td)
    check("process: 티커 없음 → 발행 예정, 인버스 → 제외 기록, 상장·통과 → 후보",r1["pipeline_added"]==["ProShares UltraPro Magnificent 7"] and len(r1["excluded_added"])==1 and r1["listed_added"]==["ABCD"],str(r1))
    check("process: 재실행 멱등(중복 추가 0)",r2["skipped"]==3 and not (r2["pipeline_added"] or r2["listed_added"] or r2["excluded_added"]),str(r2))
# ---- 5. 페이지 렌더(잠정·수동 배너, 모바일 sticky CSS) ----
S,uni,pq=mk(); df,_=L.compute(S,asof,asof,cfg,st,uni,pq)
df["d_rank"]=""; df=L.period_ranks(df,dates,lambda d:None)
import mm_site as ms
pinfo=pd.DataFrame([dict(ticker=t,index_name=f"Idx {t}",onex_path="공식 지수 레벨") for t in uni.ticker])
orig=ms.pd.read_csv; ms.pd.read_csv=lambda p,*a,**k: pinfo if str(p).endswith("product_info.csv") else orig(p,*a,**k)
h=ms.build_index(df,dict(asof="2026-10-08",generated="t",provisional=dict(raw_last="2026-10-09",reason="Close NaN"),manual=True,new_products=[],pipeline=[]))
ms.pd.read_csv=orig
check("페이지: 잠정 배지",'class="pill prov"' in h and ">잠정<" in h)
check("페이지: 수동 산출 배너 제거(예약 실행 확인 후)",'수동 산출' not in h)
import re as _re, json as _json
_d=_json.loads(_re.search(r'<script id="mmdata" type="application/json">(.*?)</script>',h,_re.S).group(1))
check("페이지: 내장 데이터(기준일·순위 행·티커 메타)",_d["asof"]=="2026-10-08" and len(_d["latest"])==int((df.table=="순위").sum()) and set(_d["tk"])>=set(df.ticker) and "p_sig" in _d["latest"][0])
_js=open(ms.DOCS/"assets"/"index.js",encoding="utf-8").read()
check("페이지: 요약 7열(순위·티커·M-score·변동성·상대강도·추세·!) + 종목 페이지 링크(JS)",all(x in _js for x in ("변동성","상대강도","추세","M-score",">!<","products/")))
check("페이지: 안내 문안 그대로 + 가이드 링크, 코드 표기(E5) 미노출",ms.NOTICE in h.replace("&#x27;","'") or ms.E(ms.NOTICE) in h and 'href="guide.html"' in h and "E5" not in h)
check("페이지: 제외 없으면 '현재 없음' · 데이터 확인 중은 별도 한 줄",("현재 없음" in h) or ("데이터 확인 중" in h))
check("페이지: 확정 배지 없음(잠정일 때만 표시)",'class="pill ok"' not in h and 'class="pill prov"' in h)
_ex=ms.exclusion_rows(pd.DataFrame([dict(ticker="ZZZ",table="제외",reason="E5",M=None),dict(ticker="YYY",table="⚠",reason="최신 확정 봉이 기준일(2026-10-08)과 다름: x",M=None)]),{"excluded":{"ZZZ":{"type":"조기상환·가속상환","date":"2026-10-01","url":"https://example.invalid/n"}}})
_exr,_held=_ex
check("제외 문장 매핑(코드 대신 사람 문장, 링크 보존) + 데이터 확인 중 분리(V3.1 §9)",_exr==[("ZZZ","발행사 조기상환 공지, 2026-10-01","https://example.invalid/n")] and _held==["YYY"],str(_ex))
import mm_guide as mg
_g=mg.guide_body(df,dict(generated="t",anomalies=None,pipeline=[],new_products=[]),uni,{"check_incomplete":{}})
check("가이드 정정(V3.1 §8): 유의확률 표현 제거·미회복 기준 서술·채권·원자재",("유의확률" not in _g) and "상위 4.4% 위치" in _g and "구조상 달성할 수 없는" in _g and "<td>채권·원자재</td>" in _g and ms.MSCORE_SHA in _g)
check("가이드: 9개 절·각주·부록 + 운영값($0.3M) 반영",all(f'id="{k}"' in _g for k in ("s1","s2","s3","s4","s5","s6","s7","s8","s9","fn","appx","appxA","appxB","appxC","longterm")) and "$0.3M" in _g)
check("가이드: 안내 문안(§2 ⑤) 재수록",ms.E(ms.NOTICE) in _g)
check("가이드: 절 순서 1→9→각주→부록",[_g.index(f'id="s{i}"') for i in range(1,10)]==sorted(_g.index(f'id="s{i}"') for i in range(1,10)) and _g.index('id="s9"')<_g.index('id="fn"')<_g.index('id="appx"'))
check("가이드: 본문에 코드명·블록 ID 미노출(각주·부록 앞)",not any(x in _g[:_g.index('id="fn"')] for x in ("MM-P","STUCK_NR","R4A","S_A","MSCORE","sha256","eligibility.yaml")) )
_nav=ms.pg("t","","index.html")
check("메뉴: 순위·장기순위·종목·Guide 순서, Guide 가 오른쪽 끝(공통 헤더) + 브랜드 아이콘",[x for x in _re.findall(r'>([^<>]+)</a>',_nav.split("<nav",1)[1].split("</nav>")[0]) if x.strip()]==["순위","장기순위","종목","Guide"] and "class=\"brand\"" in _nav and 'class="g"' in _nav.split("</nav>")[0].rsplit("<a",1)[1])
# ---- 6. 장기순위 ----
_lt=ms.compute_longterm(pd.read_csv(ms.ROOT/"data"/"scores_latest.csv"),ms.date_list()[2][-1])
_ok=_lt is not None and [t["k"] for t in _lt["tabs"]]==[5,20,60,120,250] and [t["label"] for t in _lt["tabs"]]==["1주","1달","3달","6달","1년"]
check("장기순위: 5탭(5·20·60·120·250거래일)",_ok)
if _ok:
    t5=_lt["tabs"][0]["rows"]; rk=[r["r"] for r in t5 if r["r"] is not None]
    check("장기순위: 순위 오름차순·동점 동순위·결측은 맨 아래",rk==sorted(rk) and all(t5[i]["r"] is None for i in range(len(rk),len(t5))) and rk[0]==1)
    _d5=ms.date_list()[2][-5:]; _x=[pd.read_csv(ms.DOCS/"data"/"scores"/f"{d}.csv",skiprows=1).set_index("ticker") for d in _d5]
    _t="SOXL"; _m=[x.at[_t,"M"] for x in _x if _t in x.index]
    _r=[r for r in t5 if r["t"]==_t][0]
    check("장기순위: 1주 평균 M = 최근 5거래일 일별 M 단순평균",abs(_r["m"]-sum(_m)/len(_m))<1e-4 and _r["v"]==round(sum(x.at[_t,"p_sig"] for x in _x if _t in x.index)/len(_m)*100),f"{_r} {_m}")
    t250=_lt["tabs"][4]["rows"]; _nb=[r for r in t250 if r["m"] is None]
    check("장기순위: 창의 80% 미만이면 결측(—) — 1년 탭",all(r["n"]<200 for r in _nb) and all(r["n"]>=200 for r in t250 if r["m"] is not None))
_lh=ms.build_longterm(_lt,dict(provisional=None))
check("장기순위: 기준일 표기·달력 없음·탭 컨테이너·내장 데이터",_lt["asof"] in _lh and "calbox" not in _lh and 'id="ltabs"' in _lh and 'id="ltdata"' in _lh)
# ---- 7. V3.1 종목 페이지·목록·JS ----
_it=ms.load_page_items(); _ho=ms.load_holdings()
_u=pd.read_csv(ms.DATA/"universe.csv")
_ph=ms.build_product("SOXL",_u[_u.ticker=="SOXL"].iloc[0],_it["SOXL"],_ho["SOXL"])
check("종목 페이지: 소개가 차트 바로 위, 구 '특징' 블록 없음",_ph.index("소개")<_ph.index('id="chart"') and "<h2>특징</h2>" not in _ph and 'class="intro"' in _ph)
_ib=ms.build_product("BULZ",_u[_u.ticker=="BULZ"].iloc[0],_it["BULZ"],_ho["BULZ"])
check("구성 표(V3.2): 전체 구성 전수 — BULZ 15종·SOXL 30종 모두 '전체 보기'에 전부 표시, 기본 격자는 10종 유지",_ib.count('class="hc"')==15 and "전체 보기 (15종)" in _ib and _ph.count('class="hc"')==_ho["SOXL"]["total"] and f"전체 보기 ({_ho['SOXL']['total']}종)" in _ph and _ib.split('<details',1)[0].count('class="hc"')==10)
check("소개 4~6문장·금지어 0 (37종 전부)",all(4<=len([x for x in _re.split(r"\.(?:\s+|$)",v["text"]["intro"].strip()) if x.strip()])<=6 for v in _it.values()) and len(_it)==37)
_dir=ms.build_products_dir(pd.DataFrame(),_u,_it)
check("종목 목록: 열 = 티커·섹터·구분·발행사(M-score·순위 없음), 기본 티커순",all(x in _dir for x in ("티커","섹터·테마","구분","발행사")) and "M-score" not in _dir.split("<tbody>")[0].split("</h1>")[1] and [x for x in _re.findall(r'products/([A-Z]+)\.html"><b>',_dir)]==sorted(_u.ticker))
_ij=open(ms.DOCS/"assets"/"index.js",encoding="utf-8").read(); _lj=open(ms.DOCS/"assets"/"longterm.js",encoding="utf-8").read()
check("JS: 정렬(▲▼)·열 폭 8/28/12/10/11/10/21(ICON-1Y)·기본 정렬 순위 오름차순·달력 연월 선택",all(x in _ij for x in ("data-s","▼","width:' + c.w","cyear","cmonth","sort: { k: 'rank', dir: 1 }")) and all(x in _lj for x in ("data-s","▼","w: 21","sort = { k: 'r', dir: 1 }")))
print(f"\n{ok} PASS / {len(bad)} FAIL"); sys.exit(1 if bad else 0)
