#!/usr/bin/env python3
"""
kakao_manager send_safe — 안전 가드가 붙은 카톡 전송 래퍼

기능:
  - 텍스트 / 이미지 / 파일 전송 (모드 자동 판별)
  - (나) self-chat 검증 (--verify-me): 'badge me' AXImage 확인 후 발송
  - 채팅명 정규화: 특수문자/괄호 제거하여 재시도
  - 발송 후 row 변화 검증

Usage:
  send_safe.py "<본인표시명>" --text "메시지" --verify-me   # 표시명은 config.py --self-name
  send_safe.py "<본인표시명>" --image /path/to.png --verify-me
  send_safe.py "<본인표시명>" --file /path/to.pdf --verify-me
  send_safe.py "(채팅방) 이름" --text "안녕하세요"          # 괄호 자동 우회
"""
import argparse, json, re, subprocess, sys, time

try:
    import atomacos
except ImportError:
    print(json.dumps({"ok": False, "error": "atomacos not installed"}, ensure_ascii=False))
    sys.exit(2)

BUNDLE = "com.kakao.KakaoTalkMac"
MAIN_TITLES = ("카카오톡", "KakaoTalk")


def ascript(s):
    r = subprocess.run(["osascript", "-e", s], capture_output=True, text=True)
    return r.stdout.strip(), r.returncode


def key_code(code, mods=""):
    m = f"using {{{mods}}}" if mods else ""
    ascript(f'tell application "System Events" to key code {code} {m}')


def get_app():
    try:
        return atomacos.getAppRefByBundleId(BUNDLE)
    except Exception as e:
        return None


def find_role_all(el, role, out, depth=0, max_depth=30):
    if depth > max_depth:
        return
    try:
        if el.AXRole == role:
            out.append(el)
        for ch in (el.AXChildren or []):
            find_role_all(ch, role, out, depth + 1, max_depth)
    except Exception:
        pass


def main_window(app):
    for w in app.windows():
        try:
            if w.AXTitle in MAIN_TITLES:
                return w
        except Exception:
            pass
    return None


def find_open_chat_window(app, chat_name):
    """제목에 chat_name이 포함된 채팅창(메인 제외) 반환."""
    needle = chat_name.lower()
    for w in app.windows():
        try:
            t = w.AXTitle
        except Exception:
            t = None
        if not t or t in MAIN_TITLES:
            continue
        if needle in t.lower():
            return w
    return None


def ensure_chat_tab_simple():
    """카톡 메인창 채팅 탭으로 전환 (좌측 사이드바 좌표 클릭, atomacos walk 없음)."""
    ascript('tell application "KakaoTalk" to activate')
    time.sleep(0.4)
    ascript('tell application "System Events" to tell process "KakaoTalk" to perform action "AXRaise" of (first window whose name is "카카오톡")')
    time.sleep(0.3)
    # 채팅 탭 = 사이드바 두 번째 (좌표 (375, 223))
    ascript('tell application "System Events" to click at {375, 223}')
    time.sleep(0.7)


def is_self_chat_in_list(app, chat_name):
    """메인 채팅 목록에서 chat_name과 일치 + 'badge me' AXImage 있는 row 검증.
    반환: True(본인) / False(다른 사람) / None(검증 불가).
    """
    ensure_chat_tab_simple()
    # app 재조회 (탭 전환 후)
    app = get_app()
    main = main_window(app)
    if not main:
        return None

    needle = chat_name.lower()
    rows = []
    find_role_all(main, "AXRow", rows, max_depth=12)
    if not rows:
        return None

    for row in rows:
        sts = []
        find_role_all(row, "AXStaticText", sts, max_depth=8)
        name = None
        for s in sts:
            try:
                v = s.AXValue
                if v and len(v) > 1 and not v[0].isdigit():
                    name = v
                    break
            except Exception:
                pass
        if not name or needle not in name.lower():
            continue
        imgs = []
        find_role_all(row, "AXImage", imgs, max_depth=8)
        for im in imgs:
            try:
                if im.AXDescription == "badge me":
                    return True
            except Exception:
                pass
        return False
    return None


