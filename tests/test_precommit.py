"""MM-PRICE-CHART-FIX-20261111 — 커밋 전 시크릿 검사 훅(.git/hooks/pre-commit) 시험.
임시 저장소에 이 저장소의 훅을 복사해 커밋을 시도한다(이 저장소·live 파일 쓰기 0). 훅이 없으면 SKIP.
  · 통과: 일일 자동 커밋과 같은 종류의 파일(docs/data/*.csv·*.json, data/*.csv, docs/products/*.html)
  · 차단: 본문 키 패턴 / 시크릿 의심 파일명
  · launchd 와 같은 최소 환경(PATH=/usr/bin:/bin:/usr/sbin:/sbin, HOME 만)에서도 같은 결과
시험용 가짜 키는 실행 중에 조립한다 — 이 파일 자체가 훅에 걸리지 않게."""
import sys, os, shutil, tempfile, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".git" / "hooks" / "pre-commit"
GIT = "/usr/bin/git"

P = F = 0
def ok(name, cond, info=""):
    global P, F
    if cond: P += 1; print("PASS", name)
    else: F += 1; print("FAIL", name, info)

if not HOOK.exists():
    print("SKIP 훅 없음"); print("0 PASS / 0 FAIL"); sys.exit(0)

ok("훅 실행 권한", os.access(HOOK, os.X_OK))
MIN_ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": os.environ.get("HOME", "/tmp"),
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}

def repo():
    d = Path(tempfile.mkdtemp(prefix="mm_hook_test_"))
    subprocess.run([GIT, "init", "-q", "-b", "main", str(d)], check=True, env=MIN_ENV)
    shutil.copy2(HOOK, d / ".git" / "hooks" / "pre-commit")
    return d

def commit(d, files, env=None):
    for rel, text in files.items():
        p = d / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding="utf-8")
    subprocess.run([GIT, "-C", str(d), "add", "-A"], check=True, env=env or MIN_ENV)
    r = subprocess.run([GIT, "-C", str(d), "commit", "-q", "-m", "Auto: M-score test"], capture_output=True, text=True, env=env or MIN_ENV)
    return r.returncode, r.stdout + r.stderr

AUTO = {"docs/data/scores/2026-11-10.csv": "# date=2026-11-10 N=37 rule=v\nticker,M,rank\nSOXL,1.23,1\n",
        "docs/data/charts/SOXL.json": '{"t":"SOXL","v":1,"d0":"2010-03-11","dt":[0,1],"o":[1.0,1.1],"h":[1.2,1.2],"l":[0.9,1.0],"c":[1.1,1.15]}',
        "docs/data/index.json": '{"dates":["2026-11-10"]}', "data/scores_latest.csv": "date,ticker,M\n2026-11-10,SOXL,1.23\n",
        "data/chart_overrides.yaml": "overrides:\n  - ticker: DFEN\n    date: \"2024-06-03\"\n    field: low\n",
        "docs/products/SOXL.html": "<html><body>SOXL</body></html>\n"}

d = repo()
rc, out = commit(d, AUTO)
ok("통과: 일일 자동 커밋 형태 파일(최소 환경)", rc == 0, out[-300:])

fake = "sk-" + "ant-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3"
d2 = repo(); commit(d2, {"README.md": "x\n"})
rc, out = commit(d2, {"docs/data/leak.txt": f'api_key = "{fake}"\n'})
ok("차단: 본문 키 패턴", rc != 0 and "시크릿 의심" in out, out[-300:])
rc, out = commit(d2, {"data/my_token.txt": "nothing\n"})
ok("차단: 시크릿 의심 파일명", rc != 0 and "파일명" in out, out[-300:])

d3 = repo()
env_full = dict(os.environ, **{k: v for k, v in MIN_ENV.items() if k.startswith("GIT_")})
rc, out = commit(d3, AUTO, env=env_full)
ok("통과: 일반 환경에서도 동일", rc == 0, out[-300:])

for x in (d, d2, d3): shutil.rmtree(x, ignore_errors=True)
print(f"{P} PASS / {F} FAIL")
sys.exit(1 if F else 0)
