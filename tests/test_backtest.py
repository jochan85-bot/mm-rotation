"""MM-BT-CHARTS-20261011 테스트 — 백테스트 페이지 데이터(JSON 스키마·차트 값 = CSV 값)·사유 문구 단축·3줄 제한·docs/data 무변경. python3 tests/test_backtest.py (시스템 python3: pandas 필요)"""
import json, re, subprocess, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
BTD = ROOT / "docs" / "data" / "bt"; CSV = Path("/Users/joleechan/studies/mm_rotation_20261007/bt_topn/out")
ok = fail = 0
def check(name, cond, info=""):
    global ok, fail
    if cond: ok += 1; print("PASS", name)
    else: fail += 1; print("FAIL", name, info)
J = lambda n: json.load(open(BTD / f"{n}.json", encoding="utf-8"))
POL = ["B1", "B2", "B3-1", "B3-3", "B3-5", "B3-7"]; VARS = ["C", "H1", "H2"]
meta = J("meta"); dates = J("dates")
det = pd.read_csv(CSV / "metrics_deterministic.csv"); reps = pd.read_csv(CSV / "r2_reps.csv"); rsum = pd.read_csv(CSV / "r2_summary.csv")
yr = pd.read_csv(CSV / "yearly_realized.csv"); mp = pd.read_csv(CSV / "monthly_path_2022_2023.csv"); rper = pd.read_csv(CSV / "r2_percentiles.csv")
cyc_meta = json.load(open(Path("/Users/joleechan/studies/mm_rotation_20261007/bt_topn/charts_src/daily_paths_meta.json"), encoding="utf-8"))
T = 6e-4                                                   # JSON 은 소수 4자리 반올림
# ---- 스키마 ----
exp = {"dates", "meta", "monthly", "yearly", "variants", "hist"} | {f"path_{p}_{v}" for p in ("main", "ref") for v in VARS}
check("bt JSON 12개 존재", exp == {f.stem for f in BTD.glob("*.json")}, str({f.stem for f in BTD.glob('*.json')} ^ exp))
check("dates: 주 구간 1701일 2020-01-02~2026-10-08 · 참고 4217일 2010-01-04~", len(dates["main"]) == 1701 and dates["main"][0] == "2020-01-02" and dates["main"][-1] == "2026-10-08" and len(dates["ref"]) == 4217 and dates["ref"][0] == "2010-01-04")
for pn in ("main", "ref"):
    for v in VARS:
        P = J(f"path_{pn}_{v}"); n = len(dates[pn]); good = set(P) == {"real", "ev", "dd", "stk", "r2"}
        good &= all(set(P[k]) == set(POL) and all(len(P[k][p]) == n for p in POL) for k in ("real", "ev", "dd"))
        good &= set(P["stk"]) == {"B3-3", "B3-5", "B3-7"} and all(len(x) == n for x in P["stk"].values()) and all(len(P["r2"][k]) == n for k in ("p5", "med", "p95"))
        check(f"경로 {pn}/{v} 스키마·길이", good)
        # 값 대조: 최종 누적 실현이익 = CSV realized, 최대 낙폭 = CSV maxdd, 최대 STUCK = CSV max_stuck
        bad = []
        for p in POL:
            r = det[(det.period == pn) & (det.policy == p) & (det.variant == v)].iloc[0]
            if abs(P["real"][p][-1] - r.realized) > T: bad.append((p, "realized"))
            if abs(max(P["dd"][p]) - r.maxdd) > T: bad.append((p, "maxdd"))
            if p in P["stk"] and max(P["stk"][p]) != r.max_stuck: bad.append((p, "stuck"))
            if min(P["dd"][p]) < 0 or abs(P["ev"][p][0]) > T: bad.append((p, "dd/ev 시작"))
        check(f"경로 {pn}/{v} 값 = metrics_deterministic.csv (실현이익·최대낙폭·STUCK)", not bad, str(bad))
        s = {m: rsum[(rsum.period == pn) & (rsum.policy == "R2-5") & (rsum.variant == v) & (rsum.metric == "realized")].iloc[0][m] for m in ("p5", "median", "p95")}
        check(f"경로 {pn}/{v} R2-5 띠 마지막 값 = r2_summary p5/중앙/p95", abs(P["r2"]["p5"][-1] - s["p5"]) < T and abs(P["r2"]["med"][-1] - s["median"]) < T and abs(P["r2"]["p95"][-1] - s["p95"]) < T)
        check(f"경로 {pn}/{v} 띠 순서 p5≤중앙≤p95", all(a <= b + 1e-9 and b <= c + 1e-9 for a, b, c in zip(P["r2"]["p5"], P["r2"]["med"], P["r2"]["p95"])))