def normalize_chat_name(name):
    """특수문자/괄호 제거한 핵심 토큰만."""
    n = re.sub(r"\([^)]*\)", "", name)  # (xxx) 제거
    n = re.sub(r"\[[^\]]*\]", "", n)    # [xxx] 제거
    n = re.sub(r"[^\w가-힣ㄱ-ㅎㅏ-ㅣ ]", "", n)  # 한글/영문/숫자/공백만
    return n.strip()


def search_and_open(chat_name):
    """카톡 검색으로 채팅창 열기."""
    ascript('tell application "KakaoTalk" to activate')
    time.sleep(0.4)
    app = get_app()
    main = main_window(app)
    if main:
        try:
            main.Raise()
            time.sleep(0.3)
        except Exception:
            pass
    key_code(3, "command down")  # Cmd+F
    time.sleep(0.5)
    # 검색창에 이전 검색어가 남아있으면 누적되어 엉뚱한 방으로 가므로 먼저 비운다
    key_code(0, "command down")  # Cmd+A (전체 선택)
    time.sleep(0.15)
    key_code(51)  # Delete
    time.sleep(0.2)
    subprocess.run(["pbcopy"], input=chat_name.encode(), check=True)
    key_code(9, "command down")  # Cmd+V
    time.sleep(0.8)
    key_code(125)  # Down arrow
    time.sleep(0.2)
    key_code(36)   # Enter
    time.sleep(0.9)
    # 방을 연 뒤 검색창을 비워 목록 필터가 남지 않도록 한다
    clear_search_box()


def clear_search_box():
    """메인창 검색창을 비운다 (검색어 잔류로 목록이 빈 채로 남는 문제 방지).
    AXSearchField/일반 검색 텍스트필드는 클릭으로 포커스가 안 잡힐 수 있어
    AXFocused 속성을 직접 켠 뒤 Cmd+A + Delete 로 지운다."""
    ascript(
        'tell application "System Events" to tell process "KakaoTalk"\n'
        '  set w to first window whose name is "카카오톡"\n'
        '  repeat with tf in (text fields of w)\n'
        '    try\n'
        '      if (value of tf as text) is not "" then\n'
        '        set value of attribute "AXFocused" of tf to true\n'
        '        delay 0.1\n'
        '        key code 0 using {command down}\n'
        '        delay 0.1\n'
        '        key code 51\n'
        '        delay 0.1\n'
        '      end if\n'
        '    end try\n'
        '  end repeat\n'
        'end tell'
    )


def raise_chat_window(app, chat_name):
    """채팅창 raise."""
    needle = chat_name.lower()
    for w in app.windows():
        try:
            t = w.AXTitle
            if t and t not in MAIN_TITLES and needle in t.lower():
                w.Raise()
                time.sleep(0.4)
                return w
        except Exception:
            pass
    return None


def get_input_area_position(chat_win):
    """채팅창에서 입력란(가장 아래 AXTextArea) 좌표 반환."""
    tas = []
    find_role_all(chat_win, "AXTextArea", tas)
    bottoms = []
    for t in tas:
        try:
            p = t.AXPosition
            s = t.AXSize
            bottoms.append((p.y, t, p, s))
        except Exception:
            pass
    if not bottoms:
        return None
    bottoms.sort(reverse=True)
    _, _, pos, size = bottoms[0]
    return (int(pos.x + size.width / 2), int(pos.y + size.height / 2))


def focus_input(chat_win):
    """채팅창 입력란 클릭으로 포커스."""
    coord = get_input_area_position(chat_win)
    if coord:
        x, y = coord
        ascript(f'tell application "System Events" to click at {{{x}, {y}}}')
        time.sleep(0.3)
        return True
    return False


