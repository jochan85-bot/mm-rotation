#!/usr/bin/env python3
"""트레이더 리포트 '무매 신호' 박스 정상 표시 확인 — 일회성 점검(MM-WRAP-BT-20261011 §1). 읽기 전용. 결과 한 덩어리를 stdout 으로(크론 announce 가 오너에게 전달).
확인: ① 오늘(KST) 05:00 이후 미장 리포트 커밋 존재(시각) ② index.html 마커 구간에 박스·라벨 '무매 신호'·툴팁(기준일·상위 3) ③ 리포트 실행 로그에 '무매 신호 박스 갱신 스킵' 없음."""
import re, subprocess, datetime, html
from pathlib import Path
REP = Path.home() / "mactrader-reports"; WS = Path.home() / ".openclaw" / "workspace"
KST = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(KST); since = now.replace(hour=5, minute=0, second=0, microsecond=0)
out = [f"[무매 박스 확인] {now:%Y-%m-%d %H:%M} KST"]
lg = subprocess.run(["git", "-C", str(REP), "log", "--since", since.isoformat(), "--format=%h %cd %s", "--date=format:%m-%d %H:%M"], capture_output=True, text=True).stdout.strip().splitlines()
us = [l for l in lg if "미장 리포트" in l]
out.append("미장 리포트 커밋: " + (us[0] if us else "없음(아직 실행 전이거나 미발행)"))
txt = (REP / "index.html").read_text(encoding="utf-8")
m = re.search(r"<!--MM_SIG_BEGIN-->(.*?)<!--MM_SIG_END-->", txt, re.S)
if not m: out.append("박스: 마커 구간 없음 ❌")
else:
    box = m.group(1); lab = re.search(r"<span>([^<]*)</span>", box); tt = re.search(r'title="([^"]*)"', box)
    title = html.unescape(tt.group(1)) if tt else ""
    out.append(f"박스: 라벨 '{lab.group(1) if lab else '없음'}' · 툴팁 '{title}'")
    out.append("판정: " + ("정상(라벨 '무매 신호', 기준일·상위 3 표시)" if lab and lab.group(1) == "무매 신호" and "기준일" in title else ("데이터 확인 중 표시(fail-closed 동작)" if "데이터 확인 중" in title else "이상 — 라벨 또는 툴팁 확인 필요")))
skip = []
for f in ("role1_us.log", "role1_us_err.log"):
    p = WS / "logs" / f
    if p.exists():
        for l in p.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]:
            if "무매 신호 박스 갱신 스킵" in l: skip.append(f"{f}: {l[:160]}")
out.append("리포트 로그의 박스 스킵 문구: " + ("; ".join(skip) if skip else "없음"))
print("\n".join(out))
