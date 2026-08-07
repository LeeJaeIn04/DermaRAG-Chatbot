# Hierarchical false-ready and DOM/Flight mismatch

- 검증일: 2026-08-05 (Asia/Seoul)
- parser version: `option-sections-v3-structure-guard`
- production API/schema 및 DB schema 변경 없음
- 전체 HTML, Flight payload, 전성분 원문, 쿠키, storage state 저장 없음

## 수정 요약

`A000000258200` false-ready의 직접 원인은 명시적 최상위 옵션 header 6개만 경계로 사용하고, 각 구간의 구분자 없는 한·영 내부 팬 header 36개를 성분 문자열 일부로 취급한 것이다. 새 구조 guard는 option 매핑보다 먼저 반복 계층을 검사하고 확정 또는 의심 계층형이면 모든 canonical 옵션을 unsupported로 차단한다. 내부 section 병합이나 성분 합집합은 만들지 않는다.

DOM/Flight mismatch 6개는 모두 실제 데이터 충돌이 아니라 order-only mismatch였다. 개수, 보수적 정규화 이름 multiset, 이름 유일성, optionNumber 유일성, 이름별 품절 상태가 모두 일치할 때만 Flight를 이름으로 재정렬하며 최종 옵션 표시는 DOM 순서를 유지한다.

## 수정 파일

- `app/products/option_parser.py`, `option_models.py`, `option_service.py`: 구조 선검사, 계층형/needs-review 진단 및 v3 parser version
- `app/products/ingredient_extractors/oliveyoung_option_metadata.py`: 보수적 판매 옵션 identity 기반 완전 1:1 재정렬
- `app/products/ingredient_cache_service.py`: stale parser option의 직접 분석 우회 차단
- `scripts/fixtures/header_first_option_full_sections.json` 및 관련 parser/extractor/service/cache 테스트: sanitized 구조·충돌·cache 회귀
- `research/parser_validation/*`: 실상품 보고서와 최소 DOM/Flight 진단 JSON

## 새 계층형 판정

강한 계층형 판정 조건은 다음을 모두 만족한다.

1. 서로 다른 canonical 판매 옵션에 정확히 연결되는 top-level header가 2개 이상이다.
2. top-level 구간 중 2개 이상에서 판매 옵션에 직접 연결되지 않는 nested header가 각각 2개 이상 반복된다.
3. 각 nested header 뒤, 다음 header 전까지 유효 성분이 2개 이상 존재한다.
4. nested header는 명시적 header 또는 보수적인 `한글 1~2단어 + 영문 Title Case` 구조 후보이며, 후자는 구조 차단에만 사용하고 성분 매핑에는 사용하지 않는다.

각 top-level 구간에 nested header가 1개뿐이어도 동일 nested label이 2개 이상 top-level 구간에서 반복되면 `needs_review`로 차단한다. 단순 header 개수, orphan 개수, 대괄호 존재, 문서 길이만으로는 계층형으로 판정하지 않는다.

평면 `A000000174064`는 top-level 10개가 모두 matched이고 orphan 4개가 마지막 판매 옵션 뒤의 독립 section으로만 존재해 계층형 조건을 만족하지 않는다.

## 연구 artifact 및 실상품 판정

| product_id | raw/canonical | document format | top/nested | matched | unmatched | orphan | unsupported | public | 2차 동작 |
|---|---:|---|---:|---:|---:|---:|---:|---|---|
| A000000258200 | 6/6 | hierarchical_option_internal_sections | 6/36 | 0 | 0 | 36 | 6 | unavailable | 409 retry, Playwright 없음 |
| A000000180532 | 13/12 | hierarchical_option_internal_sections | 11/196 | 0 | 0 | 201 | 12 | unavailable | 409 retry, Playwright 없음 |
| A000000145650 | 7/4 | hierarchical_option_internal_sections | 4/12 | 0 | 0 | 12 | 4 | unavailable | 409 retry, Playwright 없음 |
| A000000174064 | 10/10 | option_full_sections | 10/4 후보 | 10 | 0 | 4 | 0 | ready | v3 cache hit, Playwright 없음 |

`A000000180532`은 한 판매 옵션 header가 보수적 top-level exact 조건에 연결되지 않아 top-level 집계가 11개지만, 반복 내부 구조가 충분히 확인되어 canonical 12개 전체를 unsupported로 차단한다. `A000000145650`도 기존 unmatched에서 계층형 unsupported 우선으로 바뀌었다.

## False-ready cache 무효화

