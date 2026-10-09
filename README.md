# mm-rotation — 3배 ETF/ETN M-score 참고 표

참고용 표시 계층이다. 매매·자금·경보 코드와 무관하며 개인 보유·평단 정보를 쓰지 않는다. 투자 권유가 아니다.

- 공식: `MSCORE_V1`(σ60·RS_A·MA50/MA200 백분위 균등 평균). 정의 파일 `MSCORE_V1_1.md` sha256 `2c2b8f73ebd37bd862aa7206591bb032d8e71c716576c9fa92ac16d01079c590` (v1.1 = 산식 불변, 1x 매핑표만 교체. 구 v1 sha `41e4f209…c83a` 는 `MSCORE_V1.md` 에 보존) — 매 실행마다 대조, 불일치 시 중단·경보.
- 적격 기준: `data/eligibility.yaml` (E1~E5, 운영값 — 변경 가능)
- 일일: `scripts/mm_daily.py` (launchd `com.mm.rotation_daily`, 화~토 08:15 KST) → `data/scores/`, `docs/`
- 주간: `scripts/mm_weekly_scan.py` (launchd `com.mm.rotation_weekly`, 토 12:00 KST) → `data/issues/`, `data/status.json`, `data/new_products.json`
- 페이지: `docs/` (GitHub Pages)

- 1x 원칙(MM-PROXY-FIX-20261014): **1x = 발행사 공시 공식 지수 하나.** 지수 명세·채택 경로·출처는 `data/index_specs.yaml`, 합성 계열 정의는 `data/proxy_specs.json` + `data/ext/`(동결 연장), 생성기 `scripts/mm_proxy.py`. 매핑 교체 전 점수 이력은 `data/scores_old_mapping_20261009/` 에 보존.
