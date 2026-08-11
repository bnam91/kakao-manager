#!/usr/bin/env python3
"""kakao 안전 전송 프로토콜 (텍스트·파일 공용).

설계 원칙
  1. 대상 창을 «객체»로 잡는다 — 좌표·전역 키스트로크를 쓰지 않는다.
  2. 전송을 유발하는 마지막 동작 «직전»에 프론트앱 + 카톡 focused window 를 재확인한다.
  3. 전송 후 ①보낸 방 재조회 ②타 방 오염 검사 ③방 제목 동일성 3중 검증.
  4. 불일치면 즉시 SystemExit — ★자동 재시도 없음.
"""
import os
import subprocess
import time

import kklib as K
import kkensure as E


_LIST_TABLE = None


class Abort(SystemExit):
    pass


# ---------------------------------------------------------------- 상태 조회
def frontmost_app():
    return K.osa('tell application "System Events" to get name of first process whose frontmost is true')


def focused_window_title():
    """카톡«앱 내부»에서 키 입력을 받게 될 창. 프론트앱과 별개로 반드시 확인해야 한다.
    시트(파일전송 확인창 등)가 떠 있으면 AXFocusedWindow 가 제목 없는 시트가 되므로 부모 창까지 올라간다."""
    try:
        fw = K.app().AXFocusedWindow
    except Exception:
        return None
    t = K.g(fw, "AXTitle")
    if t:
        return t
    cur = fw
    for _ in range(6):
        cur = K.g(cur, "AXParent")
        if cur is None:
            break
        if K.g(cur, "AXRole") == "AXWindow":
            return K.g(cur, "AXTitle")
    # 부모 추적 실패 시: 시트를 가진 창을 역으로 찾는다
    for w in K.app().windows():
        for c in K.g(w, "AXChildren") or []:
            if K.g(c, "AXRole") == "AXSheet":
                return K.g(w, "AXTitle")
    return t


def _find(el, pred, d=0, maxd=8):
    if d > maxd:
        return None
    if pred(el):
        return el
    for k in K.g(el, "AXChildren") or []:
        r = _find(k, pred, d + 1, maxd)
        if r is not None:
            return r
    return None


def chatlist(unfilter=True, limit=10):
    """메인 목록창의 채팅방 스냅샷 — 타 방 오염 검사의 기준.
    ⚠️검색 필터가 걸려 있으면 목록이 잘려서 «방이 사라졌다/생겼다»는 오탐이 난다 → 먼저 필터를 푼다."""
    main = next((w for w in K.app().windows() if K.g(w, "AXTitle") in K.MAIN_TITLES), None)
    if main is None:
        return None
    if unfilter:
        E.clear_search()
    global _LIST_TABLE
    t = _LIST_TABLE
    if t is not None:
        try:
            K.g(t, "AXRole")
            _ = t.AXChildren
        except Exception:
            t = None
    if t is None:
        t = _find(main, lambda e: K.g(e, "AXRole") == "AXTable")
        _LIST_TABLE = t
    if t is None:
        return None
    # ★상위 N개만 본다: 오발송이 나면 그 방이 목록 «맨 위»로 올라오므로 전체를 훑을 필요가 없다
    out = []
    for r in K.g(t, "AXChildren") or []:
        if K.g(r, "AXRole") != "AXRow":
            continue
        tx = [x for x in K.row_text(r, maxdepth=3) if x != "프로필"]
        if not tx:
            continue
        out.append({"name": tx[0], "rest": tx[1:]})
        if len(out) >= limit:
            break
    return out


def diff_chatlist(before, after, target, payload=None):
    """타 방 오염 검사.
    ★판정 2단계:
      - HARD(오발송 확정): 다른 방의 «마지막 메시지 미리보기»에 우리가 방금 보낸 내용(payload)이 보인다
      - SOFT(경고): 다른 방이 바뀌었지만 payload 와 무관 → 상대가 보낸 «수신»일 가능성이 높다
    실계정에서는 수신 메시지가 계속 들어오므로 «변했다»만으로 정지하면 못 쓴다."""
    if before is None or after is None:
        return {"checked": False, "reason": "채팅목록 조회 실패"}
    b = {x["name"]: x["rest"] for x in before}
    a = {x["name"]: x["rest"] for x in after}
    hard, soft = [], []
    for name, rest in a.items():
        if name == target:
            continue
        why = None
        if name not in b:
            why = "목록에 새로 보임(필터 해제/신규)"
        elif b[name] != rest:
            why = "미리보기/시각 변경"
        if not why:
            continue
        item = {"room": name, "before": b.get(name), "after": rest, "why": why}
        joined = " ".join(str(x) for x in rest)
        if payload and any(tok and tok in joined for tok in payload_tokens(payload)):
            hard.append(item)
        else:
            soft.append(item)
    return {"checked": True, "misdelivery": hard, "other_rooms_changed_benign": soft}


