"""정적 페이지 생성 — docs/index.html · products.html · history.html. 외부 라이브러리·외부 스크립트 0, 개인 보유 정보 0."""
import json, html, glob, os
from pathlib import Path
import numpy as np, pandas as pd
try: from mm_lib import DATA, DOCS, ROOT, now_kst, MSCORE_SHA, load_status
except ImportError: from scripts.mm_lib import DATA, DOCS, ROOT, now_kst, MSCORE_SHA, load_status
E=html.escape
CSS="""
body{font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Noto Sans KR',sans-serif;margin:0;padding:12px 14px;color:#1b1f23;background:#fff;font-size:14px}
h1{font-size:18px;margin:4px 0 8px} h2{font-size:15px;margin:22px 0 6px} .meta{color:#444;line-height:1.55;margin-bottom:8px}
.warn{background:#fff4e5;border:1px solid #f0b34f;padding:6px 9px;border-radius:5px;margin:6px 0}
.wrap{overflow-x:auto;border:1px solid #d0d7de;border-radius:6px} table{border-collapse:separate;border-spacing:0;font-size:12.5px;min-width:1250px}
th,td{padding:5px 7px;border-bottom:1px solid #eaeef2;white-space:nowrap;text-align:right;background:#fff} th{background:#f6f8fa;cursor:pointer;position:sticky;top:0;z-index:2}
td:nth-child(1),th:nth-child(1){position:sticky;left:0;width:44px;min-width:44px;text-align:center;z-index:3;background:#f6f8fa}
td:nth-child(2),th:nth-child(2){position:sticky;left:45px;min-width:92px;text-align:left;z-index:3;font-weight:600;background:#fff}
th:nth-child(2){background:#f6f8fa} td.l,th.l{text-align:left} tr.c td{background:#fafbfc;color:#444} tr.c td:nth-child(2){background:#fafbfc}
.badge{display:inline-block;font-size:11px;padding:0 5px;border-radius:8px;background:#eee;color:#555;margin-left:3px} .b-approx{background:#ffe9c7;color:#8a5a00}
.b-prov{background:#ffd9d9;color:#8b1a1a} .up{color:#0a7a2f} .dn{color:#b3261e} .tog{cursor:pointer;color:#0366d6;margin-right:4px;user-select:none}
.foot{margin-top:26px;color:#444;border-top:1px solid #d0d7de;padding-top:8px;line-height:1.6} a{color:#0366d6} nav a{margin-right:12px}
"""
JS="""
function cv(td){var v=td.getAttribute('data-v'); if(v===null) v=td.textContent; var n=parseFloat(String(v).replace(/[,%+○×]/g,'').replace('−','-')); return isNaN(n)?String(v):n;}
function sortT(id,col){var t=document.getElementById(id),tb=t.tBodies[0],rows=Array.prototype.slice.call(tb.rows),par=rows.filter(function(r){return !r.getAttribute('data-parent')}),
 ch={};rows.forEach(function(r){var p=r.getAttribute('data-parent');if(p){(ch[p]=ch[p]||[]).push(r)}});
 var dir=(t.getAttribute('data-sc')==col&&t.getAttribute('data-sd')=='1')?-1:1;t.setAttribute('data-sc',col);t.setAttribute('data-sd',dir==1?'1':'-1');
 par.sort(function(a,b){var x=cv(a.cells[col]),y=cv(b.cells[col]);if(typeof x=='number'&&typeof y=='number')return dir*(x-y);return dir*String(x).localeCompare(String(y));});
 par.forEach(function(r){tb.appendChild(r);var g=r.getAttribute('data-g');if(g&&ch[g])ch[g].forEach(function(c){tb.appendChild(c)})});}
function tog(g){var rs=document.querySelectorAll('tr[data-parent="'+g+'"]'),open=rs.length&&rs[0].style.display=='none';rs.forEach(function(r){r.style.display=open?'table-row':'none'});}
"""
def pg(title, body, nav_cur):
    nav=" ".join(f'<a href="{h}"{" style=font-weight:700" if h==nav_cur else ""}>{n}</a>' for h,n in (("index.html","순위표"),("products.html","상품"),("history.html","이력")))
    return f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(title)}</title><style>{CSS}</style></head><body><nav>{nav}</nav>{body}<script>{JS}</script></body></html>'
