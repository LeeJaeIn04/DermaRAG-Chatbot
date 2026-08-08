# DermaRAG AWS EC2 배포 및 트러블슈팅 정리

> 이 문서는 DermaRAG를 AWS EC2에 수동 배포하면서 진행한 작업과 주요 트러블슈팅을 정리한 문서입니다.  
> 현재 배포는 **React + Nginx + Dockerized FastAPI + SQLite + Chroma Vectorstore** 구조로 동작하며, 캐시된 상품에 대해서는 상품 검색부터 옵션 선택, 성분 분석, RAG 응답 생성까지 전체 E2E 흐름을 검증했습니다.

---

## 1. 배포 목표

DermaRAG는 로컬 개발 환경에서 다음 기능을 제공하고 있었습니다.

- 올리브영 상품 검색
- 상품 옵션 선택
- 옵션별 전성분 수집 및 SQLite 캐싱
- 성분/규제 문서 검색
- 피부 프로필 기반 성분 적합성 분석
- Chroma 기반 RAG 검색
- LLM 기반 최종 분석 응답 생성
- React 기반 사용자 인터페이스

이번 배포에서는 위 기능을 AWS EC2에서 실행하고, 외부 사용자가 브라우저를 통해 React 화면에 접속하여 실제 분석까지 수행할 수 있도록 구성했습니다.

---

## 2. 최종 배포 구조

```text
사용자 브라우저
        |
        | HTTP :80
        v
+----------------------+
|        Nginx         |
|----------------------|
| /        -> React    |
| /api/*   -> FastAPI  |
+----------+-----------+
           |
           | 127.0.0.1:8001
           v
+----------------------+
| Dockerized FastAPI   |
|----------------------|
| Product API          |
| SQLite Cache         |
| RAG / LLM            |
+----------+-----------+
           |
     +-----+------+
     |            |
     v            v
 SQLite        Chroma
derma_rag.db   vectorstore
```

외부에서는 Nginx의 80번 포트만 사용하고, FastAPI의 8001 포트는 외부에 직접 공개하지 않는 구조로 정리했습니다.

---

## 3. Docker 구성

백엔드는 Playwright 공식 Python 이미지를 기반으로 구성했습니다.

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.61.0-jammy

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

RUN uv run --no-sync playwright install --with-deps chromium

COPY . .
RUN uv sync --frozen --no-dev

ENV PLAYWRIGHT_HEADLESS=false

EXPOSE 8001

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]

CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

headed Chromium을 Linux 서버에서 실행하기 위해 `xvfb`를 사용했고, 컨테이너 실행 시 `--init` 옵션도 함께 사용했습니다.

```bash
docker run -d \
  --name derma-rag \
  --init \
  --env-file .env \
  --restart no \
  -v "$PWD/data:/app/data" \
  -v "$PWD/vectorstore:/app/vectorstore" \
  -p 8001:8001 \
  derma-rag
```

---

## 4. AWS EC2 구성

AWS 서울 리전에 Ubuntu EC2 인스턴스를 생성했습니다.

배포 당시 주요 구성은 다음과 같습니다.

- OS: Ubuntu 24.04
- Architecture: amd64
- Instance: `c7i-flex.large`
- vCPU: 2
- Memory: 4 GiB
- Storage: gp3 30 GiB
- Region: `ap-northeast-2`

GitHub에서 프로젝트를 clone한 뒤 Docker를 설치하고 이미지를 서버에서 직접 빌드하는 **수동 배포 방식**을 사용했습니다.

```bash
git clone <repository-url>
cd DermaRAG-Chatbot

sudo apt update
sudo apt install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```
---

## 5. 트러블슈팅 1 - Docker 빌드 중 디스크 부족

### 문제

EC2에서 Docker 이미지를 빌드하는 과정에서 다음 오류가 발생했습니다.

```text
no space left on device
```

