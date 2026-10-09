#!/usr/bin/env python3
"""종목 페이지 '구성' 표 데이터 — data/holdings.json (MM-PAGE-V3.1 §7 → V3.2 §3·§4·§5·§6). 표시층 전용, 점수·판정 무관.

■ 경로
- ETF(24종): products.yaml 의 top_constituents.basis "1x ETF X" 를 파싱해, 1x ETF X 의 **발행사 보유 파일 전체**를 받는다.
    SSGA(xlsx) · iShares(csv) · VanEck(xlsx) · First Trust(html 표) · Invesco(JSON API).
    Invesco(QQQ·SPHB)는 dng-api.invesco.com 보유 JSON(캐시 우회 r= 필요). 실패(406/500·30건 미만)하면 SEC N-PORT(발행사 규제 제출 보유, 분기 말 기준)로 대체하고
    티커는 OpenFIGI(CUSIP/ISIN→티커)로 붙인다. 기준일(as_of)이 곧 신선도다.
- ETN(12종): data/index_specs.yaml 의 지수 구성표(microsectors.com 상품 페이지). 지수 파일에는 티커가 없어 회사명→티커를 아래 순서로 찾는다:
    ① 이번에 받은 발행사 보유 파일 전체의 정규화 회사명 일치(ts=issuer_file) ② 지수 문서가 티커를 명시한 경우(INDEX_FILE_TICKERS, ts=index_file)
    ③ yfinance Search(ts=yfinance) ④ 모르면 t=None(ts=none).
- §5 구성 누락: SMHU·XLCU·XLPU 는 지수가 1개 펀드(SMH·XLC·XLP)를 100% 추종 → 그 펀드의 발행사 보유 전체를 구성으로 쓴다(basis "SMH 보유(지수가 이 펀드를 추종)").
    GDXU 는 지수가 GDX·GDXJ 2개 펀드(76.2/23.8)로 구성 → 두 펀드의 발행사 보유를 지수 비중으로 합성(look-through)한다.

■ 제외 규칙(items 에서 빼고 total 에도 세지 않음) — 주식(보통주·ADR·REIT 등 증권)만 구성 종목이다:
    현금(US DOLLAR·외화 현금·CASH)·머니마켓(MONEY MARKET)·선물/스왑/기타 파생·담보·CONTRA(소송합의/CVR 상쇄 줄)·티커 없는 줄.
    SSGA: 티커 '-'/빈칸 또는 이름이 NONSEC 패턴 / iShares: Asset Class != Equity / VanEck: Asset Class != Stock
    First Trust: 티커 '$USD' 등 '$' 시작·빈칸 / N-PORT: assetCat != EC(주식-보통주).
- 광역(구성 100종 초과)은 items 에 비중 상위 100 까지만 저장하고 total 에 전체 N 을 기록한다.
- 실패(네트워크·형식 변경·0건)는 직전 holdings.json 의 그 종목 값을 그대로 두고 stale:true 만 붙인다(as_of 는 직전 값 그대로).

■ 링크(§4): 네이버 증권 해외종목 코드 nv 는 api.stock.naver.com/stock/{코드}/basic 이 200 이면서 종목명이 일치할 때만 저장한다(실측: 존재하지 않는 코드는 409).
    실측 규칙: 나스닥 {T}.O · NYSE 는 {T} 또는 {T}.K 중 종목마다 하나 · AMEX/Arca ETF 는 {T}. 점 티커(BRK.B)는 {BRK}{b} 처럼 클래스 문자를 소문자로 붙인다. 결과는 .local/naver_cache.json 에 캐시.
사용: python3 scripts/mm_holdings.py [--dry]   (네트워크: 발행사 사이트·SEC·OpenFIGI·네이버·yfinance, 최초 약 13분(고유 티커 약 1,100개 × 거래소·네이버 조회), 이후 캐시로 약 2분)"""
import csv, html as _html, http.cookiejar, io, json, os, re, sys, time, datetime, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOCAL = ROOT / ".local"
TOP_N = 100                                     # items 상한
SLEEP = 0.25                                    # 외부 호출 간 최소 간격(초)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
SEC_UA = "mm-rotation research (jjoychan85@gmail.com)"

# ---- 발행사 보유 파일 -------------------------------------------------------------------------------------------------
SSGA = ["SPY", "DIA", "XLK", "XLV", "XPH", "XBI", "XLF", "KRE", "XLI", "XRT", "XLY", "XLRE", "XLU", "XLC", "XLP"]
ISHARES = {"IWM": (239710, "ishares-russell-2000-etf"), "IJH": (239763, "ishares-core-sp-midcap-etf"), "SOXX": (239705, "ishares-phlx-semiconductor-etf"),
           "ITA": (239502, "ishares-us-aerospace-defense-etf"), "IYT": (239501, "ishares-transportation-average-etf"), "ITB": (239512, "ishares-us-home-construction-etf")}
