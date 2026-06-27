# DermaRAG

화장품 전성분표와 사용자 피부 반응 정보를 입력받아, 공공 성분 데이터 기반으로 피부 반응 원인 후보를 분석하는 RAG 기반 챗봇 API 프로젝트입니다.

사용자가 제품 전성분표, 피부 타입, 현재 스킨케어 루틴, 피부 반응 설명을 입력하면, 식품의약품안전처 화장품 원료성분정보를 기반으로 관련 성분 문서를 검색하고 Gemini가 근거 기반 답변을 생성합니다.

---

## 2. 현재 구현 상태

| 항목                          | 상태    |
| --------------------------- | ----- |
| 식약처 화장품 원료성분정보 API 수집       | 완료    |
| 수집 데이터 JSONL 저장             | 완료    |
| 성분 1개 = Document 1개 구조화     | 완료    |
| 로컬 HuggingFace Embedding 적용 | 완료    |
| Chroma Vector DB 저장         | 완료    |
| 성분명 exact match 기반 검색       | 완료    |
| Vector search fallback 구조   | 완료    |
| Gemini 기반 답변 생성             | 완료    |
| FastAPI `/chat` REST API 구현 | 완료    |
| LangSmith tracing           | 예정    |
| Dataset 기반 평가               | 예정    |
| 외부 서버 배포                    | 선택 사항 |

---

## 3. 주요 기능

### 3.1 전성분표 기반 성분 검색

사용자가 입력한 전성분표를 성분 단위로 분리합니다.

예시:

```text
정제수, 티타늄디옥사이드, 글리세린, 나이아신아마이드, 향료, 판테놀
```

각 성분을 개별 검색어로 사용하여 성분 DB에서 관련 문서를 검색합니다.

---

### 3.2 Hybrid Retrieval

현재 retrieval 방식은 다음 순서로 동작합니다.

```text
1. 성분명 / 영문명 / CAS 번호 / 동의어 exact match 검색
2. exact match 결과가 있으면 해당 결과 우선 반환
3. exact match 결과가 없을 경우 Chroma vector search 사용
```
---

### 3.3 Gemini 기반 답변 생성

검색된 성분 문서를 context로 구성하고, Gemini 모델이 사용자 피부 반응에 대한 답변을 생성합니다.

---

## 4. 프로젝트 구조

```text
derma-rag/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── embeddings.py
│   ├── main.py
│   ├── rag_chain.py
│   ├── retriever.py
│   └── schemas.py
│
├── data/
│   ├── mfds_ingredients_raw.jsonl
│   └── mfds_ingredients.txt
│
├── scripts/
│   ├── __init__.py
│   ├── ingest.py
│   ├── mfds_ingredients.py
│   └── test_retriever.py
│
├── vectorstore/
│   └── chroma/
│
├── .env
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

---

## 5. 파일별 역할

| 파일/폴더 | 역할 |
|---|---|
| `app/schemas.py` | `/chat` 요청과 응답에 사용할 Pydantic 스키마를 정의 |
| `app/config.py` | API key, 모델명, embedding 방식 등 프로젝트 설정값을 관리 |
| `app/embeddings.py` | 인덱싱과 검색 단계에서 동일한 embedding 모델을 사용할 수 있도록 embedding 객체를 생성 |
| `app/retriever.py` | 성분명 exact match 검색과 Chroma vector search fallback을 담당 |
| `app/rag_chain.py` | 전성분표 분리, 문서 검색, context 구성, prompt 생성, Gemini 답변 생성을 연결 |
| `scripts/mfds_ingredients.py` | 식약처 화장품 원료성분정보 API에서 성분 데이터를 수집하고 파일로 저장 |
| `scripts/ingest.py` | 수집한 성분 데이터를 LangChain `Document`로 변환하고 Chroma Vector DB에 저장 |
| `scripts/test_retriever.py` | 검색 로직이 제대로 동작하는지 터미널에서 확인하기 위한 테스트 스크립트 |
| `data/` | 공공데이터 API로 수집한 원료성분 raw 데이터와 RAG용 텍스트 파일을 저장 |
| `vectorstore/chroma/` | Chroma Vector DB가 저장되는 폴더 |

## 6. 실행 방법

### 6.1 가상환경 생성 및 활성화

```bash
python -m venv .venv
source .venv/bin/activate
```

---

### 6.2 패키지 설치

```bash
pip install -r requirements.txt
```

---

### 6.3 `.env` 설정

프로젝트 루트에 `.env` 파일을 생성합니다.

```env
GOOGLE_API_KEY=your_gemini_api_key
DATA_GO_KR_SERVICE_KEY=your_data_go_kr_service_key

GEMINI_CHAT_MODEL=gemini-2.5-flash-lite

EMBEDDING_PROVIDER=local
LOCAL_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
GEMINI_EMBEDDING_MODEL=gemini-embedding-001

LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=derma-rag
```

---

### 6.4 공공데이터 수집

```bash
python -m scripts.mfds_ingredients
```

---

### 6.5 Vector DB 생성

```bash
python -m scripts.ingest
```

---

### 6.6 Retriever 테스트

```bash
python -m scripts.test_retriever
```

---

### 6.7 FastAPI 서버 실행

```bash
uvicorn app.main:app --reload
```

Swagger UI 접속:

```text
http://127.0.0.1:8000/docs
```

---

## 7. RAG 파이프라인

현재 `/chat` 요청 처리 흐름

```text
사용자 요청
↓
FastAPI /chat
↓
ChatRequest 검증
↓
전성분표 성분 단위 분리
↓
성분명 exact match 검색
↓
필요 시 Chroma vector search fallback
↓
검색 문서 context 생성
↓
Gemini 답변 생성
↓
answer + sources 반환
```

---

## 8. 트러블슈팅

### 8.1 Gemini Embedding API quota 오류

5000개 이상의 성분 문서를 Gemini embedding API로 한 번에 인덱싱할 경우 무료 티어 요청 제한에 걸렸습니다.

예시 오류:

```text
429 RESOURCE_EXHAUSTED
Quota exceeded for metric: embed_content_free_tier_requests
```

해결 방향:

```text
- embedding 단계는 로컬 HuggingFace 모델 사용
- 답변 생성 단계만 Gemini 사용
```

현재 프로젝트는 이 방식으로 구성되어 있습니다.

---

### 8.2 검색 결과에 관련 없는 성분이 나오는 문제

초기에는 Chroma vector search만 사용하여 `나이아신아마이드` 검색 시 `알부민`, `조선현호색뿌리추출물` 같은 관련 낮은 결과가 반환되었습니다.

원인:

```text
화장품 성분명은 고유명사라 의미 기반 벡터 검색만으로는 정확도가 낮을 수 있음
```

해결:

```text
성분명 exact match 검색을 우선 적용
exact match 결과가 없을 때만 vector search 사용
```

---

### 8.3 `세린`처럼 불필요한 짧은 성분명이 같이 검색되는 문제

현재 일부 짧은 성분명은 다른 긴 성분명 내부에 포함되어 검색되었습니다.

예시:

```text
글리세린 검색 시 세린이 함께 검색될 수 있음
```

현재는 후속 개선 사항으로 남겨두었습니다.

개선 방향:

```text
- 짧은 성분명 부분 일치 제한
- 부분 일치 시 최소 길이 조건 추가
- 완전 일치 결과를 더 강하게 우선
- 전성분표에 실제 포함된 성분만 sources에 남기기
```
---

## 9. 앞으로 할 일

### 9.1 LangSmith Tracing 추가

목표:

```text
- LangChain 실행 과정을 LangSmith에서 확인
- 검색 단계, prompt 구성, LLM 응답 생성 과정을 trace로 기록
```

예정 작업:

```text
.env에 LangSmith 설정 추가
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=derma-rag

LangSmith 환경변수 설정 모듈 추가
FastAPI 실행 시 tracing 활성화
/chat 요청 실행 후 LangSmith 대시보드에서 trace 확인
```

---

### 9.2 Dataset 기반 평가 추가

LangSmith tracing 이후 진행할 예정입니다.

목표:

```text
- 대표 질문/전성분표/피부 타입 테스트셋 구성
- 답변이 안전 원칙을 지키는지 평가
- 검색된 sources가 입력 성분과 관련 있는지 평가
```
---

### 9.3 검색 품질 개선

현재 남은 검색 품질 개선 사항:

```text
- 짧은 성분명 부분 매칭 개선
- 전성분표에 없는 성분이 sources에 포함되지 않도록 필터링
- 성분명 exact match, synonym match, CAS match의 점수 체계 개선
- 검색 결과에 retrieval_type, match_score를 API 응답에도 포함할지 검토
```

---

### 9.4 답변 품질 개선

현재 prompt는 안전성과 근거 기반 답변을 강조하도록 구성되어 있습니다.

추후 개선 방향:

```text
- 검색된 식약처 원료 정보와 일반적인 피부 반응 가능성을 더 명확히 분리
- “근거 문서에서 확인된 정보” 섹션 추가
- “추론 기반 가능성” 섹션 추가
- 사용자에게 제품 사용 중단/관찰/전문가 상담 권장 문구 표준화
```

---

## 회고

이번 프로젝트를 하면서 LLM API를 호출해서 답변을 받는 것과, RAG 구조로 근거 문서를 검색한 뒤 답변을 생성하는 것은 많이 다르다는 것을 느꼈습니다. 처음에는 LangChain을 쓰면 자동으로 좋은 RAG가 만들어질 거라고 생각했는데, 실제로는 데이터를 어떻게 나누고, 어떤 기준으로 검색하고, 어떤 정보를 프롬프트에 넣을지 직접 설계하는 과정이 중요했습니다.

특히 화장품 성분명은 일반 문장 검색과 달라서 vector search만으로는 정확한 결과가 나오지 않았습니다. `나이아신아마이드`를 검색했을 때 관련 없는 성분이 나오는 문제를 겪으면서, 성분명 exact match를 먼저 적용하고 vector search를 보조적으로 사용하는 방식으로 개선했습니다.

또한 Gemini embedding API의 quota 오류를 겪으면서, 대량 데이터를 인덱싱할 때는 비용과 요청 제한도 고려해야 한다는 것을 배웠습니다.

아직 LangSmith tracing과 Dataset 기반 평가는 추가하지 못했지만, 현재는 공공데이터 수집부터 Vector DB 구축, FastAPI `/chat` API 응답까지 연결된 상태입니다. 다음 단계에서는 LangSmith를 적용해서 실행 과정을 추적하고, 평가 데이터셋을 만들어 답변 품질을 더 체계적으로 확인해보고 싶습니다.