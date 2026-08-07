# v3 ready / unmatched production distribution

- 검증일: 2026-08-05 (Asia/Seoul)
- parser: `option-sections-v3-structure-guard`
- 대상: 평면형 또는 평면형 후보 9개; 계층형 확정 4개는 제외
- production 코드·API·DB schema 변경 없음
- 전체 전성분, HTML, Flight payload, 쿠키, storage state, 스크린샷 저장 없음

구조화 결과는 [v3_ready_unmatched_distribution.json](./v3_ready_unmatched_distribution.json)에 있다.

## 실행 및 사전 cache

9개 모두 실행했고 환경·브라우저·수집 실패는 없었다. 최신 v3 ready인 `A000000251851`, `A000000226593`, `A000000174064`는 강제 수집 없이 cache hit했다. 나머지 6개만 외부 수집을 1회 수행했다.

| product_id | 기존 상태/version | cache usable | 기존 canonical key | v2/v3 ingredient key | retry/backoff | 실행 경로 |
|---|---|---:|---:|---:|---|---|
| A000000251851 | ready/v3 | Y | 5 | 0/5 | 없음 | v3 cache |
| A000000226593 | ready/v3 | Y | 7 | 0/7 | 없음 | v3 cache |
| A000000171371 | 없음 | N | 0 | 0/0 | active | 공개 409 확인 후 공식 `force_refresh` |
| A000000163378 | 없음 | N | 0 | 0/0 | 종료 | live collection |
| A000000177984 | 없음 | N | 0 | 0/0 | 종료 | live collection |
| A000000120656 | 없음 | N | 0 | 0/0 | 종료 | live collection |
| A000000174064 | ready/v3 | Y | 10 | 0/10 | 없음 | v3 cache |
| A000000241210 | ready state 없음 | N | 0 | 0/0 | 종료 | live collection; legacy v1 ingredient row 48개 존재 |
| A000000197231 | 없음 | N | 0 | 0/0 | 종료 | live collection |

대상 9개에는 v2 option ingredient key가 없었다. 별도 안전 대조군 `A000000258200`의 실제 v2 key를 `/products/analyze`에 직접 전달한 결과 HTTP 400으로 차단됐다.

## 상품별 실제 상태

cached 상품의 raw option 수와 header 진단은 직전 v3 수집 결과를 사용했으며 이번에는 parser와 Playwright를 재실행하지 않았다.

| product_id | 상품명 | 사전 가설 | raw/sold-out/canonical | headers valid/total | M/U/O/A/M/F | metadata | 실제/공개 | ready keys | analyze |
|---|---|---|---:|---:|---:|---|---|---:|---|
| A000000251851 | 네이밍 올데이 마스터 쿠션 | ready | 11/1/5 | 5/5 | 5/0/0/0/0/0 | cached v3 | ready/ready | 5 | 200, 42 ingredients |
| A000000226593 | 네이밍 제로 그래비티 커버 업 쿠션 | ready | 7/1/7 | 7/7 | 7/0/0/0/0/0 | cached v3 | ready/ready | 7 | 200, 51 ingredients |
| A000000171371 | 네이밍 플러피 파우더 블러쉬 | ready 또는 unmatched | 24/11/22 | 0/0 | 0/22/0/0/0/0 | reordered | unmatched/retry 409 | 0 | blocked |
| A000000163378 | 정샘물 스킨 누더 커버레이어 쿠션 | unmatched | 5/0/5 | 4/4 | 3/2/1/0/0/0 | complete | unmatched/unavailable | 0 | blocked |
| A000000177984 | 헤라 센슈얼 누드 글로스 | unmatched | 20/2/19 | 5/6 | 5/14/0/0/1/0 | reordered | unmatched/unavailable | 0 | blocked |
| A000000120656 | 투쿨포스쿨 프로타주 펜슬 | unmatched | 20/6/15 | 9/9 | 7/8/2/0/0/0 | reordered | unmatched/unavailable | 0 | blocked |
| A000000174064 | 에스쁘아 비글로우 파운데이션 | ready + orphan | 10/0/10 | 14/14 | 10/0/4/0/0/0 | cached v3 | ready/ready | 10 | 200, 48 ingredients |
| A000000241210 | 롬앤 더 쥬시 래스팅 틴트 | 미확정 | 45/7/38 | 0/0 | 0/38/0/0/0/0 | reordered | unmatched/unavailable | 0 | blocked |
| A000000197231 | 롬앤 글래스팅 컬러 글로스 | 미확정 | 22/3/18 | 0/0 | 0/18/0/0/0/0 | reordered | unmatched/unavailable | 0 | blocked |

