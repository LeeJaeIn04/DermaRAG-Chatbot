# 상품 데이터 수집·옵션 파싱 파이프라인 개선 및 안정화

## 1. 개선 배경

DermaRAG는 올리브영 상품을 검색하고, 사용자가 선택한 상품의 옵션별 전성분을 수집하여 분석에 활용합니다.

초기 구현에서는 Playwright를 사용해 상품 상세 페이지에 접근하고 전성분을 수집할 수 있었지만, 실제 다양한 상품을 처리하면서 다음과 같은 한계가 확인되었습니다.

- Playwright 수집 로직과 전성분 해석 로직이 강하게 결합되어 있었음
- 하나의 상품에 여러 옵션이 존재할 때 옵션별 전성분을 안정적으로 구분하기 어려웠음
- 기획세트의 `[본품]`, `[리필]`, `[증정]` 등이 성분명으로 오인되거나 반대로 정보가 유실될 수 있었음
- 상품 설명, 이벤트 안내, 주의 문구 등이 전성분에 섞이는 오탐 가능성이 있었음
- 일부 옵션만 실패해도 상품 전체를 활용하기 어려웠음
- 상품 단위 cache만으로는 옵션별 성공·실패와 partial success를 표현하기 어려웠음
- production parser와 새로운 parser의 결과를 안전하게 비교하고 전환할 기준이 없었음
- parser, cache, API, Frontend가 서로 다른 상태 판단 기준을 사용할 가능성이 있었음
- 배포 환경에서 Playwright 실행 방식도 별도로 검증할 필요가 있었음

따라서 단순히 scraper의 selector를 추가하는 수준이 아니라, **수집 → 정규화 → 옵션/전성분 파싱 → 상태 모델 → cache → API → Frontend → production 전환**까지 전체 데이터 수집 파이프라인을 단계적으로 재설계했습니다.

---

## 2. 전체 개선 구조

최종적으로 상품 데이터 수집 흐름을 다음과 같이 분리했습니다.

```text
상품 검색 / 선택
        ↓
Playwright
- 상품 페이지 렌더링
- 옵션 원본 데이터 수집
- 전성분 관련 원본 데이터 수집
        ↓
Normalization
        ↓
Option Parser
        ↓
Ingredient Parser
        ↓
ParserResult
- option status
- collection status
        ↓
Production / Shadow Parser 비교
        ↓
Safe Selector
        ↓
Effective Parser Result
        ↓
┌───────────────────────┐
│ Option-level SQLite   │
│ Cache                 │
└───────────────────────┘
        ↓
       API
        ↓
    Frontend
- ready 옵션만 분석 가능
```

핵심 원칙은 다음과 같습니다.

> Playwright는 페이지 렌더링과 원본 데이터 수집에 집중하고, 실제 데이터 해석과 상태 판단은 독립적인 parser와 service 계층에서 처리한다.

---

## 3. Playwright 수집과 Parsing 책임 분리

### 기존 문제

기존에는 Playwright가 다음 역할을 한 흐름 안에서 함께 담당했습니다.

- 상품 페이지 접근
- 옵션 선택
- DOM 데이터 수집
- 전성분 영역 판단
- 전성분 문자열 분리

이 구조에서는 페이지 접근 오류와 parsing 오류를 구분하기 어려웠고, 전성분 분리 규칙을 테스트하려면 실제 브라우저를 반복 실행해야 했습니다.

### 개선

처리 단계를 다음과 같이 분리했습니다.

```text
1. Playwright가 상품 페이지를 렌더링한다.
2. 옵션과 전성분 관련 원본 데이터를 수집한다.
3. 수집한 텍스트를 정규화한다.
4. Option Parser가 옵션별 영역을 분리한다.
5. Ingredient Parser가 구성품별 전성분을 추출한다.
6. 구조화된 ParserResult를 생성한다.
7. 필요한 결과를 SQLite에 저장한다.
```

### 개선 효과