VANECK = {"SMH": "https://www.vaneck.com/us/en/etf/equity/smh/holdings/download/xlsx/", "GDX": "https://www.vaneck.com/us/en/etf/equity/gdx/holdings/download/xlsx/",
          "GDXJ": "https://www.vaneck.com/us/en/etf/equity/gdxj/holdings/download/xlsx/"}
FIRSTTRUST = {"FDN": "https://www.ftportfolios.com/Retail/Etf/EtfHoldings.aspx?Ticker=FDN"}
INVESCO = {"QQQ": ("QQQ", "ticker"), "SPHB": ("46138E370", "cusip")}                       # 종목: (id, idType) — SPHB 는 ticker 로 조회하면 HTTP 500, CUSIP 으로 조회해야 한다(실측)
NPORT_SERIES = {"QQQ": (1067839, "S000101292"), "SPHB": (1378872, "S000030963")}     # (CIK, seriesId) — SEC company_tickers_mf.json 로 확인한 값
EXTRA_ETFS = ["SMH", "XLC", "XLP", "GDX", "GDXJ"]                                      # ETN 대체 경로(§5)에 쓰는 1x 펀드 (SPY 등은 products.yaml 에서 파싱)
FUND_ETN = {"SMHU": "SMH", "XLCU": "XLC", "XLPU": "XLP"}                                # 지수가 펀드 1개를 100% 추종
LOOKTHROUGH_ETN = {"GDXU": ("GDX", "GDXJ")}                                             # 지수가 펀드 2개로 구성 → 지수 비중으로 합성
MICROSECTORS_PAGE = {"FNGU": "fang", "BULZ": "fang-innovation", "BNKU": "big-banks", "NRGU": "big-oil", "OILU": "oil-gas-exp-prod", "GDXU": "goldminers",
                     "AIQU": "ai", "SMHU": "semis", "MNGU": "mangos", "XLCU": "communications", "XLPU": "consumer-staples", "FLYU": "travel"}
# 지수 문서가 티커를 직접 적은 회사명(지수 구성표에는 티커가 없다): microsectors.com/mangos/ 방법론 본문 "Space Exploration Technologies Class A (SPCX)"
INDEX_FILE_TICKERS = {"SPACE EXPLORATION TECHN-CL A": "SPCX"}

NONSEC = re.compile(r"\b(CASH|MONEY MARKET|US DOLLAR|CONTRA|FUTURES?|SWAPS?|OTHER ASSETS|NET OTHER|COLLATERAL|TREASURY BILL|REPO)\b|^SSI US GOV|^\$", re.I)


def today():
    return datetime.date.today().isoformat()


def _sleep():
    time.sleep(SLEEP)