특히 Python/ML 관련 의존성과 Docker layer가 쌓이면서 초기 20 GiB 루트 볼륨으로는 빌드가 완료되지 않았습니다.

### 해결

먼저 불필요한 Docker layer를 정리했습니다.

```bash
docker system prune -a -f
```

하지만 다시 빌드해도 저장 공간이 부족해 EBS 볼륨을 20 GiB에서 30 GiB로 확장했습니다.

AWS 콘솔에서 EBS 크기를 변경한 뒤 EC2 내부에서 파티션과 파일시스템을 확장했습니다.

```bash
sudo growpart /dev/nvme0n1 1
sudo resize2fs /dev/nvme0n1p1
```

확인:

```bash
df -h /
```

약 29 GiB의 루트 파일시스템이 확보된 뒤 Docker 이미지 빌드에 성공했습니다.

---

## 6. Chroma Vectorstore 배포

로컬의 `vectorstore/`는 Git에 포함하지 않도록 관리하고 있었기 때문에 EC2에서 직접 생성했습니다.

```bash
mkdir -p vectorstore

docker run --rm \
  --init \
  --env-file .env \
  -v "$PWD/vectorstore:/app/vectorstore" \
  derma-rag \
  uv run --no-sync python -m scripts.ingest
```

생성 결과:

```text
vectorstore/chroma/chroma.sqlite3
```

컨테이너 실행 시 해당 디렉터리를 bind mount하여 컨테이너를 삭제하거나 교체해도 vectorstore가 유지되도록 했습니다.

```bash
-v "$PWD/vectorstore:/app/vectorstore"
```

---

## 7. 트러블슈팅 2 - EC2에서 올리브영 실시간 수집 실패

### 문제

백엔드와 Playwright는 정상 실행됐지만 EC2에서 `/products/search`를 호출하면 다음 오류가 발생했습니다.

```text
502 Bad Gateway
올리브영의 브라우저 확인 화면을 통과하지 못했습니다.
```

진단 로그를 임시로 추가해 실제 페이지 내용을 확인했습니다.

```python
print(
    "[oliveyoung-debug]",
    {
        "url": page.url,
        "title": page.title(),
        "body_preview": last_body_text[:500],
    },
    flush=True,
)
```

EC2에서 확인된 페이지는 상품 검색 결과가 아니라 다음과 같은 접속 확인 페이지였습니다.

```text
잠시만 기다려 주세요

안전하고 원활한 올리브영 이용을 위해
접속 정보를 확인 중이에요

RAY_ID ...
```

### 확인한 사항

- Chromium 실행 정상
- Xvfb 실행 정상
- `PLAYWRIGHT_HEADLESS=false` 적용 정상
- 올리브영 URL까지 네트워크 접근 정상
- FastAPI와 Docker 실행 정상
- 상품 페이지 대신 접속 확인 페이지가 반환됨

즉 문제는 Docker나 FastAPI 자체의 실패가 아니라 **EC2 환경에서 올리브영 실시간 수집 경로가 접속 확인 단계에 걸리는 문제**였습니다.

### 대응

사이트의 접속 제어를 우회하는 방향으로 변경하지 않고, 기존 프로젝트의 **SQLite 캐시 구조를 활용하여 수집과 서비스 제공을 분리**했습니다.

```text
Mac 로컬
Playwright 상품 수집
        |
        v
SQLite Cache
        |
        | DB 파일 배포
        v
AWS EC2
캐시 기반 검색/옵션/분석
```

이 구조를 통해 EC2에서 실시간 수집이 불가능한 상황에서도 미리 수집한 상품은 정상적으로 서비스할 수 있게 했습니다.

---

## 8. SQLite 상품 캐시 배포

애플리케이션의 기본 SQLite 경로는 다음과 같습니다.

```python
database_url = "sqlite:///./data/derma_rag.db"
```

로컬 DB에는 실제 상품 및 성분 데이터가 저장되어 있었습니다.

예:

```text
products                      30
product_search_results        30
product_collection_states      2
product_ingredient_records     6
product_ingredient_items    1002
```