- 브라우저를 실행하지 않고 parser만 독립적으로 테스트 가능
- 페이지 수집 실패와 텍스트 해석 실패를 분리하여 진단 가능
- 페이지 구조 변경 시 수정 범위를 줄일 수 있음
- 저장된 원본 데이터가 있다면 Playwright를 재실행하지 않고 parser만 재검증할 수 있는 구조 확보
- 옵션 및 전성분 처리 규칙을 독립적으로 개선 가능

---

## 4. 옵션·구성품 단위 데이터 구조

상품 단위 전성분 하나만으로는 실제 상품 구성을 정확하게 표현할 수 없습니다.

예를 들어 하나의 상품에 여러 색상 옵션이 있거나, 하나의 옵션 안에 본품과 리필이 함께 포함될 수 있습니다.

```text
상품
└─ 옵션
   ├─ 구성품: 본품
   │  └─ 전성분
   ├─ 구성품: 리필
   │  └─ 전성분
   └─ 구성품: 증정
      └─ 전성분
```

따라서 데이터를 다음 단위로 구조화했습니다.

- 상품
- 옵션
- 구성품 그룹
- 구성품별 전성분
- annotation 후보
- 옵션별 처리 상태
- 상품 전체 collection 상태

### 구성품 그룹 보존

`[본품]`, `[리필]`, `[증정]` 같은 텍스트를 단순 삭제하지 않고 성분 목록에서는 제외하되 별도의 구성품 정보로 보존합니다.

```json
{
  "option_name": "기획세트",
  "components": [
    {
      "group_name": "본품",
      "ingredients": [
        "정제수",
        "글리세린",
        "판테놀"
      ]
    },
    {
      "group_name": "리필",
      "ingredients": [
        "정제수",
        "부틸렌글라이콜",
        "세라마이드엔피"
      ]
    }
  ]
}
```

이를 통해 본품, 리필, 증정품의 전성분을 서로 섞지 않고 독립적으로 저장·분석할 수 있게 했습니다.

---

## 5. 전성분 영역 판별과 오탐 감소

### 문제

상품 상세 페이지에는 전성분 외에도 쉼표로 구분된 다양한 문구가 존재합니다.

```text
미백, 주름개선
```

```text
본품, 리필
```

단순히 쉼표가 포함되어 있다는 이유로 전성분으로 판단하면 설명 문구가 성분 데이터에 포함될 수 있습니다.

### 최소 성분 개수 검증

하나의 후보 영역에서 **최소 4개 이상의 성분이 인식될 때** 실제 전성분 영역으로 판단하는 휴리스틱을 적용했습니다.

```text
정제수, 글리세린, 부틸렌글라이콜, 나이아신아마이드, 판테놀
```

반면 다음과 같은 짧은 문구는 바로 전성분으로 확정하지 않습니다.

```text
미백, 주름개선
```

이 기준은 모든 상품에 절대적으로 적용되는 규칙이 아니라, 현재까지 확인한 실제 상품 데이터에서 오탐을 줄이기 위해 적용한 휴리스틱입니다.

---

## 6. 안내 문구와 애매한 텍스트 보존

전성분 뒤에는 다음과 같은 안내 문구가 붙을 수 있습니다.

```text
리뉴얼 전후 상품이 혼재되어 출고될 수 있습니다.
```

```text
증정품은 재고 상황에 따라 변경될 수 있습니다.
```

이를 성분 목록에 포함하면 분석 데이터가 오염되지만, 바로 삭제하면 원본 정보가 유실됩니다.

따라서 성분으로 확정하기 어려운 후행 문구는 `annotation_candidates`로 분리해 보존합니다.

```json
{
  "ingredients": [
    "정제수",
    "글리세린",
    "판테놀",
    "알란토인"
  ],
  "annotation_candidates": [
    "리뉴얼 전후 상품이 혼재되어 출고될 수 있습니다."
  ]
}
```

이를 통해 성분 분석 데이터의 오염을 줄이면서도 애매한 원본 정보는 추후 parser 개선에 활용할 수 있도록 남겼습니다.

---

## 7. 실패 원인 진단 강화

parser 동작을 바로 변경하기 전에 먼저 **왜 실패했는지 관찰할 수 있도록 diagnostics를 보완**했습니다.

