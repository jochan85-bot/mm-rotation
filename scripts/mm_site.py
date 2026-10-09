"""정적 페이지 생성 — docs/index.html · products.html · history.html. 외부 라이브러리·외부 스크립트 0, 개인 정보 0."""
import json, html, re
from pathlib import Path
import numpy as np, pandas as pd
try: from mm_lib import DATA, DOCS, ROOT, now_kst, MSCORE_SHA, load_status
except ImportError: from scripts.mm_lib import DATA, DOCS, ROOT, now_kst, MSCORE_SHA, load_status
E=html.escape
CSS="""
body{font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Noto Sans KR',sans-serif;margin:0;padding:12px 14px;color:#1b1f23;background:#fff;font-size:14px}
h1{font-size:18px;margin:4px 0 8px} h2{font-size:15px;margin:22px 0 6px} .meta{color:#444;line-height:1.55;margin-bottom:8px}
.warn{background:#fff4e5;border:1px solid #f0b34f;padding:6px 9px;border-radius:5px;margin:6px 0}
.wrap{overflow-x:auto;border:1px solid #d0d7de;border-radius:6px} table{border-collapse:separate;border-spacing:0;font-size:12.5px;min-width:1500px}
th,td{padding:5px 7px;border-bottom:1px solid #eaeef2;white-space:nowrap;text-align:right;background:#fff} th{background:#f6f8fa;cursor:pointer;position:sticky;top:0;z-index:2}
td:nth-child(1),th:nth-child(1){position:sticky;left:0;width:44px;min-width:44px;text-align:center;z-index:3;background:#f6f8fa}
td:nth-child(2),th:nth-child(2){position:sticky;left:45px;min-width:92px;text-align:left;z-index:3;font-weight:600;background:#fff}
th:nth-child(2){background:#f6f8fa} td.l,th.l{text-align:left}
tr.g td{background:#eef0f3;color:#5a6270} tr.g td:nth-child(2){background:#eef0f3} tr.c td{background:#fafbfc;color:#444} tr.c td:nth-child(2){background:#fafbfc}
tr.g.c td,tr.g.c td:nth-child(2){background:#e8eaee}
.badge{display:inline-block;font-size:11px;padding:0 5px;border-radius:8px;background:#eee;color:#555;margin-left:3px} .b-approx{background:#ffe9c7;color:#8a5a00}
.b-prov{background:#ffd9d9;color:#8b1a1a} .up{color:#0a7a2f} .dn{color:#b3261e} .tog{cursor:pointer;color:#0366d6;margin-right:4px;user-select:none}
.foot{margin-top:26px;color:#444;border-top:1px solid #d0d7de;padding-top:8px;line-height:1.6} a{color:#0366d6} nav a{margin-right:12px}
td.sc{font-size:12px} td.sc .p{color:#777}
@media (max-width:600px){
 td:nth-child(3),th:nth-child(3){position:sticky;left:137px;min-width:56px;z-index:3;background:#fff}
 th:nth-child(3){background:#f6f8fa} tr.g td:nth-child(3){background:#eef0f3} tr.c td:nth-child(3){background:#fafbfc} tr.g.c td:nth-child(3){background:#e8eaee}
 td:nth-child(2),th:nth-child(2){min-width:92px;max-width:92px;overflow:hidden;text-overflow:ellipsis}
}
details.card{border:1px solid #d0d7de;border-radius:6px;margin:8px 0;padding:0 10px} details.card[open]{background:#fcfdfe} details.card:target{border-color:#0366d6;box-shadow:0 0 0 2px #cfe3ff}
details.card>summary{cursor:pointer;padding:8px 0;font-weight:600;list-style:none} details.card>summary::-webkit-details-marker{display:none}
details.card>summary::before{content:'▸ ';color:#0366d6} details.card[open]>summary::before{content:'▾ '}
.kv{display:grid;grid-template-columns:130px 1fr;gap:3px 12px;margin:4px 0 10px;font-size:13px} .kv div.k{color:#555} .feat{margin:2px 0 8px;line-height:1.55}
.sm{color:#666;font-size:12px}
"""
JS="""
function cv(td){var v=td.getAttribute('data-v'); if(v===null) v=td.textContent; var n=parseFloat(String(v).replace(/[,%+○×]/g,'').replace('−','-')); return isNaN(n)?null:n;}
function sortT(id,col){var t=document.getElementById(id),tb=t.tBodies[0],rows=Array.prototype.slice.call(tb.rows),par=rows.filter(function(r){return !r.getAttribute('data-parent')}),
 ch={};rows.forEach(function(r){var p=r.getAttribute('data-parent');if(p){(ch[p]=ch[p]||[]).push(r)}});
 var dir=(t.getAttribute('data-sc')==col&&t.getAttribute('data-sd')=='1')?-1:1;t.setAttribute('data-sc',col);t.setAttribute('data-sd',dir==1?'1':'-1');
 par.sort(function(a,b){var x=cv(a.cells[col]),y=cv(b.cells[col]);if(x===null&&y===null)return dir*String(a.cells[col].textContent).localeCompare(String(b.cells[col].textContent));if(x===null)return 1;if(y===null)return -1;return dir*(x-y);});
 par.forEach(function(r){tb.appendChild(r);var g=r.getAttribute('data-g');if(g&&ch[g])ch[g].forEach(function(c){tb.appendChild(c)})});}
function tog(g){var rs=document.querySelectorAll('tr[data-parent="'+g+'"]'),open=rs.length&&rs[0].style.display=='none';rs.forEach(function(r){r.style.display=open?'table-row':'none'});}
function openHash(){var h=location.hash.slice(1);if(!h)return;var d=document.getElementById(h);if(d&&d.tagName=='DETAILS'){d.open=true;d.scrollIntoView();}}
window.addEventListener('hashchange',openHash);window.addEventListener('load',openHash);
"""
def pg(title, body, nav_cur, manual=False):
    nav=" ".join(f'<a href="{h}"{" style=font-weight:700" if h==nav_cur else ""}>{n}</a>' for h,n in (("index.html","순위표"),("products.html","상품"),("history.html","이력")))
    return f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(title)}</title><style>{CSS}</style></head><body><nav>{nav}</nav>{body}<script>{JS}</script></body></html>'
