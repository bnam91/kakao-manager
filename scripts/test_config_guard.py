#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""config.py 가드 테스트 — ★실제 config 는 안 건드린다($KAKAO_CONFIG 로 임시파일 사용).
실행: python3 test_config_guard.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "config.py")

BASE = {
    "active": "default",
    "accounts": {
        "default": {
            "label": "테스트",
            "kakao": {"id": "test@example.com", "pw": "SECRET-PW"},
            "self_display_name": "테스터",
            "self_aliases": ["나", "self", "본인"],
            "aliases": [
                {"keywords": ["세무", "세무방", "세무관련"], "chat_name": "[세무관련] 고야"},
                {"keywords": ["프라임", "3pl"], "chat_name": "(3pl) 프라임컴퍼니"},
                {"keywords": ["태스크"], "chat_name": "고야태스크"},
            ],
        }
    },
}

ok = fail = 0
tmpdir = tempfile.mkdtemp(prefix="kakao_cfg_test_")
path = os.path.join(tmpdir, "config.json")


def write_base():
    json.dump(BASE, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def run(args, stdin=None):
    env = dict(os.environ, KAKAO_CONFIG=path)
    return subprocess.run([sys.executable, CFG] + args, input=stdin,
                          capture_output=True, text=True, env=env)


def check(desc, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✅ {desc}")
    else:
        fail += 1
        print(f"  ❌ {desc} {extra}")


write_base()
print("=== 1) --resolve: 확정/미등록/모호 구분 ===")
r = run(["--resolve", "세무방"])
check("등록된 별명 → 방이름 + exit0", r.returncode == 0 and r.stdout.strip() == "[세무관련] 고야",
      f"(rc={r.returncode} out={r.stdout.strip()!r})")

r = run(["--resolve", "리브리"])          # 어떤 별명에도 안 걸리는 이름
check("미등록 → 입력 그대로 출력 + ★exit3 + stderr 경고",
      r.returncode == 3 and r.stdout.strip() == "리브리" and "등록된 별명이 아닙니다" in r.stderr,
      f"(rc={r.returncode} err={r.stderr.strip()[:60]!r})")

r = run(["--resolve", "리브리", "--strict"])
check("--strict 면 미등록도 실패(exit2)·stdout 없음",
      r.returncode == 2 and r.stdout.strip() == "", f"(rc={r.returncode} out={r.stdout!r})")

r = run(["--resolve", "태스"])   # 키워드 "태스크" 에 부분일치(완전일치 아님)
check("부분일치(후보 유일)는 통과하되 ★stderr 경고를 남긴다",
      r.returncode == 0 and r.stdout.strip() == "고야태스크" and "부분일치" in r.stderr,
      f"(rc={r.returncode} out={r.stdout.strip()!r} err={r.stderr.strip()[:60]!r})")

# ★실제 위험 재현: 서로 다른 방의 별명이 같은 요청어를 품으면 골라선 안 된다
BASE["accounts"]["default"]["aliases"][0]["keywords"].append("세무 고야")
BASE["accounts"]["default"]["aliases"][2]["keywords"].append("고야 태스크")
write_base()
r = run(["--resolve", "고야"])
check("★후보 2개(다른 방) → 모호 중단(exit2, stdout 없음)",
      r.returncode == 2 and r.stdout.strip() == "" and "후보가" in r.stderr,
      f"(rc={r.returncode} err={r.stderr.strip()[:80]!r})")
BASE["accounts"]["default"]["aliases"][0]["keywords"].remove("세무 고야")
BASE["accounts"]["default"]["aliases"][2]["keywords"].remove("고야 태스크")
write_base()

r = run(["--resolve", "나"])
check("self_alias → 본인 표시명", r.returncode == 0 and r.stdout.strip() == "테스터",
      f"(out={r.stdout.strip()!r})")

print("=== 2) --set-account: 부분 JSON 으로 비번이 날아가지 않는가 ===")
r = run(["--set-account", "default"],
        stdin=json.dumps({"aliases": [{"keywords": ["새방"], "chat_name": "새 방"}]}, ensure_ascii=False))
saved = json.load(open(path, encoding="utf-8"))
acc = saved["accounts"]["default"]
check("부분 JSON(aliases만) 저장 성공", r.returncode == 0, f"(rc={r.returncode} err={r.stderr[:80]!r})")
check("★기존 kakao.pw 보존됨", acc["kakao"].get("pw") == "SECRET-PW", f"(pw={acc['kakao'].get('pw')!r})")
check("★기존 kakao.id 보존됨", acc["kakao"].get("id") == "test@example.com")
check("넘긴 aliases 로 갱신됨", acc["aliases"] == [{"keywords": ["새방"], "chat_name": "새 방"}])
check("self_display_name 보존", acc.get("self_display_name") == "테스터")

write_base()
r = run(["--set-account", "default"], stdin=json.dumps({"kakao": {"pw": "NEW-PW"}}, ensure_ascii=False))
acc = json.load(open(path, encoding="utf-8"))["accounts"]["default"]
check("중첩 dict 부분갱신: pw만 바꾸고 id 유지",
      acc["kakao"] == {"id": "test@example.com", "pw": "NEW-PW"}, f"(kakao={acc['kakao']})")

write_base()
r = run(["--set-account", "새계정"], stdin=json.dumps({"label": "자격증명없음"}, ensure_ascii=False))
after = json.load(open(path, encoding="utf-8"))
check("★신규 계정인데 id/pw 없으면 저장 거부(exit2)",
      r.returncode == 2 and "새계정" not in after["accounts"], f"(rc={r.returncode})")

print("=== 3) --replace-account: 명시적 교체만 통째 갈아끼움 ===")
write_base()
full = {"label": "교체됨", "kakao": {"id": "new@example.com", "pw": "PW2"}, "self_display_name": "새이름"}
r = run(["--replace-account", "default"], stdin=json.dumps(full, ensure_ascii=False))
acc = json.load(open(path, encoding="utf-8"))["accounts"]["default"]
check("교체 후 새 값만 남음", r.returncode == 0 and acc["label"] == "교체됨" and acc["aliases"] == [],
      f"(rc={r.returncode} acc={acc.get('label')})")

print(f"\n결과: ✅{ok} / ❌{fail}   (임시 config: {path})")
sys.exit(1 if fail else 0)