def f1(x,n=1,sign=False):
    if x is None or (isinstance(x,float) and np.isnan(x)): return "—"
    return f"{x:+,.{n}f}" if sign else f"{x:,.{n}f}"
def cells(r, child=False):
    appr=' <span class="badge b-approx">근사</span>' if int(r.approx) else ""
    ab="○" if (r.get("above200",0)==1) else "×"
    bq=f"β {r.beta:.2f} · R² {r.r2:.2f}" if (r.beta is not None and not pd.isna(r.beta)) else "—"
    return (f'<td>{E(str(r.rank_txt))}</td><td class="l">{E(r.ticker_txt)}</td><td class="l">{E(r.issuer)}</td><td>{E(r.type)}</td><td class="l">{E(r.proxy)}{appr}</td>'
            f'<td data-v="{r.M:.4f}"><b>{r.M:.1f}</b></td><td data-v="{r.sig*100:.3f}">{r.sig*100:.1f}</td><td>{r.p_sig:.3f}</td><td data-v="{r.rsA*100:.3f}">{f1(r.rsA*100,1,True)}</td><td>{r.p_rsA:.3f}</td>'
            f'<td data-v="{r.f1b*100:.3f}">{f1(r.f1b*100,2,True)}</td><td>{r.p_f1b:.3f}</td><td data-v="{r.c1_ma200*100:.3f}">{f1(r.c1_ma200*100,1,True)}</td><td data-v="{ 1 if ab=="○" else 0}">{ab}</td>'
            f'<td data-v="{r.close3:.4f}">{f1(r.close3,2)}</td><td data-v="{r.adtv:.4f}">{f1(r.adtv,1)}</td><td>{int(r.listed_days)}</td><td class="l">{E(bq)}</td><td class="l">{r.d_rank_html}</td><td class="l">{E(r.dgrp)}</td>')
HEAD=["순위","티커","발행사","구분","1x","M-score","σ60(%)","pct","RS_A(%)","pct","MA항(%)","pct","1x종가/MA200−1(%)","1x 200일선 상회","3배 종가","20일 평균 거래대금($M)","listed_days","대리 품질","Δ순위(5일)","동일 1x 그룹"]
def thead(tid): return "<thead><tr>"+"".join(f'<th{" class=l" if i in (1,2,4,17,18,19) else ""} onclick="sortT(\'{tid}\',{i})">{E(h)}</th>' for i,h in enumerate(HEAD))+"</tr></thead>"
def drank(v):
    if v is None or (isinstance(v,float) and np.isnan(v)) or v=="": return ""
    if v=="신규": return "신규"
    try: x=int(v)
    except: return E(str(v))
    return f'<span class="up">▲{x}</span>' if x>0 else (f'<span class="dn">▼{-x}</span>' if x<0 else "0")
