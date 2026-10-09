#!/usr/bin/env python3
"""일회성 수집 코드 (MM-PAGE-V2.3-20261015 §6) — 상품 특징표용 사실 필드 수집.

- 입력: ~/studies/mm_rotation_20261007/p8_proxyfix/{spec,sources}  (발행사 497K·PS 원문 저장본)
        data/products_cache/raw/  (이 세션에서 EDGAR/발행사 사이트에서 추가 수집한 원문)
- 출력: data/products_cache/facts_collected.json
- 외부 요청은 이미 raw/ 에 받아 둔 파일을 우선 사용한다(없으면 받음). EDGAR 요청은
  User-Agent "mm-rotation research (jjoychan85@gmail.com)", 초당 2회 이하.
- 못 찾은 값은 값 대신 "[부재] 사유" 문자열 — 추정 금지.
"""
import json, os, re, subprocess, sys, time
import yaml

HOME = os.path.expanduser('~')
SRC = f'{HOME}/studies/mm_rotation_20261007/p8_proxyfix'
ROOT = f'{HOME}/mm_rotation'
RAW = f'{ROOT}/data/products_cache/raw'
OUT = f'{ROOT}/data/products_cache/facts_collected.json'
UA = 'mm-rotation research (jjoychan85@gmail.com)'
CHECKED = '2026-10-09'

FAILS = []          # (url, reason)
def fail(url, reason): FAILS.append({'url': url, 'reason': reason})

def clean(t):
    for a, b in [('&nbsp;', ' '), ('&#160;', ' '), ('&ldquo;', '"'), ('&rdquo;', '"'), ('&quot;', '"'),
                 ('&times;', 'x'), ('&rsquo;', "'"), ('&ndash;', '-'), ('&trade;', 'TM'), ('&amp;', '&'),
                 ('&#174;', '®'), ('&#8194;', ' ')]:
        t = t.replace(a, b)
    return re.sub(r'\s+', ' ', t).strip()

def html_text(path):
    h = open(path, errors='ignore').read()
    h = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S)
    return clean(re.sub(r'<[^>]+>', ' ', h))

def fetch(url, out, ua=UA, sleep=0.6):
    if os.path.exists(out) and os.path.getsize(out) > 500:
        return True
    r = subprocess.run(['curl', '-sL', '-m', '90', '-A', ua, '-o', out, '-w', '%{http_code}', url],
                       capture_output=True, text=True)
    time.sleep(sleep)
    ok = r.stdout.strip() == '200' and os.path.exists(out) and os.path.getsize(out) > 500
    if not ok:
        fail(url, f'HTTP {r.stdout.strip()} / size {os.path.getsize(out) if os.path.exists(out) else 0}')
        if os.path.exists(out): os.remove(out)
    return ok

def pdf_text(path):
    import fitz
    return clean('\n'.join(p.get_text() for p in fitz.open(path)))

# ------------------------------------------------------------------ ETF: 보수(497K 수수료 표)
def parse_fee_table(txt):
    i = txt.find('Annual Fund Operating Expenses (expenses')
    if i < 0: i = txt.find('Management Fees')
    seg = txt[txt.find('Management Fees', i):]
    seg = seg[:1400]
    pairs = []
    pos = 0
    for m in re.finditer(r'(-?\s?\d+\.\d{2})\s*%', seg):
        label = seg[pos:m.start()]
        if len(label) > 150: break          # 각주 문장 진입 → 표 종료
        pos = m.end()
        pairs.append((label, float(m.group(1).replace(' ', ''))))
        if re.search(r'After (Expense Cap|Fee Waiver)|After Fee', label) or len(pairs) >= 9:
            break
    out = {}
    for label, v in pairs:
        L = re.sub(r'\(\d\)|\b\d\b[, ]*', ' ', label)
        L = re.sub(r'\s+', ' ', L).strip()
        if L.startswith('Management Fees'): out.setdefault('management', v)
        elif 'Distribution' in L: out.setdefault('distribution_12b1', v)
        elif L.startswith('Other Expenses'): out.setdefault('other', v)
        elif L.startswith('Acquired Fund'): out.setdefault('acquired_fund', v)
        elif L.startswith('Total Annual Fund Operating Expenses') and ('After' in L):
            out['total_net'] = v
        elif L.startswith('Total Annual Fund Operating Expenses'):
            out.setdefault('total_gross', v)
        elif 'Cap' in L or 'Waiver' in L or 'Reimbursement' in L:
            out.setdefault('waiver', v)
    if 'total_net' not in out and 'total_gross' in out:
        out['total_net'] = out['total_gross']       # 면제 행 없음 → 순 = 총
        out['waiver_note'] = '면제/상한 행 없음(총=순)'
    # 면제 기간 문구
    m = re.search(r'(?i:waive|reimburse).{0,420}?(through|until) ([A-Z][a-z]+ \d{1,2}, 20\d\d)', txt[txt.find('Management Fees'):][:3500])
    if m: out['waiver_until'] = m.group(2)
    return out

