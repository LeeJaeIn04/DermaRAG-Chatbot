# Header-first parser production validation

- 검증일: 2026-08-05 (Asia/Seoul)
- 현재 parser: `option-sections-v2-header-first`
- 경로: production과 같은 `POST /products/select` → collection queue → Playwright extractor → option service/cache
- 범위: production 코드·DB schema·API를 변경하지 않고, 상품별 1차/2차 호출과 오프라인 회귀 테스트만 수행
- 보안: CAPTCHA 우회, 리뷰 옵션 fallback, HTML·쿠키·storage state·스크린샷·전성분 원문 저장 없음

## 결론

예상 상태와 일치한 상품은 3/11개(`A000000180532`, `A000000163378`, `A000000174064`)다. 6개는 DOM/Flight 대조 실패로 parser 실행 전에 중단됐고, `A000000145650`은 안전하게 차단됐지만 `unsupported` 대신 `unmatched`, `A000000258200`은 계층형 문서를 잘못 `ready`로 저장했다.

가장 중요한 production 버그는 `A000000258200`이다. 판매 옵션 6개가 모두 명시적 최상위 header에 연결됐지만, 대괄호 없는 내부 팬 header가 section 경계로 탐지되지 않아 내부 section들이 각 판매 옵션의 성분 블록에 포함되고 `ready`가 됐다. 이번 검증에서는 코드를 수정하지 않았다.

## 상품별 호출·cache 결과

| product_id | product_name | expected | 1차 cache | 1차 재수집 | 이전 version | stale | claim | 1차 queue | 2차 cache | 2차 Playwright | 최종 저장 version |
|---|---|---|---:|---:|---|---:|---:|---|---:|---:|---|
| A000000251851 | [8월올영픽/사우나쿠션] 네이밍 올데이 마스터 쿠션 리필 기획 (+퍼프5개) | ready | N | Y | v1 | Y | Y | failed | N | N | v1 유지 |
| A000000226593 | [모공커버쿠션/여름쿠션] 네이밍 제로 그래비티 커버 업 쿠션 기획(본품+리필) | ready | N | Y | v1 | Y | Y | failed | N | N | v1 유지 |
| A000000171371 | [8월올영픽/공동개발] 네이밍 플러피 파우더 블러쉬 (+아티스트 브러쉬) 20colors | ready | N | Y | 없음 | - | Y | failed | N | N | 없음 |
| A000000180532 | [NEW/올영 1등 아이팔레트] 웨이크메이크 소프트 블러링 아이팔레트(단품/기획) | unsupported | N | Y | 없음 | - | Y | failed | N | N | 없음 |
| A000000150361 | [NEW한정기획] 홀리카홀리카 마이페이브 무드 아이 팔레트 | unsupported | N | Y | 없음 | - | Y | failed | N | N | 없음 |
| A000000258200 | [NEW 런칭/MYU 공동개발] 팁토우 위시 터치 아이 팔레트 6 Colors | unsupported | N | Y | 없음 | - | Y | complete | Y | N | v2 |
| A000000145650 | 투쿨포스쿨 바이로댕 쉐이딩 | unsupported | N | Y | 없음 | - | Y | failed | N | N | 없음 |
| A000000163378 | [얇은커버쿠션] 정샘물 스킨 누더 커버레이어 쿠션 (본품+리필) | unmatched | N | Y | 없음 | - | Y | failed | N | N | 없음 |
| A000000177984 | [마블컬렉션] 헤라 센슈얼 누드 글로스 5g 13 Colors 기획/단품 | unmatched | N | Y | 없음 | - | Y | failed | N | N | 없음 |
| A000000120656 | 투쿨포스쿨 프로타주 펜슬 (기획/단품) | unmatched | N | Y | 없음 | - | Y | failed | N | N | 없음 |
| A000000174064 | [1등 글로우 파데/웨딩피치] 에스쁘아 비글로우 파운데이션 30g 10 colors | ready 또는 unmatched + orphan | N | Y | 없음 | - | Y | complete | Y | N | v2 |

`A000000251851`과 `A000000226593`의 v1 cache는 cache hit로 사용되지 않았고 실제 재수집이 시도됐으므로 version 무효화 자체는 정상이다. 다만 재수집이 DOM/Flight mismatch로 실패해 기존 v1 row는 그대로 남았다.

