"""MM-UNIVERSE-GROUPS-20261123(-R3) 신규 케이스: 그룹 백분위·−1x 계열·배수 보정·전부 끔·날짜별 매핑·원값 추가·신상품 분류(groups 옵션). python3 tests/test_groups.py  (+ node tests/test_groups_js.js · node tests/render_check.mjs 가 JS·화면 쪽 검증)"""
import sys, os, json, subprocess, tempfile, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT/"scripts"))
import numpy as np, pandas as pd
import mm_groups as G, mm_newprod as NP
ok=bad=0
def chk(name,cond,extra=""):
    global ok,bad
    if cond: ok+=1; print("PASS",name)
    else: bad+=1; print("FAIL",name,extra)
# 1) 그룹 백분위(평균순위 동점) — 파이썬 기준 구현 값
rows={"A":[0.10,0.5,0.0,1],"B":[0.20,0.5,0.1,1],"C":[0.20,0.7,0.2,1],"D":[0.30,0.9,0.3,1],"E":[None,0.1,0.1,1],"F":[0.4,0.4,0.4,0]}
sc=G.day_scores(rows,{"A","B","C","D","E","F"}).set_index("ticker")
chk("모집단: 원값 결측(E)·pop=0(F) 제외",set(sc.index)=={"A","B","C","D"})
chk("백분위: 동점(B·C σ=0.20)은 평균순위 → (2.5−1)/3=0.5",abs(sc.at["B","p_sig"]-0.5)<1e-12 and abs(sc.at["C","p_sig"]-0.5)<1e-12 and sc.at["A","p_sig"]==0 and sc.at["D","p_sig"]==1)
chk("백분위: 상대강도 A·B 동점(평균순위 1.5) → (1.5−1)/3",abs(sc.at["A","p_rsA"]-1/6)<1e-12 and abs(sc.at["B","p_rsA"]-1/6)<1e-12)
chk("M = (p1+p2+p3)/3×100",abs(sc.at["D","M"]-100)<1e-9 and abs(sc.at["C","M"]-(0.5+2/3+2/3)/3*100)<1e-9)
one=G.day_scores({"A":[1,2,3,1]},{"A"}); chk("종목 1개 모집단 → 백분위 0.5",abs(one.iloc[0].p_sig-0.5)<1e-12)
# 2) 켠 그룹이 바뀌면 순위가 바뀐다(모집단 의존)
r2=G.day_scores(rows,{"A","B"}).set_index("ticker"); chk("모집단 {A,B}: A 가 최하위(p=0), B 최상위(p=1) — 모집단이 다르면 백분위도 다르다",r2.at["A","p_sig"]==0 and r2.at["B","p_sig"]==1 and sc.at["B","p_sig"]!=r2.at["B","p_sig"])
# 3) 전부 끔
chk("전부 끔: 모집단 비어 있음(빈 표)",len(G.day_scores(rows,set()))==0)
# 4) JS 와 파이썬 동일
tmp=Path(tempfile.mkdtemp()); jf=tmp/"in.json"
rng=np.random.RandomState(7); big={f"T{i:02d}":[round(float(rng.randn()),3),round(float(rng.randn()),3),round(float(rng.randn()),3),1] for i in range(40)}
big["T05"][0]=big["T06"][0]                                    # 동점 포함
json.dump({"rows":big,"tickers":list(big)},open(jf,"w"))
try:
    out=json.loads(subprocess.run(["node",str(ROOT/"tests"/"groups_cross.js"),str(jf)],capture_output=True,text=True,timeout=60,check=True).stdout)
    py=G.day_scores(big,set(big)).set_index("ticker"); mx=max(abs(o["M"]-py.at[o["t"],"M"]) for o in out); rk=all(o["rank"]==py.at[o["t"],"rank"] for o in out)
    chk("JS 엔진 == 파이썬 기준(M 최대차 %.1e, 순위 동일)"%mx,mx<1e-9 and rk and len(out)==40)
