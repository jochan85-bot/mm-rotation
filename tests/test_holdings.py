"""MM-PAGE-V3.2 §3~§6 구성종목 단위 테스트 — 네트워크 없음. python3 tests/test_holdings.py"""
import sys, io, json, tempfile, urllib.error
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
import openpyxl, yaml
import mm_holdings as H
ok = 0; bad = []
def check(name, cond, detail=""):
    global ok
    if cond: ok += 1; print("PASS", name)
    else: bad.append(name); print("FAIL", name, detail)

def xlsx(rows):
    wb = openpyxl.Workbook(); ws = wb.active
    for r in rows: ws.append(list(r))
    b = io.BytesIO(); wb.save(b); return b.getvalue()

# ---- 1. SSGA ----
ssga = xlsx([("Fund Name:", "SPDR S&P 500"), ("Ticker Symbol:", "SPY"), ("Holdings:", "As of 08-Oct-2026"), (None,),
             ("Name", "Ticker", "Identifier", "SEDOL", "Weight", "Sector", "Shares Held", "Local Currency"),
             ("NVIDIA CORP", "NVDA", "67066G104", "x", 8.33, "-", 1, "USD"), ("BERKSHIRE HATHAWAY INC CL B", "BRK.B", "x", "x", 1.5, "-", 1, "USD"),
             ("US DOLLAR", "-", "x", "x", 0.28, "-", 1, "USD"), ("SSI US GOV MONEY MARKET CLASS", "-", "x", "x", 0.07, "-", 1, "USD"),
             ("CONTRA METSERA INC", "-", "x", "x", 0.07, "-", 1, "USD"), (None,), ("State Street disclaimer",)])
a, r = H.parse_ssga(ssga)
check("SSGA 기준일", a == "2026-10-08", a)
check("SSGA 현금·머니마켓·CONTRA 제외, 주식만", [x["t"] for x in r] == ["NVDA", "BRK.B"], r)
check("SSGA 비중 숫자(%)", abs(r[0]["w"] - 8.33) < 1e-9)

# ---- 2. iShares ----
ish = '''iShares Russell 2000 ETF
Fund Holdings as of,"Oct 07, 2026"
Inception Date,"May 22, 2000"

Ticker,Name,Sector,Asset Class,Market Value,Weight (%),Notional Value,Quantity,Price,Location,Exchange,Currency,FX Rate,Market Currency,Accrual Date
"BTSG","BRIGHTSPRING HEALTH SERVICES INC","Health Care","Equity","282,458,805.20","0.36","282,458,805.20","4,427,254.00","63.80","United States","NASDAQ","USD","1.00","USD","-"
"MOG A","MOOG INC CLASS A","Industrials","Equity","271,024,452.09","0.35","271,024,452.09","752,031.00","360.39","United States","New York Stock Exchange Inc.","USD","1.00","USD","-"
"USD","USD CASH","Cash and/or Derivatives","Cash","1,000.00","0.10","1,000.00","1,000.00","100.00","United States","-","USD","1.00","USD","-"
"ESZ6","S&P FUTURES","Cash and/or Derivatives","Futures","0.00","0.00","1.00","1.00","1.00","United States","-","USD","1.00","USD","-"
"BLKRC","BLK CSH FND TREASURY SL AGENCY","Cash and/or Derivatives","Money Market","5.00","0.01","5.00","5.00","1.00","United States","-","USD","1.00","USD","-"
'''
a, r = H.parse_ishares(ish)
check("iShares 기준일", a == "2026-10-07", a)
check("iShares Equity 만(현금·선물·머니마켓 제외)", [x["t"] for x in r] == ["BTSG", "MOG.A"], r)
check("iShares 공백 티커 → 점 표기", r[1]["t"] == "MOG.A")
check("iShares Exchange 열 보존", r[0]["exh"] == "NASDAQ" and H.ISHARES_EX[r[1]["exh"].upper()] == "NYSE")

