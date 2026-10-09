#!/usr/bin/env python3
"""오탐(false positive) 표본 점검 — 최근 공시 중 '문제 없는 일반 공시'에 규칙이 조치를 내지 않는지 확인.
  python3 tests/fp_sample.py --build   표본 목록 tests/fp_sample.json 생성(EDGAR submissions 조회, 시드 고정) + 원문 캐시 tests/fp_cache/
  python3 tests/fp_sample.py           캐시된 표본에 현행 규칙(scripts/mm_rules.py)과 변경 전 규칙(tests/mm_rules_orig.py)을 모두 적용해 비교
표본 A = 최근 8일(스캐너 LOOKBACK) 전수 중 비-BMO 전부 + BMO 무작위 / 표본 B = 최근 1년 유니버스 관련(MicroSectors·Direxion·ProShares) 무작위.
EDGAR 요청: User-Agent 명시, 초당 5회 이하."""
import sys, json, time, random, datetime as dt, urllib.request, hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_fixtures as RF
ROOT=RF.ROOT; T=RF.T; CACHE=T/"fp_cache"; LIST=T/"fp_sample.json"
UA="mm-rotation research (jjoychan85@gmail.com)"; SEED=20261009
CIKS={"Direxion":["0001424958","0001450922"],"ProShares":["0001415311","0001174610"],"BMO":["0000927971"]}
FORMS={"497","497K","497J","497AD","485APOS","485BPOS","485BXT","8-A12B","FWP","424B2","424B3","424B5","8-K"}
def get(url,maxb=RF.MAXB):
    time.sleep(0.25); req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*"})
    with urllib.request.urlopen(req,timeout=60) as r: return r.read(maxb)
def filings(cik):
    sub=json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json",maxb=20_000_000)); rows=[]
    def add(rec):
        for i in range(len(rec["form"])):
            rows.append(dict(form=rec["form"][i],date=rec["filingDate"][i],acc=rec["accessionNumber"][i],doc=rec["primaryDocument"][i],desc=(rec.get("primaryDocDescription") or [""]*len(rec["form"]))[i]))
    add(sub["filings"]["recent"])
    for f in sub["filings"].get("files",[]): add(json.loads(get("https://data.sec.gov/submissions/"+f["name"],maxb=20_000_000)))
    return sub.get("name",""),rows
def cache_path(url): return CACHE/(hashlib.md5(url.encode()).hexdigest()[:12]+"_"+url.rsplit("/",1)[-1])
def fetch(url):
    p=cache_path(url)
    if not p.exists(): CACHE.mkdir(exist_ok=True); p.write_bytes(get(url))
    return p.read_bytes().decode("utf-8","ignore")

def build():
    rnd=random.Random(SEED); fx={i["accession"] for i in json.load(open(RF.FX/"MANIFEST.json",encoding="utf-8"))["fixtures"]}
    today=dt.date(2026,10,9); since8=str(today-dt.timedelta(days=8)); since365=str(today-dt.timedelta(days=365))
    A=[]; Bpool={"BMO":[],"Direxion":[],"ProShares":[]}; names={}
    for iss,ciks in CIKS.items():
        for cik in ciks:
            nm,rows=filings(cik); names[cik]=nm
            for x in rows:
                if x["form"] not in FORMS or not x["doc"].lower().endswith((".htm",".html",".txt")) or x["acc"] in fx: continue
                rec=dict(issuer=iss,cik=cik,name=nm,form=x["form"],date=x["date"],acc=x["acc"],desc=x["desc"],
                         url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{x['acc'].replace('-','')}/{x['doc']}")
                if x["date"]>=since8: A.append(rec)
                elif x["date"]>=since365: Bpool[iss].append(rec)
    nonbmo=[r for r in A if r["issuer"]!="BMO"]; bmo=[r for r in A if r["issuer"]=="BMO"]
    A=nonbmo+rnd.sample(bmo,max(0,20-len(nonbmo)))
    for r in A: r["set"]="A"
    micro=("GDX","FNG","BNK","NRG","OIL","MICRO","BULZ","SMH","AIQ","FLY","MNG","XLC","XLP","WTI","ETN","LAUNCH","FEE","SPLIT")
    bm=[r for r in Bpool["BMO"] if any(k in r["desc"].upper() for k in micro)]
    B=rnd.sample(bm,min(14,len(bm)))
    dx=[r for r in Bpool["Direxion"] if r["form"] in ("497","497K")]; B+=rnd.sample(dx,min(22,len(dx)))
    ps=[r for r in Bpool["ProShares"] if r["form"] in ("497","497K","485BPOS")]; B+=rnd.sample(ps,min(12,len(ps)))
    for r in B: r["set"]="B"
    json.dump(A+B,open(LIST,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
    for r in A+B: fetch(r["url"])
    print(f"표본 A {len(A)}건 + B {len(B)}건 저장 → {LIST.name}, 캐시 {CACHE.name}/")

def run():
    items=json.load(open(LIST,encoding="utf-8")); al=RF.aliases()
    new=RF.load_rules(); old=RF.load_rules(T/"mm_rules_orig.py"); old.decide=new.decide
    tot={"A":[0,0,0],"B":[0,0,0]}; rows=[]
    for it in items:
        raw=cache_path(it["url"]).read_bytes()[:RF.MAXB].decode("utf-8","ignore")
        gate=(it["issuer"]=="BMO" and "MicroSectors" not in raw[:60000])
        txt=RF.totext(raw); title=f"{it['name']} {it['form']} {it['desc']}".strip()
        r=[]
        for R in (new,old):
            iss=R.scan_text(txt,al,it["url"],it["date"],it["form"],title); r.append(RF.summarize(R.decide(iss)))
        rows.append((it,gate,r[0],r[1])); t=tot[it["set"]]; t[0]+=1; t[1]+=bool(r[0]); t[2]+=bool(r[1])
    fmt=lambda d: ", ".join(f"{t}={k}" for t,k in sorted(d.items())) or "-"
    for it,gate,n,o in rows:
        if n or o: print(f"{'HIT ' if n else 'old '} [{it['set']}] {it['issuer']} {it['form']} {it['date']} {it['desc'][:42]!r} | 현행: {fmt(n)} | 변경전: {fmt(o)} | {it['url']}")
    for k,(n,a,b) in tot.items(): print(f"표본 {k}: {n}건 중 현행 규칙 조치 발생 {a}건 / 변경 전 규칙 {b}건")
    print("스캐너 게이트(BMO 비-MicroSectors)로 실제 운영에서는 건너뛰는 표본:",sum(1 for r in rows if r[1]),"건")
    return 0 if all(t[1]==0 for t in tot.values()) else 1
if __name__=="__main__":
    if "--build" in sys.argv: build()
    else: sys.exit(run())
