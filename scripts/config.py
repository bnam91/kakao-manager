#!/usr/bin/env python3
"""
kakao_manager config — 개인 설정(JSON) 로더 (다중 계정 지원)

설정 위치 우선순위:
  1) 환경변수 $KAKAO_CONFIG 가 가리키는 파일
  2) ~/.config/kakao_manager/config.json  (권장)

계정 선택 우선순위:
  1) --account <key>  (CLI)
  2) 환경변수 $KAKAO_ACCOUNT
  3) config.json 의 "active"
  4) accounts 의 첫 번째 key

사용:
  config.py --init                       # 템플릿을 권장 위치로 복사 (없을 때만)
  config.py --check                      # 모든 계정 유효성 점검 (id/pw/self 채워졌는지)
  config.py --accounts                   # 등록된 계정 key 목록
  config.py --login-env                  # 활성 계정의 KAKAO_ID/PW 를 sh export 형식으로 출력 (eval 용)
  config.py --self-name                  # 활성 계정 본인 표시명
  config.py --resolve "별명"              # 활성 계정 alias keyword -> chat_name (없으면 입력 그대로)
  config.py --dump                       # 비밀번호 가린 전체 설정(JSON)
  config.py --account work --login-env   # 특정 계정 지정

  # 온보딩(대화로 받은 답을 기입). 계정 객체 JSON 을 stdin 으로:
  echo '{"label":"메인","kakao":{"id":"...","pw":"..."},"self_display_name":"...","aliases":[]}' \
    | config.py --set-account default
  config.py --set-active default         # 활성 계정 지정
"""
import argparse, json, os, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE / "config.example.json"
DEFAULT_PATH = Path.home() / ".config" / "kakao_manager" / "config.json"


def config_path() -> Path:
    env = os.environ.get("KAKAO_CONFIG")
    return Path(env).expanduser() if env else DEFAULT_PATH


def load() -> dict:
    p = config_path()
    if not p.exists():
        sys.stderr.write(
            f"[kakao_manager] 설정 파일이 없습니다: {p}\n"
            f"  → 먼저 실행: python3 {HERE}/config.py --init\n"
            f"  → 그다음 파일을 열어 본인 값(id/pw/표시명/채팅방)을 채우세요.\n"
        )
        sys.exit(3)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.stderr.write(f"[kakao_manager] config.json 파싱 실패: {e}\n")
        sys.exit(3)


def accounts(cfg: dict) -> dict:
    accs = cfg.get("accounts")
    if not isinstance(accs, dict) or not accs:
        sys.stderr.write("[kakao_manager] config.json 에 accounts 가 없습니다.\n")
        sys.exit(3)
    return accs


def pick_account(cfg: dict, cli_account: str | None) -> tuple[str, dict]:
    accs = accounts(cfg)
    key = cli_account or os.environ.get("KAKAO_ACCOUNT") or cfg.get("active")
    if not key or key not in accs:
        key = next(iter(accs))  # 첫 번째
    return key, accs[key]


def cmd_init():
    p = config_path()
    if p.exists():
        print(f"이미 존재: {p} (덮어쓰지 않음)")
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(EXAMPLE, p)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    print(f"생성됨: {p}\naccounts.<key> 아래 kakao.id / kakao.pw / self_display_name / aliases 를 채우세요.")


def cmd_check(cli_account):
    cfg = load()
    accs = accounts(cfg)
    all_ok = True
    for key, acc in accs.items():
        problems = []
        if not acc.get("kakao", {}).get("id"):
            problems.append("kakao.id")
        if not acc.get("kakao", {}).get("pw"):
            problems.append("kakao.pw")
        if not acc.get("self_display_name"):
            problems.append("self_display_name")
        label = acc.get("label", "")
        if problems:
            all_ok = False
            print(f"⚠️  [{key}] {label} — 미입력: {', '.join(problems)}")
        else:
            print(f"✓ [{key}] {label} — OK")
    active = cfg.get("active")
    print(f"활성 계정(active): {active}")
    sys.exit(0 if all_ok else 1)


def cmd_accounts():
    cfg = load()
    active = cfg.get("active")
    for key, acc in accounts(cfg).items():
        mark = " *(active)" if key == active else ""
        print(f"{key}\t{acc.get('label','')}{mark}")


