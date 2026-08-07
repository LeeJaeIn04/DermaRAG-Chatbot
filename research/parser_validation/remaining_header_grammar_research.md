# Remaining header grammar research

- 조사일: 2026-08-05 (Asia/Seoul)
- 범위: v3 unmatched 4개 상품의 연구 진단
- production parser·API·DB schema·parser version 변경 없음
- 전체 HTML, 전체 원문, Flight payload, 쿠키, storage state 저장 없음

구조화 결과는 [remaining_header_grammar_research.json](./remaining_header_grammar_research.json), 최소 fixture는 [research_remaining_header_grammars.json](../../scripts/fixtures/research_remaining_header_grammars.json)에 있다.

## 결론

| product_id | 실제/후보 grammar | section | exact 추가 가능 | 적용 후 unmatched | 정책 |
|---|---|---:|---:|---:|---|
| A000000171371 | `hash_english_alias` 후보 | 재검증 실패 | 0 확정 | 22 | research_only |
| A000000241210 | 상품명 prefix + 반복 full numeric/color label | 36 | 34 | 4 | production_candidate |
| A000000197231 | 반복 full numeric/color label | 17 | 16 | 2 | production_candidate |
| A000000177984 | single mismatched bracket | 6 중 1 malformed | 0 | 14 | research_only |

향후 v4 production 후보는 `repeated_unbracketed_full_option_label` 하나다. 두 롬앤 문서에서 50개 옵션을 exact로 추가 매칭할 수 있지만, 남은 42개는 그대로 차단해야 한다. 네 상품 중 모든 canonical 옵션이 매칭되는 상품은 없어 ready 전환은 0개다.

## A000000171371 — 네이밍 블러쉬

기존 v3 결과의 `#영문별칭` 관찰 후보를 재검증하려 했으나 올리브영 브라우저 검증 화면에서 중단됐다. 우회하지 않았고 실패 진단기가 만든 HTML·스크린샷은 즉시 삭제했다. 따라서 `#HALO`, `#BAGEL`, `#FEEG`, `#BASHFUL`의 실제 존재·대소문자·경계·body는 이번 산출물에서 확정하지 않는다.

판매 옵션 22개에는 괄호 영문 alias 22개가 있지만 identity는 20개뿐이다. `BAGEL`과 `PILLOW`가 각각 두 canonical 옵션에 중복되므로, alias exact만으로 전체를 안전하게 연결할 수 없다. 원문에 모든 hash section이 있다고 가정해도 현재 canonicalization 기준 최대 18개만 유일하고 4개는 ambiguous다.

따라서 `hash_english_alias`는 research_only다. 원문 반복성, 문서 내 hash 유일성, ingredient body, 마케팅 hashtag 충돌이 새 artifact에서 확인되기 전에는 production 후보가 아니다. 허용 문자도 현재 증거로 확정하지 않는다.

## A000000241210 — 롬앤 더 쥬시 래스팅 틴트

공통 formula가 아니라 옵션별 full formula가 반복된다. raw length 25,174, 줄바꿈 0, comma 1,847이며 문서 section은 36개다. 시작은 `상품명 + 용량 + 01 포멜로스킨 + ingredient body`이고 이후에도 안정적인 상품명/label prefix 뒤에 다음 body가 이어진다.

현재 38개 canonical 옵션 중 34개가 full label exact다. 문서의 `12 애플브라운`, `36 키튼리치`는 현재 판매 옵션에 없는 orphan이고, 현재 판매 중인 39~42번 4개는 문서 section이 없어 unmatched로 남는다. section 수와 identity는 live 관찰과 기존 v1 option별 cache 36개를 교차 확인했다.

숫자만 탐지하면 CI 번호·색소 호수와 대량 충돌한다. 안전 후보는 숫자가 아니라 `상품명 prefix + full option label` 전체이며, prefix 시작을 경계에 포함해 다음 section의 상품명이 이전 ingredient에 섞이지 않게 해야 한다.

## A000000197231 — 롬앤 글래스팅 컬러 글로스