주요 진단 대상은 다음과 같습니다.

- 페이지 자체 수집 실패
- 옵션 추출 실패
- 전성분 section 추출 실패
- option ↔ section mapping 실패
- 성분 정규화 실패
- production / shadow parser 결과 차이

핵심 방향은 다음과 같았습니다.

> 파서를 더 공격적으로 수정하기 전에, 어느 단계에서 실패했는지를 먼저 볼 수 있게 만든다.

이 진단 정보는 이후 production parser와 shadow parser를 안전하게 비교하는 기반이 되었습니다.

---

## 8. 옵션 단위 상태 모델 도입

기존에는 parser마다 결과 표현 방식이 달라 옵션 상태를 일관되게 판단하기 어려웠습니다.

이를 해결하기 위해 공통 상태 모델을 도입했습니다.

### Option Status

```text
ready
unmapped
empty
ambiguous
error
```

| 상태 | 의미 |
|---|---|
| `ready` | 옵션과 전성분 section이 정상 연결되고 성분 추출 성공 |
| `unmapped` | 옵션에 대응하는 section을 찾지 못함 |
| `empty` | section은 찾았지만 추출된 성분이 없음 |
| `ambiguous` | 여러 후보 중 하나를 안전하게 확정할 수 없음 |
| `error` | 처리 과정에서 오류 발생 |

### Collection Status

상품 전체에는 다음 상태를 사용합니다.

```text
ready
partial
failed
```

예를 들어:

```text
본품 → ready
리필 → ambiguous
```

이면 상품 전체는:

```text
collection_status = partial
```

입니다.

관련 공통 로직은 다음과 같습니다.

```python
build_option_level_result()
derive_collection_status()
build_parser_result()
select_safe_parser_result()
```

---

## 9. Production / Shadow Parser 안전 비교

새 parser가 더 많은 결과를 냈다고 해서 곧바로 production 결과로 채택하면 기존에 정상적으로 추출되던 데이터를 깨뜨릴 수 있습니다.

이를 방지하기 위해 `select_safe_parser_result()`를 중심으로 safe selector를 도입했습니다.

### Shadow 선택 조건

shadow는 다음 조건을 만족할 때만 선택할 수 있습니다.

- production의 기존 ready 옵션을 모두 유지
- 기존 ready 옵션의 ingredients가 동일
- 같은 실제 옵션의 `option_id`가 양쪽 parser에서 안정적으로 일치
- production보다 추가 ready 옵션을 복구

예:

```text
production
본품 → ready
리필 → unmapped

shadow
본품 → ready
리필 → ready
```

이 경우 shadow를 선택할 수 있습니다.

반면:

```text
production
본품 → [정제수, 글리세린]

shadow
본품 → [정제수, 에탄올]
리필 → ready
```

처럼 기존 정상 결과의 ingredients가 달라지면 production을 유지합니다.

---

## 10. Canonical Option ID 안정화

production과 shadow 결과를 안전하게 비교하려면 같은 실제 옵션이 양쪽 parser에서 같은 identity를 가져야 합니다.

초기에는 parser 흐름별로 option ID가 달라질 가능성이 있었기 때문에, canonical option을 한 번 생성한 뒤 양쪽 parser가 동일한 ID를 사용하도록 정리했습니다.

핵심 원칙은 다음과 같습니다.

```text
옵션 identity는 한 번만 정의한다.
production/shadow가 각각 다시 계산하지 않는다.
```

가능하면 source option id/value를 사용하고, 필요한 경우 원래 옵션 순서를 fallback으로 사용하도록 구성했습니다.

---

## 11. Shadow Observation Mode

safe selector를 만든 뒤 바로 production에 적용하지 않고, 먼저 관찰 모드에서 실제 결과를 비교했습니다.

```text
production result
        ↓
shadow result
        ↓
selector decision
        ↓
로그에서만 관찰
        ↓
실제 API/cache는 production 결과 유지
```

feature flag:

```env
PRODUCT_SHADOW_OBSERVATION_ENABLED=false
```

