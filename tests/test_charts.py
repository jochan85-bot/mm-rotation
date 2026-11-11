"""MM-PRICE-CHART-20261111 — 종목 페이지 가격 차트 데이터(scripts/mm_charts.py)·렌더(mm_site.price_chart_html)·일일 훅·가이드 시험.
합성 원천 CSV 를 임시 폴더에 만들어 쓰므로 live 파일 쓰기 0 (run_guarded.py 로 돌려도 통과해야 한다)."""
import sys, json, re, ast, shutil, tempfile, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np, pandas as pd
import mm_charts as M

P = F = 0
def ok(name, cond, info=""):
    global P, F
    if cond: P += 1; print("PASS", name)
    else: F += 1; print("FAIL", name, info)

TMP = Path(tempfile.mkdtemp(prefix="mm_charts_test_"))
COLS = ["Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends", "Stock Splits", "Capital Gains"]

def mk_src(t, closes, start="2026-01-05", splits=None, src=None, ohl=None):
    """평일 연속 봉 CSV(야후 정제본 형식). splits = {날짜: 배율}"""
    src = Path(src or TMP / "src"); src.mkdir(parents=True, exist_ok=True)
    d = pd.bdate_range(start, periods=len(closes))
    c = np.asarray(closes, float)
    o = c * 0.99 if ohl is None else ohl[0]; h = c * 1.02 if ohl is None else ohl[1]; l = c * 0.97 if ohl is None else ohl[2]
    df = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Adj Close": c, "Volume": 1000, "Dividends": 0.0, "Stock Splits": 0.0, "Capital Gains": 0.0}, index=d)
    for k, v in (splits or {}).items(): df.loc[pd.Timestamp(k), "Stock Splits"] = v
    df.index = df.index.tz_localize("America/New_York"); df.index.name = "Date"
    df[COLS].to_csv(src / f"{t}.csv")
    return src

def walk(n, p0=20.0, seed=1):
    r = np.random.default_rng(seed).normal(0, 0.02, n); return p0 * np.exp(np.cumsum(r))

# 1. 반올림
ok("q 유효숫자", M.q(56.060001373291016) == 56.06 and M.q(0.6424999833106995) == 0.6425 and M.q(1234.5678) == 1234.57 and M.q(0) is None and M.q(float("nan")) is None)

# 2. 전체 생성 · 왕복
src = mk_src("AAA", walk(300)); out = TMP / "out"
r = M.update_one("AAA", src=src, out=out)
j = json.loads((out / "AAA.json").read_text())
ok("전체 생성 status=new", r["status"] == "new" and r["bars"] == 300, r)
ok("형식 키", set(j) == {"t", "v", "d0", "dt", "o", "h", "l", "c"} and j["dt"][0] == 0 and len(j["c"]) == 300 and j["d0"] == "2026-01-05", list(j))
df, ev, fix = M.read_src("AAA", src)
ok("왕복 일치(from_obj)", M.from_obj(j).index.equals(df.index) and np.allclose(M.from_obj(j).values, df.values))
ok("거래량 미포함", "v" in j and "vol" not in j and "volume" not in j)

# 3. 덧붙임: 원천에 1봉 추가
c = walk(301); mk_src("BBB", c[:300]); M.update_one("BBB", src=src, out=out)
mk_src("BBB", c); r = M.update_one("BBB", src=src, out=out)
full = M.from_obj(json.loads((out / "BBB.json").read_text())); dfb, _, _ = M.read_src("BBB", src)
ok("새 봉 덧붙임 appended=1", r["status"] == "appended" and r["added"] == 1 and r["bars"] == 301, r)
ok("덧붙인 결과 = 전체 생성 결과", full.index.equals(dfb.index) and np.allclose(full.values, dfb.values))
r = M.update_one("BBB", src=src, out=out)
ok("새 봉 없으면 same(쓰기 없음)", r["status"] == "same" and r["added"] == 0, r)

