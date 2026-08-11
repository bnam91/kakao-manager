---
name: kakao_manager
description: 카카오톡 Mac 앱을 Claude Code 터미널에서 직접 조작하는 매니저 스킬. 카톡 앱 UI 자동화(atomacos, vendored kakao_read.py/kakao_send.py)로 채팅방 검색/목록/메시지 읽기/날짜필터/요약/메시지 전송/이미지 전송/(나) 자기채팅 식별/자동 로그인을 일관된 방식으로 처리한다. 사용자가 "카톡 매니저", "/kakao_manager", "카톡 봐줘", "단톡방 요약해줘", "현빈한테 카톡 보내줘", "카톡 자동화" 등을 말할 때 실행해.
---

# kakao_manager 스킬

> 🚨 **대상 확정 규칙 (2026-08-05 · 오발송 방지 · 동작 변경)** — `scripts/target_guard.py`
> 방 이름이 **애매하면 스크립트가 고르지 않고 중단**한다. "가장 비슷한 것"·"첫 번째 것"으로 대체하지 않는다.
> - **완전일치**가 1개면 그게 이긴다. 없으면 후보를 전부 모아 **정확히 1개일 때만** 진행.
> - 후보 2개 이상 = `TargetMismatch` **중단**(후보 목록을 에러에 찍어준다 → 정확한 이름으로 다시 호출).
> - **발송 경로는 부분일치 금지**(`send_safe.py`/`kakao_send.py`). 별명은 `config.py --resolve` 로 정확한 방이름을 먼저 확정할 것. 읽기(`kakao_read.py`)는 후보가 **유일할 때만** 부분일치 허용.
> - **발송 직전 재확인**: 키 입력은 "지금 포커스된 창"으로 들어가므로, 타이핑 직전 포커스 창 제목을 다시 대조하고 어긋나면 안 보낸다.
> - 계기: 검색은 결과 목록에서 `Down+Enter`로 **첫 줄을 무조건** 열었다 — `"신현빈"` 요청에 「고야태스크」방이 열렸다(실측). 읽기라 피해는 없었지만 같은 구조가 발송 경로에도 있었다.
> - **별명(config)도 같은 규칙**: `--resolve` 는 후보가 2개면 고르지 않고 중단(exit 2), 미등록이면 exit 3 + stderr 경고(조용한 통과 금지), 부분일치로 걸리면 경고를 남긴다. **별명은 짧고 고유하게** — 다른 방 이름을 부분문자열로 품는 키워드(예 `"세무 고야"`)를 넣으면 그 방으로 끌려간다(2026-08-05 실측·회수).
> - **`--set-account` 는 이제 진짜 병합**(기존 `kakao.id/pw` 보존). 통째 교체는 `--replace-account` 로 명시. 저장 결과에 id/pw 가 비면 저장을 거부한다.
> - 자가검증: `python3 scripts/test_target_guard.py` (13케이스) · `python3 scripts/test_config_guard.py` (14케이스) — 둘 다 카톡 없이 실행

> 📒 **작업 전 [`notes/KNOWLEDGE.md`](notes/KNOWLEDGE.md) 먼저 읽기** — 단톡방별 특징·열 때의 함정, 송장 운영 규칙, 계정 전환 주의 등 **Mac 간 git 공유 운영지식**. 새로 알게 된 방 특징/규칙은 거기에 한 줄 추가하고 commit+push(고객 PII·자격증명은 절대 금지, 그건 `~/.config`).

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

> ★★★ **pbcopy 안 먹는 환경의 전송 우회 (2026-08-04 실전, 반드시 확인)**: 일부 맥/세션에서 **`pbcopy`가 pasteboard 접근 불가**(클립보드 길이 0). `kakao_send.py`의 `type_text()`·`send_safe.py`는 pbcopy→Cmd+V 경로라 **아무것도 안 나가는데 `success:true`/`ok`를 반환**(rows_before==rows_after인데 성공으로 오탐). → **증상 판정**: 발송 후 스샷/read로 말풍선이 실제로 생겼는지 확인. rows 불변인데 success면 pbcopy 함정. → **확실한 우회 = atomacos로 입력란 직접 세팅**: 방 창의 마지막(y최대) `AXTextArea`를 찾아 `el.AXValue="<본문>"` + `el.AXFocused=True` → osascript `key code 36`(엔터). 이 방식이 유일하게 실발송됨. ★전송 전/후 **반드시 스크린샷 실물 검증**(입력란 표시 확인 → 엔터 → 말풍선 확인). 클립보드가 필요하면 `pbcopy` 말고 **osascript `set the clipboard to (read POSIX file … as «class utf8»)`** 를 쓴다(이건 동작).