- parser version을 v2에서 `option-sections-v3-structure-guard`로 올렸다.
- `A000000258200`의 기존 v2 ready row는 cache hit가 아니었고 Playwright 재수집 후 unsupported가 됐다. 새 ready option/ingredient cache는 저장되지 않았다.
- 실패 결과는 현재 정책상 collection state로 저장하지 않으므로 DB의 v2 row 자체는 남지만, version 불일치로 계속 stale이며 재사용되지 않는다.
- 과거 option key를 `/products/analyze`에 직접 보내는 경로도 현재 ready collection과 parser version 및 option key 소속을 먼저 검증하므로 stale 개별 ingredient row를 사용할 수 없다.
- `A000000174064`의 v2 ready는 한 번 재검증되어 v3 ready로 교체됐고, 2차 호출은 cache hit였다.
- `not_applicable`인 옵션 없는 공통 전성분 cache는 option parser version과 무관하게 재사용하는 기존 정책을 테스트로 유지했다.

## DOM/Flight mismatch 분석

대상 ID는 기존 production 검증 보고서에서 추출했다. 상세한 최소 DOM/Flight 행은 [flight_mismatch_diagnostics.json](./flight_mismatch_diagnostics.json)에 저장했다.

| product_id | DOM/Flight | 위치 일치 | 이름 multiset | 중복 이름 | 품절 차이 | category | 안전 재정렬 |
|---|---:|---:|---|---|---|---|---|
| A000000251851 | 11/11 | 7 | 동일·고유 | 없음 | 없음 | order_only_mismatch | 적용 |
| A000000226593 | 7/7 | 5 | 동일·고유 | 없음 | 없음 | order_only_mismatch | 적용 |
| A000000171371 | 24/24 | 0 | 동일·고유 | 없음 | 없음 | order_only_mismatch | 적용 |
| A000000150361 | 19/19 | 3 | 동일·고유 | 없음 | 없음 | order_only_mismatch | 적용 |
| A000000177984 | 20/20 | 1 | 동일·고유 | 없음 | 없음 | order_only_mismatch | 적용 |
| A000000120656 | 20/20 | 0 | 동일·고유 | 없음 | 없음 | order_only_mismatch | 적용 |

위 6개는 DOM-only/Flight-only 이름과 optionNumber 중복도 0건이다. `단품`, `기획`, `리필`, 증정 구성은 제거하지 않는 `normalize_option_label()`만 사용했다. 전성분 canonicalization 키는 Flight metadata 연결에 사용하지 않는다.

count 불일치, 이름 집합 불일치, 중복 정규화 이름, optionNumber 중복, 품절 상태 불일치, 일부만 연결 가능한 경우는 계속 `option_dom_flight_mismatch`로 차단한다. Flight parse 자체가 실패한 경우만 기존처럼 `partial_metadata_enrichment`로 DOM 옵션을 사용하며, 정상 파싱 후 충돌과 합치지 않는다.

## 재정렬 후 production 결과

| product_id | metadata | parser 결과 | 1차 공개 상태 | 2차 |
|---|---|---|---|---|
| A000000251851 | complete_match_reordered | flat 5/5 matched | ready | v3 cache hit |
| A000000226593 | complete_match_reordered | flat 7/7 matched | ready | v3 cache hit |
| A000000171371 | complete_match_reordered | flat 0/22, unmatched 22 | unavailable | 409 retry |
| A000000150361 | complete_match_reordered | hierarchical, unsupported 16 | unavailable | 409 retry |
| A000000177984 | complete_match_reordered | matched 5, unmatched 14, malformed 1 | unavailable | 409 retry |
| A000000120656 | complete_match_reordered | matched 7, unmatched 8, orphan 2 | unavailable | 409 retry |

모든 2차 호출에서 불필요한 Playwright 재실행은 없었다. ready 3개는 cache hit, mapping 실패 7개는 현재 queue/backoff 정책에 따라 HTTP 409였다. 사용자 API에는 구조 진단, selector, Flight 정보, raw header 또는 전성분 원문을 추가로 노출하지 않았다.

## 테스트

- sanitized 계층형 fixture: A258200형 bilingual 내부 header, A180532형 bracket 내부 header, A145650형 unbracketed top-level + 위치 header
- 평면 회귀: A174064 artifact, bracketed option 다수, trailing orphan 다수
- 안전 차단: uncertain repeated nested pattern, duplicate name, count/name/state/optionNumber 충돌
- cache: v2 false-ready stale, v3 ready 재사용, optionless cache 유지

```text
python -m compileall app: passed
pytest: 131 passed, 1 warning in 2.18s
git diff --check: passed
```

경고는 FastAPI TestClient의 Starlette/httpx deprecation warning이다.

## 남은 위험과 미지원 범위

- 구분자 없는 내부 header는 보수적인 반복 구조가 확인될 때 차단용으로만 탐지한다. 개별 내부 성분 매핑은 미지원이다.
- 계층형 결과와 unmatched 결과는 ready cache로 저장하지 않아 2차 상세 진단 재사용 대신 retry/backoff가 적용된다.
- 실제 DOM/Flight가 count/name/state/ID 중 하나라도 충돌하면 계속 차단하며 부분 metadata enrichment는 하지 않는다.
- fuzzy/오탈자 보정, 공통 formula 복제, 계층형 합집합, 리뷰 옵션 fallback은 추가하지 않았다.