SQLite는 WAL 모드를 사용할 수 있으므로 `.db` 파일만 복사하기 전에 `.backup` 명령을 사용하여 배포용 단일 DB 파일을 만들었습니다.

```bash
sqlite3 data/derma_rag.db \
  ".backup 'data/derma_rag_deploy.db'"
```

이후 Mac에서 EC2로 복사했습니다.

```bash
scp -i ~/Downloads/derma-rag-key.pem \
  ~/Documents/DermaRAG-Chatbot/data/derma_rag_deploy.db \
  ubuntu@<EC2_PUBLIC_IP>:/home/ubuntu/DermaRAG-Chatbot/data/derma_rag.db
```

Docker 실행 시 EC2의 `data` 디렉터리를 `/app/data`에 mount했습니다.

```bash
-v "$PWD/data:/app/data"
```

컨테이너 내부에서 실제 데이터를 확인했습니다.

```text
products: 30
ingredient_items: 1002
```

---

## 9. 캐시 기반 백엔드 E2E 검증

SQLite 캐시를 연결한 뒤 실제 API 흐름을 검증했습니다.

### 상품 검색

캐시된 상품 검색 시:

```text
source: sqlite_product_cache
```

가 반환되어 실시간 Playwright 실행 없이 검색 결과가 제공되는 것을 확인했습니다.

### 상품/옵션 선택

`/products/select`에서 다음 상태를 확인했습니다.

```text
mapping_status: matched
mapping_confidence: 1
status: ready
analysis_available: true
can_analyze: true
collection_status: ready
```

### 상품 분석

`/products/analyze`까지 호출하여 다음 항목을 확인했습니다.

```text
ingredient_count: 25
selected_option_name: 02 웻 로즈
option_specific_ingredients: true

cache_hit: true
cache_expired: false
extraction_performed: false

retrieved_doc_count: 10
exact_match_count: 10
used_rag_context: true
```

규제 데이터와 피부 프로필 기반 분석, RAG 문서 검색, LLM 최종 답변까지 모두 정상 동작했습니다.

---

## 10. React 프론트엔드 배포

프론트엔드는 Vite 기반 React 프로젝트입니다.

기존 API 기본 주소는 로컬 개발용으로 설정되어 있었습니다.

```ts
const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8001"
).replace(/\/+$/, "");
```

배포 환경에서는 Nginx reverse proxy를 사용하기 위해 다음 production 환경변수를 설정했습니다.

```env
VITE_API_BASE_URL=/api
```

이렇게 하면 React에서:

```text
/api/products/search
```

형태로 요청하고 Nginx가 이를 FastAPI로 전달합니다.

---


```text
oxide
```

만 존재했고 Linux x64용 native binding이 없었습니다.

설치된 oxide 버전:

```text
4.3.3
```

---

## 11. Nginx 구성

React production build 결과를 Nginx 정적 파일 디렉터리로 복사했습니다.

```bash
sudo mkdir -p /var/www/dermarag
sudo cp -r frontend/dist/* /var/www/dermarag/
```

Nginx 설정:

```nginx
server {
    listen 80;
    server_name _;

    root /var/www/dermarag;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8001/;

        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

설정 검증:

```bash
sudo nginx -t
```

```text
syntax is ok
test is successful
```

FastAPI proxy도 확인했습니다.

```bash
curl -s -o /dev/null \
  -w "%{http_code}\n" \
  http://127.0.0.1/api/docs
```

```text
200
```
---

## 12. 보안 그룹 정리

최종 서비스 구조에서는 FastAPI의 8001 포트를 외부에 직접 공개할 필요가 없습니다.

최종 인바운드 규칙은 다음과 같이 정리했습니다.

```text
SSH   TCP 22   -> 현재 개발자 IP /32
HTTP  TCP 80   -> 0.0.0.0/0
```

기존 외부 `8001` 허용 규칙은 삭제했습니다.

브라우저의 모든 API 요청은 다음 경로로 전달됩니다.

```text
Browser
  |
  | :80
  v
