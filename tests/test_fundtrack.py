"""MM-FUNDTRACK-20261023 단위 테스트 — 펀드추종 1x(펀드 가격 직접)·지수 N일 보정 표시 문턱(N≥2)·거래량 극소 제외 유니버스·복귀 점검.
네트워크 0·텔레그램 0. python3 tests/test_fundtrack.py"""
import sys, json, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np, pandas as pd
import mm_lib as L, mm_tailetn as TE, mm_thinwatch as TW, mm_site, mm_proxy, mm_idxhist, mm_nasdaq
ok = 0; bad = []
def check(name, cond, detail=""):
    global ok
    if cond: ok += 1; print("PASS", name)
    else: bad.append(name); print("FAIL", name, detail)
L.log = lambda m, name="daily": None
D = ROOT / "data"
uni = pd.read_csv(D / "universe.csv")

# ── §1 펀드추종 1x = 펀드 가격 직접 (전 구간)
r = uni[uni.ticker == "SMHU"].iloc[0]
check("SMHU 의 1x = SMH(펀드 가격 직접) — 공식 지수 레벨 키(IDX_SEMIS)가 아님", r.proxy == "SMH" and "펀드" in r.proxy_disp and "IDX_" not in r.proxy)
specs = json.load(open(D / "proxy_specs.json", encoding="utf-8"))["specs"]
check("지수 피드(proxy_specs)에서 IDX_SEMIS·IDX_VXLCF·IDX_VXLPF 제거", not any(k in specs for k in ("IDX_SEMIS", "IDX_VXLCF", "IDX_VXLPF")))
check("합성 키(mm_proxy.synthetic_keys)에 3종 없음", not ({"IDX_SEMIS", "IDX_VXLCF", "IDX_VXLPF"} & set(mm_proxy.synthetic_keys(D))))
check("꼬리 소스 수신 목록(etf_tr SMH/XLC/XLP) 없음", not ({"SMH", "XLC", "XLP"} & set(mm_proxy.tail_fetch_tickers(D))))
ft = json.load(open(D / "fund_track.json", encoding="utf-8"))["items"]
check("fund_track.json: SMHU→SMH·XLCU→XLC·XLPU→XLP", {k: v["fund"] for k, v in ft.items()} == {"SMHU": "SMH", "XLCU": "XLC", "XLPU": "XLP"})
check("fund_track_proxies() = {SMH, XLC, XLP}", L.fund_track_proxies() == {"SMH", "XLC", "XLP"})
need = set(L.need_tickers())
check("수신 대상에 SMH(전 이력) 포함·IDX_SEMIS 없음", "SMH" in need and "IDX_SEMIS" not in need)
ih = mm_idxhist.load_history()
check("지수 이력 표(index_history)에서 3종 제외", not ({"SMHU", "XLCU", "XLPU"} & set(ih)))
pi = pd.read_csv(D / "product_info.csv").set_index("ticker")
check("product_info 경로 라벨 = 펀드추종(펀드 가격 직접)·연장 없음", all("펀드추종" in str(pi.loc[t, "onex_path"]) and pd.isna(pi.loc[t, "onex_extension"]) for t in ("SMHU", "XLCU", "XLPU")))
import yaml
isp = yaml.safe_load(open(D / "index_specs.yaml", encoding="utf-8"))["products"]
check("index_specs: 3종 path_label 펀드추종·key=펀드·연장 null", all(isp[t]["onex"]["path_label"] == "펀드추종(펀드 가격 직접)" and isp[t]["onex"]["key"] == f for t, f in (("SMHU", "SMH"), ("XLCU", "XLC"), ("XLPU", "XLP"))) and all(isp[t]["onex"]["extension"] is None for t in ("SMHU", "XLCU", "XLPU")))

# 꼬리 보정 경로 제외 — 펀드 봉이 하루 늦어도 보정 행을 만들지 않는다
N = 60; idx = pd.bdate_range(end="2026-10-08", periods=N)
def mkdf(n, seed, vol=0.01, v=1e6):
    rr = np.random.default_rng(seed).normal(0, vol, n); c = 100 * np.cumprod(1 + rr)
    return pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Adj Close": c, "Volume": v, "Dividends": 0.0, "Stock Splits": 0.0}, index=idx[:n])
def write(raw, name, h):
    h = h.copy(); h.index = h.index.tz_localize("America/New_York"); h.index.name = "Date"; h.to_csv(raw / f"{name}.csv")
