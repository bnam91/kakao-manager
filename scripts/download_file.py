#!/usr/bin/env python3
"""
KakaoTalk 수신 파일(첨부) 다운로드 유틸

채팅방에 와 있는 파일 버블(.xlsx/.pdf/.zip 등)을 ~/Downloads 로 저장한다.
파일 버블 row 안의 AXButton[AXDescription='저장'] 을 실시간 좌표로 클릭해서
받는다. 카톡 컨테이너의 Downloads 가 ~/Downloads 로 심볼릭되어 있어
'저장'(다른 이름으로 저장 아님) 은 곧바로 ~/Downloads 에 떨어진다.

전제: 대상 채팅방이 이미 열려 있고 파일 버블이 화면에 보여야 한다.
      (먼저 `kakao_read.py "방이름"` 으로 방을 열어 둘 것. 파일이 위에 있으면 스크롤 필요)

Usage:
    python download_file.py "고야태스크" "무릎보호대"          # 파일명 일부로 매칭
    python download_file.py "고야태스크" "무릎보호대" --json
    python download_file.py "고야태스크" "송장.xlsx" --dest ~/Downloads --timeout 20

종료코드: 성공 0, 실패 1.
"""

import argparse
import json
import os
import subprocess
import sys
import time

try:
    import atomacos
except ImportError:
    print("Error: atomacos not installed. Run: uv add atomacos", file=sys.stderr)
    sys.exit(1)

try:
    import Quartz
except ImportError:
    print("Error: Quartz(pyobjc) not available", file=sys.stderr)
    sys.exit(1)

BUNDLE_ID = "com.kakao.KakaoTalkMac"
DEFAULT_DEST = os.path.expanduser("~/Downloads")


def gv(el, attr):
    try:
        return getattr(el, attr)
    except Exception:
        return None


def kids(el):
    try:
        return el.AXChildren or []
    except Exception:
        return []


def walk(root):
    stack = [root]
    while stack:
        e = stack.pop()
        yield e
        stack.extend(kids(e))


def find_room_window(app, name):
    return next((w for w in app.windows() if gv(w, "AXTitle") == name), None)


def find_file_text(win, namepart):
    """파일명(부분일치) StaticText 와 그 row 를 반환. (파일명전체, text_el, row_el) 또는 (None,None,None)."""
    for e in walk(win):
        if gv(e, "AXRole") != "AXStaticText":
            continue
        v = gv(e, "AXValue")
        if not v or namepart not in v:
            continue
        row = e
        for _ in range(8):
            if row is None or gv(row, "AXRole") == "AXRow":
                break
            row = gv(row, "AXParent")
        if row is not None and gv(row, "AXRole") == "AXRow":
            return v, e, row
    return None, None, None


def find_menu_item(app, titles):
    """열린 컨텍스트 메뉴에서 제목이 titles 중 하나인 AXMenuItem 을 반환."""
    for w in app.windows():
        for e in walk(w):
            if gv(e, "AXRole") == "AXMenuItem" and gv(e, "AXTitle") in titles:
                return e
    return None


def center(el):
    p = gv(el, "AXPosition")
    s = gv(el, "AXSize")
    if p is None or s is None:
        return None
    return (float(p.x) + float(s.width) / 2.0, float(p.y) + float(s.height) / 2.0)


def click_at(x, y):
    Quartz.CGWarpMouseCursorPosition((x, y))
    pos = (x, y)
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseDown, pos, Quartz.kCGMouseButtonLeft)
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseUp, pos, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.05)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def right_click_at(x, y):
    Quartz.CGWarpMouseCursorPosition((x, y))
    pos = (x, y)
    for et in (Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp):
        Quartz.CGEventPost(
            Quartz.kCGHIDEventTap,
            Quartz.CGEventCreateMouseEvent(None, et, pos, Quartz.kCGMouseButtonRight))
        time.sleep(0.05)


