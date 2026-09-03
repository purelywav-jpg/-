"""Data-access + business logic for posts, keywords and rank history."""
import calendar
import re
from datetime import date, datetime, timedelta

from db import get_conn


# ---------------------------------------------------------------- helpers --
def _extract_blog_id(url: str) -> str:
    m = re.search(r"blog\.naver\.com/([^/?#]+)/(\d+)", url or "")
    return m.group(1) if m else ""


def diff_display(prev_rank, curr_status, curr_rank):
    """Compute the change marker per spec section 1/2/23.

    Returns (label, delta) where delta is an int (positive = improved) or
    None when there is nothing to subtract (NEW / OUT / both unranked).
    """
    curr_ranked = curr_status == "RANKED"
    if prev_rank is None and curr_ranked:
        return "NEW ▲", None
    if prev_rank is not None and not curr_ranked:
        return "OUT ▼", None
    if prev_rank is None and not curr_ranked:
        return "-", None
    delta = prev_rank - curr_rank
    if delta > 0:
        return f"▲{delta}", delta
    if delta < 0:
        return f"▼{-delta}", delta
    return "-", 0


# ------------------------------------------------------------------ posts --
def add_post(title: str, url: str, keywords):
    conn = get_conn()
    try:
        blog_id = _extract_blog_id(url)
        cur = conn.execute(
            "INSERT INTO posts (blog_id, title, url) VALUES (?, ?, ?)",
            (blog_id, title, url),
        )
        post_id = cur.lastrowid
        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            add_keyword_to_post(post_id, kw, conn=conn)
        conn.commit()
        return post_id
    finally:
        conn.close()


def update_post(post_id: int, title: str = None, url: str = None):
    conn = get_conn()
    try:
        if title is not None:
            conn.execute("UPDATE posts SET title = ? WHERE id = ?", (title, post_id))
        if url is not None:
            conn.execute(
                "UPDATE posts SET url = ?, blog_id = ? WHERE id = ?",
                (url, _extract_blog_id(url), post_id),
            )
        conn.commit()
    finally:
        conn.close()


def delete_post(post_id: int):
    """Soft delete: removes it from active tracking but keeps all history."""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE posts SET is_active = 0, deleted_at = datetime('now', 'localtime') "
            "WHERE id = ?",
            (post_id,),
        )
        conn.commit()
    finally:
        conn.close()


def restore_post(post_id: int):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE posts SET is_active = 1, deleted_at = NULL WHERE id = ?",
            (post_id,),
        )
        conn.commit()
    finally:
        conn.close()


def list_posts(active_only: bool = True):
    conn = get_conn()
    try:
        q = "SELECT * FROM posts"
        if active_only:
            q += " WHERE is_active = 1"
        q += " ORDER BY id"
        return [dict(r) for r in conn.execute(q).fetchall()]
    finally:
        conn.close()


def get_post(post_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# --------------------------------------------------------------- keywords --
def get_or_create_keyword(keyword: str, conn=None):
    owns_conn = conn is None
    conn = conn or get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM keywords WHERE keyword = ?", (keyword,)
        ).fetchone()
        if row:
            keyword_id = row["id"]
            conn.execute(
                "UPDATE keywords SET is_active = 1 WHERE id = ?", (keyword_id,)
            )
        else:
            keyword_id = conn.execute(
                "INSERT INTO keywords (keyword) VALUES (?)", (keyword,)
            ).lastrowid
        if owns_conn:
            conn.commit()
        return keyword_id
    finally:
        if owns_conn:
            conn.close()


def add_keyword_to_post(post_id: int, keyword: str, conn=None):
    owns_conn = conn is None
    conn = conn or get_conn()
    try:
        keyword_id = get_or_create_keyword(keyword, conn=conn)
        conn.execute(
            "INSERT INTO post_keywords (post_id, keyword_id, is_active) "
            "VALUES (?, ?, 1) "
            "ON CONFLICT(post_id, keyword_id) DO UPDATE SET is_active = 1",
            (post_id, keyword_id),
        )
        if owns_conn:
            conn.commit()
        return keyword_id
    finally:
        if owns_conn:
            conn.close()


