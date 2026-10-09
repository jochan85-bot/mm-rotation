#!/usr/bin/env python3
"""mm_products_gen.py — 유니버스 37종 상품 특징표 데이터(data/products.yaml) 생성기 (블록 MM-PAGE-V2.3-20261015 §6).

사용: python3 scripts/mm_products_gen.py [--tickers A,B] [--no-llm]
  --tickers  일부 종목만 갱신(나머지는 기존 products.yaml 값을 유지)
  --no-llm   특징(feature_text) 생성 호출 없이 캐시만 사용(캐시 없으면 "[부재] LLM 미실행")

파이프라인
  1) 입력 병합: data/universe.csv · index_specs.yaml · product_info.csv · proxy_quality.csv
                + data/products_cache/facts_collected.json (collect_facts.py 가 발행사 1차 자료에서 수집한 보수·상장일·이력)
                + data/products_cache/split_check_result.json (분할 공시 대조)
  2) data/products_manual.yaml 의 수작업 보강값이 있으면 덮어쓴다(우선)
  3) feature_text: `claude -p --model claude-sonnet-5-5 --tools ""` (도구 없음, stdin 프롬프트)로 종목별 생성.
     사실 필드만 입력. 금지 표현(FORBIDDEN) 정규식 검출 → 최대 3회 재생성 → 그래도 실패하면 "[생성 실패: 금지 표현 검출]".
     캐시 data/products_cache/<TICKER>.json — 입력 해시가 같으면 재호출하지 않는다(실패 건은 다음 실행에서 재시도).
  4) data/products.yaml 기록(안정된 키 순서). 못 찾은 값은 "[부재] 사유" 문자열(추정 금지).

쓰기 범위: data/products.yaml · data/products_cache/ 만. 라이브 트레이딩 워크스페이스·launchd·텔레그램은 건드리지 않는다.
"""
import argparse, concurrent.futures as cf, csv, datetime, hashlib, json, os, re, subprocess, sys
import yaml

ROOT = os.path.expanduser('~/mm_rotation')
DATA = f'{ROOT}/data'
CACHE = f'{DATA}/products_cache'
OUT = f'{DATA}/products.yaml'
MODEL = 'claude-sonnet-5-5'
PROMPT_VERSION = 'v1'
CHECKED = '2026-10-09'
ABS = '[부재]'

# 특징 문장 금지 표현(전망·평가·권고·추측). 검출 시 재생성.
FORBIDDEN = [r'추천', r'유망', r'전망', r'기대', r'매력', r'우수', r'좋은', r'유리', r'불리', r'매수', r'매도', r'투자하',
             r'할 것이', r'할 것으로', r'일 것', r'것으로 (보|예|판단|추정)', r'로 보인', r'보입니다', r'듯하', r'예상', r'권장',
             r'바람직', r'적합', r'가능성', r'유력', r'안정적', r'위험이 (낮|적|크)', r'리스크가 (낮|적|크)']
FORBID_RE = re.compile('|'.join(FORBIDDEN))

SCHEMA_DOC = """\
# =====================================================================================================
# products.yaml — 유니버스 37종 상품 특징표 데이터 (scripts/mm_products_gen.py 가 생성. 직접 편집 금지:
#   수작업 보강은 data/products_manual.yaml, 수집 원천은 data/products_cache/facts_collected.json)
#
# 스키마 (meta.schema 에도 동일 목록)
#   meta.footnotes[]            공통 각주 문자열 목록
#   products.<TICKER>:
#     ticker                    티커
#     issuer                    발행사 (운용사/계산대리인 병기)
#     type                      ETF | ETN
#     leverage                  배수 (일간 리셋)
#     official_index            {name, provider, return_type, name_source{url, form, doc_date}}   공식 지수명은 index_specs 그대로
#     onex                      1x 경로 {label, key, exact, series_source, extension, beta_252, r2_252, n_252, measured, verdict, note}
#     sector_theme              섹터/테마 (공식 지수명의 한국어 표기; products_manual.yaml)
#     construction              {weighting, rebalance, n_constituents, description|selection_rule+capping, source}
#     top_constituents          {basis, as_of, items[{symbol|name, weight_pct}], source, note}   (지수 구성 상위 3~5)
#     fee                       ETF: {kind, gross_pct, net_pct, management_pct, other_pct, acquired_fund_pct, waiver_pct,
#                                      waiver_until, summary, basis_doc{url, form, doc_date}, issuer_page{gross_pct, net_pct, asof, url}, note}
#                               ETN: {kind, summary, items[{text, quote, src}], redemption_fee, changes[{date, event, url}], basis_doc, note}
#     inception                 {date(YYYY-MM-DD), kind, source_url, first_trade_yahoo, note, relisting}
#     split_history             {text, corroboration[{date, event, url}], note}
#     structural_risk[]         '사실'만: {fact, source_url}
#     sources[]                 출처 URL 목록
#     checked                   확인일 YYYY-MM-DD
#     feature_text              특징 2~3줄 (claude-sonnet-5-5 생성; 금지어 검증 통과분만)
#   못 찾은 값은 "[부재] 사유" 문자열 — 추정하지 않는다.
#   생성 메타 data/products_cache/_gen_stats.json (금지어 검출·재생성 통계)
# =====================================================================================================
"""

