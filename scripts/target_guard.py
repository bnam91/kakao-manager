#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""오발송 방지 공용 가드 (kakao_manager 전역).

원칙 — 「조용한 폴백 금지」(~/.claude/org/wiki/ops/no-silent-fallback-on-target-mismatch.md):
  1. 대상을 지정했는데 못 찾으면 **예외를 던지고 중단**한다. 가장 비슷한 것·첫 번째 것으로 대체하지 않는다.
  2. 후보가 2개 이상이면 고르지 말고 **모호(ambiguous)로 중단**한다 — 사람이 정확한 이름을 다시 준다.
  3. 발송 직전 대상을 **재확인**한다(찾은 시점과 쓰는 시점 사이에 창이 바뀔 수 있다).
  4. 실패는 시끄럽게. 조용한 폴백은 로그상 성공으로 보여 육안 검수 전까지 안 잡힌다.

사건 기록(2026-08-05, 김민재): kakao_read 검색은 결과 목록에서 Down+Enter로 **첫 줄을 무조건** 열었다.
"신현빈"을 요청했는데 「고야태스크」방이 열렸다. 읽기라 피해는 없었지만, 같은 구조가 send 경로에도 있었다.

매칭 tier (엄격 → 느슨):
  0 = 제목 완전일치
  1 = 정규화(괄호/대괄호/기호 제거, 소문자) 일치
  2 = 타깃 + 인원수 꼬리표 (예: "방이름 (9)")
  3 = 부분일치 **단, 후보가 정확히 1개일 때만** (읽기 전용에서만 허용)

발송 경로는 max_tier=2 (부분일치 금지). 읽기 경로는 max_tier=3.
"""
import re

MAIN_TITLES = ("카카오톡", "KakaoTalk")


class TargetMismatch(RuntimeError):
    """대상 불일치/모호/부재 — 대체하지 말고 중단."""


def normalize(s):
    """괄호·대괄호·특수문자 제거 후 소문자."""
    if not s:
        return ""
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"\[[^\]]*\]", "", s)
    s = re.sub(r"[^\w가-힣ㄱ-ㅎㅏ-ㅣ]", "", s)
    return s.strip().lower()


_COUNT_SUFFIX = re.compile(r"^\s*[\(\[]\s*\d+\s*[\)\]]\s*$")


def tier_of(title, target):
    """title이 target에 얼마나 엄격하게 맞는지. 안 맞으면 None."""
    if not title or not target:
        return None
    if title == target:
        return 0
    nt, ng = normalize(title), normalize(target)
    if nt and ng and nt == ng:
        return 1
    if title.startswith(target) and _COUNT_SUFFIX.match(title[len(target):]):
        return 2
    if ng and ng in nt:
        return 3
    return None


def pick(items, target, title_of=lambda x: x, max_tier=2, what="대상"):
    """**정확히 1개**로 확정될 때만 반환. 0개 → 부재 중단 / 2개 이상 → 모호 중단.
    ★어떤 경우에도 '첫 번째 것'·'가장 비슷한 것'을 반환하지 않는다.

    확정 규칙:
      - tier0(완전일치)가 1개면 그것이 이긴다. (사용자가 정확한 이름을 줬다)
      - tier0가 없으면 tier1~max_tier 후보를 **전부 합쳐서** 1개일 때만 통과.
        (tier가 엄격한 쪽이 조용히 이기면 안 된다 — 예: "고야" 요청에 정규화가
         「[세무관련] 고야」를 집어가고 「고야태스크」가 묻히는 사고)"""
    titles = []
    exact, loose = [], []
    for it in items:
        t = title_of(it)
        if t in MAIN_TITLES:
            continue
        titles.append(t)
        k = tier_of(t, target)
        if k is None:
            continue
        # ★모호 판정은 **항상 가장 느슨한 tier까지** 훑는다.
        #   max_tier로 후보를 먼저 잘라내면, 잘린 쪽에 진짜 의도한 방이 있어도 안 보이고
        #   남은 하나가 조용히 확정된다(예: "고야" → 「고야태스크」가 잘리고 「[세무관련] 고야」 확정).
        (exact if k == 0 else loose).append((k, it))

    if len(exact) == 1:
        return exact[0][1]
    if len(exact) > 1:
        raise TargetMismatch(
            f"★중단: {what} '{target}' 완전일치가 {len(exact)}개입니다 — 고르지 않습니다.")

    cands = loose
    if len(cands) == 1:
        k, it = cands[0]
        if k > max_tier:
            raise TargetMismatch(
                f"★중단: {what} '{target}' 은 부분일치('{title_of(it)}')로만 걸립니다 — "
                f"이 경로(max_tier={max_tier})에서는 부분일치로 보내지 않습니다. "
                f"정확한 방 이름을 지정하세요(config.py --resolve 사용)."
            )
        return it
    if len(cands) > 1:
        cands = [it for _k, it in cands]
        raise TargetMismatch(
            f"★중단: {what} '{target}' 후보가 {len(cands)}개로 모호합니다 — 고르지 않습니다. "
            f"후보={[title_of(c) for c in cands]}. 정확한 이름을 지정하세요."
        )
    raise TargetMismatch(
        f"★중단: {what} '{target}' 을(를) 못 찾았습니다 — 비슷한 것으로 대체하지 않습니다. "
        f"현재 목록={titles}"
    )


def assert_match(title, target, max_tier=2, what="대상"):
    """발송/입력 직전 재확인용. 안 맞으면 즉시 중단."""
    k = tier_of(title, target)
    if k is None or k > max_tier:
        raise TargetMismatch(
            f"★중단: {what} 불일치 — 기대='{target}' / 실제='{title}'. "
            f"찾은 시점과 쓰는 시점 사이에 대상이 바뀌었을 수 있습니다."
        )
    return k