를 두어 필요한 환경에서만 관찰할 수 있도록 했습니다.

또한 production이 이미 `ready`인 경우 shadow를 실행하지 않도록 제한해 불필요한 parser 실행 비용을 줄였습니다.

### 로그 정책

```text
상품 단위 selector 요약 → INFO
옵션별 상세 비교       → DEBUG
```

전체 ingredients, raw HTML, 옵션 raw 데이터와 같은 대량 정보는 운영 로그에 직접 남기지 않도록 제한했습니다.

---

## 12. Option-level Cache Migration

초기 cache는 사실상 상품 전체 성공 여부를 중심으로 설계되어 있었습니다.

예를 들어:

```text
본품 → ready
리필 → ambiguous
```

처럼 일부 옵션만 성공한 경우에도 본품 데이터는 유효하지만, 상품 전체를 정상 cache로 활용하기 어려웠습니다.

이를 해결하기 위해 SQLite cache를 옵션 단위 상태까지 저장할 수 있도록 확장했습니다.

### Collection-level metadata

```text
collection_status
parser_version
diagnostics
option_count
```

### Option-level metadata

```text
option_status
mapped_section_id
parser_version
diagnostics
```

기존 schema를 제거하지 않고 **additive migration** 방식으로 확장했습니다.

```text
legacy cache
+
new option-level cache
```

를 함께 지원하도록 구성했습니다.

---

## 13. Partial Success 저장

이번 개선의 핵심 중 하나는 **일부 옵션이 실패해도 성공한 옵션을 버리지 않는 것**입니다.

예:

```text
상품 collection_status = partial

본품
status = ready
ingredients = [...]

리필
status = ambiguous
ingredients = 없음

증정품
status = unmapped
ingredients = 없음
```

이 전체 상태를 cache에 저장합니다.

- `ready` 옵션은 실제 ingredients까지 저장
- non-ready 옵션도 삭제하지 않고 상태와 diagnostics 보존

즉:

```text
일부 실패
≠
전체 데이터 폐기
```

가 되도록 변경했습니다.

---

## 14. Cache Completeness 기준 수정

초기 구현에서는 신규 cache가 완전한지 판단할 때 사실상 모든 옵션이 성공해야 하는 것처럼 처리될 가능성이 있었습니다.

하지만 다음 두 개념은 다릅니다.

```text
모든 옵션이 ready
```

```text
cache snapshot이 필요한 상태 정보를 완전하게 기록함
```

예를 들어:

```text
collection_status = partial
본품 = ready
리필 = ambiguous
```

도 정상적으로 완성된 cache입니다.

따라서 cache completeness는 다음과 같은 metadata가 온전히 기록되어 있는지로 판단하도록 변경했습니다.

- collection status
- parser version
- option count
- 각 option의 status
- 각 option의 parser version

---

## 15. `mapped_section_id = NULL` 처리 이슈

실제 구현 과정에서 non-ready 옵션의 `mapped_section_id`가 `NULL`이면 cache를 불완전하다고 판단하는 문제가 있었습니다.

하지만 다음 상태에서는 `NULL`이 정상입니다.

```text
status = unmapped
mapped_section_id = NULL
```

이는 section 추출에 성공했다는 뜻이 아니라:

> section을 찾지 못했다는 실패 상태가 정상적으로 기록되었다.

는 의미입니다.

`ambiguous` 역시 하나의 section을 확정하지 못한 경우 `mapped_section_id=NULL`이 정상일 수 있습니다.

따라서 `mapped_section_id`를 cache completeness 필수 조건에서 제거했습니다.

---

## 16. Legacy Cache 호환 유지

기존 cache 데이터를 migration 때문에 모두 무효화하지 않도록 legacy fallback을 유지했습니다.

```text
new option-level metadata가 완전함
→ new reader 사용

신규 metadata가 없거나 불완전함
→ legacy reader fallback
```

이를 통해 기존 cache를 깨뜨리지 않고 새 구조를 단계적으로 적용했습니다.

---

## 17. API에 옵션 상태 노출

