---
name: kakao_manager
description: 카카오톡 Mac 앱을 Claude Code 터미널에서 직접 조작하는 매니저 스킬. 카톡 앱 UI 자동화(atomacos, vendored kakao_read.py/kakao_send.py)로 채팅방 검색/목록/메시지 읽기/날짜필터/요약/메시지 전송/이미지 전송/(나) 자기채팅 식별/자동 로그인을 일관된 방식으로 처리한다. 사용자가 "카톡 매니저", "/kakao_manager", "카톡 봐줘", "단톡방 요약해줘", "현빈한테 카톡 보내줘", "카톡 자동화" 등을 말할 때 실행해.
---

# kakao_manager 스킬

## 1. 환경 사전 점검 (실행 전 항상 검사)

```bash
# 1) 카카오톡 Mac 앱 실행 여부
osascript -e 'tell application "System Events" to (name of processes) contains "KakaoTalk"'
# false 면: open -a KakaoTalk

# 2) 카카오톡 로그인 여부 (창 이름이 '로그인'이면 아직 로그인 안 됨)
osascript -e 'tell application "System Events" to tell process "KakaoTalk" to get name of every window'
# '로그인' 포함 시 → 자동 로그인 시퀀스 실행 (아래 2.1)

# 3) uv 설치
test -x ~/.local/bin/uv && echo OK || curl -LsSf https://astral.sh/uv/install.sh | sh

# 4) (vendored) kakao_send.py/kakao_read.py 는 스킬 폴더에 동봉됨 — 외부 플러그인 클론 불필요
#    경로: ~/.claude/skills/kakao_manager/scripts/kakao_send.py, kakao_read.py
test -f ~/.claude/skills/kakao_manager/scripts/kakao_send.py && echo "vendored OK" || echo "MISSING kakao_send.py"

# 5) 접근성 권한 (atomacos가 카톡 enumerate 가능한지 한 줄 테스트)
source $HOME/.local/bin/env && uv run --with atomacos --python 3.12 python -c "
import atomacos
app = atomacos.getAppRefByBundleId('com.kakao.KakaoTalkMac')
print('OK' if app else 'PERM_NEEDED')
"
# PERM_NEEDED 또는 ValueError 발생 시:
# open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
# → 사용자에게 터미널 앱 토글 ON 요청
```

## 0. 개인 설정 (최초 1회 — 자격증명/채팅방을 JSON으로 분리)

모든 개인정보(카톡 계정·본인 표시명·자주 쓰는 채팅방)는 **레포 밖** JSON 파일에서 읽는다. 코드/SKILL.md에는 절대 하드코딩하지 않는다.

- 설정 파일: `~/.config/kakao_manager/config.json` (`$KAKAO_CONFIG`로 경로 변경 가능)
- 템플릿: `scripts/config.example.json`
- **다중 계정 지원**: `accounts.<key>` 아래에 계정별로 id/pw/표시명/채팅방을 둔다. `active` 가 기본 계정. 호출마다 `--account <key>` 또는 `$KAKAO_ACCOUNT` 로 전환.

```bash
# 1) 설정 파일 생성 (없을 때만 템플릿 복사)
python3 scripts/config.py --init
# 2) 사용자에게 ~/.config/kakao_manager/config.json 을 열어 accounts.<key> 의
#    id/pw/표시명/채팅방을 채우라고 안내 (계정 여러 개면 accounts 에 추가)
# 3) 유효성 점검 (모든 계정)
python3 scripts/config.py --check
# 계정 목록
python3 scripts/config.py --accounts
```

> 실행 전 `--check` 가 통과하지 않으면(=id/pw/표시명 미입력) 작업을 멈추고 사용자에게 설정을 채우라고 요청한다.

## 0.5 최초 셋업 온보딩 (직원이 설치 후 처음 실행할 때)