def f1(x,n=1,sign=False):
    if x is None or (isinstance(x,float) and np.isnan(x)): return "—"
    return f"{x:+,.{n}f}" if sign else f"{x:,.{n}f}"
def nz(x): return x is not None and not (isinstance(x,float) and np.isnan(x))
def short_index(name):
    """공식 지수명 짧게: 상표 표기·'Index'·제공사 접두 일부 제거"""
    n=str(name or "")
    n=re.sub(r"\((R|TM|SM)\)|[®™]|\bSM\b","",n)
    n=re.sub(r"\s*-\s*gross total return version"," GTR",n); n=re.sub(r"\s*-\s*net total return version"," NTR",n)
    n=re.sub(r"\bMicroSectors\b\s*","",n); n=re.sub(r"\s+Index\b","",n); n=re.sub(r"\s{2,}"," ",n).strip()
    return n if len(n)<=30 else n[:29]+"…"
def path_short(p):
    p=str(p or "")
    return "복합" if "+" in p else ("exact" if "exact" in p else ("레벨" if "지수 레벨" in p else "—"))
def _lowliq():
    try:
        from mm_lib import load_yaml_simple
        return float(load_yaml_simple(DATA/"eligibility.yaml")["E2"]["threshold"])
    except Exception: return 0.3
LOWLIQ=_lowliq()
def badge_tip(r):
    tips=[]
    for b in str(r.badges).split(" · "):
        if b=="근사": tips.append(f"근사: 3배÷1x 회귀 β {r.beta:.2f}·R² {r.r2:.2f}(n={int(r.n_beta)}) — β 2.7~3.3 밖 또는 R²<0.85" if nz(r.beta) else "근사")
        elif b=="표본부족": tips.append(f"표본부족: 회귀 표본 n={int(r.n_beta)}<60 (경로는 공식 지수, 검증 미완)")
        elif b=="신규": tips.append(f"신규: 3배 상장 {int(r.listed_days)}거래일 <252")
        elif b=="저유동": tips.append(f"저유동: 20일 평균 거래대금 ${r.adtv:.2f}M <${LOWLIQ:g}M")
        elif b.startswith("무거래"): tips.append(f"{b}: 최근 20봉 중 거래량 0 인 봉 {b[3:]}개")
    return " / ".join(tips)