ish2 = '''iShares Core S&P Mid-Cap ETF
Fund Holdings as of,"Oct 07, 2026"

Ticker,Name,Type,Sector,Asset Class,Market Value,Notional Value,Quantity,Price,Location,Exchange,Currency,FX Rate,Market Currency,Accrual Date,Market Weight,Notional Weight
"OKTA","OKTA CLASS A","EQUITY","Information Technology","Equity","1,299,311,828.00","1,299,311,828.00","5,960,146.00","218.00","United States","NASDAQ","USD","1.00","USD","-","1.06","1.06"
"HOG","HARLEY DAVIDSON","SWAP","Consumer Discretionary","Equity","0.00","4,284,537.95","158,981.00","26.95","United States","NYSE","USD","1.00","USD","-","-","-"
"MLISW","CASH COLLATERAL USD BOASW CFD","COLLATERAL","Cash and/or Derivatives","Cash Collateral and Margins","2,040,318.55","2,040,318.55","2,039,000.00","100.00","United States","-","USD","1.00","USD","-","1.00","1.00"
'''
a, r = H.parse_ishares(ish2)
check("iShares IJH 형식(Type·Market Weight): EQUITY 만, SWAP·담보 제외", [x["t"] for x in r] == ["OKTA"] and abs(r[0]["w"] - 1.06) < 1e-9, r)

# ---- 3. VanEck ----
van = xlsx([("Daily Holdings (%)  10/08/2026",), ("",), ("Number", "Ticker", "Holding Name", "Identifier (FIGI)", "Shares", "Asset Class", "Market Value (US$)", "Notional Value", "% of Net Assets"),
            (1, "NEM", "Newmont Corp", "x", "1", "Stock", "$1", " -- ", "11.23%"), (2, "NST AU", "Northern Star Resources Ltd", "x", "1", "Stock", "$1", " -- ", "2.87%"),
            (3, "-USD CASH-", "", " ", "1", "Cash Bal", "$1", " -- ", "0.05%"), (4, " -- ", "Other/Cash", " -- ", " -- ", "Cash", "$-1", " -- ", "-0.00%"), ("disclaimer",)])
a, r = H.parse_vaneck(van)
check("VanEck 기준일(MM/DD/YYYY)", a == "2026-10-08", a)
check("VanEck Stock 만, 현금 제외", [x["n"] for x in r] == ["Newmont Corp", "Northern Star Resources Ltd"], r)
check("VanEck 해외 상장은 t=None(회사명만)", r[0]["t"] == "NEM" and r[1]["t"] is None)

# ---- 4. First Trust ----
ft = '''<span>Holdings of the Fund as of 10/8/2026</span><table>
<tr><td>Security Name</td><td>Identifier</td><td>CUSIP</td><td>Classification</td><td>Shares / Quantity</td><td>Market Value</td><td>Weighting</td></tr>
<tr><td>Meta Platforms, Inc. (Class A)</td><td>META</td><td>30303M102</td><td>Communication Services</td><td>802,106</td><td>$578</td><td>10.77%</td></tr>
<tr><td>Alphabet Inc. (Class C)</td><td>GOOG</td><td>02079K107</td><td>Communication Services</td><td>1</td><td>$1</td><td>4.57%</td></tr>
<tr><td>US Dollar</td><td>$USD</td><td></td><td></td><td></td><td></td><td>0.08%</td></tr></table>'''
a, r = H.parse_firsttrust(ft)
check("First Trust 기준일·현금($USD) 제외", a == "2026-10-08" and [x["t"] for x in r] == ["META", "GOOG"], (a, r))

