#!/usr/bin/env python3
"""판정 규칙 픽스처 테스트 — 실제 EDGAR 공시 원문 → mm_rules.scan_text → mm_rules.decide → expected.json 대조.
사용: python3 tests/run_fixtures.py [--rules PATH]   (--rules: 비교용으로 다른 mm_rules.py 를 로드, 예: tests/mm_rules_orig.py)
스캐너(mm_weekly_scan)와 같은 조건: 앞 700000바이트만 읽고, totext 동일, BMO 문서는 앞 60000자에 'MicroSectors' 없으면 건너뜀."""
import sys, re, json, csv, html, importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; T=ROOT/"tests"; FX=T/"fixtures"
MAXB=700_000

def load_rules(path=None):
    p=Path(path) if path else ROOT/"scripts"/"mm_rules.py"
    spec=importlib.util.spec_from_file_location("mm_rules_under_test",p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def totext(h): return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",re.sub(r"<(script|style).*?</\1>"," ",h,flags=re.S))))

def aliases(with_fngb=False):
    """mm_weekly_scan.aliases() 와 같은 규칙(이름 = yf_longName + 접두 제거본, 12자 이상 / 티커 4자 이상이면 단어경계 정규식).
    현 유니버스 + 과거 시점 티커(현 유니버스에 없는 ERX·GUSH·NUGT·SOXS) 추가. with_fngb=True 는 알려진 한계 스트레스 전용."""
    info={r["ticker"]:r.get("yf_longName","") for r in csv.DictReader(open(ROOT/"data"/"product_info.csv",encoding="utf-8"))}
    tickers=[r["ticker"] for r in csv.DictReader(open(ROOT/"data"/"universe.csv",encoding="utf-8"))]
    hist={ # 과거 시점 이름(당시 공시 표기). FNGB 는 이름 없이 티커만(스캐너 방식: 4자 이상 티커 정규식)
        "ERX":"Direxion Daily Energy Bull 3X Shares","GUSH":"Direxion Daily S&P Oil & Gas Exp. & Prod. Bull 3X Shares",
        "NUGT":"Direxion Daily Gold Miners Index Bull 3X Shares","SOXS":"Direxion Daily Semiconductor Bear 3X Shares"}
    if with_fngb: hist["FNGB"]=""   # 스트레스용: FNGB 는 유니버스에 없어 운영 별칭맵에는 없다
    al={}
    for tk in tickers+[h for h in hist if h not in tickers]:
        ln=info.get(tk) if tk in info else hist.get(tk,"")
        names=set()
        if isinstance(ln,str) and ln:
            n=ln.replace("™","").strip(); names.add(n)
            for pre in ("Direxion Daily ","ProShares ","MicroSectors "):
                if n.startswith(pre): names.add(n[len(pre):])
        names={x for x in names if len(x)>=12}
        al[tk]=(names, re.compile(r"\b%s\b"%re.escape(tk)) if len(tk)>=4 else None)
    return al

def run_one(R,al,it):
    raw=(FX/it["file"]).read_bytes()[:MAXB].decode("utf-8","ignore")
    if it["issuer"]=="BMO" and "MicroSectors" not in raw[:60000]:
        return [],[],"스캐너 게이트(MicroSectors 없음)로 건너뜀"
    txt=totext(raw)
    issues=R.scan_text(txt,al,it["url"],it["filed"],it["form"],it["title"])
    return issues,R.decide(issues),""

def summarize(acts):
    """티커 -> 'exclude' | 'exclude_revalidate' | 'note' | 'a+b'(복수) ; 없으면 키 없음"""
    d={}
    for a in acts:
        d.setdefault(a["ticker"],[])
        if a["kind"] not in d[a["ticker"]]: d[a["ticker"]].append(a["kind"])
    return {t:"+".join(sorted(k)) for t,k in d.items()}

def main():
    rp=sys.argv[sys.argv.index("--rules")+1] if "--rules" in sys.argv else None
    R=load_rules(rp); al=aliases()
    if not hasattr(R,"decide"): R.decide=load_rules().decide   # 변경 전 비교용 파일에는 decide 가 없다 — ACT_MAP 은 동일
    man=json.load(open(FX/"MANIFEST.json",encoding="utf-8"))["fixtures"]; exp=json.load(open(T/"expected.json",encoding="utf-8"))
    print(f"규칙 파일: {rp or 'scripts/mm_rules.py'} | 별칭 티커 {len(al)}종")
    rows=[]; bad=[]
    for it in man:
        issues,acts,note=run_one(R,al,it)
        got=summarize(acts); want={k:v for k,v in exp[it["id"]]["tickers"].items() if v!="none"}
        ok=(got==want); rows.append((it,want,got,ok,note))
        if not ok: bad.append((it,want,got,issues,acts))
    main_rows=[r for r in rows if not r[0].get("extra")]; ext_rows=[r for r in rows if r[0].get("extra")]
    fmt=lambda d: ", ".join(f"{t}={k}" for t,k in sorted(d.items())) or "조치 없음"
    for title,rs in (("[본 7건]",main_rows),("[보조 음성/보강 대조]",ext_rows)):
        print(title)
        for it,want,got,ok,note in rs:
            print(f"  {'PASS' if ok else 'FAIL'} {it['id']:<3} {it['form']:<5} {it['filed']} | 기대: {fmt(want)} | 실제: {fmt(got)}"+(f" | {note}" if note else ""))
    # 알려진 한계(미수정): ±600자 창 귀속은 같은 창에 나온 신규 상품(FNGB)까지 잡는다. 운영 별칭맵에는 FNGB 가 없어 영향 없음 — 집계·종료코드에서 제외.
    it_b=next(i for i in man if i["id"]=="b"); _,acts_b,_=run_one(R,aliases(with_fngb=True),it_b); got_b=summarize(acts_b)
    print(f"  {'XPASS' if got_b=={'FNGU':'exclude'} else 'XFAIL'} b+FNGB 별칭 | 기대: FNGU=exclude | 실제: {fmt(got_b)} | [알려진 한계·집계 제외] 같은 창에 나온 신규 FNGB 귀속")
    n_ok=sum(1 for r in main_rows if r[3]); print(f"결과: 본 {n_ok}/{len(main_rows)}  보조 {sum(1 for r in ext_rows if r[3])}/{len(ext_rows)}")
    for it,want,got,issues,acts in bad:
        print(f"\n--- 불일치 상세 {it['id']} ({it['file']}) ---")
        for t in sorted(set(want)|set(got)):
            if want.get(t)!=got.get(t): print(f"  {t}: 기대 {want.get(t,'없음')} / 실제 {got.get(t,'없음')}")
        for o in issues[:12]: print(f"  이슈 {o['ticker']} {o['type']} strong={o['strong']} | …{o['snippet'][:220]}…")
        if not issues: print("  (scan_text 이슈 0건)")
    return 0 if all(r[3] for r in rows) else 1

if __name__=="__main__": sys.exit(main())
