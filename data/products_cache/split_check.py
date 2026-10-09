# 일회성: Yahoo splits_yf 중 2020년 이후 분할을 EDGAR 공시(497 보충서 등)와 대조
import json,subprocess,time,re,os,datetime
UA="mm-rotation research (jjoychan85@gmail.com)"
RAW='raw'
def get(u):
    r=subprocess.run(['curl','-s','-m','90','-A',UA,u],capture_output=True); time.sleep(0.6); return r.stdout
def clean(t):
    t=re.sub(r'<[^>]+>',' ',t)
    for a,b in [('&nbsp;',' '),('&#160;',' '),('&amp;','&'),('&#8203;','')]: t=t.replace(a,b)
    return re.sub(r'\s+',' ',t)
EV=[('0001424958','HIBL','2020-04-23','reverse'),('0001424958','DPST','2020-04-23','reverse'),('0001424958','RETL','2020-04-23','reverse'),
    ('0001424958','RETL','2021-01-11','forward'),('0001424958','SOXL','2021-03-02','forward'),('0001424958','TECL','2021-03-02','forward'),('0001424958','HIBL','2021-03-02','forward'),
    ('0001424958','DPST','2021-10-25','forward'),('0001424958','RETL','2021-10-25','forward'),('0001424958','DPST','2023-06-05','reverse'),('0001424958','LABU','2023-12-04','reverse'),
    ('0001174610','TQQQ','2025-11-20','forward'),('0001174610','UDOW','2025-11-20','forward'),('0001174610','UMDD','2021-05-25','forward'),('0001174610','UDOW','2021-05-25','forward'),
    ('0001174610','TQQQ','2022-01-13','forward'),('0001174610','UPRO','2022-01-13','forward')]
res=[]
for cik,t,d,kind in EV:
    dt=datetime.date.fromisoformat(d)
    s=(dt-datetime.timedelta(days=60)).isoformat(); e=(dt+datetime.timedelta(days=3)).isoformat()
    found=None
    for form in ['497','497K','8-K','497J']:
        j=json.loads(get(f'https://efts.sec.gov/LATEST/search-index?q={t}%20split&forms={form}&ciks={cik}&dateRange=custom&startdt={s}&enddt={e}') or b'{}')
        for x in j.get('hits',{}).get('hits',[]):
            acc,fn=x['_id'].split(':'); path=f'{RAW}/sp_{acc}.htm'
            if not os.path.exists(path):
                open(path,'wb').write(get(f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace("-","")}/{fn}'))
            txt=clean(open(path,errors='ignore').read())
            m=re.search(r'\b'+t+r'\b.{0,400}?(reverse (share|stock)? ?split|share split|stock split|split)',txt) or re.search(r'(reverse (share|stock)? ?split|share split|stock split).{0,400}?\b'+t+r'\b',txt)
            if m and re.search(r'20\d\d',txt[max(0,m.start()-200):m.end()+300]):
                found={'filed':x['_source']['file_date'],'form':form,'url':f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace("-","")}/{fn}','snippet':txt[max(0,m.start()-100):m.end()+260]}
                break
        if found: break
    res.append({'ticker':t,'date':d,'kind':kind,'found':found})
    print(t,d,kind,'->',(found['filed']+' '+found['form']+' '+found['url']) if found else 'NOT FOUND')
json.dump(res,open('split_check_result.json','w'),ensure_ascii=False,indent=1)
