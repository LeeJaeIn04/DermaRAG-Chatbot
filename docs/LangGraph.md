# DermaRAG - LangGraph Agent Version

DermaRAG는 화장품 전성분표와 사용자 피부 반응 정보를 바탕으로, 공공 성분 데이터에서 관련 근거를 검색하고 Gemini로 안전한 답변을 생성하는 RAG 기반 챗봇 API입니다.

이번 버전에서는 기존 LangChain RAG 흐름을 LangGraph `StateGraph` 기반 workflow로 재구성하고, 사용자 입력 유형에 따라 처리 경로를 선택하는 Agent routing 구조를 추가했습니다.

---

## 1. 핵심 변화

기존 구조는 `/chat` 요청이 들어오면 하나의 RAG 함수가 순차적으로 모든 작업을 처리하는 방식이었습니다.

이번 버전에서는 LangGraph를 적용하여 처리 단계를 node 단위로 분리했습니다.

```text
기존 구조

/chat
  ↓ 
build_answer()
  ↓
성분 분리 → 문서 검색 → context 생성 → 답변 생성 → sources 생성
```

```text
LangGraph 적용 후

/chat
  ↓
derma_rag_graph.invoke()
  ↓
classify_intent
  ↓
route별 node 실행
  ↓
answer + sources 반환
```

---

## 2. LangGraph Workflow

`StateGraph`를 사용


```text
START
  ↓
classify_intent
  ↓
conditional routing
  ├── ingredient_rag
  │     ↓
  │   parse_ingredients
  │     ↓
  │   retrieve_documents
  │     ↓
  │   build_context
  │     ↓
  │   generate_answer
  │     ↓
  │   build_sources
  │     ↓
  │   END
  │
  ├── safety_warning
  │     ↓
  │   safety_warning_node
  │     ↓
  │   END
  │
  ├── routine_check
  │     ↓
  │   routine_check_node
  │     ↓
  │   END
  │
  └── general_answer
        ↓
      general_answer_node
        ↓
      END
```

---

## 3. Agent Routing

`classify_intent` node는 사용자 입력을 분석해서 어떤 경로로 처리할지 결정합니다.


| Route            | 실행 조건                            | 처리 방식            |
| ---------------- | -------------------------------- | ---------------- |
| `ingredient_rag` | 전성분표가 입력된 경우                     | 성분 검색 기반 RAG 답변  |
| `safety_warning` | 부종, 진물, 물집, 호흡곤란 등 위험 신호가 포함된 경우 | 안전 안내 우선 답변      |
| `routine_check`  | 전성분표 없이 루틴 조합 질문이 들어온 경우         | 루틴/사용 상황 중심 답변   |
| `general_answer` | 전성분표와 루틴 정보가 부족한 경우              | 일반 안내 및 추가 입력 요청 |

위험 증상이 감지되면 전성분표가 있더라도 `safety_warning` route를 우선합니다.

---

## 4. 응답 형식

```text
1. 요약
2. 가능성 있는 원인 후보
3. 루틴/사용 상황에서 함께 볼 점
4. 지금 할 수 있는 안전한 대응
5. 주의 문구
```

---

## 5. 현재 프로젝트 구조

```text
derma-rag/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── embeddings.py
│   ├── main.py
│   ├── rag_chain.py
│   ├── retriever.py
│   ├── schemas.py
│   └── graph/
│       ├── __init__.py
│       ├── state.py
│       ├── nodes.py
│       └── workflow.py
│
├── scripts/
│   ├── __init__.py
│   ├── ingest.py
│   ├── mfds_ingredients.py
│   ├── test_retriever.py
│   └── test_agent_graph.py
│
├── data/
│   ├── mfds_ingredients_raw.jsonl
│   └── mfds_ingredients.txt
│
├── vectorstore/
│   └── chroma/
│
├── .env
├── .env.example
├── .gitignore
├── pyproject.toml
├── uv.lock
└── README.md
```

---

## 6. 주요 파일 역할

