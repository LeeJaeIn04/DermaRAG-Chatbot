# headless A/B 테스트 결과 PLAYWRIGHT_HEADLESS=false(=headed
# Chromium)에서만 올리브영 검색/수집이 정상 동작했다. GUI가 없는
# Linux 컨테이너에서도 headed Chromium을 그대로 실행하기 위해
# Xvfb 가상 디스플레이를 쓴다(docker-entrypoint.sh). Playwright
# 수집 로직(app/products/playwright_runtime.py 등)과 올리브영 검증
# 처리는 이 이미지에서 전혀 건드리지 않는다.
FROM mcr.microsoft.com/playwright/python:v1.61.0-jammy

WORKDIR /app

# headed Chromium을 위한 가상 디스플레이.
RUN apt-get update \
    && apt-get install -y --no-install-recommends xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# app/products/playwright_runtime.py는 channel="chrome"으로
# 실행하므로(기본 Chromium이 아니다) Chrome 채널을 별도로 설치한다.
RUN uv run playwright install --with-deps chrome

COPY . .

# 로컬/배포 모두 headed Chromium을 기본으로 쓴다. 실제 값은 런타임
# 환경변수(.env 또는 오케스트레이터 설정)로 덮어쓸 수 있다.
ENV PLAYWRIGHT_HEADLESS=false

EXPOSE 8001

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