def rk(v): return f'<td data-v="{v:.0f}">{v:.0f}</td>' if nz(v) else '<td data-v="">—</td>'
def cells(r, pinfo):
    ptip=r.proxy_tip if isinstance(r.proxy_tip,str) else ""
    pi=pinfo.get(r.ticker,{})
    iname=pi.get("index_name",""); ishort=short_index(iname) or (r.proxy_disp if isinstance(r.proxy_disp,str) and r.proxy_disp else r.proxy)
    tip=f"{iname} | 경로: {pi.get('onex_path','')} | 1x 계열 {r.proxy}"+(f" | {ptip}" if ptip else "")+(f" | {r.proxy_tail}" if isinstance(r.proxy_tail,str) and r.proxy_tail else "")
    bd=str(r.badges) if isinstance(r.badges,str) and r.badges else ""
    bq=f"β {r.beta:.2f} · R² {r.r2:.2f} (n={int(r.n_beta)})" if nz(r.beta) else "—"
    ab="○" if (getattr(r,"above200",0)==1) else "×"
    def sc(v,p,d,sign):
        return f'<td class="sc" data-v="{v*100:.3f}">{f1(v*100,d,sign)} <span class="p">· {p:.3f}</span></td>'
    return (f'<td data-v="{r.rank_n}">{E(str(r.rank_txt))}</td><td class="l" title="{E(str(r.issuer))} · {E(str(r.type))}">{r.ticker_html}</td>'
            f'<td data-v="{r.M:.4f}"><b>{r.M:.1f}</b></td>{rk(r.r5)}{rk(r.r20)}{rk(r.r60)}<td class="l" data-v="{r.d_rank_n}">{r.d_rank_html}</td>'
            f'<td class="l" title="{E(badge_tip(r))}">{E(bd) if bd else "—"}</td><td class="l" title="{E(tip)}">{E(ishort)}</td>'
            f'{sc(r.sig,r.p_sig,1,False)}{sc(r.rsA,r.p_rsA,1,True)}{sc(r.f1b,r.p_f1b,2,True)}'
            f'<td data-v="{r.c1_ma200*100:.3f}">{f1(r.c1_ma200*100,1,True)}</td><td data-v="{ 1 if ab=="○" else 0}">{ab}</td>'
            f'<td data-v="{r.close3:.4f}">{f1(r.close3,2)}</td><td data-v="{r.adtv:.4f}">{f1(r.adtv,1)}</td><td>{int(r.listed_days)}</td><td class="l">{E(bq)}</td><td class="l">{E(r.dgrp)}</td>')
HEAD=["순위","티커","M-score","5일 순위","20일 순위","60일 순위","Δ순위(5일)","거래 가능성","1x (공식 지수)","σ60(%)·pct","RS_A(%)·pct","MA항(%)·pct","1x종가/MA200−1(%)","1x 200일선 상회","3배 종가","20일 평균 거래대금($M)","listed_days","대리 품질","동일 1x 그룹"]
LEFT=(1,6,7,8,17,18)
def thead(tid): return "<thead><tr>"+"".join(f'<th{" class=l" if i in LEFT else ""} onclick="sortT(\'{tid}\',{i})">{E(h)}</th>' for i,h in enumerate(HEAD))+"</tr></thead>"
def drank(v):
    if v is None or (isinstance(v,float) and np.isnan(v)) or v=="": return "",""
    if v=="신규": return "신규",""
    try: x=int(v)
    except: return E(str(v)),""
    return (f'<span class="up">▲{x}</span>' if x>0 else (f'<span class="dn">▼{-x}</span>' if x<0 else "0")),x