| 파일                            | 역할                                        |
| ----------------------------- | ----------------------------------------- |
| `app/main.py`                 | FastAPI 앱과 `/chat`, `/health` endpoint 정의 |
| `app/schemas.py`              | 요청/응답 Pydantic schema 정의                  |
| `app/config.py`               | API key, 모델명, embedding 설정 관리             |
| `app/embeddings.py`           | embedding provider 생성                     |
| `app/retriever.py`            | exact match 검색과 vector search fallback 수행 |
| `app/rag_chain.py`            | RAG 답변 생성을 위한 재사용 함수 모음                   |
| `app/graph/state.py`          | LangGraph에서 공유하는 state 타입 정의              |
| `app/graph/nodes.py`          | LangGraph node 함수 정의                      |
| `app/graph/workflow.py`       | StateGraph 구성 및 compile                   |
| `scripts/test_agent_graph.py` | route별 Agent 동작 테스트                       |

---

## 7. 데이터 준비

### 7.1 식약처 성분 데이터 수집

```bash
uv run python -m scripts.mfds_ingredients
```

---

### 7.2 Vector DB 생성

```bash
uv run python -m scripts.ingest
```

---

## 8. 테스트

### 8.1 Retriever 테스트

```bash
uv run python -m scripts.test_retriever
```

---

### 9.2 LangGraph Agent route 테스트

```bash
uv run python -m scripts.test_agent_graph
```

---

## 9. FastAPI 실행

```bash
uv run uvicorn app.main:app --reload
```

---

## 10. LangGraph State

LangGraph workflow에서 사용하는 state는 `DermaRagState`로 관리합니다.

| State key          | 의미                   |
| ------------------ | -------------------- |
| `request`          | 사용자 입력               |
| `route`            | 선택된 처리 route         |
| `warnings`         | 위험 신호 또는 route 관련 안내 |
| `ingredient_names` | 분리된 성분명 목록           |
| `docs`             | 검색된 문서               |
| `context`          | LLM에 전달할 검색 context  |
| `answer`           | 최종 답변                |
| `sources`          | 응답에 포함할 근거 문서        |

---

## 11. 향후 개선 방향

* 기능별 멀티 에이전트 구조 적용
* LangSmith tracing 추가
* 답변 안전성 평가 자동화
* Streamlit 또는 React 기반 챗봇 UI

---

## 회고

기존 구현에서는 하나의 함수 안에서 성분 분리, 검색 , context 생성, 답변 생성 sources 생성이 순서대로 실행되었습니다. 이 방식은 사용자의 입력 유형에 따라 처리하는 로직을 추가하기엔 한계가 있다고 생각했습니다.

초기 RAG에서는 사용자 입력이 들어오면 성분 문서를 검색하고, 검색된 context를 기반으로 답변을 생성하는 흐름이었습니다. 하지만 실제 챗봇 입력을 생각해보았을 때, 모든 질문이 성분 검색을 필요로 하지 않을 것 같다는 생각이 들었습니다. 예를 들어, "새 화장품을 바른 뒤 얼굴이 붓고 진물이 나요." 라는 질문은 성분 DB 검색보다 안전 안내가 더 중요합니다. 또한 "비타민 C 세럼이랑 BHA 토너를 같이 써도 되나요?" 라는 질문은 성분 기반 답변보다는 루틴 사용 상황 중심 안내가 더 적절합니다. 그래서 classify_intent node를 추가하게 되었습니다. 이를 통해 필요한 경우에만 RAG 를 실행하고, 안전 안내가 필요한 경우에는 별도의 흐름으로 처리할 수 있었습니다.

또한 ingredient_rag route에서는 검색 문서가 있으므로 sources를 반환하지만, routine_check나 general_answer처럼 검색이 핵심이 아닌 route에서는 sources가 비어 있을 수 있습니다. 처음에는 모든 응답에 sources가 있어야 한다고 생각할 수도 있지만, route별 역할을 분리하면서 어떤 경우에 sources가 필요한지 더 분명해졌습니다.

아직 기능별 멀티 에이전트 구조까지 구현한 것은 아니지만, 현재의 route 기반 구조는 이후 IngredientRAGAgent, SafetyAgent, RoutineAgent 처럼 역할별 agent를 분리하는 방향으로 확장하는 방향으로 개선할 것입니다.
