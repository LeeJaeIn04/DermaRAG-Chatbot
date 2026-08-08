FROM mcr.microsoft.com/playwright/python:v1.61.0-jammy

WORKDIR /app

# headed Chromium을 위한 가상 디스플레이
RUN apt-get update \
    && apt-get install -y --no-install-recommends xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

# 의존성 파일과 Python 버전을 먼저 복사하여 Docker layer cache 활용
COPY pyproject.toml uv.lock .python-version ./

# 애플리케이션 소스 없이 외부 의존성만 먼저 설치
RUN uv sync --frozen --no-dev --no-install-project

# uv sync로 설치된 Playwright를 사용해 Chromium 설치
RUN uv run --no-sync playwright install --with-deps chromium

# 프로젝트 소스 복사
COPY . .

# 프로젝트 자체까지 build 시점에 최종 동기화
RUN uv sync --frozen --no-dev

ENV PLAYWRIGHT_HEADLESS=false

EXPOSE 8001

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]

# runtime에서는 dependency sync를 다시 하지 않음
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]