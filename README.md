# mm-rotation — 3배 ETF/ETN M-score 참고 표

참고용 표시 계층이다. 매매·자금·경보 코드와 무관하며 개인 정보를 쓰지 않는다. 투자 권유가 아니다.

- 공식: `MSCORE_V1`(σ60·RS_A·MA50/MA200 백분위 균등 평균). 정의 파일 `MSCORE_V1_1.md` sha256 `b4ce99a877b7a4e053de14458c61fbfb7a592e5b4375a7d6ddacb9374fecd8f8` (v1.1 = 산식 불변, 1x 매핑표만 교체; V2.3 후속 기록 추가로 sha 재등재, 직전 `69de08d1…bdaa2`(← `2c2b8f73…c590`). 구 v1 sha `41e4f209…c83a` 는 `MSCORE_V1.md` 에 보존) — 매 실행마다 대조, 불일치 시 중단·경보.
- **모집단(V2.3)**: 유니버스 전체(37종 + 주간 점검 B 편입분) 중 **E5(문제 공지) 미해당 ∧ ⚠(최신 봉 불일치·이상 봉·피처 불가) 없는 종목**. 백테스트(MM-P4~P7, MM-PROXY-FIX)의 모집단과 같은 정의다. E1~E4 는 제외 조건이 아니라 **표시 전용 배지**(`거래 가능성` 열)이며 점수·순위를 바꾸지 않는다. 값은 `data/eligibility.yaml`(운영값 — 백테스트 근거 아님, 오너 변경 가능).
- **기간 평균 순위**: 5·20·60일 순위 = 해당 N거래일의 **일별 M-score 단순평균**을 오늘 모집단 안에서 순위 매긴 값(결측일 제외, 창의 80% 미만이면 `—`). 일별 M-score 는 *그날그날의 모집단 안 백분위 점수*라 모집단이 날마다 달라질 수 있고, 평균은 그 점수들의 평균이다(절대 수준의 평균이 아님).
- **이상 봉 가드**: 1x(지수 레벨) 일간수익률 |r|>25% 인 봉이 60봉 창 안에 있으면 ⚠·순위 제외·σ60 보류, 3배 봉 |r|>75%(기준일 봉)이면 ⚠. 전 구간 목록 `data/anomalies.csv`. 기준값은 운영값(`eligibility.yaml`).
- 일일: `scripts/mm_daily.py` (launchd `com.mm.rotation_daily`, 화~토 08:15 KST) → `docs/data/scores/YYYY-MM-DD.csv`, `docs/data/index.json`, `docs/`. 파일이 없거나 규칙 버전(첫 줄 `rule=`)이 다른 날짜는 자동으로 다시 산출한다.
- 주간: `scripts/mm_weekly_scan.py` (launchd `com.mm.rotation_weekly`, 토 12:00 KST) → `data/issues/`, `data/status.json`, `data/pipeline.json`(발행 예정), `data/new_products.json`(상장·분류 통과), `data/excluded_candidates.json`(규칙 제외 사유), `data/candidate_overrides.json`(오너 지시 제외). 판정 규칙 `scripts/mm_rules.py`, 신규 상품 분류 `scripts/mm_newprod.py`.
- 페이지: `docs/` (GitHub Pages). 상품 특징표 `data/products.yaml` → `products.html`(티커 클릭 시 카드로 이동, 카드는 접기/펼치기).
- 수동 실행한 산출물은 페이지 상단에 `수동 산출`이 표시된다(예약 실행이면 launchd 가 설정하는 `XPC_SERVICE_NAME` 으로 구분).
- 테스트: `python3 tests/test_v23.py`(배지·이상 봉·E3·기간 평균·분류·렌더), `python3 tests/run_fixtures.py`(공시 판정 규칙 7종 픽스처).

- 1x 원칙(MM-PROXY-FIX-20261014): **1x = 발행사 공시 공식 지수 하나.** 지수 명세·채택 경로·출처는 `data/index_specs.yaml`, 합성 계열 정의는 `data/proxy_specs.json` + `data/ext/`(동결 연장), 생성기 `scripts/mm_proxy.py`. 매핑 교체 전 점수 이력은 `data/scores_old_mapping_20261009/` 에 보존.
- 한계: 후B(합성층 재편입) 기준 섀도 진입 가능, 후A(허용집합 동결)에서는 판정 ①(a) 불성립 — 2022 깊이 우위는 에너지·FANG ETN 합성 이력에 의존(`MSCORE_V1_1.md` 후속 기록).