def sh_quote(v) -> str:
    return "'" + str(v).replace("'", "'\\''") + "'"


def cmd_login_env(cli_account):
    cfg = load()
    key, acc = pick_account(cfg, cli_account)
    k = acc.get("kakao", {})
    if not k.get("id") or not k.get("pw"):
        sys.stderr.write(f"[kakao_manager] [{key}] kakao.id/pw 가 비어있습니다. config.json 을 채우세요.\n")
        sys.exit(1)
    # eval "$(config.py --login-env)" 로 사용
    print(f"export KAKAO_ID={sh_quote(k['id'])}")
    print(f"export KAKAO_PW={sh_quote(k['pw'])}")


def cmd_self_name(cli_account):
    cfg = load()
    _, acc = pick_account(cfg, cli_account)
    print(acc.get("self_display_name", ""))


def cmd_resolve(keyword, cli_account):
    cfg = load()
    _, acc = pick_account(cfg, cli_account)
    kw = keyword.strip().lower()
    for a in acc.get("self_aliases", []):
        if a.lower() == kw:
            print(acc.get("self_display_name", keyword))
            return
    for entry in acc.get("aliases", []):
        for k in entry.get("keywords", []):
            if k.lower() == kw or kw in k.lower() or k.lower() in kw:
                print(entry.get("chat_name", keyword))
                return
    print(keyword)  # 매칭 없으면 입력 그대로


def _load_or_skeleton() -> dict:
    p = config_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"active": None, "accounts": {}}


def _save(cfg: dict):
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def cmd_set_account(key):
    """stdin 으로 받은 계정 객체 JSON 을 accounts[key] 에 병합. 기존 다른 계정은 보존."""
    raw = sys.stdin.read().strip()
    if not raw:
        sys.stderr.write("[kakao_manager] stdin 으로 계정 JSON 을 넘기세요.\n")
        sys.exit(2)
    try:
        acc = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"[kakao_manager] 입력 JSON 파싱 실패: {e}\n")
        sys.exit(2)
    if not isinstance(acc, dict) or "kakao" not in acc:
        sys.stderr.write("[kakao_manager] 계정 객체에 kakao.{id,pw} 가 필요합니다.\n")
        sys.exit(2)
    acc.setdefault("self_aliases", ["나", "self", "본인"])
    acc.setdefault("aliases", [])
    cfg = _load_or_skeleton()
    cfg.setdefault("accounts", {})
    cfg["accounts"][key] = acc
    if not cfg.get("active"):
        cfg["active"] = key
    _save(cfg)
    print(f"✓ 계정 '{key}' 저장됨 ({config_path()})")


def cmd_set_active(key):
    cfg = _load_or_skeleton()
    if key not in cfg.get("accounts", {}):
        sys.stderr.write(f"[kakao_manager] '{key}' 계정이 없습니다. 먼저 --set-account 로 추가하세요.\n")
        sys.exit(1)
    cfg["active"] = key
    _save(cfg)
    print(f"✓ 활성 계정 = '{key}'")


def cmd_dump():
    cfg = load()
    for acc in accounts(cfg).values():
        if acc.get("kakao", {}).get("pw"):
            acc["kakao"]["pw"] = "***"
    print(json.dumps(cfg, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--account", metavar="KEY", help="사용할 계정 key (기본: active)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--init", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--accounts", action="store_true")
    g.add_argument("--login-env", action="store_true")
    g.add_argument("--self-name", action="store_true")
    g.add_argument("--resolve", metavar="KEYWORD")
    g.add_argument("--dump", action="store_true")
    g.add_argument("--set-account", metavar="KEY", help="stdin JSON 을 해당 계정에 병합 저장")
    g.add_argument("--set-active", metavar="KEY", help="활성 계정 지정")
    args = p.parse_args()

    if args.init:
        cmd_init()
    elif args.check:
        cmd_check(args.account)
    elif args.accounts:
        cmd_accounts()
    elif args.login_env:
        cmd_login_env(args.account)
    elif args.self_name:
        cmd_self_name(args.account)
    elif args.resolve:
        cmd_resolve(args.resolve, args.account)
    elif args.dump:
        cmd_dump()
    elif args.set_account:
        cmd_set_account(args.set_account)
    elif args.set_active:
        cmd_set_active(args.set_active)


if __name__ == "__main__":
    main()
