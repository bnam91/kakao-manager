#!/usr/bin/env python3
"""내가 보낸 메시지 삭제 (스크롤 탐색 + 안전가드).

Usage: kk_del2.py "<방>" "<본문/파일명 일부>" [--me] [--dry]
  스크롤로 대상 row 를 화면에 올린 뒤 우클릭 → OCR 메뉴 → 삭제 → 결과 검증.
"""
import argparse, json, time
import Quartz
import kklib as K
import kkmenu as M
import kksafe as S
import kkensure as E

ap = argparse.ArgumentParser()
ap.add_argument("room")
ap.add_argument("needle")
ap.add_argument("--me", action="store_true")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
ROOM, NEEDLE = a.room, a.needle
LABEL = "나에게서만 삭제" if a.me else "모두에게서 삭제"


def scroll(clicks):
    w = K.find_room(ROOM)
    p, s = K.g(w, "AXPosition"), K.g(w, "AXSize")
    x, y = p.x + s.width / 2, p.y + s.height / 2
    for _ in range(abs(clicks)):
        ev = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 1,
                                                  2 if clicks > 0 else -2)
        Quartz.CGEventSetLocation(ev, Quartz.CGPointMake(float(x), float(y)))
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        time.sleep(0.15)


def find_visible(needle):
    w = K.find_room(ROOM)
    p, s = K.g(w, "AXPosition"), K.g(w, "AXSize")
    top, bot = p.y + 95, p.y + s.height - 95
    hit = None
    for r in K.rows(ROOM):
        rp, rs = K.g(r, "AXPosition"), K.g(r, "AXSize")
        if rp is None or rs is None or rs.height < 20:
            continue
        if needle in " ".join(K.row_text(r)) and rp.y >= top and rp.y + rs.height <= bot:
            hit = r
    return hit


def bubble_point(r, needle=None):
    """우클릭 지점: ①needle 을 담은 텍스트 요소 ②가장 큰 이미지 ③row 안쪽 폴백(창 경계로 클램프)."""
    named, imgs = [], []

    def rec(el):
        role, v = K.g(el, "AXRole"), K.g(el, "AXValue")
        p, s = K.g(el, "AXPosition"), K.g(el, "AXSize")
        if p is not None and s is not None and s.width > 10 and s.height > 10:
            if needle and isinstance(v, str) and needle in v:
                named.append((p.x + s.width / 2, p.y + s.height / 2))
            if role == "AXImage" and s.width > 25 and s.height > 20:
                imgs.append((s.width * s.height, p.x + s.width / 2, p.y + s.height / 2))
        for k in K.g(el, "AXChildren") or []:
            rec(k)

    rec(r)
    if named:
        x, y = named[0]
    elif imgs:
        imgs.sort(reverse=True)
        x, y = imgs[0][1], imgs[0][2]
    else:
        rp, rs = K.g(r, "AXPosition"), K.g(r, "AXSize")
        x, y = rp.x + rs.width * 0.75, rp.y + rs.height / 2
    # 창 안쪽으로 클램프 (경계를 벗어나면 바탕화면을 클릭하게 된다)
    w = K.find_room(ROOM)
    wp, ws = K.g(w, "AXPosition"), K.g(w, "AXSize")
    x = min(max(x, wp.x + 8), wp.x + ws.width - 8)
    y = min(max(y, wp.y + 95), wp.y + ws.height - 105)
    return x, y


def window_buttons(titles_wanted):
    """창 최상위의 버튼(선택모드 확인/취소 등)."""
    w = K.find_room(ROOM)
    found = {}
    for c in K.g(w, "AXChildren") or []:
        if K.g(c, "AXRole") == "AXButton" and K.g(c, "AXTitle") in titles_wanted:
            found[K.g(c, "AXTitle")] = c
    return found


def in_select_mode():
    b = window_buttons({"확인", "취소"})
    return len(b) == 2


def leave_select_mode():
    b = window_buttons({"취소"})
    if "취소" in b:
        try:
            b["취소"].Press()
        except Exception:
            K.click_el(b["취소"])
        time.sleep(1.0)
        return True
    return False


def row_checkbox(r):
    box = []

    def rec(el):
        if K.g(el, "AXRole") == "AXCheckBox":
            box.append(el)
        for k in K.g(el, "AXChildren") or []:
            rec(k)

    rec(r)
    return box[0] if box else None


out = {"room": ROOM, "needle": NEEDLE, "mode": LABEL}
E.ensure_room(ROOM)
if in_select_mode():
    print("  [i] 이전 선택모드 잔존 → 취소")
    leave_select_mode()
cl_before = S.chatlist()

r = None
for i in range(16):
    r = find_visible(NEEDLE)
    if r is not None:
        break
    scroll(-2 if i % 4 == 3 else 3)   # 위로 못 찾으면 아래로도 훑는다
    time.sleep(0.4)