def tlink(t): return f'<a href="products.html#{E(t)}">{E(t)}</a>'
def build_index(df, meta):
    st=load_status()
    pinfo={r["ticker"]:r for r in pd.read_csv(DATA/"product_info.csv").to_dict("records")}
    el=df[df.table=="순위"].copy().sort_values(["rank","M"],ascending=[True,False])
    N=len(df); n=len(el); up=int(el.above200.sum()) if n else 0
    gcnt=el.groupby("proxy").ticker.count(); rowsHTML=[]; done=set()
    def prep(m,g):
        m=m.copy(); m["dgrp"]=g; m["rank_txt"]=str(int(m["rank"])); m["rank_n"]=int(m["rank"])
        m["d_rank_html"],x=drank(m.get("d_rank")); m["d_rank_n"]=x
        return m
    for _,r in el.iterrows():
        g=r.proxy if gcnt[r.proxy]>=2 else ""
        if g and g in done: continue
        if g:
            done.add(g); members=el[el.proxy==g].sort_values("adtv",ascending=False)
            rep=prep(members.iloc[0],g)
            rep["ticker_html"]=f'<span class="tog" onclick="tog(\'{E(g)}\')">▸</span>'+" · ".join(tlink(t) for t in members.ticker)
            cls="g" if str(rep.badges) not in ("","nan") and isinstance(rep.badges,str) and rep.badges else ""
            rowsHTML.append(f'<tr class="{cls}" data-g="{E(g)}">'+cells(rep,pinfo)+"</tr>")
            for _,m in members.iterrows():
                m=prep(m,g); m["ticker_html"]=tlink(m.ticker)
                cls="c g" if isinstance(m.badges,str) and m.badges else "c"
                rowsHTML.append(f'<tr class="{cls}" data-parent="{E(g)}" style="display:none">'+cells(m,pinfo)+"</tr>")
        else:
            r=prep(r,g); r["ticker_html"]=tlink(r.ticker)
            cls="g" if isinstance(r.badges,str) and r.badges else ""
            rowsHTML.append(f'<tr class="{cls}">'+cells(r,pinfo)+"</tr>")
    prov=meta.get("provisional")
    banner=(f'<div class="warn"><span class="badge b-prov">잠정</span> 기준일 {E(meta["asof"])} · 사유: SPY 일봉 최신 행({E(prov["raw_last"])})이 {E(prov["reason"])} → 직전 확정일로 산출</div>' if prov else "")
    if meta.get("manual"): banner+='<div class="warn"><span class="badge b-prov">수동 산출</span> 이 페이지는 수동 실행으로 산출됐습니다. 예약(launchd) 첫 자동 실행이 확인되면 이 표기가 사라집니다.</div>'
    stale=df[df.table=="⚠"]
    stale_html=(f'<div class="warn">⚠ 순위 제외 {len(stale)}종: '+", ".join(f"{E(r.ticker)}({E(r.reason)})" for r in stale.itertuples())+"</div>") if len(stale) else ""
    chk=st.get("check_incomplete",{}); chk_html=(f'<div class="warn">점검 미완: '+", ".join(f"{E(k)}({E(v)})" for k,v in chk.items())+"</div>") if chk else ""
    nbad=int((el.badges.fillna("")!="").sum())
    body=f"""<h1>무매 M-score 공용 페이지</h1>
<div class="meta">기준일 <b>{E(meta['asof'])}</b> (US 종가) · 산출 {E(meta['generated'])} KST · 순위 모집단 <b>{n}/{N}</b> · 1x 200일선 상회 <b>{up}/{n}</b> · 거래 가능성 배지 {nbad}종 (회색 행)<br>
M-score = [pct(σ60) + pct(RS_A: 12-1개월 수익률) + pct(MA50/MA200−1)] / 3 × 100 — 1x = 발행사 공시 공식 지수(지수 레벨 또는 동일 지수 1x ETF — 툴팁·상품 페이지 참조). pct 모집단 = 유니버스 중 E5(문제 공지) 미해당·⚠ 없는 종목 전체이며 배지는 점수·순위를 바꾸지 않습니다 (정의 sha256 {E(MSCORE_SHA[:8])}…). 5·20·60일 순위 = 일별 M-score(그날 모집단 안 백분위 점수)의 N거래일 단순평균을 오늘 모집단 안에서 순위 매긴 값(창의 80% 미만이면 —). 참고용 표시이며 개인 정보는 사용하지 않습니다.</div>
{banner}{stale_html}{chk_html}
<h2>순위표</h2><div class="wrap"><table id="t1">{thead('t1')}<tbody>{''.join(rowsHTML)}</tbody></table></div>
<div class="meta" style="margin-top:6px">회색 행 = 거래 가능성 열에 배지가 있는 종목(근사 · 표본부족 · 신규 · 저유동 · 무거래N). 접힌 행(동일 1x 그룹)의 3배 열은 거래대금 최대 티커 값이며 ▸ 로 개별 티커를 펼칩니다. 티커를 누르면 상품 카드로 이동합니다. 동점은 같은 순위 번호입니다.</div>"""
    ex=df[df.table=="제외"]
    xrows=[]
    for r in ex.itertuples():
        e=st["excluded"].get(r.ticker,{})
        xrows.append(f'<tr><td class="l">{E(r.ticker)}</td><td>{E(r.type)}</td><td>{"—" if pd.isna(r.M) else f"{r.M:.1f}"}</td><td class="l" style="white-space:normal;min-width:260px">{E(e.get("title",""))}</td><td>{E(e.get("date",""))}</td><td class="l">{"<a href=%s>링크</a>"%html.escape(e.get("url",""),quote=True) if e.get("url") else "—"}</td><td class="l" style="white-space:normal">{E(e.get("action",""))}</td></tr>')
    body+=f"""<h2>제외 (E5 문제 공지 — 조기상환·가속상환·상장폐지·청산·배수 변경·지수 변경(재검증 전))</h2><div class="wrap"><table style="min-width:800px"><thead><tr><th class="l">티커</th><th>구분</th><th>M-score</th><th class="l">공지 제목</th><th>날짜</th><th class="l">링크</th><th class="l">조치</th></tr></thead><tbody>{''.join(xrows) or '<tr><td colspan=7>없음</td></tr>'}</tbody></table></div>"""
    # 신규 상장(지수 확정 대기) / 발행 예정
    newp=meta.get("new_products",[])
    if newp:
        rows="".join(f'<tr><td class="l">{E(c.get("ticker") or c.get("name",""))}</td><td class="l">{E(c.get("issuer",""))}</td><td>{E(c.get("leverage",""))}</td><td class="l">{E(c.get("index",""))}</td><td>{E(c.get("found",""))}</td><td class="l">{E(c.get("status",""))}</td></tr>' for c in newp)
        body+=f'<h2>신규 상장 — 공식 지수 확정 대기 (점수 미산출)</h2><div class="wrap"><table style="min-width:700px"><thead><tr><th class="l">티커</th><th class="l">발행사</th><th>배수</th><th class="l">지수</th><th>확인일</th><th class="l">상태</th></tr></thead><tbody>{rows}</tbody></table></div>'
    pipe=meta.get("pipeline",[])
    prow="".join(f'<tr><td class="l">{E(p.get("issuer",""))}</td><td class="l">{E(p.get("name",""))}</td><td>{E(p.get("filed",""))}</td><td class="l"><a href="{html.escape(p.get("url",""),quote=True)}">공시</a></td><td class="l" style="white-space:normal;min-width:260px">{E(p.get("note",""))}</td></tr>' for p in pipe)
    body+=f'<h2>발행 예정 (공시 단계 — 티커 없음)</h2><div class="wrap"><table style="min-width:600px"><thead><tr><th class="l">발행사</th><th class="l">상품명</th><th>공시일</th><th class="l">링크</th><th class="l">비고</th></tr></thead><tbody>{prow or "<tr><td colspan=5>없음</td></tr>"}</tbody></table></div>'
    body+="""<div class="foot"><b>한계 고지</b><br>① 주식 지수·섹터 안에서 진입 시점 지표로 회복 불능을 예측하지 못함(MM-P2)<br>② 2013~2020 바구니 재생에서 고정 6종 대비 열세, 2021 이후 우세(MM-P5)<br>③ 상위권이 특정 ETN(에너지·FANG+)에 몰리는 경향(MM-P4~P6). 백테스트 재확인(MM-PROXY-FIX-20261014): 후A(허용집합 동결)에서는 판정 ①(a) 불성립 — 2022 깊이 우위는 에너지·FANG ETN 합성 이력에 의존</div>"""
    return pg("무매 M-score",body,"index.html")