# ---- 5. N-PORT / Invesco JSON ----
np_xml = '''<?xml version="1.0"?><edgarSubmission xmlns="http://www.sec.gov/edgar/nport"><formData><genInfo><repPdDate>2026-06-30</repPdDate></genInfo><invstOrSecs>
<invstOrSec><name>NVIDIA Corp</name><cusip>67066G104</cusip><identifiers><isin value="US67066G1040"/></identifiers><pctVal>8.5</pctVal><payoffProfile>Long</payoffProfile><assetCat>EC</assetCat></invstOrSec>
<invstOrSec><name>Nasdaq futures</name><cusip>N/A</cusip><pctVal>0.5</pctVal><payoffProfile>Long</payoffProfile><assetCat>DE</assetCat></invstOrSec>
<invstOrSec><name>Short thing</name><pctVal>-1</pctVal><payoffProfile>Short</payoffProfile><assetCat>EC</assetCat></invstOrSec></invstOrSecs></formData></edgarSubmission>'''
a, r = H.parse_nport(np_xml.encode())
check("N-PORT 기준일·주식(EC)·Long 만", a == "2026-06-30" and len(r) == 1 and r[0]["cusip"] == "67066G104" and r[0]["isin"] == "US67066G1040", (a, r))
a, r = H.parse_invesco_json({"effectiveDate": "2026-10-08T00:00:00", "holdings": [
    {"ticker": "NVDA", "issuerName": "NVIDIA Corp", "percentageOfTotalNetAssets": 8.4, "securityTypeName": "Common Stock"},
    {"ticker": "ASML", "issuerName": "ASML Holding NV", "percentageOfTotalNetAssets": 0.7, "securityTypeName": "American Depository Receipt"},
    {"ticker": "PDD", "issuerName": "PDD Holdings", "percentageOfTotalNetAssets": 0.2, "securityTypeName": "American Depository Receipt - NY"},
    {"ticker": "USD", "issuerName": "US Dollar", "percentageOfTotalNetAssets": 0.47, "securityTypeName": "Currency"},
    {"ticker": "NQZ6", "issuerName": "NASDAQ 100 E-MINI Dec26", "percentageOfTotalNetAssets": 0.14, "securityTypeName": "Index Future"},
    {"ticker": "MMF", "issuerName": "Invesco Treasury", "percentageOfTotalNetAssets": 0.05, "securityTypeName": "Money Market Fund, Taxable"},
    {"ticker": "USDPDV", "issuerName": "USD Pending Dividends", "percentageOfTotalNetAssets": None, "securityTypeName": "Currency"}, None]})
check("Invesco JSON: 보통주·ADR 만(통화·선물·머니마켓 제외)", a == "2026-10-08" and [x["t"] for x in r] == ["NVDA", "ASML", "PDD"], (a, r))
check("Invesco 조회 식별자(SPHB 는 CUSIP)", H.INVESCO["QQQ"] == ("QQQ", "ticker") and H.INVESCO["SPHB"] == ("46138E370", "cusip"))

# ---- 6. 티커 정규화 ----
check("norm_ticker", [H.norm_ticker(x) for x in ("BRK/B", "BRK-B", "MOG A", "NST AU", "$USD", "-", "AMD", "PE&OLES* MM")] == ["BRK.B", "BRK.B", "MOG.A", None, None, None, "AMD", None])

# ---- 7. 100 상한 + total + 정렬 ----
rows = [{"n": f"Co{i}", "t": f"T{chr(65 + i % 26)}{chr(65 + i // 26)}", "w": float(i % 7) + i / 1000, "ts": "issuer_file"} for i in range(150)]
e = H.make_entry("1x ETF IWM 보유", "2026-10-07", rows, {"name": "x", "url": "u"}, "2026-10-09")
ws = [x["w"] for x in e["items"]]
check("items 상한 100 · total=전체 150 · scope", len(e["items"]) == 100 and e["total"] == 150 and e["scope"] == "전체 150종 중 상위 100", (len(e["items"]), e["total"], e["scope"]))
check("비중 내림차순", ws == sorted(ws, reverse=True))
check("상위 100 = 전체 중 최대 비중 100개", min(ws) >= sorted((r["w"] for r in rows), reverse=True)[99] - 1e-3)
e2 = H.make_entry("지수 구성종목", "2026-10-08", rows[:30], {"name": "x", "url": "u"}, "2026-10-09")
check("100 이하는 scope '전체'", e2["scope"] == "전체" and e2["total"] == 30 and len(e2["items"]) == 30)
check("스키마 키", set(e2) == {"basis", "as_of", "fetched", "total", "scope", "source", "items"} and set(e2["items"][0]) == {"n", "t", "w", "ts", "ex", "nv"})

# ---- 8. 네이버 코드 ----
check("나스닥 → T.O 우선", H.naver_candidates("AMD", "NASDAQ")[0] == "AMD.O")
check("NYSE → 접미 없는 코드 우선, 이어서 .K (실측: JPM 은 접미 없음, ABBV 는 .K)", H.naver_candidates("JPM", "NYSE")[:2] == ["JPM", "JPM.K"] and H.naver_candidates("GDX", "AMEX")[0] == "GDX")
check("점 티커 BRK.B → BRKb", H.naver_candidates("BRK.B", "NYSE")[0] == "BRKb" and H.naver_candidates("BF.B", "NYSE")[0] == "BFb")
check("거래소 미상이면 모든 접미 시도", H.naver_candidates("XYZ", None) == ["XYZ.O", "XYZ", "XYZ.K", "XYZ.A"])
check("yfinance 거래소 코드 → ex", [H.YF_EX.get(x) for x in ("NMS", "NGM", "NYQ", "ASE", "PCX", "XXX")] == ["NASDAQ", "NASDAQ", "NYSE", "AMEX", "AMEX", None])
check("이름 일치 검사(F5·HP·3M 같은 짧은 이름 포함)", H.names_agree("F5  Inc.", "F5 INC") and H.names_agree("3M Company", "3M CO") and H.names_agree("Advanced Micro Devices Inc.", "ADVANCED MICRO DEVICES") and H.names_agree("Alphabet Inc. Class A", "ALPHABET INC-CL A") and not H.names_agree("Foo Mining", "Bar Software"))