트리거: "카톡 매니저 처음 써", "초기 셋업", "세팅 도와줘", 또는 `config.py --check` 가 실패할 때.
**Claude가 대화로 하나씩 질문하고, 받은 답을 config 에 기입한다.** 직원이 JSON 을 직접 편집할 필요 없음.

### 단계 A — 질문 (대화형 인터뷰)
계정 1개당 아래를 묻는다. 계정이 여러 개면(예: 개인폰+업무폰) 반복.
1. **카카오 ID** (전화번호 또는 이메일)
2. **비밀번호** — ⚠️ 받은 직후 곧바로 config 에만 기입하고, 확인용으로 다시 평문 출력하지 않는다
3. **본인 카톡 표시명** ((나) 자기채팅 식별·동명이인 구분용)
4. **자주 쓰는 채팅방** (선택) — "별명 → 정확한 방이름" 쌍. 없으면 건너뜀(나중에 추가 가능)
5. 계정 더 있나? (있으면 1~4 반복, key 는 default/work 등)

### 단계 B — 기입 (config 저장)
받은 답을 계정 객체로 만들어 stdin 으로 전달(JSON 직접 편집 X):
```bash
echo '{"label":"메인","kakao":{"id":"<답>","pw":"<답>"},"self_display_name":"<답>","aliases":[{"keywords":["<별명>"],"chat_name":"<정확한방>"}]}' \
  | python3 scripts/config.py --set-account default
# 활성 계정 지정 (보통 첫 계정)
python3 scripts/config.py --set-active default
python3 scripts/config.py --check   # 채워졌는지 확인
```

### 단계 C — 정상 세팅 테스트 (아래 0.6 실행)

## 0.6 정상 세팅 테스트 (자가진단 + 선택적 전송 테스트)

트리거: "세팅 됐는지 확인", "테스트 해줘", 온보딩 직후.

### ① 자가진단 (읽기 전용 — 메시지 안 보냄)
```bash
source $HOME/.local/bin/env && \
  uv run --with atomacos --python 3.12 python scripts/selftest.py
# 특정 계정: 끝에 --account work
```
- 체크: uv / 앱실행 / 로그인 / 접근성 권한 / config 유효 / 메인창 / 채팅목록 / (나) 식별
- `❌ FAIL` 있으면 해당 항목 안내대로 해결(로그인 FAIL → 2.1 자동 로그인). `⚠️ WARN` 은 참고(예: 채팅 탭 아님 → Cmd+2).
- 종료코드: FAIL 있으면 1.

### ② 전송 테스트 (실제로 1건 보냄 — 반드시 사용자에게 먼저 물어봄)
자가진단이 통과하면, **전송까지 검증할지** 사용자에게 묻는다. 자동으로 보내지 말 것.

> "전송 테스트를 해볼까요? **(1) 나와의 채팅**(안전, 남에게 안 감) / **(2) 특정 채팅방** / (3) 건너뛰기"

- **(1) 나와의 채팅**: 가장 안전. `--verify-me` 로 (나) 검증 후 발송.
  ```bash
  source $HOME/.local/bin/env && cd scripts && \
    uv run --with atomacos --python 3.12 python send_safe.py "$(python3 config.py --self-name)" \
      --text "✅ kakao_manager 세팅 테스트" --verify-me --json
  ```
- **(2) 특정 채팅방**: ⚠️ **오발송 주의** — 엉뚱한 방에 갈 수 있음. 반드시 **"어느 방으로 보낼까요?"** 한 번 더 물어 정확한 방이름을 확정한 뒤 발송. (별명이면 `config.py --resolve` 로 정확한 방이름 변환)
  ```bash
  TARGET="$(python3 scripts/config.py --resolve '<사용자가 답한 방>')"
  # 사용자에게 TARGET 을 보여주고 "여기로 보냅니다" 최종 확인 후:
  source $HOME/.local/bin/env && cd scripts && \
    uv run --with atomacos --python 3.12 python send_safe.py "$TARGET" --text "✅ 세팅 테스트" --json
  ```