> ★★★ **손쉬운 사용·입력 모니터링 권한 OFF 진단 (2026-08-04, 시간 태우지 말 것)**: 카톡 UI 자동화가 **통째로 막히면** 곧장 이 진단부터. 증상 = osascript `keystroke`→**error 1002**("키스트로크 허용 안 됨"), `click`/UI제어→**-25211**("보조 접근 거부"), 카톡이 자동로그인(Auto Login=1)돼 있어도 **메인창이 트레이로 숨어 `app.windows()`가 0개**. **★재시작·activate·메뉴바/Dock 클릭 등 우회는 전부 실패한다** — 이건 **사람이 시스템설정 > 개인정보 보호 및 보안 > ①손쉬운 사용 ②입력 모니터링에서 터미널/osascript를 직접 ON 해야만** 풀린다(자동화 불가). → **반복 재시도로 시간 태우지 말고 즉시 현빈에게 권한 ON 요청 보고**. 빠른 체크: `osascript -e 'tell application "System Events" to key code 999'` 가 error 1002면 막힌 것, 조용히 통과하면 권한 정상.

### 인라인 이미지(사진) 원본 판독 → 로컬 저장 후 Read (2026-08-04 실전)
카톡 말풍선은 넓은 이미지의 **좌우를 하드 크롭**해 표/문서 일부만 보인다. 원본 전체를 읽으려면 **우클릭 〉 저장하기**로 `~/Downloads`에 받아 `Read`한다(더블클릭 뷰어는 안 열리고, "복사하기"는 이미지가 아니라 텍스트만 잡힘).
```bash
# 1) 방 넓게 raise → 이미지 우클릭(Quartz right-click) → 컨텍스트 메뉴의 '저장하기' AXMenuItem 좌표를 atomacos로 얻어 그 좌표 클릭
#    ★'저장하기' 좌표는 고정좌표 클릭이 자꾸 빗나감 → 반드시 atomacos AXMenuItem 'AXPosition+AXSize/2' 로 실좌표 취득해 클릭
#    저장 패널 뜨면 osascript 'key code 36'(Return, 기본위치 수락)
# 2) 저장 확인: find ~/Downloads -iname 'KakaoTalk_Photo_*.png' -mmin -1  → 그 경로를 Read
```
- ⚠️ **백그라운드 챗펄스 폴러가 atomacos를 동시에 쓰면 `system memory failure` 경합** → 이미지 저장/좌표작업 직전엔 `pkill -f chatpulse_poller_kakao`로 폴러 잠깐 정지, 작업 후 재무장.

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
python3 scripts/config.py --resolve "별명"     # -> chat_name 출력. stdout 계약은 그대로(항상 방이름 한 줄)
#   exit 0 = 별명으로 확정 / exit 3 = 미등록(입력 그대로 출력 + stderr 경고) / exit 2 = 모호(출력 없음, 후보 표시)
#   부분일치로 걸리면 exit 0 이어도 stderr 에 "부분일치" 경고가 뜬다 — 의도한 방인지 확인할 것
python3 scripts/config.py --resolve "별명" --strict   # 미등록도 실패 처리(조용한 통과 완전 차단)
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

### ★★★ 전송 절대규칙 — 오후 6시 45분 이후 답장 금지 (현빈 지시 2026-06-18, 2026-06-24 리밋 18:45로 변경)
**오후 6시 45분(18:45) 이후**에는 외부로 나가는 **카톡 답장·전송을 절대 하지 않는다.** 6시 45분 이후 카톡은 **읽기/다운로드/요약만**.
- 전송(`kakao_send.py`) 직전 **현재 시각(`date +%H%M`)이 1845 이상인지 확인** → 18:45 이후면 전송 중단.
- 수령 확인 답장 등 단순 응답도 6시 45분 이후 금지.
- **예외**: 현빈이 따로 개인적으로 "보내라"고 요청한 경우에만 허용.
- 내부 보고(tele-code claude-tg, telegram-send)·쿠팡매니저 핸드오프는 '외부 답장'이 아니므로 시간 무관 허용.
- 6시 45분 이후 답장이 필요해 보이면 보내지 말고 다음날/현빈 승인으로 보류.

