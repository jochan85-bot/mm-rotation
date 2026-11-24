"""MM-PRODUCT-POOL-CHARTS-20261124 신규 케이스. 사용: python3 tests/test_pool.py [pool_result.json 경로(헤드리스 결과, 없으면 해당 항 건너뜀)]
 5-1 미국 기본 SOXL·TQQQ·GDXU 기본 상태 값 = 저장 계열·점수 CSV · 기존 파일(차트 37·series·scores) 불변(LIVE_DOCS 와 대조)
 5-2 신규 49종 차트 파일 전수 존재·상장일 시작 · 86종 차트 대상
 5-4 SQQQ 인버스만 순위 = 메인 표(G.table) 순위 같은 날짜 3일 (+BITU·SOXL) / JS 엔진 ↔ 파이썬 기준 구현
 5-5 자기 그룹 고정·기본값 2종류·풀 변경 시 차트 재계산(헤드리스 결과)"""
import sys, os, json, subprocess, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT/"scripts"))
import numpy as np, pandas as pd
import mm_groups as G, mm_charts as C
LIVE=Path(os.environ.get("LIVE_DOCS", str(Path.home()/"mm_rotation"/"docs")))
ok=bad=0
def chk(name,cond,extra=""):
    global ok,bad
    if cond: ok+=1; print("PASS",name)
    else: bad+=1; print("FAIL",name,extra)
D=ROOT/"docs"; DA=ROOT/"data"
base=list(pd.read_csv(DA/"universe.csv").ticker); new=list(pd.read_csv(DA/"universe_groups.csv").ticker)
# 5-2 차트 대상·파일
chk("차트 대상 = 86종(기본 37 + 신규 49)",len(C.universe())==86 and set(C.universe())==set(base)|set(new))
miss=[t for t in base+new if not (D/"data"/"charts"/f"{t}.json").exists()]; chk("차트 파일 86종 전수 존재",not miss,miss)
badstart=[]
for t in new:
    j=json.load(open(D/"data"/"charts"/f"{t}.json")); src=pd.read_csv(ROOT/".local"/"p0view"/"data"/f"{t}.csv",usecols=[0]).iloc[0,0][:10]
    if j["d0"]!=src or len(j["c"])<5: badstart.append((t,j["d0"],src))
chk("신규 49종 차트 시작일 = 원천 첫 봉(상장일, 상장 전 구간 없음)·봉 5개 이상",not badstart,badstart)
# 5-1 기존 파일 불변
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
if LIVE.exists():
    d=[t for t in base if sha(D/"data"/"charts"/f"{t}.json")!=sha(LIVE/"data"/"charts"/f"{t}.json")]; chk("미국 기본 37종 차트 파일 불변(라이브 사본 대조)",not d,d)
    ds=[t for t in base+new if sha(D/"data"/"series"/f"{t}.json")!=sha(LIVE/"data"/"series"/f"{t}.json")]; chk("86종 series 파일 불변",not ds,ds)
    sc_live=sorted(p.name for p in (LIVE/"data"/"scores").glob("*.csv")); dd=[n for n in sc_live if sha(D/"data"/"scores"/n)!=sha(LIVE/"data"/"scores"/n)]
    chk("기존 docs/data/scores 불변",not dd and sc_live==sorted(p.name for p in (D/"data"/"scores").glob("*.csv")),dd[:3])
    chk("scores_latest.csv 불변",sha(DA/"scores_latest.csv")==sha(LIVE.parent/"data"/"scores_latest.csv"))