def payload_tokens(payload):
    """오발송 판정용 토큰 — 파일명/본문 앞부분."""
    p = str(payload)
    toks = [p]
    if len(p) > 12:
        toks.append(p[:12])
    return [t for t in toks if len(t) >= 6]


# ---------------------------------------------------------------- 창 선택 / 가드
def select_room(title):
    """🔴 결정적 창 선택: 「창」 메뉴의 «정확 제목» 항목을 눌러 그 창을 키 윈도우로 만든다.
    좌표 클릭이 아니라 메뉴 항목 객체를 누르므로 다른 방이 선택될 여지가 없다."""
    K.osa('tell application "KakaoTalk" to activate')
    time.sleep(0.5)
    app = K.app()
    item = None
    for ch in K.g(app, "AXChildren") or []:
        if K.g(ch, "AXRole") != "AXMenuBar":
            continue
        for m in K.g(ch, "AXChildren") or []:
            if K.g(m, "AXTitle") != "창":
                continue
            for sub in K.g(m, "AXChildren") or []:
                for it in K.g(sub, "AXChildren") or []:
                    if K.g(it, "AXTitle") == title:
                        item = it
    if item is None:
        # 「창」 메뉴에 없으면 창 객체를 직접 Raise
        w = K.find_room(title)
        if w is None:
            raise Abort(f"[STOP] '{title}' 창 없음 — select_room 실패")
        w.Raise()
    else:
        try:
            item.Press()
        except Exception:
            w = K.find_room(title)
            if w is None:
                raise Abort(f"[STOP] '{title}' 창 없음")
            w.Raise()
    time.sleep(0.8)


def guard(title, step, require_front=True):
    """전송 유발 동작 «직전»에 호출. 프론트앱 + 카톡 focused window 를 함께 본다."""
    w = K.find_room(title)
    if w is None:
        raise Abort(f"[STOP:{step}] '{title}' 창이 사라짐")
    fw = focused_window_title()
    if fw != title:
        raise Abort(f"[STOP:{step}] 카톡 focused window 가 '{fw}' — '{title}' 아님. 전송 중단")
    if require_front:
        fa = frontmost_app()
        if fa != "KakaoTalk":
            raise Abort(f"[STOP:{step}] 최전면 앱이 '{fa}' — 키 입력 유출 위험. 전송 중단")
    return w


def window_at_point(x, y, normal_only=False):
    """그 화면좌표에서 «맨 위에 있는» 창. (OnScreenOnly 목록은 앞→뒤 순서)
    normal_only=True 면 일반 앱 창(layer<=0)만 본다 — 스크린샷/알림 같은 클릭통과 오버레이 오탐 방지."""
    import Quartz
    info = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID)
    for w in info:
        layer = int(w.get("kCGWindowLayer", 0))
        if layer < 0:
            continue
        if normal_only and layer > 0:
            continue
        if float(w.get("kCGWindowAlpha", 1)) == 0:
            continue
        b = w["kCGWindowBounds"]
        if b["X"] <= x <= b["X"] + b["Width"] and b["Y"] <= y <= b["Y"] + b["Height"]:
            return {"owner": w.get("kCGWindowOwnerName"), "name": w.get("kCGWindowName", ""),
                    "layer": int(w.get("kCGWindowLayer", 0))}
    return None


