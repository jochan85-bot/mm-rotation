"""MM-DECOUPLE-20261021 단위 테스트 — 순위 자격은 1x 신선도로만, 3배 봉 부재는 무거래 표시용 행(src3=nobar). 네트워크 0·텔레그램 0·실제 데이터 0. python3 tests/test_decouple.py"""
import sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np, pandas as pd
from scipy.stats import rankdata
import mm_lib as L, mm_tailetn as TE
ok = 0; bad = []
def check(name, cond, detail=""):
    global ok
    if cond: ok += 1; print("PASS", name)
    else: bad.append(name); print("FAIL", name, detail)
L.log = lambda m, name="daily": None
cfg = L.load_yaml_simple(ROOT / "data" / "eligibility.yaml")
N = 420; idx = pd.bdate_range(end="2026-10-08", periods=N); asof = idx[-1]; st = {"excluded": {}}
def series(vol=0.01, start=100.0, seed=0, volm=1e6):
    r = np.random.default_rng(seed).normal(0.0004, vol, N); c = start * np.cumprod(1 + r)
    return pd.DataFrame({"Close": c, "Volume": np.full(N, volm), "Open": c, "High": c, "Low": c}, index=idx)
class Stub:
    def __init__(s, data): s.d = data; s.F = {}
    def loadp(s, k): return s.d[k]
    def pct_rank(s, x):
        n = len(x); return np.array([0.5]) if n == 1 else (rankdata(x) - 1) / (n - 1)
    def feat1x(s, px):
        if px in s.F: return s.F[px]
        c = s.d[px]["Close"].values.astype(float); r = np.r_[np.nan, c[1:] / c[:-1] - 1]
        s60 = pd.Series(r).rolling(60).std().values * np.sqrt(252); sc = pd.Series(c)
        ma50 = sc.rolling(50).mean().values; ma200 = sc.rolling(200).mean().values
        f2a = np.full(len(c), np.nan)
        for k in range(252, len(c)): f2a[k] = c[k - 21] / c[k - 252] - 1
        s.F[px] = dict(s60=s60, f2a=f2a, f1b=ma50 / ma200 - 1); return s.F[px]
def mk(extra=None):
    d = {}; tick = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    for i, t in enumerate(tick):
        d["X" + t] = series(0.01 + 0.002 * i, seed=i); d[t] = series(0.03 + 0.006 * i, seed=10 + i)
    if extra: extra(d)
    uni = pd.DataFrame(dict(ticker=tick, group="A", type="ETF", issuer="Z", proxy=["X" + t for t in tick], proxy_disp="", proxy_tip="", leverage="3x"))
    pq = pd.DataFrame([dict(ticker=t, proxy="X" + t, beta=3.0, r2=0.99, n=252, measured="2026-10-08", ok=1) for t in tick])
    return Stub(d), uni, pq
def run(extra=None, tn=None):
    L._TN = tn or {}
    S, uni, pq = mk(extra); df, _ = L.compute(S, asof, asof, cfg, st, uni, pq); return S, df
row = lambda df, t: df[df.ticker == t].iloc[0]
S0, base = run(); b = row(base, "AAA")
check("기준: 5종 전부 순위·nobar 없음", (base.table == "순위").all() and (base.src3 == "").all())

