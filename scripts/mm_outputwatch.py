#!/usr/bin/env python3
"""[MM-OUTPUT-WATCH-20261028] 무매 M-score 기대 산출 미생성 감시 — 스크립트형(LLM 0), 게이트웨이 command 크론이 화~토 09:00 KST 에 1회 실행.
기대 파일 = docs/data/scores/<직전 US 거래일>.csv (달력은 일일 잡과 같은 L.prev_us_session). 존재하고 mtime 이 당일 08:00 KST 이후면 침묵,
없거나 구형이면 텔레그램 1건 '[mm_rotation] 기대 산출 미생성 <날짜>'. 달력 조회·기동 실패는 fail-closed(경보).
일일 잡 자체가 launchd 에서 아예 안 떴거나 import 이전에 죽은 경우까지 잡는 최후 방어선(mm_bootalert 는 import 단계 예외만 본다).
옵션: --now <ISO KST>  --scores-dir <폴더>  (시험용).  MM_OUTPUTWATCH_SUPPRESS=1 이면 발송 억제(출력만)."""
import os, sys, json, subprocess, time, urllib.parse, urllib.request, datetime as dt
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
KST = dt.timezone(dt.timedelta(hours=9))
sys.path.insert(0, str(Path(__file__).resolve().parent))
def log(msg):
    try:
        d = ROOT / ".local" / "logs"; d.mkdir(parents=True, exist_ok=True)
        with open(d / "outputwatch.log", "a") as f: f.write(f"{dt.datetime.now(KST):%Y-%m-%d %H:%M:%S} {msg}\n")
    except Exception: pass
    print(msg, flush=True)
def alert(msg):
    log(msg)
    try:
        with open(ROOT / ".local" / "logs" / "alerts.log", "a") as f: f.write(f"{dt.datetime.now(KST):%Y-%m-%d %H:%M:%S} {msg}\n")
    except Exception: pass
    if os.environ.get("MM_OUTPUTWATCH_SUPPRESS") == "1":
        print("[outputwatch] 발송 억제(시험):", msg); return False
    import mm_tg                                         # MM-ALERT-PATH-20261028: 모든 경보가 같은 발송 함수(mm_tg.send)를 탄다
    return mm_tg.send(msg, "mm_outputwatch", retries=3, wait=10, on_fail=log)["ok"]
def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default
def main():
    now = dt.datetime.fromisoformat(arg("--now")) if arg("--now") else dt.datetime.now(KST)
    if now.tzinfo is None: now = now.replace(tzinfo=KST)
    scores = Path(arg("--scores-dir", str(ROOT / "docs" / "data" / "scores")))
    try:
        import mm_lib as L
        exp = L.prev_us_session(now)                         # 일일 잡(mm_daily.feed_check)과 같은 달력 원천
    except BaseException as e:
        alert(f"[mm_rotation] 기대 산출 확인 불가(달력 조회 실패, fail-closed): {type(e).__name__}: {str(e)[:200]}"); return 1
    day = f"{exp:%Y-%m-%d}"; p = scores / f"{day}.csv"
    since = now.replace(hour=8, minute=0, second=0, microsecond=0).timestamp()
    if not p.exists():
        alert(f"[mm_rotation] 기대 산출 미생성 {day} — 파일 없음({p.name})"); return 1
    mt = p.stat().st_mtime
    if mt < since:
        alert(f"[mm_rotation] 기대 산출 미생성 {day} — 파일 mtime {dt.datetime.fromtimestamp(mt, KST):%m-%d %H:%M} 이 당일 08:00 이전(구형)"); return 1
    log(f"정상: 기대 산출 {day} 존재, mtime {dt.datetime.fromtimestamp(mt, KST):%m-%d %H:%M}")
    return 0
if __name__ == "__main__":
    try: sys.exit(main())
    except SystemExit: raise
    except BaseException as e:
        alert(f"[mm_rotation] 산출 감시 자체 실패(fail-closed): {type(e).__name__}: {str(e)[:200]}"); sys.exit(1)