# ------------------------------------------------------------------ ETF: 지수 구성 서술/변경 이력
def parse_construction(txt):
    i = txt.find('Principal Investment Strateg')
    seg = txt[i:i + 4000]
    seg = re.sub(r'Summary Prospectus \d+ Direxion[^.]{0,80}?ETF ', '', seg)
    seg = re.sub(r'\d+ :: [A-Za-z0-9 ®]+ PROSHARES\.COM ', '', seg)
    j = seg.find('The Index')
    seg = seg[j:] if j >= 0 else seg
    cut = len(seg)
    for k in ['The Fund, under normal circumstances', 'Under normal circumstances', 'The Fund will concentrate',
              'The components of the Index and the percentages']:
        p = seg.find(k)
        if 0 < p < cut: cut = p
    desc = seg[:cut].strip()
    n = None
    m = re.search(r'(?:consisted of|had|comprised of|was comprised of|consists of|includes|selects) (?:approximately )?([\d,]+) (?:constituents|securities|components|stocks|companies)', desc + ' ' + seg[:cut + 400])
    if m: n = m.group(1)
    else:
        m = re.search(r'(?:includes|selects(?: the)?) (\d[\d,]*) (?:of the |smallest |companies)', desc)
        if m: n = m.group(1)
    if n is None:
        m = re.search(r'(?:performance of|designed to measure the performance of) (?:approximately )?(\d[\d,]*) (?:of the largest|small|leading|securities)', desc)
        if m: n = m.group(1)
    return desc[:1100], n

def parse_index_history(txt):
    out = []
    for m in re.finditer(r'The performance shown (?:prior to|from) [A-Z][a-z]+ \d{1,2}, 20\d\d.{0,900}?(?=If the Fund had|If Fund|Updated performance|Total Return for|After-tax|Average Annual)', txt):
        s = m.group(0).strip()
        out.append(s)
    # 중복 제거(개요/본문 중복)
    seen, res = set(), []
    for s in out:
        k = s[:80]
        if k in seen: continue
        seen.add(k); res.append(s[:900])
    return res

# ------------------------------------------------------------------ ETN: PS 조항
def ps_terms(path):
    t = open(path, errors='ignore').read()
    flat = clean(t)
    d = {}
    m = re.search(r'Initial Trade Date:\s*([A-Z][a-z]+ \d{1,2}, 20\d\d)', t)
    if m: d['initial_trade_date_text'] = m.group(1)
    m = re.search(r'Initial Issue Date:\s*([A-Z][a-z]+ \d{1,2}, 20\d\d)', t)
    if m: d['initial_issue_date_text'] = m.group(1)
    m = re.search(r'Maturity Date:\s*([A-Z][a-z]+ \d{1,2}, 20\d\d)', t)
    if m: d['maturity_text'] = m.group(1)
    m = re.search(r'Minimum Redemption\s*Amount:\s*At least ([\d,]+) (?:notes|ETNs)', t) or \
        re.search(r'"?Minimum Redemption Amount"?\s+is ([\d,]+) ETNs', flat) or \
        re.search(r'Minimum Redemption Amount[^.]{0,40}?(?:is|of) (?:at least )?([\d,]{6}) (?:ETNs|notes)', flat)
    if m: d['min_redemption'] = m.group(1)
    m = re.search(r'Redemption Fee Amount:.{0,260}?\(a\)\s*([\d.]+)%', flat)
    if m: d['redemption_fee_pct'] = m.group(1)
    d['credit_risk_senior_unsecured'] = bool(re.search(r'senior\s+unsecured\s+(?:debt\s+)?obligations', flat)) or bool(
        re.search(r'unsecured obligations of (?:the issuer|Bank of Montreal)|our unsecured obligations', flat))
    d['no_listing_obligation'] = bool(re.search(r'no obligation to maintain (?:any )?listing|not obligated to maintain the listing', flat))
    d['issuer_call_right'] = bool(re.search(r'[Cc]all [Rr]ight|Call Settlement Date', flat))
    return d

