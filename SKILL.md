---
name: kakao_manager
description: 카카오톡 Mac 앱을 Claude Code 터미널에서 직접 조작하는 매니저 스킬. team-attention/kakaotalk 플러그인을 래핑해서 채팅방 검색/목록/메시지 읽기/날짜필터/요약/메시지 전송/이미지 전송/(나) 자기채팅 식별/자동 로그인을 일관된 방식으로 처리한다. 사용자가 "카톡 매니저", "/kakao_manager", "카톡 봐줘", "단톡방 요약해줘", "OO한테 카톡 보내줘", "카톡 자동화" 등을 말할 때 실행해.
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

# 4) 플러그인 레포 클론
test -d ~/github/plugins-for-claude-natives || \
  (cd ~/github && git clone https://github.com/team-attention/plugins-for-claude-natives.git)

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
- 보안 텍스트필드는 `set value` 거부 → keystroke + Tab 우회 필수

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
    click text field 1 of window 1
    delay 0.3
    key code 0 using {command down}  -- Cmd+A
    delay 0.15
    key code 51                       -- Delete
    delay 0.15
    keystroke "$KAKAO_ID"
    delay 0.3
    key code 48                       -- Tab
    delay 0.3
    key code 0 using {command down}
    delay 0.15
    key code 51
    delay 0.15
    keystroke "$KAKAO_PW"
    delay 0.4
    key code 36                       -- Enter
  end tell
end tell
EOF
```

### 2.2 채팅 탭 활성화 (목록 조회 전 필수)
카톡 메인창이 친구 탭에 있으면 `--list`가 0개 반환. 항상 채팅 탭부터:
```bash
osascript -e 'tell application "KakaoTalk" to activate' && \
osascript -e 'tell application "System Events" to tell process "KakaoTalk" to key code 19 using {command down}'
# Cmd+1=친구, Cmd+2=채팅, Cmd+3=더보기
```

## 3. 핵심 명령어 (플러그인 호출)

플러그인 경로: `~/github/plugins-for-claude-natives/plugins/kakaotalk/scripts/`

```bash
# 코어(읽기/전송) = 플러그인 레포
ALIAS_RUN='source $HOME/.local/bin/env && cd ~/github/plugins-for-claude-natives/plugins/kakaotalk/scripts && uv run --with atomacos --python 3.12 python'
# 이 스킬의 래퍼(send_safe/targets 등) = 스킬 scripts/ (SKILLDIR 은 이 SKILL.md 가 있는 폴더)
ALIAS_RUN_SAFE='source $HOME/.local/bin/env && cd "$SKILLDIR/scripts" && uv run --with atomacos --python 3.12 python'
```

### 채팅방 검색
```bash
$ALIAS_RUN kakao_read.py --search "키워드" --json
```

### 채팅방 목록 (채팅 탭일 때만)
```bash
$ALIAS_RUN kakao_read.py --list --limit 50 --json
```

### 메시지 읽기 (오늘만, 정확 날짜)
```bash
# --date YYYY-MM-DD, --scroll-up/down N, --limit N
$ALIAS_RUN kakao_read.py "채팅방" --scroll-down 5 --date 2026-05-29 --json --limit 200
```

### 메시지 보내기 (텍스트)
```bash
$ALIAS_RUN kakao_send.py "채팅방" "메시지"
# 옵션: --no-signature, --close, --json
```

### 이미지 전송 (PNG)
**권장: `send_safe.py --image`** — 입력란을 **동적으로 찾아**(AXTextArea 최하단) 포커스하므로 고정 좌표가 필요 없다. 창을 옮기거나 크기를 바꿔도 안전.
```bash
$ALIAS_RUN_SAFE send_safe.py "채팅방" --image /path/to.png --json
# (나)에게 보낼 땐 --verify-me 추가
```
> ⚠️ 고정 좌표(`click at {x,y}`)로 입력란을 클릭하는 방식은 **금지**. 사용자가 창을 옮기면 깨진다. 좌표가 필요하면 `send_safe.get_input_area_position()`처럼 AXPosition+AXSize에서 매번 재계산할 것.

### 파일 전송 (⚠️ 현재 미동작 — 4번 한계 참조)
신뢰성 있는 파일 전송은 카톡 입력란 옆의 첨부 버튼(클립 아이콘) 직접 클릭이 필요. 향후 구현 예정.

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
9. **키워드 알람** — 단톡방에서 특정 키워드 발생 시 Telegram 알림 (텔레그램 봇 통합)
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

## 11. 오픈채팅 방 일괄 조사 (URL·공지·존재여부) — 2026-06-16 검증

번호가 연속된 여러 오픈채팅방(예: `"<프리픽스>_체험단01~NN"`)을 전수 조사해 **존재여부 / 채팅방 URL / 공지**를 시트로 정리하는 워크플로. 실전 검증된 기법과 함정:

### 11.1 오픈채팅 탭과 채팅 탭은 별개 — 검색을 구분
- 메인창 상단에 **`채팅` / `오픈채팅` 두 탭(AXButton)** 이 있다. 오픈채팅방은 **오픈채팅 탭에서만** 검색에 잡힌다. 채팅 탭에서 검색하면 일부 번대(예: 3·4·5번대)가 **빈 결과**로 누락된다 → "없는 방"으로 오판 금지.
- 탭 전환: AXButton('오픈채팅')의 `AXPosition+AXSize` 중앙을 **좌표 클릭**(`osascript ... click at {x,y}`). PID ref에서 `.Press()`는 실패할 수 있어 좌표 클릭이 안정적.
- 전수 열거: `kakao_read.search_chats('<프리픽스>_체험단0')`, `...1`, `...2` … 십자리별로 검색(결과 20개 제한이라 십자리 단위가 안전). 검색은 flaky하니 **빈 결과는 2~3회 재시도**. 빠진 번호는 개별 정밀검색(`체험단{NN}` 부분문자열 매칭)으로 재확인 후에만 "없음" 판정.
- "없는 방 = 강퇴/내보내짐"인 경우가 많다. 이름 앞뒤에 다른 토큰이 붙어 번호가 중간에 임베드된 변종도 있음(예: `<다른토큰>_<프리픽스>_체험단36_…`) → 부분문자열 매칭으로 잡는다.

### 11.2 채팅방 URL 조회 = 메뉴바 "채팅 > 채팅방 URL 복사"
- 방 창을 연/포커스한 상태에서 메뉴바 **AXMenuBar → '채팅' → '채팅방 URL 복사'** 를 `.Press()` → `pbpaste`로 `https://open.kakao.com/o/...` 획득.
- **false-positive 방지**: 복사 전 클립보드에 sentinel을 넣고, 복사 후 값이 sentinel과 같으면 '조회 불가', 메뉴 항목 `AXEnabled=False`면 '비활성'으로 판정.
- (검증: 39개 방 전부 조회 가능했음)

### 11.3 공지(공지사항)는 AX/OCR 불가 → 창 영역 캡처 후 이미지 판독
- 노란/회색 **공지 배너는 접근성 텍스트가 없는 커스텀 렌더링** → AX 트리에 안 잡힘. macOS Vision OCR도 **한국어는 깨짐**(폰트 문제). 유일한 방법: **창 영역만 캡처 → 이미지를 직접 판독(Claude가 읽기)**.
- 창 bounds는 **System Events `position`/`size`** 로 받는다(신뢰). `CGWindowListCopyWindowInfo`는 카톡 창을 **빈 결과**로 반환하고, AX `AXPosition`은 깨진 상태에서 엉뚱한 값(예: 84×77)을 주며 `set AXPosition`은 not-settable. 캡처: `screencapture -x -R<x,y,w,h> out.png` (음수 좌표=좌측 보조모니터도 캡처됨).
- 공지 **접힘/펼침 상태가 방마다 다름**: 접히면 첫 줄(제목)만, 펼치면 본문(단 길면 "전체보기"로 잘림). 전체 본문 필요 시 "전체보기" 클릭이 필요하나 좌표가 fragile → 가시 내용 + "(접힘/전체보기 더 있음)" 플래그로 마무리.

### 11.4 전송(브로드캐스트) — 보내자마자 즉시 검증 (★중요)
- 활발한 방은 **전송 직후 새 메시지가 폭주**해 내 메시지가 위로 밀린다 → **보내자마자 즉시** 스크린샷 또는 마지막 보낸 메시지를 확인할 것. (지연 검증하면 "안 보내졌다"고 오판함 — 실제론 전송됨)
- 전송 전 **입력란을 명시적으로 클릭**(창 하단 중앙 좌표)해 포커스 확보 후 `Cmd+A`→`Delete`(잔여 제거)→`pbcopy`+`Cmd+V`(멀티라인/이모지 보존)→`Enter`. 방을 연 직후 포커스가 입력란이 아닐 수 있음.

### 11.5 환경 함정 (atomacos / 재시작)
- **`getAppRefByBundleId('com.kakao.KakaoTalkMac')` 가 "not found in running apps"로 깨질 때가 있다** (NSWorkspace가 `frontmost: None` + 앱 몇 개만 보이는 비정상 세션 뷰). 우회: `pid = pgrep -x KakaoTalk` → **`atomacos.getAppRefByPid(pid)`**. `kakao_read.get_kakao_app`/`kakao_send.get_kakao_app`를 PID 버전으로 **몽키패치**하면 내부 호출까지 우회됨. (단 PID ref에서 메시지 텍스트 추출이 빈 값으로 나올 수 있어, 내용 검증은 스크린샷 권장)
- **카톡을 `killall`/quit로 재시작하면 로그아웃된다(자동로그인 유지 안 됨)** → 함부로 재시작 금지. 재시작했으면 2.1 자동 로그인 시퀀스로 재로그인.
- CC Bash 셸이 **i386(Rosetta)** 라, 이 셸에서 `open -a`로 카톡을 띄우면 NSWorkspace 등록이 틀어질 수 있음(`arch -arm64 open`도 완전 해결 안 됨). 결론: **PID 우회가 가장 확실**.

## 12. 방 열기 신뢰 패턴 / 이름 매칭 함정

### 12.1 검색 이름 ≠ 읽기·전송 호출 이름 (괄호/특수문자)
- 채팅방명에 **괄호 `(...)` / 대괄호 / 이모지**가 있으면 `--search`는 잘 잡지만, **직접 호출(`kakao_read.py "<풀네임>"`)은 "채팅방을 찾을 수 없습니다"로 실패**할 수 있다. 카톡 검색 인덱스가 괄호 토큰을 다르게 처리하는 것으로 추정.
- 대응: 호출 실패 시 **특수문자를 제거하고 핵심 토큰만으로 재시도**(예: `(3pl) ○○컴퍼니` → `○○컴퍼니`). 검색 결과 문자열을 그대로 호출에 쓰지 말고 `send_safe.py`의 `normalize_chat_name`을 거친다.

### 12.2 "채팅창 못 찾음" = 단일창 단정 금지 → 방 열기 자체가 실패한 것
카톡 Mac은 **멀티창 모드가 정상**(채팅 더블클릭 시 별도 창이 뜸). `send_safe.py`/`kakao_send.py`가 "채팅창 못 찾음"으로 실패하면 단일창 모드가 아니라 **방 열기 단계가 불안정해서 별도 창이 안 뜬 것**. 다음 순서가 가장 신뢰도 높음:
1. **검색창 포커스**: atomacos `field.AXFocused = True`. (Cmd+F는 토글/포커스가 불안정해 비추)
2. **한글 입력**: 클립보드 `pbcopy` + **Cmd+V(`key code 9`)**. System Events `keystroke "한글"`은 영문 IME에서 깨짐(예: "aa").
3. **방 열기**: **Quartz 정식 더블클릭** — `CGEventSetIntegerValueField(e, kCGMouseEventClickState, cs)`로 down/up(cs=1) 후 다시 down/up(cs=2). 단일클릭·`Down+Enter`·단발 클릭은 안 열림. 행 좌표는 atomacos `AXRow`의 `AXPosition + AXSize/2`.
4. 별도 창(AXTitle=방이름, AXTextArea 다수)이 뜨면 → `send_safe.py "방이름" --text "..."`가 정상 작동.
5. 검증: 결과 `ok:true` + `rows_before < rows_after`.

**오발송 가드**: 동명이인/유사방이 여러 개면 atomacos로 **행 이름을 정확매칭한 그 행만** 더블클릭. 본인(나) 채팅 식별은 §4 'badge me'(채팅 목록 row에만 있고 채팅창 헤더엔 없음) 검증을 반드시 거친다.

## 13. 타겟(방 묶음) — 반복 작업의 대상 분리

**개념**: 이 스킬(§11 일괄조사, §11.4 브로드캐스트 등)은 **범용 엔진**이다. 특정 작업 대상(예: "○○ 체험단 39개 방")은 스킬에 하드코딩하지 않고 **'타겟'이라는 레포 밖 데이터**로 분리한다. 타겟은 *고정 메시지를 반복 발송하는 캠페인이 아니라*, 그때그때 다른 작업을 돌릴 **고정된 방 집합**이다. 자격증명(`config.json`)과 같은 원칙: 개인/계정 종속 데이터는 `~/.config/kakao_manager/` 에.

- 저장: `~/.config/kakao_manager/targets/<name>.json` (gitignore, 0600). 템플릿: `scripts/target.example.json`.
- 데이터 레이어: `scripts/targets.py` (엔진이 아니라 **데이터 CRUD**만; AX 자동화는 Claude가 §11~§12 절차로 구동).

```bash
python3 scripts/targets.py --list                 # 등록된 타겟
python3 scripts/targets.py --init <name>          # 템플릿 복사 → account/prefix/rooms 채우기
python3 scripts/targets.py --account <name>       # 이 타겟의 계정 key (config.py --account 로 전달)
python3 scripts/targets.py --rooms <name>         # 방 제목 한 줄씩 (브로드캐스트 루프용)
python3 scripts/targets.py --rooms <name> --field url   # URL만
echo '{"rooms":[...]}' | python3 scripts/targets.py --save <name> --at <ISO>  # 일괄조사 스냅샷 저장
```

**작업 흐름 예** ("<name> 방들 일괄조사해줘"):
1. `ACC=$(targets.py --account <name>)` → 해당 계정으로 로그인/활성화(§2)
2. `prefix`/`number_range`로 §11.1 전수 검색 → 존재/URL/공지 수집
3. 결과를 `targets.py --save <name> --at <ISO>` 로 스냅샷 저장 + (필요 시) 구글시트 정리
4. ("<name> 방들에 이거 보내줘") → `targets.py --rooms <name>` 루프 + §11.4(보내자마자 즉시 검증) + 방 닫고 다음

> 공개 레포엔 타겟 **이름조차** 들어가지 않는다. 새 작업 대상이 생기면 `targets.py --init`로 로컬에만 만든다.
