# mm-rotation — 3배 ETF/ETN M-score 참고 표

참고용 표시 계층이다. 매매·자금·경보 코드와 무관하며 개인 정보를 쓰지 않는다. 투자 권유가 아니다.

- 공식: `MSCORE_V1`(σ60·RS_A·MA50/MA200 백분위 균등 평균). 정의 파일 `MSCORE_V1_1.md` sha256 `69de08d1f26936f347f16d4e91832fb7e304de38ef8908deb76f4eb9d82bdaa2` (v1.1 = 산식 불변, 1x 매핑표만 교체; V2.3 후속 기록 추가로 sha 재등재, 직전 `2c2b8f73…c590`. 구 v1 sha `41e4f209…c83a` 는 `MSCORE_V1.md` 에 보존) — 매 실행마다 대조, 불일치 시 중단·경보.
- **모집단(V2.3)**: 유니버스 전체(37종 + 주간 점검 B 편입분) 중 **E5(문제 공지) 미해당 ∧ ⚠(최신 봉 불일치·이상 봉·피처 불가) 없는 종목**. 백테스트(MM-P4~P7, MM-PROXY-FIX)의 모집단과 같은 정의다. E1~E4 는 제외 조건이 아니라 **표시 전용 배지**(`거래 가능성` 열)이며 점수·순위를 바꾸지 않는다. 값은 `data/eligibility.yaml`(운영값 — 백테스트 근거 아님, 오너 변경 가능).
- **기간 평균 순위**: 5·20·60일 순위 = 해당 N거래일의 **일별 M-score 단순평균**을 오늘 모집단 안에서 순위 매긴 값(결측일 제외, 창의 80% 미만이면 `—`). 일별 M-score 는 *그날그날의 모집단 안 백분위 점수*라 모집단이 날마다 달라질 수 있고, 평균은 그 점수들의 평균이다(절대 수준의 평균이 아님).
- **이상 봉 가드**: 1x(지수 레벨) 일간수익률 |r|>25% 인 봉이 60봉 창 안에 있으면 ⚠·순위 제외·σ60 보류, 3배 봉 |r|>75%(기준일 봉)이면 ⚠. 전 구간 목록 `data/anomalies.csv`. 기준값은 운영값(`eligibility.yaml`).
- 일일: `scripts/mm_daily.py` (launchd `com.mm.rotation_daily`, 화~토 08:15 KST) → `data/scores/`, `docs/`. 이력은 규칙 버전(`rule_ver`)이 다른 날짜를 자동 재산출한다.
- 주간: `scripts/mm_weekly_scan.py` (launchd `com.mm.rotation_weekly`, 토 12:00 KST) → `data/issues/`, `data/status.json`, `data/pipeline.json`(발행 예정), `data/new_products.json`(상장·분류 통과), `data/excluded_candidates.json`(규칙 제외 사유), `data/candidate_overrides.json`(오너 지시 제외). 판정 규칙 `scripts/mm_rules.py`, 신규 상품 분류 `scripts/mm_newprod.py`.
- 페이지: `docs/` (GitHub Pages). 상품 특징표 `data/products.yaml` → `products.html`(티커 클릭 시 카드로 이동, 카드는 접기/펼치기).
- 수동 실행한 산출물은 페이지 상단에 `수동 산출`이 표시된다(예약 실행이면 launchd 가 설정하는 `XPC_SERVICE_NAME` 으로 구분).
- 테스트: `python3 tests/test_v23.py`(배지·이상 봉·E3·기간 평균·분류·렌더), `python3 tests/run_fixtures.py`(공시 판정 규칙 7종 픽스처).

- 1x 원칙(MM-PROXY-FIX-20261014): **1x = 발행사 공시 공식 지수 하나.** 지수 명세·채택 경로·출처는 `data/index_specs.yaml`, 합성 계열 정의는 `data/proxy_specs.json` + `data/ext/`(동결 연장), 생성기 `scripts/mm_proxy.py`. 매핑 교체 전 점수 이력은 `data/scores_old_mapping_20261009/` 에 보존.
- 한계: 후B(합성층 재편입) 기준 섀도 진입 가능, 후A(허용집합 동결)에서는 판정 ①(a) 불성립 — 2022 깊이 우위는 에너지·FANG ETN 합성 이력에 의존(`MSCORE_V1_1.md` 후속 기록).
