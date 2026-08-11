#!/usr/bin/env python3
"""카톡 실측 공용 헬퍼 — 대화방 창을 '정확 제목'으로만 잡고, 매 액션 직전 재확인한다."""
import subprocess
import time
import atomacos

BUNDLE = "com.kakao.KakaoTalkMac"
MAIN_TITLES = ("카카오톡", "KakaoTalk")


_APP = None


def app(retries: int = 6):
    """앱 참조 캐시 + 재시도. activate 직후 일시적으로 bundle 조회가 실패하는 사례 있음."""
    global _APP
    if _APP is not None:
        try:
            _APP.windows()
            return _APP
        except Exception:
            _APP = None
    last = None
    for i in range(retries):
        try:
            _APP = atomacos.getAppRefByBundleId(BUNDLE)
            _APP.windows()
            return _APP
        except Exception as e:
            last = e
            time.sleep(0.6)
    raise SystemExit(f"[STOP] KakaoTalk 접근 실패: {last}")


def osa(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"osascript fail: {r.stderr.strip()}")
    return r.stdout.strip()


def key(code: int, mods: str = ""):
    clause = f"using {{{mods}}}" if mods else ""
    osa(f'tell application "System Events" to key code {code} {clause}')


def find_room(title_exact: str):
    """정확히 일치하는 제목의 대화방 창만 반환. 부분일치/폴백 없음."""
    for w in app().windows():
        if w.AXTitle == title_exact:
            return w
    return None


def assert_room(title_exact: str, step: str):
    """🔴 가드: 전송/삭제 직전 호출. 창 존재 + 정확 제목 + 활성(main) 확인."""
    w = find_room(title_exact)
    if w is None:
        titles = [x.AXTitle for x in app().windows()]
        raise SystemExit(f"[STOP:{step}] '{title_exact}' 창 없음. 현재 창들={titles}")
    try:
        is_main = bool(w.AXMain)
    except Exception:
        is_main = None
    front = osa('tell application "System Events" to get name of first process whose frontmost is true')
    if front != "KakaoTalk":
        raise SystemExit(f"[STOP:{step}] 최전면 앱이 KakaoTalk 아님: {front}")
    if is_main is False:
        raise SystemExit(f"[STOP:{step}] '{title_exact}' 창이 활성 창이 아님(AXMain=False)")
    print(f"  [GUARD OK:{step}] window='{w.AXTitle}' AXMain={is_main} front={front}")
    return w


def raise_room(title_exact: str):
    osa('tell application "KakaoTalk" to activate')
    time.sleep(0.8)
    w = find_room(title_exact)
    if w is None:
        titles = [x.AXTitle for x in app().windows()]
        raise SystemExit(f"[STOP] '{title_exact}' 창 없음. 현재 창들={titles}")
    try:
        w.Raise()
    except Exception:
        pass
    time.sleep(0.7)
    return assert_room(title_exact, "raise")


def click_point(x: float, y: float, delay: float = 0.15):
    """Quartz 좌표 클릭 (카톡 커스텀 버튼은 AXPress 미지원 → 클릭 폴백)."""
    import Quartz

    pt = Quartz.CGPointMake(float(x), float(y))
    move = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, pt, 0)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, move)
    time.sleep(delay)
    down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, pt, Quartz.kCGMouseButtonLeft)
    up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, pt, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.08)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
    time.sleep(delay)


def right_click_point(x: float, y: float, delay: float = 0.2):
    import Quartz

    pt = Quartz.CGPointMake(float(x), float(y))
    move = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, pt, 0)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, move)
    time.sleep(delay)
    down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventRightMouseDown, pt, Quartz.kCGMouseButtonRight)
    up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventRightMouseUp, pt, Quartz.kCGMouseButtonRight)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.08)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
    time.sleep(delay)


def click_el(el):
    p, s = g(el, "AXPosition"), g(el, "AXSize")
    if p is None or s is None:
        raise SystemExit("[STOP] 요소 좌표 없음")
    click_point(p.x + s.width / 2, p.y + s.height / 2)


def g(el, attr, default=None):
    try:
        return getattr(el, attr)
    except Exception:
        return default


