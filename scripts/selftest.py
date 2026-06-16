#!/usr/bin/env python3
"""
kakao_manager selftest — 설치/세팅 자가진단 (읽기 전용, 메시지 전송 안 함)

체크 항목:
  1) uv 설치
  2) 카카오톡 Mac 앱 실행
  3) 카카오톡 로그인 상태 (창 이름이 '로그인'이 아님)
  4) 접근성 권한 (atomacos 로 카톡 enumerate 가능)
  5) config.json 유효성 (활성 계정 id/pw/표시명)
  6) 메인창 탐지
  7) 채팅 목록 읽힘 (AXRow > 0; 친구 탭이면 0일 수 있어 WARN)
  8) (나) 자기채팅 식별 ('badge me' AXImage 탐지; 없으면 WARN)

실행 (atomacos 필요):
  uv run --with atomacos --python 3.12 python selftest.py
  uv run --with atomacos --python 3.12 python selftest.py --json
  uv run --with atomacos --python 3.12 python selftest.py --account work

종료코드: FAIL 이 하나라도 있으면 1, 아니면 0. (WARN 은 0)
"""
import argparse, json, os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PY = HERE / "config.py"
BUNDLE = "com.kakao.KakaoTalkMac"
MAIN_TITLES = ("카카오톡", "KakaoTalk")

PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"


def ascript(s):
    r = subprocess.run(["osascript", "-e", s], capture_output=True, text=True)
    return r.stdout.strip(), r.returncode


def check_uv():
    for p in (Path.home() / ".local/bin/uv", Path("/opt/homebrew/bin/uv"), Path("/usr/local/bin/uv")):
        if p.exists():
            return PASS, str(p)
    from shutil import which
    w = which("uv")
    return (PASS, w) if w else (FAIL, "uv 미설치 → curl -LsSf https://astral.sh/uv/install.sh | sh")


def check_running():
    out, _ = ascript('tell application "System Events" to (name of processes) contains "KakaoTalk"')
    if out == "true":
        return PASS, "실행 중"
    return FAIL, "카톡 앱 미실행 → open -a KakaoTalk"


def check_login():
    out, rc = ascript('tell application "System Events" to tell process "KakaoTalk" to get name of every window')
    if rc != 0:
        return WARN, "창 목록 조회 실패 (접근성 권한 확인 필요)"
    if "로그인" in out:
        return FAIL, "로그인 창이 떠 있음 → 자동 로그인 시퀀스 필요 (SKILL.md 2.1)"
    if not out.strip():
        return WARN, "창이 없음 — 로그인 상태 불명. open -a KakaoTalk 로 메인창을 열어 확인"
    return PASS, f"로그인됨 (창: {out[:60]})"


def get_app():
    try:
        import atomacos
        return atomacos.getAppRefByBundleId(BUNDLE)
    except Exception as e:
        return None


def find_role_all(el, role, out, depth=0, max_depth=14):
    if depth > max_depth:
        return
    try:
        if el.AXRole == role:
            out.append(el)
        for ch in (el.AXChildren or []):
            find_role_all(ch, role, out, depth + 1, max_depth)
    except Exception:
        pass


def run_checks(account):
    results = []

    def add(name, status, detail=""):
        results.append({"name": name, "status": status, "detail": detail})

    s, d = check_uv();        add("uv 설치", s, d)
    s, d = check_running();   add("카톡 앱 실행", s, d)
    running_ok = (s == PASS)
    s, d = check_login();     add("카톡 로그인", s, d)

    # config 유효성
    args = [sys.executable, str(CONFIG_PY), "--check"]
    if account:
        args = [sys.executable, str(CONFIG_PY), "--account", account, "--check"]
    try:
        r = subprocess.run(args, capture_output=True, text=True)
        cfg_ok = r.returncode == 0
        line = (r.stdout.strip().splitlines() or [""])[-1]
        add("config.json 유효", PASS if cfg_ok else FAIL, (r.stdout + r.stderr).strip()[:200])
    except Exception as e:
        add("config.json 유효", FAIL, str(e))

    # atomacos 기반 (앱 실행 안 되면 skip)
    if not running_ok:
        add("접근성 권한", SKIP, "앱 미실행으로 건너뜀")
        add("메인창 탐지", SKIP, "")
        add("채팅 목록 읽힘", SKIP, "")
        add("(나) 자기채팅 식별", SKIP, "")
        return results

    try:
        import atomacos  # noqa
    except Exception:
        add("접근성 권한", FAIL, "atomacos import 실패 → uv run --with atomacos 로 실행")
        add("메인창 탐지", SKIP, "")
        add("채팅 목록 읽힘", SKIP, "")
        add("(나) 자기채팅 식별", SKIP, "")
        return results

    app = get_app()
    if not app:
        add("접근성 권한", FAIL, "카톡 enumerate 불가 → 시스템 설정>개인정보>손쉬운 사용에서 터미널 권한 ON")
        add("메인창 탐지", SKIP, "")
        add("채팅 목록 읽힘", SKIP, "")
        add("(나) 자기채팅 식별", SKIP, "")
        return results
    add("접근성 권한", PASS, "atomacos enumerate OK")

    main = None
    try:
        for w in app.windows():
            if w.AXTitle in MAIN_TITLES:
                main = w
                break
    except Exception as e:
        add("메인창 탐지", FAIL, str(e))
        return results
    if not main:
        add("메인창 탐지", WARN, "메인창(카카오톡) 안 보임 — 창이 닫혀있을 수 있음")
        add("채팅 목록 읽힘", SKIP, "")
        add("(나) 자기채팅 식별", SKIP, "")
        return results
    add("메인창 탐지", PASS, "")

    rows = []
    find_role_all(main, "AXRow", rows, max_depth=12)
    if rows:
        add("채팅 목록 읽힘", PASS, f"row {len(rows)}개")
    else:
        add("채팅 목록 읽힘", WARN, "row 0개 — 채팅 탭이 아닐 수 있음 (Cmd+2로 채팅 탭 전환 후 재시도)")

    found_me = False
    for row in rows:
        imgs = []
        find_role_all(row, "AXImage", imgs, max_depth=8)
        for im in imgs:
            try:
                if im.AXDescription == "badge me":
                    found_me = True
                    break
            except Exception:
                pass
        if found_me:
            break
    if found_me:
        add("(나) 자기채팅 식별", PASS, "'badge me' 탐지됨")
    else:
        add("(나) 자기채팅 식별", WARN, "'badge me' 미탐지 — 목록에 (나) 채팅이 안 보이거나 스크롤 필요")

    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--account", metavar="KEY", help="검사할 계정 key (기본: active)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    results = run_checks(args.account)
    has_fail = any(r["status"] == FAIL for r in results)

    if args.json:
        print(json.dumps({"ok": not has_fail, "results": results}, ensure_ascii=False, indent=2))
    else:
        icon = {PASS: "✅", FAIL: "❌", WARN: "⚠️ ", SKIP: "⏭️ "}
        print("=== kakao_manager 자가진단 ===")
        for r in results:
            print(f"{icon.get(r['status'],'?')} {r['name']}: {r['status']}" + (f" — {r['detail']}" if r['detail'] else ""))
        print("---")
        print("결과: " + ("❌ 실패 항목 있음 (위 FAIL 해결 필요)" if has_fail else "✅ 통과 (WARN은 참고)"))

    sys.exit(1 if has_fail else 0)


if __name__ == "__main__":
    main()