FOOTNOTES = [
    'MicroSectors ETN 전 종목 BMO 발행 — 발행사 집중',
    'TPOR 지수 변경 이력(2022-08 ^DJT → S&P Transportation Select Industry FMC Capped): '
    'Direxion 497K(2026-02-27)에 "2022-08-01 이전 성과는 Dow Jones Transportation Average Index(야후 ^DJT) 300% 목표, '
    '2022-08-01부터 S&P Transportation Select Industry FMC Capped Index 300% 목표"로 명시 — 날짜·명칭 공시와 일치(정정 없음)',
    '발행사 자료 기반 자동 생성',
]


def iso(d):
    """m/d/yyyy · mm/dd/yyyy · 'Month D, YYYY' → YYYY-MM-DD"""
    if not d: return None
    for fmt in ('%m/%d/%Y', '%B %d, %Y'):
        try: return datetime.datetime.strptime(d.strip(), fmt).strftime('%Y-%m-%d')
        except ValueError: pass
    return d


def absent(reason): return f'{ABS} {reason}'


def pct(v): return None if v is None else round(float(v), 4)


def load_inputs():
    uni = list(csv.DictReader(open(f'{DATA}/universe.csv', encoding='utf-8')))
    info = {r['ticker']: r for r in csv.DictReader(open(f'{DATA}/product_info.csv', encoding='utf-8'))}
    pq = {r['ticker']: r for r in csv.DictReader(open(f'{DATA}/proxy_quality.csv', encoding='utf-8'))}
    idx = yaml.safe_load(open(f'{DATA}/index_specs.yaml', encoding='utf-8'))['products']
    facts = json.load(open(f'{CACHE}/facts_collected.json', encoding='utf-8'))
    split = json.load(open(f'{CACHE}/split_check_result.json', encoding='utf-8')) if os.path.exists(f'{CACHE}/split_check_result.json') else []
    manual = yaml.safe_load(open(f'{DATA}/products_manual.yaml', encoding='utf-8')) if os.path.exists(f'{DATA}/products_manual.yaml') else {}
    return uni, info, pq, idx, facts, split, manual