## parser 결과

`-`는 parser 이전 수집 실패라 계산하지 않은 값이다. 문서 유형은 연구상 기대 유형이며, `A000000258200`은 production에서 사실상 `option_full_sections`로 오분류됐다.

| product_id | document format | raw/canonical | headers valid/total | matched | unmatched | orphan | ambiguous | malformed | unsupported | internal/public | 예상 일치 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| A000000251851 | option_full_sections | - | - | - | - | - | - | - | - | extraction_failed / unavailable | N |
| A000000226593 | option_full_sections | - | - | - | - | - | - | - | - | extraction_failed / unavailable | N |
| A000000171371 | option_full_sections | - | - | - | - | - | - | - | - | extraction_failed / unavailable | N |
| A000000180532 | hierarchical_option_internal_sections | 13/12 | 210/210 | 0 | 3 | 201 | 0 | 0 | 9 | unsupported / unavailable | Y |
| A000000150361 | hierarchical_option_internal_sections | - | - | - | - | - | - | - | - | extraction_failed / unavailable | N |
| A000000258200 | hierarchical_option_internal_sections → 잘못 ready | 6/6 | 6/6 | 6 | 0 | 0 | 0 | 0 | 0 | ready / ready | N |
| A000000145650 | hierarchical_option_internal_sections | 7/4 | 12/12 | 0 | 4 | 12 | 0 | 0 | 0 | unmatched / unavailable | N |
| A000000163378 | option_full_sections | 5/5 | 4/4 | 3 | 2 | 1 | 0 | 0 | 0 | unmatched / unavailable | Y |
| A000000177984 | option_full_sections | - | - | - | - | - | - | - | - | extraction_failed / unavailable | N |
| A000000120656 | option_full_sections | - | - | - | - | - | - | - | - | extraction_failed / unavailable | N |
| A000000174064 | option_full_sections | 10/10 | 14/14 | 10 | 0 | 4 | 0 | 0 | 0 | ready / ready | Y |

## 진단 상세

### Parser까지 도달한 상품

- `A000000180532`: unmatched는 `]30 클래시 누드 블러링`, `21 폴 인 피그 블러링`, `22 멜로우 어텀 블러링`. 9개 최상위 header는 다음 내부 header 직전까지 유효 성분이 없어 `invalid_ingredient_section`으로 unsupported 처리됐다. orphan header는 201개이며 내부 색상/제형 header들이다. 내부 section 합집합은 수행되지 않았고 ready cache도 생성되지 않았다.
- `A000000258200`: 6개 모두 `explicit_bracketed_exact`, 성분 수는 각 61/51/51/62/51/51개로 처리됐다. 내부 header가 경계로 탐지되지 않은 false-ready이며 orphan·unsupported 진단도 생성되지 않았다.
- `A000000145650`: unmatched는 `3 쿨 토프`, `2 모던`, `1.5 뉴트럴`, `1 클래식`. `[왼쪽]`, `[중앙]`/`[가운데]`, `[오른쪽]` 계열 12개가 orphan이 됐다. 최상위 shade header를 인식하지 못해 계층형 unsupported가 아니라 unmatched로 분류됐다.
- `A000000163378`: matched 3개는 `explicit_star_colon_exact`; unmatched는 `엔라이트`, `미디엄 딥`. orphan은 `★ N라이트 :` 1개다. unmatched 옵션의 ingredients는 비어 있다.
- `A000000174064`: 10개 모두 `explicit_bracketed_exact`, 각 48개 성분으로 matched. orphan은 `[기존 21호 아이보리]`, `[기획증정 - 스틱파데 20호]`, `[기획증정 - 스틱파데 21호]`, `[기획증정 - 스틱파데 22호]`이며 ready가 허용됐다.

실상품에서 ambiguous와 malformed header는 발생하지 않았다. sanitized fixture의 alias collision은 두 후보 모두 ambiguous로 차단하며 첫 후보를 선택하지 않고, malformed header도 unmatched 진단으로 차단하는 기존 테스트를 통과했다.