# 4. 야후가 이력을 분할 조정(2:1) → 기존 파일(조정 전)과 일정 비율 불일치 → 전체 재생성 + split 표시
c = walk(200, 40.0, 3); mk_src("CCC", c); M.update_one("CCC", src=src, out=out)
mk_src("CCC", np.r_[c / 2.0, c[-1] / 2.0 * 1.01], splits={str(pd.bdate_range("2026-01-05", periods=201)[-1].date()): 2.0})
r = M.update_one("CCC", src=src, out=out)
ok("이력 재조정 감지 → rebuilt + split", r["status"] == "rebuilt" and r.get("split") is True and "재조정" in r["note"], r)
cc = M.from_obj(json.loads((out / "CCC.json").read_text())).c
ok("재생성 후 인접 봉 점프 없음", float((cc / cc.shift(1)).dropna().sub(1).abs().max()) < 0.2)

# 5. 분할 반영 지연(이력 미조정 + 분할 후 봉 3:1 점프) → 보류, 기존 파일 유지
c = walk(120, 90.0, 4); mk_src("DDD", c); M.update_one("DDD", src=src, out=out)
before = (out / "DDD.json").read_bytes()
sd = pd.bdate_range("2026-01-05", periods=121)[-1]
mk_src("DDD", np.r_[c, c[-1] / 3.0 * 0.99], splits={str(sd.date()): 3.0})
r = M.update_one("DDD", src=src, out=out)
ok("분할 미반영 새 봉 → held", r["status"] == "held" and "분할" in r["note"], r)
ok("보류 시 기존 파일 바이트 불변", (out / "DDD.json").read_bytes() == before)
# 캘린더 이벤트만 있는 경우(야후 Stock Splits 열이 아직 비어 있음)도 보류
mk_src("DDD", np.r_[c, c[-1] / 3.0 * 0.99])
r = M.update_one("DDD", src=src, out=out, cal_events={"DDD": [(sd, 3.0)]})
ok("나스닥 캘린더 이벤트로도 held", r["status"] == "held", r)
r = M.update_one("DDD", src=src, out=out)
ok("분할 이벤트 없는 큰 하락은 실제 등락으로 덧붙임", r["status"] == "appended", r)

# 6. 최초 생성인데 원천이 분할 미반영 → 파일 미작성
mk_src("EEE", np.r_[walk(50, 30, 5), walk(50, 30, 5)[-1] / 4 * np.ones(3)], splits={str(pd.bdate_range("2026-01-05", periods=53)[50].date()): 4.0})
r = M.update_one("EEE", src=src, out=out)
ok("최초 생성 + 분할 미반영 → held·파일 없음", r["status"] == "held" and not (out / "EEE.json").exists(), r)

# 7. 중간 봉 삽입(결손 보충) → 전체 재생성
c = walk(80, 10, 6); d = pd.bdate_range("2026-01-05", periods=80)
s1 = mk_src("FFF", c); p = s1 / "FFF.csv"; h = pd.read_csv(p, index_col=0); h.drop(h.index[40]).to_csv(p)
M.update_one("FFF", src=src, out=out); mk_src("FFF", c)
r = M.update_one("FFF", src=src, out=out)
ok("봉 삽입 → rebuilt(날짜 구성 변경)", r["status"] == "rebuilt" and "날짜" in r["note"] and r["bars"] == 80, r)

# 8. 마지막 봉 소폭 정정(분할 아님) → 원천으로 재생성, split 표시 없음
c = walk(60, 25, 7); mk_src("GGG", c); M.update_one("GGG", src=src, out=out)
c2 = c.copy(); c2[-1] *= 1.003; mk_src("GGG", c2)
r = M.update_one("GGG", src=src, out=out)
ok("마지막 봉 정정 → rebuilt·split 아님", r["status"] == "rebuilt" and not r.get("split") and "대조 불일치" in r["note"], r)

