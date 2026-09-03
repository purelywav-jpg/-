"""Text menu for managing posts/keywords and checking ranks (spec section 5).

Run: python cli.py
"""
from datetime import date

import db
import models
from rank_checker import run_daily_check

MENU = """
==============================================
 네이버 블로그 순위추적 - 관리 메뉴
 (순위는 네이버 블로그 검색 API 기준입니다)
==============================================
 1. 포스팅 목록
 2. 포스팅 추가
 3. 포스팅 수정
 4. 포스팅 삭제
 5. 키워드 추가
 6. 키워드 삭제
 7. 순위 확인 (지금 바로 체크)
 8. 순위 이력 (월별 일자별)
 9. 월별 조회 (요약)
 0. 종료
==============================================
"""


def _print_posts(active_only=True):
    posts = models.list_posts(active_only=active_only)
    if not posts:
        print("등록된 포스팅이 없습니다.")
        return posts
    for p in posts:
        state = "" if p["is_active"] else " [삭제됨]"
        print(f"  [{p['id']}] {p['title']}{state}")
        print(f"        {p['url']}")
        kws = models.list_keywords_for_post(p["id"])
        if kws:
            print("        키워드: " + ", ".join(k["keyword"] for k in kws))
    return posts


def action_list_posts():
    print("\n--- 포스팅 목록 ---")
    _print_posts(active_only=True)


def action_add_post():
    print("\n--- 포스팅 추가 ---")
    title = input("포스팅 제목: ").strip()
    url = input("포스팅 URL: ").strip()
    print("추적 키워드를 한 줄에 하나씩 입력하세요. 빈 줄 입력 시 종료.")
    keywords = []
    while True:
        kw = input(f"키워드 {len(keywords) + 1}: ").strip()
        if not kw:
            break
        keywords.append(kw)
    if not title or not url or not keywords:
        print("제목/URL/키워드는 필수입니다. 취소되었습니다.")
        return
    post_id = models.add_post(title, url, keywords)
    print(f"등록 완료 (post_id={post_id}). 다음 순위체크부터 자동 포함됩니다.")


def action_edit_post():
    print("\n--- 포스팅 수정 ---")
    posts = _print_posts()
    if not posts:
        return
    try:
        post_id = int(input("수정할 포스팅 ID: ").strip())
    except ValueError:
        print("잘못된 입력입니다.")
        return
    post = models.get_post(post_id)
    if not post:
        print("해당 포스팅이 없습니다.")
        return
    new_title = input(f"새 제목 (엔터=유지, 현재: {post['title']}): ").strip()
    new_url = input(f"새 URL (엔터=유지, 현재: {post['url']}): ").strip()
    models.update_post(post_id, title=new_title or None, url=new_url or None)
    print("수정 완료.")


def action_delete_post():
    print("\n--- 포스팅 삭제 ---")
    posts = _print_posts()
    if not posts:
        return
    try:
        post_id = int(input("삭제할 포스팅 ID: ").strip())
    except ValueError:
        print("잘못된 입력입니다.")
        return
    models.delete_post(post_id)
    print("삭제 완료. (과거 순위 기록은 유지됩니다)")


def action_add_keyword():
    print("\n--- 키워드 추가 ---")
    posts = _print_posts()
    if not posts:
        return
    try:
        post_id = int(input("키워드를 추가할 포스팅 ID: ").strip())
    except ValueError:
        print("잘못된 입력입니다.")
        return
    kw = input("추가할 키워드: ").strip()
    if not kw:
        print("취소되었습니다.")
        return
    models.add_keyword_to_post(post_id, kw)
    print("추가 완료. 다음 순위체크부터 자동 포함됩니다.")


def action_delete_keyword():
    print("\n--- 키워드 삭제 ---")
    posts = _print_posts()
    if not posts:
        return
    try:
        post_id = int(input("포스팅 ID: ").strip())
    except ValueError:
        print("잘못된 입력입니다.")
        return
    kws = models.list_keywords_for_post(post_id)
    if not kws:
        print("연결된 키워드가 없습니다.")
        return
    for k in kws:
        print(f"  [{k['id']}] {k['keyword']}")
    try:
        keyword_id = int(input("삭제할 키워드 ID: ").strip())
    except ValueError:
        print("잘못된 입력입니다.")
        return
    models.remove_keyword_from_post(post_id, keyword_id)
    print("삭제 완료. (과거 순위 기록은 유지됩니다)")


def action_check_rank():
    print("\n--- 순위 확인 ---")
    run_daily_check(check_date=date.today().isoformat())


def action_history():
    print("\n--- 순위 이력 ---")
    posts = _print_posts()
    if not posts:
        return
    try:
        post_id = int(input("포스팅 ID: ").strip())
    except ValueError:
        print("잘못된 입력입니다.")
        return
    kws = models.list_keywords_for_post(post_id)
    for k in kws:
        print(f"  [{k['id']}] {k['keyword']}")
    try:
        keyword_id = int(input("키워드 ID: ").strip())
        year = int(input(f"연도 (기본 {date.today().year}): ") or date.today().year)
        month = int(input(f"월 (기본 {date.today().month}): ") or date.today().month)
    except ValueError:
        print("잘못된 입력입니다.")
        return
    rows = models.get_history(post_id, keyword_id, year, month)
    if not rows:
        print("데이터가 없습니다.")
        return
    for r in rows:
        d = r["checked_date"][5:]
        disp = f"{r['rank']}위" if r["status"] == "RANKED" else "미노출"
        print(f"  {d}   {disp}")


def action_monthly():
    print("\n--- 월별 조회 ---")
    months = models.available_months()
    print("조회 가능한 월: " + ", ".join(months))
    ym = input(f"조회할 월 (YYYY-MM, 기본 {months[0]}): ").strip() or months[0]
    year, month = (int(x) for x in ym.split("-"))
    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"{year}년 {month}월 순위 (네이버 블로그 검색 API 기준)")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    for p in models.list_posts(active_only=True):
        kws = models.list_keywords_for_post(p["id"])
        if not kws:
            continue
        print(f"\n포스팅: {p['title']}")
        print(f"{'키워드':<20}{'현재':>8}{'변동':>8}{'최고':>8}")
        for k in kws:
            s = models.monthly_summary(p["id"], k["id"], year, month)
            cur = f"{s['current_rank']}위" if s["current_rank"] else "미노출"
            best = f"{s['best_rank']}위" if s["best_rank"] else "-"
            print(f"{k['keyword']:<20}{cur:>8}{s['change_label']:>8}{best:>8}")


ACTIONS = {
    "1": action_list_posts,
    "2": action_add_post,
    "3": action_edit_post,
    "4": action_delete_post,
    "5": action_add_keyword,
    "6": action_delete_keyword,
    "7": action_check_rank,
    "8": action_history,
    "9": action_monthly,
}


def main():
    db.init_db()
    db.seed_if_empty()
    while True:
        print(MENU)
        choice = input("선택: ").strip()
        if choice == "0":
            print("종료합니다.")
            break
        action = ACTIONS.get(choice)
        if not action:
            print("잘못된 선택입니다.")
            continue
        try:
            action()
        except Exception as e:  # keep the menu alive on bad input / API errors
            print(f"오류가 발생했습니다: {e}")


if __name__ == "__main__":
    main()
