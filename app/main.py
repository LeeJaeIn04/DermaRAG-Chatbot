from fastapi import FastAPI
from app.graph.workflow import derma_rag_graph
from app.schemas import ChatRequest, ChatResponse

app = FastAPI(
    title="DermaRAG API",
    description="성분 기반 피부 반응 원인 후보 분석 챗봇 API",
    version="0.1.0",
)

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "project": settings.langsmith_project,
    }

@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    final_state = derma_rag_graph.invoke(
        {
            "request" : request,
        }
    )
    
    return ChatResponse (
        answer = final_state.get("answer", ""),
        sources = final_state.get("sources", []),
    )