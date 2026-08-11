#!/usr/bin/env python3
"""ensure_room(title) — 창 상태가 무너져 있어도 대상 대화방을 «무인»으로 복구해 올린다.

복구 순서: 앱 실행 → 로그인 → 방 창 확보(검색) → 최소화 해제 → 화면 안으로 이동/축소 → 활성화 → 🔴제목 정확일치 검증
"""
import json
import subprocess
import sys
import time

import atomacos
import kklib as K

BUNDLE = "com.kakao.KakaoTalkMac"
LOG = []


def log(m):
    LOG.append(m)
    print(f"  · {m}", flush=True)


def running():
    r = subprocess.run(["pgrep", "-x", "KakaoTalk"], capture_output=True, text=True)
    return r.returncode == 0


def visible_frame():
    """메뉴바/Dock 을 뺀 사용가능 영역 (top-left 원점, 논리 포인트)."""
    from AppKit import NSScreen
    scr = NSScreen.mainScreen()
    full = scr.frame()
    vis = scr.visibleFrame()
    # NSScreen 은 bottom-left 원점 → AX 의 top-left 원점으로 변환
    top = full.size.height - (vis.origin.y + vis.size.height)
    return {"x": vis.origin.x, "y": top, "w": vis.size.width, "h": vis.size.height}


def wins():
    try:
        return K.app().windows()
    except SystemExit:
        return []


def titles():
    return [K.g(w, "AXTitle") for w in wins()]


def ensure_running(timeout=40):
    if not running():
        log("카톡 미실행 → open -a KakaoTalk")
        subprocess.run(["open", "-a", "KakaoTalk"], check=True)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if running():
            try:
                K._APP = None
                if wins():
                    return True
            except Exception:
                pass
        time.sleep(1.0)
    return running()


def ensure_logged_in(timeout=90):
    t = titles()
    if "로그인" not in t:
        return True
    log("로그인 창 감지 → config 자격증명으로 자동 로그인")
    env = subprocess.run(
        ["python3", "-c",
         "import sys;sys.path.insert(0,'/Users/a1/.claude/skills/kakao_manager/scripts');"
         "import config;print(config.login_env())"],
        capture_output=True, text=True)
    script = subprocess.run(
        ["python3", "/Users/a1/.claude/skills/kakao_manager/scripts/config.py", "--login-env"],
        capture_output=True, text=True).stdout
    kid = kpw = None
    for line in script.splitlines():
        if line.startswith("export KAKAO_ID="):
            kid = line.split("=", 1)[1].strip().strip("'\"")
        if line.startswith("export KAKAO_PW="):
            kpw = line.split("=", 1)[1].strip().strip("'\"")
    if not kid or not kpw:
        raise SystemExit("[STOP] 자격증명 없음 — 수동 로그인 필요")
    K.osa(f'''
    tell application "KakaoTalk" to activate
    delay 0.8
    tell application "System Events" to tell process "KakaoTalk"
      set frontmost to true
      delay 0.4
      set lw to (first window whose name is "로그인")
      perform action "AXRaise" of lw
      delay 0.4
      try
        if (value of checkbox "자동 로그인" of lw) is 0 then click checkbox "자동 로그인" of lw
      end try
      delay 0.2
      set value of text field 1 of lw to "{kid}"
      delay 0.3
      set value of attribute "AXFocused" of text field 2 of lw to true
      delay 0.3
      keystroke "{kpw}"
      delay 0.4
      perform action "AXPress" of button "로그인" of lw
    end tell''')
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(2.0)
        K._APP = None
        if "로그인" not in titles():
            log("로그인 완료")
            return True
    return False


def main_window():
    return next((w for w in wins() if K.g(w, "AXTitle") in K.MAIN_TITLES), None)


def menu_item(menu_title, item_title):
    """앱 메뉴바 항목을 «객체»로 찾는다 (좌표·단축키 없이 확정적으로 누르기 위함)."""
    for ch in K.g(K.app(), "AXChildren") or []:
        if K.g(ch, "AXRole") != "AXMenuBar":
            continue
        for m in K.g(ch, "AXChildren") or []:
            if K.g(m, "AXTitle") != menu_title:
                continue
            for sub in K.g(m, "AXChildren") or []:
                for it in K.g(sub, "AXChildren") or []:
                    if K.g(it, "AXTitle") == item_title:
                        return it
    return None


