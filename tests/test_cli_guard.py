"""MM-SPLIT-GUARD-20261106 D1 시험 — CLI 안전: --help·알 수 없는 인자가 산출/발행으로 이어질 경로 0 · --dry-run 이 발행 경로를 만들지 않음
네트워크 0 · 텔레그램 0 · push 0 · 실제 데이터 0. 사용: python3 tests/test_cli_guard.py"""
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

# ───────────────────────── (A) CLI 안전 ─────────────────────────
calls = {"run": 0, "push": 0, "dry": 0, "sub": []}
D.run = lambda *a, **k: (calls.__setitem__("run", calls["run"] + 1), None)[1]
D.git_push = lambda T: calls.__setitem__("push", calls["push"] + 1)
_orig_dry = D.dry_run
D.dry_run = lambda argv, keep=False: (calls.__setitem__("dry", calls["dry"] + 1), 0)[1]
def call_main(argv):
    buf = io.StringIO(); err = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err): rc = D.main(argv)
    except SystemExit as e: rc = e.code
    return rc, buf.getvalue(), err.getvalue()
for flag in ("--help", "-h"):
    calls.update(run=0, push=0, dry=0); rc, out, err = call_main([flag])
    check(f"{flag}: 사용법만 출력·종료 0·산출/push/dry-run 0", rc == 0 and "usage" in out.lower() and calls == {"run": 0, "push": 0, "dry": 0, "sub": []}, (rc, calls))
calls.update(run=0, push=0, dry=0); rc, out, err = call_main(["--bogus"])
check("--bogus: 종료 2·산출 0 (모르는 인자는 더 이상 조용히 일일 실행이 되지 않는다)", rc == 2 and calls["run"] == 0 and calls["push"] == 0, (rc, calls))
calls.update(run=0, push=0, dry=0); rc, out, err = call_main(["--no-pus"])           # 오타 접두 약어도 거부 (allow_abbrev=False)
check("--no-pus(약어 오타): 종료 2·산출 0", rc == 2 and calls["run"] == 0, (rc, calls))
calls.update(run=0, push=0, dry=0); rc, out, err = call_main(["--dry-run", "--no-fetch"])
check("--dry-run: dry_run() 만 호출 — run()/git_push() 직접 호출 0", rc == 0 and calls["dry"] == 1 and calls["run"] == 0 and calls["push"] == 0, (rc, calls))
def with_env(env, argv):
    saved = {k: os.environ.get(k) for k in env}
    for k, v in env.items():
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = v
    try: return call_main(argv)
    finally:
        for k, v in saved.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v
calls.update(run=0, push=0, dry=0); rc, out, err = with_env({"XPC_SERVICE_NAME": None, "MM_AUTO": None}, [])
check("수동 실행(터미널)에서 인자 없음: 사용법 + 종료 2 · 산출/push 0 (실행 경로는 명시 플래그만)", rc == 2 and calls["run"] == 0 and calls["push"] == 0 and "--run" in err, (rc, calls, err[-120:]))
calls.update(run=0, push=0, dry=0); rc, out, err = with_env({"XPC_SERVICE_NAME": None, "MM_AUTO": None}, ["--run"])
check("수동 실행 + --run: run() 1회", rc == 0 and calls["run"] == 1, (rc, calls))
calls.update(run=0, push=0, dry=0); rc, out, err = with_env({"XPC_SERVICE_NAME": "com.mm.rotation_daily", "MM_AUTO": None}, [])
check("launchd(com.mm.rotation_daily) 인자 없음: 종전대로 run() 1회", rc == 0 and calls["run"] == 1, (rc, calls))
calls.update(run=0, push=0, dry=0); rc, out, err = with_env({"XPC_SERVICE_NAME": None, "MM_AUTO": "1"}, [])
check("MM_AUTO=1 인자 없음(자동 호출): run() 1회", rc == 0 and calls["run"] == 1, (rc, calls))
# --regen-from DATE (공백형) → '=' 형 정규화
calls.update(run=0, push=0, dry=0); seen = {}
D.run = lambda *a, **k: (seen.__setitem__("argv", list(sys.argv)), calls.__setitem__("run", calls["run"] + 1), None)[2]
call_main(["--regen-from", "2026-11-04", "--regen-reason", "SOXL 복원", "--no-push"])
check("--regen-from DATE 공백형이 '=' 형으로 정규화(run 이 sys.argv 로 읽음)", "--regen-from=2026-11-04" in seen.get("argv", []) and "--regen-reason=SOXL 복원" in seen.get("argv", []), seen)

