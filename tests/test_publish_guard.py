"""MM-SPLIT-GUARD-20261106 D2 시험 — 발행 가드: 과거 T 자동 발행 금지 · 종목 수 축소 덮어쓰기 금지 · --regen-from 예외
네트워크 0 · 텔레그램 0 · push 0 · 실제 데이터 0. 사용: python3 tests/test_publish_guard.py"""
import sys, io, os, json, tempfile, contextlib, subprocess as _sp
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np, pandas as pd
import mm_lib as L
L.log = lambda m, name="daily": None
import mm_daily as D
ok = 0; bad = []
def check(name, cond, detail=""):
    global ok
    if cond: ok += 1; print("PASS", name)
    else: bad.append(name); print("FAIL", name, detail)

P = pd.Timestamp
# ───────────────────────── (B) 발행 가드 ─────────────────────────
check("과거 T(11-04 < 직전 발행 11-05) 자동 발행 차단", D.stale_T_guard(P("2026-11-05"), P("2026-11-04"), False) is True)
check("같은 T·더 새 T 는 통과", D.stale_T_guard(P("2026-11-05"), P("2026-11-05"), False) is False and D.stale_T_guard(P("2026-11-05"), P("2026-11-06"), False) is False)
check("직전 발행 없음 → 통과", D.stale_T_guard(None, P("2026-11-04"), False) is False)
check("--regen-from 명시 시 과거 T 예외", D.stale_T_guard(P("2026-11-05"), P("2026-11-04"), True) is False)
check("종목 수 축소 덮어쓰기(37→36) 차단", D.shrink_guard(37, 36, False) is True)
check("같거나 늘어나면 통과·파일 없음 통과", D.shrink_guard(37, 37, False) is False and D.shrink_guard(36, 37, False) is False and D.shrink_guard(None, 36, False) is False)
check("--regen-from 명시 시 축소도 예외", D.shrink_guard(37, 36, True) is False)
with tempfile.TemporaryDirectory() as td:
    L.SCORES = Path(td); (Path(td) / "2026-11-04.csv").write_text("# date=2026-11-04 N=37 rule=V2.3\nticker\n")
    L.day_path = lambda d: Path(td) / f"{pd.Timestamp(d).date()}.csv"
    check("existing_day_n: 헤더 N 읽기·없는 날짜 None", L.existing_day_n(P("2026-11-04")) == 37 and L.existing_day_n(P("2026-11-03")) is None)

check("통과 로그 1줄 형식: 통과: T=…, 직전 발행 T=…, N=…", D.pass_msg(P("2026-11-06"), P("2026-11-05"), 37) == "[발행 가드] 통과: T=2026-11-06, 직전 발행 T=2026-11-05, N=37")
check("직전 발행 없음이면 '없음'", D.pass_msg(P("2026-11-06"), None, 37).endswith("직전 발행 T=없음, N=37"))
print(f"\n{ok} PASS / {len(bad)} FAIL"); sys.exit(0 if not bad else 1)