- **(3) 건너뛰기**: 자가진단 결과만으로 마무리.

발송 후 결과 JSON 의 `ok`/`rows_before→rows_after` 로 실제 전달 확인하고 사용자에게 체크리스트로 보고한다.

## 2. 자동 셋업

### 2.1 카카오톡 자동 로그인 (config.json 기반)
- 자격증명은 활성 계정의 `kakao.id` / `kakao.pw` 에서만 읽는다 (`config.py --login-env`).
- 다른 계정으로 로그인하려면 `--account <key>` 추가.
- ⚠️ 비번칸(`AXSecureTextField`)은 `set value`·클릭·Tab 모두 포커스를 못 잡음 → **`AXFocused` 속성을 직접 ON 한 뒤 `keystroke`** 로 입력. ID칸은 일반 텍스트필드라 `set value` 로 바로 넣으면 됨.
- 로그인 폼이 `window 1`이 아닐 수 있음(빈 이름 창이 같이 뜸) → 창 이름 `"로그인"` 으로 참조.

```bash
# 활성 계정 자격증명 -> 환경변수로 주입 (transcript에 평문 노출 최소화)
eval "$(python3 scripts/config.py --login-env)"
# 특정 계정: eval "$(python3 scripts/config.py --account work --login-env)"
osascript <<EOF
tell application "KakaoTalk" to activate
delay 0.6
tell application "System Events"
  tell process "KakaoTalk"
    set frontmost to true
    delay 0.3
    set lw to (first window whose name is "로그인")
    perform action "AXRaise" of lw
    delay 0.3
    -- (선택) 자동 로그인 체크
    try
      if (value of checkbox "자동 로그인" of lw) is 0 then click checkbox "자동 로그인" of lw
    end try
    delay 0.2
    -- ID: 일반 텍스트필드 → set value 로 바로 입력
    set value of text field 1 of lw to "$KAKAO_ID"
    delay 0.3
    -- 비번: AXSecureTextField → 클릭/Tab 으론 포커스 안 됨, AXFocused 직접 ON 후 keystroke
    set value of attribute "AXFocused" of text field 2 of lw to true
    delay 0.3
    keystroke "$KAKAO_PW"
    delay 0.4
    perform action "AXPress" of button "로그인" of lw
  end tell
end tell
EOF
# 7~10초 대기 후 창 이름이 "카카오톡"(메인)이면 성공. 여전히 "로그인"이면 비번 미입력/오타 의심.
```

### 2.2 채팅 탭 활성화 (목록 조회 전 필수)
카톡 메인창이 친구 탭에 있으면 `--list`가 0개 반환. 항상 채팅 탭부터:
```bash
osascript -e 'tell application "KakaoTalk" to activate' && \
osascript -e 'tell application "System Events" to tell process "KakaoTalk" to key code 19 using {command down}'
# Cmd+1=친구, Cmd+2=채팅, Cmd+3=더보기
```

## 3. 핵심 명령어 (스킬 자체 vendored 스크립트)

★ 스크립트 경로(vendored): `~/.claude/skills/kakao_manager/scripts/` — `kakao_send.py`/`kakao_read.py`는 원래 team-attention 외부 플러그인 것이었으나 **git pull 휘발 방지를 위해 스킬 폴더로 복사(vendoring)해 왔다(2026-06-17, 현빈 지시)**. 이제 외부 플러그인을 갱신해도 우리 카톡 동작·서명설정(SIGNATURE="")은 안 깨진다. 외부 플러그인 의존 없음.

```bash
ALIAS_RUN='source $HOME/.local/bin/env 2>/dev/null; cd ~/.claude/skills/kakao_manager/scripts && uv run --with atomacos --python 3.12 python'
```

### 채팅방 검색
```bash
$ALIAS_RUN kakao_read.py --search "키워드" --json
```

