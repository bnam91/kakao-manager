#!/bin/bash
# kakao_manager 안전 전송 러너 — 의존성(uv + pyobjc)을 고정해 한 줄로 실행한다.
source "$HOME/.local/bin/env" 2>/dev/null
cd "$(dirname "$0")" || exit 1
exec uv run --quiet \
  --with atomacos \
  --with pyobjc-framework-Quartz \
  --with pyobjc-framework-Cocoa \
  --with pyobjc-framework-Vision \
  --with pyobjc-framework-ApplicationServices \
  --python 3.12 python kk.py "$@"