def build_index(df, meta):
    st=load_status()
    el=df[df.table=="적격"].copy().sort_values(["rank","M"],ascending=[True,False])
    N=len(df); n=len(el); up=int(el.above200.sum()) if n else 0
    # 동일 1x 그룹 접기
    cnt=el.groupby("proxy").ticker.count(); rowsHTML=[]; done=set()
    for _,r in el.iterrows():
        g=r.proxy if cnt[r.proxy]>=2 else ""
        r=r.copy(); r["dgrp"]=g
        if g and g in done: continue
        if g:
            done.add(g); members=el[el.proxy==g].sort_values("adtv",ascending=False); rep=members.iloc[0].copy()
            rep["dgrp"]=g; rep["ticker_txt"]=" · ".join(members.ticker); rep["rank_txt"]=str(int(rep["rank"])); rep["d_rank_html"]=drank(rep.get("d_rank"))
            rowsHTML.append(f'<tr class="p" data-g="{E(g)}">'+cells(rep).replace('<td class="l">'+E(rep.ticker_txt)+'</td>',f'<td class="l"><span class="tog" onclick="tog(\'{E(g)}\')">▸</span>{E(rep.ticker_txt)}</td>',1)+"</tr>")
            for _,m in members.iterrows():
                m=m.copy(); m["dgrp"]=g; m["ticker_txt"]=m.ticker; m["rank_txt"]=str(int(m["rank"])); m["d_rank_html"]=drank(m.get("d_rank"))
                rowsHTML.append(f'<tr class="c" data-parent="{E(g)}" style="display:none">'+cells(m)+"</tr>")
        else:
            r["ticker_txt"]=r.ticker; r["rank_txt"]=str(int(r["rank"])); r["d_rank_html"]=drank(r.get("d_rank"))
            rowsHTML.append("<tr>"+cells(r)+"</tr>")
    prov=meta.get("provisional")
    banner=(f'<div class="warn"><span class="badge b-prov">잠정</span> 기준일 {E(meta["asof"])} · 사유: SPY 일봉 최신 행({E(prov["raw_last"])})이 {E(prov["reason"])} → 직전 확정일로 산출</div>' if prov else "")
    stale=df[df.table=="⚠"]
    stale_html=(f'<div class="warn">⚠ 순위 제외 {len(stale)}종(최신 확정 봉이 기준일과 다름): '+", ".join(f"{E(r.ticker)}({E(r.reason)})" for r in stale.itertuples())+"</div>") if len(stale) else ""
    chk=st.get("check_incomplete",{}); chk_html=(f'<div class="warn">점검 미완: '+", ".join(f"{E(k)}({E(v)})" for k,v in chk.items())+"</div>") if chk else ""
    body=f"""<h1>무매 M-score 공용 페이지</h1>
<div class="meta">기준일 <b>{E(meta['asof'])}</b> (US 종가) · 산출 {E(meta['generated'])} KST · 적격 <b>{n}/{N}</b> · 1x 200일선 상회 <b>{up}/{n}</b><br>
M-score = [pct(σ60) + pct(RS_A: 12-1개월 수익률) + pct(MA50/MA200−1)] / 3 × 100 — 1x 기초지수 ETF 기준, 적격 종목 내 백분위 단순평균 (정의 sha256 {E(MSCORE_SHA[:8])}…). 참고용 표시이며 개인 보유·평단 정보는 사용하지 않습니다.</div>
{banner}{stale_html}{chk_html}
<h2>표1. 적격 순위표</h2><div class="wrap"><table id="t1">{thead('t1')}<tbody>{''.join(rowsHTML)}</tbody></table></div>
<div class="meta" style="margin-top:6px">접힌 행(동일 1x 그룹)의 3배 열은 거래대금 최대 티커 값이며 ▸ 로 개별 티커를 펼칩니다. 동점은 같은 순위 번호입니다.</div>"""
    # 대기
    wt=df[df.table=="대기"].sort_values("M",ascending=False)
    wrows=[]
    for r in wt.itertuples():
        appr=' <span class="badge b-approx">근사</span>' if int(r.approx) else ""
        wrows.append(f'<tr><td class="l">{E(r.ticker)}</td><td class="l">{E(r.issuer)}</td><td>{E(r.type)}</td><td class="l">{E(r.proxy)}{appr}</td><td>{"—" if pd.isna(r.M) else f"{r.M:.1f}"}</td><td>{int(r.listed_days)}</td><td>{"—" if pd.isna(r.adtv) else f"{r.adtv:.2f}"}</td><td class="l" style="white-space:normal;min-width:420px">{E(r.reason)}</td></tr>')
    for c in meta.get("new_products",[]):
        wrows.append(f'<tr><td class="l">{E(c.get("ticker") or c.get("name",""))}</td><td class="l">{E(c.get("issuer",""))}</td><td>{E(c.get("type",""))}</td><td class="l">미정</td><td>산출 불가(1x 매핑 미정)</td><td>—</td><td>—</td><td class="l" style="white-space:normal">신규 편입 {E(c.get("found",""))} — E1 미달 상태로 대기, 출처 {E(c.get("source",""))}</td></tr>')
    body+=f"""<h2>표2. 대기 (E1~E4 미달 — M-score 는 적격 집합에 1개 추가했을 때의 값, 숫자만)</h2><div class="wrap"><table style="min-width:900px"><thead><tr><th class="l">티커</th><th class="l">발행사</th><th>구분</th><th class="l">1x</th><th>M-score</th><th>listed_days</th><th>20일 평균 거래대금($M)</th><th class="l">사유</th></tr></thead><tbody>{''.join(wrows) or '<tr><td colspan=8>없음</td></tr>'}</tbody></table></div>"""
    ex=df[df.table=="제외"]
    xrows=[]
    for r in ex.itertuples():
        e=st["excluded"].get(r.ticker,{})
        xrows.append(f'<tr><td class="l">{E(r.ticker)}</td><td>{E(r.type)}</td><td>{"—" if pd.isna(r.M) else f"{r.M:.1f}"}</td><td class="l" style="white-space:normal;min-width:260px">{E(e.get("title",""))}</td><td>{E(e.get("date",""))}</td><td class="l">{"<a href=%s>링크</a>"%html.escape(e.get("url",""),quote=True) if e.get("url") else "—"}</td><td class="l" style="white-space:normal">{E(e.get("action",""))}</td></tr>')
    body+=f"""<h2>표3. 제외 (E5 문제 공지)</h2><div class="wrap"><table style="min-width:800px"><thead><tr><th class="l">티커</th><th>구분</th><th>M-score</th><th class="l">공지 제목</th><th>날짜</th><th class="l">링크</th><th class="l">조치</th></tr></thead><tbody>{''.join(xrows) or '<tr><td colspan=7>없음</td></tr>'}</tbody></table></div>"""
    body+="""<div class="foot"><b>한계 고지</b><br>① 주식 지수·섹터 안에서 진입 시점 지표로 회복 불능을 예측하지 못함(MM-P2)<br>② 2013~2020 바구니 재생에서 고정 6종 대비 열세, 2021 이후 우세(MM-P5)<br>③ 상위권이 특정 ETN(에너지·FANG+)에 몰리는 경향(MM-P4~P6)</div>"""
    return pg("무매 M-score",body,"index.html")
