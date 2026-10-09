# 일회성 수집 코드: BMO(CIK 927971) FWP 중 MicroSectors 보도자료 전수 수집 (EDGAR FTS, User-Agent 준수, <=2req/s)
import json,subprocess,time,re,os,sys
UA="mm-rotation research (jjoychan85@gmail.com)"
def get(u):
    r=subprocess.run(['curl','-s','-m','60','-A',UA,u],capture_output=True); time.sleep(0.5); return r.stdout
seen={}
for q in ['MicroSectors','%22BMO%20Announces%22','%22Financing%20Spread%22','%22Call%20Settlement%20Date%22']:
    for frm in range(0,400,100):
        d=json.loads(get(f'https://efts.sec.gov/LATEST/search-index?q={q}&forms=FWP&ciks=0000927971&dateRange=custom&startdt=2022-01-01&enddt=2026-10-09&from={frm}') or b'{}')
        hits=d.get('hits',{}).get('hits',[])
        if not hits: break
        for x in hits: seen[x['_id']]=x['_source']['file_date']
print(len(seen))
json.dump(seen,open('raw/fwp_index.json','w'),indent=1,sort_keys=True)