### 채팅방 목록 (채팅 탭일 때만)
```bash
$ALIAS_RUN kakao_read.py --list --limit 50 --json
```

### 안읽음 총합 (백그라운드 — UI/스샷 불필요)
Dock 뱃지값을 읽어 전체 안읽음 합계를 즉시 반환. 카톡 포커스·창 상태 무관.
```bash
python3 scripts/unread.py            # 정수 (예: 29)
python3 scripts/unread.py --json     # {"unread_total": 29}
```
- 한계: **전체 합계만**. 방별 분해 불가(메시지 DB가 SQLCipher 암호화). "어느 방에 몇 개"는 `--list` UI 필요.

### 메시지 읽기 (오늘만, 정확 날짜)
```bash
# --date YYYY-MM-DD, --scroll-up/down N, --limit N
$ALIAS_RUN kakao_read.py "채팅방" --scroll-down 5 --date 2026-05-29 --json --limit 200
```

### 메시지 보내기 (텍스트)
```bash
$ALIAS_RUN kakao_send.py "채팅방" "메시지" --no-signature
# 옵션: --no-signature, --close, --json
```
> ★★★ 서명 금지(현빈 지시 2026-06-17): 외부로 나가는 모든 메시지 끝에 'sent with claude code' 같은 서명이 **절대 붙으면 안 됨**. vendored `kakao_send.py`의 `SIGNATURE`를 빈 문자열로 패치해 뒀고(스킬 폴더 사본이라 외부 git pull 영향 없음 = 휘발 안 됨), 안전벨트로 **전송 시 항상 `--no-signature`도 명시**한다. 전송 후 read로 끝줄에 서명 안 붙었는지 검증할 것.

### 이미지 전송 (PNG 클립보드 paste 방식)
```bash
osascript -e 'set the clipboard to (read POSIX file "/path/to.png" as «class PNGf»)'
osascript <<EOF
tell application "KakaoTalk" to activate
delay 0.3
tell application "System Events"
  tell process "KakaoTalk"
    repeat with w in windows
      if (name of w) is "<채팅방명>" then  -- config.py --resolve 로 얻은 정확한 채팅방명
        perform action "AXRaise" of w
        exit repeat
      end if
    end repeat
    delay 0.4
    click at {911, 763}  -- 입력란 좌표 (창 크기 따라 조정)
    delay 0.3
    key code 9 using {command down}   -- Cmd+V
    delay 1.5
    key code 36                        -- Enter
  end tell
end tell
EOF
```

### 파일 전송 (⚠️ 현재 미동작 — 4번 한계 참조)
신뢰성 있는 파일 전송은 카톡 입력란 옆의 첨부 버튼(클립 아이콘) 직접 클릭이 필요. 향후 구현 예정.

### 수신 파일 다운로드 (.xlsx/.pdf/.zip 등 → ~/Downloads)
상대가 보낸 파일 첨부를 ~/Downloads 로 저장한다. **방을 먼저 연 뒤** 실행(파일이 화면에 보여야 함).
```bash
# 1) 방 열기 (파일이 위에 있으면 스크롤 필요)
$ALIAS_RUN kakao_read.py "고야태스크" --json --limit 60 >/dev/null
# 2) 파일명 일부로 다운로드
source $HOME/.local/bin/env && cd ~/.claude/skills/kakao_manager && \
  uv run --with atomacos --python 3.12 python scripts/download_file.py "고야태스크" "무릎보호대" --json
# -> {"ok": true, "path": "/Users/.../Downloads/....xlsx", "size": 8133}
```
- **동작 원리**: 파일 버블을 **우클릭 → 컨텍스트 메뉴 '저장하기' 클릭**(Quartz 마우스 이벤트). 카톡 컨테이너 `Downloads → ~/Downloads` 심링크라 곧장 ~/Downloads 에 떨어진다.
- ⚠️ footer 의 '저장' 버튼은 hover 시에만/불안정하게 떠서 안 씀 → **우클릭 메뉴 경로가 안정적**.
- '저장하기' 후 이름없는 AXDialog(저장 패널)가 뜨면 자동으로 Return 처리(기본 위치 수락).
- 파일명 정규화(NFC/NFD) 차이로 `ls|grep` 이 빗나갈 수 있음 → 검증은 `ls ~/Downloads/*.xlsx` 나 python `os.path.exists` 로.