Option-level cache와 partial 상태가 실제 서비스 흐름에서도 사용될 수 있도록 API 응답에 상태를 추가했습니다.

### 상품 응답

```text
collection_status
```

### 옵션 응답

```text
status
analysis_available
```

예:

```json
{
  "collection_status": "partial",
  "options": [
    {
      "option_name": "본품",
      "status": "ready",
      "analysis_available": true
    },
    {
      "option_name": "리필",
      "status": "ambiguous",
      "analysis_available": false
    }
  ]
}
```

`analysis_available`은 다음 기준으로 결정합니다.

```text
analysis_available = status == "ready"
```

---

## 18. 상품 단위가 아닌 Option 단위 분석 허용

partial 상품에서는 상품 전체 상태만 보고 분석을 막으면 안 됩니다.

예:

```text
상품 = partial

본품 = ready
리필 = ambiguous
```

이 경우 본품은 충분히 분석할 수 있습니다.

따라서 분석 가능 여부를 상품 전체 `collection_status`가 아니라 **사용자가 선택한 option의 `analysis_available`**을 기준으로 판단하도록 변경했습니다.

이를 통해 하나의 옵션 실패 때문에 이미 정상적으로 수집된 옵션까지 분석할 수 없는 문제를 해결했습니다.

---

## 19. Partial Cache 재사용

partial 결과도 정상적인 cache snapshot으로 인정한 뒤 다음과 같이 재사용하도록 변경했습니다.

```text
ready cache   → HIT
partial cache → HIT
```

따라서 이미 partial 결과가 저장된 상품을 다시 요청하면 정상 옵션과 실패 상태를 그대로 재사용할 수 있습니다.

### 효과

- Playwright 브라우저 실행 횟수 감소
- 동일 상품 페이지 반복 접근 감소
- 외부 사이트 요청 수 감소
- 기존 성공 데이터 유지

---

## 20. Frontend 상태 동기화

Backend가 옵션 상태를 제공하기 시작하면서 Frontend도 동일한 기준을 사용하도록 변경했습니다.

핵심 기준은:

```text
analysis_available
```

입니다.

기존의 별도 판단 기준 대신 Backend에서 결정한 옵션 상태를 그대로 사용합니다.

### UI 정책

모든 옵션은 목록에서 확인할 수 있게 유지하되, non-ready 옵션은:

```text
disabled
+ "분석 불가"
```

로 표시합니다.

### 기본 선택 로직

기존에는 첫 번째 옵션을 자동 선택했습니다.

하지만 다음과 같은 경우 문제가 생깁니다.

```text
1. 기획세트 → ambiguous
2. 본품 → ready
```

따라서:

```text
첫 번째 옵션
```

이 아니라:

```text
첫 번째 analysis_available == true 옵션
```

을 자동 선택하도록 변경했습니다.

ready 옵션이 하나도 없으면 자동 선택하지 않습니다.

---

## 21. Selector 결과의 Production 전환

관찰 모드에서 검증한 뒤 safe selector가 선택한 결과를 실제 production 경로에 적용했습니다.

feature flag:

```env
PRODUCT_SELECTED_PARSER_RESULT_ENABLED=false
```

를 추가했습니다.

### OFF

```text
production parser
→ API
→ cache
```

### ON

```text
production ─┐
            ├─ selector
shadow ─────┘
                ↓
        effective result
                ↓
            API + cache
```

뒤쪽 코드에서는 production/shadow 여부를 계속 나누지 않고 `effective_parser_result` 하나를 사용하도록 통일했습니다.

이를 통해 API와 cache가 서로 다른 parser 결과를 사용하는 문제를 방지했습니다.

---

## 22. Production 전환 중 발생한 주요 이슈

### 22.1 중복 append

초기에는 shadow가 effective result로 선택될 때 기존 production 데이터가 들어 있는 배열에 shadow 결과를 추가하면서 중복이 발생할 수 있었습니다.

```text
production entries
+
shadow entries
```

가 아니라, 선택된 effective result로 완전히 교체하도록 수정했습니다.

