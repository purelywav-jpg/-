# 네이버 블로그 자동 작성 툴

사진 몇 장 넣고 메모 한 줄 쓰면, 네이버 상위노출 공식이 적용된 블로그 글이 완성되고 임시저장까지 되는 Claude Code 툴입니다. 자세한 규칙은 [`CLAUDE.md`](./CLAUDE.md) 를 참고하세요.

## ⚠️ 이 코드는 원격(클라우드) 세션에서 생성되었습니다

네이버 로그인(비밀번호/2단계 인증/패스키를 직접 눈으로 보고 입력)과 브라우저 자동화로 임시저장하는 과정은 **화면을 볼 수 있는 로컬 컴퓨터에서만** 동작합니다. 이 브랜치를 로컬로 내려받아 아래 순서대로 진행하세요.

## 로컬 설치 순서

1. 이 브랜치를 pull 받은 뒤 `naver-blog-writer/` 폴더로 이동합니다.
2. Node.js(LTS)가 없다면 설치합니다.
3. 터미널에서:
   ```
   npm install
   npx playwright install chromium
   ```
4. `data/config.json` 의 `naverBlogId` 에 본인 네이버 블로그 아이디(blog.naver.com/뒤의 아이디)를 채웁니다.
5. 이 폴더에서 `claude` 실행 → `/setup-login` (또는 `node scripts/naver_login.js`) 으로 브라우저가 뜨면 직접 로그인합니다. 로그인 세션은 `naver-profile/` 폴더에 저장되며(비밀번호는 저장 안 됨), `.gitignore`에 포함되어 있어 커밋되지 않습니다.
6. `data/profile.md`, `data/blogger-profile.md` 를 열어 업종·목표·지역·화자 톤 등을 채우세요. 비워두면 Claude Code가 첫 `/write` 실행 시 인터뷰로 물어봅니다.
7. `input/photos/` 에 사진을 넣고 채팅에 `/write <소재 메모>` 를 입력하면 초안 생성 → 검수 → 승인 → 임시저장까지 진행됩니다.

## 폴더 구조

- `CLAUDE.md` — 마스터 지침 (절대 규칙, 글쓰기 공식, 실측 셀렉터 지식)
- `.claude/commands/` — `/write`, `/learn-style`, `/analyze-trends`, `/setup-login`
- `scripts/` — Playwright 자동화 (`naver_login.js`, `naver_draft.js`, `mosaic.js`, `probe_selectors.js`)
- `data/` — 사실 정보(`profile.md`), 화자 캐릭터(`blogger-profile.md`), 권위 문구·촬영 가이드·협찬 표기 문구, 학습된 트렌드/문체
- `input/photos/`, `input/videos/` — 소재 사진·영상 (커밋되지 않음)
- `drafts/` — 생성된 초안 JSON과 검증용 스크린샷/텍스트 덤프 (커밋되지 않음, 예시 파일만 예외)

## 안전장치

- **발행 금지**: `scripts/lib/browser.js` 의 `installPublishGuard()` 가 진짜 발행 버튼 클릭을 코드 수준에서 항상 차단합니다. 임시저장까지만 자동화하며, 발행은 항상 사람이 직접 합니다.
- **사실 지어내기 금지**: `data/profile.md` 와 사진에서 확인된 정보만 사용하고, 확인 안 된 정보는 되묻습니다.
- **협찬 표기**: 공정위 표시광고법에 따라 협찬·체험단 글은 `data/sponsored-disclosure.md` 의 문구를 본문 상단에 자동 포함합니다.
- **개인정보 모자이크**: 사진에 타인 얼굴·차량 번호판 등이 보이면 `scripts/mosaic.js` 로 모자이크 처리 후 원본 대신 처리본을 사용합니다.

## 비용

API 요금 없이 Claude 구독 토큰만 사용합니다. 상위 모델(Opus 등)은 글쓰기 품질이 좋은 대신 사용량을 빨리 소모하니, 글쓰기는 상위 모델로 트렌드 분석·오류 수정은 하위 모델로 돌리는 것을 권장합니다.

## 주의

브라우저 자동화는 네이버 약관상 회색지대입니다. 본인 계정으로, 하루 1~2건 수준으로만 사용하세요. `naver-profile/` 폴더는 로그인 세션이므로 외부 공유·커밋을 금지합니다.