# ---------------------------------------------------------------------------------------- 레코드 조립
def build(t, u, info, pq, ix, fa, split_res):
    is_etf = ix['type'] == 'ETF'
    ii = ix['index']
    rec = {}
    rec['ticker'] = t
    if is_etf:
        fam = fa['issuer_family']
        adv = 'Rafferty Asset Management, LLC' if fam == 'Direxion' else 'ProShare Advisors LLC'
        rec['issuer'] = f"{u['issuer']} (운용: {adv}; 497K 명시)"
    else:
        rec['issuer'] = 'Bank of Montreal(BMO) 발행 · MicroSectors 브랜드 (구조화·마케팅 REX Shares, LLC; 계산대리인 BMO Capital Markets Corp.)'
    rec['type'] = ix['type']
    rec['leverage'] = '3x (일간 리셋)'

    # ---- 공식 지수
    ns = ii['name_source']
    if is_etf:
        nsrc = {'url': ns['url'], 'form': ns['form'], 'doc_date': str(ns['doc_date'])}
    else:
        nsrc = {'url': fa['ps']['url'], 'form': f"BMO 가격보충서 {fa['ps']['doc_id']}", 'doc_date': str(fa['ps']['doc_date'])}
    rec['official_index'] = {'name': ii['official_name'], 'provider': ii['provider'],
                             'return_type': ii['return_type'] if not str(ii['return_type']).startswith('NOT ') else absent('발행사 문서 미명시(497K: PR/TR 언급 없음)'),
                             'name_source': nsrc}

    # ---- 1x 경로
    ox = ix['onex']; q = pq[t]
    v = ox['validation']
    onex = {'label': ox['path_label'], 'key': ox['key'], 'exact': ox['exact'], 'series_source': ox['series_source'],
            'extension': ox['extension'], 'beta_252': float(q['beta']), 'r2_252': float(q['r2']), 'n_252': int(q['n']),
            'measured': q['measured'], 'verdict': v['verdict']}
    if u.get('vstate'): onex['note'] = u['vstate']
    # 교차확인: proxy_quality.csv vs index_specs.validation
    if abs(float(q['beta']) - v['beta_252']) > 0.0015 or abs(float(q['r2']) - v['r2_252']) > 0.00015:
        onex['crosscheck'] = f"proxy_quality.csv(β {q['beta']}, R² {q['r2']}) ≠ index_specs(β {v['beta_252']}, R² {v['r2_252']}) — csv 값 채택"
    rec['onex'] = onex
    rec['sector_theme'] = absent('products_manual.yaml 미등재')

    # ---- 구성 방식
    if is_etf:
        cn = fa['construction']
        n = cn['n_constituents_text']
        rec['construction'] = {
            'weighting': ii['weighting'], 'rebalance': ii['rebalance'],
            'n_constituents': (f'{n} (497K 서술)' if n else absent('497K 종목 수 미명시')),
            'description': cn['description'],
            'source': {'url': cn['doc']['url'], 'form': '497K Principal Investment Strategy', 'doc_date': cn['doc']['doc_date']}}
        w = str(ii['weighting'])
        if w.startswith('NOT STATED'):                       # index_specs 가 '497K 미명시'로 판정한 건 → 값 대신 [부재]
            rec['construction']['weighting'] = absent('497K 가중방식 미명시')
            rec['construction']['weighting_note'] = w
        elif 'NOT stated' in w or 'ambiguous' in w:          # 부분 서술(상한 규칙은 있으나 가중 기준 불명확)
            rec['construction']['weighting_note'] = '497K 가중 기준 불명확/부분 서술 — 원문 메모: ' + w
    else:
        c = {'weighting': ii['weighting'], 'rebalance': ii['rebalance'], 'n_constituents': ii.get('n_constituents') or absent('PS 미명시'),
             'selection_rule': ii.get('selection_rule') or absent('PS 별도 선정 규칙 미명시'),
             'capping': ii.get('capping') or absent('PS 미명시'),
             'source': {'url': fa['ps']['url'], 'form': f"BMO 가격보충서 {fa['ps']['doc_id']}", 'doc_date': str(fa['ps']['doc_date'])}}
        rec['construction'] = c

    # ---- 상위 구성
    if is_etf:
        top = fa.get('top')
        if top:
            items = [{'symbol': s, 'weight_pct': w} for s, w in top['items'][:5]]
            rec['top_constituents'] = {
                'basis': f"1x ETF {top['etf']} 상위 보유 (지수 구성과 동일 가정)", 'as_of': CHECKED, 'items': items,
                'source': top['source'], 'note': top['caveat'] + (f" · 1x ETF 지수 문서: {top['etf_index_doc'].get('index_name','')}" if top.get('etf_index_doc') else '')}
        else:
            rec['top_constituents'] = absent('1x ETF 상위 보유 미수집')
    else:
        cs = ix['index']['constituents']
        items = [{'name': i['name'], 'weight_pct': i['weight_pct']} for i in cs['items'][:5]]
        tc = {'basis': '지수 구성종목 (microsectors.com 상품 페이지)', 'as_of': cs['as_of'], 'items': items,
              'source': fa['web_url'] + ' (microsectors.com 상품 페이지 구성종목 표; 가중치 반올림)',
              'note': f"전체 {ii.get('n_constituents')}"}
        lts = [fa[k] for k in ('lookthrough_top', 'lookthrough_top_2') if fa.get(k)]
        if lts:
            tc['lookthrough'] = [{'etf': lt['etf'], 'items': [{'symbol': s, 'weight_pct': w} for s, w in lt['items']],
                                  'source': lt['source'], 'caveat': lt['caveat']} for lt in lts]
        rec['top_constituents'] = tc

    # ---- 보수/비용
    if is_etf:
        f7 = fa['fee_497k']; pg = fa.get('fee_issuer_page')
        gross, net = f7.get('total_gross'), f7.get('total_net')
        fee = {'kind': 'ETF 총보수(연, 497K 보수표)', 'gross_pct': gross, 'net_pct': net, 'management_pct': f7.get('management'),
               'other_pct': f7.get('other'), 'acquired_fund_pct': f7.get('acquired_fund'), 'waiver_pct': f7.get('waiver')}
        if f7.get('waiver_until'): fee['waiver_until'] = f7['waiver_until']
        fee['summary'] = (f"총 {gross:.2f}%" + (f" → 면제·상한 적용 후 {net:.2f}%" if net is not None and abs(net - gross) > 1e-9 else " (면제 없음)")
                          + f" · 운용보수 {f7.get('management'):.2f}% (497K {f7['doc']['doc_date']})")
        fee['basis_doc'] = f7['doc']
        notes = []
        if pg:
            fee['issuer_page'] = {'gross_pct': pg['gross'], 'net_pct': pg['net'], 'asof': iso(pg.get('asof')), 'url': pg['url']}
            if abs(pg['gross'] - gross) > 0.0051 or abs(pg['net'] - net) > 0.0051:
                notes.append(f"발행사 페이지({iso(pg.get('asof'))}) 총 {pg['gross']:.2f}%/순 {pg['net']:.2f}% ≠ 497K 총 {gross:.2f}%/순 {net:.2f}% — "
                             "산정 시점 차이로 추정되나 공시상 사유 미확인; 두 값 병기")
        else:
            notes.append(absent('발행사 팩트시트 미개통(direxion.com 301→내부주소)으로 현재 보수 교차확인 불가; 497K 값만 사용'))
        if f7.get('waiver_note'): notes.append(f7['waiver_note'])
        fee['note'] = ' / '.join(notes) if notes else None
        rec['fee'] = fee
    else:
        items = [{'text': it['value'], 'quote': it['quote'], 'src': it['src']} for it in fa['fee_items'].values()]
        changes = [{'date': e['date'], 'event': e['event'], 'url': e['url']} for e in fa.get('events', [])
                   if '스프레드' in e['event']]
        tm = fa['ps']['terms']
        fee = {'kind': 'ETN 비용 = 투자자 수수료(Daily Investor Fee) + 금융비용(Prime Rate + Financing Spread)',
               'summary': ' ; '.join(i['text'] for i in items),
               'items': items,
               'redemption_fee': f"{tm.get('redemption_fee_pct', '0.125')}% (조기상환 시, 면제 가능)",
               'changes': changes,
               'basis_doc': {'url': fa['ps']['url'], 'form': f"BMO 가격보충서 {fa['ps']['doc_id']}", 'doc_date': str(fa['ps']['doc_date'])}}
        nt = ['스프레드는 PS 상 계산대리인이 상한 내에서 조정 가능 — PS 일자 이후 변경분은 EDGAR FWP 보도자료로만 확인(2022-01~2026-10-09 FWP 전문검색에서 인상 공시는 GDXU 2건만 확인, 검색 누락 가능)']
        if t in ('OILU', 'FLYU'):
            nt.append('최신 수정 PS 미확보 — 상품 페이지가 연결한 문서가 ' + str(fa['ps']['doc_date']) + ' 기준(요율이 이후 바뀌었는지 이 문서로는 확인 불가)')
        fee['note'] = ' / '.join(nt)
        rec['fee'] = fee

    # ---- 상장일
    fy = info[t]['first_bar']
    if is_etf:
        inc = fa['inception']
        d = iso(inc.get('date'))
        if d:
            rec['inception'] = {'date': d, 'kind': inc['kind'], 'source_url': inc['url'], 'first_trade_yahoo': fy,
                                'note': f"발행사 설정일과 Yahoo 첫 봉({fy})의 차이는 설정일↔거래 개시일 차이 가능" if d != fy else None}
        else:
            rec['inception'] = {'date': absent('발행사 일 단위 일자 미확보'), 'month_only': inc.get('month_only'), 'first_trade_yahoo': fy,
                                'source_url': inc['url'], 'kind': inc['kind']}
        # 구 지수 → 현 지수 전환 등은 structural_risk
    else:
        tm = fa['ps']['terms']
        itd = iso(tm.get('initial_trade_date_text'))
        rec['inception'] = {'date': itd, 'kind': 'PS 의 Initial Trade Date (발행일 기준 최초 거래일 확정)', 'source_url': fa['ps']['url'],
                            'first_trade_yahoo': fy, 'maturity': iso(tm.get('maturity_text')), 'note': None}
        rel = None
        if t == 'FNGU':
            rel = ("현행 FNGU 는 2025-02-19 신규 발행(구 티커 FNGB, 만기 2045-02-17)이며 2025-06-24 부로 FNGU 티커 사용. "
                   "구 FNGU(만기 2038-01-08, 2018-01 출시)는 BMO 가 2025-05 콜(상환) — 아래 structural_risk 참조")
        elif t in ('BNKU', 'NRGU'):
            rel = ("현행 시리즈는 2025-02-19 신규 발행(만기 2045-02-17). 구 시리즈는 BMO 가 2024-07-25 콜결제 예정으로 전량 상환 공지(2024-07-08)")
        if rel: rec['inception']['relisting'] = rel
        if t in ('XLCU', 'XLPU'):
            rec['inception']['note'] = ('PS Initial Trade Date 2026-09-09, 보도자료상 거래 개시 "다음날"(2026-09-10) vs Yahoo 첫 봉 2026-09-11 — '
                                        '1일 차이 미해소(Yahoo 봉 누락 또는 개시일 차이; 발행사 문서 기준일 우선)')

    # ---- 분할·역분할
    txt = info[t]['splits_yf']
    sp = {'text': txt if txt and txt != '없음' else '없음 (Yahoo splits)', 'basis': 'Yahoo Finance splits (product_info.csv splits_yf; 제3자 시세 데이터)'}
    corr = [{'date': r['date'], 'event': f"{'역분할' if r['kind']=='reverse' else '분할'} 공시 대조: {r['found']['form']} {r['found']['filed']} 제출", 'url': r['found']['url']}
            for r in split_res if r['ticker'] == t and r['found']]
    for e in fa.get('events', []):
        if '분할' in e['event']:
            corr.append({'date': e['date'], 'event': e['event'], 'url': e['url']})
    sp['corroboration'] = corr
    old_sp = [x.strip() for x in (txt or '').split(';') if x.strip() and x.strip() != '없음']
    sp['note'] = (f'Yahoo 분할 {len(old_sp)}건 중 발행사 공시로 대조된 것 {len(corr)}건; 나머지는 공시 미대조(Yahoo 값 그대로)'
                  if old_sp else ('Yahoo 기록 없음' + ('; 구 시리즈 이력 별도(structural_risk)' if t in ('FNGU', 'BNKU', 'NRGU') else '')))
    rec['split_history'] = sp

    # ---- 구조 리스크(사실만)
    sr = []
    if is_etf:
        src = fa['construction']['doc']['url']
        if fa['issuer_family'] == 'Direxion':
            sr.append({'fact': '497K 명시: 1일보다 길거나 짧게 보유한 투자자의 수익률을 지수 성과의 300%로 간주해서는 안 되며(should not be expected to be 300%), 1일을 넘는 기간의 수익률은 일별 수익률을 복리로 곱한 결과라 지수의 300%와 크게 다를 수 있다', 'source_url': src})
        else:
            sr.append({'fact': '497K 명시(Compounding/Volatility Risk): 1일을 넘는 보유기간의 펀드 성과는 일간 목표(Daily Target)와 다를 수 있으며 그 차이가 클 수 있다', 'source_url': src})
        for h in fa['index_change_history']:
            sr.append({'fact': '지수(추종 목표) 변경 이력 — ' + h, 'source_url': src})
        if fa.get('formerly'):
            sr.append({'fact': f"펀드명 표기 변경: 497K(2026-02-27)는 '(formerly the {fa['formerly']})'로 표기 — 상품명에서 'Shares'→'ETF'", 'source_url': src})
        f7 = fa['fee_497k']
        if f7.get('waiver') not in (None, 0) and f7.get('waiver_until'):
            sr.append({'fact': f"운용보수 면제/비용상한 계약 기한 {f7['waiver_until']} (497K 보수표 각주)" + (" — 497K: 이사회 동의로 종료·변경될 수 있음" if fa['issuer_family'] == 'Direxion' else " — 497K: 이사회 승인 없이 기한 전 종료 불가, 면제분은 5년 내 환수 가능"), 'source_url': src})
    else:
        tm = fa['ps']['terms']; psu = fa['ps']['url']
        sr.append({'fact': 'BMO 발행 선순위 무담보 채무 — 발행사 신용위험에 노출(PS: senior unsecured debt obligations of Bank of Montreal; 예금자보호·FDIC 대상 아님)' if tm.get('credit_risk_senior_unsecured') else absent('PS 신용위험 문구 미확인'), 'source_url': psu})
        sr.append({'fact': f"만기 {iso(tm.get('maturity_text'))}; 발행사 콜권(call right) {'있음' if tm.get('issuer_call_right') else absent('PS 미확인')}; 투자자 조기상환은 최소 {tm.get('min_redemption', absent('PS 미확인'))} ETN 단위(발행사가 면제 가능)이고 상환수수료 {tm.get('redemption_fee_pct', absent('PS 미확인'))}%", 'source_url': psu})
        if tm.get('no_listing_obligation'):
            sr.append({'fact': 'BMO 는 상장 유지 의무가 없으며 사유 불문 상장 폐지를 결정할 수 있음(PS)', 'source_url': psu})
        for e in fa.get('events', []):
            if re.search(r'상환|콜|티커|스프레드|분할', e['event']):
                sr.append({'fact': f"{e['date']} — {e['event']}", 'source_url': e['url']})
    rec['structural_risk'] = sr

    # ---- 출처
    srcs = []
    def add(u):
        if u and u not in srcs and str(u).startswith('http'): srcs.append(u)
    add(nsrc['url']); add(rec['construction']['source']['url'] if isinstance(rec['construction'].get('source'), dict) else None)
    add(rec['fee']['basis_doc']['url']); add(rec['inception'].get('source_url'))
    if is_etf and fa.get('fee_issuer_page'): add(fa['fee_issuer_page']['url'])
    for s in sr: add(s.get('source_url'))
    for c in sp['corroboration']: add(c['url'])
    for e in fa.get('events', []): add(e['url'])
    if not is_etf:
        add(fa['web_url'])
        for x in rec['top_constituents'].get('lookthrough', []):
            m = re.search(r'https?://\S+', x['source'])
            if m: add(m.group(0))
    rec['sources'] = srcs
    rec['checked'] = CHECKED
    rec['feature_text'] = absent('미생성')
    return rec