def raise_room(room):
    subprocess.run(["osascript", "-e", 'tell application "KakaoTalk" to activate'],
                   capture_output=True)
    subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to tell process "KakaoTalk" to '
         f'set frontmost to true'],
        capture_output=True,
    )
    subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to tell process "KakaoTalk" to '
         f'perform action "AXRaise" of (first window whose name is "{room}")'],
        capture_output=True,
    )


def dismiss_save_dialog_if_any(app):
    """'저장' 후 이름없는 AXDialog(저장 패널)가 뜨면 Return 으로 기본 위치(=~/Downloads) 수락."""
    for w in app.windows():
        if gv(w, "AXSubrole") == "AXDialog" or gv(w, "AXRole") == "AXSheet":
            subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to key code 36'],  # Return
                capture_output=True,
            )
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description="KakaoTalk 수신 파일 다운로드")
    ap.add_argument("room", help="채팅방 이름 (이미 열려 있어야 함)")
    ap.add_argument("namepart", help="파일명 일부 (부분일치)")
    ap.add_argument("--dest", default=DEFAULT_DEST, help="저장 폴더 (기본 ~/Downloads)")
    ap.add_argument("--timeout", type=float, default=15.0, help="저장 대기 최대 초")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    dest = os.path.expanduser(args.dest)
    app = atomacos.getAppRefByBundleId(BUNDLE_ID)

    win = find_room_window(app, args.room)
    if win is None:
        return _fail(args, f"채팅방 '{args.room}' 창이 없음 — 먼저 kakao_read.py 로 방을 열 것")

    raise_room(args.room)
    time.sleep(0.5)
    # raise 후 핸들이 바뀔 수 있어 재취득
    win = find_room_window(app, args.room) or win

    fname, text_el, row = find_file_text(win, args.namepart)
    if text_el is None:
        return _fail(args, f"'{args.namepart}' 파일 버블을 못 찾음 — 방에서 해당 파일이 화면에 보이는지(스크롤) 확인")

    target_path = os.path.join(dest, fname)
    before = os.path.exists(target_path)

    # 파일 버블 footer 의 '저장' 버튼은 hover 시에만/불안정하게 나타나므로
    # 파일 버블을 우클릭해 컨텍스트 메뉴의 '저장하기' 항목을 클릭하는 안정 경로를 쓴다.
    file_pt = center(text_el)
    if file_pt is None:
        return _fail(args, "파일 버블 좌표를 못 읽음")

    item = None
    for _ in range(4):
        right_click_at(*file_pt)
        time.sleep(0.7)
        item = find_menu_item(app, ("저장하기", "저장"))
        if item is not None:
            break
    if item is None:
        # 메뉴 닫고 실패
        subprocess.run(["osascript", "-e",
                        'tell application "System Events" to key code 53'],  # Esc
                       capture_output=True)
        return _fail(args, "우클릭 컨텍스트 메뉴에서 '저장하기'를 못 찾음")

    item_pt = center(item)
    if item_pt is None:
        return _fail(args, "'저장하기' 메뉴 좌표를 못 읽음")
    click_at(*item_pt)

    # 저장 대기 (저장 패널이 뜨면 Return 으로 수락)
    deadline = time.time() + args.timeout
    saved = False
    while time.time() < deadline:
        time.sleep(0.4)
        dismiss_save_dialog_if_any(app)
        if os.path.exists(target_path):
            # before 가 True 였다면(기존 파일) 재저장 검증 위해 mtime 변화 확인은 생략, 존재로 OK
            saved = True
            break

    if not saved:
        return _fail(args, f"제한시간({args.timeout}s) 내 {target_path} 미생성 — 저장 패널 수동 확인 필요")

    size = os.path.getsize(target_path)
    if args.json:
        print(json.dumps({"ok": True, "file": fname, "path": target_path,
                          "size": size, "existed_before": before}, ensure_ascii=False))
    else:
        print(f"다운로드완료: {target_path}")
    return 0


def _fail(args, msg):
    if args.json:
        print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    else:
        print(f"실패: {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