if r is None:
    raise SystemExit(f"[STOP] '{NEEDLE}' 를 화면에 올리지 못함")

out["row"] = K.row_text(r)
x, y = bubble_point(r, NEEDLE)

# 🔴 우클릭 지점이 정말 이 대화방인지
hit = S.hit_test(x, y)
if hit is None or hit.get("window") != ROOM:
    raise SystemExit(f"[STOP] 우클릭 지점이 '{ROOM}' 아님: {hit}")
out["hit"] = hit

K.right_click_point(x, y)
time.sleep(1.4)
mw, items = M.read_menu()
out["menu"] = [t for t, _, _ in items]
if mw is None:
    raise SystemExit("[STOP] 컨텍스트 메뉴 안 뜸")

norm = lambda s: s.replace(" ", "")
hits = [it for it in items if norm(it[0]) == norm(LABEL)]
if len(hits) != 1:
    K.key(53)
    raise SystemExit(f"[STOP] '{LABEL}' 항목 {len(hits)}개 — 메뉴={out['menu']}")
out["menu_item_xy"] = (int(hits[0][1]), int(hits[0][2]))

if a.dry:
    K.key(53)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    raise SystemExit(0)

M.click(hits[0][1], hits[0][2])
time.sleep(2.0)

# ★'나에게서만 삭제' 는 «다중선택 모드»로 진입한다 — 체크박스 선택 후 확인까지 해야 실제로 지워진다
if in_select_mode():
    out["select_mode"] = True
    tgt = None
    for _ in range(12):
        tgt = find_visible(NEEDLE)
        if tgt is not None:
            break
        scroll(2)
        time.sleep(0.3)
    if tgt is None:
        leave_select_mode()
        raise SystemExit("[STOP] 선택모드에서 대상 row 를 못 찾음 — 취소하고 정지")
    cb = row_checkbox(tgt)
    if cb is None:
        leave_select_mode()
        raise SystemExit("[STOP] 대상 row 체크박스 없음 — 취소하고 정지")
    hit2 = S.hit_test(*[K.g(cb, "AXPosition").x + K.g(cb, "AXSize").width / 2,
                        K.g(cb, "AXPosition").y + K.g(cb, "AXSize").height / 2])
    if hit2 is None or hit2.get("window") != ROOM:
        leave_select_mode()
        raise SystemExit(f"[STOP] 체크박스 지점 불일치 {hit2}")
    try:
        cb.Press()
    except Exception:
        K.click_el(cb)
    time.sleep(0.8)
    out["checkbox_value"] = K.g(cb, "AXValue")
    btns = window_buttons({"확인"})
    if "확인" not in btns:
        leave_select_mode()
        raise SystemExit("[STOP] 선택모드 '확인' 버튼 없음")
    try:
        btns["확인"].Press()
    except Exception:
        K.click_el(btns["확인"])
    time.sleep(2.0)

# 확인 팝업/시트가 뜨면 처리 ('모두에게서 삭제'는 시트 없이 즉시 실행됨)
sheets = K.sheets_of(ROOM)
out["sheets"] = [K.row_text(s) for s in sheets]
for sh in sheets:
    txt = K.row_text(sh)
    btn = None

    def rec_btn(el):
        global btn
        if K.g(el, "AXRole") == "AXButton" and K.g(el, "AXTitle") in ("삭제", "확인"):
            btn = el
        for k in K.g(el, "AXChildren") or []:
            rec_btn(k)

    rec_btn(sh)
    if btn is not None:
        out["sheet_button"] = K.g(btn, "AXTitle")
        out["sheet_text"] = txt
        try:
            btn.Press()
        except Exception:
            K.click_el(btn)
        time.sleep(2.0)
        break
sheets = K.sheets_of(ROOM)
popup = M.find_menu_window()
if popup:
    pit, _ = M.ocr_region(popup["x"], popup["y"], popup["w"], popup["h"])
    out["popup"] = [t for t, _, _ in pit]
    cands = [i for i in pit if norm(i[0]) in ("삭제", "확인")]
    if len(cands) == 1:
        M.click(cands[0][1], cands[0][2])
        out["popup_clicked"] = cands[0][0]
        time.sleep(2.0)

time.sleep(1.5)
after = K.snapshot(ROOM)
joined = " ".join(" ".join(x["texts"]) for x in after)
out["still_present"] = NEEDLE in joined
out["deleted_notice_count"] = sum(1 for x in after if "삭제되었습니다" in " ".join(x["texts"]))
out["contamination"] = S.diff_chatlist(cl_before, S.chatlist(), ROOM)
out["ok"] = not out["still_present"]
print(json.dumps(out, ensure_ascii=False, indent=1))