# 9. 시가·고가·저가 결손/역전 정리
cl = np.array([10.0, 11.0, 12.0])
mk_src("HHH", cl, ohl=(np.array([np.nan, 11.5, 12.0]), np.array([10.5, 11.2, 12.4]), np.array([9.5, 11.1, 0.0])))
dfh, _, fix = M.read_src("HHH", src)
ok("O 결손→C, H≥max(O,C), L≤min(O,C)·0→C", dfh.o.iloc[0] == 10.0 and dfh.h.iloc[1] == 11.5 and dfh.l.iloc[1] == 11.0 and dfh.l.iloc[2] == 12.0 and fix >= 3, (dfh.values.tolist(), fix))

# 10. daily_update: 종목 단위 실패 격리 + alerts 로그 + 정리(prune)
(out / "ZZZ.json").write_text("{}")
logs = []
res = M.daily_update(log=lambda m, *k: logs.append((m, k[0] if k else "daily")), tickers=["AAA", "NOPE"], src=src, out=out, cal=False)
ok("실패 격리: NOPE=error, AAA 정상", res["NOPE"]["status"] == "error" and res["AAA"]["status"] in ("same", "appended"), res)
ok("오류는 alerts 로그", any(k == "alerts" and "NOPE" in m for m, k in logs), logs)
ok("요약 로그 1줄", sum(1 for m, k in logs if m.startswith("[mm_charts] 가격 차트")) == 1)
ok("유니버스 밖 파일 정리", not (out / "ZZZ.json").exists() and not (out / "BBB.json").exists())

# 11. 실제 원천(37종) 생성 — 임시 폴더로, 용량·봉 수·분할 일치
real = TMP / "real"
if M.SRC.exists():
    res = M.daily_update(log=lambda *a: None, out=real, cal=False, full=True)
    uni = M.universe()
    tot = sum(f.stat().st_size for f in real.glob("*.json"))
    ok("37종 전부 생성", len(uni) == 37 and all(res[t]["status"] == "new" for t in uni), {t: r["status"] for t, r in res.items() if r["status"] != "new"})
    ok("합계 15MB 이하", tot <= 15e6, tot)
    chk = M.check(out=real)
    ok("원천과 전 종목 일치·분할 미반영 0", bool(chk.equal.all()) and all(len(a) == 0 for a in chk.art), chk[~chk.equal].t.tolist())
    pi = pd.read_csv(ROOT / "data" / "product_info.csv").set_index("ticker")
    bad = [t for t in uni if str(chk.set_index("t").loc[t, "first"]) != str(pi.loc[t, "first_bar"]) and t not in ("XLCU", "XLPU")]
    ok("첫 봉 = 상장 첫 거래일(product_info first_bar, XLCU·XLPU 는 나스닥 보충으로 하루 빠름)", not bad, bad)
else:
    print("SKIP 실제 원천 없음")

# 12. 렌더러: 소개 안 차트 컨테이너, 새 절 없음, 버튼·문구·출처
import mm_site
html = mm_site.price_chart_html("SOXL")
ok("컨테이너·티커", 'id="pchart" data-t="SOXL"' in html)
ok("기간 버튼 6개(1개월~전체)·기본 1년", re.findall(r'data-prange="(\w+)"', html) == ["m1", "m3", "m6", "y1", "y3", "all"] and 'class="btn on" data-prange="y1" aria-pressed="true"' in html)
ok("봉 주기 일봉/주봉·기본 일봉", 'data-piv="d" aria-pressed="true">일봉' in html and 'data-piv="w" aria-pressed="false">주봉' in html)
ok("축 전환 버튼", "data-pscale" in html)
ok("차트 아래 한 줄 정확 문구", '<div class="chartnote">분할 조정 가격 · 참고용</div>' in html)
ok("M-score 차트 data-range 와 충돌 없음", "data-range=" not in html)
ok("새 h2 절 없음", "<h2" not in html)
src_site = (ROOT / "scripts" / "mm_site.py").read_text(encoding="utf-8")
ok("출처 표기: NOTICE 문구 + tradingview 링크", "TradingView Lightweight Charts™ · Copyright (с) 2025 TradingView, Inc." in mm_site.PRICE_ATTR and 'href="https://www.tradingview.com/"' in mm_site.PRICE_ATTR)
ok("종목 페이지 스크립트에 pricechart.js", '<script src="../assets/pricechart.js"></script>' in src_site)
body = re.search(r'def build_product\(.*?return pg\(', src_site, re.S).group(0)
ok("가격 차트는 소개 절 안(M-score 차트 다음·구성 절 앞)", body.index("{chart_html}") < body.index("{price_chart_html(t)}") < body.index("<h2>구성</h2>"))