def dump(el, depth=0, maxdepth=7, path="x", out=None):
    out = out if out is not None else []
    if depth > maxdepth:
        return out
    role = g(el, "AXRole", "?")
    parts = [f"{'  '*depth}{path} {role}"]
    for a in ("AXSubrole", "AXTitle", "AXDescription", "AXValue", "AXHelp", "AXIdentifier"):
        v = g(el, a)
        if v not in (None, "", False):
            s = str(v)
            if len(s) > 70:
                s = s[:70] + "…"
            parts.append(f"{a[2:]}={s!r}")
    p, s = g(el, "AXPosition"), g(el, "AXSize")
    if p is not None and s is not None:
        parts.append(f"@({int(p.x)},{int(p.y)}) {int(s.width)}x{int(s.height)}")
    out.append(" ".join(parts))
    for i, k in enumerate(g(el, "AXChildren") or []):
        dump(k, depth + 1, maxdepth, f"{path}.{i}", out)
    return out


def rows(title_exact: str):
    """대화방 메시지 테이블의 row 요소 리스트."""
    w = find_room(title_exact)
    if w is None:
        return []
    for ch in g(w, "AXChildren") or []:
        if g(ch, "AXRole") == "AXScrollArea":
            for t in g(ch, "AXChildren") or []:
                if g(t, "AXRole") == "AXTable":
                    return [r for r in (g(t, "AXChildren") or []) if g(r, "AXRole") == "AXRow"]
    return []


def row_text(r, maxdepth=6):
    """row 안의 모든 텍스트/설명 수집."""
    acc = []

    def rec(el, d=0):
        if d > maxdepth:
            return
        for a in ("AXValue", "AXDescription", "AXTitle", "AXHelp"):
            v = g(el, a)
            if isinstance(v, str) and v.strip():
                acc.append(v.strip())
        for k in g(el, "AXChildren") or []:
            rec(k, d + 1)

    rec(r)
    return acc


def sheets_of(title_exact: str):
    w = find_room(title_exact)
    if w is None:
        return []
    return [c for c in (g(w, "AXChildren") or []) if g(c, "AXRole") == "AXSheet"]


def confirm_file_sheet(title_exact: str):
    """'파일 전송' 확인 시트의 전송 버튼(오른쪽, 제목없음)을 누른다."""
    target = None
    for s in sheets_of(title_exact):
        if "파일 전송" in " ".join(row_text(s)):
            target = s
            break
    if target is None:
        raise SystemExit("[STOP] '파일 전송' 확인 시트 없음 — 임의 Return/클릭 금지")
    print("  [확인시트]", row_text(target))
    btns = []

    def collect(el, d=0):
        if d > 6:
            return
        if g(el, "AXRole") == "AXButton":
            p, s_ = g(el, "AXPosition"), g(el, "AXSize")
            if p is not None and s_ is not None:
                btns.append((int(p.x), int(s_.width), g(el, "AXTitle"), el))
        for k in g(el, "AXChildren") or []:
            collect(k, d + 1)

    collect(target)
    cands = [b for b in btns if b[2] != "취소" and b[1] >= 100]
    if len(cands) != 1:
        raise SystemExit(f"[STOP] 전송 버튼 후보 {len(cands)}개: {[(b[0],b[1],b[2]) for b in btns]}")
    assert_room(title_exact, "confirm-send")
    el = cands[0][3]
    try:
        el.Press()
        print("  [OK] 전송 버튼 AXPress")
    except Exception as e:
        # 카톡 커스텀 버튼: AXPress 가 AXErrorFailure 를 던져도 실제로는 동작함.
        print(f"  [i] AXPress 예외({type(e).__name__}) — 시트 소멸 여부로 판정")
        time.sleep(1.5)
        if any("파일 전송" in " ".join(row_text(s)) for s in sheets_of(title_exact)):
            print("  [i] 시트 잔존 → 좌표 클릭 폴백")
            click_el(el)
    return True


def snapshot_light(title_exact: str, tail: int = 4):
    """★속도 개선판: 전체 row 를 깊이 순회하지 않고 «개수 + 마지막 N개 텍스트»만 읽는다.
    검증에 필요한 정보(도착 여부·개수 변화)는 그대로 얻으면서 AX 순회 비용을 줄인다."""
    rs = rows(title_exact)
    out = {"count": len(rs), "tail": []}
    for r in rs[-tail:]:
        out["tail"].append(row_text(r))
    return out


def last_row_text(title_exact: str, tail: int = 2):
    rs = rows(title_exact)
    return [row_text(r) for r in rs[-tail:]]


def snapshot(title_exact: str):
    """현재 화면에 마운트된 row 요약 리스트."""
    out = []
    for i, r in enumerate(rows(title_exact)):
        p, s = g(r, "AXPosition"), g(r, "AXSize")
        out.append({
            "i": i,
            "y": int(p.y) if p else None,
            "h": int(s.height) if s else None,
            "texts": row_text(r),
        })
    return out