def hit_test(x, y):
    """그 좌표에서 «실제로 클릭을 받을» UI 요소의 (pid, 창 제목).
    CGWindowList 는 클릭 통과(click-through) 오버레이까지 세어 오탐이 나므로 AX 히트테스트를 쓴다."""
    import ApplicationServices as AS
    sw = AS.AXUIElementCreateSystemWide()
    err, el = AS.AXUIElementCopyElementAtPosition(sw, float(x), float(y), None)
    if err != 0 or el is None:
        return None
    _, pid = AS.AXUIElementGetPid(el, None)
    cur, title = el, None
    for _ in range(12):
        e1, role = AS.AXUIElementCopyAttributeValue(cur, "AXRole", None)
        if e1 == 0 and role == "AXWindow":
            e2, t = AS.AXUIElementCopyAttributeValue(cur, "AXTitle", None)
            title = t if e2 == 0 else None
            break
        e3, parent = AS.AXUIElementCopyAttributeValue(cur, "AXParent", None)
        if e3 != 0 or parent is None:
            break
        cur = parent
    return {"pid": int(pid), "window": title}


def kakao_pid():
    r = subprocess.run(["pgrep", "-x", "KakaoTalk"], capture_output=True, text=True)
    return int(r.stdout.split()[0]) if r.stdout.strip() else None


def click_verified(el, title, step):
    """🔴 좌표 클릭 방어 2중:
       ① AX 히트테스트로 «그 점을 클릭하면 누가 받는지»를 확인 (pid + 창 제목)
       ② 일반 레이어(layer<=0) 창들 중 그 점을 덮는 최상단이 대상 창인지 확인"""
    p, s = K.g(el, "AXPosition"), K.g(el, "AXSize")
    if p is None or s is None:
        raise Abort(f"[STOP:{step}] 클릭 대상 좌표 없음")
    x, y = p.x + s.width / 2, p.y + s.height / 2
    hit = hit_test(x, y)
    kp = kakao_pid()
    if hit is None:
        raise Abort(f"[STOP:{step}] ({int(x)},{int(y)}) 히트테스트 실패")
    if hit["pid"] != kp:
        raise Abort(f"[STOP:{step}] 클릭 수신자가 카톡이 아님: {hit} (kakao pid={kp}) — 클릭 중단")
    if hit["window"] not in (None, title):
        raise Abort(f"[STOP:{step}] 클릭 수신 창이 '{hit['window']}' — '{title}' 아님. 클릭 중단")
    top = window_at_point(x, y, normal_only=True)
    if top is not None and (top["owner"] not in ("KakaoTalk", "카카오톡") or top["name"] != title):
        raise Abort(f"[STOP:{step}] 그 지점을 덮는 창이 {top} — 클릭 중단")
    K.click_point(x, y)
    return {"x": int(x), "y": int(y), "hit": hit}


def room_input(w):
    return _find(w, lambda e: K.g(e, "AXRole") == "AXTextArea"
                 and K.g(e, "AXDescription") == "메시지 입력", maxd=4)


def send_button(w):
    for c in K.g(w, "AXChildren") or []:
        if K.g(c, "AXRole") == "AXButton":
            s = K.g(c, "AXSize")
            if s is not None and 60 <= s.width <= 100 and 25 <= s.height <= 40:
                return c
    return None