## 알려진 한계 (MM-PAGE-V2.3-FOLLOWUP-20261016 §3, 수정 없음)
- **공시 판정 규칙(`mm_rules.py`)**: 신규 상품이 같은 공시 창에 함께 나오면 인접 문구가 신규 상품에도 귀속될 수 있다(예: FNGB 를 별칭맵에 넣으면 같은 공시의 FNGU 상환이 FNGB 에도 잡힘 — `run_fixtures.py` 에 XFAIL 표기, 현 유니버스에는 FNGB 없음). UBOT 2026-03-13 보충서(지수 방법론 개정)는 지수 교체가 아니라 개정이라 잡지 않는다.
- **신규 상장 지수 확정**: 자동 확정은 구현하지 않는다(신규 상장은 드물고 지수 확정은 문서 확인이 필요). 신규 상장은 "지수 확정 대기"로 표시하고 주간 텔레그램에 1줄로 알린다.
- **PR/TR**: ETF 25종의 가격수익/총수익 구분은 발행사 공시에 없다([부재]). M-score 피처(σ60·12-1개월 수익률·MA50/MA200)에 미치는 차이는 배당 수준이라 점수에 사실상 영향이 없다고 보고 추가 조사하지 않는다.
- **분할 이력**: 상품 카드의 분할·역분할은 yfinance 분할 데이터 기준이며 발행사 공시와 별도 대조하지 않는다.
- **저유동 배지 기준**: 20일 평균 거래대금 < $0.3M(`eligibility.yaml` E2, 운영값, 2026-10-09 $1M→$0.3M 변경). 근거: 무매 1회 매수액 대비 충분하고 `무거래N` 배지가 체결 위험을 별도로 잡는다.

## 달력·날짜별 순위 소급 (MM-PAGE-V2.3-FOLLOWUP-20261016 §4)
- `history.html` = 달력 뷰. 월 단위 이동, 날짜 칸 아래 숫자 = 그날 모집단 N, 데이터 없는 날(휴장·결측)은 비활성. 날짜를 누르면 그 기준일의 순위표(§8 열 전부, 거래 가능성·5/20/60일 순위 포함)를 같은 페이지에 표시. 달력 JS 는 `data/index.json` · `data/scores/<날짜>.csv` · `data/tickers.json` 만 읽는다(정적, 외부 라이브러리 0).
- **저장 위치**: GitHub Pages 가 `/docs` 만 서빙하므로 `docs/data/scores/YYYY-MM-DD.csv` + `docs/data/index.json`(날짜·N) + `docs/data/tickers.json`(티커별 지수명·툴팁). (`data/scores/` 가 아님.) 각 CSV 첫 줄 `# date=… N=… rule=…`, 열은 순위표 열만, 모집단 행만 기록.
- **범위**: 2020-01-02 ~ 최신. 5/20/60일 평균 순위의 창을 채우려고 시작 전 약 64거래일은 기록 없이 메모리로만 산출한다.
- **소급 모집단** = 그 날짜에 3배 일봉이 존재 ∧ 1x 피처 산출 가능(252봉) ∧ 이상 봉 ⚠ 아님. 생성 규칙은 매일 산출과 같은 코드(`mm_lib.compute`)·M-score v1.1 산식·현행 1x 매핑.
- **E5(공지 제외)는 소급 적용하지 않는다**(과거 공지 데이터 없음). 저유동·무거래 배지는 그 날짜 직전 20봉으로, 근사·표본부족 배지는 현재 측정값(β·R²)으로 표시한다. 소급은 현재 1x 매핑을 과거에 적용한 값이므로 당시 실제 공개 순위가 아니다.
- 소급 시작 전 상장하지 않았거나 시계열이 사라진 종목은 그 날짜 모집단에서 빠진다(상장 전 날짜의 N 이 작은 이유).
- 테스트: `python3 tests/test_calendar.py`(헤더 N=행 수, index.json=파일 목록, 순위 단조).

- 1x 경로 집계(실측, `data/index_specs.yaml`·`product_info.csv`): exact 1x ETF 18 · 공식 지수 레벨 18 · 복합 1(TPOR) = 37.
