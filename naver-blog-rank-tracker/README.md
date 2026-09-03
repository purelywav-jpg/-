# 네이버 블로그 포스팅 순위추적 시스템

포스팅(블로그 글) + 키워드를 등록해두면, 네이버 블로그 검색 API로 매일 실제 순위를 측정해서
SQLite에 쌓고, 상승/하락/신규/이탈 변동과 월별 통계를 웹 대시보드와 CLI에서 확인할 수 있는 도구입니다.

**중요:** 모든 순위는 "네이버 블로그 검색 API 기준 순위"입니다. 실제 네이버 앱/PC 통합검색
노출 순위와 다를 수 있습니다. 화면 상단에 항상 이 안내 문구가 표시됩니다.

## 1. 준비

```bash
cd naver-blog-rank-tracker
python3 -m venv venv && source venv/bin/activate   # 선택 사항
pip install -r requirements.txt
cp .env.example .env
```

`.env` 파일을 열어 네이버 검색 API 키를 입력합니다.

1. https://developers.naver.com/apps 접속 후 로그인
2. "애플리케이션 등록" → 사용 API에서 **검색** 체크
3. 발급된 Client ID / Client Secret 을 `.env` 의
   `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` 에 입력

키가 없어도 프로그램 자체(등록/수정/삭제/화면)는 실행되지만, 실제 순위 조회(체크) 시에는
`ERROR` 상태로 기록되니 실제 사용을 위해서는 반드시 발급받아야 합니다.

## 2. 최초 실행 (DB 생성 + 기본 5개 포스팅/10개 키워드 등록)

```bash
python3 db.py
```

스펙에 명시된 5개 포스팅과 10개 키워드가 최초 1회만 자동으로 등록됩니다.
(이미 데이터가 있으면 건너뜁니다.)

## 3. 사용 방법

### 웹 대시보드 (추천)

```bash
python3 app.py
```

브라우저에서 http://localhost:5000 접속.

- **대시보드**: 오늘자 전체 현황(등록 포스팅/키워드 수, TOP10/TOP30/미노출, 오늘 상승/하락/변동없음),
  필터(전체/상승/하락/변동없음/TOP10/TOP30/미노출), "지금 순위 체크" 버튼
- **포스팅 관리**: 포스팅 목록/추가/수정/삭제, 포스팅별 키워드 추가/삭제
- **포스팅 상세**: 월 선택 → 키워드별 현재/변동/최고/최저/평균/노출일수 + 일자별 순위 그래프
- **월별 조회**: 월 선택 → 포스팅별 전체 키워드의 현재/최고/월간변화 요약

### CLI (터미널 메뉴)

```bash
python3 cli.py
```

포스팅 목록 / 추가 / 수정 / 삭제, 키워드 추가 / 삭제, 순위 확인, 순위 이력, 월별 조회를
번호로 선택해서 사용할 수 있습니다.

### 순위 체크만 단독 실행 (자동화용)

```bash
python3 rank_checker.py                 # 오늘 날짜로 체크
python3 rank_checker.py --max-rank 300  # 300위까지 검색
```

## 4. 매일 자동 실행 설정 (STEP 10)

### Linux/macOS: cron

```bash
crontab -e
# 매일 오전 9시에 실행
0 9 * * * /전체/경로/naver-blog-rank-tracker/scripts/run_daily_check.sh >> /전체/경로/naver-blog-rank-tracker/data/cron.log 2>&1
```

### Windows: 작업 스케줄러

"기본 작업 만들기" → 매일 원하는 시각 → 동작: 프로그램 시작
- 프로그램: `python.exe`
- 인수: `rank_checker.py`
- 시작 위치: `naver-blog-rank-tracker` 폴더 경로

## 5. 데이터 구조 (SQLite, `data/tracker.db`)

- `posts` (id, blog_id, title, url, is_active, created_at, deleted_at)
- `keywords` (id, keyword, is_active, created_at)
- `post_keywords` (id, post_id, keyword_id, is_active, created_at) — 같은 키워드에 여러
  포스팅을 연결할 수 있고, 각 포스팅은 고유 URL로 구분되어 개별 추적됩니다.
- `rank_history` (id, post_id, keyword_id, rank, status, checked_date, checked_at) —
  `UNIQUE(post_id, keyword_id, checked_date)` 로 하루 중복 측정을 DB 레벨에서 차단합니다.
  `status` 는 `RANKED` / `NOT_FOUND` / `ERROR` 중 하나이며, 순위를 임의로 추정하지 않고
  실제 API 응답에서 찾은 경우에만 `rank` 숫자를 저장합니다.

## 6. 순위 변동 계산 규칙

`변동 = 이전 순위 - 현재 순위` (숫자가 클수록 많이 상승)

| 상황 | 표시 |
|---|---|
| 이전 8위 → 오늘 15위 | `▼7` |
| 이전 15위 → 오늘 8위 | `▲7` |
| 이전 8위 → 오늘 8위 | `-` |
| 이전 미노출 → 오늘 12위 | `NEW ▲` |
| 이전 12위 → 오늘 미노출 | `OUT ▼` |

## 7. 포스팅/키워드 삭제 정책

포스팅이나 키워드를 삭제해도 `rank_history` 는 절대 삭제하지 않습니다. 삭제는 "현재 추적
목록에서 제외"하는 소프트 삭제(`is_active=0`)이며, 과거 월의 순위 데이터는 계속 조회할 수
있습니다.

## 8. 알려진 제약

- 네이버 검색 API는 한 키워드당 최대 1000위(요청 파라미터 `start`+`display` ≤ 1000)까지만
  조회할 수 있습니다. `NAVER_TRACKER_MAX_RANK` 로 조절하세요(기본 100위).
- 네이버 오픈 API는 일일 호출 한도가 있습니다(애플리케이션 기준 25,000회/일). 포스팅×키워드
  조합이 매우 많다면 `--max-rank` 를 낮춰 호출량을 줄이세요.