# ---------------------------------------------------------------- 전송
def send_text(title, text, timing=None, inject=None):
    """★포커스 비의존 경로: 입력창 AXValue 세팅 + 그 창의 전송버튼 객체 Press.
    전역 키스트로크·좌표를 전혀 쓰지 않으므로 다른 앱/다른 방으로 샐 수 없다."""
    t = timing if timing is not None else {}
    t0 = time.time()
    E.ensure_room(title)
    t["ensure"] = round(time.time() - t0, 2)

    s = time.time()
    cl_before = chatlist()
    before = K.snapshot(title)
    t["snapshot_before"] = round(time.time() - s, 2)

    s = time.time()
    select_room(title)
    w = K.find_room(title)
    inp, btn = room_input(w), send_button(w)
    if inp is None or btn is None:
        raise Abort("[STOP] 입력창/전송버튼 요소 확보 실패")
    draft = K.g(inp, "AXValue")
    if isinstance(draft, str) and draft.strip():
        raise Abort(f"[STOP] 입력창에 사람이 쓰던 초안이 있음({draft[:30]!r}) — 덮어쓰지 않고 정지")
    # ★본문은 키스트로크가 아니라 «그 창의 입력 요소»에 직접 넣는다 → 다른 앱·다른 방으로 샐 수 없다
    inp.AXValue = text
    time.sleep(0.25)
    if K.g(inp, "AXValue") != text:
        raise Abort("[STOP] 입력창에 본문이 들어가지 않음")
    t["fill"] = round(time.time() - s, 2)

    # 🔴 클릭 직전 최종 확인 — 확인과 실행 사이 간격 최소화
    s = time.time()
    try:
        if inject:                 # ★고장 주입(테스트 전용): 이 지점에서 포커스를 빼앗아 본다
            inject()
        w2 = guard(title, "before-send-click")
        if K.g(room_input(w2), "AXValue") != text:
            raise Abort("[STOP] 전송 직전 본문 불일치")
        t["click"] = click_verified(send_button(w2), title, "send-click")
    except SystemExit:
        # 롤백: 넣어둔 본문을 회수해 초안을 남기지 않는다 (★자동 재시도는 하지 않는다)
        try:
            ww = K.find_room(title)
            if ww is not None:
                ii = room_input(ww)
                if ii is not None and K.g(ii, "AXValue") == text:
                    ii.AXValue = ""
        except Exception:
            pass
        raise
    t["press"] = round(time.time() - s, 2)

    s = time.time()
    ok = False
    for _ in range(20):
        time.sleep(0.25)
        after = K.snapshot(title)
        if any(text.split("\n")[0] in " ".join(x["texts"]) for x in after):
            ok = True
            break
    t["wait_arrival"] = round(time.time() - s, 2)
    if not ok:
        raise Abort("[STOP] 전송 후 방에서 본문을 찾지 못함")

    s = time.time()
    v = verify(title, before, cl_before, expect=text)
    t["verify"] = round(time.time() - s, 2)
    t["total"] = round(time.time() - t0, 2)
    return {"ok": True, "verify": v, "timing": t}


def clipboard_files(paths):
    from AppKit import NSPasteboard, NSURL
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    return bool(pb.writeObjects_([NSURL.fileURLWithPath_(p) for p in paths]))


def menu_paste():
    """「편집 > Paste」 메뉴 항목을 «객체»로 눌러 붙여넣기.
    전역 ⌘V 와 달리 카톡 앱에만 전달되므로 다른 앱으로 키가 새지 않는다."""
    app = K.app()
    for ch in K.g(app, "AXChildren") or []:
        if K.g(ch, "AXRole") != "AXMenuBar":
            continue
        for m in K.g(ch, "AXChildren") or []:
            if K.g(m, "AXTitle") != "편집":
                continue
            for sub in K.g(m, "AXChildren") or []:
                for it in K.g(sub, "AXChildren") or []:
                    if K.g(it, "AXTitle") in ("Paste", "붙여넣기"):
                        if not K.g(it, "AXEnabled"):
                            return False, "Paste 메뉴 비활성(입력 포커스 없음)"
                        try:
                            it.Press()
                            return True, "menu"
                        except Exception as e:
                            return False, f"Press 실패: {type(e).__name__}"
    return False, "Paste 메뉴 항목 없음"


def cancel_sheet(title):
    """롤백: 대상 창에 떠 있는 확인 시트를 '취소'로 닫는다 (전송 안 함)."""
    for sh in K.sheets_of(title):
        b = _find(sh, lambda e: K.g(e, "AXRole") == "AXButton" and K.g(e, "AXTitle") == "취소")
        if b is not None:
            try:
                b.Press()
            except Exception:
                try:
                    K.click_el(b)
                except Exception:
                    pass
            time.sleep(0.8)
            return True
    return False


def confirm_sheet_on(title):
    for s in K.sheets_of(title):
        if "파일 전송" in " ".join(K.row_text(s)):
            return s
    return None


