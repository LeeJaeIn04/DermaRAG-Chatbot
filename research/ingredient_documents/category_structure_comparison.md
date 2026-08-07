# 전성분 문서 구조 비교 조사

조사 기준은 상품 상세 페이지의 production 상품 옵션 선택 창과 상품정보 제공고시다. 리뷰 옵션은 사용하지 않았다. 신규 3개 상품은 옵션과 전성분을 동일 browser/context/page에서 각 1회 수집했고, 기존 artifact 5개는 재호출하지 않았다. Production parser·DB schema·cache 판정은 변경하지 않았다.

기존 artifact가 상품명을 저장하지 않은 A000000150361, A000000258200, A000000145650, A000000163378은 호출 제한을 지키기 위해 `product_name=null`을 유지했다. 신규 상품명은 페이지 `og:title`에서 수집했다.

## 표본 비교

| product_id | category | sale options | canonical options | top-level headers | internal headers | document format | mapping relation | unmatched sale options | orphan sections |
|---|---|---:|---:|---:|---:|---|---|---:|---:|
| A000000180532 | 아이섀도 팔레트 | 13 | 12 | 12 | 198 | `hierarchical_option_internal_sections` | many-sale→one + one→many | 1 | 1 |
| A000000150361 | 아이섀도 팔레트 | 19 | 15 | 17 | 144¹ | `hierarchical_option_internal_sections` | many-sale→one + one→many | 1² | 2 |
| A000000258200 | 아이섀도 팔레트 | 6 | 6 | 6 | 36 | `hierarchical_option_internal_sections` | one→many | 0 | 0 |
| A000000145650 | 쉐딩·컨투어 | 7 | 4 | 4 | 12 | `hierarchical_option_internal_sections` | many-sale→one + one→many | 0 | 0 |
| A000000163378 | 쿠션 | 5 | 5 | 4 | 0 | `option_full_sections` | one→one + needs-review | 2² | 0 |
| A000000174064 | 파운데이션 | 10 | 10 | 14 | 0 | `option_full_sections` + `component_sections` | one→one | 0 | 4 |
| A000000177984 | 립 | 20 | 17 | 6 | 0 | `option_full_sections` | one→one + many-sale→one | 11 | 0 |
| A000000120656 | 단색 아이섀도우 | 20 | 15 | 9 | 0 | `option_full_sections` | one→one + many-sale→one | 8 | 2 |

¹ 출시 세대별 무구분자 문법이 섞여 있어 144개 중 일부는 수동 검토 대상이다. ² `유자↔유즈` probable 표기 차이다. 쿠션의 unmatched 2개는 `엔라이트↔N라이트` probable match와 `미디엄 딥` 부재를 합산했다. 모든 원문은 줄바꿈이 0개여서 line 기반 분리는 유효하지 않았다.

## 팔레트 3개 비교

### A000000180532

- 대괄호 최상위 팔레트 header 12개 아래 대괄호 내부 색상 header가 각각 16~19개 있다.
- 현재 canonical 12개 중 11개가 연결된다. 현재 30호는 header가 없고, 현재 판매에 없는 25호 section이 있다.
- 단품·기획 21호는 하나의 canonical header를 공유한다. `[펄]`은 문법상 bracketed이나 의미는 formula type 또는 내부 팬 후보라 확정하지 않았다.

### A000000150361

- 판매 19개는 package/promotion token 제거 시 15개 canonical 후보로 수렴한다. 폴인오트·유자 시트러스 티·시나몬 롤·11 레터프롬스프링은 단품/기획이 같은 상위 identity를 공유한다.
- 상위 17개에는 현재 canonical 후보에 대응하는 15개 후보와 문서 전용 `04 앙버터`, `09 타로리더`가 있다. `유자 시트러스 티↔유즈 시트러스 티`는 probable 표기라 exact로 확정하지 않았다. 각 팔레트는 9개 내부 section 후보를 갖지만 일부 경계는 low-confidence다.
- 실제 내부 문법은 `1.`, `01이름:`, `[01 이름]`, `1) 이름:`, 영문명, `#영문명`, `이름:`이다. `Cream Shine`, `Yeast`, `Glaze`는 팬 이름인지 제형인지 확정하지 않았다.
- DOM과 Flight는 같은 19개 이름·품절 상태를 제공했지만 순서가 달라 production은 `option_dom_flight_mismatch`로 차단했다. 연구 artifact는 동일 페이지의 유일 정규화 이름 대조만 사용했다.

### A000000258200

- 판매 옵션 6개와 대괄호 최상위 팔레트명 6개가 연결되지만 판매명의 `00`~`05` 번호는 header에서 생략된다.
- 각 팔레트 아래 한글+영문 팬 이름 6개가 대괄호·콜론·줄바꿈 없이 이어진다. 독립 매트·쉬머·글리터·펄 header는 발견되지 않았다.
- 새턴/머큐리, 주피터/플루토는 각각 내부 이름과 본문 hash가 같아 서로 다른 판매 옵션이 동일 문서를 공유할 가능성이 있다.