# ------------------------------------------------------------------ main
def main():
    facts = {}
    uni = [r.split(',')[0] for r in open(f'{ROOT}/data/universe.csv').read().splitlines()[1:]]
    idx = yaml.safe_load(open(f'{ROOT}/data/index_specs.yaml'))['products']
    tx = yaml.safe_load(open(f'{SRC}/spec/threex_etf.yaml'))['etfs']
    ms = yaml.safe_load(open(f'{SRC}/spec/microsectors.yaml'))
    docs = ms['documents']
    onex_top = json.load(open(f'{SRC}/data/onex_top_holdings_yf.json'))

    # ---------- ETF
    # 1x ETF 매핑(상위 보유): index_specs onex.top_holdings_proxy 없는 6종은 onex_index_doc 의 1x ETF 로 대체
    alt_1x = {'TQQQ': 'QQQ', 'UDOW': 'DIA', 'TNA': 'IWM', 'URTY': 'IWM', 'MIDU': 'IJH', 'UMDD': 'IJH'}
    # Direxion 중 팩트시트 미개통(301→minio 내부주소) 종목의 상장일 보강 출처
    old497k = {  # 2017-02-28 497K (펀드 설정 10년 미만 시점 → Since Inception 일자 표기)
        'SPXL': ('000119312517059556/d337866d497k.htm', 'old497k_SPXL_20170228.htm'),
        'TNA':  ('000119312517059524/d330843d497k.htm', 'old497k_TNA_20170228.htm'),
        'TECL': ('000119312517059546/d336832d497k.htm', 'old497k_TECL_20170228.htm'),
        'SOXL': ('000119312517059635/d350592d497k.htm', 'old497k_SOXL_20170228.htm'),
        'FAS':  ('000119312517059600/d340641d497k.htm', 'old497k_FAS_20170228.htm'),
        'DRN':  ('000119312517059537/d336356d497k.htm', 'old497k_DRN_20170228.htm'),
    }
    ncsr_name = {'HIBL': 'S&P 500® High Beta Bull 3X Shares', 'WEBL': 'Dow Jones Internet Bull 3X Shares',
                 'LABU': 'S&P Biotech Bull 3X Shares'}
    ncsr_url = 'https://www.sec.gov/Archives/edgar/data/1424958/000113322825000113/dset-efp11635_ncsr.htm'
    ncsr_txt = None
    if os.path.exists(f'{RAW}/direxion_ncsr_20250103.htm'):
        ncsr_txt = html_text(f'{RAW}/direxion_ncsr_20250103.htm')

    for t in uni:
        p = idx[t]
        if p['type'] != 'ETF': continue
        f = {'issuer_family': 'Direxion' if 'Direxion' in p['issuer'] else 'ProShares'}
        spec = tx[t]
        txt = open(f'{SRC}/sources/etf3x/txt_{t}.txt').read()
        txt = re.sub(r'\s+', ' ', txt)
        # ---- 보수
        fee = parse_fee_table(txt)
        fee['doc'] = {'url': spec['source_url'], 'form': spec['source_form'], 'doc_date': str(spec['doc_date'])}
        f['fee_497k'] = fee
        # ---- 구성
        desc, n = parse_construction(txt)
        f['construction'] = {'description': desc, 'n_constituents_text': n,
                             'doc': {'url': spec['source_url'], 'doc_date': str(spec['doc_date'])}}
        f['index_change_history'] = parse_index_history(txt)
        m = re.search(r'\(formerly the ([^)]+?)\)', txt)
        f['formerly'] = m.group(1) if m else None
        # ---- 상위 구성
        if 'top_holdings_proxy' in p['onex']:
            th = p['onex']['top_holdings_proxy']
            f['top'] = {'etf': th['etf'], 'items': th['items'][:5], 'source': th['source'], 'caveat': th['caveat'],
                        'etf_index_doc': p['onex'].get('onex_doc', {})}
        elif t in alt_1x:
            e = alt_1x[t]
            f['top'] = {'etf': e, 'items': onex_top[e][:5],
                        'source': 'yfinance funds_data.top_holdings (2026-10-09), p8_proxyfix/data/onex_top_holdings_yf.json',
                        'caveat': f'1x ETF {e} 보유 상위 — 지수 구성과 동일 가정 [미검증]',
                        'etf_index_doc': {'index_name': p['onex']['onex_index_doc']}}
        # ---- 상장일/발행사 페이지 보수
        if f['issuer_family'] == 'ProShares':
            pg = f'{RAW}/ps_{t.lower()}.html'
            url = f'https://www.proshares.com/our-etfs/leveraged-and-inverse/{t.lower()}'
            if not os.path.exists(pg): fetch(url, pg, ua='Mozilla/5.0 (mm-rotation research jjoychan85@gmail.com)')
            if os.path.exists(pg):
                s = html_text(pg)
                m1 = re.search(r'Since Inception Inception Date.*?(\d\d/\d\d/\d{4})', s)
                m2 = re.search(r'Gross Expense Ratio ([\d.]+)% Net Expense Ratio ([\d.]+)%', s)
                m3 = re.search(r'Price as of (\d\d/\d\d/\d{4})', s)
                f['inception'] = {'date': m1.group(1) if m1 else None, 'url': url, 'asof': m3.group(1) if m3 else None,
                                  'kind': 'proshares.com 제품 페이지 Inception Date'}
                if m2: f['fee_issuer_page'] = {'gross': float(m2.group(1)), 'net': float(m2.group(2)), 'url': url,
                                              'asof': m3.group(1) if m3 else None}
        else:
            pdf = f'{RAW}/dx_{t}.pdf'
            url = f'https://www.direxion.com/uploads/{t}-Fact-Sheet.pdf'
            if not os.path.exists(pdf): fetch(url, pdf, ua='Mozilla/5.0 (mm-rotation research jjoychan85@gmail.com)')
            got = False
            if os.path.exists(pdf):
                try:
                    s = pdf_text(pdf)
                    m1 = re.search(r'Inception Date (\d\d/\d\d/\d{4})', s)
                    m2 = re.search(r'Gross Expense Ratio ([\d.]+)% Net Expense Ratio\*? ([\d.]+)%', s)
                    m3 = re.search(r'(?:As of|as of)\s+(\d\d/\d\d/\d{4})', s)
                    if m1:
                        f['inception'] = {'date': m1.group(1), 'url': url, 'asof': m3.group(1) if m3 else None,
                                          'kind': 'direxion.com 팩트시트 Inception Date'}
                        got = True
                    if m2: f['fee_issuer_page'] = {'gross': float(m2.group(1)), 'net': float(m2.group(2)), 'url': url,
                                                  'asof': m3.group(1) if m3 else None}
                except Exception as e:
                    fail(url, f'PDF 파싱 실패 {e}')
            if not got and t in ncsr_name and ncsr_txt:
                m = re.search(r'Since Inception \((\d\d/\d\d/\d{4})\) Direxion Daily ' + re.escape(ncsr_name[t]), ncsr_txt)
                if m:
                    f['inception'] = {'date': m.group(1), 'url': ncsr_url, 'asof': '2024-10-31',
                                      'kind': 'N-CSR(2025-01-03 제출, FY2024-10-31) 연차보고서 Since Inception 일자'}
                    got = True
            if not got and t in old497k:
                u, fn = old497k[t]
                url2 = 'https://www.sec.gov/Archives/edgar/data/1424958/' + u
                fetch(url2, f'{RAW}/{fn}')
                if os.path.exists(f'{RAW}/{fn}'):
                    s = html_text(f'{RAW}/{fn}')
                    m = re.search(r'Since Inception \((\d{1,2}/\d{1,2}/\d{4})\)', s)
                    if m:
                        f['inception'] = {'date': m.group(1), 'url': url2, 'asof': '2017-02-28',
                                          'kind': '497K(2017-02-28) 성과표 Since Inception 일자(당시 설정 10년 미만)'}
                        got = True
            if not got:
                m = re.search(r'Since Inception in ([A-Z][a-z]+ 20\d\d)', txt)
                f['inception'] = {'date': None, 'month_only': m.group(1) if m else None, 'url': spec['source_url'],
                                  'kind': '497K PM 서술(월 단위)'}
        facts[t] = f

    # ---------- ETN
    etn_doc = {'FNGU': 'FNGB_A11', 'BULZ': 'BULZ_A28', 'BNKU': 'BNKU_A2', 'NRGU': 'NRGU_A2', 'OILU': 'OILU_A4',
               'GDXU': 'GDXU_A28', 'AIQU': 'AIQU_PS', 'SMHU': 'SMHU_PS', 'MNGU': 'MNGU_PS', 'XLCU': 'XLCU_PS',
               'XLPU': 'XLPU_PS', 'FLYU': 'FLYU_PS'}
    for t in uni:
        p = idx[t]
        if p['type'] != 'ETN': continue
        did = etn_doc[t]
        d = docs[did]
        path = f"{SRC}/{d['path']}"
        terms = ps_terms(path)
        e = ms['etns'][t]
        fe = e['financing_and_fees']
        quote = None; fee_src = None
        for k, v in fe.items():
            if k.startswith('daily_') and isinstance(v, dict):
                quote = v if quote is None else quote
        # 투자자 수수료·금융비용 인용문(문서 그대로)
        fee_items = {k: v for k, v in fe.items() if k.startswith('daily_') and isinstance(v, dict)}
        facts[t] = {'ps': {'doc_id': did, 'url': d['url'], 'doc_date': d['doc_date'], 'terms': terms},
                    'fee_items': {k: {'value': v['value'], 'quote': v['quote'], 'src': v['src']} for k, v in fee_items.items()},
                    'redemption_fee': fe.get('redemption_fee', {}).get('value'),
                    'n_constituents': p['index'].get('n_constituents'),
                    'constituents': p['index']['constituents'],
                    'constituent_changes': p['index'].get('constituent_changes')}
        if 'edgar_424B2' in e: facts[t]['edgar_424B2'] = e['edgar_424B2']
        facts[t]['web_url'] = docs['WEB_' + t]['url']
        if t == 'FNGU':
            facts[t]['ps']['addendum_note'] = '2025-06-02 부록(Addendum): 티커 FNGB→FNGU 2025-06-24 시가 기준 변경'
        if t in ('XLCU', 'XLPU'):
            # EDGAR 424B2 가 정본 → PS(pdf) 와 동일 문서
            pass

    # ---------- BMO 이벤트(EDGAR FWP 보도자료; raw/fwp_*.htm 원문으로 검증)
    def fwp(acc): return clean(re.sub(r'<[^>]+>', ' ', open(f'{RAW}/fwp_{acc}.htm', errors='ignore').read()))
    edgar = 'https://www.sec.gov/Archives/edgar/data/927971/'
    fwp_ids = {k.split(':')[0]: k.split(':')[1] for k in json.load(open(f'{RAW}/fwp_pr_index.json'))}
    def url_of(acc, fn=None): return edgar + acc.replace('-', '') + '/' + fwp_ids[acc]
    ev = {t: [] for t in facts}
    def add(t, date, text, acc, fn, must):
        s = fwp(acc)
        ok = all(re.search(x, s) for x in must)
        if not ok: fail(url_of(acc), f'이벤트 검증 문구 불일치 {must}')
        ev[t].append({'date': date, 'event': text, 'url': url_of(acc), 'verified': ok})
    add('BNKU', '2024-07-08', 'BMO, 구 BNKU(Big Banks 3X, 만기 2039-03-25) 등 4개 ETN 전량 상환(콜) 발표 — 콜결제일 2024-07-25 예정',
        '0001214659-24-012103', 'x78240fwp.htm', [r'BNKU', r'July 25, 2024', r'redeem all'])
    add('NRGU', '2024-07-08', 'BMO, 구 NRGU(Big Oil 3X) 등 4개 ETN 전량 상환(콜) 발표 — 콜결제일 2024-07-25 예정',
        '0001214659-24-012103', 'x78240fwp.htm', [r'NRGU', r'July 25, 2024', r'redeem all'])
    add('BNKU', '2025-02-19', 'BMO·REX, 신규 BNKU/BNKD/NRGU/NRGD 시리즈 론칭 공지(거래 시작 다음 날) — 현행 BNKU 는 이 신규 시리즈',
        '0001214659-25-003127', 'z_launch.htm', [r'BNKU', r'launch'])
    add('NRGU', '2025-02-19', 'BMO·REX, 신규 BNKU/BNKD/NRGU/NRGD 시리즈 론칭 공지 — 현행 NRGU 는 이 신규 시리즈',
        '0001214659-25-003127', 'z_launch.htm', [r'NRGU', r'launch'])
    add('FNGU', '2025-02-19', 'BMO, 구 FNGU(FANG+ Index 3x, 만기 2038-01-08, 2018-01 출시) 전량 상환(콜) 발표·티커를 FNGA 로 변경 예고(2025-03-03 예정)·콜결제일 2025-05-15 예정; 신규 ETN FNGB 론칭(만기 2045) — 사유: "레버리지 지원 비용 증가로 기존 수수료가 시장 환경을 반영하지 못함"',
        '0001214659-25-003129', 'z218250fwp.htm', [r'May 15, 2025', r'FNGB', r'costs associated with supporting the leverage'])
    add('FNGU', '2025-05-01', 'BMO, 구 FNGU(당시 티커 FNGA) 콜권 행사·콜 측정기간 2025-05-02 시작 공지',
        '0001214659-25-006784', 'r430250fwp.htm', [r'exercised its call right', r'May 2, 2025'])
    add('FNGU', '2025-06-02', 'BMO, 현행 ETN(구 FNGB, 만기 2045-02-17, CUSIP 063679385) 티커를 2025-06-24 개장 시점부로 FNGU 로 변경한다고 공지(2025-02-19 최초 공지의 "2025-06-02 예정"에서 일정 변경; PS 부록 2025-06-02 와 일치)',
        '0001214659-25-008686', 'o62250fwp.htm', [r'FNGB', r'FNGU', r'June 24, 2025'])
    add('FNGU', '2025-02-19', '현행 FNGU 의 전신 FNGB: Initial Trade Date 2025-02-19(거래 2025-02-20), 투자자수수료 2025-08-19 까지 연 0.35% 할인 후 연 0.95%',
        '0001214659-25-006333', 'p421258fwp.htm', [r'February 19, 2025', r'0\.35%', r'August 19, 2025'])
    add('BULZ', '2022-10-31', 'BMO, 1-for-10 역분할 시행(공지 2022-10-21)', '0001214659-22-012563', 'reverse2022.htm',
        [r'BULZ', r'1 for 10', r'October 31, 2022'])
    add('GDXU', '2022-10-31', 'BMO, 1-for-10 역분할 시행(공지 2022-10-21)', '0001214659-22-012563', 'reverse2022.htm',
        [r'GDXU', r'1 for 10', r'October 31, 2022'])
    add('BULZ', '2026-02-24', 'BMO, 10-for-1 분할(split) 시행 예정 공지(2026-02-12)', '0001214659-26-001604', 'i211263fwp.htm',
        [r'BULZ', r'10-for-1', r'February 24, 2026'])
    add('GDXU', '2025-11-21', 'BMO 계산대리인, 금융 스프레드 2.25% → 3.25% 인상(공지 2025-11-14, 시행 예정 2025-11-21)', '0001214659-25-016738', 'j1113250fwp.htm',
        [r'GDXU', r'2\.25%', r'3\.25%', r'November 21, 2025'])
    add('GDXU', '2026-02-06', 'BMO 계산대리인, 금융 스프레드 3.25% → 5.00% 인상(공지 2026-01-30, 시행 예정 2026-02-06)', '0001214659-26-001009', 'p1302610fwp.htm',
        [r'GDXU', r'3\.25%', r'5\.00%', r'February 6, 2026'])
    add('AIQU', '2026-06-01', 'BMO·REX AIQU/AIQD 론칭 공지(거래 시작 다음 날, NYSE Arca, 만기 2046-05-30)', '0001214659-26-006994', 'launch_aiqu.htm',
        [r'AIQU', r'NYSE Arca'])
    add('SMHU', '2026-08-03', 'BMO·REX SMHU/SMHD 론칭 공지(Cboe BZX, 만기 2046-07-31) — 투자자수수료 2027-01-31 까지 면제 후 연 0.70%', '0001214659-26-009465', 'launch_smhu.htm',
        [r'SMHU', r'Cboe BZX', r'January 31, 2027', r'0\.70%'])
    add('MNGU', '2026-08-26', 'BMO·REX MNGU 론칭 공지(NYSE Arca, 만기 2046-07-31) — 투자자수수료 2027-01-31 까지 면제 후 연 0.95%', '0001214659-26-010861', 'launch_mngu.htm',
        [r'MNGU', r'NYSE Arca', r'January 31, 2027', r'0\.95%'])
    add('XLCU', '2026-09-09', 'BMO·REX XLCU/XLCD/XLPU/XLPD 론칭 공지(Cboe BZX, 만기 2046-07-31)', '0001214659-26-011490', 'launch_xlc.htm',
        [r'XLCU', r'Cboe BZX'])
    add('XLPU', '2026-09-09', 'BMO·REX XLCU/XLCD/XLPU/XLPD 론칭 공지(Cboe BZX, 만기 2046-07-31)', '0001214659-26-011490', 'launch_xlc.htm',
        [r'XLPU', r'Cboe BZX'])
    add('FLYU', '2022-06-22', 'MicroSectors(REX Shares), FLYU/FLYD 론칭 보도자료(NYSE Arca 거래 시작 2022-06-22)', '0001214659-22-008212', 'launch_fly.htm',
        [r'FLYU', r'NYSE Arca'])
    for t in facts:
        if t in ev and ev[t]: facts[t]['events'] = sorted(ev[t], key=lambda x: x['date'])


    # ---------- 펀드추종지수 ETN: 구성 ETF 의 look-through 상위 보유(yfinance funds_data, 제3자 시세 데이터 — 기존 p8 파이프라인과 동일 소스)
    try:
        import yfinance as yf
        for t, e in {'SMHU': 'SMH', 'XLCU': 'XLC', 'XLPU': 'XLP'}.items():
            th = yf.Ticker(e).funds_data.top_holdings
            facts[t]['lookthrough_top'] = {
                'etf': e, 'items': [[sym, round(float(w) * 100, 2)] for sym, nm, w in th.head(5).reset_index().values.tolist()],
                'source': f'yfinance funds_data.top_holdings ({CHECKED})',
                'caveat': f'구성 ETF {e} 보유 상위 — 지수는 {e} 단일 구성(100%)이므로 look-through 로 표기 [제3자 시세 데이터·미검증]'}
    except Exception as ex:
        fail('yfinance funds_data (SMH/XLC/XLP)', str(ex))

    # ---------- GDXU: 구성 2종 ETF(GDX·GDXJ)의 look-through 상위 보유 — VanEck 팩트시트(발행사 1차, 2026-09-30 기준; p8 저장본으로 문구 검증)
    fs = {'GDX': ('gdx_factsheet.txt', 'https://www.vaneck.com/us/en/investments/gold-miners-etf-gdx-fact-sheet.pdf',
                  [('NEWMONT CORP NEM', 'NEM', 11.07), ('AGNICO EAGLE MINES LTD AEM', 'AEM', 10.99), ('BARRICK MINING CORP B', 'B', 7.92),
                   ('WHEATON PRECIOUS METALS CORP WPM', 'WPM', 5.53), ('FRANCO-NEVADA CORP FNV', 'FNV', 5.08)]),
          'GDXJ': ('gdxj_factsheet.txt', 'https://www.vaneck.com/us/en/investments/junior-gold-miners-etf-gdxj-fact-sheet.pdf',
                   [('COEUR MINING INC CDE', 'CDE', 6.64), ('ALAMOS GOLD INC AGI', 'AGI', 6.45), ('EQUINOX GOLD CORP EQX', 'EQX', 5.87),
                    ('ENDEAVOUR MINING PLC EDV LN', 'EDV LN', 5.53), ('IAMGOLD CORP IAG', 'IAG', 5.07)])}
    lts = []
    for e, (fn, url, items) in fs.items():
        txt = open(f'{SRC}/sources/etf1x/{fn}', errors='ignore').read()
        ok = all(f'{n} {w:.2f}' in txt for n, _, w in items)
        if not ok: fail(url, f'{e} 팩트시트 상위 보유 문구 검증 실패')
        lts.append({'etf': e, 'items': [[sym, w] for _, sym, w in items], 'source': f'VanEck {e} 팩트시트 Top Holdings (as of 2026-09-30, 발행사 1차) {url}',
                    'caveat': f'구성 ETF {e} 보유 상위 — 지수는 GDX 76.2%·GDXJ 23.8%(microsectors.com) 구성이므로 look-through 로 표기',
                    'verified': ok})
    facts['GDXU']['lookthrough_top'] = lts[0]
    facts['GDXU']['lookthrough_top_2'] = lts[1]

    json.dump({'checked': CHECKED, 'facts': facts, 'fails': FAILS}, open(OUT, 'w'), ensure_ascii=False, indent=1, default=str)
    print('facts', len(facts), 'fails', len(FAILS))
    for x in FAILS: print('FAIL', x)

if __name__ == '__main__':
    main()