raw length 3,206, 줄바꿈 0이며 17개 full formula section이 있다. 틴트와 같은 `repeated_unbracketed_full_option_label` 계열이지만 상품명 prefix 없이 `01 피오니 발레 + body`가 곧바로 반복된다.

18개 canonical 옵션 중 16개는 공백 정규화만으로 exact 연결된다. `14 뮤이지`는 문서 section이 없고, 판매 옵션 `20 클라우드민트`와 문서 `20 클라우디 민트`는 exact identity가 달라 각각 unmatched/orphan이다. 이를 자동 수정하거나 번호 20만으로 연결하지 않는다.

따라서 두 롬앤 문법은 일부만 동일하다. 공통 semantic role은 canonical option header이고 공통 boundary는 full label 끝부터 다음 header 시작이지만, 틴트에만 안정적인 상품명 prefix가 있다.

## A000000177984 — 헤라 센슈얼 누드 글로스

기존 연구 artifact의 원문에는 `[누디스트)`가 실제로 존재한다. extractor는 DOM `inner_text()`에 `strip()`만 적용하므로 괄호를 치환하는 정규화 경로가 없다. 같은 문서의 다른 malformed bracket은 0개다.

이 후보는 span 626~632, 다음 정상 `[플러티]`는 924에서 시작하며 사이 body는 290자·comma 25개다. `401 누디스트` canonical identity도 하나뿐이므로 이 문서에서는 `safe_single_bracket_repair_candidate`다. 다만 단일 오탈자 표본만으로 일반 bracket 자동 보정을 허용하지 않아 research_only로 유지한다.

## 규칙 분류

Production candidate:

- `repeated_unbracketed_full_option_label`: 숫자+색상명 full canonical label exact, 문서/옵션 양쪽 유일, 반복 section 2개 이상, 각 body 유효, fuzzy 없음.
- 반복 상품명 prefix가 있으면 prefix까지 header로 취급하고 모든 후보를 계층형 structure guard에 먼저 전달한다.

Research only:

- `hash_english_alias`: 원문 재확인 실패와 BAGEL/PILLOW alias 중복 때문에 보류.
- `single_mismatched_bracket_repair`: 헤라 한 표본에서는 안전 후보지만 일반화 증거 부족.

Reject:

- 숫자 단독, 번호만 fallback, 한국어/영어 의미 유사도, fuzzy color match, `클라우드↔클라우디` 자동 보정, 일반 bracket 자동 복구, 공통 formula 복제.

## v3 회귀 및 계층형 위험

Pure-English hash를 기존 `#영숫자코드`와 별도 grammar로 유지하고 판매 옵션의 실제 괄호 alias와 exact 비교하면 ready 3개와의 직접 충돌 위험은 낮다. 하지만 마케팅 hashtag 확인 전에는 추가하지 않는다. 숫자-only는 성분의 CI·색소 번호를 header로 오인하므로 위험이 높아 reject다.

Full-label exact 규칙 자체의 ready 회귀 위험은 낮지만, 계층형 4개 상품에서는 새 unbracketed 후보가 top-level/internal 구조 판정보다 먼저 flat mapping되면 false-ready가 재발할 수 있다. v4는 모든 신규 후보를 header inventory에 넣고 `hierarchical_option_internal_sections` 차단을 먼저 수행해야 한다.

## Fixture와 검증

연구 fixture는 네 문법 사례만 축약해 저장했고 전체 원문을 포함하지 않는다. 오프라인 프로토타입은 candidate/header span, following body span, exact option 후보, duplicate count, mapping status와 reason을 출력한다. fuzzy·편집 거리·의미 유사도는 사용하지 않는다.

네이밍 원문은 browser verification 때문에 미확정이다. 다음 단계는 해당 원문이 합법적으로 다시 수집 가능한 시점에 hash 문자·유일성·경계를 별도 artifact로 확정한 뒤, 우선 롬앤용 full-label exact 규칙만 v4에 구현하는 것이다.
