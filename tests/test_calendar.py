"""달력 소급 파일 정합 검사 — 헤더 N = 행 수, index.json = 파일 목록, 순위 단조, 날짜 범위. python3 tests/test_calendar.py"""
import sys, json
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parent.parent; D=ROOT/"docs"/"data"
idx=json.load(open(D/"index.json")); files=sorted((D/"scores").glob("*.csv")); bad=[]
if idx["count"]!=len(files) or [r["d"] for r in idx["dates"]]!=[f.stem for f in files]: bad.append("index.json != 파일 목록")
if idx["first"]!="2020-01-02": bad.append("소급 시작일 "+str(idx["first"]))
tot=0
for f,r in zip(files,idx["dates"]):
    head=open(f,encoding="utf-8").readline(); x=pd.read_csv(f,skiprows=1)
    if f"date={f.stem} " not in head: bad.append(f"{f.name}: 헤더 날짜")
    if len(x)!=r["n"] or f"N={len(x)} " not in head: bad.append(f"{f.name}: N {r['n']} != 행 {len(x)}")
    if not x["rank"].is_monotonic_increasing: bad.append(f"{f.name}: 순위 비단조")
    if not x.M.between(0,100).all(): bad.append(f"{f.name}: M 범위")
    if x.ticker.duplicated().any(): bad.append(f"{f.name}: 티커 중복")
    tot+=f.stat().st_size
print(f"{len(files)}일 {idx['first']}~{idx['last']} 총 {tot/1e6:.1f}MB, 위반 {len(bad)}건"); [print(" ",b) for b in bad[:10]]; sys.exit(1 if bad else 0)
