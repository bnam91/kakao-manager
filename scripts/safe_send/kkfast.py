#!/usr/bin/env python3
"""속도 개선판 안전전송 — ★검증은 그대로 유지하고 «대기 방식»만 바꾼다.
개선점
  1. 전체 row 깊은 순회 → «개수 + 마지막 N개»만 (snapshot_light)
  2. 고정 sleep → 조건 폴링 (시트 등장/소멸, 도착)
  3. 여러 건 보낼 때 ensure_room 을 1회로 묶기 (batch)
"""
import os
import time

import kklib as K
import kkensure as E
import kksafe as S
from kksafe import Abort


def poll(cond, timeout=12.0, interval=0.15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = cond()
        if v:
            return v
        time.sleep(interval)
    return None


def confirm_sheet_fast(title):
    """확인 시트의 전송 버튼을 누르고 «시트가 사라질 때까지» 폴링."""
    sheet = None
    for sh in K.sheets_of(title):
        if "파일 전송" in " ".join(K.row_text(sh)):
            sheet = sh
    if sheet is None:
        raise Abort("[STOP] 확인 시트 없음")
    btns = []

    def rec(el, d=0):
        if d > 6:
            return
        if K.g(el, "AXRole") == "AXButton":
            p, s = K.g(el, "AXPosition"), K.g(el, "AXSize")
            if p is not None and s is not None:
                btns.append((K.g(el, "AXTitle"), int(s.width), el))
        for k in K.g(el, "AXChildren") or []:
            rec(k, d + 1)

    rec(sheet)
    cands = [b for b in btns if b[0] != "취소" and b[1] >= 100]
    if len(cands) != 1:
        raise Abort(f"[STOP] 전송 버튼 후보 {len(cands)}개")
    S.guard(title, "confirm-send", require_front=False)
    try:
        cands[0][2].Press()
    except Exception:
        pass
    gone = poll(lambda: not any("파일 전송" in " ".join(K.row_text(s))
                                for s in K.sheets_of(title)), timeout=6.0)
    if not gone:
        K.click_el(cands[0][2])
        gone = poll(lambda: not any("파일 전송" in " ".join(K.row_text(s))
                                    for s in K.sheets_of(title)), timeout=6.0)
    if not gone:
        raise Abort("[STOP] 확인 시트가 닫히지 않음")


def send_file_fast(title, path, ensured=False, timing=None):
    t = timing if timing is not None else {}
    t0 = time.time()
    path = os.path.abspath(path)
    name = os.path.basename(path)
    if not os.path.exists(path):
        raise Abort(f"[STOP] 파일 없음: {path}")

    s = time.time()
    if not ensured:
        E.ensure_room(title)
    t["ensure"] = round(time.time() - s, 2)

    s = time.time()
    cl_before = S.chatlist()
    before = K.snapshot_light(title)
    t["snapshot_before"] = round(time.time() - s, 2)

    s = time.time()
    if not S.clipboard_files([path]):
        raise Abort("[STOP] 클립보드 기록 실패")
    S.select_room(title)
    w = S.guard(title, "before-paste")
    inp = S.room_input(w)
    if inp is None:
        raise Abort("[STOP] 입력창 없음")
    try:
        inp.AXFocused = True
    except Exception:
        pass
    S.guard(title, "paste")
    ok, how = S.menu_paste()
    if not ok:
        raise Abort(f"[STOP] 붙여넣기 실패: {how}")
    t["paste"] = round(time.time() - s, 2)

    s = time.time()

    def sheet_ready():
        for sh in K.sheets_of(title):
            txt = " ".join(K.row_text(sh))
            if "묶어보내기" in txt:
                b = S._find(sh, lambda e: K.g(e, "AXRole") == "AXButton" and K.g(e, "AXTitle") == "확인")
                if b is not None:
                    try:
                        b.Press()
                    except Exception:
                        K.click_el(b)
                return False
            if "파일 전송" in txt:
                return sh
        return False

    sh = poll(sheet_ready, timeout=10.0)
    t["sheet"] = round(time.time() - s, 2)
    if not sh:
        raise Abort("[STOP] 대상 창에 확인 시트가 안 뜸 — 붙여넣기 유출 의심, 정지")
    if name not in " ".join(K.row_text(sh)):
        S.cancel_sheet(title)
        raise Abort("[STOP] 확인 시트 파일명 불일치 — 취소")

    s = time.time()
    try:
        confirm_sheet_fast(title)
    except SystemExit:
        S.cancel_sheet(title)
        raise
    t["confirm"] = round(time.time() - s, 2)

    s = time.time()
    arrived = poll(lambda: K.snapshot_light(title)["count"] > before["count"], timeout=20.0, interval=0.2)
    t["wait_arrival"] = round(time.time() - s, 2)
    if not arrived:
        raise Abort("[STOP] 도착 미확인")

    s = time.time()
    after = K.snapshot_light(title)
    joined = " ".join(" ".join(x) for x in after["tail"])
    found = name in joined
    if not found and after["count"] <= before["count"]:
        raise Abort(f"[STOP] 재조회에서 '{name}' 미발견")
    cont = S.diff_chatlist(cl_before, S.chatlist(), title, payload=name)
    if not cont.get("checked"):
        raise Abort(f"[STOP] 타 방 오염검사를 못 했다({cont.get('reason')}) — "
                    f"검증 생략은 성공이 아니다. 목록창을 복구하고 재확인 필요")
    if cont.get("misdelivery"):
        raise Abort(f"[STOP] ★오발송 확정: {cont['misdelivery']}")
    fw = S.focused_window_title()
    if fw != title:
        raise Abort(f"[STOP] 전송 후 활성 방이 '{fw}'")
    t["verify"] = round(time.time() - s, 2)
    t["total"] = round(time.time() - t0, 2)
    return {"ok": True, "found_in_room": found, "rows": [before["count"], after["count"]],
            "contamination": cont, "timing": t}


def send_files_batch(title, paths):
    """여러 건 — ensure_room 1회로 묶는다 (건마다 가드/검증은 그대로)."""
    E.ensure_room(title)
    out = []
    for p in paths:
        out.append(send_file_fast(title, p, ensured=True))
    return out
