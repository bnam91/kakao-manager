#!/usr/bin/env python3
"""kakao_manager 안전 전송 CLI (텍스트·파일 공용).

  python kk.py send-file "<방 정확제목>" <파일...>
  python kk.py send-text "<방 정확제목>" "<본문>"
  python kk.py delete    "<방 정확제목>" "<본문/파일명 일부>" [--me]
  python kk.py check     "<방 정확제목>"          # 전송 없이 창 상태만 복구·점검

모든 전송은 🔴대상 방 정확일치 가드 + 전송직전 재확인 + 전송후 3중 검증을 통과해야만 성공으로 본다.
"""
import json
import os
import sys
import time

import kklib as K
import kkensure as E
import kksafe as S
import kkfast as F


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    cmd, room = sys.argv[1], sys.argv[2]
    rest = sys.argv[3:]

    if cmd == "check":
        t0 = time.time()
        E.ensure_room(room)
        w = K.find_room(room)
        p, s = K.g(w, "AXPosition"), K.g(w, "AXSize")
        print(json.dumps({
            "ok": True, "room": K.g(w, "AXTitle"),
            "pos": [int(p.x), int(p.y)], "size": [int(s.width), int(s.height)],
            "frontmost": S.frontmost_app(), "focused_window": S.focused_window_title(),
            "rows": K.snapshot_light(room, tail=2), "elapsed": round(time.time() - t0, 2),
            "recovery": E.LOG,
        }, ensure_ascii=False, indent=1))
        return

    if cmd == "send-file":
        files = [os.path.abspath(x) for x in rest]
        if not files:
            sys.exit("파일을 지정하세요")
        t0 = time.time()
        E.ensure_room(room)
        results = []
        for f in files:
            results.append(F.send_file_fast(room, f, ensured=True))
        print(json.dumps({"ok": True, "count": len(files),
                          "total_sec": round(time.time() - t0, 1),
                          "per_file": [r["timing"]["total"] for r in results],
                          "results": [{"found": r["found_in_room"], "rows": r["rows"],
                                       "contamination": r["contamination"]} for r in results]},
                         ensure_ascii=False, indent=1))
        return

    if cmd == "send-text":
        r = S.send_text(room, rest[0])
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return

    if cmd == "delete":
        import subprocess
        args = ["python", os.path.join(os.path.dirname(os.path.abspath(__file__)), "kk_del2.py"),
                room] + rest
        sys.exit(subprocess.call([sys.executable] + args[1:]))

    print(__doc__)
    sys.exit(2)


if __name__ == "__main__":
    main()
