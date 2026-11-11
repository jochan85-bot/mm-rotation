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
ok("9절 변경 이력 2026-11-11 2줄(가격 차트 추가 + 표시 보정·축 서식)", g.count("<tr><td>2026-11-11</td>") == 2 and "시세 오류 봉 2건" in g)

# ---- MM-PRICE-CHART-FIX-20261111: 시세 오류 봉 표시 보정 · 가격 서식 · 축 여백 · 후보 스캔 ----
# 17. 보정 목록: 실제 data/chart_overrides.yaml — 2건, 기록한 보정값 = 규칙 결과, 현재 차트 데이터와 원값 일치
ovs = M.load_overrides()
ok("보정 목록 2건(DFEN 2024-06-03 · NAIL 2020-03-16, 저가)", sorted((x["ticker"], x["date"], x["field"]) for x in ovs) == [("DFEN", "2024-06-03", "low"), ("NAIL", "2020-03-16", "low")])
ok("보정 목록 항목마다 원값·보정값·사유", all(x["reason"] and x["original"] > 0 and x["corrected"] > 0 for x in ovs))
for x in ovs:
    j = json.loads((M.OUT / f"{x['ticker']}.json").read_text(encoding="utf-8")); df0 = M.from_obj(j); r0 = df0.loc[pd.Timestamp(x["date"])]
    act, skip = M.active_overrides(x["ticker"], j=j, ovs=ovs)
    ok(f"{x['ticker']} 원값 일치·적용 1건", act == [{"d": x["date"], "f": "l"}] and not skip, (act, skip))
    df1 = M.apply_overrides(df0, act); r1 = df1.loc[pd.Timestamp(x["date"])]
    ok(f"{x['ticker']} 보정값 = 기록값, 시가·종가·고가 불변", r1.l == x["corrected"] and r1.o == r0.o and r1.c == r0.c and r1.h == r0.h and r0.l == x["original"], (r0.tolist(), r1.tolist()))
    ok(f"{x['ticker']} 원본 DataFrame 불변(사본에만 적용)", df0.loc[pd.Timestamp(x["date"])].l == x["original"])
    ok(f"{x['ticker']} 보정 봉 외 전부 동일", df1.drop(index=pd.Timestamp(x["date"])).equals(df0.drop(index=pd.Timestamp(x["date"]))))
# 원값이 현재 데이터와 다르면(원천이 바뀜) 미적용 + 사유
bad_ov = [dict(ovs[0], original=ovs[0]["original"] * 2)]
act, skip = M.active_overrides(bad_ov[0]["ticker"], ovs=bad_ov)
ok("원값 불일치 → 미적용 + 사유", act == [] and len(skip) == 1 and "원값" in skip[0], skip)
act, skip = M.active_overrides("DFEN", ovs=[dict(ovs[0], date="1999-01-04")])
ok("해당 날짜 봉 없음 → 미적용", act == [] and "봉 없음" in skip[0], skip)
# 규칙 단위: 범위 안이면 그대로, 고가 필드도 대칭
ok("clip_bar 저가 범위 밖 → min(시,종)", M.clip_bar(10, 12, 1, 8, "low") == (12, 8))
ok("clip_bar 저가가 이미 범위 끝 → 그대로·지정 안 한 고가 불변", M.clip_bar(10, 12, 8, 8, "low") == (12, 8))
ok("clip_bar 고가 범위 밖 → max(시,종)", M.clip_bar(10, 99, 7, 8, "high") == (10, 7))
# 임시 yaml 로더(형식 오류 항목 무시)
ty = TMP / "ov.yaml"; ty.write_text('overrides:\n  - {ticker: AAA, date: "2026-01-06", field: low, original: 1, corrected: 2, reason: r}\n  - {ticker: BBB, date: "2026-01-06", field: close, original: 1, corrected: 2}\n', encoding="utf-8")
ok("로더: 허용 필드(low/high)만", [x["ticker"] for x in M.load_overrides(ty)] == ["AAA"])
ok("로더: 파일 없음 → []", M.load_overrides(TMP / "none.yaml") == [])

# 18. 차트 JSON 원본 무변경: 보정 기능은 docs/data/charts 를 쓰지 않는다(소스 정적 확인 + update_one 결과에 보정 없음)
csrc = (ROOT / "scripts" / "mm_charts.py").read_text(encoding="utf-8")
ok("update_one·to_obj 경로에 보정 호출 없음", "apply_overrides" not in csrc.split("def update_one")[1].split("def calendar_events")[0].split("OVR =")[0])
src = mk_src("OVT", walk(60, seed=7)); outo = TMP / "out_ov"; M.update_one("OVT", src=src, out=outo)
b0 = (outo / "OVT.json").read_bytes(); M.daily_update(log=lambda *a: None, tickers=["OVT"], src=src, out=outo, cal=False)
ok("daily_update 후 차트 파일 = 원천 그대로(보정 목록과 무관)", (outo / "OVT.json").read_bytes() == b0)

# 19. 렌더러: 보정 종목만 data-ov + 문구 「시세 오류 봉 N건 보정」, 나머지는 기존 문구
hd = mm_site.price_chart_html("DFEN"); hs = mm_site.price_chart_html("SOXL")
ok("DFEN data-ov(날짜·필드)", 'data-ov="[{&quot;d&quot;:&quot;2024-06-03&quot;,&quot;f&quot;:&quot;l&quot;}]"' in hd)
ok("DFEN 문구 「분할 조정 가격 · 시세 오류 봉 1건 보정 · 참고용」", '<div class="chartnote">분할 조정 가격 · 시세 오류 봉 1건 보정 · 참고용</div>' in hd)
ok("SOXL data-ov 없음·기존 문구", "data-ov" not in hs and '<div class="chartnote">분할 조정 가격 · 참고용</div>' in hs)
ok("보정 문구 종목 = 목록 종목(37종 중 DFEN·NAIL 만)", sorted(t for t in M.universe() if "시세 오류 봉" in mm_site.price_chart_html(t)) == ["DFEN", "NAIL"])

