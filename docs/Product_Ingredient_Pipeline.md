# DermaRAG Product Ingredient Pipeline

## 1. 개요

DermaRAG의 기존 기능은 사용자가 직접 입력한 화장품 전성분을 식약처 성분 데이터 기반 RAG로 분석하는 것이었다.

이번 작업에서는 사용자가 전성분을 직접 복사하지 않아도 실제 상품을 검색하고 선택한 뒤, 상품 상세 페이지에서 전성분을 가져올 수 있도록 상품 처리 파이프라인을 추가했다.

현재 구현된 흐름은 다음과 같다.

```text
상품 검색
→ 상품 후보 반환
→ 상품 선택
→ 상품 카테고리 분류
→ 올리브영 상품 페이지 접속
→ 상품정보 제공고시 자동 펼침
→ 전성분 추출 및 정규화
```

현재는 Mock 상품 검색 Provider와 실제 올리브영 상품 URL을 이용해 기능을 검증하고 있다.

향후에는 추출한 전성분을 공용 DB에 저장하고, 기존 성분 RAG와 연결하여 상품별 주의 성분과 근거를 설명하는 기능으로 확장할 예정이다.

---

## 2. 개발 목표

상품 파이프라인의 최종 목표는 다음 두 가지 질문을 처리하는 것이다.

### 상품을 기준으로 분석

```text
“이 상품이 민감성 피부에 괜찮은지 분석해줘.”
```

예정 처리 흐름:

```text
상품 검색 및 선택
→ 저장된 전성분 조회
→ 저장된 데이터가 없으면 실시간 추출
→ 식약처 성분 RAG 검색
→ 사용자 피부 정보와 비교
→ 주의 성분과 근거 설명
```

### 성분을 기준으로 상품 검색

```text
“나이아신아마이드가 들어간 상품을 알려줘.”
```

예정 처리 흐름:

```text
질문에서 성분명 추출
→ 정규화된 성분명으로 상품 DB 검색
→ 해당 성분을 포함한 상품 후보 반환
→ 상품 선택 시 상세 분석
```

---

## 3. 현재 구현 상태

### 완료

- 상품 데이터 모델 정의
- 상품 검색 Provider 인터페이스 정의
- Mock 상품 검색 Provider 구현
- 상품 검색 API 구현
- 상품 선택 API 구현
- 상품 카테고리 분류기 분리
- 스킨케어·색조 분류 우선순위 처리
- Playwright 기반 올리브영 전성분 추출기 구현
- 상품정보 제공고시 자동 스크롤
- 상품정보 제공고시 아코디언 자동 클릭
- 클릭 타이밍 문제 재시도 처리
- 전성분 원문 및 성분 목록 반환
- 상품 서비스와 추출기 연결
- 서비스 단위 테스트와 실제 페이지 통합 테스트 작성

### 진행 예정

- SQLite 기반 상품·전성분 저장소
- 기존 상품의 전성분 캐시 재사용
- 전성분 갱신 주기 및 변경 감지
- 추출 결과와 기존 성분 RAG 연결
- 사용자 피부 프로필 기반 상품 분석
- 특정 성분을 포함한 상품 역검색
- 색조 상품 옵션별 전성분 처리
- `product_analysis` LangGraph route
- `ingredient_product_search` LangGraph route

---

## 4. 프로젝트 구조

```text
app/
├── main.py
├── products/
│   ├── __init__.py
│   ├── models.py
│   ├── classifier.py
│   ├── service.py
│   │
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── mock.py
│   │
│   └── ingredient_extractors/
│       ├── __init__.py
│       ├── base.py
│       └── oliveyoung_browser.py
│
└── ...

scripts/
├── check_oliveyoung_ingredients.py
├── test_product_classifier.py
├── test_product_service.py
└── test_oliveyoung_ingredient_extractor.py
```

각 파일의 역할은 다음과 같다.