# ---- 9. 회사명 → 티커 ----
nix = H.name_index([{"n": "MICRON TECHNOLOGY INC", "t": "MU"}, {"n": "Alphabet Inc. (Class A)", "t": "GOOGL"}, {"n": "Alphabet Inc. (Class C)", "t": "GOOG"},
                    {"n": "TAIWAN SEMICONDUCTOR MANUFACTURING ADR", "t": "TSM"}])
check("지수 표기 이름 → 발행사 파일 티커", H.resolve_name("MICRON TECHNOLOGY INC", nix) == ("MU", "issuer_file"))
check("Class A / C 구분", H.resolve_name("ALPHABET INC-CL A", nix)[0] == "GOOGL" and H.resolve_name("ALPHABET INC-CL C", nix)[0] == "GOOG")
check("앞 두 토큰 유일 일치(TAIWAN SEMICONDUCTOR-SP ADR)", H.resolve_name("TAIWAN SEMICONDUCTOR-SP ADR", nix)[0] == "TSM")
check("지수 문서가 티커 명시한 이름(SPCX)", H.resolve_name("SPACE EXPLORATION TECHN-CL A", nix) == ("SPCX", "index_file"))
check("모르면 (None, none)", H.resolve_name("NO SUCH CO", nix) == (None, "none"))

# ---- 10. look-through ----
lt = H.lookthrough([(76.2, [{"n": "Newmont", "t": "NEM", "w": 10.0, "ts": "issuer_file"}, {"n": "Foreign Gold", "t": None, "w": 5.0}]), (23.8, [{"n": "Newmont", "t": "NEM", "w": 2.0}, {"n": "Foreign Gold", "t": None, "w": 4.0}])])
d = {x["n"]: x["w"] for x in lt}
check("look-through: 지수 비중 × 펀드 비중, 같은 종목 합산", abs(d["Newmont"] - (7.62 + 0.476)) < 1e-9 and abs(d["Foreign Gold"] - (3.81 + 0.952)) < 1e-9 and len(lt) == 2, d)

# ---- 11. build(): SMHU/XLCU 펀드 대체 · GDXU 합성 · 실패 시 직전값(stale) · ETN 이름→티커 ----
tmp = Path(tempfile.mkdtemp()); (tmp / "data").mkdir()
yaml.safe_dump({"products": {
    "SPXL": {"type": "ETF", "top_constituents": {"basis": "1x ETF SPY 상위 보유"}}, "TQQQ": {"type": "ETF", "top_constituents": {"basis": "1x ETF QQQ 상위 보유"}},
    "SMHU": {"type": "ETN"}, "XLCU": {"type": "ETN"}, "GDXU": {"type": "ETN"}, "FNGU": {"type": "ETN"}}}, open(tmp / "data" / "products.yaml", "w"))
yaml.safe_dump({"products": {
    "SMHU": {"index": {"constituents": {"as_of": "2026-10-08", "items": [{"name": "VANECK SEMICONDUCTOR ETF", "weight_pct": 100.0}]}}},
    "GDXU": {"index": {"constituents": {"as_of": "2026-10-08", "items": [{"name": "VANECK GOLD MINERS ETF", "weight_pct": 76.2}, {"name": "VANECK JUNIOR GOLD MINERS", "weight_pct": 23.8}]}}},
    "FNGU": {"index": {"constituents": {"as_of": "2026-10-08 start-of-day", "items": [{"name": "MICRON TECHNOLOGY INC", "weight_pct": 11.0}, {"name": "UNKNOWN WIDGET CORP", "weight_pct": 9.0}]}}}}}, open(tmp / "data" / "index_specs.yaml", "w"))
