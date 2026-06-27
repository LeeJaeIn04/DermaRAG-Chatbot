from fastapi import FastAPI
from app.config import settings
from app.schemas import ChatRequest, ChatResponse
from app.rag_chain import build_answer

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
def chat(request: ChatRequest):
    return build_answer(request)