### 22.2 Shadow Provenance 유실

shadow 결과를 선택한 뒤 다시 production result처럼 포장하면 실제 결과의 출처가 사라집니다.

초기 형태:

```text
실제 결과 = shadow
저장 source = production
```

이를 수정해 선택된 `ParserResult` 자체를 그대로 effective result로 사용했습니다.

```text
source = shadow
```

가 DB 저장 경로까지 유지되도록 했습니다.

### 22.3 선택되지 않은 Raw Shadow 저장 가능성

shadow source 저장을 허용하면서 selector가 선택하지 않은 raw shadow까지 cache에 들어갈 수 있는지 점검했습니다.

실제 저장 경로는 동일한 `effective_parser_result`를 사용하고 있었고, 다음 조건일 때만 shadow가 effective result가 됩니다.

```text
selected_parser_result_enabled = true
AND
selection.selected == shadow
```

따라서 선택되지 않은 raw shadow가 cache에 저장되는 경로가 없도록 유지했습니다.

---

## 23. 관련 모듈 역할

### `normalization.py`

수집한 원본 텍스트를 parser가 처리하기 쉬운 형태로 정리합니다.

주요 역할:

- 연속 공백 제거
- 줄바꿈 형식 통일
- 빈 문자열 제거
- 괄호 및 구분자 정리
- 비교에 사용할 문자열 형식 통일

### `option_parser.py`

수집된 데이터에서 옵션별 영역을 분리합니다.

주요 역할:

- 옵션 이름 인식
- 옵션별 원본 데이터 분리
- 옵션 사이의 경계 판별
- 옵션별 파싱 결과 생성

### `ingredient_parsing.py`

옵션 내부 텍스트에서 실제 전성분과 기타 문구를 분리합니다.

주요 역할:

- 전성분 후보 분리
- 최소 성분 개수 검증
- 구성품 그룹 인식
- 성분 목록 생성
- 후행 안내 문구 분리

### `option_models.py`

옵션 파싱 과정에서 사용하는 내부 데이터 구조를 정의합니다.

주요 데이터:

- 옵션 이름
- 구성품 그룹
- 구성품별 전성분
- annotation 후보
- 파싱 상태
- 파싱 오류

### `parser_state.py`

parser 종류와 무관하게 사용할 공통 옵션/상품 상태와 selector 결과 구조를 정의합니다.

### DB model / repository 계층

상품, 옵션, 전성분, option-level 상태, parser metadata 등을 SQLite에 저장하고 legacy cache와 신규 cache를 함께 읽습니다.

### API schema 계층

상품 검색, 상품 선택, 옵션 상태, 분석 가능 여부 등 Frontend와 주고받는 요청·응답 구조를 정의합니다.

---

## 24. 최종 데이터 수집 흐름

```text
상품 페이지 수집
        ↓
Canonical Option 생성
        ↓
Production Parser
        ↓
ParserResult
        │
        ├─ ready
        │    ↓
        │  그대로 사용
        │
        └─ partial / failed
             ↓
        Shadow Parser
             ↓
        Shadow ParserResult
             ↓
        Safe Selector
             ↓
      Effective ParserResult
             ↓
     ┌───────┴────────┐
     ↓                ↓
Option-level Cache    API
     ↓                ↓
Option Status     collection_status
Parser Version    option.status
Diagnostics       analysis_available
     └───────┬────────┘
             ↓
          Frontend
             ↓
     ready 옵션만 분석
```

---

## 25. Playwright Headless 배포 이슈

데이터 수집 구조 개선 후 배포 환경에서 Playwright 실행 방식도 검증했습니다.

배포 서버에는 일반적으로 GUI가 없기 때문에 초기에는:

```env
PLAYWRIGHT_HEADLESS=true
```

를 사용할 계획이었습니다.

이를 위해 Playwright 실행 모드를 환경변수 기반으로 분리했습니다.

```python
headless=settings.playwright_headless
```

하지만 실제 A/B 테스트에서 다음 차이가 확인되었습니다.