| 파일 | 역할 |
|---|---|
| `products/models.py` | 상품 후보, 검색 결과, 전성분 추출 결과 모델 |
| `products/classifier.py` | 상품명을 기반으로 스킨케어·색조 분류 |
| `products/service.py` | 상품 검색, 선택 및 전성분 추출 연결 |
| `providers/base.py` | 상품 검색 Provider 인터페이스 |
| `providers/mock.py` | 개발 및 테스트용 상품 목록 |
| `ingredient_extractors/base.py` | 전성분 추출기 인터페이스 |
| `ingredient_extractors/oliveyoung_browser.py` | Playwright 기반 올리브영 전성분 추출 |
| `check_oliveyoung_ingredients.py` | 실제 페이지 추출 가능성 확인용 스크립트 |
| `test_product_classifier.py` | 상품 카테고리 분류 테스트 |
| `test_product_service.py` | 상품 검색·선택·추출기 연결 테스트 |
| `test_oliveyoung_ingredient_extractor.py` | 실제 올리브영 페이지 통합 테스트 |

---

## 5. 상품 모델

상품 검색 결과는 `ProductCandidate`로 표현한다.

주요 필드는 다음과 같다.

```text
product_id
source
brand_name
product_name
category
category_path
product_url
image_url
original_price
sale_price
rank
search_query
fetched_at
```

상품의 전성분 추출 결과는 `ProductIngredientResult`로 표현한다.

```text
product_id
product_url
raw_ingredients
ingredients
extraction_method
extraction_success
error_message
```

`raw_ingredients`와 `ingredients`를 모두 유지한다.

```text
raw_ingredients
→ 상품 페이지에 표시된 전성분 원문

ingredients
→ 쉼표 기준으로 분리하고 공백을 정리한 성분 목록
```

원문을 함께 보관하면 성분 분리 정책이 변경되었을 때 상품 페이지를 다시 요청하지 않고 재처리할 수 있다.

---

## 6. 상품 카테고리 분류

상품 카테고리는 다음과 같이 구분한다.

```text
skincare
color_makeup
other
unknown
```

상품명과 카테고리 경로의 키워드를 기반으로 분류한다.

색조 키워드는 스킨케어 키워드보다 먼저 검사한다.

예를 들어 다음 상품명에는 색조 키워드와 스킨케어 키워드가 함께 포함되어 있다.

```text
컬러 글로우 립 세럼
```

```text
립
→ color_makeup 키워드

세럼
→ skincare 키워드
```

스킨케어 키워드를 먼저 검사하면 해당 상품이 `skincare`로 잘못 분류된다.

현재 분류 순서는 다음과 같다.

```text
카테고리 경로
→ 색조 키워드
→ 스킨케어 키워드
→ 기타 또는 분류 불명
```

이 우선순위는 회귀 테스트로 보호한다.

---

## 7. 상품 검색과 선택

현재 상품 검색은 `MockProductSearchProvider`를 사용한다.

Mock Provider에는 다음 세 종류의 검증용 상품이 포함되어 있다.

```text
MOCK-SKIN-001
→ 스킨케어 분류 테스트

MOCK-COLOR-001
→ 색조 분류 테스트

A000000149135
→ 실제 올리브영 전성분 추출 테스트
```

상품 검색 후 결과는 `ProductSearchService`의 `_last_candidates`에 임시 저장된다.

```text
/products/search
→ 상품 목록 검색 및 분류
→ _last_candidates에 저장

/products/select
→ product_id로 직전 후보에서 상품 선택

/products/extract-ingredients
→ 선택한 상품의 product_url로 전성분 추출
```

현재 구조는 단일 사용자 개발 환경을 위한 임시 구조다.

여러 사용자가 동시에 검색할 경우 `_last_candidates`가 서로 덮어써질 수 있으므로 실제 서비스에서는 `search_id`, 사용자 세션 또는 DB 기반 상태 관리로 변경해야 한다.

---

## 8. 올리브영 전성분 DOM 조사

검증에 사용한 상품 URL은 다음과 같다.

```text
https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000149135
```

브라우저 개발자 도구에서 확인한 전성분 구조는 다음과 같다.

```html
<tr>
    <th scope="row">
        화장품법에 따라 기재해야 하는 모든 성분
    </th>
    <td>
        정제수, 다이부틸아디페이트, 프로판다이올, ...
    </td>
</tr>
```

전성분이 이미지가 아닌 DOM 텍스트로 제공되므로, 해당 상품에서는 OCR 없이 전성분을 추출할 수 있다.

추출 방식은 다음과 같다.

```text
“모든 성분” 문구를 포함한 TH 탐색
→ 같은 행의 다음 TD 탐색
→ TD의 innerText 추출
```

---

## 9. Playwright 전성분 추출기

일반 HTTP 요청으로 올리브영 페이지에 접근했을 때 `403 Forbidden`이 발생했다.

