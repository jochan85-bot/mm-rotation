"""[MM-RESTORE-20261028 §4-2] mm_lib import 단계 실패용 경보 — 표준 라이브러리만 쓴다(mm_lib·numpy·pandas 에 의존하지 않음).
일일·주간 잡의 본문 try/except 는 mm_lib 가 import 된 뒤에야 동작하므로, import 단계(FileNotFoundError·ImportError 등)에서 죽으면
launchd stderr 에만 남고 침묵했다. 여기서 alerts.log 1줄 + 텔레그램 1건을 낸다. 시험용: MM_BOOTALERT_SUPPRESS=1 이면 발송 억제."""
import os, json, subprocess, time, traceback, urllib.parse, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
def fail(kind, exc):
    msg = f"[mm_rotation] {kind} 기동 실패(import 단계): {type(exc).__name__}: {str(exc)[:300]}"
    try:
        logs = ROOT / ".local" / "logs"; logs.mkdir(parents=True, exist_ok=True)
        with open(logs / "alerts.log", "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n{traceback.format_exc()[-1200:]}\n")
    except Exception:
        pass
    if os.environ.get("MM_BOOTALERT_SUPPRESS") == "1":
        print("[bootalert] 발송 억제(시험):", msg); return False
    for k in range(2):
        try:
            chat = json.load(open(ROOT / ".local" / "config.json"))["chat_id"]
            tok = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", "mactrader-telegram-bot-token", "-a", "mactrader", "-w"],
                                 capture_output=True, text=True, timeout=20).stdout.strip()
            if not tok: return False
            body = urllib.parse.urlencode({"chat_id": chat, "text": msg[:3900], "disable_web_page_preview": "true"}).encode()
            if urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=body), timeout=30).status == 200:
                return True
        except Exception:
            time.sleep(10)
    return False
