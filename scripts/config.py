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
  config.py --resolve "별명"              # alias -> chat_name. exit 0=확정 / 3=미등록(입력 그대로 출력·stderr 경고) / 2=모호(출력 없음)
  config.py --resolve "별명" --strict     # 미등록도 실패로 (조용한 통과 완전 차단)
  config.py --dump                       # 비밀번호 가린 전체 설정(JSON)
  config.py --account work --login-env   # 특정 계정 지정

  # 온보딩(대화로 받은 답을 기입). 계정 객체 JSON 을 stdin 으로:
  echo '{"label":"메인","kakao":{"id":"...","pw":"..."},"self_display_name":"...","aliases":[]}' \
    | config.py --set-account default
  config.py --set-active default         # 활성 계정 지정
"""
from __future__ import annotations  # python 3.10 에서 'str | None' 타입힌트 호환
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


def resolve_alias(acc: dict, keyword: str) -> tuple[str, str, list]:
    """별명 → 정확한 방이름. 반환 (결과이름, 상태, 후보목록).

    상태: 'self'(자기채팅) | 'exact'(키워드 완전일치) | 'partial'(부분일치·유일)
          | 'none'(매칭 없음 → 입력 그대로) | 'ambiguous'(후보 2개 이상 → 고르지 않음)

    ★부분일치는 **후보가 유일할 때만** 쓴다. 구판은 `kw in k or k in kw` 로 아무거나 먼저 걸린 걸
      집어서, 키워드 '세무 고야' 때문에 `resolve('고야')` 가 「[세무관련] 고야」로 끌려갔다
      (「고야태스크」가 따로 있는데도). 2026-08-05 실측.
    """
    kw = keyword.strip().lower()
    for a in acc.get("self_aliases", []):
        if a.lower() == kw:
            return acc.get("self_display_name", keyword), "self", []

    exact, partial = [], []
    for entry in acc.get("aliases", []):
        name = entry.get("chat_name", keyword)
        for k in entry.get("keywords", []):
            kl = k.lower()
            if kl == kw:
                exact.append(name)
                break
            if kw in kl or kl in kw:
                partial.append(name)
                break

    uniq_exact = sorted(set(exact))
    if len(uniq_exact) == 1:
        return uniq_exact[0], "exact", uniq_exact
    if len(uniq_exact) > 1:
        return keyword, "ambiguous", uniq_exact

    uniq_partial = sorted(set(partial))
    if len(uniq_partial) == 1:
        return uniq_partial[0], "partial", uniq_partial
    if len(uniq_partial) > 1:
        return keyword, "ambiguous", uniq_partial

    return keyword, "none", []


def cmd_resolve(keyword, cli_account, strict=False):
    """stdout 계약은 유지(=방 이름 한 줄). ★단, 조용히 넘어가지 않는다:
    매칭 없음/모호는 stderr 로 알리고 종료코드로 구분한다.
      0=별명으로 확정(self/exact/partial) · 3=매칭 없음(입력 그대로 출력) · 2=모호(출력 안 함)
    --strict 면 '매칭 없음'도 실패(2)로 올린다."""
    cfg = load()
    _, acc = pick_account(cfg, cli_account)
    name, status, cands = resolve_alias(acc, keyword)

    if status == "ambiguous":
        sys.stderr.write(
            f"[kakao_manager] ★중단: 별명 '{keyword}' 후보가 {len(cands)}개입니다 — 고르지 않습니다.\n"
            f"  후보: {cands}\n  → 정확한 방 이름을 직접 쓰거나 별명을 더 고유하게 만드세요.\n")
        sys.exit(2)

    if status == "none":
        msg = (f"[kakao_manager] 별명 '{keyword}' 은 등록된 별명이 아닙니다 — "
               f"입력값을 그대로 방 이름으로 씁니다(정확일치 필요).\n")
        if strict:
            sys.stderr.write("[kakao_manager] ★중단(--strict): " + msg[len("[kakao_manager] "):])
            sys.exit(2)
        sys.stderr.write(msg)
        print(name)
        sys.exit(3)

    if status == "partial":
        sys.stderr.write(f"[kakao_manager] 주의: '{keyword}' 는 부분일치로 '{name}' 에 걸렸습니다"
                         f"(후보 유일). 의도한 방이 맞는지 확인하세요.\n")
    print(name)


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


def cmd_set_account(key, replace=False):
    """stdin 계정 JSON 을 accounts[key] 에 ★진짜 병합★(기존 값 보존). 기존 다른 계정도 보존.

    ⚠️구판은 docstring 만 '병합'이고 실제로는 `accounts[key] = acc` 로 **통째 교체**했다 —
      문서대로 부분 JSON(예: aliases 만)을 넘기면 **kakao.id/pw 가 통째로 날아갔다.**
      이제 넘긴 키만 덮어쓰고, kakao 같은 중첩 dict 도 키 단위로 병합한다.
      통째로 갈아끼우려면 --replace-account 를 명시적으로 쓴다.
    """
    raw = sys.stdin.read().strip()
    if not raw:
        sys.stderr.write("[kakao_manager] stdin 으로 계정 JSON 을 넘기세요.\n")
        sys.exit(2)
    try:
        incoming = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"[kakao_manager] 입력 JSON 파싱 실패: {e}\n")
        sys.exit(2)
    if not isinstance(incoming, dict):
        sys.stderr.write("[kakao_manager] 계정 JSON 은 객체여야 합니다.\n")
        sys.exit(2)

    cfg = _load_or_skeleton()
    cfg.setdefault("accounts", {})
    existing = cfg["accounts"].get(key) if not replace else None
    if replace:
        acc = incoming
    elif isinstance(existing, dict):
        acc = dict(existing)
        for k, v in incoming.items():
            if isinstance(v, dict) and isinstance(acc.get(k), dict):
                merged = dict(acc[k]); merged.update(v); acc[k] = merged   # kakao.{id,pw} 부분 갱신 허용
            else:
                acc[k] = v
    else:
        acc = incoming

    acc.setdefault("self_aliases", ["나", "self", "본인"])
    acc.setdefault("aliases", [])

    # ★저장 전 검증: 병합 결과에 자격증명이 남아있어야 한다(빈 값으로 덮어쓴 사고 방지)
    kk = acc.get("kakao") or {}
    if not kk.get("id") or not kk.get("pw"):
        sys.stderr.write(
            f"[kakao_manager] ★중단: 저장하면 계정 '{key}' 의 kakao.id/pw 가 비게 됩니다 — 저장하지 않았습니다.\n"
            f"  기존 계정이 없으면 id/pw 를 함께 넘기고, 일부만 고칠 땐 기존 계정이 있는지 먼저 확인하세요.\n")
        sys.exit(2)

    cfg["accounts"][key] = acc
    if not cfg.get("active"):
        cfg["active"] = key
    _save(cfg)
    mode = "교체" if replace else "병합"
    print(f"✓ 계정 '{key}' 저장됨({mode}) ({config_path()})")


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
    p.add_argument("--strict", action="store_true",
                   help="--resolve 전용: 등록된 별명이 아니면 통과시키지 않고 실패(exit 2)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--init", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--accounts", action="store_true")
    g.add_argument("--login-env", action="store_true")
    g.add_argument("--self-name", action="store_true")
    g.add_argument("--resolve", metavar="KEYWORD")
    g.add_argument("--dump", action="store_true")
    g.add_argument("--set-account", metavar="KEY", help="stdin JSON 을 해당 계정에 ★병합★ 저장(기존 id/pw 보존)")
    g.add_argument("--replace-account", metavar="KEY", help="stdin JSON 으로 해당 계정을 ★통째 교체★(기존 값 버림)")
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
        cmd_resolve(args.resolve, args.account, strict=args.strict)
    elif args.dump:
        cmd_dump()
    elif args.set_account:
        cmd_set_account(args.set_account)
    elif args.replace_account:
        cmd_set_account(args.replace_account, replace=True)
    elif args.set_active:
        cmd_set_active(args.set_active)


if __name__ == "__main__":
    main()
