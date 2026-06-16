# kakao_manager 새 맥 셋업 체크리스트

> **대상**: 이 스킬을 **새 Mac에 클론해서 처음 세팅하는 담당자**.
> 카카오 계정의 **ID/비번**을 가진 사람이어야 하며(또는 옆에서 입력 가능해야 함), 세팅 중 카톡 자동 로그인을 1회 수행한다.

자격증명·작업대상은 **레포 밖**(`~/.config/kakao_manager/`)에 저장되며 git에 커밋되지 않는다. 클론만으로는 동작하지 않고, 아래 세팅을 거쳐야 한다.

---

## 0. 선행 요구사항

- [ ] macOS + **카카오톡 Mac 앱** 설치 (App Store)
- [ ] **uv** 설치 — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- [ ] **접근성 권한**: 시스템 설정 → 개인정보 보호 및 보안 → **손쉬운 사용**에서 터미널/Claude Code 토글 **ON**
- [ ] (공지 캡처 작업 시) **화면 기록 권한** 같은 위치에서 ON
- [ ] 메시지 읽기/전송 코어 플러그인 클론:
      `git clone https://github.com/team-attention/plugins-for-claude-natives.git ~/github/plugins-for-claude-natives`

## 1. 스킬 클론

```bash
git clone https://github.com/bnam91/kakao-manager.git ~/.claude/skills/kakao_manager
```

- [ ] `~/.claude/skills/kakao_manager`에 클론됨

## 2. 계정(자격증명) 등록 — ID·비번·표시명·채팅방 확인

가장 쉬운 방법: Claude에게 **"카톡 매니저 처음 써, 셋업 도와줘"** 라고 하면 대화로 하나씩 물어보고 채워준다. 이때 확인받는 항목:

- [ ] **카카오 ID** (전화번호 또는 이메일)
- [ ] **비밀번호** (받는 즉시 config에만 기입, 평문 재출력 안 함)
- [ ] **본인 카톡 표시명** — (나) 자기채팅 식별·동명이인 구분용
- [ ] **자주 쓰는 채팅방 별칭** (선택) — `별명 → 정확한 채팅방명` 쌍

수동으로 하려면:
```bash
cd ~/.claude/skills/kakao_manager
python3 scripts/config.py --init          # ~/.config/kakao_manager/config.json 생성
# 파일 열어 accounts.default 의 id/pw/self_display_name/aliases 채우기
python3 scripts/config.py --check         # 채워졌는지 검증 (OK 떠야 함)
```

## 3. 계정 추가 (ID/비번 더 등록할 때)

업무폰 등 **여러 계정**을 쓰면 계정을 추가한다. 다시 **아이디·비번·표시명·별칭·실제 채팅방명**을 확인받아 등록:

```bash
# 대화형: Claude에게 "카톡 계정 하나 더 추가해줘" → work 등 key로 인터뷰 후 기입
# 수동:
echo '{"label":"업무폰","kakao":{"id":"<ID>","pw":"<PW>"},"self_display_name":"<표시명>","aliases":[{"keywords":["<별명>"],"chat_name":"<정확한 채팅방명>"}]}' \
  | python3 scripts/config.py --set-account work
python3 scripts/config.py --set-active work   # 기본 계정 지정(선택)
python3 scripts/config.py --accounts          # 등록된 계정 확인
```

- [ ] 계정별 `--check` 통과

## 4. 자가진단 (읽기 전용 — 메시지 안 보냄)

```bash
cd ~/.claude/skills/kakao_manager
source $HOME/.local/bin/env && \
  uv run --with atomacos --python 3.12 python scripts/selftest.py
# 특정 계정: 끝에 --account work
```

- [ ] uv / 앱실행 / 로그인 / 접근성 / config / 메인창 / 채팅목록 / (나) 식별 **모두 ✅** (FAIL 0)
- [ ] 카톡이 **로그인 창**이면: Claude에게 "카톡 자동 로그인 해줘" (SKILL.md §2.1)

## 5. 전송 테스트 (선택, 1건 실제 발송 — 먼저 물어봄)

- [ ] **나와의 채팅**으로 안전 테스트:
```bash
cd ~/.claude/skills/kakao_manager/scripts
source $HOME/.local/bin/env && \
  uv run --with atomacos --python 3.12 python send_safe.py "$(python3 config.py --self-name)" \
    --text "✅ kakao_manager 세팅 테스트" --verify-me --json
```
- [ ] 결과 `ok:true` + `rows_before→rows_after` 증가 확인

## 6. (선택) 타겟 = 작업할 방 묶음 등록

특정 방 집합(예: 체험단 N개 방)을 반복 작업하려면 **타겟**으로 등록(레포 밖 저장):
```bash
python3 scripts/targets.py --init <이름>     # 템플릿 생성
# ~/.config/kakao_manager/targets/<이름>.json 의 account/prefix/rooms 채우기
python3 scripts/targets.py --list
```
이후 `"<이름> 방들 일괄조사해줘"` / `"<이름> 방들에 이거 보내줘"`로 사용. (SKILL.md §13)

---

## ⚠️ 주의

- `config.json`(비번)·`targets/`(작업대상)은 **절대 git 커밋 금지** — `.gitignore`로 차단됨, `~/.config`에만 둔다.
- 비번은 `config.py --login-env`로 환경변수 주입만 하고 평문 출력하지 않는다.
- 카톡을 함부로 `killall`/재시작하면 **로그아웃**된다(자동로그인 유지 안 됨).