def send_text(message):
    subprocess.run(["pbcopy"], input=message.encode("utf-8"), check=True)
    time.sleep(0.2)
    key_code(9, "command down")
    time.sleep(0.4)
    key_code(36)
    time.sleep(0.4)


def send_image(path):
    ascript(f'set the clipboard to (read POSIX file "{path}" as «class PNGf»)')
    time.sleep(0.3)
    key_code(9, "command down")
    time.sleep(1.5)
    key_code(36)
    time.sleep(0.5)


def send_file(path):
    ascript(f'set the clipboard to ((POSIX file "{path}") as «class furl»)')
    time.sleep(0.3)
    key_code(9, "command down")
    time.sleep(1.5)
    key_code(36)
    time.sleep(0.5)


def count_rows(chat_win):
    rows = []
    find_role_all(chat_win, "AXRow", rows)
    return len(rows)


def run(args):
    app = get_app()
    if not app:
        return {"ok": False, "error": "KakaoTalk not running or accessibility denied"}

    # === Step 1: (나) 검증 (옵션) ===
    if args.verify_me:
        result = is_self_chat_in_list(app, args.chat)
        if result is None:
            # 정규화 후 재검증
            norm = normalize_chat_name(args.chat)
            if norm and norm != args.chat:
                result = is_self_chat_in_list(app, norm)
        if not result:
            return {"ok": False, "error": "verify-me failed: 'badge me' AXImage 없음 (본인 채팅 아님)", "chat": args.chat}

    # === Step 2: 채팅창 열기 ===
    chat_win = find_open_chat_window(app, args.chat)
    tried_norm = False
    if not chat_win:
        # 검색으로 시도
        search_and_open(args.chat)
        app = get_app()
        chat_win = find_open_chat_window(app, args.chat)
    if not chat_win:
        # 정규화 후 재시도
        norm = normalize_chat_name(args.chat)
        if norm and norm != args.chat:
            tried_norm = True
            search_and_open(norm)
            app = get_app()
            chat_win = find_open_chat_window(app, norm)
    if not chat_win:
        return {"ok": False, "error": "채팅창 못 찾음", "chat": args.chat, "tried_norm": tried_norm}

    # === Step 3: raise + focus ===
    chat_win = raise_chat_window(app, chat_win.AXTitle) or chat_win
    if not focus_input(chat_win):
        return {"ok": False, "error": "입력란 포커스 실패", "chat": chat_win.AXTitle}

    rows_before = count_rows(chat_win)

    # === Step 4: 전송 ===
    if args.text:
        send_text(args.text)
        kind = "text"
    elif args.image:
        send_image(args.image)
        kind = "image"
    elif args.file:
        send_file(args.file)
        kind = "file"
    else:
        return {"ok": False, "error": "--text/--image/--file 중 하나 필수"}

    # === Step 5: 검증 ===
    time.sleep(1.2)
    rows_after = count_rows(chat_win)
    delivered = rows_after > rows_before

    return {
        "ok": delivered,
        "kind": kind,
        "chat": chat_win.AXTitle,
        "rows_before": rows_before,
        "rows_after": rows_after,
        "tried_norm": tried_norm,
        "verified_me": args.verify_me,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("chat", help="채팅방 이름 (부분 일치)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--text", "-t", help="텍스트 메시지")
    g.add_argument("--image", "-i", help="이미지 파일 경로 (.png 권장)")
    g.add_argument("--file", "-f", help="파일 경로 (.txt/.pdf/.xlsx 등)")
    p.add_argument("--verify-me", action="store_true", help="(나) 본인 채팅인지 'badge me'로 검증 후 발송")
    p.add_argument("--json", "-j", action="store_true", help="JSON 출력")
    args = p.parse_args()

    result = run(args)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result.get("ok"):
            print(f"✓ [{result.get('chat')}] {result.get('kind')} 전송 완료 (rows {result.get('rows_before')}→{result.get('rows_after')})")
        else:
            print(f"✗ 실패: {result.get('error')}")
            sys.exit(1)


if __name__ == "__main__":
    main()
