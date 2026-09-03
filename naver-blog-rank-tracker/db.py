"""SQLite schema + connection helper for the Naver blog rank tracker."""
import os
import sqlite3

DB_PATH = os.environ.get(
    "NAVER_TRACKER_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tracker.db"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    blog_id     TEXT NOT NULL,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL UNIQUE,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    deleted_at  TEXT
);

CREATE TABLE IF NOT EXISTS keywords (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword     TEXT NOT NULL UNIQUE,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS post_keywords (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id     INTEGER NOT NULL REFERENCES posts(id),
    keyword_id  INTEGER NOT NULL REFERENCES keywords(id),
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE(post_id, keyword_id)
);

CREATE TABLE IF NOT EXISTS rank_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id       INTEGER NOT NULL REFERENCES posts(id),
    keyword_id    INTEGER NOT NULL REFERENCES keywords(id),
    rank          INTEGER,
    status        TEXT NOT NULL CHECK(status IN ('RANKED', 'NOT_FOUND', 'ERROR')),
    checked_date  TEXT NOT NULL,
    checked_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE(post_id, keyword_id, checked_date)
);

CREATE INDEX IF NOT EXISTS idx_rank_history_lookup
    ON rank_history(post_id, keyword_id, checked_date);
"""


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


DEFAULT_POSTS = [
    {
        "title": "남양주 보컬학원 다산 실용음악학원 실력과 시스템 전부 만족한 메트뮤직레이블",
        "url": "https://m.blog.naver.com/wlsdud9601/224325536475",
        "keywords": ["남양주 보컬학원", "다산 실용음악학원"],
    },
    {
        "title": "성복역 테라피를 찾는다면 이바롬에스테틱 용인 수지 피부관리 소개",
        "url": "https://m.blog.naver.com/wlsdud9601/224392309865",
        "keywords": ["성복역 테라피", "용인 수지 피부관리"],
    },
    {
        "title": "송리단길 데이트 마레이스튜디오 송파 향수 후기",
        "url": "https://m.blog.naver.com/wlsdud9601/224399151376",
        "keywords": ["송리단길 데이트", "송파 향수"],
    },
    {
        "title": "위례 헬스장 추천 | 그룹 PT 무제한 가능, 위례역 헬스장 MVM 피트니스 위례역점.",
        "url": "https://m.blog.naver.com/wlsdud9601/224162854801",
        "keywords": ["위례 헬스장 추천", "위례역 헬스장"],
    },
    {
        "title": "위례역 헬스장 추천｜위례 헬스장 MVM 피트니스 위례역점 여성 1만원 후기",
        "url": "https://m.blog.naver.com/wlsdud9601/224162054049",
        "keywords": ["위례역 헬스장 추천", "위례 헬스장"],
    },
]


def seed_if_empty():
    """Populate the 5 posts / 10 keywords from the spec on first run only."""
    import re

    conn = get_conn()
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM posts").fetchone()["c"]
        if count > 0:
            return False
        for p in DEFAULT_POSTS:
            m = re.search(r"blog\.naver\.com/([^/]+)/(\d+)", p["url"])
            blog_id = m.group(1) if m else ""
            cur = conn.execute(
                "INSERT INTO posts (blog_id, title, url) VALUES (?, ?, ?)",
                (blog_id, p["title"], p["url"]),
            )
            post_id = cur.lastrowid
            for kw in p["keywords"]:
                kw_row = conn.execute(
                    "SELECT id FROM keywords WHERE keyword = ?", (kw,)
                ).fetchone()
                if kw_row:
                    keyword_id = kw_row["id"]
                else:
                    keyword_id = conn.execute(
                        "INSERT INTO keywords (keyword) VALUES (?)", (kw,)
                    ).lastrowid
                conn.execute(
                    "INSERT OR IGNORE INTO post_keywords (post_id, keyword_id) VALUES (?, ?)",
                    (post_id, keyword_id),
                )
        conn.commit()
        return True
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    seeded = seed_if_empty()
    print(f"DB initialized at {DB_PATH}")
    print("Seed data inserted." if seeded else "Seed data already present, skipped.")
