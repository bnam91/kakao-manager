# kakao_manager

카카오톡 Mac 앱을 **Claude Code 터미널에서 직접 조작**하는 매니저 스킬.
[team-attention/kakaotalk](https://github.com/team-attention/plugins-for-claude-natives) 플러그인을 래핑해서 채팅방 검색·목록·메시지 읽기·날짜필터·요약·전송·이미지 전송·(나) 자기채팅 식별·자동 로그인을 일관된 방식으로 처리한다.

## 설치 (다른 맥에 클론해서 쓰기)

```bash
# 1) 스킬 디렉터리에 클론
git clone https://github.com/bnam91/kakao-manager.git ~/.claude/skills/kakao_manager

# 2) 개인 설정 생성 (자격증명/채팅방은 레포 밖 ~/.config 에 저장 — 절대 커밋 안 됨)
cd ~/.claude/skills/kakao_manager
python3 scripts/config.py --init
# ~/.config/kakao_manager/config.json 을 열어 accounts.<key> 의 id/pw/표시명 입력
python3 scripts/config.py --check

# 3) 자가진단 (읽기 전용, 메시지 안 보냄)
source $HOME/.local/bin/env && \
  uv run --with atomacos --python 3.12 python scripts/selftest.py
```

> 처음 실행이면 Claude에게 "카톡 매니저 처음 써, 셋업 도와줘"라고 하면 대화형으로 config를 채워준다. (SKILL.md §0.5)

## 요구사항

- macOS + 카카오톡 Mac 앱
- [uv](https://docs.astral.sh/uv/) (`atomacos`를 on-the-fly 설치)
- **접근성 권한**: 시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용에서 터미널/Claude Code 토글 ON

## 구조

| 파일 | 역할 |
|---|---|
| `SKILL.md` | 전체 운영 절차 + 실전 함정 (Claude가 읽는 본체) |
| `scripts/config.py` | 다중 계정 자격증명/채팅방 alias 관리 (레포 밖 JSON) |
| `scripts/config.example.json` | 설정 템플릿 |
| `scripts/selftest.py` | 자가진단 (uv/로그인/권한/config/(나) 식별) |
| `scripts/send_safe.py` | 안전 전송 (이름 정규화 + (나) 검증 가드) |

메시지 읽기/전송 코어(`kakao_read.py` / `kakao_send.py`)는 위 플러그인 레포에서 가져온다.

## 보안

- `config.json`(자격증명)은 **레포 밖** `~/.config/kakao_manager/`에 0600 권한으로 저장되며 `.gitignore`로 커밋이 차단된다.
- 비밀번호는 `config.py --login-env`로 환경변수 주입만 하고 평문 출력하지 않는다.

## 라이선스

MIT