def ensure_main_window(timeout=25):
    """메인 목록창 복원. ★타 방 오염검사에 필수.
    ⚠️`open -a KakaoTalk` 는 이미 실행중인 앱의 «닫힌 목록창»을 되살리지 못한다 → 「창 > 채팅」 메뉴를 쓴다."""
    if main_window() is not None:
        return main_window()
    log("메인 목록창 없음 → 「창 > 채팅」 메뉴로 복원")
    K.osa('tell application "KakaoTalk" to activate')
    time.sleep(0.6)
    for item in ("채팅", "친구"):
        it = menu_item("창", item)
        if it is None:
            continue
        try:
            it.Press()
        except Exception:
            pass
        t0 = time.time()
        while time.time() - t0 < 8:
            time.sleep(0.7)
            K._APP = None
            if main_window() is not None:
                log(f"「창 > {item}」 으로 목록창 복원됨")
                return main_window()
    subprocess.run(["open", "-a", "KakaoTalk"], check=True)
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(1.0)
        K._APP = None
        if main_window() is not None:
            return main_window()
    # Dock 아이콘 클릭 폴백
    try:
        K.osa('tell application "System Events" to tell process "Dock" to click UI element "카카오톡" of list 1')
        time.sleep(2.0)
    except Exception:
        pass
    return main_window()


def unminimize(w):
    try:
        if K.g(w, "AXMinimized"):
            log("최소화 상태 → 복원")
            K.osa(f'tell application "System Events" to tell process "KakaoTalk" to '
                  f'set value of attribute "AXMinimized" of (first window whose name is "{K.g(w,"AXTitle")}") to false')
            time.sleep(1.5)
            return True
    except Exception:
        pass
    return False


def fit_on_screen(title):
    """창이 화면 밖으로 걸쳐 있으면 «전체가 보이도록» 크기·위치를 보정한다."""
    vf = visible_frame()
    w = K.find_room(title)
    if w is None:
        return False
    p, s = K.g(w, "AXPosition"), K.g(w, "AXSize")
    W, H = s.width, s.height
    newW, newH = min(W, vf["w"]), min(H, vf["h"])
    x, y = p.x, p.y
    nx = min(max(x, vf["x"]), vf["x"] + vf["w"] - newW)
    ny = min(max(y, vf["y"]), vf["y"] + vf["h"] - newH)
    if (abs(nx - x) < 1 and abs(ny - y) < 1 and abs(newW - W) < 1 and abs(newH - H) < 1):
        return False
    log(f"화면 밖 걸침 보정: pos({int(x)},{int(y)})→({int(nx)},{int(ny)}) size({int(W)}x{int(H)})→({int(newW)}x{int(newH)})")
    if newW != W or newH != H:
        K.osa(f'tell application "System Events" to tell process "KakaoTalk" to '
              f'set size of (first window whose name is "{title}") to {{{int(newW)}, {int(newH)}}}')
        time.sleep(0.6)
    K.osa(f'tell application "System Events" to tell process "KakaoTalk" to '
          f'set position of (first window whose name is "{title}") to {{{int(nx)}, {int(ny)}}}')
    time.sleep(0.8)
    return True


