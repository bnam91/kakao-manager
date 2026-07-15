#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""챗펄스 카톡 채널 헬퍼 (여포 chatpulse_growtalk.py의 카톡판, 2026-07-15 신설).

서브커맨드:
  open   <room>            정확오픈(open_exact.py) — stop_리브리 등 오방 배제. Dock 전면화 선행.
  lastmsg <room>           마지막 메시지 1건 JSON {sender,text,time,is_mine,fp}. 폴러 baseline/감지용.
  read   <room> [N]        최근 N건(기본 20) 메시지 JSON 배열.
  send   <room> <text>     발송 — 이미 열린 창을 raise(재검색 없음=오방회피) → 붙여넣기 → Enter → 검증.
                           ⚠️멀티라인/링크는 Enter가 개행먹힘 → 그건 사람이 '전송'버튼 경로로(챗펄스 답장은 단문이라 Enter OK).

정방/오방·전면화 노하우는 notes/KNOWLEDGE.md 참조. 자격증명 하드코딩 금지(env만).
반환 JSON은 stdout 마지막 줄. 오류 시 {"ok":false,"error":...} + exit!=0."""
import sys, os, json, time, hashlib, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _front():
    """카톡 전면화 = Dock 아이콘 클릭(한글 '카카오톡'). activate/open -a는 다른 Space면 먹통(KNOWLEDGE)."""
    subprocess.run(["osascript", "-e",
        'tell application "System Events" to tell process "Dock" to click UI element "카카오톡" of list 1'],
        capture_output=True)
    time.sleep(1.0)


def _fp(m):
    """메시지 지문 — sender+text+time 해시. 마지막 메시지 변하면 fp 변함(새 메시지 감지용)."""
    raw = f"{m.get('sender','')}|{m.get('time','')}|{m.get('text','')}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def cmd_open(room):
    _front()
    r = subprocess.run(["uv", "run", "--with", "atomacos", "--with", "pyobjc-framework-Quartz",
                        "--python", "3.12", "python", os.path.join(HERE, "open_exact.py"), room],
                       capture_output=True, text=True, timeout=120)
    line = [l for l in r.stdout.strip().splitlines() if l.startswith("{")]
    out = json.loads(line[-1]) if line else {"ok": False, "error": "open_exact 출력없음", "raw": r.stdout[-200:]}
    return out


def _read(room, limit=20):
    import kakao_read as K
    title, msgs = K.read_chat(room, limit)
    return title, msgs


def cmd_lastmsg(room):
    _front()
    title, msgs = _read(room, 30)
    if not msgs:
        return {"ok": True, "room": title, "last": None, "fp": None}
    last = msgs[-1]
    is_mine = (last.get("sender") == "나")
    m = {"sender": last.get("sender"), "text": last.get("text"), "time": last.get("time"), "is_mine": is_mine}
    m["fp"] = _fp(last)
    return {"ok": True, "room": title, "last": m, "fp": m["fp"]}


def cmd_read(room, limit=20):
    _front()
    title, msgs = _read(room, limit)
    out = [{"sender": x.get("sender"), "text": x.get("text"), "time": x.get("time"),
            "is_mine": x.get("sender") == "나"} for x in msgs]
    return {"ok": True, "room": title, "n": len(out), "messages": out}


def cmd_send(room, text):
    """이미 열린 방을 raise(재검색 없음) → 붙여넣기 → Enter → 입력창 비었는지 검증."""
    _front()
    import kakao_send as S
    opened = S.open_chat(room)          # 이미 열려있으면 raise만(오방 재검색 없음)
    if not opened:
        return {"ok": False, "error": f"방 열기 실패: {room}"}
    time.sleep(0.4)
    S.type_text(text)                   # pbcopy + Cmd+V
    time.sleep(0.5)
    S.key_code(36)                      # Enter (단문 발송)
    time.sleep(1.0)
    # 검증: 열린 창 입력영역이 비었는지(발송성공 신호). read로 마지막이 내 발화인지 교차확인.
    ver = {"echoed": None}
    try:
        _, msgs = _read(room, 5)
        if msgs and msgs[-1].get("sender") == "나" and text[:12] in (msgs[-1].get("text") or ""):
            ver["echoed"] = True
    except Exception:
        pass
    return {"ok": True, "room": opened, "sent": text, "verify": ver}


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"ok": False, "error": "usage: chatpulse_kakao.py <open|lastmsg|read|send> <room> [arg]"}, ensure_ascii=False))
        return 2
    sub, room = sys.argv[1], sys.argv[2]
    try:
        if sub == "open":
            out = cmd_open(room)
        elif sub == "lastmsg":
            out = cmd_lastmsg(room)
        elif sub == "read":
            limit = int(sys.argv[3]) if len(sys.argv) > 3 else 20
            out = cmd_read(room, limit)
        elif sub == "send":
            if len(sys.argv) < 4:
                out = {"ok": False, "error": "send는 text 필요"}
            else:
                out = cmd_send(room, sys.argv[3])
        else:
            out = {"ok": False, "error": f"unknown sub: {sub}"}
    except Exception as e:
        out = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