def remove_keyword_from_post(post_id: int, keyword_id: int):
    """Unlink a keyword from a post (history is preserved)."""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE post_keywords SET is_active = 0 "
            "WHERE post_id = ? AND keyword_id = ?",
            (post_id, keyword_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_keywords_for_post(post_id: int, active_only: bool = True):
    conn = get_conn()
    try:
        q = (
            "SELECT k.id, k.keyword, pk.is_active FROM post_keywords pk "
            "JOIN keywords k ON k.id = pk.keyword_id WHERE pk.post_id = ?"
        )
        if active_only:
            q += " AND pk.is_active = 1"
        q += " ORDER BY k.id"
        return [dict(r) for r in conn.execute(q, (post_id,)).fetchall()]
    finally:
        conn.close()


def list_all_active_post_keywords():
    """All (post, keyword) pairs that should be checked today."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT p.id AS post_id, p.title, p.url, p.blog_id, "
            "       k.id AS keyword_id, k.keyword "
            "FROM post_keywords pk "
            "JOIN posts p ON p.id = pk.post_id "
            "JOIN keywords k ON k.id = pk.keyword_id "
            "WHERE pk.is_active = 1 AND p.is_active = 1 AND k.is_active = 1 "
            "ORDER BY p.id, k.id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ----------------------------------------------------------- rank history --
def record_rank(post_id, keyword_id, rank, status, checked_date):
    """Insert today's measurement. No-ops silently if one already exists for
    this (post, keyword, date) -- duplicate-measurement guard (spec 20)."""
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO rank_history "
            "(post_id, keyword_id, rank, status, checked_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (post_id, keyword_id, rank, status, checked_date),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_previous_rank(post_id, keyword_id, before_date):
    """Most recent measurement strictly before `before_date`."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT rank, status, checked_date FROM rank_history "
            "WHERE post_id = ? AND keyword_id = ? AND checked_date < ? "
            "ORDER BY checked_date DESC LIMIT 1",
            (post_id, keyword_id, before_date),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_latest_rank(post_id, keyword_id):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT rank, status, checked_date FROM rank_history "
            "WHERE post_id = ? AND keyword_id = ? "
            "ORDER BY checked_date DESC LIMIT 1",
            (post_id, keyword_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_history(post_id, keyword_id, year: int, month: int):
    """All daily rows within a given YYYY-MM, sorted by date (spec 8/9)."""
    conn = get_conn()
    try:
        prefix = f"{year:04d}-{month:02d}"
        rows = conn.execute(
            "SELECT rank, status, checked_date FROM rank_history "
            "WHERE post_id = ? AND keyword_id = ? AND checked_date LIKE ? "
            "ORDER BY checked_date",
            (post_id, keyword_id, f"{prefix}%"),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def monthly_summary(post_id, keyword_id, year: int, month: int):
    """Spec section 10: 월초/월말/현재/최고/최저/평균/월간변화/노출/미노출 일수."""
    rows = get_history(post_id, keyword_id, year, month)
    ranked = [r["rank"] for r in rows if r["status"] == "RANKED" and r["rank"] is not None]
    latest_overall = get_latest_rank(post_id, keyword_id)

    summary = {
        "start_rank": None,
        "end_rank": None,
        "current_rank": latest_overall["rank"] if latest_overall else None,
        "current_status": latest_overall["status"] if latest_overall else "NOT_FOUND",
        "best_rank": min(ranked) if ranked else None,
        "worst_rank": max(ranked) if ranked else None,
        "avg_rank": round(sum(ranked) / len(ranked), 1) if ranked else None,
        "change_label": "-",
        "change_delta": None,
        "days_ranked": len(ranked),
        "days_not_found": sum(1 for r in rows if r["status"] == "NOT_FOUND"),
        "days_measured": len(rows),
    }

    ranked_rows = [r for r in rows if r["status"] == "RANKED"]
    if ranked_rows:
        summary["start_rank"] = ranked_rows[0]["rank"]
        summary["end_rank"] = ranked_rows[-1]["rank"]
        label, delta = diff_display(
            summary["start_rank"], "RANKED", summary["end_rank"]
        )
        summary["change_label"] = label
        summary["change_delta"] = delta

    return summary


def graph_series(post_id, keyword_id, year: int, month: int):
    """Spec section 9: one point per day the rank was actually measured,
    ready for a rank chart (small y = better, so charts should invert axis)."""
    rows = get_history(post_id, keyword_id, year, month)
    return [
        {"date": r["checked_date"], "rank": r["rank"], "status": r["status"]}
        for r in rows
    ]


def available_months():
    """Distinct YYYY-MM values that have any recorded data (spec 17)."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT substr(checked_date, 1, 7) AS ym FROM rank_history "
            "ORDER BY ym DESC"
        ).fetchall()
        months = [r["ym"] for r in rows]
        this_month = date.today().strftime("%Y-%m")
        if this_month not in months:
            months.insert(0, this_month)
        return months
    finally:
        conn.close()


def dashboard_summary(today: str = None):
    """Spec section 12: overall dashboard counters for the given day."""
    today = today or date.today().isoformat()
    posts = list_posts(active_only=True)
    pairs = list_all_active_post_keywords()

    top10 = top30 = not_found = 0
    up = down = same = 0
    rows_out = []

    for pair in pairs:
        latest = get_latest_rank(pair["post_id"], pair["keyword_id"])
        prev = get_previous_rank(pair["post_id"], pair["keyword_id"], today)

        status = latest["status"] if latest else "NOT_FOUND"
        rank = latest["rank"] if latest else None

        if status == "RANKED" and rank is not None:
            if rank <= 10:
                top10 += 1
            if rank <= 30:
                top30 += 1
        else:
            not_found += 1

        prev_rank = prev["rank"] if prev and prev["status"] == "RANKED" else None
        label, delta = diff_display(prev_rank, status, rank)
        if delta is not None and delta > 0:
            up += 1
        elif delta is not None and delta < 0:
            down += 1
        else:
            same += 1

        rows_out.append(
            {
                "post_id": pair["post_id"],
                "post_title": pair["title"],
                "post_url": pair["url"],
                "keyword_id": pair["keyword_id"],
                "keyword": pair["keyword"],
                "rank": rank,
                "status": status,
                "change_label": label,
                "change_delta": delta,
            }
        )

    return {
        "date": today,
        "post_count": len(posts),
        "keyword_count": len({p["keyword_id"] for p in pairs}),
        "top10": top10,
        "top30": top30,
        "not_found": not_found,
        "up": up,
        "down": down,
        "same": same,
        "rows": rows_out,
    }


def filter_rows(rows, mode: str):
    """Spec section 13 filter set."""
    if mode == "up":
        return [r for r in rows if (r["change_delta"] or 0) > 0]
    if mode == "down":
        return [r for r in rows if (r["change_delta"] or 0) < 0]
    if mode == "same":
        return [r for r in rows if r["status"] == "RANKED" and (r["change_delta"] or 0) == 0]
    if mode == "top10":
        return [r for r in rows if r["status"] == "RANKED" and r["rank"] and r["rank"] <= 10]
    if mode == "top30":
        return [r for r in rows if r["status"] == "RANKED" and r["rank"] and r["rank"] <= 30]
    if mode == "not_found":
        return [r for r in rows if r["status"] != "RANKED"]
    return rows


def month_days(year: int, month: int):
    return calendar.monthrange(year, month)[1]