# 재생성 대조 기록(엔진 재생 vs out/*.csv)
chk = cyc_meta["check"]
check("재생성 대조: 결정적 36건 전부 일치(총 실현이익·최대 낙폭·2022 최저·최대 STUCK)", len(chk["deterministic"]) == 36 and all(x["ok"] for x in chk["deterministic"]))
check("재생성 대조: R2-5 6조×1,000회 반복별 실현이익·낙폭·STUCK 일치", len(chk["r2"]) == 6 and all(v["max_abs_diff_realized"] < 1e-9 and v["max_abs_diff_maxdd"] < 1e-9 and v["max_stuck_mismatch"] == 0 for v in chk["r2"].values()))
# ---- 월별(차트 3) ----
M = J("monthly"); mcols = [c for c in mp.columns if c.startswith("mp_")]
bad = []
for v in VARS:
    for p in POL + ["R2-5"]:
        row = mp[(mp.policy == p) & (mp.variant == v) & (mp.stat == ("median" if p == "R2-5" else "value"))].iloc[0]
        got = M["series"][v][p][3:]
        if any(abs(a - row[c]) > T for a, c in zip(got, mcols)): bad.append((v, p))
check("월별 JSON 2022-01~2023-12 = monthly_path_2022_2023.csv", not bad, str(bad))
check("월별: 시작점 2021-10 = 0, 2021-11·12 는 정책(R2 제외)만", M["months"][:3] == ["2021-10", "2021-11", "2021-12"] and all(M["series"]["C"][p][0] == 0 for p in POL) and M["series"]["C"]["R2-5"][1] is None and all(M["series"]["C"][p][1] is not None for p in POL))
# ---- 연도별(차트 4) ----
Y = J("yearly"); ycols = [c for c in yr.columns if c.startswith("y")]
bad = []
for v in VARS:
    for p in POL + ["R2-5"]:
        row = yr[(yr.policy == p) & (yr.variant == v) & (yr.stat == ("median" if p == "R2-5" else "value"))].iloc[0]
        if any(abs(a - row[c]) > T for a, c in zip(Y["series"][v][p], ycols)): bad.append((v, p))
check("연도별 JSON = yearly_realized.csv", not bad and Y["years"] == [2020, 2021, 2022, 2023, 2024, 2025, 2026], str(bad))
# ---- 경보 변형(차트 5) ----
V = J("variants"); bad = []
for pn in ("main", "ref"):
    for p in POL:
        for v in VARS:
            r = det[(det.period == pn) & (det.policy == p) & (det.variant == v)].iloc[0]
            for k in ("realized", "maxdd", "min_rel_2022"):
                if abs(V[pn][p][v][k] - r[k]) > T: bad.append((pn, p, v, k))
    for p in ("R2-5", "R2-7"):
        for v in VARS:
            for k in ("realized", "maxdd", "min_rel_2022"):
                m = rsum[(rsum.period == pn) & (rsum.policy == p) & (rsum.variant == v) & (rsum.metric == k)].iloc[0]["median"]
                if abs(V[pn][p][v][k] - m) > T: bad.append((pn, p, v, k))
check("변형 비교 JSON = metrics_deterministic.csv·r2_summary.csv 중앙값", not bad, str(bad[:5]))
# ---- 히스토그램(차트 6) ----
H = J("hist"); bad = []
for pn in ("main", "ref"):
    for k in ("realized", "maxdd"):
        h = H[pn][k]
        for key, d in h["dist"].items():
            n, v = key.split("|"); x = reps[(reps.period == pn) & (reps.policy == f"R2-{n}") & (reps.variant == v)][k].values
            e = np.array(h["edges"]); c = np.histogram(x, bins=np.linspace(x.min() * 0 + reps[reps.period == pn][k].min(), reps[reps.period == pn][k].max(), 25))[0]
            b3 = det[(det.period == pn) & (det.policy == f"B3-{n}") & (det.variant == v)].iloc[0][k]
            pc = rper[(rper.period == pn) & (rper.variant == v) & (rper.dist == f"R2-{n}") & (rper.metric == k)].iloc[0].pct_le
            if sum(d["counts"]) != 1000 or list(c) != d["counts"] or abs(d["b3"] - b3) > T or abs(d["pct_le"] - pc) > 0.06: bad.append((pn, k, key))