### ★ 거래처 답장 톤 — 인사말 + 감사 무드 (현빈 지시 2026-06-24)
거래처(리브리 등)에 보내는 **수령·확인 답장은 "안녕하세요 담당자님, 확인 감사합니다" 정도의 무드**로 쓴다 = **인사말(안녕하세요 담당자님) + 감사(확인/잘 받았습니다 + 감사합니다)**.
- ⚠️ **문구를 그대로 박아쓰지 말 것** — 위 예시는 '무드' 참고용. 상황(송장 수령/문의/독촉 등)에 맞게 그 톤으로 자연스럽게 변형.
- 하지 말 것: "확인했습니다. 진행하겠습니다."처럼 인사·감사 없이 딱딱하게 끝내기(2026-06-24 실수 — 감사인사 누락).
- 이모지 사용 금지(현빈 지시).

### ★ 작업 종료 공통 규칙 — 대화창 닫기 (필수)
모든 카톡 작업(읽기/전송/다운로드/요약)이 끝나면 **그 대화방 창을 반드시 닫는다.** 용무 끝난 대화창을 열어두지 않음(현빈 지시 2026-06-17 — 누적 시 화면 혼란·오발송 위험).
- 닫기: `kakao_send.py`/`kakao_read.py`의 `--close` 옵션, 또는 osascript `keystroke "w" using command down`.
- ★타이밍: `activate` 직후 바로 창 조회하면 인식 안 됨 → **activate 후 1s+ 대기** → `window "방이름"` 존재 확인 → `AXRaise` → `Cmd+W`. 닫은 뒤 창 목록에 메인 '카카오톡'만 남았는지 검증.
- 메인 '카카오톡'(앱 목록창)은 닫지 않는다 — 개별 대화방 창만.
- ★**검색어도 클리어**: `--search`로 채팅 검색을 썼으면 채팅탭 검색바에 검색어가 남아 목록이 필터된 채 유지된다 → atomacos로 메인창 walk → 첫 검색필드(`AXTextField`/`AXSearchField`) `AXValue=''`로 비운다(안 먹으면 `AXFocused=True` 후 Cmd+A→Delete). 다음 작업이 엉뚱한 필터 상태에서 시작되는 것 방지.

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

---

# ★파일첨부 · 안전전송 (2026-08-11 실측 반영 · 여포)

> 실측 근거: `references/2026-08-11_첨부삭제_실측리포트.md` / 절차 정본: `references/안전전송_프로토콜.md`
> 측정 환경: 인텔맥북(x86_64), 카톡 계정 「고야 CLD」, 대상방 「신현빈」 1:1. 전 과정 타 방 발신 0건.

## 실행 (한 줄)

```bash
SAFE=~/.claude/skills/kakao_manager/scripts/safe_send/run.sh

$SAFE send-file "신현빈" ~/Desktop/문서.pdf          # 파일 1개~여러개 (PDF/엑셀/이미지/영상)
$SAFE send-text "신현빈" "안녕하세요"                 # ★키보드 입력을 쓰지 않는 안전 경로
$SAFE delete   "신현빈" "문서.pdf"                    # 모두에게서 삭제(진짜 회수)
$SAFE delete   "신현빈" "문서.pdf" --me               # 나에게서만(현재 기기 한정)
$SAFE check    "신현빈"                               # 전송 없이 창 상태만 점검·복구
```

- ★**방 이름은 «정확 제목»으로만.** 부분일치 폴백 없음 — 못 찾으면 멈춘다.
- **성공 판정 = stdout JSON 의 `ok:true` + `found:true` + `contamination.misdelivery:[]` 세 개가 전부 맞을 때만.**
- `[STOP:...]` = **아무것도 전송되지 않은 채 멈춘 것.** ★**자동 재시도 금지** — 원인 확인 후 사람이 다시 실행. (재시도가 오발송을 두 배로 만든다.)
- 1건당 **12~13초**(검증 포함), 10건 약 **2분 5초**.

## 되는 것 / 형태 (실측)

