#!/usr/bin/env python3
"""정확한 이름의 카톡 방만 여는 헬퍼 (부분매치 오픈 방지).

배경(2026-07-13): "리브리" 검색이 'stop_리브리'(구방)와 '리브리'(신규·한수지)를 모두 잡고,
kakao_read/search_and_open_chat 은 검색 첫 결과(=stop_리브리)를 열어 엉뚱한 방을 읽는 사고가 났다.
이 헬퍼는 ① 열려있는 비-메인 대화창을 모두 닫아 find_open_chat 오매치를 제거하고
② 검색결과 행 중 이름이 target 과 '정확히' 일치하는 행을 Quartz 클릭+Enter 로 연다.

사용:  uv run --with atomacos --with pyobjc-framework-Quartz --python 3.12 python open_exact.py "리브리"
반환(stdout json): {"ok":bool,"opened":"<열린창제목>","candidates":[...]}
이후 kakao_read/kakao_send 는 열린 그 창(정확매치)을 그대로 쓰면 된다.
"""
import sys, os, time, subprocess, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kakao_read as K
import Quartz


def _click(x, y):
    for t in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
        e = Quartz.CGEventCreateMouseEvent(None, t, (x, y), Quartz.kCGMouseButtonLeft)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, e)
        time.sleep(0.06)


def _safe(el, a, d=None):
    return K.safe_get_attr(el, a, d)


def open_exact(target: str) -> dict:
    # 1) 검색 필터 (Cmd+F → target 붙여넣기)
    K.clear_search_and_go_main()
    K.key_code(3, "command down"); time.sleep(0.5)   # Cmd+F
    K.key_code(0, "command down"); time.sleep(0.1)   # Cmd+A
    subprocess.run(["pbcopy"], input=target.encode(), check=True)
    K.key_code(9, "command down"); time.sleep(1.2)   # Cmd+V
    # 2) 정확매치 행 찾기
    app = K.get_kakao_app()
    found = None; cands = []
    for win in app.windows():
        if _safe(win, 'AXTitle') not in K.MAIN_WINDOW_TITLES:
            continue
        for child in _safe(win, 'AXChildren', []):
            if _safe(child, 'AXRole') != 'AXScrollArea':
                continue
            for tbl in _safe(child, 'AXChildren', []):
                if _safe(tbl, 'AXRole') != 'AXTable':
                    continue
                for row in _safe(tbl, 'AXChildren', []):
                    if _safe(row, 'AXRole') != 'AXRow':
                        continue
                    texts = K._extract_row_texts(row)
                    if not texts:
                        continue
                    cands.append(texts[0])
                    if texts[0] == target:   # 정확매치
                        pos = _safe(row, 'AXPosition'); sz = _safe(row, 'AXSize')
                        if pos and sz:
                            found = (pos.x + sz.width / 2, pos.y + sz.height / 2)
                break
            break
        break
    if not found:
        K.clear_search_and_go_main()
        return {"ok": False, "opened": None, "candidates": cands, "error": "exact_row_not_found"}
    # 3) 정확매치 행 클릭 + Enter → 별도 대화창 열기 (검증된 흐름)
    _click(found[0], found[1]); time.sleep(0.4)
    K.key_code(36); time.sleep(1.4)   # Enter
    # 4) 검증
    app = K.get_kakao_app()
    opened = [_safe(w, 'AXTitle') for w in app.windows()
              if _safe(w, 'AXTitle') and _safe(w, 'AXTitle') not in K.MAIN_WINDOW_TITLES]
    ok = target in opened
    # 5) target 이 제대로 열렸으면, target 아닌 stray 대화창(예: stop_리브리)만 닫아 오매치 차단
    if ok:
        for w in list(app.windows()):
            t = _safe(w, 'AXTitle', '')
            if t and t not in K.MAIN_WINDOW_TITLES and t != target:
                try:
                    w.AXRaise()
                except Exception:
                    pass
                time.sleep(0.2)
                K.run_applescript('tell application "System Events" to tell process "KakaoTalk" to keystroke "w" using command down')
                time.sleep(0.3)
    return {"ok": ok, "opened": (target if ok else (opened[0] if opened else None)), "candidates": cands}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "usage: open_exact.py <정확한방이름>"}, ensure_ascii=False))
        sys.exit(1)
    res = open_exact(sys.argv[1])
    print(json.dumps(res, ensure_ascii=False))
    sys.exit(0 if res.get("ok") else 2)