H.DATA, H.LOCAL = tmp / "data", tmp / "local"
def mk(*pairs): return [{"n": n, "t": t, "w": w, "ts": "issuer_file"} for n, t, w in pairs]
FUND = {"SPY": mk(("NVIDIA CORP", "NVDA", 8.0), ("MICRON TECHNOLOGY INC", "MU", 1.0)), "SMH": mk(("Nvidia Corp", "NVDA", 19.6), ("Taiwan Semi", "TSM", 9.3)),
        "XLC": mk(("META", "META", 20.0)), "XLP": mk(("COSTCO", "COST", 10.0)), "GDX": mk(("Newmont", "NEM", 11.0)), "GDXJ": mk(("Alamos", "AGI", 6.0))}
def fetcher(fail=()):
    def f(etf, log=print):
        if etf in fail: raise ConnectionError("boom")
        return {"as_of": "2026-10-08", "rows": [dict(r) for r in FUND[etf]], "src": {"name": f"src {etf}", "url": f"https://x/{etf}"}}
    return f
prev = {"generated": "2026-10-01", "items": {"TQQQ": {"basis": "1x ETF QQQ 보유", "as_of": "2026-10-01", "fetched": "2026-10-01", "total": 1, "scope": "전체", "source": {"name": "old", "url": "o"},
                                                  "items": [{"n": "NVIDIA", "t": "NVDA", "w": 9.0, "ts": "issuer_file", "ex": "NASDAQ", "nv": "NVDA.O"}]}}}
obj, info = H.build(prev, lambda *a: None, fetcher=fetcher(fail=("QQQ",)), do_enrich=False)
it = obj["items"]
check("37종 구조: 모든 종목 키 존재·구성 0건 없음", set(it) == {"SPXL", "TQQQ", "SMHU", "XLCU", "GDXU", "FNGU"} and all(e["items"] for e in it.values()), list(it))
check("실패한 ETF(QQQ)는 직전 값 유지 + stale:true + as_of 그대로", it["TQQQ"].get("stale") is True and it["TQQQ"]["as_of"] == "2026-10-01" and it["TQQQ"]["items"][0]["nv"] == "NVDA.O")
check("정상 항목에는 stale 키 없음", "stale" not in it["SPXL"] and "stale" not in it["SMHU"])
check("SMHU → SMH 보유 대체 + basis 문구", it["SMHU"]["basis"] == "SMH 보유(지수가 이 펀드를 추종)" and it["SMHU"]["total"] == 2 and it["SMHU"]["items"][0]["t"] == "NVDA")
check("XLCU → XLC 보유(products.yaml 에 없는 index_specs 라도 펀드 경로 우선)", it["XLCU"]["basis"].startswith("XLC 보유") and it["XLCU"]["items"][0]["t"] == "META")
check("GDXU look-through 합성", it["GDXU"]["total"] == 2 and abs(it["GDXU"]["items"][0]["w"] - round(0.762 * 11.0, 3)) < 1e-9 and "GDX·GDXJ" in it["GDXU"]["basis"], it["GDXU"])
check("ETN 지수 구성: 이름→티커(issuer_file), 모르는 이름은 t=None", [(x["t"], x["ts"]) for x in it["FNGU"]["items"]] == [("MU", "issuer_file"), (None, "none")] and it["FNGU"]["basis"] == "지수 구성종목", it["FNGU"]["items"])
check("1x ETF 항목: basis·fetched·source", it["SPXL"]["basis"] == "1x ETF SPY 보유" and it["SPXL"]["fetched"] == H.today() and it["SPXL"]["source"]["name"] == "src SPY")
check("실패 요약에 QQQ", "QQQ" in info["fails"] and "TQQQ" in info["stale"])
# 직전 값조차 없는 경우에도 빈 구성으로 내보내지 않음(항목 누락으로 드러난다)
obj2, info2 = H.build({}, lambda *a: None, fetcher=fetcher(fail=("QQQ",)), do_enrich=False)
check("직전 값 없는 실패는 빈 구성 항목을 만들지 않는다", "TQQQ" not in obj2["items"] and "TQQQ" in info2["stale"])

