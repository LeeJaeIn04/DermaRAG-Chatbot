#!/usr/bin/env bash
set -euo pipefail

# PLAYWRIGHT_HEADLESS=false(headed Chromium)는 실제 화면 출력이
# 필요하다. GUI가 없는 Linux 컨테이너에서는 Xvfb로 가상 디스플레이를
# 띄운 뒤에만 그 상태로 앱을 실행한다 - Playwright 수집 로직이나
# 올리브영 검증 처리는 여기서 바꾸지 않는다(settings.playwright_headless
# 값을 그대로 존중할 뿐이다).
if [ "${PLAYWRIGHT_HEADLESS:-false}" = "false" ]; then
  exec xvfb-run --auto-servernum --server-args="-screen 0 1920x1080x24" "$@"
fi

exec "$@"