calls.update(run=0, push=0, dry=0); rc, out, err = call_main(["--regen-from", "2026-11-04", "--no-push"])
check("--regen-from 만 (사유 없음): 종료 2·산출 0 (--regen-reason 필수)", rc == 2 and calls["run"] == 0 and calls["push"] == 0 and "--regen-reason" in err, (rc, calls, err[-160:]))
calls.update(run=0, push=0, dry=0); rc, out, err = call_main(["--regen-from=2026-11-04", "--regen-reason", "   "])
check("--regen-reason 이 공백뿐이어도 거부(종료 2·산출 0)", rc == 2 and calls["run"] == 0, (rc, calls))
calls.update(run=0, push=0, dry=0); rc, out, err = call_main(["--dry-run", "--regen-from", "2026-11-04"])
check("--dry-run 이어도 --regen-from 은 사유 필수(종료 2·dry_run 호출 0)", rc == 2 and calls["dry"] == 0 and calls["run"] == 0, (rc, calls))
calls.update(run=0, push=0, dry=0); rc, out, err = call_main(["--regen-from=2026-11-04", "--regen-reason=SOXL 복원", "--no-push"])
check("--regen-from + 사유: 정상 run() 1회", rc == 0 and calls["run"] == 1, (rc, calls))

# dry_run 내부: 실제 함수로 — copytree/subprocess 를 가로채 발행 경로가 없음을 증명
D.dry_run = _orig_dry
rec = {"cmds": [], "env": None, "copied": None, "rm": None}
import shutil
_ct, _sr, _rt = shutil.copytree, _sp.run, shutil.rmtree
shutil.copytree = lambda src, dst, **k: (rec.__setitem__("copied", (str(src), str(dst))), Path(dst, "scripts").mkdir(parents=True, exist_ok=True), Path(dst, "data").mkdir(exist_ok=True))[0]
class _R:  # CompletedProcess 흉내
    returncode = 0; stdout = "…\n산출 완료 순위 37/37"; stderr = ""
def fake_run(cmd, **kw):
    rec["cmds"].append(list(cmd)); rec["env"] = kw.get("env") or rec["env"]; return _R()
_sp.run = fake_run; D.subprocess.run = fake_run
shutil.rmtree = lambda p, **k: rec.__setitem__("rm", str(p))
try:
    with contextlib.redirect_stdout(io.StringIO()): D.dry_run(["--dry-run", "--no-fetch"])
finally:
    shutil.copytree, _sp.run, shutil.rmtree = _ct, _sr, _rt; D.subprocess.run = _sr
if rec["copied"]: _rt(str(Path(rec["copied"][1]).parent), ignore_errors=True)       # 시험이 만든 빈 임시 폴더 정리(rmtree 를 가로챈 탓에 남는다)
flat = [" ".join(c) for c in rec["cmds"]]
child = next((c for c in rec["cmds"] if any(x.endswith("mm_daily.py") for x in c)), [])
check("dry-run: 복사본 경로에서 실행(live scripts 아님)", rec["copied"] and str(L.ROOT) == rec["copied"][0] and any(str(Path(rec["copied"][1]) / "scripts" / "mm_daily.py") == x for x in child), (rec["copied"], child))
check("dry-run: 복사본에서 git remote remove origin 선행", any("remote" in c and "remove" in c and "origin" in c for c in rec["cmds"]), flat)
check("dry-run: 자식에 --no-push·--no-alert 강제 + --dry-run 제거", "--no-push" in child and "--no-alert" in child and "--dry-run" not in child, child)
check("dry-run: 자식 환경 MM_DRY_RUN_CHILD=1·MM_TG_SUPPRESS=1", (rec["env"] or {}).get("MM_DRY_RUN_CHILD") == "1" and (rec["env"] or {}).get("MM_TG_SUPPRESS") == "1", rec["env"])
check("dry-run: git push 명령 0건", not any(c[:1] == ["git"] and "push" in c for c in rec["cmds"]), flat)
check("dry-run: 임시 복사본 삭제", rec["rm"] is not None)
# git_push 이중 차단: 자식 환경변수가 있으면 subprocess 호출 0
pushed = []
D.subprocess.run = lambda *a, **k: pushed.append(a) or _R()
os.environ["MM_DRY_RUN_CHILD"] = "1"
try: D.git_push(pd.Timestamp("2026-11-05"))
finally: os.environ.pop("MM_DRY_RUN_CHILD", None); D.subprocess.run = _sr
check("MM_DRY_RUN_CHILD=1 이면 git_push() 는 어떤 subprocess 도 부르지 않는다", pushed == [], pushed)
# 자식 모드에서 main() 은 push=False·alert=False 로 run 호출
got = {}
D.run = lambda push=True, fetch=True, manual=None, alert=None: (got.update(push=push, alert=alert), None)[1]
os.environ["MM_DRY_RUN_CHILD"] = "1"
try: call_main(["--no-fetch"])
finally: os.environ.pop("MM_DRY_RUN_CHILD", None)
check("자식 모드: 인자에 --no-push/--no-alert 가 없어도 push=False·alert=False", got == {"push": False, "alert": False}, got)

print(f"\n{ok} PASS / {len(bad)} FAIL"); sys.exit(0 if not bad else 1)