# ---------------------------------------------------------------------------------------- 특징 생성
def feature_input(rec):
    """feature_text 입력 = 사실 필드만(출처 URL·인용문·스키마 메타 제외)"""
    def items(tc):
        if not isinstance(tc, dict): return str(tc)
        its = tc.get('items', [])
        return [(i.get('symbol') or i.get('name')) + ' ' + str(i['weight_pct']) + '%' for i in its]
    r = rec
    d = {'티커': r['ticker'], '유형': r['type'], '발행사': r['issuer'], '배수': r['leverage'],
         '공식 지수명': r['official_index']['name'], '지수 제공사': r['official_index']['provider'],
         '섹터/테마': r['sector_theme'],
         '지수 가중방식': r['construction']['weighting'], '리밸런스': r['construction']['rebalance'],
         '지수 종목 수': r['construction'].get('n_constituents'),
         '상위 구성': items(r['top_constituents']) if isinstance(r['top_constituents'], dict) else r['top_constituents'],
         '상위 구성 기준': r['top_constituents'].get('basis') if isinstance(r['top_constituents'], dict) else None,
         '비용 요약': r['fee']['summary'],
         ('ETN 최초 거래일(PS Initial Trade Date; 상장일과 다를 수 있음)' if r['type']=='ETN' else '상장일(ISO)'): r['inception'].get('date'), '분할 이력(Yahoo)': r['split_history']['text'],
         '구조 사실': [s['fact'] for s in r['structural_risk']]}
    if r['construction'].get('selection_rule'): d['종목 선정 규칙'] = r['construction']['selection_rule']
    lt = r['top_constituents'].get('lookthrough') if isinstance(r['top_constituents'], dict) else None
    if lt: d['구성 ETF 상위 보유'] = {x['etf']: [i['symbol'] + ' ' + str(i['weight_pct']) + '%' for i in x['items']] for x in lt}
    return d