def build_products(uni, df, meta, p0):
    st=load_status(); rows=[]
    for r in uni.itertuples():
        d=df[df.ticker==r.ticker]; d=d.iloc[0] if len(d) else None
        pr=p0[p0.ticker==r.ticker]; pr=pr.iloc[0] if len(pr) else None
        appr=' <span class="badge b-approx">근사</span>' if int(r.approx) else ""
        note=[]
        if r.ticker in st["notes"]: note+=[str(x) for x in st["notes"][r.ticker]]
        if r.ticker in st.get("check_incomplete",{}): note.append("점검 미완: "+st["check_incomplete"][r.ticker])
        rows.append(f'<tr><td class="l"><b>{E(r.ticker)}</b></td><td class="l">{E(r.issuer)}</td><td>{E(r.type)}</td><td>{E(r.leverage)}</td><td class="l" style="white-space:normal;min-width:220px">{E(str(pr.index_name)) if pr is not None else "—"}<br><span style="color:#777">{E(str(pr.index_name_source)) if pr is not None else ""}</span></td><td class="l">{E(r.proxy)}{appr}</td><td class="l">{(f"β {d.beta:.2f} · R² {d.r2:.2f} ({E(str(d.proxy_measured))})" if d is not None and d.beta is not None and not pd.isna(d.beta) else "—")}</td><td>{E(str(pr.first_bar)) if pr is not None else "—"}</td><td class="l" style="white-space:normal;min-width:200px">{E(str(pr.splits_yf)) if pr is not None else "—"}</td><td class="l" style="white-space:normal;min-width:240px">{E(" / ".join(note)) or "—"}</td></tr>')
    for c in meta.get("new_products",[]):
        rows.append(f'<tr><td class="l"><b>{E(c.get("ticker") or c.get("name",""))}</b></td><td class="l">{E(c.get("issuer",""))}</td><td>{E(c.get("type",""))}</td><td>{E(c.get("leverage",""))}</td><td class="l">{E(c.get("index",""))}</td><td class="l">미정</td><td>—</td><td>—</td><td>—</td><td class="l" style="white-space:normal">초안 · 신규 편입 {E(c.get("found",""))} · 출처 {E(c.get("source",""))}</td></tr>')
    body=f"""<h1>상품 정보</h1><div class="meta">유니버스 {len(uni)}종 + 신규 편입 {len(meta.get('new_products',[]))}종. 추종지수명·출처는 MM-P0B 조사(발행사 1차 자료 / 지식 기반 [미검증] 표기), 대리 품질은 data/proxy_quality.csv, 분할 이력은 yfinance 기록. 수수료·금융비용은 자동 수집하지 않으며 발행사 문서를 확인하십시오.</div>
<div class="wrap"><table style="min-width:1100px"><thead><tr><th class="l">티커</th><th class="l">발행사</th><th>구분</th><th>배수</th><th class="l">추종지수 · 출처</th><th class="l">1x 대리</th><th class="l">대리 품질</th><th>첫 일봉</th><th class="l">분할·역분할</th><th class="l">비고</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"""
    return pg("무매 상품",body,"products.html")