### Parser 이전 수집 실패

`A000000251851`, `A000000226593`, `A000000171371`, `A000000150361`, `A000000177984`, `A000000120656`은 모두 옵션 DOM 수집과 Flight 파싱 자체 이후 `option_dom_flight_mismatch`에서 중단됐다. 이는 `flight_parse_failed`나 parser unsupported/unmatched와 구분해 기록했으며 ingredient parser는 실행되지 않았다. OliveYoung 검증 페이지, browser launch, ingredient disclosure 실패는 이번 실행에서 관찰되지 않았다.

## 2차 호출과 공개 API

- 새 v2 ready cache가 저장된 `A000000258200`, `A000000174064`만 2차에 cache hit했고 Playwright 없이 동일 ready 결과를 반환했다.
- 나머지 9개는 실패 진단을 ready cache에 저장하지 않는다. 즉시 2차 호출은 cache reuse가 아니라 queue retry gate의 HTTP 409 `PRODUCT_COLLECTION_RETRY_LATER`였고 Playwright는 실행되지 않았다. 따라서 “1차와 동일한 실패 진단 재사용” 요구는 현재 저장 정책으로 충족되지 않는다.
- 1차 차단 응답은 HTTP 200의 공개 `option_status=unavailable`, ready는 `option_status=ready`였다. 2차 retry 응답도 일반화된 오류이며 selector, Flight mismatch 상세, raw header, 전성분 원문은 사용자 API에 노출되지 않았다.
- production extractor에는 `_collect_review_options` 경로가 없었고, 검증 중 리뷰 옵션 fallback 호출은 0회였다.

## 안전성 확인

- 원문 위치 경계로 재검증한 8개 연구 artifact 모두 matched block 안의 orphan raw header 포함 0건이었다. 동일 처방끼리 ingredient set이 같다는 사실은 누출 증거로 사용하지 않았다.
- 모든 unmatched·ambiguous·unsupported section의 `ingredients`는 빈 배열이었다. 다른 옵션 성분 복사나 공통 formula 자동 복제는 없었다.
- `A000000180532`은 계층형 내부 section을 합치지 않고 차단됐다. 반면 `A000000258200`은 내부 header 미탐지로 false-ready이므로 이 안전 조건을 충족하지 못한다.
- `A000000145650`은 ready가 되지 않아 분석은 차단됐지만, 기대했던 계층형 unsupported 진단은 만들지 못했다.

## 오프라인 테스트

다음 10개 test module을 함께 실행했다: header-first, canonicalization/실상품 fixture, option service, parser-version cache, ingredient cache/repository, selection public status, analysis endpoint, queue/stale lease, ingredient resolution.

```text
105 passed, 1 warning in 2.58s
```

경고는 FastAPI TestClient의 `httpx` 사용에 대한 Starlette deprecation warning이며 테스트 실패는 아니다.

## Production 수정이 필요한 버그

1. **Critical — `A000000258200` false-ready:** 명시적이지 않은 내부 팬 header가 section boundary에서 빠져 계층형 문서가 평면 전체 성분 section으로 승인된다.
2. **High — DOM/Flight mismatch 회귀:** 대표 상품 6개가 parser 전에 차단돼 기존 ready 3개를 실제 parser로 회귀 검증할 수 없다. count/name/sold-out 대조의 어느 필드가 불일치했는지 별도 extractor 진단이 필요하다.
3. **Medium — 계층형 상태 오진단:** `A000000145650`은 안전하게 blocked지만 top-level shade header 미탐지로 unsupported가 아닌 unmatched가 된다.
4. **Medium — 실패 결과 2차 재사용 불가:** 실패 진단이 cache되지 않아 즉시 2차 요청은 동일 진단 대신 retry-later만 반환한다.
5. **Low — stale row 잔존:** v1 cache는 정상적으로 무시되지만 재수집 실패 시 DB row의 parser version은 v1로 남는다.

## 이번 단계에서 구현하지 않을 항목

계층형 section 병합/합집합, 공통 formula 복제, fuzzy matching, alias·오탈자 보정, parser 문법 확장, 리뷰 옵션 fallback, DB/API schema 변경은 모두 미실시 상태를 유지한다.