# ---- 12. enrich: 거래소·네이버 검증 ----
def fake_http(url, headers=None, data=None, retries=2, timeout=60):
    code = urllib.parse.unquote(url.split("/stock/")[1].split("/basic")[0])
    good = {"AMD.O": ("Advanced Micro Devices  Inc.", "NSQ"), "JPM": ("JPMorgan Chase & Co.", "NYS"), "ABBV.K": ("AbbVie Inc.", "NYS"), "BRKb": ("Berkshire Hathaway Inc Class B", "NYS"), "WRONG": ("Totally Different Corp", "NYS"), "WAB": ("Westinghouse Air Brake Technologies Corp", "NYS")}
    if code in good: return json.dumps({"reutersCode": code, "stockNameEng": good[code][0], "stockExchangeType": {"code": good[code][1]}}).encode()
    raise urllib.error.HTTPError(url, 409, "Not Exist Master", {}, None)
import urllib.parse
H.http_get = fake_http
H.yf_exchange = lambda t, c, d: {"AMD": "NMS", "JPM": "NYQ", "BRK.B": "NYQ", "NOPE": "NMS", "WRONG": "NMS", "WAB": "NYQ", "ABBV": "NYQ"}.get(t)
ent = {"A": {"items": [{"n": "ADVANCED MICRO DEVICES", "t": "AMD"}, {"n": "JPMORGAN CHASE & CO", "t": "JPM"}, {"n": "BERKSHIRE HATHAWAY INC CL B", "t": "BRK.B"},
                       {"n": "No Such Co", "t": "NOPE"}, {"n": "Wrong Name Inc", "t": "WRONG"}, {"n": "WABTEC CORP", "t": "WAB"}, {"n": "ABBVIE INC", "t": "ABBV"}, {"n": "Foreign Gold", "t": None}]}}
st = H.enrich(ent, 60, lambda *a: None)
g = {x["n"]: (x["ex"], x["nv"]) for x in ent["A"]["items"]}
check("enrich: 나스닥 AMD → (NASDAQ, AMD.O)", g["ADVANCED MICRO DEVICES"] == ("NASDAQ", "AMD.O"), g)
check("enrich: NYSE JPM → (NYSE, JPM)", g["JPMORGAN CHASE & CO"] == ("NYSE", "JPM"))
check("enrich: 점 티커 BRK.B → BRKb", g["BERKSHIRE HATHAWAY INC CL B"] == ("NYSE", "BRKb"))
check("enrich: NYSE 인데 접미 없는 코드가 409 면 .K 로 (ABBV → ABBV.K)", g["ABBVIE INC"] == ("NYSE", "ABBV.K"), g["ABBVIE INC"])
check("enrich: 네이버에 없으면 nv=None (ex 는 유지)", g["No Such Co"] == ("NASDAQ", None))
check("enrich: 이름 불일치는 nv=None", g["Wrong Name Inc"][1] is None and st["naver_name_mismatch"] == 1, (g["Wrong Name Inc"], st))
check("enrich: 이름은 달라도 거래소 일치(WAB)면 인정", g["WABTEC CORP"] == ("NYSE", "WAB") and st["naver_name_by_exchange"] == 1, (g["WABTEC CORP"], st))
check("enrich: 이름·거래소 모두 다르면 거절(WRONG: yf NASDAQ ≠ 네이버 NYSE)", g["Wrong Name Inc"][1] is None)
check("enrich: 티커 없는 항목은 ex/nv 모두 None", g["Foreign Gold"] == (None, None))
cache = json.load(open(H.LOCAL / "naver_cache.json"))
check("네이버 결과 캐시 저장(유효·무효 모두)", cache["AMD.O"]["ok"] is True and cache["NOPE.O"]["ok"] is False and "at" in cache["AMD.O"])
calls = []
def counting_http(url, **k): calls.append(url); return fake_http(url, **k)
H.http_get = counting_http
ent2 = {"A": {"items": [{"n": "ADVANCED MICRO DEVICES", "t": "AMD"}, {"n": "No Such Co", "t": "NOPE"}]}}
H.enrich(ent2, 60, lambda *a: None)
check("재실행은 캐시로 네이버 재호출 0", calls == [], calls)

# ---- 13. dump / 0건 가드 ----
p = tmp / "h.json"; H.dump({"generated": "2026-10-09", "items": {"SPXL": e}}, p)
back = json.load(open(p, encoding="utf-8"))
check("dump 왕복(한 줄 항목 형식 포함)", back["items"]["SPXL"]["items"] == e["items"] and back["items"]["SPXL"]["total"] == 150 and back["generated"] == "2026-10-09")
print(f"\n{ok} PASS / {len(bad)} FAIL")
if bad: print("FAILED:", bad); sys.exit(1)