`M/U/O/A/M/F`는 matched/unmatched/orphan/ambiguous/malformed/unsupported 순서다. 모든 문서는 `option_full_sections`로 분류됐고 예상 밖 unsupported는 없었다.

사전 상태와 실제 상태는 확정 가설 7개에서 모두 일치했다. A171371은 허용된 두 가설 중 unmatched였고, 미확정 롬앤 2개도 실제로는 unmatched였다.

## Matched canonical 옵션과 규칙

- `A000000251851`: 17N, 23N, 22N, 21N, 21P — 저장된 `explicit_hash_alphanumeric_code_exact`
- `A000000226593`: 19P, 17N, 19N, 23N, 22N, 21N, 21P — 저장된 `explicit_hash_alphanumeric_code_exact`
- `A000000163378`: 페어라이트, 라이트, 미디엄 — `explicit_star_colon_exact`
- `A000000177984`: 란제리, 380 체리쉬, 462 스피치리스, 102 플러티, 18 이노센트 — `explicit_bracketed_exact`
- `A000000120656`: 01 샤이닝 린넨, 02 로지 듀, 08 센티드 부케, 09 쉬어 누드, 11 듀 베이지, 07 뮤티드 토프, 10 클래시 휘그 — `explicit_bracketed_exact`
- `A000000174064`: 22N 뉴트럴페탈, 25N 뉴트럴탠, 22C 쿨페탈, 13N 뉴트럴포슬린, 23C 쿨베이지, 23N 뉴트럴베이지, 21N 뉴트럴아이보리, 3C 웨딩피치, 20C 쿨바닐라, 21C 쿨아이보리 — 저장된 `explicit_bracketed_exact`

A171371과 롬앤 2개는 인식된 명시적 header가 0개라 사용된 매칭 규칙이 없다.

## Unmatched canonical 옵션

- `A000000171371` (22): [Best] 헤일로(HALO), [Best] 베이글 (BAGEL), [Best] 토스트 (TOAST), [Best] 필로우 (PILLOW), 피이그 (FEEG), 카야 (KAYA), 헤이즈 (HAZE), 타로 (TARO), 텐더 (TENDER), 포브 (POVE), 어빗 (A BIT), 페이지 (PAGIE), 배쉬풀(BASHFUL), 베이글(BAGEL), 필로우(PILLOW), 치피 (CHIPPY), 조이 (JOY), 헤이그 (HAGUE), 티크 (TEAK), 야미 (YUMMY), [Best] 니제 (NIESE), 그레이브 (GRAVE)
- `A000000163378` (2): 엔라이트, 미디엄 딥
- `A000000177984` (14): 조지아, 로즐린, 10 베어로맨스, 133 로지체리, 410 세레나데, 325 선키스드, 421 로즐린, 415 브라우니보이, 422 란제리, 401 누디스트, 390 웻베리, 418 허니드, 470 체리콕, 200 조지아
- `A000000120656` (8): 21 스위티 베일, 14 피치 블룸, 15 피오니 티, 16 밀키 로즈, 18 프로스티 라벤더, 19 베베 핑크, 20 미스티 그린, 22 허밍 글로우
- `A000000241210` (38): 41소이아몬드, 42소이 피그, 39 미스티 피치, 40 베이지 그레이프, 38 클라우디베리, 23 피치 피치 미, 01 포멜로스킨, 02 누카다미아, 03 베어 그레이프, 04 피그피그, 05 쥬쥬브, 06 필링앵두, 07 체리밤, 08 핑크 펌킨, 09 멀드 피치, 10 베어 애프리콧, 11 파파야 잼, 13 잇 도토리, 14 아몬드 로즈, 15 베어 피그, 16 플럼 콕, 19 썸머 센트, 20 쥬쥬 피그, 21 그레이프 밤, 22 도토리 밤, 24 베어 쥬시 오, 26 신비 복숭아, 27 허니 듀 멜론, 28 설화 딸기, 29 조선 무화과, 30 보늬 밤, 31 탠드 코코, 32 태니 구아바, 33 알로하 쥬시, 34 차이 애프리콧, 35 얼그레이 리치, 17 다크 코코넛, 37 구아바데이지
- `A000000197231` (18): 01피오니발레, 12크림 쉘, 14 뮤이지, 19 조이베리, 20 클라우드민트, 02 너티 베이그, 03 로즈 핀치, 04 그레이피 웨이, 05 딤 모브, 06 디픈 무어, 08 체리 업, 13 구아바크림, 21 토피 크림, 22 크림 머드, 23 크림 헤이즈, 24 크림베베, 25 크림빈즈, 07 스프링 피버

unmatched section의 ingredient list는 전부 비어 있었고 partial option key는 공개 응답이나 ready cache에 저장되지 않았다.

## 원인 분류