| 대상 | 결과 |
|---|---|
| **PDF** | ✅ **파일 그대로**(이미지 변환 아님) — 거래처 인쇄용으로 사용 가능 |
| 엑셀(.xlsx) | ✅ 파일로 감 |
| 이미지(.png) | ✅ 단 **사진 버블로 변환**되어 파일명이 사라진다 |
| **한글·공백 파일명** | ✅ 안 깨진다 |
| 이미지 여러 장 | ✅ 5장 → **1건 그리드 묶음**, 순서 유지 |
| 동영상(.mp4) | ✅ 재생 가능한 영상 버블 |
| 모두에게서 삭제 | ✅ 텍스트·파일·이미지·영상 전부, **확인창 없이 즉시** |
| 삭제 시간제한 | **46분 지난 메시지도 성공** — 통설의 5분 제한 미관측 |

## 🔴 반드시 알아야 할 것 3가지

1. ★★**기존 `kakao_send.py`(전역 ⌘V → 전역 Enter)는 오발송 위험이 크다.**
   전역 키입력은 **그 순간 최전면 앱**으로 간다. **실측 재현**: TextEdit을 최전면에 둔 채 같은 시퀀스를 돌리자 **문장이 TextEdit에 그대로 찍혔다.**
   ⇒ **새 경로는 입력창 요소에 `AXValue`를 직접 넣는다.** 카톡이 비활성이어도 되고, **키입력이 아니라 원리적으로 다른 앱·다른 방으로 샐 수 없다.** 새 전송은 `safe_send`를 쓸 것.
2. 🔴**카톡 앱을 «종료»하지 마라.**
   재실행 시 **「다른 기기에서 로그인 중 → 강제 로그아웃?」 게이트**가 떠서 **무인 복구 불가**이고, 복구해도 **그날 그 방에서 보낸 대화 이력이 이 맥 클라이언트에서 사라진다**(상대 단말에는 남음 ⇒ **로컬에서 삭제도 못 하게 된다**). 창만 닫는 건 안전하다.
3. ⚠️**타 방 오염검사에 「변했다」만 쓰면 못 쓴다.** 실계정은 수신 메시지가 계속 들어와 오탐이 난다.
   ⇒ **다른 방 미리보기에 «우리가 보낸 내용»이 보이는가**로 판정한다.

## 창 상태 강건성 — 사람 손 없이 되는가 (실측)

| 상황 | 무인 | 복구 방법 |
|---|:--:|---|
| 대화창만 닫힘(앱 실행중) | ✅ | 목록창 확보 → `⌘2` → `⌘F` 정확제목 검색 → 열린 방 검증 |
| 최소화(Dock) | ✅ | `AXMinimized=false` |
| **화면 밖으로 걸침** | ✅ | `NSScreen.visibleFrame`로 가용영역 계산 → 크기 축소 + 위치 클램프 |
| 다른 앱이 덮음(비활성) | ✅ | `activate` + 「창」메뉴 항목 Press로 키 윈도우화 |
| 카톡의 다른 창이 활성 | ✅ | 동일. focused window를 제목으로 재확인 |
| **앱 자체 종료** | ❌ | 강제 로그아웃 게이트 — 위 2번 참조 |
| 화면 잠금/절전 직후 | **미검증** | 해제 암호가 없어 시도 시 복구 불가 — 추측으로 안 메움 |

## 경로 비교 (왜 A-2인가)

| 경로 | 판정 |
|---|---|
| A-1 클립보드 파일URL → **전역 ⌘V** | 동작하나 **포커스 사고 위험** |
| **A-2 클립보드 파일URL → 「편집 > Paste」 «메뉴 항목» Press** | **★권장** — 전역 키입력 없음 |
| A-3 Finder에서 실제 ⌘C | ❌ AppleEvent `-1712` timeout |
| B 「파일전송」/⌘O → ⌘⇧G 경로입력 | 동작하나 단계 많고 전역 키입력 3회 |
| C 픽셀 드래그앤드롭 | 동작하나 **좌표 의존**, 드롭지점이 목록창과 겹치면 위험 |
| D AppleScript/atomacos 직접 첨부 | ❌ 불가 |

★**선정 기준 = 「이상적 상태에서 제일 빠른 것」이 아니라 「창 상태·포커스에 제일 덜 흔들리는 것」.**
