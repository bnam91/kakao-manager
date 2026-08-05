#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""target_guard 단위테스트 — 카톡 없이 돌아간다. `python3 test_target_guard.py`"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import target_guard as TG

ROOMS = [
    "고야태스크", "(3pl) 프라임컴퍼니", "[세무관련] 고야", "다산로지스_업무소통",
    "신현빈 (#VI6782)", "신현빈", "신현빈 대표님 IP_Team",
    "리브리_빈박_이민준, 현빈 업무폰", "1기 일요일반 졸업",
]

ok = fail = 0


def check(desc, fn, expect):
    """expect: ('ok', 값) | ('raise', 메시지조각)"""
    global ok, fail
    try:
        got = fn()
        if expect[0] == "ok" and got == expect[1]:
            ok += 1
            print(f"  ✅ {desc} → {got!r}")
        else:
            fail += 1
            print(f"  ❌ {desc} → {got!r} (기대={expect})")
    except TG.TargetMismatch as e:
        if expect[0] == "raise" and expect[1] in str(e):
            ok += 1
            print(f"  ✅ {desc} → 중단({expect[1]})")
        else:
            fail += 1
            print(f"  ❌ {desc} → 예외 {e} (기대={expect})")


print("=== 1) 발송 경로(max_tier=2, 부분일치 금지) ===")
# ★핵심: 발송에서 부분일치는 안 걸린다 — 정확한 이름을 요구한다
check("정확일치 '고야태스크'", lambda: TG.pick(ROOMS, "고야태스크", max_tier=2), ("ok", "고야태스크"))
# 완전일치 방이 존재하면 그게 이긴다(사용자가 정확한 이름을 준 것) — 유사 후보에 묻히지 않는다
check("'신현빈' → 완전일치 방이 이김",
      lambda: TG.pick(ROOMS, "신현빈", max_tier=2), ("ok", "신현빈"))
check("'다산' 부분일치는 발송에서 거부",
      lambda: TG.pick(ROOMS, "다산", max_tier=2), ("raise", "부분일치"))
check("없는 방", lambda: TG.pick(ROOMS, "없는방", max_tier=2), ("raise", "못 찾았습니다"))
check("인원수 꼬리표 '방A (9)'",
      lambda: TG.pick(["방A (9)", "방B"], "방A", max_tier=2), ("ok", "방A (9)"))

print("=== 2) 읽기 경로(max_tier=3, 유일할 때만 부분일치) ===")
check("'다산' → 유일하므로 허용",
      lambda: TG.pick(ROOMS, "다산", max_tier=3), ("ok", "다산로지스_업무소통"))
check("'신현빈' → 완전일치가 이김(읽기도 동일)",
      lambda: TG.pick(ROOMS, "신현빈", max_tier=3), ("ok", "신현빈"))
# ★설계 핵심: 정규화(tier1)가 조용히 이기면 안 된다 — 「[세무관련] 고야」와 「고야태스크」 둘 다 후보
check("'고야' → 고야태스크/[세무관련] 고야 → 모호중단",
      lambda: TG.pick(ROOMS, "고야", max_tier=3), ("raise", "모호"))
check("'고야' → 발송 경로에서도 모호중단",
      lambda: TG.pick(ROOMS, "고야", max_tier=2), ("raise", "모호"))

print("=== 3) 발송 직전 재확인 assert_match ===")
check("일치", lambda: TG.assert_match("고야태스크", "고야태스크", max_tier=2), ("ok", 0))
check("창이 바뀐 경우 → 중단",
      lambda: TG.assert_match("다산로지스_업무소통", "고야태스크", max_tier=2), ("raise", "불일치"))
check("None 제목 → 중단", lambda: TG.assert_match(None, "고야태스크", max_tier=2), ("raise", "불일치"))

print("=== 4) 메인창은 후보에서 제외 ===")
check("메인창만 있을 때", lambda: TG.pick(["카카오톡"], "카카오톡", max_tier=3),
      ("raise", "못 찾았습니다"))

print(f"\n결과: ✅{ok} / ❌{fail}")
sys.exit(1 if fail else 0)
