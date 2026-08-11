#!/usr/bin/env python3
"""카톡 커스텀 컨텍스트 메뉴 처리 — AX 미노출이라 CGWindowList + Vision OCR 로 항목을 찾는다."""
import subprocess
import tempfile
import time

import Quartz
import Vision
from Foundation import NSURL


def kakao_windows():
    info = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    out = []
    for w in info:
        # 오너명은 시스템 언어에 따라 '카카오톡' 또는 'KakaoTalk'
        if w.get("kCGWindowOwnerName") not in ("KakaoTalk", "카카오톡"):
            continue
        b = w["kCGWindowBounds"]
        out.append({
            "id": int(w["kCGWindowNumber"]),
            "layer": int(w.get("kCGWindowLayer", 0)),
            "name": w.get("kCGWindowName", ""),
            "x": b["X"], "y": b["Y"], "w": b["Width"], "h": b["Height"],
        })
    return out


def find_menu_window(min_layer: int = 1):
    """레이어가 일반 창(0)보다 위인 팝업/메뉴 창을 반환."""
    cands = [w for w in kakao_windows() if w["layer"] >= min_layer and w["w"] > 60 and w["h"] > 60]
    if not cands:
        return None
    # 가장 위 레이어, 그중 가장 작은 창
    cands.sort(key=lambda w: (-w["layer"], w["w"] * w["h"]))
    return cands[0]


def ocr_region(x, y, w, h, scale_hint=2):
    """화면 영역을 캡처해 OCR. [(text, cx, cy)] (화면 좌표계) 반환."""
    tmp = tempfile.mktemp(suffix=".png")
    subprocess.run(
        ["screencapture", "-x", "-R", f"{int(x)},{int(y)},{int(w)},{int(h)}", tmp],
        check=True,
    )
    url = NSURL.fileURLWithPath_(tmp)
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, {})
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(0)  # accurate
    req.setRecognitionLanguages_(["ko-KR", "en-US"])
    req.setUsesLanguageCorrection_(False)
    handler.performRequests_error_([req], None)
    res = []
    for obs in req.results() or []:
        cand = obs.topCandidates_(1)
        if not cand:
            continue
        text = cand[0].string()
        bb = obs.boundingBox()  # 정규화, 좌하단 원점
        cx = x + (bb.origin.x + bb.size.width / 2) * w
        cy = y + (1 - (bb.origin.y + bb.size.height / 2)) * h
        res.append((text, cx, cy))
    return res, tmp


def click(x, y, delay=0.15):
    pt = Quartz.CGPointMake(float(x), float(y))
    Quartz.CGEventPost(Quartz.kCGHIDEventTap,
                       Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, pt, 0))
    time.sleep(delay)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap,
                       Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, pt,
                                                      Quartz.kCGMouseButtonLeft))
    time.sleep(0.08)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap,
                       Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, pt,
                                                      Quartz.kCGMouseButtonLeft))
    time.sleep(delay)


def read_menu(pad=6):
    """현재 떠 있는 컨텍스트 메뉴의 항목 목록을 OCR로 읽는다."""
    mw = find_menu_window()
    if mw is None:
        return None, []
    items, shot = ocr_region(mw["x"] - pad, mw["y"] - pad, mw["w"] + pad * 2, mw["h"] + pad * 2)
    return mw, items


def click_menu_item(label: str, exact=True):
    """메뉴 항목 라벨을 OCR로 찾아 클릭. 못 찾으면 ESC 후 예외."""
    mw, items = read_menu()
    if mw is None:
        raise SystemExit("[STOP] 컨텍스트 메뉴 창을 찾지 못함")
    norm = lambda s: s.replace(" ", "")
    hits = [it for it in items if (norm(it[0]) == norm(label) if exact else norm(label) in norm(it[0]))]
    if len(hits) != 1:
        subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 53'])
        raise SystemExit(f"[STOP] '{label}' 항목 {len(hits)}개 (OCR={[i[0] for i in items]})")
    _, cx, cy = hits[0]
    click(cx, cy)
    return {"menu": mw, "label": label, "x": cx, "y": cy, "ocr": [i[0] for i in items]}
