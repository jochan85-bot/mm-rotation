"""[MM-ALERT-PATH-20261028] mm_rotation 텔레그램 발송 공용 함수 — 표준 라이브러리만(mm_lib·numpy 비의존).
mm_lib.tg_send · mm_bootalert.fail · mm_outputwatch.alert 가 모두 이 함수 하나를 탄다.
종전에는 성공 시 아무 기록이 없어(실패만 alerts.log) '발송은 됐는데 안 왔다'와 '발송 자체가 안 됐다'를 로그로 구분할 수 없었다.
이제 모든 시도 결과(HTTP 상태·message_id·chat_id·시도 횟수·오류)를 .local/logs/tg_sent.log 에 JSON 한 줄로 남긴다(토큰은 기록하지 않는다).
토큰=키체인(mactrader-telegram-bot-token), chat_id=.local/config.json — 뭉치 청산 알림과 같은 봇·같은 채팅.
MM_TG_SUPPRESS=1 이면 발송하지 않고 'suppressed' 로만 기록(시험용)."""
import os, json, time, subprocess, traceback, urllib.parse, urllib.request, urllib.error
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / ".local"
def _rec(d):
    try:
        (LOCAL / "logs").mkdir(parents=True, exist_ok=True)
        with open(LOCAL / "logs" / "tg_sent.log", "a") as f:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    except Exception:
        pass
def send(text, source, retries=3, wait=30, on_fail=None):
    """텔레그램 1건. 반환 dict(ok, status, message_id, chat_id, attempts, error). 예외를 올리지 않는다.
    on_fail(msg): 시도 실패 줄을 호출측 로그(alerts.log)에 남기는 콜백."""
    res = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "source": source, "ok": False, "status": None, "message_id": None,
           "chat_id": None, "attempts": 0, "error": None, "text_head": str(text)[:40]}
    def fail(msg):
        if on_fail:
            try: on_fail(msg)
            except Exception: pass
    if os.environ.get("MM_TG_SUPPRESS") == "1":
        res["error"] = "suppressed"; _rec(res); return res
    tok = ""
    for k in range(1, retries + 1):
        res["attempts"] = k
        try:
            chat = json.load(open(LOCAL / "config.json"))["chat_id"]; res["chat_id"] = chat
            tok = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", "mactrader-telegram-bot-token", "-a", "mactrader", "-w"],
                                 capture_output=True, text=True, timeout=20).stdout.strip()
            if not tok:
                res["error"] = "keychain token empty"; fail(f"tg_send 시도 {k}/{retries} 실패: 키체인 토큰 비어 있음"); break   # 재시도해도 같은 결과
            body = urllib.parse.urlencode({"chat_id": chat, "text": str(text)[:3900], "disable_web_page_preview": "true"}).encode()
            r = urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=body), timeout=30)
            res["status"] = r.status
            try:
                res["message_id"] = json.loads(r.read().decode()).get("result", {}).get("message_id")
            except Exception:
                pass
            if r.status == 200:
                res["ok"] = True; res["error"] = None
                if k > 1: fail(f"tg_send 시도 {k}/{retries} 에서 성공")
                break
            res["error"] = f"HTTP {r.status}"; fail(f"tg_send 시도 {k}/{retries} 실패: HTTP {r.status}")
        except Exception as e:
            red = lambda s: s.replace(tok, "<token>") if tok else s
            extra = f" code={getattr(e,'code',None)} reason={getattr(e,'reason',None)!r}" if isinstance(e, urllib.error.URLError) else ""
            res["error"] = red(f"{type(e).__name__}: {str(e)[:200]}"); res["status"] = getattr(e, "code", res["status"])
            fail(f"tg_send 시도 {k}/{retries} 실패: {red(type(e).__name__ + ': ' + str(e))}{extra}\n{red(traceback.format_exc())}")
        if k < retries: time.sleep(wait)
    _rec(res)
    return res
