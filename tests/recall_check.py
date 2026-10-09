#!/usr/bin/env python3
"""회귀(재현율) 점검 — 7건 픽스처 밖의 '알려진 실제 사건' 공시에서 규칙(정규식 수준, 티커 귀속 없이)이 해당 유형을 계속 잡는지 확인.
과적합 방지용: 규칙을 7건에 맞춰 고친 뒤에도 독립 사건을 놓치지 않는지 본다. 원문은 fp_sample 캐시(tests/fp_cache)에 받아 쓴다."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_fixtures as RF, fp_sample as FP
EV=[ # (발행사 cik, accession, 문서, 설명, 기대 유형)
 ("1424958","0001193125-25-230306","d949346d497.htm","Direxion 2025-10-03 거래 중단·청산","상장폐지·청산"),
 ("1424958","0001193125-25-151293","d949204d497.htm","Direxion 2025-06-27 거래 중단·청산","상장폐지·청산"),
 ("1424958","0001193125-26-106262","d111775d497.htm","Direxion 2026-03-13 청산(SHPD 등)","상장폐지·청산"),
 ("1424958","0001193125-25-161967","d67146d497.htm","Direxion 2025-07-21 기초지수 변경","지수 변경"),
 ("1424958","0001193125-25-192834","d78482d497.htm","Direxion 2025-08-29 역분할","역분할·액면분할"),
 ("1424958","0001193125-26-076908","d100149d497.htm","Direxion 2026-02-26 역분할(MUD·TSLS)","역분할·액면분할"),
 ("1424958","0001193125-26-265925","d105555d497.htm","Direxion 2026-06-10 20-for-1 액면분할(KORU·MUU)","역분할·액면분할"),
 ("927971","0001214659-21-012516","p1129215fwp.htm","BMO 2021-12-01 ETN 4종 조기상환 보도자료(독립 사건)","조기상환·가속상환"),
 ("927971","0001214659-20-010065","p121200fwp.htm","BMO 2020-12-01 ETN 6종 조기상환 보도자료(독립 사건)","조기상환·가속상환"),
 ("927971","0001214659-26-000920","z126260fwp.htm","BMO 2026-01-28 GDXD·FNGD 역분할 보도자료","역분할·액면분할"),
 ("927971","0001214659-25-016738","j1113250fwp.htm","BMO 2025-11-14 GDXU Financing Spread 인상 보도자료","금융비용·수수료 변경"),
]
def main():
    R=RF.load_rules(); bad=0
    for cik,acc,doc,lab,want in EV:
        url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/{doc}"
        t=RF.totext(FP.fetch(url)); got=sorted({typ for typ,s,rx in R.TRIG if rx.search(t)}); ok=want in got; bad+=not ok
        print(f"  {'PASS' if ok else 'FAIL'} {lab} | 기대 유형 {want} | 규칙이 잡은 유형 {got}")
    print(f"재현율 점검: {len(EV)-bad}/{len(EV)}"); return 1 if bad else 0
if __name__=="__main__": sys.exit(main())