PROMPT = """아래 [사실]은 ETF/ETN 한 종목의 발행사 공시 기반 사실 필드다. 이 사실만으로 한국어 '특징'을 2~3문장(줄) 작성하라.

규칙:
- [사실]에 없는 내용은 절대 쓰지 말 것(추측·일반 상식·외부 지식·수치 계산 금지). 숫자·날짜·이름은 입력 그대로.
- 전망·평가·권고·추측 표현 금지. 사용 금지 어휘: 추천, 유망, 전망, 기대, 매력, 우수, 좋은, 유리, 불리, 매수, 매도, 투자하, 예상, 권장, 적합, 가능성,
  '~할 것이다', '~로 보인다', '~일 것' 류. 비용·구조는 '~이다/~한다/~로 명시돼 있다' 식의 서술문으로만 쓴다.
- 문장 1: 무엇을 추종하는 어떤 상품인지(발행사·유형·지수·섹터). 문장 2: 지수 구성 방식과 상위 구성(기준 명시). 문장 3(선택): 비용 또는 구조상 사실 중 가장 중요한 한 가지(예: ETN 이면 발행사 신용위험·콜/상환 이력, ETF 면 지수 변경·보수 면제 기한).
- 불릿·마크다운·머리말 없이 문장만 줄바꿈으로 구분해 출력.

[사실]
{facts}
"""