# ---------- 상품 ----------
def load_products():
    p=DATA/"products.yaml"
    if not p.exists(): return None
    try:
        import yaml
        return yaml.safe_load(open(p,encoding="utf-8"))
    except Exception: return None
def fmt(v):
    if v is None or (isinstance(v,float) and np.isnan(v)): return "—"
    if isinstance(v,dict): return "<br>".join(f"<span class='sm'>{E(str(k))}</span> {fmt(x)}" for k,x in v.items())
    if isinstance(v,(list,tuple)):
        if v and all(isinstance(x,dict) for x in v): return "<br>".join(fmt(x) for x in v)
        return "<br>".join(fmt(x) for x in v)
    s=str(v)
    if re.fullmatch(r"https?://\S+",s): return f'<a href="{html.escape(s,quote=True)}">{E(s[:70])}{"…" if len(s)>70 else ""}</a>'
    return E(s)
FIELDS=[("official_index","공식 지수명"),("onex","1x (경로·β·R²·n)"),("sector_theme","섹터/테마"),("construction","구성 방식·종목 수"),("top_constituents","상위 구성"),("fee","보수 (ETN은 금융비용 포함)"),("inception","상장일"),("split_history","분할·역분할 이력"),("structural_risk","구조 리스크"),("sources","출처"),("checked","확인일")]
def build_products(uni, df, meta, p0):
    st=load_status(); prod=load_products(); prods=(prod or {}).get("products",prod or {}) if isinstance(prod,dict) else {}
    if isinstance(prods,list): prods={x.get("ticker"):x for x in prods}
    pmeta=(prod or {}).get("meta",{}) if isinstance(prod,dict) else {}
    foot=pmeta.get("footnotes",[]) if isinstance(pmeta.get("footnotes",[]),list) else [pmeta.get("footnotes")]
    cards=[]; byiss={}
    for r in uni.itertuples():
        d=df[df.ticker==r.ticker]; d=d.iloc[0] if len(d) else None
        pr=p0[p0.ticker==r.ticker]; pr=pr.iloc[0] if len(pr) else None
        px=prods.get(r.ticker,{}) or {}
        byiss.setdefault(r.issuer,[]).append(r.ticker)
        mtxt=("" if d is None or not nz(d.M) else f"M {d.M:.1f}"+(f" · {int(d['rank'])}위" if nz(d["rank"]) else " · 순위 제외")); 
        tab=(d.table if d is not None else "—")
        bd=(str(d.badges) if d is not None and isinstance(d.badges,str) and d.badges else "—")
        head=f'{E(r.ticker)} <span class="sm">{E(r.issuer)} · {E(r.type)} · {E(r.leverage)}</span> <span class="sm">{E(mtxt)}{" · ⚠ "+E(str(d.reason)) if tab=="⚠" else ""}</span>'
        note=[]
        if r.ticker in st["notes"]: note+=[str(x) for x in st["notes"][r.ticker]]
        if r.ticker in st.get("check_incomplete",{}): note.append("점검 미완: "+st["check_incomplete"][r.ticker])
        kv=[("당일 M-score·순위",E(mtxt) or "—"),("거래 가능성",E(bd))]
        if px:
            if px.get("feature_text"): kv.insert(0,("특징",f'<div class="feat">{E(str(px["feature_text"]))}</div><span class="sm">발행사 자료 기반 자동 생성</span>'))
            for key,label in FIELDS:
                if key in px: kv.append((label,fmt(px[key])))
        elif pr is not None:   # products.yaml 미적재 시 수집된 기본 정보
            kv+= [("공식 지수명",E(str(pr.index_name))),("제공사·구성·리밸런스",E(f"{pr.index_provider} · {pr.index_weighting} · {pr.index_rebalance}")),("1x 경로",E(f"{pr.onex_path} · {pr.onex_index_doc}")),("첫 일봉",E(str(pr.first_bar))),("분할 이력",E(str(pr.splits_yf)))]
        if d is not None and nz(d.beta): kv.append(("대리 품질(3배 on 1x)",E(f"β {d.beta:.2f} · R² {d.r2:.2f} (n={int(d.n_beta)}, 측정 {d.proxy_measured})")))
        if note: kv.append(("비고",E(" / ".join(note))))
        body="".join(f'<div class="k">{E(k)}</div><div>{v}</div>' for k,v in kv)
        cards.append(f'<details class="card" id="{E(r.ticker)}"><summary>{head}</summary><div class="kv">{body}</div></details>')
    srows="".join(f'<tr><td class="l">{E(i)}</td><td>{len(t)}</td><td class="l" style="white-space:normal">{" ".join(tlink(x) for x in t)}</td></tr>' for i,t in sorted(byiss.items()))
    ftxt="".join(f"<li>{E(str(x))}</li>" for x in foot if x)
    body=f"""<h1>상품 정보</h1><div class="meta">유니버스 {len(uni)}종. 1x = 발행사가 공시한 공식 지수 하나(MM-PROXY-FIX-20261014). 카드의 지수명은 발행사 문서 원문(index_specs), 특징 문장은 사실 필드만으로 자동 생성한 요약입니다(전망·평가 없음). 티커를 누르면 해당 카드가 열립니다.</div>
<h2>발행사별 요약</h2><div class="wrap"><table style="min-width:420px"><thead><tr><th class="l">발행사</th><th>종목 수</th><th class="l">티커</th></tr></thead><tbody>{srows}</tbody></table></div>
<ul class="meta">{ftxt}</ul>
<h2>티커별 카드</h2>{''.join(cards)}"""
    return pg("무매 상품",body,"products.html")
