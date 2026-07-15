#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""챗펄스 폴러 — 카톡 (여포 chatpulse_poller.py의 카톡판, 정본 정합 2026-07-15)

감쇠 스케줄(정본 동일): 마지막 대화 후 0~5분=30초 / 5~30분=10분 / 30분~=1시간(야간 22~09시는 담날 09시까지 sleep).
새 메시지 감지(스레드 텍스트 변화) → 새 내용 출력 + exit 0. 오류 exit 2. 8시간 하트비트 exit 3.
※카톡은 채팅만 감시(그로우톡의 주문상태 감시는 해당 없음). read는 전면화 내장, 빈 결과일 때만 재오픈 복구.

사용: python3 chatpulse_poller_kakao.py --room "리브리" [--last-activity "2026-07-15T12:22:00"]
자격증명 하드코딩 금지(카톡 데스크톱 앱 세션이라 비번 불필요). run_in_background로 띄우고 exit 시 에이전트 재기동."""
import sys, os, time, subprocess
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
HEARTBEAT_HOURS = 8


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _cp(sub, room, *extra):
    """chatpulse_kakao.py 호출 → stdout 텍스트. atomacos 필요하므로 uv로 실행."""
    r = subprocess.run(["uv", "run", "--with", "atomacos", "--with", "pyobjc-framework-Quartz",
                        "--python", "3.12", "python", os.path.join(HERE, "chatpulse_kakao.py"),
                        sub, room, *extra],
                       capture_output=True, text=True, timeout=150)
    out = r.stdout.strip()
    if r.returncode != 0 or out.startswith(("ERROR", "OPEN_FAIL", "SEND_FAIL")):
        raise RuntimeError(out[-200:] or (r.stderr or "no output")[-200:])
    return out


def read_thread_text(room):
    """스레드 텍스트. read가 내부에서 전면화(read의 _front). ★빈 결과일 때만 재오픈 복구
    (이미 열린 창은 open_exact 재실행이 오히려 상태를 흐트려 빈값 유발 — 방치 open 금지)."""
    txt = _cp("read", room)
    if not txt.strip():
        log("read empty → 재오픈 복구 시도")
        try:
            _cp("open", room)
        except Exception as e:
            log(f"reopen warn: {e}")
        txt = _cp("read", room)
    return txt


def interval_for(elapsed_sec, now):
    if elapsed_sec < 300:
        return 30
    if elapsed_sec < 1800:
        return 600
    # 1시간 모드 + 야간(22~09) → 담날 09시까지 대기 (정본 동일)
    if now.hour >= 22 or now.hour < 9:
        resume = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now.hour >= 9:
            resume += timedelta(days=1)
        return max(60, int((resume - now).total_seconds()))
    return 3600


def main():
    room = "리브리"
    last_activity = time.time()
    for i, a in enumerate(sys.argv):
        if a == "--room" and i + 1 < len(sys.argv):
            room = sys.argv[i + 1]
        if a == "--last-activity" and i + 1 < len(sys.argv):
            last_activity = datetime.fromisoformat(sys.argv[i + 1]).timestamp()

    try:
        baseline = read_thread_text(room)
    except Exception as e:
        print(f"ERROR baseline: {e}", flush=True); sys.exit(2)
    log(f"baseline {len(baseline)} chars, room={room}, "
        f"last_activity={datetime.fromtimestamp(last_activity).strftime('%H:%M')}")

    started = time.time()
    while True:
        now = datetime.now()
        elapsed = time.time() - last_activity
        iv = interval_for(elapsed, now)
        if iv >= 3600:
            log(f"sleep {iv}s (cold/night)")
        time.sleep(iv)

        if time.time() - started > HEARTBEAT_HOURS * 3600:
            print("HEARTBEAT: no new message, restart me", flush=True); sys.exit(3)

        try:
            cur = read_thread_text(room)
        except Exception as e:
            print(f"ERROR poll: {e}", flush=True); sys.exit(2)

        if cur != baseline:
            new_part = cur[len(baseline):] if cur.startswith(baseline) else cur[-800:]
            print("NEW_MESSAGE:", flush=True)
            print(new_part.strip()[-800:], flush=True)
            sys.exit(0)


if __name__ == "__main__":
    main()