```text
PLAYWRIGHT_HEADLESS=false
→ 상품 검색 정상
→ 상품 선택 정상
→ 전성분 수집 정상

PLAYWRIGHT_HEADLESS=true
→ 브라우저 확인 화면
→ 정상 상품 HTML 수집 실패
→ locator 탐색 실패
→ PRODUCT_COLLECTION_RETRY_LATER / 409
```

실제로 확인된 화면은 다음과 같은 브라우저 확인 페이지였습니다.

```text
"잠시만 기다리십시오…"
"안전하고 원활한 올리브영 이용을 위해 접속 정보를 확인 중이에요"
```

처음에는 parser나 cache 문제를 의심했지만, 동일 조건에서 headless 설정만 바꿔 비교한 결과 상품 HTML을 받기 이전 단계에서 발생하는 문제임을 확인했습니다.

---

## 26. 배포 실행 방식 재검토

따라서 다음 가정을 제거했습니다.

```text
배포 서버 = 무조건 headless=true
```

현재 검토 중인 방식은 Linux/Docker 환경에서 Xvfb 가상 디스플레이를 제공하고 Chromium은 `headless=false`로 실행하는 구조입니다.

```text
Linux / Docker
      ↓
Xvfb Virtual Display
      ↓
Chromium
headless=false
      ↓
Playwright Live Collection
```

이 방식은 브라우저 확인 절차를 우회하기 위한 구현이 아니라, **현재 정상 동작이 확인된 headed Chromium 실행 환경을 GUI가 없는 서버에서도 제공하기 위한 배포 방식**입니다.

실제 배포 환경에서 Xvfb 기반 live collection이 정상 동작하는지는 추가 검증이 필요한 상태입니다.

---

## 27. 테스트 및 검증

데이터 수집 파이프라인을 단계적으로 변경하면서 회귀 테스트도 함께 확장했습니다.

### Backend 주요 검증 항목

- Option status 모델
- Collection status 계산
- Safe selector
- Canonical option identity
- Partial cache 저장
- Partial cache 재조회
- Legacy cache fallback
- `mapped_section_id=NULL` 처리
- Failed 상품 분석 차단
- Selector flag OFF 시 production-only 동작 유지
- Selector flag ON 시 shadow 적용
- Shadow provenance 보존
- Shadow cache 재조회
- Playwright headless boolean 설정 변환

---

## 28. 주요 트러블슈팅

### 28.1 Playwright 수집과 Parsing 로직 결합

**문제**

브라우저 접근, 옵션 수집, 전성분 해석이 하나의 흐름에 결합되어 있어 테스트와 오류 추적이 어려웠습니다.

**해결**

Playwright는 원본 데이터 수집에 집중하고, 정규화·옵션 분리·전성분 분석을 독립적인 parser 모듈로 분리했습니다.

**결과**

브라우저 없이 parser를 테스트할 수 있고, 수집 오류와 parsing 오류를 별도로 확인할 수 있게 되었습니다.

### 28.2 구성품 그룹 정보 유실

**문제**

본품, 리필, 증정품 등의 텍스트를 제거하면 각 전성분이 어느 구성품에 해당하는지 알 수 없고, 그대로 두면 성분명으로 오인될 수 있었습니다.

**해결**

구성품 이름을 성분 목록에서는 제외하되 별도의 component group으로 보존했습니다.

**결과**

세트 상품의 구성품별 전성분을 독립적으로 저장하고 분석할 수 있게 되었습니다.

### 28.3 상품 설명을 전성분으로 오인

**문제**

쉼표로 구분된 짧은 설명이나 전성분 뒤의 안내 문구가 성분 목록에 포함될 수 있었습니다.

**해결**

최소 성분 개수로 전성분 후보를 검증하고, 애매한 후행 문구는 `annotation_candidates`로 분리했습니다.

**결과**

성분 분석 데이터의 오염을 줄이면서 원본 정보가 완전히 유실되는 것도 방지했습니다.

### 28.4 일부 옵션 실패로 전체 상품 차단

**문제**

상품 단위 ready/failed 상태만 사용하면 하나의 옵션 실패 때문에 이미 성공한 옵션까지 사용할 수 없었습니다.

