#!/usr/bin/env python3
"""
kakao_manager targets — '타겟(방 묶음)' 데이터 레이어

타겟이란?
  반복 작업(일괄조사·브로드캐스트)의 대상이 되는 **고정된 오픈채팅방 집합**.
  예: "○○체험단" = 수십 개 방 묶음. 캠페인(고정 메시지)이 아니라, 그때그때 다른
  작업을 돌릴 대상 목록이다. 실 타겟은 레포 밖 ~/.config 에 저장(커밋 금지).

저장 위치 우선순위:
  1) 환경변수 $KAKAO_TARGETS_DIR
  2) ~/.config/kakao_manager/targets/<name>.json

사용:
  targets.py --list                      # 등록된 타겟 목록
  targets.py --init <name>               # 템플릿을 <name>.json 으로 복사 (없을 때만)
  targets.py --show <name>               # 타겟 전체(JSON)
  targets.py --rooms <name>              # 방 제목만 한 줄씩 (브로드캐스트 루프용)
  targets.py --rooms <name> --field url  # 방의 특정 필드만 (num/title/url/exists)
  targets.py --account <name>            # 타겟이 속한 계정 key 출력 (config.py --account 로 넘김)
  echo '<survey JSON>' | targets.py --save <name> --at 2026-06-16T10:00:00
                                         # 일괄조사 결과(rooms 배열 등)를 타겟에 저장
"""
import argparse, json, os, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE / "target.example.json"


def targets_dir() -> Path:
    env = os.environ.get("KAKAO_TARGETS_DIR")
    base = Path(env).expanduser() if env else Path.home() / ".config" / "kakao_manager" / "targets"
    return base


def target_path(name: str) -> Path:
    return targets_dir() / f"{name}.json"


def load(name: str) -> dict:
    p = target_path(name)
    if not p.exists():
        sys.stderr.write(
            f"[kakao_manager] 타겟이 없습니다: {p}\n"
            f"  → 먼저 실행: python3 {HERE}/targets.py --init {name}\n"
            f"  → 그다음 파일을 열어 account/prefix/rooms 를 채우세요.\n"
        )
        sys.exit(3)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.stderr.write(f"[kakao_manager] {p} 파싱 실패: {e}\n")
        sys.exit(3)


def save(name: str, data: dict):
    p = target_path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def cmd_list():
    d = targets_dir()
    if not d.exists():
        print(f"(타겟 없음 — {d} 미생성)")
        return
    names = sorted(p.stem for p in d.glob("*.json"))
    if not names:
        print(f"(타겟 없음 — {d} 비어있음)")
        return
    for n in names:
        try:
            t = json.loads(target_path(n).read_text(encoding="utf-8"))
            label = t.get("label", "")
            acc = t.get("account", "")
            nrooms = len([r for r in t.get("rooms", []) if r.get("exists", True)])
            print(f"{n}\t{label}\t계정={acc}\t방={nrooms}개")
        except Exception:
            print(f"{n}\t(파싱 실패)")


def cmd_init(name):
    p = target_path(name)
    if p.exists():
        print(f"이미 존재: {p} (덮어쓰지 않음)")
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["name"] = name
    save(name, data)
    print(f"생성됨: {p}\naccount/prefix/number_range/rooms 를 채우세요.")


def cmd_show(name):
    print(json.dumps(load(name), ensure_ascii=False, indent=2))


def cmd_rooms(name, field, only_existing):
    t = load(name)
    for r in t.get("rooms", []):
        if only_existing and not r.get("exists", True):
            continue
        val = r.get(field, "")
        if val:
            print(val)


def cmd_account(name):
    print(load(name).get("account", ""))


def cmd_save(name, at):
    raw = sys.stdin.read().strip()
    if not raw:
        sys.stderr.write("[kakao_manager] stdin 으로 타겟 JSON(또는 {rooms:[...]} ) 을 넘기세요.\n")
        sys.exit(2)
    try:
        incoming = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"[kakao_manager] 입력 JSON 파싱 실패: {e}\n")
        sys.exit(2)
    # 기존 타겟에 병합 (rooms/last_survey 등 갱신, 나머지 키 보존)
    base = {}
    if target_path(name).exists():
        base = load(name)
    base.update(incoming)
    base["name"] = name
    if at:
        base["last_survey"] = at
    save(name, base)
    nrooms = len(base.get("rooms", []))
    print(f"✓ 타겟 '{name}' 저장됨 (방 {nrooms}개, last_survey={base.get('last_survey')})")


def main():
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true")
    g.add_argument("--init", metavar="NAME")
    g.add_argument("--show", metavar="NAME")
    g.add_argument("--rooms", metavar="NAME")
    g.add_argument("--account", metavar="NAME")
    g.add_argument("--save", metavar="NAME")
    p.add_argument("--field", default="title", help="--rooms 출력 필드 (기본 title; num/url/exists)")
    p.add_argument("--all", action="store_true", help="--rooms 시 exists=false 도 포함")
    p.add_argument("--at", help="--save 시 last_survey 에 기록할 ISO 일시")
    args = p.parse_args()

    if args.list:
        cmd_list()
    elif args.init:
        cmd_init(args.init)
    elif args.show:
        cmd_show(args.show)
    elif args.rooms:
        cmd_rooms(args.rooms, args.field, not args.all)
    elif args.account:
        cmd_account(args.account)
    elif args.save:
        cmd_save(args.save, args.at)


if __name__ == "__main__":
    main()