이에 따라 접근 제한을 우회하는 방식은 사용하지 않고, 일반 사용자가 볼 수 있는 Chrome 브라우저에서 공개적으로 표시되는 DOM을 Playwright로 읽는 방식을 검증했다.

사용하지 않는 방식:

```text
CAPTCHA 우회
stealth 플러그인
프록시 회전
브라우저 지문 위조
로그인 쿠키 강제 복사
```

현재 추출기는 다음 순서로 동작한다.

```text
Google Chrome 실행
→ 상품 상세 페이지 접속
→ 상품정보 제공고시 위치까지 자동 스크롤
→ 제공고시 아코디언 버튼 탐색
→ 아코디언 자동 클릭
→ 전성분 TH가 표시될 때까지 대기
→ 인접한 TD에서 전성분 추출
→ ProductIngredientResult 반환
```

---

## 10. 클릭 레이스 컨디션 해결

초기에는 상품정보 제공고시 버튼을 한 번만 클릭하고 고정된 시간 동안 대기했다.

```text
스크롤
→ 한 번 클릭
→ 1.5초 대기
→ 전성분 TH를 최대 60초 대기
```

올리브영 페이지는 스크롤 직후에도 지연 콘텐츠를 로드하면서 요소 위치가 계속 바뀌었다.

이 때문에 selector와 실제 클릭 대상이 정확해도 클릭이 타이밍상 처리되지 않는 경우가 있었다.

실제 클릭 대상:

```html
<button
    class="Accordion_accordion-btn__..."
    aria-expanded="false"
>
    <span>상품정보 제공고시</span>
</button>
```

수정된 방식:

```text
버튼 클릭
→ 짧은 시간 동안 전성분 표시 여부 확인
→ 열리지 않았으면 재클릭
→ 최대 5회 시도
```

`aria-expanded="true"`인 경우에는 다시 클릭하지 않는다.

이미 열린 아코디언을 재시도 과정에서 다시 닫는 문제를 방지하기 위함이다.

해당 로직을 별도 반복 테스트로 검증한 뒤 정식 추출기에 반영했다.

---

## 11. 상품 서비스와 추출기 연결

초기 서비스 연결에는 다음 문제가 있었다.

### 추출기 속성명 불일치

```text
생성자:
ingredient_extractors

실제 사용:
ingredient_extractor
```

단수와 복수가 달라 존재하지 않는 속성을 조회할 수 있었다.

추출기 객체를 하나만 저장하므로 프로젝트 전체에서 다음 단수형 이름으로 통일했다.

```python
ingredient_extractor
```

### `find_product()` 호출 인자 불일치

`find_product()`는 상품 목록을 필요로 했지만 `product_id`만 전달하고 있었다.

또한 검색 결과를 `_last_candidates`에 갱신하지 않아 다음 요청에서 선택할 상품 목록이 존재하지 않았다.

수정 후 흐름:

```text
search()
→ 분류가 완료된 상품 목록 생성
→ self._last_candidates에 저장

extract_product_ingredients()
→ _last_candidates에서 product_id 탐색
→ 선택한 상품의 product_url 확인
→ ingredient_extractor.extract() 호출
```

---

## 12. API

FastAPI는 다음 명령으로 실행한다.