def send_file(title, path, timing=None, allow_bundle_notice=True):
    """파일 첨부. ★확인 시트가 «대상 창의 자식»으로 뜬 것을 확인한 뒤에만 전송을 누른다
    (붙여넣기가 다른 방으로 샜다면 시트가 안 뜨므로 아무것도 전송되지 않는다)."""
    t = timing if timing is not None else {}
    t0 = time.time()
    path = os.path.abspath(path)
    name = os.path.basename(path)
    if not os.path.exists(path):
        raise Abort(f"[STOP] 파일 없음: {path}")

    E.ensure_room(title)
    t["ensure"] = round(time.time() - t0, 2)

    s = time.time()
    cl_before = chatlist()
    before = K.snapshot(title)
    t["snapshot_before"] = round(time.time() - s, 2)

    s = time.time()
    if not clipboard_files([path]):
        raise Abort("[STOP] 클립보드에 파일 URL 기록 실패")
    t["clipboard"] = round(time.time() - s, 2)

    s = time.time()
    select_room(title)
    w = guard(title, "before-paste")
    inp = room_input(w)
    if inp is None:
        raise Abort("[STOP] 입력창 없음")
    try:
        inp.AXFocused = True      # 좌표 클릭 대신 요소에 직접 포커스
    except Exception:
        pass
    time.sleep(0.2)
    guard(title, "paste")
    ok, how = menu_paste()
    if not ok:
        raise Abort(f"[STOP] 붙여넣기 실패: {how}")
    t["paste"] = round(time.time() - s, 2)

    s = time.time()
    sheet = None
    for _ in range(24):
        time.sleep(0.25)
        for sh in K.sheets_of(title):
            txt = " ".join(K.row_text(sh))
            if "묶어보내기" in txt and allow_bundle_notice:
                b = _find(sh, lambda e: K.g(e, "AXRole") == "AXButton" and K.g(e, "AXTitle") == "확인")
                if b is not None:
                    try:
                        b.Press()
                    except Exception:
                        K.click_el(b)
                    time.sleep(1.0)
                continue
            if "파일 전송" in txt:
                sheet = sh
                break
        if sheet is not None:
            break
    t["sheet"] = round(time.time() - s, 2)
    if sheet is None:
        raise Abort(f"[STOP] '{title}' 창에 파일전송 확인 시트가 안 뜸 — 붙여넣기가 새었을 수 있음. "
                    f"아무것도 전송하지 않고 정지")
    if name not in " ".join(K.row_text(sheet)):
        raise Abort(f"[STOP] 확인 시트의 파일명 불일치: {K.row_text(sheet)}")

    s = time.time()
    try:
        guard(title, "confirm-send", require_front=False)
        K.confirm_file_sheet(title)
    except SystemExit:
        cancel_sheet(title)          # 롤백: 확인 시트를 취소해 아무것도 보내지 않는다
        raise
    t["confirm"] = round(time.time() - s, 2)

    s = time.time()
    ok = False
    for _ in range(40):
        time.sleep(0.25)
        after = K.snapshot(title)
        if len(after) > len(before) or any(name in " ".join(x["texts"]) for x in after):
            ok = True
            break
    t["wait_arrival"] = round(time.time() - s, 2)
    if not ok:
        raise Abort("[STOP] 전송 후 방에 도착물이 확인되지 않음")

    s = time.time()
    v = verify(title, before, cl_before, expect=name, media_ok=True)
    t["verify"] = round(time.time() - s, 2)
    t["total"] = round(time.time() - t0, 2)
    return {"ok": True, "verify": v, "timing": t}


# ---------------------------------------------------------------- 검증
def verify(title, rows_before, cl_before, expect=None, media_ok=False):
    """①보낸 방 재조회 ②타 방 오염 검사 ③활성 방 제목 동일성."""
    res = {}
    after = K.snapshot(title)
    joined = " ".join(" ".join(x["texts"]) for x in after)
    res["rows_before"] = len(rows_before)
    res["rows_after"] = len(after)
    res["found_in_room"] = (expect in joined) if expect else None
    res["row_delta"] = len(after) - len(rows_before)
    if expect and not res["found_in_room"]:
        if not (media_ok and res["row_delta"] > 0):
            raise Abort(f"[STOP] 재조회에서 '{expect}' 미발견 — 도착 미확인")
    res["tail"] = [x["texts"] for x in after[-2:]]

    cl_after = chatlist()
    res["contamination"] = diff_chatlist(cl_before, cl_after, title, payload=expect)
    if not res["contamination"].get("checked"):
        raise Abort(f"[STOP] 타 방 오염검사 불가({res['contamination'].get('reason')}) — 검증 미완")
    if res["contamination"].get("misdelivery"):
        raise Abort(f"[STOP] ★오발송 확정 — 다른 방에 우리 내용이 나타남: "
                    f"{res['contamination']['misdelivery']} — 즉시 전체 정지, 재시도 금지")

    res["focused_window_after"] = focused_window_title()
    if res["focused_window_after"] != title:
        raise Abort(f"[STOP] 전송 후 활성 방이 '{res['focused_window_after']}' 로 바뀜")
    return res