## 4. (나) 본인 채팅 식별 (필수 안전장치)

송신 전 반드시 검증해야 함. 동명이인이 있을 수 있어서.

### 식별자: AXImage description = 'badge me'
```python
# 메인 윈도우 채팅 목록의 각 row 안에 AXImage AXDescription='badge me' 가 있으면 (나) 본인
import atomacos
app = atomacos.getAppRefByBundleId('com.kakao.KakaoTalkMac')
main = next(w for w in app.windows() if w.AXTitle == '카카오톡')
# walk rows, find AXImage with description 'badge me'
```

### 사용자 메모
- 본인 카톡 표시명: `config.py --self-name` 으로 조회 (config.json 의 `self_display_name`)
- 본인 (나) 채팅방: 표시명 일치 + AXImage('badge me') 가 있는 row
- 동명이인이 있을 수 있으므로 송신 전 반드시 'badge me' 로 검증 (위 식별자 참조)

## 5. 자주 쓰는 채팅방 alias (config.json 기반)

채팅방 alias는 `config.json` 의 `aliases` 배열에서 관리한다. 하드코딩 금지.

```bash
# 사용자가 별명으로 "OO한테 보내줘" 라고 하면, 먼저 keyword 를 정확한 채팅방명으로 해석:
python3 scripts/config.py --resolve "별명"     # -> config 에 등록된 chat_name 출력 (없으면 입력 그대로)
python3 scripts/config.py --resolve "나"       # -> self_display_name 출력
```

- 검색 시 괄호 `(...)` / 대괄호 `[...]` 매칭이 실패하면 핵심 토큰만 추출해 재시도 (send_safe.py 의 `normalize_chat_name`).
- alias 목록을 보려면 `config.py --dump` (비밀번호는 가려짐).

## 6. 알려진 한계 / 우회

| 한계 | 영향 | 우회 |
|---|---|---|
| 화면에 마운트된 메시지만 추출 | 과거 메시지 누락 가능 | `--scroll-up N` / `--scroll-down N` |
| 사진/첨부 안 텍스트 안 잡힘 | OCR 필요 | 별도 OCR 파이프라인 (todo) |
| 답글 인용 원본 누락 가능성 | 컨텍스트 일부 손실 | AXImage 'badge me'·답글 마커 추가 walk (todo) |
| 파일/영상 클립보드 paste 안 됨 | 텍스트/이미지만 가능 | 첨부 버튼 자동화 (todo) |
| 그룹 채팅 발신자별 통계 없음 | 수동 집계 | 후속 헬퍼 스크립트 (todo) |
| 화면 미마운트 과거 메시지 전부 추출 | 한계 | **kakaocli** (silver-flight-group) 폴백 검토 — Full Disk Access + SQLCipher DB 읽기 |
| AppleScript "모든 앱 hide" 사용 금지 | Claude Code 터미널까지 hide되어 작업 불가 | hide 절대 X. 카톡만 raise |

## 7. 표준 운영 절차 (사용자 의도별)

### 의도: "오늘 X 단톡 요약"
1. 사전 점검 (1번)
2. 채팅 탭 활성 (2.2)
3. `kakao_read.py "X" --scroll-down 5 --date $(date +%Y-%m-%d) --json --limit 300`
4. 결과 분석 → 액션 거리 추출 → 사용자 보고

### 의도: "Y에게 카톡 보내줘"
1. 사전 점검
2. `kakao_read.py --search "Y" --json` → 후보 확인
3. **본인 채팅이면 (나) 마커 검증** (4번)
4. 동명이인 위험 있으면 사용자에게 확인 1회
5. `kakao_send.py "Y" "메시지"`
6. 결과 검증 (최신 row 확인)