Nginx
  |
  | /api/*
  v
127.0.0.1:8001
  |
  v
FastAPI
```

이를 통해 FastAPI를 직접 인터넷에 노출하지 않고 Nginx를 단일 진입점으로 사용했습니다.

---

## 13. 최종 E2E 검증 결과

실제 React UI에서 다음 흐름을 최종 검증했습니다.

```text
상품 검색
   |
   v
상품 선택
   |
   v
옵션 선택
   |
   v
옵션별 전성분 조회
   |
   v
SQLite Cache
   |
   v
성분 / 피부 적합성 / 규제 분석
   |
   v
Chroma RAG 검색
   |
   v
LLM 응답 생성
   |
   v
React 화면에 분석 결과 출력
```

검증 결과:

- React 외부 접속 성공
- Nginx static serving 성공
- Nginx `/api` reverse proxy 성공
- Dockerized FastAPI 실행 성공
- SQLite 상품 캐시 조회 성공
- 상품 옵션 선택 성공
- 옵션별 전성분 조회 성공
- 피부 프로필 기반 분석 성공
- MFDS 규제 데이터 조회 성공
- Chroma RAG 검색 성공
- LLM 분석 답변 생성 성공
- React UI 최종 결과 표시 성공

따라서 **캐시된 상품을 기준으로 프론트엔드부터 RAG/LLM 응답까지 전체 배포 E2E 흐름이 정상 동작함을 확인했습니다.**

---

## 14. 상품 캐시 갱신 방법

Mac 로컬에서 필요한 상품을 추가 수집한 뒤 배포용 DB를 만듭니다.

```bash
sqlite3 data/derma_rag.db \
  ".backup 'data/derma_rag_deploy.db'"
```

EC2 컨테이너를 잠시 중지합니다.

```bash
docker stop derma-rag
```

Mac에서 새 DB를 EC2로 전송합니다.

```bash
scp -i ~/Downloads/derma-rag-key.pem \
  ~/Documents/DermaRAG-Chatbot/data/derma_rag_deploy.db \
  ubuntu@<EC2_PUBLIC_IP>:/home/ubuntu/DermaRAG-Chatbot/data/derma_rag.db
```

다시 실행합니다.

```bash
docker start derma-rag
```

`data` 디렉터리를 bind mount하고 있기 때문에 **Docker 이미지를 다시 빌드하거나 Chroma vectorstore를 다시 생성할 필요는 없습니다.**

---

## 15. 배포 과정 주요 트러블슈팅 요약

| 문제 | 원인/상황 | 해결 |
|---|---|---|
| Playwright Chrome 의존성 | 서버 환경에서 로컬 Chrome 직접 사용이 부적합 | Playwright Chromium으로 통일 |
| Linux headed 실행 | GUI가 없는 서버 | Xvfb 사용 |
| Docker build disk 부족 | 20 GiB EBS에 Docker layer/의존성 누적 | EBS 30 GiB 확장 |
| Vectorstore 미존재 | Git에서 vectorstore 제외 | EC2에서 ingest 실행 |
| SQLite 데이터 미존재 | DB가 Git에서 제외 | 로컬 DB `.backup` 후 EC2 배포 |
| EC2 실시간 상품 수집 실패 | 접속 확인 페이지 반환 | 수집과 캐시 기반 serving 분리 |
| Tailwind build 실패 | Linux native optional dependency 누락 | oxide Linux x64 binding 추가 |
| React 검색 동작 중단 | HTTP 환경에서 `crypto.randomUUID()` 호출 실패 | feature detection + fallback |
| Frontend/Backend origin 분리 | React와 FastAPI 포트가 다름 | Nginx `/api` reverse proxy |
| FastAPI 직접 노출 | 초기 8001 외부 허용 | 8001 제거, Nginx 단일 진입점 |
