"""MM-BT-CHARTS-20261011 — 백테스트 결과(bt_topn/out/*.csv + charts_src/daily_paths.npz) → docs/data/bt/*.json 변환. 멱등(재실행하면 같은 파일을 다시 쓴다).
표시층 전용: 입력은 읽기 전용, 출력은 docs/data/bt/ 뿐(기존 docs/data 파일 무접촉). 일별 경로가 없으면 charts_src/gen_daily_paths.py(엔진 import, 읽기 전용 재생)를 먼저 실행한다.
실행: /usr/bin/python3 scripts/mm_bt_data.py [--regen]   (pandas 는 시스템 python3 에만 있다)"""
import json, subprocess, sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUTD = ROOT / "docs" / "data" / "bt"
BT = Path("/Users/joleechan/studies/mm_rotation_20261007/bt_topn")
CSV = BT / "out"; CS = BT / "charts_src"
POL = ["B1", "B2", "B3-1", "B3-3", "B3-5", "B3-7"]
LABEL = {"B1": "B1 SOXL 단독", "B2": "B2 보유 6종 고정", "B3-1": "B3-1 상위 1", "B3-3": "B3-3 상위 3", "B3-5": "B3-5 상위 5", "B3-7": "B3-7 상위 7",
         "R2-5": "R2-5 무작위 중앙값", "R2-7": "R2-7 무작위 중앙값"}