def open_room_by_search(title, timeout=25):
    """메인창 채팅탭에서 정확 제목으로 검색해 방을 연다. 다른 방이 열리면 즉시 정지."""
    m = ensure_main_window()
    if m is None:
        raise SystemExit("[STOP] 메인 목록창 복원 실패 — 사람 개입 필요")
    before = {t for t in titles() if t not in K.MAIN_TITLES}
    K.osa('tell application "KakaoTalk" to activate')
    time.sleep(0.8)
    try:
        m.Raise()
    except Exception:
        pass
    time.sleep(0.6)
    K.key(19, "command down")   # Cmd+2 채팅 탭
    time.sleep(0.8)
    K.key(3, "command down")    # Cmd+F
    time.sleep(1.0)
    subprocess.run(["pbcopy"], input=title.encode(), check=True)
    K.key(9, "command down")
    time.sleep(1.6)
    K.key(125)
    time.sleep(0.4)
    K.key(36)
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(1.0)
        K._APP = None
        now = {t for t in titles() if t not in K.MAIN_TITLES}
        new = now - before
        if title in now:
            if new and new != {title}:
                raise SystemExit(f"[STOP] 의도치 않은 방이 함께 열림: {new}")
            log(f"검색으로 '{title}' 방 오픈")
            return True
        if new:
            raise SystemExit(f"[STOP] 다른 방이 열림: {new} — 전송 금지, 정지")
    raise SystemExit(f"[STOP] '{title}' 방 오픈 실패 (열린 방={titles()})")


_SEARCH_FIELD = None


def clear_search():
    """검색바 비우기. ★요소를 캐시해 매번 메인창 전체를 훑지 않는다(속도 병목이었음)."""
    global _SEARCH_FIELD
    if _SEARCH_FIELD is not None:
        try:
            v = K.g(_SEARCH_FIELD, "AXValue")
            if isinstance(v, str) and v:
                _SEARCH_FIELD.AXValue = ""
            return True
        except Exception:
            _SEARCH_FIELD = None

    m = main_window()
    if m is None:
        return False

    def rec(el, d=0):
        global _SEARCH_FIELD
        if d > 8:
            return False
        if K.g(el, "AXRole") == "AXTextField":
            v = K.g(el, "AXValue")
            if isinstance(v, str):
                _SEARCH_FIELD = el
                if v:
                    try:
                        el.AXValue = ""
                    except Exception:
                        return False
                return True
        for k in K.g(el, "AXChildren") or []:
            if rec(k, d + 1):
                return True
        return False

    return rec(m)


def ensure_room(title, do_clear_search=True):
    """🔴 전송·삭제 직전에 반드시 호출. 실패 시 SystemExit 로 정지."""
    t0 = time.time()
    if not ensure_running():
        raise SystemExit("[STOP] 카카오톡 실행 실패")
    K._APP = None
    if not ensure_logged_in():
        raise SystemExit("[STOP] 로그인 실패 — 사람 개입 필요")

    if main_window() is None:          # ★타 방 오염검사에 목록창이 필요하다
        log("메인 목록창 없음 → 복원")
        ensure_main_window()

    w = K.find_room(title)
    if w is None:
        log(f"'{title}' 창 없음 → 검색으로 오픈")
        open_room_by_search(title)
        if do_clear_search:
            clear_search()
        w = K.find_room(title)
    if w is None:
        raise SystemExit(f"[STOP] '{title}' 창 확보 실패")

    unminimize(w)
    fit_on_screen(title)

    K.osa('tell application "KakaoTalk" to activate')
    time.sleep(0.8)
    w = K.find_room(title)
    try:
        w.Raise()
    except Exception:
        pass
    time.sleep(0.8)

    # 🔴 최종 가드
    g = K.assert_room(title, "ensure_room")
    p, s = K.g(g, "AXPosition"), K.g(g, "AXSize")
    vf = visible_frame()
    inside = (p.x >= vf["x"] - 1 and p.y >= vf["y"] - 1
              and p.x + s.width <= vf["x"] + vf["w"] + 1
              and p.y + s.height <= vf["y"] + vf["h"] + 1)
    if not inside:
        raise SystemExit(f"[STOP] 창이 여전히 화면 밖: pos={p} size={s} visible={vf}")
    log(f"준비완료 ({time.time()-t0:.1f}s) pos=({int(p.x)},{int(p.y)}) size=({int(s.width)}x{int(s.height)})")
    return g


if __name__ == "__main__":
    room = sys.argv[1] if len(sys.argv) > 1 else "신현빈"
    ensure_room(room)
    print(json.dumps({"ok": True, "room": room, "steps": LOG,
                      "windows": titles()}, ensure_ascii=False, indent=1))
