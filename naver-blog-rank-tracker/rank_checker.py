"""Daily rank check job (spec section 19).

1. active posts 확인 -> 2. 연결된 키워드 확인 -> 3. 네이버 검색 ->
4. 포스팅 순위 확인 -> 5. 오늘 데이터 저장 -> 6. 전일 순위와 비교 ->
7. ▲/▼ 계산 -> 8. 월간 통계는 조회 시점에 계산되므로 별도 저장 불필요.

Run manually with `python rank_checker.py`, or wire it into cron /
Task Scheduler for a daily automatic run (see README).
"""
import argparse
import sys
from datetime import date

import models
from naver_api import DEFAULT_MAX_RANK, search_rank


def run_daily_check(check_date: str = None, max_rank: int = DEFAULT_MAX_RANK, verbose: bool = True):
    check_date = check_date or date.today().isoformat()
    pairs = models.list_all_active_post_keywords()

    results = []
    for pair in pairs:
        prev = models.get_previous_rank(pair["post_id"], pair["keyword_id"], check_date)
        prev_rank = prev["rank"] if prev and prev["status"] == "RANKED" else None

        rank, status = search_rank(pair["keyword"], pair["url"], max_rank=max_rank)
        stored = models.record_rank(
            pair["post_id"], pair["keyword_id"], rank, status, check_date
        )

        label, delta = models.diff_display(prev_rank, status, rank)
        result = {
            **pair,
            "rank": rank,
            "status": status,
            "change_label": label,
            "stored": stored,
        }
        results.append(result)

        if verbose:
            rank_disp = f"{rank}위" if status == "RANKED" else "미노출"
            dup = "" if stored else " (이미 측정됨, 스킵)"
            print(
                f"[{pair['title'][:24]:<24}] {pair['keyword']:<16} "
                f"{rank_disp:<8} {label}{dup}"
            )

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="네이버 블로그 순위 일일 체크")
    parser.add_argument("--date", help="YYYY-MM-DD (기본값: 오늘)", default=None)
    parser.add_argument(
        "--max-rank", type=int, default=DEFAULT_MAX_RANK, help="최대 검색 순위 (기본 100)"
    )
    args = parser.parse_args()

    import db as db_module

    db_module.init_db()
    db_module.seed_if_empty()

    print(f"=== 순위 체크 시작: {args.date or date.today().isoformat()} "
          f"(네이버 블로그 검색 API 기준 순위, 최대 {args.max_rank}위까지 확인) ===")
    run_daily_check(check_date=args.date, max_rank=args.max_rank)
    print("=== 완료 ===")
    sys.exit(0)