# 20. pricechart.js: fix()(보정)·주봉은 보정 후 집계·fmt()(가격 서식)를 node 로 그대로 실행
js = (ROOT / "docs" / "assets" / "pricechart.js").read_text(encoding="utf-8")
ok("축: 맨 위·아래 잘린 눈금 글자 숨김(entireTextOnly)", "entireTextOnly: true" in js)
ok("축: 아래 여백(로고 자리) scaleMargins", "scaleMargins: { top: 0.08, bottom: 0.16 }" in js)
ok("로고 표기 유지(attributionLogo: true)", "attributionLogo: true" in js)
ok("가격 서식 함수 1개를 축·십자선·판독 줄 공용(priceFormatter: fmt)", "priceFormatter: fmt" in js and js.count("function fmt(") == 1)
if node:
    import re as _re
    grab = lambda name: _re.search(r"  function " + name + r"\(.*?\n  \}\n", js, _re.S).group(0)
    code = _re.search(r"  function ymdKey\(t\).*?\n", js).group(0) + grab("fix") + grab("weekly") + grab("fmt") + r"""
const t=(s)=>Date.UTC(+s.slice(0,4),+s.slice(5,7)-1,+s.slice(8,10))/1000;
const a=[{time:t('2024-05-31'),open:27.2,high:28.56,low:27.19,close:28.56},{time:t('2024-06-03'),open:28.75,high:29.28,low:0.27,close:10.17},{time:t('2024-06-04'),open:28.76,high:29.01,low:28.19,close:28.93}];
const f=fix(a,[{d:'2024-06-03',f:'l'}]); const w=weekly(f); const w0=weekly(a);
const g=fix([{time:t('2024-06-03'),open:5,high:9,low:4,close:6}],[{d:'2024-06-03',f:'h'},{d:'2024-06-03',f:'l'}]);
const cases=[4785.6,1234.567,56.06,1,0.9996,0.999,0.272,0.2,0.17708,0.0123,0.0000123,0];
console.log(JSON.stringify({f,w,w0,orig:a[1].low,same:fix(a,[])===a,g,fm:cases.map(fmt)}));"""
    r = json.loads(subprocess.run([node, "-e", code], capture_output=True, text=True, timeout=30).stdout)
    ok("JS 보정: 저가 0.27 → 10.17(시가·종가·고가 불변)", r["f"][1] == {"time": r["f"][1]["time"], "open": 28.75, "high": 29.28, "low": 10.17, "close": 10.17}, r["f"][1])
    ok("JS 보정: 원본 배열 불변", r["orig"] == 0.27 and r["same"] is True)
    ok("JS 주봉 = 보정 후 일봉 집계(저가 10.17, 미보정이면 0.27)", r["w"][-1]["low"] == 10.17 and r["w0"][-1]["low"] == 0.27, (r["w"], r["w0"]))
    ok("JS 보정: 고가·저가 동시 필드 / 범위 안 값", r["g"][0]["high"] == 6 and r["g"][0]["low"] == 5)
    ok("JS·Python 보정 규칙 일치(DFEN 기록값)", r["f"][1]["low"] == [x for x in ovs if x["ticker"] == "DFEN"][0]["corrected"])
    ok("JS fmt: 1 이상 소수 2자리·쉼표, 1 미만 유효숫자 3자리",
       r["fm"] == ["4,785.60", "1,234.57", "56.06", "1.00", "1.00", "0.999", "0.272", "0.200", "0.177", "0.0123", "0.0000123", "0.00"], r["fm"])
else:
    print("SKIP node 없음")

# 21. 후보 스캔 양성 대조: 실제 37종 — DFEN 2024-06-03 은 잡히고(배수 > 10), NAIL 2020-03-16 은 고저폭 기준으로는 안 잡힌다(정체 봉 유형이라 폭이 평범)
hits = {}
for t in M.universe():
    for x in M.range_outliers(M.from_obj(json.loads((M.OUT / f"{t}.json").read_text(encoding="utf-8")))): hits[(t, x["date"])] = x
ok("스캔 양성 대조: DFEN 2024-06-03 검출", ("DFEN", "2024-06-03") in hits and hits[("DFEN", "2024-06-03")]["mult"] > 10, hits.get(("DFEN", "2024-06-03")))
ok("스캔: NAIL 2020-03-16 은 이 기준 밖(알려진 한계)", ("NAIL", "2020-03-16") not in hits)
ok("스캔: 합성 이력 — 튄 봉 1개만 검출", [x["date"] for x in M.range_outliers(pd.DataFrame({"o": [10.0] * 41, "h": [10.5] * 20 + [10.5] + [10.5] * 20, "l": [9.5] * 20 + [0.3] + [9.5] * 20, "c": [10.0] * 41}, index=pd.bdate_range("2026-01-05", periods=41)))] == ["2026-02-02"])
z = pd.DataFrame({"o": [10.0] * 30, "h": [10.0] * 15 + [11.0] + [10.0] * 14, "l": [10.0] * 30, "c": [10.0] * 30}, index=pd.bdate_range("2026-01-05", periods=30))
ok("스캔: 분모 0(정체 봉 연속) → note 분모0·배수 inf", [(x["note"], x["mult"]) for x in M.range_outliers(z)] == [("분모0", float("inf"))])

shutil.rmtree(TMP, ignore_errors=True)
print(f"{P} PASS / {F} FAIL")
sys.exit(1 if F else 0)
