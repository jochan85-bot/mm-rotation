# mm-rotation — 3배 ETF/ETN M-score 참고 표

참고용 표시 계층이다. 매매·자금·경보 코드와 무관하며 개인 정보를 쓰지 않는다. 투자 권유가 아니다.

- 산식·모집단·기간 평균 순위·이상 봉 가드·1x 원칙·한계의 **설명은 `docs/guide.html`(가이드 페이지)로 옮겼다** — 이 README 는 운영(파일·잡·테스트)만 적는다. 정의 파일 `MSCORE_V1_1.md` sha256 `b4ce99a877b7a4e053de14458c61fbfb7a592e5b4375a7d6ddacb9374fecd8f8` 은 매 실행마다 대조하며 불일치하면 중단·경보한다. 운영값은 `data/eligibility.yaml`.
- 일일: `scripts/mm_daily.py` (launchd `com.mm.rotation_daily`, 화~토 08:15 KST) → `docs/data/scores/YYYY-MM-DD.csv`, `docs/data/index.json`, `docs/`. 파일이 없거나 규칙 버전(첫 줄 `rule=`)이 다른 날짜는 자동으로 다시 산출한다.
- 주간: `scripts/mm_weekly_scan.py` (launchd `com.mm.rotation_weekly`, 토 12:00 KST) → `data/issues/`, `data/status.json`, `data/pipeline.json`(발행 예정), `data/new_products.json`(상장·분류 통과), `data/excluded_candidates.json`(규칙 제외 사유), `data/candidate_overrides.json`(오너 지시 제외). 판정 규칙 `scripts/mm_rules.py`, 신규 상품 분류 `scripts/mm_newprod.py`.
- 페이지(MM-PAGE-V3-DESIGN-20261010): `docs/` (GitHub Pages) — `index.html`(달력 통합 순위표) · `guide.html`(기술 설명) · `products.html`(목록) · `products/<티커>.html`(37종) · `data/series/<티커>.json`(차트). 스타일 `docs/assets/mm.css`, 동작 `assets/index.js`·`chart.js`. 렌더러 `scripts/mm_site.py`·`mm_guide.py`, 종목 문구 `scripts/mm_page_text.py`(products.yaml 이 바뀐 종목만 LLM 재생성 → `data/products_page.json`, 마지막 수정일 갱신), 제외 사유 문장표 `data/exclusion_text.yaml`.
- 수동 실행한 산출물은 페이지 상단에 `수동 산출`이 표시된다(예약 실행이면 launchd 가 설정하는 `XPC_SERVICE_NAME` 으로 구분).
- 테스트: `python3 tests/test_v23.py`(배지·이상 봉·E3·기간 평균·분류·렌더), `python3 tests/run_fixtures.py`(공시 판정 규칙 7종 픽스처).

- 1x 원칙·경로 집계·백테스트 한계·알려진 한계·달력 소급 규칙은 모두 `docs/guide.html` 에 있다. 지수 명세 `data/index_specs.yaml`, 합성 계열 `data/proxy_specs.json`+`data/ext/`, 생성기 `scripts/mm_proxy.py`, 매핑 교체 전 이력 `data/scores_old_mapping_20261009/`.
- 달력 데이터: `docs/data/scores/YYYY-MM-DD.csv`(첫 줄 `# date= N= rule=`) + `docs/data/index.json`. 정합 검사 `python3 tests/test_calendar.py`. (`history.html` 은 삭제 — 달력은 메인에 통합.)
- 구성 종목 링크(MM-CLOSE-FINAL-20261010): 종목 페이지 구성 박스 → 네이버 증권 해외종목 **기업개요 탭** `/worldstock/stock/{코드}/overview`(데이터가 없으면 종합 페이지, 코드가 없으면 네이버 검색). 코드 접미 실측 규칙은 나스닥 `.O` · NYSE 는 종목마다 접미 없음 또는 `.K` · AMEX/Arca ETF 는 접미 없음 · 점 티커는 `BRKb`. 규칙·실측일 `data/link_rules.yaml`, 선택 코드 `scripts/mm_links.py`(주간 `mm_holdings` 갱신이 호출), 구성 데이터 `data/holdings.json`·`scripts/mm_holdings.py`.
- 지수 이력 재구성 표시(MM-NEWIDX-CHECK-20261011): 정적 사실 `data/index_history.json`(공식 지수 레벨 경로 18종의 공식 첫 날짜·연장 방법·구간·꼬리 보정·상장일, `python3 scripts/mm_idxhist.py --build` 로 재생성 — 새 공식 지수 레벨 종목을 편입하면 다시 실행), 비율·사유 계산 `scripts/mm_idxhist.py`(점수 창 252거래일), 표시는 메인 JS `why()`·장기순위 `compute_longterm`·종목 페이지·Guide 부록 A. 점수·순위에는 영향 없음. 테스트 `python3 tests/test_idxhist.py`.
- 적격 규칙(MM-RECON-RULE-20261011): 1x 시계열의 점수 창(최근 252거래일) 안에 `data/index_history.json` 의 방법이 "구성종목 복제"인 연장 구간이 1일이라도 있으면 그 종목은 M-score 미산출(table=`이력부족`). 판정·복귀 예정일 `scripts/mm_idxhist.py`(`BLOCK_METHODS`·`recon_blocked`·`eligible_date`), 적용 `mm_lib.compute`. 규칙 변경 후 날짜 파일은 `python3 scripts/mm_daily.py --no-fetch --no-push --no-alert --regen-from=YYYY-MM-DD` 로 해당 날짜부터 강제 재산출(RULE_VER 는 그대로 — 바뀌지 않은 날짜 파일은 바이트 동일). 테스트 `python3 tests/test_recon.py`.