| product_id | 원인 | 근거 |
|---|---|---|
| A000000171371 | unsupported_header_grammar | `#영문코드` 후보가 현재 alphanumeric hash 문법에 포함되지 않아 detected header 0. 자동 문법 확장은 하지 않음 |
| A000000163378 | no_corresponding_document_header + canonicalization_difference | 미디엄 딥 header 없음; 엔라이트와 orphan `★ N라이트 :`는 exact identity 불일치 |
| A000000177984 | no_corresponding_document_header + malformed_header | 14개 누락; `[누디스트)` 1개는 괄호 불일치로 malformed |
| A000000120656 | no_corresponding_document_header + document_not_updated | 현재 옵션 8개 누락과 현재 판매에 없는 `[12호]`, `[13호]` orphan 공존 |
| A000000241210 | unknown | 38개 모두 unmatched이고 명시적 header 0; 공통 formula/미지원 문법을 원문 근거 없이 확정하지 않음 |
| A000000197231 | unknown | 18개 모두 unmatched이고 명시적 header 0; 공통 formula/미지원 문법을 원문 근거 없이 확정하지 않음 |

원인 분포는 no-corresponding 3, unsupported grammar 1, document-not-updated 1, canonicalization difference 1, malformed 1, unknown 2다. 한 상품에 복수 원인이 있을 수 있으며 possible-shared-formula는 근거 부족으로 0이다.

## Orphan 및 ready 안전성

- ready + orphan은 `A000000174064` 한 개다: `[기존 21호 아이보리]`, `[기획증정 - 스틱파데 20호]`, `[기획증정 - 스틱파데 21호]`, `[기획증정 - 스틱파데 22호]`.
- unmatched 상품 orphan: `A000000163378`의 `★ N라이트 :`, `A000000120656`의 `[12호]`, `[13호]`.
- 원문 구간 기준 orphan header가 matched ingredient block에 남은 경우는 0건이다.
- ready DB는 option key/ingredient record가 5/5, 7/7, 10/10으로 일치하고 key 충돌이 없다. 최소 ingredient 수는 각각 42, 51, 48개다.
- A251851은 원본 판매 옵션 11개가 canonical 5개를 공유하며, 나머지 ready 상품도 저장된 source option 이름 수와 canonical 관계가 유지됐다.

## Cache, analyze, 공개 API

- ready 3개는 첫·둘째 선택 모두 v3 cache hit였고 Playwright 실행은 0회다.
- ready 3개의 실제 `/products/analyze`는 모두 HTTP 200: ingredient count 42/51/48.
- unmatched 6개는 ready collection state와 partial option key를 저장하지 않았다. 즉시 2차 호출은 모두 HTTP 409이며 Playwright 재실행은 0회다.
- A171371은 사전 backoff 공개 409를 확인한 뒤 공식 `force_refresh` 서비스 경로로 1회 수집했고, 이후 재호출도 409였다.
- live 수집 5개는 DOM/Flight `complete_match_reordered`, A163378만 동일 순서 `complete_match`였다. 재정렬 후 metadata 충돌은 없었다.
- 공개 API에서 mapping diagnostics, raw header, selector, 원문은 노출되지 않았다. review extractor/fallback도 존재하거나 호출되지 않았다.

## 분포

- 실행: total 9, executed 9, not-executed 0, environment failure 0, collection failure 0, parser executed 6
- 상태: ready 3, unmatched 6, unsupported 0, ambiguous 0, malformed 차단 포함 상품 1
- 옵션: canonical 139, matched 37, unmatched 102, orphan 7
- 전체 옵션 매칭률: 37/139 = **26.6%**
- ready 평균 canonical 옵션 수: **7.33**
- unmatched 상품 평균 매칭률: **22.2%**

상품별 매칭률은 A251851 100%, A226593 100%, A171371 0%, A163378 60%, A177984 26.3%, A120656 46.7%, A174064 100%, A241210 0%, A197231 0%다.

## 테스트와 남은 항목

```text
python -m compileall app: passed
pytest: 131 passed, 1 warning in 3.04s
git diff --check: passed
```

경고는 FastAPI TestClient의 Starlette/httpx deprecation warning이다.

이번 검증에서 새 false-ready나 cache 안전성 버그는 발견되지 않았다. 다만 A171371의 pure-English hash header 후보, 롬앤 2개의 header 0건 문서, A177984 malformed 표기는 후속 연구 대상이다. ready 분석 smoke에서 임베딩 모델이 반복 초기화되어 지연이 컸으므로 별도 성능 조사 가치가 있다.

요청 제한에 따라 fuzzy/오탈자 보정, 공통 formula 복제, 계층형 병합, 신규 header 문법, 리뷰 fallback은 구현하지 않았다.
