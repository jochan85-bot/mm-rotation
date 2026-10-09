# mm-rotation — 3배 ETF/ETN M-score 참고 표

참고용 표시 계층이다. 매매·자금·경보 코드와 무관하며 개인 보유·평단 정보를 쓰지 않는다. 투자 권유가 아니다.

- 공식: `MSCORE_V1`(σ60·RS_A·MA50/MA200 백분위 균등 평균). 정의 파일 sha256 `41e4f209f338ba7ebb09bc7905be081f99e6b5abfef3170b84494bb223a9c83a` — 매 실행마다 대조, 불일치 시 중단·경보.
- 적격 기준: `data/eligibility.yaml` (E1~E5, 운영값 — 변경 가능)
- 일일: `scripts/mm_daily.py` (launchd `com.mm.rotation_daily`, 화~토 08:15 KST) → `data/scores/`, `docs/`
- 주간: `scripts/mm_weekly_scan.py` (launchd `com.mm.rotation_weekly`, 토 12:00 KST) → `data/issues/`, `data/status.json`, `data/new_products.json`
- 페이지: `docs/` (GitHub Pages)
