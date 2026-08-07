# v4 repeated unbracketed full option label

- parser version: `option-sections-v4-unbracketed-full-label`
- 새 grammar: `repeated_unbracketed_full_option_label`
- variants: `full_label_direct`, `product_prefix_plus_full_label`
- mapping rule: `explicit_full_option_label_exact`
- API·DB schema 변경 없음

## 구현

새 비교 함수는 NFKC, casefold, 공백 차이만 정규화한다. 기획 문구, `호`, 기호, 숫자나 색상명 일부를 제거하지 않는다. `01포멜로스킨`과 `01 포멜로스킨`은 같지만, `[기획] 01 포멜로스킨`은 같지 않다.

직접 label variant는 문서 처음부터 반복되는 2자리 숫자+한글 full label만 허용한다. prefix variant는 연구에서 확인된 `롬앤 더 쥬시 래스팅 틴트`와 첫 section의 `3.5g` 조합만 exact로 허용한다. 임의 prefix 제거는 없다.

기존 structure guard와 명시적 header 판정을 먼저 수행하고, valid explicit header가 없는 flat 문서에서만 새 grammar를 시도한다. 후보 3개 이상, exact option 후보 2개 이상, 숫자 순서, 동일 variant, body 20자·성분 3개 이상, 모든 section의 동일 첫 base 원료를 요구한다. 다음 header 시작을 현재 body 끝으로 사용한다.

중복 full label은 ambiguous, 현재 옵션과 exact identity가 없는 label은 orphan, header가 없는 현재 옵션은 unmatched다. 일부만 매칭돼도 `ProductOptionService`는 ready state와 option ingredient entry를 저장하지 않는다.

## 목표 상품

| product_id | 검증 | matched | unmatched | orphan | ready | analyze |
|---|---|---:|---:|---:|---:|---:|
| A000000241210 | real-count sanitized fixture; live backoff 준수 | 34 | 4 | 2 | N | 400 |
| A000000197231 | production headed live | 16 | 2 | 1 | N | 400 |

`A197231`의 unmatched는 `14 뮤이지`, `20 클라우드민트`이며 문서의 `20 클라우디 민트`는 orphan이다. `A241210`은 active retry/backoff를 우회하지 않아 live 재수집하지 않았고, 연구상 현재 header가 없는 39~42번 4개를 unmatched로 고정한 최소 fixture로 검증했다. 새 ready 상품은 0개다.

## Cache와 회귀

v3 ready cache는 v4에서 stale로 판정하고, option 없는 `not_applicable` 공통 cache는 유지한다. 실제 `A251851` 5개와 `A226593` 7개 옵션은 v4로 재검증되어 ready가 됐고, 재호출은 브라우저 없이 cache hit HTTP 200이었다.

`A174064`는 기존 sanitized 실문서에서 10 matched + 4 orphan으로 ready를 유지한다. live 재검증은 브라우저 검증 화면에서 중단돼 v4 cache를 만들지 않았고 stale v3 key는 analyze HTTP 400으로 차단됐다.

계층형 `A180532`, `A258200`, `A145650`은 기존 실문서 artifact에서 각각 12/6/4개 전부 unsupported이며 false-ready가 없다. 실제 A258200 v2 key도 analyze HTTP 400으로 차단됐다.

## 테스트와 제한

새 production fixture는 prefix/direct, 공백 비교, 부분·숫자·색상 단독 금지, 중복, 빈 body, body 중간 언급, orphan, missing option, 계층형 우선, malformed/hash 미지원과 34/4·16/2 분포를 검증한다. service/cache 테스트는 partial 저장 차단, v2/v3 stale 차단, v4 재사용, 공통 cache 유지도 확인한다.

관련 parser/service/cache 테스트는 56개, 외부 브라우저 테스트를 제외한 전체 suite는 225개가 통과했다. 전체 실행에서는 sandbox가 headed Chrome 실행을 막은 기존 외부 통합 테스트 1개만 실패했고 나머지 226개는 통과했다. 이후 승인된 live 검증에서는 브라우저 검증 화면이 나타나 더 진행하지 않았고, 자동 생성된 HTML·스크린샷은 삭제했다.

`hash_english_alias`, malformed bracket repair, numeric-only, fuzzy/edit-distance, 공통 formula 복제, 계층형 section 병합은 추가하지 않았다. 남은 unmatched는 실제 문서 header 부재 또는 full identity 불일치다.