with tempfile.TemporaryDirectory() as td:
    raw = Path(td); write(raw, "SPY", mkdf(N, 1)); write(raw, "FUND", mkdf(N - 1, 2)); write(raw, "ETN3", mkdf(N, 3, 0.03))
    u = pd.DataFrame({"ticker": ["ETN3"], "proxy": ["FUND"]})
    before = (raw / "FUND.csv").read_bytes()
    i0 = TE.fill(idx[-1], u, raw, log=lambda m: None, write=True, skip_proxies={"FUND"})
    check("펀드추종 proxy 는 꼬리 보정 제외: info 비어 있음·RAW 바이트 불변(보정 행 0)", i0 == {} and (raw / "FUND.csv").read_bytes() == before)
    i1 = TE.fill(idx[-1], u, raw, log=lambda m: None, write=False)
    check("대조군: skip 없으면 같은 입력이 3배÷3 으로 1일 보정됨", i1.get("FUND", {}).get("status") == "filled" and i1["FUND"]["days"] == 1)
check("apply_tail_etn 이 fund_track_proxies 를 skip 으로 넘김(소스 배선)", "skip_proxies=fund_track_proxies()" in (ROOT / "scripts" / "mm_lib.py").read_text(encoding="utf-8"))

# ── §2 지수 N일 보정 표시 문턱 — 1일은 기록만, 2일 이상 표시
cfg = {"E1": {"threshold": 252}, "E2": {"threshold": 0.3}, "E4": {"beta_min": 2.7, "beta_max": 3.3, "r2_min": 0.85}, "E6": {"threshold": 1000}}
b = lambda n: L.badges_for(500, 5.0, 0, 3.0, 0.99, 252, cfg, tailn=n)
check("badges_for: tailn=1 → 배지 없음(1일 보정은 src 기록만)", b(1) == [])
check("badges_for: tailn=2 → 지수보정2", b(2) == ["지수보정2"])
check("badges_for: tailn=3 → 지수보정3", b(3) == ["지수보정3"])
check("badges_for: tailn=0 → 배지 없음", b(0) == [])
check("TAIL_BADGE_MIN = 2", L.TAIL_BADGE_MIN == 2)
check("4일 이상은 보정 자체를 안 한다(⚠) — MAX_GAP=3", TE.MAX_GAP == 3)
check("가이드 문구: 2~3일만 표시·1일은 기록만", "N이 2~3일일 때만 표시" in (ROOT / "scripts" / "mm_guide.py").read_text(encoding="utf-8"))

# ── §3 거래량 극소 제외 — 유니버스 밖·제외 목록·복귀 점검
check("유니버스에서 XLCU·XLPU 제거(35종)", "XLCU" not in set(uni.ticker) and "XLPU" not in set(uni.ticker) and len(uni) == 35, len(uni))
th = json.load(open(D / "thin_excluded.json", encoding="utf-8"))["items"]
check("thin_excluded.json = XLCU·XLPU, 규칙 E7", [x["ticker"] for x in th] == ["XLCU", "XLPU"] and all(x["rule"] == "E7" and x["reason"] == "거래량 극소" for x in th))
el = L.load_yaml_simple(D / "eligibility.yaml")
check("eligibility.yaml E7: threshold 1000·return_days 20·E6 와 같은 문턱", el["E7"]["threshold"] == 1000 and el["E7"]["return_days"] == 20 and el["E7"]["threshold"] == el["E6"]["threshold"] == mm_nasdaq.LOW_VOL_THRESHOLD)
rows = mm_site.thin_exclusion_rows()
check("제외 목록 행: 사유에 '거래량 극소(발행사 공시 아님)'·링크 없음", len(rows) == 2 and all("거래량 극소(발행사 공시 아님)" in s and u_ == "" for _, s, u_ in rows) and [t for t, _, _ in rows] == ["XLCU", "XLPU"], rows)
_xr, _held = mm_site.exclusion_rows(pd.DataFrame([dict(ticker="A", table="순위")]), {"excluded": {}})
check("exclusion_rows 가 thin 행을 포함", [t for t, _, _ in _xr] == ["XLCU", "XLPU"])
check("수신 유지: need_tickers 에 XLCU·XLPU(3배) 포함(복귀 점검용 거래량 수신 계속)", {"XLCU", "XLPU"} <= need)
check("mm_nasdaq 수신 대상에 thin 포함", {"XLCU", "XLPU"} <= set(mm_nasdaq.etn_tickers()) and {"XLCU", "XLPU"} <= set(mm_nasdaq.three_x_tickers()))
wk = (ROOT / "scripts" / "mm_weekly_scan.py").read_text(encoding="utf-8")
check("주간 스캔: 복귀 점검 줄 배선·신상품 재발견 방지", "mm_thinwatch.check()" in wk and "known_tick|=set(L.thin_tickers())" in wk)
check("자동 복귀 코드 없음(universe.csv 쓰기 없음)", "universe.csv" not in (ROOT / "scripts" / "mm_thinwatch.py").read_text(encoding="utf-8").replace("universe.csv 에 행을 되돌리는", ""))