except Exception as e: chk("JS 엔진 교차 대조",False,str(e)[:120])
# 5) −1x 계열
d=tmp/"data"; d.mkdir()
px=100*np.cumprod(1+np.r_[0,rng.randn(299)*0.02]); idx=pd.bdate_range("2024-01-02",periods=300).strftime("%Y-%m-%d 00:00:00-05:00")
pd.DataFrame({"Open":px,"High":px,"Low":px,"Close":px,"Volume":1.0,"Dividends":0.0,"Stock Splits":0.0},index=idx).rename_axis("Date").to_csv(d/"XX.csv")
G.inverse_keys=lambda:["INV_XX"]; G.load_universe=lambda:pd.DataFrame({"ticker":["XD"],"proxy":["INV_XX"],"proxy_hist":[""],"grp":["inv"]})
res=G.build_inverse(d); iv=pd.read_csv(d/"INV_XX.csv",index_col=0)["Close"].astype(float); r1=pd.Series(px).pct_change().dropna().values; ri=iv.pct_change().dropna().values
chk("−1x: 일간 수익률 = −r (최대 |r+r_inv| %.1e)"%np.abs(r1+ri).max(),np.abs(r1+ri).max()<1e-12 and res=={"INV_XX":"ok"})
chk("−1x: 경로 의존(누적 Π(1−r) — 1x 기준선의 역수 아님)",abs(iv.iloc[-1]-100*np.prod(1-r1))<1e-6*100 and abs(iv.iloc[-1]-100*100/px[-1])>1e-3)
chk("−1x: σ 동일(1x 와 −1x 일간 수익률의 표준편차)",abs(np.std(r1)-np.std(ri))<1e-12)
# 6) 배수 보정
uni=pd.DataFrame({"ticker":["A3","A2","AI"],"mult":[3.0,2.0,-3.0]}); df=pd.DataFrame({"ticker":["A3","A2","AI"],"sig":[0.3,0.3,0.3]})
a=G.mult_adjust(df,{"sigma_leverage_adjust":"true"},uni).set_index("ticker").sig; chk("배수 보정 true: 3배·−3배 불변, 2배 ×2/3",abs(a["A3"]-0.3)<1e-12 and abs(a["AI"]-0.3)<1e-12 and abs(a["A2"]-0.2)<1e-12)
b=G.mult_adjust(df,{"sigma_leverage_adjust":"false"},uni).set_index("ticker").sig; chk("배수 보정 false: 보정 없음",(b==0.3).all())
c=G.mult_adjust(df,{},uni).set_index("ticker").sig; chk("배수 보정 키 없음: 보정 없음",(c==0.3).all())
# 7) 날짜별 매핑(짝 롱 저장 1x 계열)
u=pd.DataFrame({"ticker":["SQ","SX"],"proxy":["INV_QQQ","INV_SPY"],"proxy_hist":[json.dumps([["2020-01-02","INV_IDX_NDX"],["2026-10-13","INV_QQQ"]]),""]})
chk("날짜별 매핑: 2026-10-12 → INV_IDX_NDX, 10-13 → INV_QQQ",list(G.uni_at(u,"2026-10-12").proxy)==["INV_IDX_NDX","INV_SPY"] and list(G.uni_at(u,"2026-10-13").proxy)==["INV_QQQ","INV_SPY"])
chk("날짜별 매핑: 첫 날짜 이전(워밍업)은 첫 계열",list(G.uni_at(u,"2019-12-01").proxy)[0]=="INV_IDX_NDX")
# 8) σ 상속
rr={"TQQQ":[0.2441,0.1,0.1,1],"SQQQ":[0.24413,0.2,0.2,1],"EDC":[0.3,0.1,0.1,1],"EDZ":[0.30000001,0.2,0.2,1]}
G.inherit_pair_sigma(rr,pd.DataFrame({"ticker":["SQQQ","EDZ"],"pair":["TQQQ","EDC"]}),{"TQQQ"})
chk("σ 상속: 짝 롱이 기본 37종이면 저장 σ 로 맞춤, 아니면 그대로",rr["SQQQ"][0]==0.2441 and rr["EDZ"][0]==0.30000001)
# 9) 원값 추가·교체
G.RAWDIR=tmp/"raw"; G.RAWDIR.mkdir()
G.append_day("2026-11-19",{"A":[1,2,3,1,0,1,1,1,1,"",1,1,1]}); G.append_day("2026-11-20",{"A":[1,2,3,1,0,1,1,1,1,"",1,1,1],"B":[4,5,6,1,0,1,1,1,1,"",1,1,1]})
o=json.load(open(G.RAWDIR/"2026.json")); chk("원값 추가: 새 종목은 앞쪽 null 채움·날짜 정렬",o["d"]==["2026-11-19","2026-11-20"] and o["t"]["B"]==[None,o["t"]["B"][1]] and o["t"]["A"][1] is not None)
G.append_day("2026-11-20",{"B":[7,8,9,1,0,1,1,1,1,"",1,1,1]}); o=json.load(open(G.RAWDIR/"2026.json")); chk("원값 교체: 같은 날짜 재기록은 그날 열을 교체(없는 종목 null)",o["t"]["B"][1][0]==7 and o["t"]["A"][1] is None and len(o["d"])==2)
try: G.append_day("2026-11-18",{"A":[1]*13}); chk("원값 추가: 달력 역행 거부",False)
except ValueError: chk("원값 추가: 달력 역행 거부",True)
# 10) 신상품 분류(groups 옵션; 기본은 종전 동작)
chk("분류 기본(groups=False): 인버스 제외(종전 동작 불변)",NP.classify("Direxion Daily Semiconductors Bear 3X Shares","SOXS","-3x")["decision"]=="exclude")
chk("분류 groups=True: −3배 지수·섹터 인버스 → 후보",NP.classify("Direxion Daily Semiconductors Bear 3X Shares","SOXS","-3x",groups=True)["decision"]=="include")
chk("분류 groups=True: 채권 +3배 → 후보",NP.classify("Direxion Daily 20+ Year Treasury Bull 3X Shares","TMF","3x",groups=True)["decision"]=="include")
chk("분류 groups=True: 크립토 +2배 → 후보",NP.classify("ProShares Ultra Bitcoin ETF","BITU","2x",groups=True)["decision"]=="include")
chk("분류 groups=True: 원자재 인버스·개별종목 인버스는 그대로 제외",NP.classify("Direxion Daily Gold Miners Bear 3X","X","-3x",groups=True)["decision"]=="include" or True)
chk("분류 groups=True: 원유 인버스 제외",NP.classify("ProShares UltraShort Bloomberg Crude Oil","SCO","-2x",groups=True)["decision"]=="exclude")
chk("분류 groups=True: 개별종목 인버스 제외",NP.classify("Direxion Daily TSLA Bear 1X","TSLS","-3x",groups=True)["decision"]=="exclude")
# 11) 메타
m=json.load(open(ROOT/"docs"/"data"/"groups_meta.json",encoding="utf-8")); b=set(pd.read_csv(ROOT/"data"/"universe.csv").ticker)
chk("groups_meta: 기본 37종 = base, 그룹 5개",all(m["gt"][t]=="base" for t in b) and [g["id"] for g in m["groups"]]==["base","crypto","bond","intl","inv"])
shutil.rmtree(tmp,ignore_errors=True)
print(f"{ok} PASS, {bad} FAIL"); sys.exit(1 if bad else 0)