**해결**

옵션별 상태와 `analysis_available`, 상품의 `partial` 상태를 도입했습니다.

**결과**

성공한 옵션은 그대로 분석할 수 있고, 실패한 옵션만 제한할 수 있게 되었습니다.

### 28.5 Partial Cache를 불완전 Cache로 판단

**문제**

일부 옵션이 non-ready라는 이유로 partial cache 전체를 invalid로 판단할 가능성이 있었습니다.

**해결**

parser 성공 여부와 cache completeness를 분리했습니다.

**결과**

partial 상태도 정상적인 cache snapshot으로 재사용할 수 있게 되었습니다.

### 28.6 `mapped_section_id=NULL` 처리 오류

**문제**

`unmapped`나 일부 `ambiguous` 상태에서 NULL이 정상인데도 cache invalid로 판단하는 문제가 있었습니다.

**해결**

`mapped_section_id`를 cache completeness 필수 조건에서 제거했습니다.

**결과**

실패 상태 자체도 정상적인 상태 데이터로 보존하고 재사용할 수 있게 되었습니다.

### 28.7 Shadow Parser 적용 위험

**문제**

새 parser가 일부 데이터를 더 추출하더라도 기존 정상 결과를 변경할 위험이 있었습니다.

**해결**

기존 ready 결과를 그대로 보존하면서 추가 ready 옵션만 복구하는 경우에만 shadow를 선택하는 Safe Selector를 도입했습니다.

**결과**

새 parser를 observation → validation → production 순서로 단계적으로 도입할 수 있게 되었습니다.

### 28.8 Shadow Provenance 유실

**문제**

선택된 shadow 결과를 production result처럼 다시 포장하면 실제 parser source 정보가 사라질 수 있었습니다.

**해결**

선택된 `ParserResult` 자체를 effective result로 사용했습니다.

**결과**

cache에서도 결과의 실제 생성 parser를 추적할 수 있게 되었습니다.

### 28.9 Headless 환경에서 상품 수집 실패

**문제**

배포를 가정해 `headless=true`로 실행했을 때 실제 상품 페이지 대신 브라우저 확인 화면이 나타났습니다.

**분석**

동일 조건 A/B 테스트에서 다음 차이를 확인했습니다.

```text
headless=false → 정상 수집
headless=true  → 브라우저 확인 화면 및 수집 실패
```

**대응**

배포 서버에서 무조건 headless 모드를 사용하는 대신 Linux의 가상 디스플레이에서 headed Chromium을 실행하는 방향으로 배포 구조를 재검토했습니다.

---

## 29. 개선 결과

상품 전체의 성공/실패 중심 구조를 옵션 단위의 부분 성공 구조로 전환하고, Playwright 수집부터 parser, cache, API, Frontend, production rollout까지 하나의 일관된 상태 모델로 연결했다.

주요 개선 결과:

- Playwright와 parser 책임 분리
- 옵션별 전성분 관리
- 본품 / 리필 / 증정품 구조 보존
- 전성분 오탐 감소
- 애매한 후행 문구 보존
- 실패 원인 세분화
- Partial Success 지원
- Option-level Cache 도입
- Legacy Cache 호환 유지
- Partial Cache 재사용
- 불필요한 Playwright 재실행 감소
- Production / Shadow Parser 안전 비교
- Canonical Option ID 안정화
- Feature Flag 기반 단계적 Production 전환
- Parser Provenance 보존
- Backend / Frontend 상태 기준 통일
- 배포 환경에서 Playwright 실행 조건 검증

---

## 30. 현재 상태와 이후 작업

- Docker 환경에서 Xvfb + headed Chromium 검증
- 실제 배포 환경에서 Playwright live collection 검증
- 상품별 parser failure 사례 추가 수집
- diagnostics 기반 parser 규칙 개선
- 필요한 옵션만 다시 처리하는 selective recollection 고도화
- 배포 후 수집 실패율 및 cache hit rate 관찰
- 실제 상품 데이터를 이용한 회귀 테스트 확대