세 팔레트 모두 “최상위 판매/canonical 옵션 → 여러 내부 색상 또는 제형 후보” 구조를 보인다. 다만 내부 문법은 bracketed, heterogeneous, delimiterless bilingual로 서로 다르므로 평면 header-first parser로는 부족하다.

## 다색 팬: 쉐딩과 팔레트

- A000000145650은 `1호 클래식`, `2호 모던`, `1.5호 뉴트럴`, `3호 쿨토프` 아래 `[왼쪽]`, `[중앙/가운데]`, `[오른쪽]` 3개 section을 둔다.
- 판매 7개는 포장/기획 제거 시 shade 4개로 수렴한다. 각 shade 내부 세 팬은 성분 집합은 같고 순서가 달라 팬별 전체 목록 반복으로 관찰했으며 공통 베이스 문법으로 확정하지 않았다.
- 팔레트와 쉐딩 모두 계층형 parser가 필요하다. `multi_internal_color_group`은 내부가 실제 색상인지 제형인지 불명확한 표본을 과도하게 확정하므로, 상위 구조명은 `hierarchical_option_internal_sections`가 더 정확하다.

## 베이스 메이크업

### 쿠션 A000000163378

- 판매 5개는 모두 `[본품+리필]`이며 숫자/영숫자 shade code가 없다. 문서는 `★ 페어라이트 :`, `★ N라이트 :`, `★ 라이트 :`, `★ 미디엄 :` 4개 전체 formula section이다.
- `엔라이트↔N라이트`는 probable match라 exact로 확정하지 않았고 `미디엄 딥` section은 없다. 네 section의 성분 집합은 같고 순서는 다르다.

### 파운데이션 A000000174064

- 실제 상품명은 “[1등 글로우 파데/웨딩피치] 에스쁘아 비글로우 파운데이션 30g 10 colors”이며 판매 10개는 모두 판매 중이다.
- `[3C 웨딩피치]`, `[13N 뉴트럴포슬린]`, `[20C 쿨바닐라]` 등 N/C undertone code를 보존한 대괄호 header가 10개 판매 shade와 1:1 연결된다.
- 현재 10개는 각각 전체 formula를 반복하며 성분 집합은 같고 순서는 다르다. `공통성분`, `전 색상 공통`, `색상에 따라 포함 가능`, `May contain`, `±` 문법은 발견되지 않았다.
- `[기존 21호 아이보리]`와 기획증정 스틱파데 20/21/22호 4개는 현재 판매 option이 아닌 별도 component/orphan section이다.

## 색조 단일 옵션형

### 립 A000000177984

- 실제 상품명은 “[마블컬렉션] 헤라 센슈얼 누드 글로스 5g 13 Colors 기획/단품”이다. 판매 20개(판매 18, 일시품절 2)는 색상명 기준 17 canonical 후보로 수렴한다.
- 실제 header는 `[란제리]`, `[스피치리스]`, `[플러티]`, `[체리쉬]`, `[이노센트]`와 괄호가 잘못 닫힌 `[누디스트)`뿐이다. 번호, 영문 alias, `#COLOR` header는 발견되지 않았다.
- 문서 6개는 색상별 전체 formula다. 현재 canonical 11개는 section이 없으며, 란제리처럼 단품/기획 판매 구성이 하나의 색상명 header를 공유한다.

### 단색 아이섀도우 A000000120656

- 실제 상품명은 “투쿨포스쿨 프로타주 펜슬 (기획/단품)”이다. 판매 20개(판매 14, 일시품절 6)는 package 제거 시 15 canonical shade다.
- 실제 header는 `[1호]`, `[2호]`, `[7호]`~`[13호]`의 숫자+호 문법뿐이다. 색상명·영문명·매트/쉬머/글리터 제형 header는 발견되지 않았다.
- 현재 shade 중 1·2·7·8·9·10·11호만 1:1 연결되고, 14·15·16·18·19·20·21·22는 section이 없다. 현재 판매에 없는 12·13호 section이 남아 있다.

## Parser 우선순위와 needs_review

1. 우선 지원: 명시적 대괄호/콜론 기반 `option_full_sections`, 그다음 package token을 제외한 many-sale→one canonical mapping.
2. 다음 지원: 최상위 option header와 내부 section을 별도로 유지하는 `hierarchical_option_internal_sections`. 내부 역할은 색상/제형/구성품 후보와 confidence를 보존해야 한다.
3. 후순위: 무구분자 한·영 팬 이름과 세대별 혼합 문법. orphan section, malformed bracket, probable identity, 동일 본문 공유는 자동 확정하지 않는다.

모든 표본은 현재 판매 option 부재를 판매 종료로 추정하지 않았고, 내부 header 의미가 불명확하면 `unknown_internal_header`/후보 역할과 `needs_review`를 유지했다.

## 연구 artifact와 fixture 후보

- 상품별 JSON에는 원문, hash, 옵션 원형, 공통 수집 필드, 현재 평면 parser 결과, A/B/C 집합, 계층 header 역할 및 confidence를 저장했다.
- `sanitized_fixture_candidates.json`에는 최소 option row와 header 기대값만 저장했다. 전체 HTML·쿠키·storage state·전체 전성분 원문은 포함하지 않았다.
