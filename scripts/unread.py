#!/usr/bin/env python3
"""
KakaoTalk 안읽음 총합 조회 유틸 (백그라운드, UI/스크린샷 불필요)

Dock 뱃지값(StatusLabel)을 lsappinfo 로 읽어 '전체 안읽음 합계'를 반환한다.
카톡이 포커스를 받지 않아도 즉시 동작한다.

한계: 전체 합계만 제공. 방별 분해는 불가(메시지 DB가 SQLCipher 로 암호화되어
본문/방별 카운트를 읽을 수 없음). "어느 방에 몇 개"는 채팅목록 UI(kakao_read --list)가 필요.

Usage:
    python unread.py            # 정수 한 줄 출력 (예: 29)
    python unread.py --json     # {"unread_total": 29}
"""

import argparse
import json
import re
import subprocess

KAKAO_BUNDLE_ID = "com.kakao.KakaoTalkMac"


def unread_total() -> int:
    """카톡 Dock 뱃지의 전체 안읽음 합계. 뱃지 없으면(=안읽음 0) 0."""
    try:
        out = subprocess.run(
            ["lsappinfo", "info", "-only", "StatusLabel", "-app", KAKAO_BUNDLE_ID],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return 0
    m = re.search(r'"label"\s*=\s*"(\d+)"', out)
    return int(m.group(1)) if m else 0


def main():
    ap = argparse.ArgumentParser(description="KakaoTalk 안읽음 총합 조회")
    ap.add_argument("--json", action="store_true", help="JSON 으로 출력")
    args = ap.parse_args()

    n = unread_total()
    if args.json:
        print(json.dumps({"unread_total": n}, ensure_ascii=False))
    else:
        print(n)


if __name__ == "__main__":
    main()