# ---- HTTP -------------------------------------------------------------------------------------------------------------
_OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def http_get(url, headers=None, data=None, retries=2, timeout=60):
    """쿠키 유지 GET/POST(VanEck 쿠키 리다이렉트 대응). 5xx·네트워크 오류만 재시도, 4xx 는 바로 올린다."""
    h = {"User-Agent": UA, "Accept": "*/*"}
    h.update(headers or {})
    last = None
    for i in range(retries + 1):
        try:
            with _OPENER.open(urllib.request.Request(url, data=data, headers=h), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code < 500: raise
        except Exception as e:
            last = e
        time.sleep(1.5 * (i + 1))
    raise last


# ---- 파서(네트워크 없음, 단위 테스트 대상) ------------------------------------------------------------------------------------
def norm_ticker(t):
    """발행사 티커 표기 정리: 'MOG A'·'BRK/B'·'BRK-B' → 'MOG.A'·'BRK.B'. 미국 상장 형식(영문 1~5자 [+클래스 1자])이 아니면 None(예: VanEck 해외 'NST AU')."""
    if t is None: return None
    s = str(t).strip().upper().replace("*", "")
    if not s or s in ("-", "--") or s.startswith("$"): return None
    s = re.sub(r"[ /\-]", ".", s)
    return s if re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", s) else None


def _pct(x):
    if x is None: return None
    s = str(x).replace("%", "").replace(",", "").strip()
    try: return float(s)
    except ValueError: return None


def parse_ssga(xlsx):
    """SSGA 일별 보유 xlsx → (as_of, [ {n,t,w} ]). 헤더 'Name' 줄 이후 첫 빈 줄까지. 티커 '-'·현금/머니마켓/CONTRA 줄은 제외."""
    import openpyxl
    rows = list(openpyxl.load_workbook(io.BytesIO(xlsx), read_only=True).active.iter_rows(values_only=True))
    as_of = None
    for r in rows[:6]:
        if r[0] and str(r[0]).startswith("Holdings") and r[1]:
            m = re.search(r"(\d{2}-[A-Za-z]{3}-\d{4})", str(r[1]))
            if m: as_of = datetime.datetime.strptime(m.group(1), "%d-%b-%Y").date().isoformat()
    hdr = next(i for i, r in enumerate(rows) if r[0] == "Name")
    out = []
    for r in rows[hdr + 1:]:
        if r[0] is None: break
        t = norm_ticker(r[1]) if r[1] not in (None, "-") else None
        w = _pct(r[4])
        if w is None or t is None or NONSEC.search(str(r[0])): continue
        out.append({"n": str(r[0]).strip(), "t": t, "w": w})
    return as_of, out


def parse_ishares(text):
    """iShares latest-holdings.csv → (as_of, [ {n,t,w,exh} ]). 두 가지 열 형식: 'Weight (%)'(IWM·SOXX·ITA·IYT·ITB) / 'Type'+'Market Weight'(IJH — SWAP 줄이 Asset Class=Equity 로 섞여 있어 Type=EQUITY 만).
    Asset Class == Equity 만(현금·선물·머니마켓·담보 제외), 평가액 0(스왑) 제외. exh=발행사 파일의 Exchange 열."""
    m = re.search(r'Fund Holdings as of,"?([A-Za-z]{3} \d{1,2}, \d{4})', text)
    as_of = datetime.datetime.strptime(m.group(1), "%b %d, %Y").date().isoformat() if m else None
    lines = text.splitlines()
    hi = next(i for i, l in enumerate(lines) if l.startswith("Ticker,Name"))
    out = []
    for r in csv.DictReader(lines[hi:]):
        if not r.get("Ticker") or r.get("Asset Class") != "Equity": continue
        if "Type" in r and r["Type"] != "EQUITY": continue
        if (_pct(r.get("Market Value")) or 0) == 0: continue
        w = _pct(r.get("Weight (%)") if "Weight (%)" in r else r.get("Market Weight"))
        t = norm_ticker(r["Ticker"])
        if w is None or t is None: continue
        out.append({"n": r["Name"].strip(), "t": t, "w": w, "exh": (r.get("Exchange") or "").strip()})
    return as_of, out


def parse_vaneck(xlsx):
    """VanEck 일별 보유 xlsx → (as_of, [ {n,t,w} ]). Asset Class == Stock 만. 해외 상장('NST AU' 형식)은 t=None 으로 두고 회사명만 쓴다."""
    import openpyxl
    rows = list(openpyxl.load_workbook(io.BytesIO(xlsx), read_only=True).active.iter_rows(values_only=True))
    m = re.search(r"(\d{2}/\d{2}/\d{4})", str(rows[0][0]))
    as_of = datetime.datetime.strptime(m.group(1), "%m/%d/%Y").date().isoformat() if m else None
    hdr = next(i for i, r in enumerate(rows) if r[0] == "Number")
    out = []
    for r in rows[hdr + 1:]:
        if r[0] is None or not isinstance(r[0], (int, float)) or str(r[5]).strip() != "Stock": continue
        w = _pct(r[8])
        if w is None: continue
        out.append({"n": str(r[2]).strip(), "t": norm_ticker(r[1]), "w": w})
    return as_of, out


def parse_firsttrust(h):
    """First Trust EtfHoldings.aspx 의 표 → (as_of, [ {n,t,w} ]). 7열(이름·티커·CUSIP·분류·수량·평가액·비중) 줄만; 티커가 '$USD' 등 '$' 이거나 빈칸이면 현금."""
    m = re.search(r"Holdings of the Fund as of (\d{1,2}/\d{1,2}/\d{4})", h)
    as_of = datetime.datetime.strptime(m.group(1), "%m/%d/%Y").date().isoformat() if m else None
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", h[h.find("Holdings of the Fund"):], re.S):
        c = [_html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
        if len(c) != 7 or c[0] == "Security Name": continue
        t, w = norm_ticker(c[1]), _pct(c[6])
        if t is None or w is None or NONSEC.search(c[0]): continue
        out.append({"n": c[0], "t": t, "w": w})
    return as_of, out


def parse_invesco_json(obj):
    """Invesco dng-api holdings JSON → (as_of, [ {n,t,w} ]). 필드: effectiveDate · holdings[].{ticker, issuerName, percentageOfTotalNetAssets, securityTypeName}.
    securityTypeName 이 보통주/예탁증서(ADR)/REIT 인 줄만 — Currency·Currency Collateral·Synthetic Cash·Index Future·Money Market Fund·Uninvestible Cash 는 제외."""
    as_of = str(obj.get("effectiveDate") or "")[:10] or None
    out = []
    for x in obj.get("holdings") or []:
        if not x or not re.search(r"Common Stock|Depos[ai]tory Receipt|REIT", str(x.get("securityTypeName") or ""), re.I): continue
        t, w, n = norm_ticker(x.get("ticker")), _pct(x.get("percentageOfTotalNetAssets")), str(x.get("issuerName") or "").strip()
        if w is None or t is None or NONSEC.search(n): continue
        out.append({"n": n, "t": t, "w": w})
    return as_of, out


def parse_nport(xml):
    """SEC N-PORT primary_doc.xml → (as_of=repPdDate, [ {n,w,cusip,isin} ]). assetCat == EC(주식-보통주)·Long 만. 티커는 없다(OpenFIGI 로 붙인다)."""
    ns = {"n": "http://www.sec.gov/edgar/nport"}
    r = ET.fromstring(xml)
    as_of = (r.findtext(".//n:repPdDate", namespaces=ns) or "")[:10] or None
    out = []
    for e in r.findall(".//n:invstOrSec", ns):
        if e.findtext("n:assetCat", namespaces=ns) != "EC" or e.findtext("n:payoffProfile", namespaces=ns) not in (None, "Long"): continue
        w = _pct(e.findtext("n:pctVal", namespaces=ns))
        isin = e.find("n:identifiers/n:isin", ns)
        if w is None: continue
        out.append({"n": (e.findtext("n:name", namespaces=ns) or "").strip(), "w": w, "cusip": (e.findtext("n:cusip", namespaces=ns) or "").strip(),
                    "isin": isin.get("value") if isin is not None else ""})
    return as_of, out


# ---- 가져오기 ---------------------------------------------------------------------------------------------------------
def fetch_etf(etf, log=print):
    """1x ETF 1개의 발행사 보유 → {as_of, rows(전체 주식), src:{name,url}} (rows: n,t,w,ts[,exh]). 실패하면 예외."""
    ts = "issuer_file"
    if etf in SSGA:
        url = f"https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-{etf.lower()}.xlsx"
        as_of, rows = parse_ssga(http_get(url)); name = f"SSGA {etf} 일별 보유 xlsx"
    elif etf in ISHARES:
        pid, slug = ISHARES[etf]
        url = f"https://www.ishares.com/us/products/{pid}/{slug}/latest-holdings.csv"
        as_of, rows = parse_ishares(http_get(url).decode("utf-8-sig", "ignore")); name = f"iShares {etf} 보유 csv"
    elif etf in VANECK:
        url = VANECK[etf]
        as_of, rows = parse_vaneck(http_get(url)); name = f"VanEck {etf} 일별 보유 xlsx"
    elif etf in FIRSTTRUST:
        url = FIRSTTRUST[etf]
        as_of, rows = parse_firsttrust(http_get(url).decode("utf-8", "ignore")); name = f"First Trust {etf} 보유 표"
    elif etf in INVESCO:
        sid, idt = INVESCO[etf]
        url = f"https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/{sid}/holdings/fund?idType={idt}&productType=ETF"
        try:       # r= 은 CDN 이 과거 실패 응답(406)을 URL 별로 캐시해 두는 경우를 피하는 캐시 우회 값(실측: 같은 URL 은 406, r 를 붙이면 200)
            as_of, rows = parse_invesco_json(json.loads(http_get(url + f"&r={int(time.time())}", headers={"Accept": "application/json", "Origin": "https://www.invesco.com"}, retries=1)))
            name = f"Invesco {etf} 보유 JSON"
            if len(rows) < 30: raise ValueError(f"Invesco 응답 주식 {len(rows)}건(미리보기·형식 변경 의심)")
        except Exception as e:
            log(f"  {etf}: Invesco 발행사 API 실패({type(e).__name__}: {str(e)[:60]}) → SEC N-PORT 대체")
            as_of, rows, url = fetch_nport(etf, log)
            name = f"SEC N-PORT {etf} (발행사 제출, 기준일 {as_of}; Invesco 일별 파일 접근 불가)"; ts = "openfigi"
    else:
        raise KeyError(etf)
    if not rows: raise ValueError(f"{etf}: 주식 구성 0건")
    for r in rows: r.setdefault("ts", ts if r.get("t") else "none")
    return {"as_of": as_of or today(), "rows": rows, "src": {"name": name, "url": url}}


def fetch_nport(etf, log=print):
    """SEC 에서 해당 펀드(seriesId)의 최신 NPORT-P 를 찾아 받고, CUSIP/ISIN → 티커(OpenFIGI)를 붙인다 → (as_of, rows, url)."""
    cik, sid = NPORT_SERIES[etf]
    sub = json.loads(http_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers={"User-Agent": SEC_UA}))
    rec = sub["filings"]["recent"]
    cands = [rec["accessionNumber"][i] for i, f in enumerate(rec["form"]) if f == "NPORT-P"][:150]
    cache = _jload(LOCAL / "nport_cache.json", {})
    acc = None
    for a in cands:
        if a == (cache.get(etf) or {}).get("acc"): acc = a; break                          # 이전에 찾은 것까지 내려갔는데 더 새 것이 없음
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{a.replace('-', '')}/primary_doc.xml"
        head = http_get(url, headers={"User-Agent": SEC_UA, "Range": "bytes=0-1500"}).decode("utf-8", "ignore"); _sleep()
        if f"<seriesId>{sid}</seriesId>" in head: acc = a; break
    if acc is None: raise LookupError(f"{etf}: N-PORT 없음(seriesId {sid})")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/primary_doc.xml"
    as_of, rows = parse_nport(http_get(url, headers={"User-Agent": SEC_UA}))
    _jsave(LOCAL / "nport_cache.json", dict(cache, **{etf: {"acc": acc, "as_of": as_of}}))
    tick = figi_tickers([(r["cusip"], r["isin"]) for r in rows])
    for r in rows: r["t"] = norm_ticker(tick.get((r["cusip"], r["isin"])))
    return as_of, rows, url


def figi_tickers(ids):
    """[(cusip, isin)] → {(cusip, isin): 티커}. OpenFIGI v3(무키: 분당 25회·요청당 10건), 미국(exchCode US) 상장 우선. 결과는 .local/figi_cache.json."""
    cache = _jload(LOCAL / "figi_cache.json", {})
    key = lambda c, i: f"{c}|{i}"
    todo = [(c, i) for c, i in ids if key(c, i) not in cache]
    for b in range(0, len(todo), 10):
        batch = todo[b:b + 10]
        jobs = [({"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} if c else {"idType": "ID_ISIN", "idValue": i}) for c, i in batch]
        try:
            res = json.loads(http_get("https://api.openfigi.com/v3/mapping", headers={"Content-Type": "application/json"}, data=json.dumps(jobs).encode(), retries=1))
        except Exception:
            time.sleep(8); continue                                                            # 이번 배치는 비워 둠(다음 실행에서 재시도)
        for (c, i), r in zip(batch, res):
            d = [x for x in (r.get("data") or []) if x.get("exchCode") == "US" and x.get("securityType") in ("Common Stock", "ADR", "Depositary Receipt", "REIT")] or (r.get("data") or [])[:1]
            if not d and c and i:                                                              # CUSIP 로 못 찾으면 ISIN 으로 한 번 더
                try:
                    r2 = json.loads(http_get("https://api.openfigi.com/v3/mapping", headers={"Content-Type": "application/json"},
                                             data=json.dumps([{"idType": "ID_ISIN", "idValue": i}]).encode(), retries=0))[0]
                    d = [x for x in (r2.get("data") or []) if x.get("exchCode") == "US"][:1]
                except Exception: d = []
            cache[key(c, i)] = d[0]["ticker"] if d else None
        time.sleep(2.6)
    _jsave(LOCAL / "figi_cache.json", cache)
    return {(c, i): cache.get(key(c, i)) for c, i in ids}


# ---- 캐시 I/O -----------------------------------------------------------------------------------------------------------
def _jload(p, default):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return default


def _jsave(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    json.dump(obj, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, p)


# ---- 회사명 → 티커(ETN 지수 구성용) ---------------------------------------------------------------------------------------------
_GENERIC = {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "THE", "NV", "SA", "AG", "HOLDINGS", "HLDGS", "GROUP", "CMN", "COM",
            "ORD", "SHS", "ADR", "SP", "CLASS", "CL", "ORDINARY", "SHARES", "INCORPORATED", "DE", "OF"}


def norm_name(s):
    """회사명 정규화: 대문자·구두점 제거·공통 접미어 제거. 클래스 표기('CLASS A'·'-A'·'CL A'·'(Class A)')는 마지막 토큰 'A' 로 통일해 GOOGL/GOOG 구분을 유지."""
    s = re.sub(r"[^A-Z0-9 ]", " ", str(s).upper().replace("&", " AND ").replace("-", " "))
    toks = s.split()
    cls = toks[-1] if len(toks) >= 2 and toks[-1] in ("A", "B", "C") else None
    core = [t for t in toks if t not in _GENERIC]
    if cls and core and core[-1] != cls: core.append(cls)
    return " ".join(core)


def name_index(all_rows):
    """norm_name → {티커} (여러 파일 합집합). 값이 2개 이상이면 모호 → 사용 안 함."""
    ix = {}
    for r in all_rows:
        if r.get("t"): ix.setdefault(norm_name(r["n"]), set()).add(r["t"])
    return ix


def resolve_name(name, ix):
    """(ticker|None, ts). 정규화 이름 일치 → 앞 두 토큰 일치(유일할 때) → INDEX_FILE_TICKERS → yfinance Search → none."""
    if name in INDEX_FILE_TICKERS: return INDEX_FILE_TICKERS[name], "index_file"
    k = norm_name(name)
    c = ix.get(k)
    if c and len(c) == 1: return next(iter(c)), "issuer_file"
    kt = k.split()
    if len(kt) >= 2 and kt[-1] not in ("A", "B", "C"):                                              # 클래스 구분 없는 이름만 앞 두 토큰 일치 허용
        cs = {t for kk, ts in ix.items() if kk.split()[:2] == kt[:2] for t in ts}
        if len(cs) == 1: return next(iter(cs)), "issuer_file"
    return None, "none"


def yf_search_ticker(name):
    """yfinance Search 로 미국 상장 주식 티커 보완. 이름 첫 토큰이 일치하는 NMS/NYQ/NGM/NCM/ASE/PCX 만 인정. 원문 이름으로 못 찾으면 클래스 표기를 뗀 이름으로 한 번 더."""
    try:
        import yfinance as yf
    except Exception:
        return None
    qs = [name, " ".join(w for w in norm_name(name).split() if not (len(w) == 1 and w in "ABC"))]
    for q in dict.fromkeys(qs):
        try:
            for c in yf.Search(q, max_results=6, news_count=0).quotes:
                if c.get("quoteType") == "EQUITY" and c.get("exchange") in ("NMS", "NYQ", "NGM", "NCM", "ASE", "PCX") and "." not in c.get("symbol", ""):
                    if norm_name(c.get("shortname") or c.get("longname") or "").split()[:1] == norm_name(name).split()[:1]: return c["symbol"]
        except Exception:
            pass
        time.sleep(SLEEP)
    return None


# ---- 거래소 · 네이버 코드 --------------------------------------------------------------------------------------------------
YF_EX = {"NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NYQ": "NYSE", "ASE": "AMEX", "PCX": "AMEX", "BATS": "AMEX"}
ISHARES_EX = {"NASDAQ": "NASDAQ", "NEW YORK STOCK EXCHANGE INC.": "NYSE", "NYSE": "NYSE", "NYSE ARCA": "AMEX", "NYSE MKT": "AMEX", "CBOE BZX FORMERLY BATS": "AMEX"}
NAVER_EX = {"NSQ": "NASDAQ", "NYS": "NYSE", "AMX": "AMEX"}


def naver_candidates(t, ex):
    """네이버 코드 후보(앞일수록 우선). 실측: 나스닥 'T.O' · NYSE 는 종목마다 접미 없는 'T'(JPM·XOM·GE) 또는 'T.K'(ABBV·ORCL·UBER) 중 하나만 유효 · AMEX/Arca ETF 는 접미 없는 'T'(GDX·SPY).
    점 티커 BRK.B → 'BRKb'(클래스 문자 소문자). 앞 후보가 409 면 다음 후보를 시도하므로 순서는 호출 수에만 영향."""
    base = t.replace(".", "")
    if "." in t: a, b = t.split("."); base = a + b.lower()
    o, k, a_, bare = base + ".O", base + ".K", base + ".A", base
    return {"NASDAQ": [o, bare, k], "NYSE": [bare, k, o], "AMEX": [bare, a_, k, o]}.get(ex) or [o, bare, k, a_]


def naver_check(code, cache, deadline):
    """api.stock.naver.com/stock/{code}/basic → {ok, name, ex}. 200 이면 존재, 409 면 없음. 캐시 30일. 마감 시각 지나면 None(미확인)."""
    c = cache.get(code)
    if c and (datetime.date.today() - datetime.date.fromisoformat(c["at"])).days < 30: return c
    if time.time() > deadline: return None
    _sleep()
    try:
        j = json.loads(http_get(f"https://api.stock.naver.com/stock/{urllib.parse.quote(code)}/basic", retries=1, timeout=20))
        e = j.get("stockExchangeType") or {}
        r = {"ok": bool(j.get("reutersCode")), "name": j.get("stockNameEng") or "", "ex": NAVER_EX.get(e.get("code")) if isinstance(e, dict) else None, "at": today()}
    except urllib.error.HTTPError as e:
        if e.code != 409: return None
        r = {"ok": False, "name": "", "ex": None, "at": today()}
    except Exception:
        return None
    cache[code] = r
    return r


def names_agree(a, b):
    """네이버 영문명과 보유 회사명이 의미 있는 토큰(2자 이상, F5·HP·3M 포함)을 하나라도 공유하면 같은 회사로 본다 — 같은 티커가 다른 회사를 가리키는 오링크 방지."""
    ta = {t for t in norm_name(a).split() if len(t) >= 2 and t != "AND"}
    tb = {t for t in norm_name(b).split() if len(t) >= 2 and t != "AND"}
    return bool(ta & tb) or any(x[:4] == y[:4] for x in ta for y in tb if len(x) >= 4 and len(y) >= 4)


def yf_exchange(t, cache, deadline):
    c = cache.get(t)
    if c and (datetime.date.today() - datetime.date.fromisoformat(c["at"])).days < 90: return c["ex"]
    if time.time() > deadline: return None
    try:
        import yfinance as yf
        ex = yf.Ticker(t.replace(".", "-")).fast_info.get("exchange")
    except Exception:
        return None
    cache[t] = {"ex": ex, "at": today()}
    return ex


def enrich(entries, budget_s=900, log=print):
    """모든 구성 항목에 ex(거래소)·nv(네이버 코드)를 채운다. 티커 단위로 한 번만 조회. 예산(초)을 넘기면 남은 것은 ex/nv=None 으로 두고 다음 실행이 이어서 처리한다."""
    deadline = time.time() + budget_s
    ncache = _jload(LOCAL / "naver_cache.json", {}); ycache = _jload(LOCAL / "yf_exchange_cache.json", {})
    hint = {}
    for e in entries.values():
        for x in e["items"]:
            if x.get("exh"): hint.setdefault(x["t"], ISHARES_EX.get(x["exh"].upper()))
    uniq = {}
    for e in entries.values():
        for x in e["items"]:
            if x.get("t"): uniq.setdefault(x["t"], x["n"])
    res, stats = {}, {"yf_ex": 0, "naver_ok": 0, "naver_no": 0, "naver_name_mismatch": 0, "naver_name_by_exchange": 0, "unchecked": 0}
    for i, (t, name) in enumerate(sorted(uniq.items())):
        yex = yf_exchange(t, ycache, deadline)
        ex = YF_EX.get(yex) or hint.get(t)
        if yex: stats["yf_ex"] += 1
        nv, nex, checked = None, None, True
        for code in naver_candidates(t, ex):
            r = naver_check(code, ncache, deadline)
            if r is None: checked = False; break
            if r["ok"]:
                if names_agree(r["name"], name): nv, nex = code, r["ex"]; break
                if r["ex"] and ex and r["ex"] == ex:                                               # 이름 표기가 달라도(WABTEC↔Westinghouse Air Brake) 티커·거래소가 두 출처에서 일치하면 같은 종목
                    nv, nex = code, r["ex"]; stats["naver_name_by_exchange"] += 1; log(f"  이름 달라도 거래소 일치로 인정 {code}: '{r['name']}' / '{name}'"); break
                stats["naver_name_mismatch"] += 1; log(f"  네이버 이름 불일치(거절) {code}: '{r['name']}' ≠ '{name}'")
        if nv: stats["naver_ok"] += 1
        elif checked: stats["naver_no"] += 1
        else: stats["unchecked"] += 1
        res[t] = (ex or nex, nv)
        if i % 100 == 99:
            _jsave(LOCAL / "naver_cache.json", ncache); _jsave(LOCAL / "yf_exchange_cache.json", ycache); log(f"  enrich {i + 1}/{len(uniq)}")
    _jsave(LOCAL / "naver_cache.json", ncache); _jsave(LOCAL / "yf_exchange_cache.json", ycache)
    for e in entries.values():
        for x in e["items"]:
            x["ex"], x["nv"] = res.get(x.get("t"), (None, None))
            x.pop("exh", None)
    return stats


# ---- 항목 조립 ---------------------------------------------------------------------------------------------------------
def make_entry(basis, as_of, rows, src, fetched):
    """rows(전체 주식) → 스키마 항목. 비중 내림차순·상위 TOP_N·total=전체 N."""
    rows = sorted(rows, key=lambda r: -r["w"])
    total = len(rows)
    items = [{"n": r["n"], "t": r.get("t"), "w": round(r["w"], 3), "ts": r.get("ts") or ("issuer_file" if r.get("t") else "none"), "ex": None, "nv": None,
              **({"exh": r["exh"]} if r.get("exh") else {})} for r in rows[:TOP_N]]
    return {"basis": basis, "as_of": as_of, "fetched": fetched, "total": total, "scope": "전체" if total <= TOP_N else f"전체 {total}종 중 상위 {TOP_N}",
            "source": src, "items": items}


def lookthrough(parts):
    """[(지수 비중 %, fund rows)] → 합성 rows. 같은 종목(티커, 없으면 정규화 이름)은 비중 합산."""
    acc = {}
    for iw, rows in parts:
        for r in rows:
            k = r.get("t") or norm_name(r["n"])
            a = acc.setdefault(k, {"n": r["n"], "t": r.get("t"), "w": 0.0, "ts": r.get("ts")})
            a["w"] += iw / 100.0 * r["w"]
    return list(acc.values())


def etf_list(prods):
    """products.yaml → {종목: 1x ETF}"""
    out = {}
    for t, p in prods.items():
        m = re.search(r"1x ETF ([A-Z0-9]+)", str((p.get("top_constituents") or {}).get("basis", "")))
        if p["type"] == "ETF" and m: out[t] = m.group(1)
    return out


def build(prev=None, log=print, budget_s=900, fetcher=fetch_etf, do_enrich=True):
    """전체 구성 산출 → (holdings dict, 보고용 상세). 네트워크 실패는 종목별로 흡수(직전 값 + stale)."""
    prods = yaml.safe_load(open(DATA / "products.yaml", encoding="utf-8"))["products"]
    ix = yaml.safe_load(open(DATA / "index_specs.yaml", encoding="utf-8"))["products"]
    prev_items = (prev or {}).get("items", {})
    td = today()
    needs = etf_list(prods)
    want = sorted(set(needs.values()) | set(EXTRA_ETFS))
    got, fails = {}, {}
    for etf in want:
        try:
            got[etf] = fetcher(etf, log); log(f"  {etf}: {len(got[etf]['rows'])}종 as_of {got[etf]['as_of']} ({got[etf]['src']['name']})")
        except Exception as e:
            fails[etf] = f"{type(e).__name__}: {str(e)[:100]}"; log(f"  {etf}: 실패 {fails[etf]}")
        _sleep()
    entries, stale = {}, {}
    nix = name_index([r for g in got.values() for r in g["rows"]])
    for t, p in prods.items():
        if p["type"] == "ETF":
            etf = needs.get(t)
            if etf in got:
                g = got[etf]; entries[t] = make_entry(f"1x ETF {etf} 보유", g["as_of"], g["rows"], g["src"], td)
            else: stale[t] = fails.get(etf, "1x ETF 불명")
        elif t in FUND_ETN:
            etf = FUND_ETN[t]
            if etf in got:
                g = got[etf]; entries[t] = make_entry(f"{etf} 보유(지수가 이 펀드를 추종)", g["as_of"], g["rows"], g["src"], td)
            else: stale[t] = fails.get(etf, "펀드 불명")
        elif t in LOOKTHROUGH_ETN:
            fs = LOOKTHROUGH_ETN[t]
            c = ((ix.get(t) or {}).get("index") or {}).get("constituents") or {}
            w = {str(i["name"]).upper(): i["weight_pct"] for i in c.get("items", [])}
            wf = [next((v for k, v in w.items() if f in k or (f == "GDX" and "GOLD MINERS ETF" in k) or (f == "GDXJ" and "JUNIOR" in k)), None) for f in fs]
            if all(f in got for f in fs) and all(wf):
                rows = lookthrough([(wf[0], got[fs[0]]["rows"]), (wf[1], got[fs[1]]["rows"])])
                src = {"name": f"VanEck {'·'.join(fs)} 일별 보유 xlsx (지수 비중 {wf[0]:g}%·{wf[1]:g}% 로 합성)", "url": got[fs[0]]["src"]["url"]}
                entries[t] = make_entry(f"{'·'.join(fs)} 보유(지수가 이 두 펀드를 {wf[0]:g}%·{wf[1]:g}%로 추종)", min(got[f]["as_of"] for f in fs), rows, src, td)
            else: stale[t] = "; ".join(fails.get(f, "") for f in fs) or "GDX·GDXJ 비중 불명"
        else:                                                                                       # 그 밖의 ETN: 지수 구성표(index_specs)
            c = ((ix.get(t) or {}).get("index") or {}).get("constituents") or {}
            rows = []
            for i in c.get("items", []):
                if i.get("name") is None or i.get("weight_pct") is None: continue
                tk, ts = resolve_name(str(i["name"]), nix)
                rows.append({"n": str(i["name"]), "t": tk, "w": float(i["weight_pct"]), "ts": ts})
            if rows:
                slug = MICROSECTORS_PAGE.get(t)
                entries[t] = make_entry("지수 구성종목", str(c.get("as_of", "")).split(" ")[0], rows,
                                        {"name": "microsectors.com 상품 페이지 지수 구성", "url": f"https://microsectors.com/{slug}/" if slug else "https://microsectors.com/"}, td)
            else: stale[t] = "지수 구성표 비어 있음"
    # 이름으로 못 찾은 ETN 항목은 yfinance Search 로 한 번 더(결과 캐시)
    sc = _jload(LOCAL / "yf_search_cache.json", {})
    for t, e in entries.items():
        if e["basis"] != "지수 구성종목": continue
        for x in e["items"]:
            if x["t"] is None:
                if not sc.get(x["n"]) and do_enrich: sc[x["n"]] = yf_search_ticker(x["n"])               # 못 찾은 이름은 매 실행 재시도(소수)
                if sc.get(x["n"]): x["t"], x["ts"] = sc[x["n"]], "yfinance"
    _jsave(LOCAL / "yf_search_cache.json", sc)
    stats = enrich(entries, budget_s, log) if do_enrich else {}
    for t, why in stale.items():                                                                    # 실패 → 직전 값 유지(+stale)
        old = prev_items.get(t)
        if old:
            entries[t] = dict(old, stale=True)
        log(f"  {t}: 갱신 실패({why}) → {'직전 값 유지(stale)' if old else '직전 값 없음!'}")
    return {"generated": td, "items": {t: entries[t] for t in prods if t in entries}}, {"fails": fails, "stale": stale, "enrich": stats}


def dump(obj, path):
    """항목은 한 줄씩(diff 가독성·용량), 상위 구조는 들여쓰기. 임시 파일 → 원자적 교체."""
    parts = []
    for t, e in obj["items"].items():
        head = {k: v for k, v in e.items() if k != "items"}
        body = ",\n".join("   " + json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in e["items"])
        parts.append(f'  {json.dumps(t)}: {json.dumps(head, ensure_ascii=False)[:-1]}, "items": [\n{body}\n  ]}}')
    txt = '{"generated": %s, "items": {\n%s\n}}\n' % (json.dumps(obj["generated"]), ",\n".join(parts))
    json.loads(txt)                                                                                 # 쓰기 전 재파싱 검증
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(txt, encoding="utf-8")
    os.replace(tmp, path)


def refresh(log=print, budget_s=900, write=True):
    """주간 점검 훅·CLI 공용: 구성 갱신 후 data/holdings.json 저장. 요약 dict 반환."""
    p = DATA / "holdings.json"
    prev = _jload(p, {})
    obj, info = build(prev, log, budget_s)
    bad = [t for t, e in obj["items"].items() if not e["items"]]
    if bad: raise RuntimeError(f"구성 0건 종목: {bad}")
    if write: dump(obj, p)
    return {"n": len(obj["items"]), "stale": sorted(info["stale"]), "fails": info["fails"], "enrich": info["enrich"]}


if __name__ == "__main__":
    s = refresh(write="--dry" not in sys.argv)
    print(json.dumps(s, ensure_ascii=False))