VARS = ["C", "H1", "H2"]
VLABEL = {"C": "지속(C)", "H1": "신규 동결(H1)", "H2": "매수 정지(H2)"}
STUCK_POL = ["B3-3", "B3-5", "B3-7"]
# 신규 ETN 지수 재구성 비중(%) — 인계장 §10, 2026-10-08 기준(MM-NEWIDX-CHECK-20261011). AIQU·MNGU 는 현재 순위 제외지만 시뮬레이션 유니버스에는 포함돼 있다.
ETN_RECON = {"MNGU": 86, "SMHU": 75, "XLCU": 75, "XLPU": 75, "AIQU": 60}
R = lambda x, n=4: None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def dump(name, obj):
    OUTD.mkdir(parents=True, exist_ok=True)
    (OUTD / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main(regen=False):
    if regen or not (CS / "daily_paths.npz").exists():
        subprocess.run(["/usr/bin/python3", str(CS / "gen_daily_paths.py")], check=True, env={"PYTHONUTF8": "1", "PATH": "/usr/bin:/bin"})
    Z = np.load(CS / "daily_paths.npz"); MJ = json.load(open(CS / "daily_paths_meta.json", encoding="utf-8"))
    md = MJ["master_dates"]
    det = pd.read_csv(CSV / "metrics_deterministic.csv"); reps = pd.read_csv(CSV / "r2_reps.csv"); rsum = pd.read_csv(CSV / "r2_summary.csv")
    rper = pd.read_csv(CSV / "r2_percentiles.csv"); yr = pd.read_csv(CSV / "yearly_realized.csv"); mp = pd.read_csv(CSV / "monthly_path_2022_2023.csv")
    cyc = pd.read_csv(CSV / "cycles_deterministic.csv")
    rm = json.load(open(CSV / "run_meta.json", encoding="utf-8"))
    dates = {}
    for pn in ("main", "ref"):
        s = MJ[f"{pn}_start"]; dates[pn] = md[s:]
    dump("dates.json", dates)

    # ---- 경로 파일: period × variant ----
    for pn in ("main", "ref"):
        for v in VARS:
            o = {"real": {}, "ev": {}, "dd": {}, "stk": {}, "r2": {}}
            for p in POL:
                o["real"][p] = [R(x) for x in Z[f"{pn}|{p}|{v}|real"]]
                o["ev"][p] = [R(x) for x in Z[f"{pn}|{p}|{v}|ev"]]
                o["dd"][p] = [R(x) for x in Z[f"{pn}|{p}|{v}|dd"]]
            for p in STUCK_POL: o["stk"][p] = [int(x) for x in Z[f"{pn}|{p}|{v}|stk"]]
            for k in ("p5", "med", "p95"): o["r2"][k] = [R(x) for x in Z[f"{pn}|R2-5|{v}|{k}"]]
            dump(f"path_{pn}_{v}.json", o)

    # ---- 상태 4 구간(날짜 쌍) + 조건·한계 메타 ----
    runs = {pn: [[dates[pn][a], dates[pn][b]] for a, b in MJ[f"{pn}_g4_runs"]] for pn in ("main", "ref")}
    gm = cyc[(cyc.period == "main") & (cyc.variant == "C")]
    synth = {p: round(100 * float((gm[gm.policy == p].layer == 2).mean()), 1) for p in POL}
    meta = {
        "periods": {"main": {"label": "주 구간 2020~", "start": dates["main"][0], "end": dates["main"][-1], "days": len(dates["main"])},
                    "ref": {"label": "참고 구간 2010~", "start": dates["ref"][0], "end": dates["ref"][-1], "days": len(dates["ref"])}},
        "policies": POL, "labels": LABEL, "variants": VARS, "variant_labels": VLABEL,
        "g4_runs": runs, "synth_start_share_main": synth, "etn_recon": ETN_RECON,
        "r2_seed_base": rm["seeds"]["r2_seed_base"], "r2_reps": rm["seeds"]["r2_reps"], "prereg_sha256": rm["prereg_sha256"],
        "src": "~/studies/mm_rotation_20261007/bt_topn/out (MM-WRAP-BT-20261011 §2) + charts_src/daily_paths.npz",
    }
    dump("meta.json", meta)

    # ---- 차트 3 월별(주 구간) : 2021-10-29 = 0 기준 P_rel ----
    mcols = [c for c in mp.columns if c.startswith("mp_")]
    months = [c[3:] for c in mcols]
    dm = dates["main"]; idx = {d: i for i, d in enumerate(dm)}
    ref_i = idx["2021-10-29"]
    last_of = {}
    for i, d in enumerate(dm): last_of[d[:7]] = i
    pre = {}
    for v in VARS:
        pre[v] = {p: {m: R(Z[f"main|{p}|{v}|ev"][last_of[m]] - Z[f"main|{p}|{v}|ev"][ref_i]) for m in ("2021-11", "2021-12")} for p in POL}
    mon = {"months": ["2021-10", "2021-11", "2021-12"] + months, "series": {}}
    for v in VARS:
        s = {}
        for p in POL:
            row = mp[(mp.policy == p) & (mp.variant == v) & (mp.stat == "value")].iloc[0]
            s[p] = [0.0, pre[v][p]["2021-11"], pre[v][p]["2021-12"]] + [R(row[c]) for c in mcols]
        row = mp[(mp.policy == "R2-5") & (mp.variant == v) & (mp.stat == "median")].iloc[0]
        s["R2-5"] = [0.0, None, None] + [R(row[c]) for c in mcols]
        mon["series"][v] = s
    mon["note"] = "2021-11·2021-12 는 일별 경로 재생성값, 2022-01~2023-12 는 monthly_path_2022_2023.csv, 기준 2021-10-29 = 0. R2-5 는 CSV 월별 중앙값(2022-01~)"
    dump("monthly.json", mon)

    # ---- 차트 4 연도별(주 구간) ----
    ycols = [c for c in yr.columns if c.startswith("y")]
    ann = {"years": [int(c[1:]) for c in ycols], "series": {}}
    for v in VARS:
        s = {}
        for p in POL:
            row = yr[(yr.policy == p) & (yr.variant == v) & (yr.stat == "value")].iloc[0]; s[p] = [R(row[c]) for c in ycols]
        row = yr[(yr.policy == "R2-5") & (yr.variant == v) & (yr.stat == "median")].iloc[0]; s["R2-5"] = [R(row[c]) for c in ycols]
        ann["series"][v] = s
    dump("yearly.json", ann)

    # ---- 차트 5 변형 비교 ----
    cmp_ = {}
    for pn in ("main", "ref"):
        o = {}
        for p in POL:
            o[p] = {v: {k: R(det[(det.period == pn) & (det.policy == p) & (det.variant == v)].iloc[0][k]) for k in ("realized", "maxdd", "min_rel_2022")} for v in VARS}
        for rp in ("R2-5", "R2-7"):
            o[rp] = {v: {k: R(rsum[(rsum.period == pn) & (rsum.policy == rp) & (rsum.variant == v) & (rsum.metric == k)].iloc[0]["median"]) for k in ("realized", "maxdd", "min_rel_2022")} for v in VARS}
        cmp_[pn] = o
    dump("variants.json", cmp_)

    # ---- 차트 6 분포 히스토그램(period × metric 공통 구간 24칸) ----
    NB = 24; hist = {}
    for pn in ("main", "ref"):
        hist[pn] = {}
        for k in ("realized", "maxdd"):
            sub = reps[(reps.period == pn)]
            lo, hi = float(sub[k].min()), float(sub[k].max()); step = (hi - lo) / NB
            edges = [lo + i * step for i in range(NB + 1)]
            h = {"edges": [R(e, 5) for e in edges], "dist": {}}
            for n in (5, 7):
                for v in VARS:
                    x = sub[(sub.policy == f"R2-{n}") & (sub.variant == v)][k].values
                    c = np.histogram(x, bins=edges)[0]
                    assert int(c.sum()) == len(x) == 1000          # 마지막 칸은 닫힌 구간 → 1,000회 전부 포함
                    pct = rper[(rper.period == pn) & (rper.variant == v) & (rper.dist == f"R2-{n}") & (rper.metric == k)].iloc[0]
                    b3 = det[(det.period == pn) & (det.policy == f"B3-{n}") & (det.variant == v)].iloc[0][k]
                    q = {s: R(rsum[(rsum.period == pn) & (rsum.policy == f"R2-{n}") & (rsum.variant == v) & (rsum.metric == k)].iloc[0][s]) for s in ("p5", "median", "p95")}
                    h["dist"][f"{n}|{v}"] = {"counts": [int(t) for t in c], "b3": R(b3), "pct_le": R(pct.pct_le, 1), **q}
            hist[pn][k] = h
    dump("hist.json", hist)
    print("OK", sorted(p.name for p in OUTD.glob("*.json")))


if __name__ == "__main__":
    main("--regen" in sys.argv)
