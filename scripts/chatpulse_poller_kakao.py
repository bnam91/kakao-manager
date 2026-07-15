#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""챗펄스 카톡 폴러 (여포 chatpulse_poller.py의 카톡판, 2026-07-15 신설).

맥박 스케줄(주의력 감쇠)로 카톡 방의 새 메시지를 감지 → 에이전트를 깨운다.
백그라운드(run_in_background)로 띄우고, 종료(exit)되면 하니스가 에이전트를 재기동한다.

폴러 계약(챗펄스 SKILL.md, 신규 채널 동일):
  · baseline(마지막 대화 시각 + 지문) 받아 감쇠 스케줄로 체크.
  · 상대 새 메시지 감지 → 새 내용 출력 + exit 0   (에이전트가 답장 생성·발송 후 새 baseline으로 재기동)
  · 오류(카톡 사망·읽기 불가) → 사유 출력 + exit 2
  · 장시간 무변화/야간중지 하트비트 → 상태 출력 + exit 3 (에이전트가 재시작/재스케줄 판단)

맥박:
  경과<5분 → 30초 / <30분 → 10분 / 그외 → 1시간.
  상대답장·내발신 = last_activity 리셋(→30초 모드). (내발신 감지 시 baseline 갱신하고 계속, 깨우지 않음)
  야간(22:00~09:00 KST)은 '1시간 모드'일 때만 중지 → exit 3(status=night_pause, resume_at=09:00). 뜨거우면 밤에도 계속.

사용:
  python3 chatpulse_poller_kakao.py --room "리브리" --last-activity <epoch> --last-fp <fp> [--max-run 28800]
자격증명 하드코딩 금지(env만). 카톡 데스크톱은 앱 세션이라 별도 비번 없음."""
import sys, os, json, time, argparse, subprocess
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
KST = timezone(timedelta(hours=9))


def _now_kst():
    return datetime.now(KST)


def _interval(elapsed):
    if elapsed < 300:
        return 30
    if elapsed < 1800:
        return 600
    return 3600


def _is_night(dt):
    return dt.hour >= 22 or dt.hour < 9


def _secs_to_9am(dt):
    nine = dt.replace(hour=9, minute=0, second=0, microsecond=0)
    if dt.hour >= 9:
        nine = nine + timedelta(days=1)
    return max(60, int((nine - dt).total_seconds()))


def _lastmsg(room):
    """chatpulse_kakao.py lastmsg 호출 → dict. 실패 시 {'ok':False}."""
    r = subprocess.run(["python3", os.path.join(HERE, "chatpulse_kakao.py"), "lastmsg", room],
                       capture_output=True, text=True, timeout=90)
    line = [l for l in r.stdout.strip().splitlines() if l.startswith("{")]
    if not line:
        return {"ok": False, "error": "lastmsg 출력없음:" + (r.stderr or r.stdout)[-160:]}
    return json.loads(line[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", required=True)
    ap.add_argument("--last-activity", type=float, default=None, help="마지막 대화 epoch(없으면 now)")
    ap.add_argument("--last-fp", default="", help="마지막 메시지 지문(없으면 첫 폴에서 확립)")
    ap.add_argument("--max-run", type=int, default=28800, help="하트비트 재시작 상한(기본 8h)")
    args = ap.parse_args()

    start = time.time()
    last_activity = args.last_activity if args.last_activity else start
    last_fp = args.last_fp

    # 시작 시 baseline fp 미확립이면 1회 확립(깨우지 않음)
    if not last_fp:
        lm = _lastmsg(args.room)
        if not lm.get("ok"):
            print(json.dumps({"status": "error", "error": lm.get("error")}, ensure_ascii=False)); return 2
        last_fp = lm.get("fp") or ""

    while True:
        now = time.time()
        if now - start > args.max_run:
            print(json.dumps({"status": "heartbeat", "reason": "max_run 도달 → 재시작 판단",
                              "room": args.room, "last_fp": last_fp,
                              "last_activity": last_activity}, ensure_ascii=False)); return 3

        elapsed = now - last_activity
        iv = _interval(elapsed)
        dt = _now_kst()
        if iv == 3600 and _is_night(dt):
            print(json.dumps({"status": "night_pause", "reason": "야간(22~09) 1시간모드 중지",
                              "resume_hint_sec": _secs_to_9am(dt), "resume_at": "09:00 KST",
                              "room": args.room, "last_fp": last_fp,
                              "last_activity": last_activity}, ensure_ascii=False)); return 3

        time.sleep(iv)

        lm = _lastmsg(args.room)
        if not lm.get("ok"):
            print(json.dumps({"status": "error", "error": lm.get("error"), "room": args.room},
                             ensure_ascii=False)); return 2
        fp = lm.get("fp") or ""
        if fp and fp != last_fp:
            last = lm.get("last") or {}
            last_fp = fp
            last_activity = time.time()          # 대화 발생 → 리셋(30초 모드)
            if last.get("is_mine"):
                continue                          # 내 발신 → baseline만 갱신, 깨우지 않음
            # ★상대 새 메시지 → 에이전트 기상
            print(json.dumps({"status": "new_message", "room": lm.get("room", args.room),
                              "last": last, "last_fp": last_fp,
                              "last_activity": last_activity}, ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.exit(main())
