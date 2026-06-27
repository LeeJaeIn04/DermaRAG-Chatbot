from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    question: str = Field(
        ...,
        description="사용자의 질문 또는 피부 반응 설명",
        examples=["쿠션을 바꾼 뒤, 볼에 좁쌀이 올라오고 따가워요."],
    )
    skin_type: str | None = Field(
        default=None,
        description="사용자가 알고 있는 피부 타입",
        examples=["건성, 지성, 복합성, 수부지, 민감성"],
    )
    ingredient_list: str | None = Field(
        default=None,
        description="제품 전성분표",
        examples=["정제수, 티타늄디옥사이드, 글리세린, 나이아신아마이드, 향료"],
    )
    current_routine: str | None = Field(
        default=None,
        description="현재 스킴케어 루틴",
        examples=["BHA 토너를 주 3회 사용 중"],
    )

class Source(BaseModel):
    source: str
    content: str

class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]=Field(default_factory=list)