def call_llm(prompt):
    cmd = ['claude', '-p', '--model', MODEL, '--tools', '', '--no-session-persistence', '--disable-slash-commands', '--strict-mcp-config',
           '--system-prompt', '너는 공시 사실만으로 중립적 한국어 설명문을 쓰는 편집자다. 전망·평가·권고는 쓰지 않는다.']
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=ROOT, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f'claude -p 실패 rc={r.returncode}: {r.stderr[:200]}')
    return r.stdout.strip()


def violations(text):
    return sorted(set(m.group(0) for m in FORBID_RE.finditer(text)))


def gen_feature(rec, use_llm, stats):
    t = rec['ticker']
    fin = feature_input(rec)
    h = hashlib.sha256((PROMPT_VERSION + MODEL + json.dumps(fin, ensure_ascii=False, sort_keys=True)).encode()).hexdigest()[:16]
    cpath = f'{CACHE}/{t}.json'
    cache = json.load(open(cpath, encoding='utf-8')) if os.path.exists(cpath) else None
    if cache and cache.get('input_hash') == h and cache.get('status') == 'ok' and not violations(cache['feature_text']):
        stats['cache_hit'] += 1
        return cache['feature_text']
    if not use_llm:
        stats['skipped_no_llm'] += 1
        return cache['feature_text'] if cache and cache.get('status') == 'ok' and cache.get('input_hash') == h else absent('LLM 미실행(--no-llm) 또는 캐시 없음')
    prompt = PROMPT.format(facts=json.dumps(fin, ensure_ascii=False, indent=1))
    attempts = []
    text = None
    for n in range(1, 5):                # 최초 1회 + 재생성 최대 3회
        try:
            out = call_llm(prompt)
        except Exception as e:
            attempts.append({'n': n, 'error': str(e)[:200]}); stats['llm_errors'] += 1; continue
        stats['calls'] += 1
        v = violations(out)
        attempts.append({'n': n, 'text': out, 'violations': v})
        if n > 1: stats['regens'] += 1
        if v:
            stats['violation_attempts'] += 1
            for x in v: stats['violation_terms'][x] = stats['violation_terms'].get(x, 0) + 1
            continue
        text = out; break
    status = 'ok' if text else 'fail'
    final = text if text else '[생성 실패: 금지 표현 검출]'
    if status == 'fail':
        stats['failed'].append(t)
    stats['first_try_violation'] += 1 if attempts and attempts[0].get('violations') else 0
    json.dump({'ticker': t, 'input_hash': h, 'model': MODEL, 'prompt_version': PROMPT_VERSION, 'status': status,
               'generated': datetime.datetime.now().isoformat(timespec='seconds'), 'feature_input': fin,
               'feature_text': final, 'attempts': attempts}, open(cpath, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return final


def check_manual_fee(rec, fa):
    """수작업 ETN 비용 요약의 % 수치가 PS 인용문·FWP 이벤트에 실재하는지 대조(없으면 경고 + 요약 앞에 표시)"""
    if rec['type'] != 'ETN': return
    corpus = ' '.join([it['quote'] + ' ' + it['value'] for it in fa['fee_items'].values()] + [e['event'] for e in fa.get('events', [])])
    miss = [x for x in set(re.findall(r'\d+\.\d+%', rec['fee']['summary'])) if x not in corpus]
    if miss:
        print(f"WARN {rec['ticker']}: 수작업 비용 요약의 수치 {miss} 가 근거 문서·이벤트에 없음", file=sys.stderr)
        rec['fee']['note'] = (rec['fee'].get('note') or '') + f' / [검증 경고] 요약 수치 {miss} 근거 미확인'


# ---------------------------------------------------------------------------------------- 병합·기록
def deep_merge(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        for k, v in b.items(): a[k] = deep_merge(a.get(k), v) if k in a else v
        return a
    return b


def dump_yaml(obj):
    class D(yaml.SafeDumper): pass
    D.add_representer(type(None), lambda d, _: d.represent_scalar('tag:yaml.org,2002:null', 'null'))
    def rep_str(d, s):
        style = '|' if '\n' in s else None
        return d.represent_scalar('tag:yaml.org,2002:str', s, style=style)
    D.add_representer(str, rep_str)
    return yaml.dump(obj, Dumper=D, allow_unicode=True, sort_keys=False, width=140, default_flow_style=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tickers', default='')
    ap.add_argument('--no-llm', action='store_true')
    a = ap.parse_args()
    uni, info, pq, idx, facts, split_res, manual = load_inputs()
    want = [x.strip().upper() for x in a.tickers.split(',') if x.strip()]
    order = [r['ticker'] for r in uni]
    prev = {}
    if os.path.exists(OUT):
        prev = (yaml.safe_load(open(OUT, encoding='utf-8')) or {}).get('products', {})
    stats = {'calls': 0, 'regens': 0, 'cache_hit': 0, 'skipped_no_llm': 0, 'llm_errors': 0, 'violation_attempts': 0,
             'first_try_violation': 0, 'violation_terms': {}, 'failed': []}
    recs = {}
    todo = []
    for r in uni:
        t = r['ticker']
        if want and t not in want and t in prev:
            recs[t] = prev[t]; continue
        rec = build(t, r, info, pq, idx[t], facts['facts'][t], split_res)
        if t in manual: rec = deep_merge(rec, manual[t])
        check_manual_fee(rec, facts['facts'][t])
        recs[t] = rec; todo.append(t)
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(gen_feature, recs[t], not a.no_llm, stats): t for t in todo}
        for f in cf.as_completed(futs):
            recs[futs[f]]['feature_text'] = f.result()
    # 수작업 보강이 feature_text 를 직접 지정한 경우 우선
    for t in todo:
        if t in manual and 'feature_text' in manual[t]: recs[t]['feature_text'] = manual[t]['feature_text']
    doc = {'meta': {'generated': datetime.datetime.now().isoformat(timespec='seconds'), 'checked': CHECKED, 'block': 'MM-PAGE-V2.3-20261015 §6',
                    'count': len(recs), 'feature_model': MODEL,
                    'schema': ['ticker', 'issuer', 'type', 'leverage', 'official_index', 'onex', 'sector_theme', 'construction', 'top_constituents',
                               'fee', 'inception', 'split_history', 'structural_risk', 'sources', 'checked', 'feature_text'],
                    'footnotes': FOOTNOTES},
           'products': {t: recs[t] for t in order if t in recs}}
    open(OUT, 'w', encoding='utf-8').write(SCHEMA_DOC + dump_yaml(doc))
    stats['updated'] = todo
    stats['run_at'] = datetime.datetime.now().isoformat(timespec='seconds')
    sp = f'{CACHE}/_gen_stats.json'
    hist = json.load(open(sp, encoding='utf-8')) if os.path.exists(sp) else {'runs': []}
    hist['runs'].append(stats)          # 실행 이력 누적(금지어 검출·재생성 통계)
    json.dump(hist, open(sp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in stats.items() if k != 'updated'}, ensure_ascii=False))
    print('wrote', OUT, len(recs))


if __name__ == '__main__':
    main()