# ── §3-1 3배 봉 없음 → 순위 포함 · 무거래 +1 · 종가 직전 값 · 20일 거래대금 0 집계
for miss in (1, 2, 5):
    def drop3(d, miss=miss): d["AAA"] = d["AAA"].iloc[:-miss]
    S, df = run(drop3); r = row(df, "AAA"); h = S.d["AAA"]
    check(f"3배 봉 {miss}일 없음: 순위 포함·⚠ 아님", r.table == "순위" and pd.notna(r["rank"]) and pd.notna(r.M) and r.reason == "", (r.table, r.reason))
    check(f"3배 봉 {miss}일 없음: src3=nobar·무거래 +1(배지 무거래N)", r.src3 == "nobar" and r.zero_vol == 1 and r.badges.split(" · ")[-1] == "무거래1", (r.src3, r.zero_vol, r.badges))
    check(f"3배 봉 {miss}일 없음: 3배 종가 = 직전 값", abs(r.close3 - float(h["Close"].iloc[-1])) < 1e-12, (r.close3, float(h["Close"].iloc[-1])))
    exp = float((h["Close"] * h["Volume"]).iloc[-19:].sum() / 20 / 1e6)
    check(f"3배 봉 {miss}일 없음: 20일 거래대금에 그날 0 집계(= 실제 19일 합 ÷ 20)", abs(r.adtv - exp) < 1e-9, (r.adtv, exp))
    check(f"3배 봉 {miss}일 없음: 마지막 실제 봉 날짜 d3 보존·RAW 불변", r.d3 == str(h.index[-1].date()) and len(S.d["AAA"]) == N - miss)
    check(f"3배 봉 {miss}일 없음: 1x 점수(sig·rsA·f1b) 불변", all(abs(r[c] - b[c]) < 1e-12 for c in ("sig", "rsA", "f1b")))
S, df = run(lambda d: d.__setitem__("AAA", d["AAA"].iloc[:-1]))
check("3배 봉 부재로 ⚠ 0 (전 사유에 '3배' 없음)", (df.table == "⚠").sum() == 0 and not df.reason.str.contains("3배").any())
# ── 덮어쓰기 멱등: 다음 실행에 실제 봉이 오면 nobar 가 사라진다
S2, df2 = run(); r2 = row(df2, "AAA")
check("실제 봉이 오면 nobar 해제·무거래 0·종가 실제값", r2.src3 == "" and r2.zero_vol == 0 and abs(r2.close3 - float(S2.d["AAA"]["Close"].iloc[-1])) < 1e-12 and r2.badges == "")
S3, df3 = run(lambda d: d.__setitem__("AAA", d["AAA"].iloc[:-1])); S4, df4 = run(lambda d: d.__setitem__("AAA", d["AAA"].iloc[:-1]))
check("같은 입력 두 번 → 결과 동일(멱등)", df3[["ticker", "M", "rank", "close3", "adtv", "zero_vol", "src3"]].fillna(-1).equals(df4[["ticker", "M", "rank", "close3", "adtv", "zero_vol", "src3"]].fillna(-1)))

# ── §3-2 1x 지연 1~3일 보정(mm_tailetn) 후 순위 포함 · 4일 지연은 ⚠
def tail_case(lag):
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td); cal = idx
        def w(name, h): h2 = h.copy(); h2.index = h2.index.tz_localize("America/New_York"); h2.index.name = "Date"; h2.to_csv(raw / f"{name}.csv")
        w("SPY", series(0.005, 400.0, 99)); w("XAAA", series(0.01, seed=0).iloc[:N - lag]); w("AAA", series(0.03, seed=10))
        uni = pd.DataFrame({"ticker": ["AAA"], "proxy": ["XAAA"]})
        info = TE.fill(asof, uni, raw, log=lambda m: None)
        def ld(name):
            h = TE._rd(raw / f"{name}.csv"); h.index = TE._days(h.index); return h[["Close", "Volume"]]
        fixed = ld("XAAA")
    def ex(d): d["XAAA"] = fixed
    def only(d): d["XAAA"] = fixed
    return run(only, tn=info)
for lag in (1, 2, 3):
    S, df = tail_case(lag); r = row(df, "AAA")
    check(f"1x {lag}일 지연: 3배÷3 보정 후 순위 포함·" + ("배지 지수보정1 없음(1일 보정은 src 기록만, MM-FUNDTRACK-20261023 §2)" if lag == 1 else f"배지 지수보정{lag}"), r.table == "순위" and (("지수보정" not in r.badges) if lag == 1 else (f"지수보정{lag}" in r.badges)) and r.src3 == "", (r.table, r.reason, r.badges))
