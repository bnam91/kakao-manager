#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""챗펄스 카톡 헬퍼 — open / read / lastmsg / send  (여포 chatpulse_growtalk.py의 카톡판, 정본 정합 2026-07-15)

사용: python3 chatpulse_kakao.py <open|read|lastmsg|send> <room> ["메시지"]
- open  <room>            : open_exact로 정확오픈(오방 stop_리브리 배제) + Dock 전면화 선행 → "OPEN_OK"/에러문자열
- read  <room>            : 스레드 텍스트 전문 출력(라인 = "발신자 | 시각 | 내용")
- lastmsg <room>          : 텍스트 tail(마지막 ~600자) — 발신자 판별용(정본 lastmsg와 동형)
- send  <room> "메시지"   : 이미 열린 방 raise(재검색X=오방회피) → 붙여넣기 → Enter → 검증 → "SENT_OK"/"SENT_UNVERIFIED ..."

정본 대비: 채널만 카톡(atomacos), 계약(서브커맨드·plain text 출력)은 동일. 이모지 금지는 호출측 책임.
전면화 = Dock 아이콘 클릭(한글 "카카오톡"; activate/open -a는 다른 Space면 먹통 — notes/KNOWLEDGE.md).
자격증명 하드코딩 금지 — 카톡 데스크톱은 앱 세션 로그인이라 스크립트에 비번 불필요(계정전환은 KNOWLEDGE)."""
import sys, os, time, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _front():
    subprocess.run(["osascript", "-e",
        'tell application "System Events" to tell process "Dock" to click UI element "카카오톡" of list 1'],
        capture_output=True)
    time.sleep(1.0)


def _msgs_to_text(msgs):
    """구조화 메시지 → 정본식 텍스트. ★카드/파일 메시지는 text가 비어도 '발신자 | 시각' 라인 생성(diff 감지 유지)."""
    lines = []
    for m in msgs:
        sender = (m.get("sender") or "?").strip()
        t = (m.get("time") or "").strip()
        txt = (m.get("text") or "").strip()
        lines.append(f"{sender} | {t} | {txt}")
    return "\n".join(lines)


def read_text(room, limit=60):
    """방을 열어(이미 열려있으면 그 창) 스레드 텍스트 반환. 정본 read_thread 대응."""
    import kakao_read as K
    title, msgs = K.read_chat(room, limit)
    return title, _msgs_to_text(msgs)


def cmd_open(room):
    _front()
    r = subprocess.run(["uv", "run", "--with", "atomacos", "--with", "pyobjc-framework-Quartz",
                        "--python", "3.12", "python", os.path.join(HERE, "open_exact.py"), room],
                       capture_output=True, text=True, timeout=120)
    import json as _j
    line = [l for l in r.stdout.strip().splitlines() if l.startswith("{")]
    out = _j.loads(line[-1]) if line else {"ok": False}
    if out.get("ok"):
        return "OPEN_OK"
    return f"OPEN_FAIL: {out.get('error') or out.get('opened') or r.stdout[-160:]}"


def cmd_send(room, text):
    """이미 열린 방 raise(재검색X) → 붙여넣기 → Enter → 검증. 정본 send_msg 대응(단문 Enter; 멀티라인/링크는 사람 전송버튼 경로)."""
    _front()
    import kakao_send as S
    opened = S.open_chat(room)          # 열려있으면 raise만(오방 재검색 없음)
    if not opened:
        return f"SEND_FAIL: 방 열기 실패 {room}"
    time.sleep(0.4)
    S.type_text(text)                   # pbcopy + Cmd+V
    time.sleep(0.6)
    S.key_code(36)                      # Enter (단문 발송)
    time.sleep(1.5)
    try:
        _, txt = read_text(room, 6)
        return "SENT_OK" if text[:20] in txt else f"SENT_UNVERIFIED tail={txt[-160:]!r}"
    except Exception as e:
        return f"SENT_UNVERIFIED(read_fail: {str(e)[:80]})"


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "read"
    room = sys.argv[2] if len(sys.argv) > 2 else "리브리"
    try:
        if cmd == "open":
            print(cmd_open(room))
        elif cmd == "read":
            # ★read도 전면화 필요 — atomacos AX 트리 읽기가 KakaoTalk 비활성/타Space면 빈 결과.
            #   감지 신뢰성 우선(고객 회신 놓침 방지). 전면화 빈도는 핫모드(대화 후 ~5분)에만 집중, 이후 감쇠.
            _front(); _, txt = read_text(room, 80); print(txt)
        elif cmd == "lastmsg":
            _front(); _, txt = read_text(room, 40); print(txt[-600:])
        elif cmd == "send":
            print(cmd_send(room, sys.argv[3]))
        else:
            print(f"UNKNOWN_CMD: {cmd}"); return 2
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {str(e)[:200]}"); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