# 13. pricechart.js: 버전 고정·SRI·로고 표기·폴백·lazy(그 종목 파일 1개)
js = (ROOT / "docs" / "assets" / "pricechart.js").read_text(encoding="utf-8")
ok("CDN 버전 고정 5.2.1 + SRI", "lightweight-charts@5.2.1/dist/lightweight-charts.standalone.production.js" in js and "sha384-KkYqTZlM13Zya6fVUF3IGCBOQ1ehFeJVVgxaVvD/0MebineF9EI8Jkd3NnWNChqN" in js and "crossOrigin = 'anonymous'" in js)
ok("attributionLogo 유지", "attributionLogo: true" in js)
ok("불러오기 실패 폴백 문구", "차트를 불러오지 못했습니다" in js)
ok("그 종목 파일 1개만 fetch", js.count("fetch(") == 1 and "'../data/charts/' + T + '.json'" in js)
ok("전체 = 로그 축", "st.log = st.range === 'all'" in js)

# 14. 주봉 집계(node 로 pricechart.js 의 weekly 함수 그대로 실행)
node = shutil.which("node")
if node:
    fn = re.search(r"function weekly\(a\) \{.*?\n  \}\n", js, re.S).group(0)
    days = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-10", "2026-11-11", "2026-11-13", "2026-11-17"]   # 11-09(월) 휴장 가정, 11-12 휴장
    a = [dict(time=int(pd.Timestamp(d, tz="UTC").timestamp()), open=10 + i, high=20 + i, low=5 + i, close=11 + i) for i, d in enumerate(days)]
    code = fn + "process.stdout.write(JSON.stringify(weekly(" + json.dumps(a) + ")));"
    w = json.loads(subprocess.run([node, "-e", code], capture_output=True, text=True, timeout=30).stdout)
    t2d = lambda t: str(pd.Timestamp(t, unit="s").date())
    ok("주봉 3개(월요일 시작, 휴장 주 포함)", [t2d(x["time"]) for x in w] == ["2026-11-02", "2026-11-10", "2026-11-17"], w)
    ok("주봉 O=첫 H=max L=min C=마지막", w[0] == dict(time=a[0]["time"], open=10, high=24, low=5, close=15) and w[1] == dict(time=a[5]["time"], open=15, high=27, low=10, close=18), w)
else:
    print("SKIP node 없음")

# 15. 일일 훅: 후단(build_all 뒤·git_push 앞)·예외 격리
dsrc = (ROOT / "scripts" / "mm_daily.py").read_text(encoding="utf-8")
ok("훅 위치: build_all 뒤·git_push 앞", dsrc.index("mm_site.build_all(") < dsrc.index("mm_charts.daily_update(") < dsrc.index("if push: git_push(T)"))
tree = ast.parse(dsrc)
wrapped = any(isinstance(n, ast.Try) and "mm_charts" in ast.unparse(n.body[0]) and any(ast.unparse(h.type) == "Exception" for h in n.handlers) for n in ast.walk(tree))
ok("훅 예외 격리(try/except Exception)", wrapped)

# 16. 가이드: 설명 단락 + 9절 변경 이력 1줄 + 외부 라이브러리 명시
g = (ROOT / "scripts" / "mm_guide.py").read_text(encoding="utf-8")
ok("가이드 가격 차트 단락", 'id="pricechart"' in g and "외부 라이브러리 1개" in g)
ok("9절 변경 이력 2026-11-11 1줄", g.count("<tr><td>2026-11-11</td>") == 1)

shutil.rmtree(TMP, ignore_errors=True)
print(f"{P} PASS / {F} FAIL")
sys.exit(1 if F else 0)