S, df = tail_case(4); r = row(df, "AAA")
check("1x 4일 지연: 보정 안 됨 → ⚠ (사유는 1x)", r.table == "⚠" and "1x" in r.reason and "최신 확정 봉이 기준일" in r.reason, r.reason)
def lag1(d): d["XAAA"] = d["XAAA"].iloc[:-1]
S, df = run(lag1); r = row(df, "AAA")
check("1x 최신 봉 하루 늦음(보정 없음) → ⚠", r.table == "⚠" and f"1x {idx[-2].date()}" in r.reason, r.reason)
def lag1_and_3x(d): d["XAAA"] = d["XAAA"].iloc[:-4]; d["AAA"] = d["AAA"].iloc[:-3]
S, df = run(lag1_and_3x); r = row(df, "AAA")
check("1x 4일 지연 + 3배도 부재 → ⚠ 사유에 3배 언급 없음(1x 만)", r.table == "⚠" and "3배" not in r.reason, r.reason)

# ── §3-4 1x Close NaN → ⚠
def nan1x(d): x = d["XAAA"].copy(); x.iloc[-1, x.columns.get_loc("Close")] = np.nan; d["XAAA"] = x
S, df = run(nan1x); r = row(df, "AAA")
check("1x 기준일 Close NaN → ⚠·순위 제외", r.table == "⚠" and pd.isna(r["rank"]) and pd.isna(r.M), (r.table, r.reason))
def nan1x_nobar(d): nan1x(d); d["AAA"] = d["AAA"].iloc[:-1]
S, df = run(nan1x_nobar); r = row(df, "AAA")
check("1x Close NaN + 3배 부재 → ⚠ (사유는 1x 종가)", r.table == "⚠" and "종가" in r.reason, r.reason)

# ── 상장 전/후 (첫 3배 봉 이전)
def nobars(d): d["AAA"] = d["AAA"].iloc[:0]
L._FB = {"AAA": asof + pd.Timedelta(days=30)}
S, df = run(nobars); r = row(df, "AAA")
check("상장일 이전·3배 봉 전무 → ⚠(상장 전, 표시용 행 없음)", r.table == "⚠" and "상장 전" in r.reason and r.src3 == "", (r.table, r.reason))
L._FB = {"AAA": asof - pd.Timedelta(days=3)}
S, df = run(nobars); r = row(df, "AAA")
check("상장일 이후·3배 봉 전무(이력 유실) → 순위 포함·nobar·종가 NaN·무거래1", r.table == "순위" and r.src3 == "nobar" and pd.isna(r.close3) and r.zero_vol == 1 and pd.notna(r.M), (r.table, r.reason, r.close3, r.zero_vol))
L._FB = {}
S, df = run(nobars); r = row(df, "AAA")
check("상장일 미상 + 3배 봉 전무 → ⚠(상장 전)", r.table == "⚠" and "상장 전" in r.reason)
L._FB = None

# ── with_nobar 단위
h = series(seed=3).iloc[:-2]; x = L.with_nobar(h, asof)
check("with_nobar: 행 +1·asof·Volume 0·OHLC=Close=직전 종가·src=nobar 아님(열 없으면 생략)", len(x) == len(h) + 1 and x.index[-1] == asof and x["Volume"].iloc[-1] == 0 and x["Close"].iloc[-1] == h["Close"].iloc[-1] == x["Open"].iloc[-1] and "src" not in x.columns)
h["src"] = "yahoo"; x = L.with_nobar(h, asof)
check("with_nobar: src 열이 있으면 nobar", x["src"].iloc[-1] == "nobar" and (x["src"].iloc[:-1] == "yahoo").all())
check("with_nobar: 원본 불변", len(h) == N - 2)
print(f"{ok} PASS, {len(bad)} FAIL"); sys.exit(1 if bad else 0)