### 의도: "그룹채팅 내일 미팅 안내 보내고 응답 모아줘"
1. 메시지 전송
2. 일정 시간 후 read로 응답 폴링 (시간 윈도우 + sender 필터)

## 8. 추가/개선 권장 기능 (우선순위 순)

### 우선순위 ★★★ (다음 작업 권장)
1. **--unread 옵션** — 메인창 row의 unread count (오른쪽 숫자 뱃지) 기준 안 읽은 채팅방만 추출
2. **첨부버튼 자동화** — 입력란 옆 클립 아이콘 클릭 → 파일 picker → 파일 경로 입력 → 전송. 클립보드 우회보다 안정적
3. **답장 인용 메시지 마커 감지** — 답글 시 AXImage 또는 AXGroup 별도 구조 walk 보강
4. **send 전 'badge me' 자동 검증 가드** — `--self` 또는 `--verify-me` 플래그로 (나)가 아니면 abort

### 우선순위 ★★
5. **그룹채팅 발신자별 집계** — `--by-sender` 옵션으로 sender Counter 출력
6. **OCR 파이프라인** — 사진 attached rows를 screencapture → OCR(Vision framework) → text 회수
7. **답장 초안 워크플로** — read + Claude로 톤 학습 → draft 생성 → 사용자 승인 → send (이메일 templater 패턴)
8. **카톡 → Notion 자동 백업** — 매일 자정 cron으로 단톡방 어제 내용 Notion DB에 저장

### 우선순위 ★
9. **키워드 알람** — 단톡방에서 특정 키워드 발생 시 Telegram 알림 (현빈 텔레그램 봇 통합)
10. **bulk 검색** — 모든 채팅방에서 키워드 검색 (시간 ↑↑ 주의)
11. **kakocli 폴백** — 화면 안 보이는 과거 메시지 조회 시 silver-flight-group/kakocli 자동 호출
12. **그룹 채팅 멘션** — `@이름` 입력 시 카톡 자동완성 처리

## 9. 보안/주의

- `config.json` 은 `~/.config/kakao_manager/` (레포 밖)에 두고 권한 0600 권장 (`--init` 이 자동 설정). **절대 git에 커밋 금지** (`.gitignore` 로 차단됨)
- 자격증명 transcript 노출 주의 — `config.py --login-env` 로 export 후 osascript에 변수만 전달, 비밀번호 원문은 출력하지 않음
- 카톡 UI 자동 조작 중에는 사용자 키보드/마우스 동시 사용 금지 (충돌)
- 시스템 설정 GUI 권한 부여는 사람이 수동 처리만 가능 (자동화 불가)
- **`hide all apps` 패턴 절대 금지** — Claude Code 터미널까지 hide됨

## 10. 검증 완료 (2026-05-29 기준)
- ✅ 자동 로그인 (.env 기반, secure field keystroke 우회)
- ✅ 채팅방 검색/목록 (채팅 탭 활성 상태에서)
- ✅ 메시지 읽기 + 날짜(ISO) 정확 추출 (AXHelp 파싱)
- ✅ `--scroll-up/down`, `--date` 옵션 (자체 패치)
- ✅ 텍스트 메시지 전송 (서명 자동)
- ✅ 이미지(PNG) 클립보드 paste 전송
- ✅ 본인 (나) 채팅 식별 (badge me)
- ✅ tmux 다른 세션으로 카톡 정보 전달 (tele-code 연계)
- ❌ 파일(.txt/.pdf 등) 클립보드 paste 전송 — 첨부버튼 자동화 필요
- ❌ 영상 전송 — 미테스트, 파일과 동일 한계로 추정
- ❌ "나와의 채팅" 정식 방 자동 생성 (검색에 없으면 미존재)