# 복귀 조건: trailing 20일 평균 ≥1000 이 20거래일 연속
def run_tw(vols, n_days=120):
    ix = pd.bdate_range(end="2026-10-08", periods=n_days)                   # SPY 달력. 종목은 첫 봉(= vols 의 첫 값)부터 끝까지 매 거래일 봉이 있다
    h = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": np.asarray(vols, float)}, index=ix[-len(vols):])
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td); write(raw, "SPY", pd.DataFrame({"Close": 1.0, "Volume": 1.0}, index=ix)); write(raw, "TT", h)
        return TW.check([{"ticker": "TT"}], raw, threshold=1000, need=20)[0]
r0 = run_tw([2000] * 39)                                   # 첫 평균이 생기는 날(20번째 봉)부터 20일 연속 ≥1000 → 정확히 20일
check("거래량 2000주 39봉(첫 평균 20일째부터 20일 연속) → 연속 20·복귀 후보", r0["streak"] == 20 and r0["candidate"], r0)
r1 = run_tw([2000] * 38)
check("연속 19일 → 후보 아님", r1["streak"] == 19 and not r1["candidate"], r1)
r2 = run_tw([2000] * 60)
check("연속 41일 → 후보", r2["streak"] == 41 and r2["candidate"], r2)
r3 = run_tw([2000] * 50 + [0] * 5)
check("최근 5일 거래 없음이어도 20일 평균(1,500)이 1000 이상이면 연속 유지(평균 기준)", r3["streak"] == 36 and r3["candidate"] and abs(r3["avg20"] - 1500) < 1e-9, r3)
r4 = run_tw([100] * 60)
check("거래량 100주 → 연속 0·후보 아님", r4["streak"] == 0 and not r4["candidate"] and abs(r4["avg20"] - 100) < 1e-9, r4)
r5 = run_tw([2000] * 40 + [0] * 25)
check("거래 끊김(0 25일) → 20일 평균이 1000 미만으로 내려가면 연속 0", r5["streak"] == 0 and not r5["candidate"], r5)
check("line(): 후보 없음 문구", "복귀 후보: 없음" in TW.line([r4]) and "TT 20일 평균 100주(연속 0/20일)" in TW.line([r4]))
check("line(): 후보 있으면 티커·'자동 복귀 없음'", "복귀 후보: TT" in TW.line([r0]) and "자동 복귀 없음" in TW.line([r0]))
check("line(): 제외 종목 없으면 None", TW.line([]) is None)
# 페이지 모듈: 유니버스 밖 종목 페이지 정리
with tempfile.TemporaryDirectory() as td:
    old = mm_site.DOCS; mm_site.DOCS = Path(td); (Path(td) / "products").mkdir()
    for t in ("AAA", "XLCU"): (Path(td) / "products" / f"{t}.html").write_text("x")
    gone = mm_site.prune_product_pages(pd.DataFrame({"ticker": ["AAA"]})); mm_site.DOCS = old
    check("prune_product_pages: 유니버스 밖 종목 페이지만 삭제", gone == ["XLCU"] and (Path(td) / "products" / "AAA.html").exists() and not (Path(td) / "products" / "XLCU.html").exists())
# 소개 문구 재생성 방지: 유니버스 밖 종목은 ensure 대상 아님
import mm_page_text as PT
src = (ROOT / "scripts" / "mm_page_text.py").read_text(encoding="utf-8")
check("mm_page_text.ensure: 유니버스 밖 종목은 건너뜀(발행사 폴백 해시 불일치 → 불필요한 LLM 호출 방지)", "if active is not None and t not in active: continue" in src)
prods = PT.load_products(); items = json.load(open(D / "products_page.json", encoding="utf-8"))["items"]
iu = dict(uni[["ticker", "issuer"]].values)
check("SMHU 소개·필드 입력 해시가 products.yaml 변경(onex 라벨) 후에도 저장값과 동일 → LLM 재생성 0", PT.input_hash(prods["SMHU"], iu["SMHU"]) == items["SMHU"]["hash"] and PT.intro_hash(prods["SMHU"], iu["SMHU"]) == items["SMHU"]["intro_hash"])
print(f"{ok} PASS, {len(bad)} FAIL"); sys.exit(1 if bad else 0)