else: print("SKIP 라이브 대조(경로 없음)")
# 5-1 기본 상태 값 = 저장 계열
by,cal=G.all_raw(); bset=set(base); last=cal[-1]
sc=G.day_scores(by[last],bset).set_index("ticker"); latest=pd.read_csv(DA/"scores_latest.csv").set_index("ticker")
for t in ("SOXL","TQQQ","GDXU"):
    s=json.load(open(D/"data"/"series"/f"{t}.json")); r=sc.loc[t]
    chk(f"{t} 기본(미국 기본만) M·순위 = 저장 계열 마지막 값",s["d"][-1]==last and abs(round(r.M,1)-s["m"][-1])<1e-9 and int(r["rank"])==s["r"][-1] and len(sc)==s["n"][-1],(s["d"][-1],last,r.M,s["m"][-1]))
    chk(f"{t} 기본 백분위 3항 = scores_latest(100배 반올림)",all(round(r[k]*100)==round(latest.at[t,k]*100) for k in ("p_sig","p_rsA","p_f1b")) and int(r["rank"])==int(latest.at[t,"rank"]),(dict(r),dict(latest.loc[t])))
# 기본 상태 전 구간: 파이썬 기준 구현 ↔ 저장 계열(샘플 날짜 30일 × 3종)
ser=G.series_scores(by,cal,bset,idx_from=0); samp=cal[::max(1,len(cal)//30)]; mis=0
for t in ("SOXL","TQQQ","GDXU"):
    s=json.load(open(D/"data"/"series"/f"{t}.json")); pos={d:i for i,d in enumerate(s["d"])}
    for d in samp:
        if d not in pos: continue
        x=ser[d]; x=x[x.ticker==t]
        if not len(x) or abs(round(float(x.iloc[0].M),1)-s["m"][pos[d]])>1e-9 or int(x.iloc[0]["rank"])!=s["r"][pos[d]]: mis+=1
chk("기본 상태 SOXL·TQQQ·GDXU 샘플 30일 M·순위 저장 계열 일치",mis==0,mis)
# 신규 종목 기본 상태(5개 전부) = 저장 계열: 파이썬 기준 구현
allset=set(base)|set(new); mis=0
for t in ("SQQQ","BITU","TMF","JPNU"):
    s=json.load(open(D/"data"/"series"/f"{t}.json")); pos={d:i for i,d in enumerate(s["d"])}
    for d in samp+[last]:
        if d not in pos: continue
        x=G.day_scores(by[d],allset); x=x[x.ticker==t]
        if not len(x) or abs(round(float(x.iloc[0].M),1)-s["m"][pos[d]])>1e-9 or int(x.iloc[0]["rank"])!=s["r"][pos[d]]: mis+=1
chk("신규 종목 기본 상태(5개 전부) 저장 계열 = 원값 재계산 일치(SQQQ·BITU·TMF·JPNU)",mis==0,mis)
# 5-4 JS 엔진: 인버스만 SQQQ 순위(차트 시리즈) = 메인 표 순위 / 파이썬 기준 구현
o=json.loads(subprocess.run(["node",str(ROOT/"tests"/"pool_cross.js")],capture_output=True,text=True,timeout=120,check=True).stdout)
POOL={"inv":{"inv"},"crypto":{"crypto"},"all":None,"base_inv":{"base","inv"}}
gt=json.load(open(D/"data"/"groups_meta.json"))["gt"]
n_ok=0;n_all=0
for c in o["cases"]:
    chk(f"{c['tk']}·{c['pool']}·{c['d']} 차트 시리즈 순위/N = 메인 표 순위/N",c["table_rank"]==c["series_rank"] and (c["table_rank"] is None or c["table_n"]==c["series_n"]),c)
    ts={t for t,g in gt.items() if POOL[c["pool"]] is None or g in POOL[c["pool"]]}
    x=G.day_scores(by[c["d"]],ts); x=x[x.ticker==c["tk"]]
    pr=int(x.iloc[0]["rank"]) if len(x) else None; pn=len(G.day_scores(by[c["d"]],ts))
    chk(f"{c['tk']}·{c['pool']}·{c['d']} JS 엔진 = 파이썬 기준 구현(순위·N)",pr==c["table_rank"] and (pr is None or pn==c["table_n"]),(pr,pn,c))
# 5-3/5-5 헤드리스 결과
rp=sys.argv[1] if len(sys.argv)>1 else None
if rp and Path(rp).exists():
    R=json.load(open(rp)); by_l={}
    for r in R: by_l.setdefault(r["label"],{})[r["view"]]=r
    chk("헤드리스: 24건(12시나리오×모바일·데스크톱) 오류·깨짐 0",len(R)==24 and not [r["label"] for r in R if r["bad"]],[(r["label"],r["view"],r["errs"],r["pfail"]) for r in R if r["bad"]][:3])
    chk("전 시나리오 가격 차트 표시(불러오지 못했습니다 0)·버튼 5개",all((not r["pfail"]) and r["pcanvas"]>=1 and len(r["btns"])==5 for r in R))
    for r in R:
        own=[b for b in r["btns"] if b["lock"]]
        chk(f"{r['label']}·{r['view']} 자기 그룹 1개 고정·켜짐",len(own)==1 and own[0]["on"] and own[0]["pressed"]=="true")
        if "lockClick" in r: chk(f"{r['label']}·{r['view']} 잠금 버튼 눌러도 변화 없음",r["lockClick"]["before"]==r["lockClick"]["after"])
        if "toggle" in r: chk(f"{r['label']}·{r['view']} 다른 그룹 토글 시 상태 반전·숫자 갱신",r["toggle"]["now"]!=r["toggle"]["was"] and r["toggle"]["csvg"] and r["toggle"]["pstat"]!=r["pstat"])
    g=lambda l: by_l[l]["desktop"]
    on=lambda r:[b["g"] for b in r["btns"] if b["on"]]
    chk("기본값: 미국 기본 SOXL = base 만",on(g("SOXL_기본"))==["base"]); chk("기본값: 신규 SQQQ·BITU·TMF·JPNU = 5개 전부",all(len(on(g(l)))==5 for l in ("SQQQ_전부","BITU_전부","TMF_기본상태","JPNU_기본상태")))
    chk("저장값에 자기 그룹이 없어도 고정으로 켜짐(SOXL, 저장 inv)",sorted(on(g("SOXL_저장값_다른종목에서")))==["base","inv"])
    chk("SQQQ 인버스만 = inv 만",on(g("SQQQ_인버스만"))==["inv"]); chk("BITU 크립토만 = crypto 만",on(g("BITU_크립토만"))==["crypto"])
    def num(s,k):
        import re; m=re.search(k,s); return m
    for l in ("SOXL_기본","SQQQ_전부","GDXU_기본","TQQQ_기본"):
        p=g(l)["pstat"]; chk(f"{l} 상단: M-score·순위(N종 중 k위)·변동성·상대강도·추세 표시",all(w in p for w in ("M-score","종 중","위","변동성","상대강도","추세")),p)
    chk("풀 변경 시 상단 숫자·차트 판독 줄 갱신(SOXL 기본 vs +인버스 vs 전부)",len({g(l)["pstat"] for l in ("SOXL_기본","SOXL_기본+인버스","SOXL_전부")})==3 and len({g(l)["readout"] for l in ("SOXL_기본","SOXL_기본+인버스","SOXL_전부")})==3)
    # 5-1 브라우저 값 = 기본 상태 파이썬 기준
    import re
    for t,l in (("SOXL","SOXL_기본"),("TQQQ","TQQQ_기본"),("GDXU","GDXU_기본")):
        p=g(l)["pstat"]; r=sc.loc[t]; chk(f"{t} 브라우저 상단 M-score·순위 = 저장 기준",f"{r.M:.1f}" in p and f"{len(sc)}종 중 {int(r['rank'])}위" in p,(p,r.M,r["rank"]))
        chk(f"{t} 브라우저 차트 판독(마지막 점) M·순위 = 저장 계열",f"M-score {r.M:.1f}" in g(l)["readout"].replace("  "," ") or (f"{r.M:.1f}" in g(l)["readout"] and f"{int(r['rank'])}위" in g(l)["readout"]),g(l)["readout"])
print(f"\n{ok} PASS / {bad} FAIL"); sys.exit(1 if bad else 0)