```bash
uv run --env-file .env \
  python -m uvicorn app.main:app --reload
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

### 상품 검색

```http
POST /products/search
```

요청 예:

```json
{
  "query": "라운드랩"
}
```

### 상품 선택

```http
POST /products/select
```

요청 예:

```json
{
  "product_id": "A000000149135"
}
```

### 전성분 추출

```http
POST /products/extract-ingredients
```

요청 예:

```json
{
  "product_id": "A000000149135"
}
```

예상 응답 구조:

```json
{
  "product_id": "A000000149135",
  "product_url": "https://www.oliveyoung.co.kr/...",
  "raw_ingredients": "정제수, 다이부틸아디페이트, ...",
  "ingredients": [
    "정제수",
    "다이부틸아디페이트",
    "프로판다이올"
  ],
  "extraction_method": "browser_dom",
  "extraction_success": true,
  "error_message": null
}
```

---

## 13. 테스트

전체 테스트는 다음 명령으로 실행한다.

```bash
uv run python -m pytest -v
```

현재 결과:

```text
27 collected
27 passed
0 failed
```

### 분류기 테스트

```text
선크림 → skincare
세럼 → skincare
쿠션 → color_makeup
립 틴트 → color_makeup
립 세럼 → color_makeup 우선
불명확한 상품 → unknown
```

### 상품 서비스 테스트

```text
상품 후보 반환
limit 적용
상품 ID 기반 검증
상품 category 검증
metadata.result_count 일치
알려진 product_id 선택
존재하지 않는 product_id 처리
product_id 앞뒤 공백 처리
```

### 전성분 추출 서비스 테스트

실제 Playwright 대신 `FakeIngredientExtractor`를 주입하여 다음 연결을 검증한다.

```text
올바른 product_id 전달
올바른 product_url 전달
추출 결과 반환
후보에 없는 product_id 처리
검색 전에 추출을 요청한 경우 처리
추출기가 설정되지 않은 경우 처리
```

### 실제 페이지 통합 테스트

실제 올리브영 상품 페이지를 대상으로 다음 결과를 확인했다.

```text
extraction_success=True
전성분 42개 추출
ingredients에 “정제수” 포함
```

실제 페이지 테스트는 외부 네트워크와 사이트 구조에 영향을 받으므로 향후 `pytest.mark.integration`으로 일반 단위 테스트와 분리할 예정이다.

---

## 14. 현재 한계

### 실제 상품 검색 Provider 미구현

현재 상품 검색은 Mock Provider 기반이다.

실제 올리브영 상품 URL에서 전성분을 추출하는 것은 가능하지만, 올리브영 전체 상품 검색 Provider는 아직 구현하지 않았다.

### 메모리 기반 검색 후보

`_last_candidates`가 전역 서비스 객체에 저장되어 여러 사용자가 동시에 검색할 경우 서로의 후보를 덮어쓸 수 있다.

현재는 단일 사용자 개발 및 Swagger 확인 용도로만 사용한다.

### 외부 페이지 의존성

다음 변경이 발생하면 selector를 재검토해야 한다.

```text
상품정보 제공고시 제목 변경
아코디언 구조 변경
전성분 TH 문구 변경
TH와 TD의 형제 구조 변경
접근 정책 변경
```
---

## 15. 다음 개발 계획

### Phase 1: 상품·전성분 저장소

SQLite와 SQLAlchemy를 이용해 다음 데이터를 공용으로 저장한다.

```text
상품 기본 정보
전성분 원문
정규화된 성분 목록
추출 날짜
마지막 확인 날짜
전성분 hash
추출 성공 여부
```

처리 방식:

```text
저장된 전성분 없음
→ 실시간 추출 후 저장

최신 전성분 있음
→ 저장된 데이터 재사용

갱신 기간 만료
→ 다시 추출하고 변경 여부 확인
```

초기 TTL 예시:

```text
90일
```

### Phase 2: 상품 분석 RAG

```text
추출 또는 저장된 전성분
→ 기존 식약처 성분 RAG
→ 상품별 주요 성분과 주의 성분 분석
→ 근거 및 출처 포함
```

새 LangGraph route:

```text
product_analysis
```

### Phase 3: 사용자 맞춤 분석

```text
피부 타입
피부 고민
알레르기
피하고 싶은 성분
과거 피부 반응
현재 루틴
```

상품 데이터는 모든 사용자가 공유하지만 사용자 피부 정보는 사용자 또는 세션별로 분리한다.

### Phase 4: 성분으로 상품 검색

공용 DB에 저장된 상품을 대상으로 다음 질문을 처리한다.

```text
“나이아신아마이드가 들어간 상품을 알려줘.”
```

새 LangGraph route:

```text
ingredient_product_search
```

초기에는 다음과 같이 검색 범위를 명시한다.

```text
현재까지 수집된 상품 중에서 검색한 결과입니다.
```

### Phase 5: 색조 옵션

색조 상품은 옵션마다 전성분이 다를 수 있으므로 다음 키로 저장한다.

```text
source + product_id + option_id
```

---

## 17. 목표 아키텍처

```text
상품 검색 Provider
        ↓
상품 선택
        ↓
상품·전성분 Repository 조회
        ├─ 최신 캐시 있음
        │       ↓
        │   저장된 전성분 사용
        │
        └─ 없음 또는 만료
                ↓
        OliveYoungIngredientExtractor
                ↓
          전성분 DB 저장
        ↓
기존 식약처 성분 RAG
        ↓
사용자 피부 프로필 비교
        ↓
상품 분석 답변