check("히스토그램: 1,000회·구간별 횟수·B3 값·백분위 = CSV", not bad, str(bad[:5]))
# ---- 메타·한계 4줄 ----
page = (ROOT / "docs" / "backtest.html").read_text(encoding="utf-8")
sy = meta["synth_start_share_main"]
check("한계: 합성 구간 시작 사이클 비율 = REPORT 값(0.0·0.0·32.2·39.9·34.9·34.5)", [sy[p] for p in POL] == [0.0, 0.0, 32.2, 39.9, 34.9, 34.5])
check("한계 4줄 문구", all(t in page for t in ["합성 구간에서 시작한 사이클 비율", "B3-1 32.2%", "MNGU 86%", "SMHU·XLCU·XLPU 75%", "AIQU 60%", "2022 한 번의 하락", "단일 시드(20261013+반복번호) 1,000회"]) and page.count("<li>") == 4)
check("상단: 조건 2줄 + 과거 시뮬레이션 1줄", "V2.2" in page and "익절 12%" in page and "손절 없음" in page and "총자금 1" in page and "슬롯당 1/N" in page and "1x 공식 지수 기준 M-score" in page and "과거 시뮬레이션이며 미래 성과를 뜻하지 않음" in page)
check("버튼: 주 구간 2020~ / 참고 구간 2010~ / 지속(C)·신규 동결(H1)·매수 정지(H2)", all(t in page for t in ["주 구간 2020~", "참고 구간 2010~", "지속(C)", "신규 동결(H1)", "매수 정지(H2)"]))
check("차트 7개 컨테이너", all(f'id="c{n}' in page for n in ("1", "2a", "3", "4", "5a", "6r5", "7")))
check("외부 라이브러리 0 (script src 는 assets/bt.js 하나)", re.findall(r'<script[^>]*src="([^"]*)"', page) == ["assets/bt.js"])
check("메뉴 4종은 그대로(backtest 링크 없음), Guide 7절 링크 있음", 'href="backtest.html"' not in "".join(re.findall(r'<nav class="top">.*?</nav>', page)) and 'backtest.html' in (ROOT / "docs" / "guide.html").read_text(encoding="utf-8"))
js = (ROOT / "docs" / "assets" / "bt.js").read_text(encoding="utf-8")
check("차트 정의: 가로 스크롤 없는 viewBox·점 탐침·범례 토글", "viewBox" in js and "pointermove" in js and "aria-pressed" in js and "XMLHttpRequest" not in js)
# ---- 사유 문구(§1) ----
import mm_site
r = {"badges": "표본부족 · 신규 · 저유동 · 무거래2", "listed_days": 90, "adtv": 0.1749, "n_beta": 45}
check("Python 사유(longterm.json 생성): 신규 90일 · $0.17M · 무거래 2일 · 표본 45", mm_site._why_text(r) == "표본 45 · 신규 90일 · $0.17M · 무거래 2일", mm_site._why_text(r))
ix = (ROOT / "docs" / "assets" / "index.js").read_text(encoding="utf-8"); lt = (ROOT / "docs" / "assets" / "longterm.js").read_text(encoding="utf-8")
check("index.js 사유: '$…M'·'표본 N'(개 없음)·'재구성 N%'", "o.push('$' + fx(r.adtv, 2) + 'M')" in ix and "o.push('표본 ' + r.n_beta)" in ix and "o.push('재구성 ' + hp + '%')" in ix and "' · 거래대금 $'" in ix)   # 그룹 패널의 개별 거래대금 줄은 사유가 아니라 패널 정보라 그대로
check("longterm.js: 구 문구(longterm.json)를 표시 때 변환", "shortW" in lt and "재구성 $1%" in lt)
css = (ROOT / "docs" / "assets" / "mm.css").read_text(encoding="utf-8")
check("CSS: 사유 3줄 제한 복원(line-clamp 3, 해제 규칙 없음)", ".wr{display:-webkit-box;-webkit-line-clamp:3" in css and "-webkit-line-clamp:unset" not in css)
g = (ROOT / "docs" / "guide.html").read_text(encoding="utf-8")
check("Guide 5절 '사유 표기' 열 = 새 문구", all(t in g for t in ["<td>신규 N일</td>", "<td>$x.xxM</td>", "<td>무거래 N일</td>", "<td>표본 N</td>", "<td>재구성 N%</td>"]) and "<td>표본 N개</td>" not in g and "<td>거래대금 $x.xxM</td>" not in g)
check("Guide 7절: 사실 3줄 + 링크(수치 = REPORT 표 3·1)", all(t in g for t in ["100.0% 이하", "0.5% 이하", "0.904", "1.919 → 1.904", "1.919 → 1.617", "0.395 → 0.310", "시뮬레이션 그래프 보기 →"]))
b5 = det[(det.period == "main") & (det.policy == "B3-5")].set_index("variant"); b1 = det[(det.period == "ref") & (det.policy == "B3-1") & (det.variant == "C")].iloc[0]
pp = rper[(rper.period == "main") & (rper.variant == "C") & (rper.basket == "B3-5")].set_index("metric")
check("Guide 7절 수치 = CSV", round(b5.loc["C", "realized"], 3) == 1.919 and round(b5.loc["H1", "realized"], 3) == 1.904 and round(b5.loc["H2", "realized"], 3) == 1.617 and round(b5.loc["H2", "maxdd"], 3) == 0.310 and round(b1.maxdd, 3) == 0.904 and pp.loc["realized", "pct_le"] == 100.0 and pp.loc["maxdd", "pct_le"] == 0.5)
# ---- docs/data 무변경 ----
st = subprocess.run(["git", "status", "--porcelain", "--", "docs/data"], cwd=ROOT, capture_output=True, text=True).stdout.strip().splitlines()
check("docs/data: 기존 파일 무변경(신규 bt/ 만)", all(l.startswith("?? docs/data/bt") for l in st), str(st[:5]))
print(f"\n{ok} PASS / {fail} FAIL"); sys.exit(1 if fail else 0)