CAL_JS=r"""
(function(){
var IDX=null,TK={},cur=null,cache={};
function $(i){return document.getElementById(i)}
function pad(n){return (n<10?'0':'')+n}
function f1(x,n,sg){if(x===null||isNaN(x))return '—';var s=Math.abs(x).toLocaleString('en-US',{minimumFractionDigits:n,maximumFractionDigits:n});return (x<0?'−':(sg?'+':''))+s}
function esc(t){return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function num(v){return (v===''||v===undefined)?null:parseFloat(v)}
function parse(txt){var L=txt.split('\n'),h=L[0].match(/N=(\d+)/),cols=L[1].split(','),rows=[];
 for(var i=2;i<L.length;i++){if(!L[i])continue;var c=L[i].split(','),o={};cols.forEach(function(k,j){o[k]=c[j]});rows.push(o)}
 return {n:h?parseInt(h[1]):rows.length,rows:rows}}
function tip(r){var o=[],b=r.badges?r.badges.split(' · '):[];
 b.forEach(function(x){if(x=='근사')o.push('근사: 3배÷1x 회귀 β '+f1(num(r.beta),2)+'·R² '+f1(num(r.r2),2)+'(n='+r.n_beta+') — β 2.7~3.3 밖 또는 R²<0.85');
 else if(x=='표본부족')o.push('표본부족: 회귀 표본 n='+r.n_beta+'<60 (경로는 공식 지수, 검증 미완)');
 else if(x=='신규')o.push('신규: 3배 상장 '+r.listed_days+'거래일 <252');
 else if(x=='저유동')o.push('저유동: 20일 평균 거래대금 $'+f1(num(r.adtv),2)+'M <$'+LOW+'M');
 else if(x.indexOf('무거래')==0)o.push(x+': 최근 20봉 중 거래량 0 인 봉 '+x.slice(3)+'개')});return o.join(' / ')}
function rk(v){return v===''?'<td data-v="">—</td>':'<td data-v="'+v+'">'+v+'</td>'}
function sc(v,p,d,sg){var x=num(v)*100;return '<td class="sc" data-v="'+x.toFixed(3)+'">'+f1(x,d,sg)+' <span class="p">· '+f1(num(p),3,false)+'</span></td>'}
function row(r){var m=TK[r.ticker]||{},b=r.badges||'',dr=r.d_rank,dh='',dn='';
 if(dr==='신규')dh='신규';else if(dr!==''){var x=parseInt(dr);dn=x;dh=x>0?'<span class="up">▲'+x+'</span>':(x<0?'<span class="dn">▼'+(-x)+'</span>':'0')}
 var bq=r.beta!==''?'β '+f1(num(r.beta),2)+' · R² '+f1(num(r.r2),2)+' (n='+r.n_beta+')':'—';
 var ab=r.above200==='1'?'○':'×',c1=num(r.c1_ma200)*100;
 return '<tr'+(b?' class="g"':'')+'><td data-v="'+r.rank+'">'+r.rank+'</td><td class="l" title="'+esc((m.iss||'')+' · '+(m.typ||''))+'"><a href="products.html#'+esc(r.ticker)+'">'+esc(r.ticker)+'</a></td>'
 +'<td data-v="'+num(r.M).toFixed(4)+'"><b>'+f1(num(r.M),1)+'</b></td>'+rk(r.r5)+rk(r.r20)+rk(r.r60)+'<td class="l" data-v="'+dn+'">'+dh+'</td>'
 +'<td class="l" title="'+esc(tip(r))+'">'+(b?esc(b):'—')+'</td><td class="l" title="'+esc(m.tip||'')+'">'+esc(m.ix||r.proxy)+'</td>'
 +sc(r.sig,r.p_sig,1,false)+sc(r.rsA,r.p_rsA,1,true)+sc(r.f1b,r.p_f1b,2,true)
 +'<td data-v="'+c1.toFixed(3)+'">'+f1(c1,1,true)+'</td><td data-v="'+(ab=='○'?1:0)+'">'+ab+'</td><td data-v="'+num(r.close3)+'">'+f1(num(r.close3),2)+'</td><td data-v="'+num(r.adtv)+'">'+f1(num(r.adtv),1)+'</td><td>'+r.listed_days+'</td><td class="l">'+esc(bq)+'</td><td class="l">'+esc(r.proxy)+'</td></tr>'}
function show(d){cur=d;draw();var o=$('dayout');o.innerHTML='불러오는 중…';
 var go=function(x){var nb=x.rows.filter(function(r){return r.badges}).length;
  o.innerHTML='<div class="meta"><b>'+d+'</b> 기준 · <b>'+x.n+'종</b> · 거래 가능성 배지 '+nb+'종(회색 행)</div><div class="wrap"><table id="tcal"><thead>'+HEAD+'</thead><tbody>'+x.rows.map(row).join('')+'</tbody></table></div>'};
 if(cache[d])return go(cache[d]);
 fetch('data/scores/'+d+'.csv').then(function(r){if(!r.ok)throw 0;return r.text()}).then(function(t){cache[d]=parse(t);go(cache[d])}).catch(function(){o.innerHTML='이 날짜 파일을 읽지 못했습니다.'})}
function draw(){var y=cur_y,m=cur_m,first=new Date(y,m-1,1).getDay(),last=new Date(y,m,0).getDate(),dates=window.__dm,h='<div class="calh"><button id="cprev">‹</button> <b>'+y+'년 '+m+'월</b> <button id="cnext">›</button></div><table class="cal"><tr>'+['일','월','화','수','목','금','토'].map(function(x){return '<th>'+x+'</th>'}).join('')+'</tr><tr>';
 for(var i=0;i<first;i++)h+='<td></td>';
 for(var d=1;d<=last;d++){var k=y+'-'+pad(m)+'-'+pad(d),n=dates[k];
  h+=(n!==undefined?'<td class="on'+(k==cur?' sel':'')+'" data-d="'+k+'"><b>'+d+'</b><span>'+n+'</span></td>':'<td class="off">'+d+'</td>');
  if((first+d)%7==0&&d<last)h+='</tr><tr>'}
 $('calbox').innerHTML=h+'</tr></table>';
 $('cprev').onclick=function(){mv(-1)};$('cnext').onclick=function(){mv(1)};
 Array.prototype.forEach.call(document.querySelectorAll('td.on'),function(td){td.onclick=function(){show(td.getAttribute('data-d'))}})}
var cur_y,cur_m;
function mv(dm){var y=cur_y,m=cur_m+dm;if(m<1){m=12;y--}if(m>12){m=1;y++}
 var f=IDX.first.split('-'),l=IDX.last.split('-');if(y*12+m<(+f[0])*12+(+f[1])||y*12+m>(+l[0])*12+(+l[1]))return;cur_y=y;cur_m=m;draw()}
Promise.all([fetch('data/index.json').then(function(r){return r.json()}),fetch('data/tickers.json').then(function(r){return r.json()})]).then(function(a){
 IDX=a[0];TK=a[1];var dm={};IDX.dates.forEach(function(x){dm[x.d]=x.n});window.__dm=dm;
 var l=IDX.last.split('-');cur_y=+l[0];cur_m=+l[1];$('calinfo').innerHTML='소급 범위 '+IDX.first+' ~ '+IDX.last+' · '+IDX.count+'거래일 (날짜 칸 아래 숫자 = 그날 모집단 N종). 회색(비활성) 날짜는 데이터 없음(휴장·결측).';
 show(IDX.last)}).catch(function(){$('calinfo').innerHTML='index.json 을 읽지 못했습니다(파일을 직접 열면 브라우저가 막습니다 — 웹 주소로 여십시오).'});
})();
"""
CAL_CSS=""".calh{margin:6px 0}.calh button{font-size:16px;padding:0 10px;cursor:pointer}table.cal{border-collapse:collapse;min-width:0!important;width:100%;max-width:520px;font-size:13px}
table.cal th{position:static!important;text-align:center;cursor:default;background:#f6f8fa} table.cal td{position:static!important;text-align:center;border:1px solid #eaeef2;height:42px;padding:2px;vertical-align:top;background:#fff;min-width:0;width:14%}
table.cal td.on{cursor:pointer;background:#f4f9ff} table.cal td.on span{display:block;font-size:10px;color:#777} table.cal td.off{color:#bbb;background:#fafafa} table.cal td.sel{background:#cfe3ff}"""
def build_history(files, latest_df, anom):
    ar="".join(f'<tr><td>{E(r.date)}</td><td>{E(r.series)}</td><td class="l">{E(str(r.ticker))}</td><td class="l">{E(str(r.used_by))}</td><td>{r.ret*100:+.1f}%</td><td>{r.prev_close:,.4g}→{r.close:,.4g}</td></tr>' for r in anom.itertuples()) if anom is not None and len(anom) else ""
    head=thead("tcal").replace('<thead><tr>','').replace('</tr></thead>','')
    js=CAL_JS.replace("HEAD",json.dumps(head,ensure_ascii=False)).replace("LOW",json.dumps(LOWLIQ))
    body=f"""<h1>달력 — 날짜별 순위 (소급)</h1><div class="meta" id="calinfo">불러오는 중…</div>
<div class="meta">날짜를 누르면 그 기준일의 순위표가 아래에 표시됩니다. 소급은 매일 산출과 같은 코드·M-score v1.1 산식·매핑으로 만들었고, 그 날짜에 3배 일봉이 존재 ∧ 1x 피처 산출 가능(252봉) ∧ 이상 봉 ⚠ 아님인 종목만 모집단입니다. <b>E5(공지 제외)는 소급 적용하지 않습니다</b>(과거 공지 데이터 없음). 저유동·무거래 배지는 그 날짜 직전 20봉으로, 근사·표본부족 배지는 현재 측정값(β·R²)으로 표시합니다.</div>
<div id="calbox"></div><div id="dayout"></div>
<h2>이상 봉 목록 (전 구간, 이 봉이 속한 60일 창은 점수 집계에서 제외)</h2><div class="meta">분할·역분할 조정 후에도 1x 일간수익률 |r|&gt;25% 또는 3배 |r|&gt;75% 인 봉. 데이터 오류 의심 목록이며 실제 급변일도 포함될 수 있습니다(기준값은 data/eligibility.yaml 운영값). 파일: data/anomalies.csv</div>
<div class="wrap"><table style="min-width:620px"><thead><tr><th>날짜</th><th>계열</th><th class="l">키</th><th class="l">사용 종목</th><th>일간수익률</th><th>종가</th></tr></thead><tbody>{ar or '<tr><td colspan=6>없음</td></tr>'}</tbody></table></div>
<script>{js}</script>"""
    return pg("무매 달력",body,"history.html").replace("</style>",CAL_CSS+"</style>",1)
