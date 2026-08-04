# DermaRAG Frontend

React, TypeScript, Vite, Tailwind CSS로 구현한 DermaRAG 상품 성분 분석 UI입니다.

## 실행 방법

프로젝트 루트에서 백엔드를 실행합니다.

```bash
uv run uvicorn app.main:app --reload --port 8001
```

다른 터미널에서 프론트엔드를 실행합니다.

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

기본 프론트엔드 주소는 `http://localhost:5173`, 백엔드 주소는
`http://127.0.0.1:8001`입니다.

백엔드 주소가 다르면 `.env`의 값을 변경합니다.

```env
VITE_API_BASE_URL=http://127.0.0.1:8001
```

## 검증

```bash
npm run lint
npm run build
```

실제 상품 분석은 백엔드의 Playwright 브라우저 실행 환경과 Gemini API 설정이
필요합니다. 상품 후보 검색은 현재 백엔드의 Mock Provider 결과를 사용합니다.