def build_history(files, latest_df):
    el=latest_df[latest_df.table=="적격"].sort_values(["rank","M"],ascending=[True,False]).head(10)
    tick=list(el.ticker); dates=[]; M={}; R={}
    for f in files[-30:]:
        d=pd.read_csv(f); dt_=d.date.iloc[0]; dates.append(dt_)
        for t in tick:
            r=d[(d.ticker==t)]
            if len(r) and r.iloc[0].table=="적격": M[(t,dt_)]=r.iloc[0].M; R[(t,dt_)]=r.iloc[0]["rank"]
    def tbl(D,fmt):
        h="<tr><th class='l'>티커</th>"+"".join(f"<th>{E(x[5:])}</th>" for x in dates)+"</tr>"
        b="".join("<tr><td class='l'><b>%s</b></td>"%E(t)+"".join("<td>%s</td>"%(fmt(D[(t,x)]) if (t,x) in D and not pd.isna(D[(t,x)]) else "—") for x in dates)+"</tr>" for t in tick)
        return f'<div class="wrap"><table style="min-width:900px"><thead>{h}</thead><tbody>{b}</tbody></table></div>'
    body=f"""<h1>이력 — 적격 상위 10 (최근 {len(dates)}거래일)</h1><div class="meta">최신 기준일 상위 10 티커의 날짜별 값. 과거 날짜는 당시 데이터로 재산출했고 E4(대리 품질)·E5(공지) 상태는 현재 값을 적용했습니다. 숫자만 표시합니다.</div>
<h2>M-score</h2>{tbl(M,lambda v:f"{v:.1f}")}<h2>순위</h2>{tbl(R,lambda v:f"{int(v)}")}"""
    return pg("무매 이력",body,"history.html")
def build_all(latest_df, uni, meta, p0, score_files):
    DOCS.mkdir(exist_ok=True)
    (DOCS/"index.html").write_text(build_index(latest_df,meta),encoding="utf-8")
    (DOCS/"products.html").write_text(build_products(uni,latest_df,meta,p0),encoding="utf-8")
    (DOCS/"history.html").write_text(build_history(score_files,latest_df),encoding="utf-8")
    (DOCS/".nojekyll").write_text("")