def write_tickers_json(uni, p0):
    pinfo={r["ticker"]:r for r in p0.to_dict("records")}; out={}
    for r in uni.itertuples():
        pi=pinfo.get(r.ticker,{}); ptip=r.proxy_tip if isinstance(r.proxy_tip,str) else ""
        out[r.ticker]=dict(ix=short_index(pi.get("index_name","")),tip=f"{pi.get('index_name','')} | 경로: {pi.get('onex_path','')} | 1x 계열 {r.proxy}"+(f" | {ptip}" if ptip else ""),iss=r.issuer,typ=r.type,proxy=r.proxy)
    (DOCS/"data").mkdir(parents=True,exist_ok=True)
    json.dump(out,open(DOCS/"data"/"tickers.json","w",encoding="utf-8"),ensure_ascii=False,separators=(",",":"))
def build_all(latest_df, uni, meta, p0, score_files):
    DOCS.mkdir(exist_ok=True)
    (DOCS/"index.html").write_text(build_index(latest_df,meta),encoding="utf-8")
    (DOCS/"products.html").write_text(build_products(uni,latest_df,meta,p0),encoding="utf-8")
    write_tickers_json(uni,p0)
    (DOCS/"history.html").write_text(build_history(score_files,latest_df,meta.get("anomalies")),encoding="utf-8")
    (DOCS/".nojekyll").write_text("")
