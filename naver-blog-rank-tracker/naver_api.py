"""Thin wrapper around the Naver Search API (blog search) used to find the
actual rank of a specific post URL for a given keyword.

Requires a Naver "검색 API" application registered at
https://developers.naver.com/apps -> Client ID / Client Secret, provided via
the NAVER_CLIENT_ID / NAVER_CLIENT_SECRET environment variables (see .env.example).

We never guess or estimate a rank: if the API errors out we return status
ERROR, and if the post is not found within max_rank results we return
NOT_FOUND. Only a rank actually observed in the API response is stored.
"""
import os
import re
import time

import requests
from dotenv import load_dotenv

load_dotenv()

SEARCH_URL = "https://openapi.naver.com/v1/search/blog.json"
PAGE_SIZE = 100  # Naver max display per request
DEFAULT_MAX_RANK = int(os.environ.get("NAVER_TRACKER_MAX_RANK", "100"))

_LINK_RE = re.compile(r"blog\.naver\.com/([^/?#]+)/(\d+)")


class NaverAPIError(Exception):
    pass


def extract_blog_id_lognum(url: str):
    """Pull (blog_id, log_no) out of any naver blog URL flavor
    (m.blog.naver.com, blog.naver.com, PostView.naver?blogId=...&logNo=...)."""
    m = _LINK_RE.search(url or "")
    if m:
        return m.group(1), m.group(2)
    m2 = re.search(r"blogId=([^&]+)", url or "")
    m3 = re.search(r"logNo=(\d+)", url or "")
    if m2 and m3:
        return m2.group(1), m3.group(1)
    return None, None


def _get_credentials():
    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise NaverAPIError(
            "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET is not set. "
            "Create an app at https://developers.naver.com/apps and set them "
            "in your .env file."
        )
    return client_id, client_secret


def search_rank(keyword: str, target_url: str, max_rank: int = DEFAULT_MAX_RANK):
    """Return (rank_or_None, status) for `target_url` under `keyword`.

    status is one of RANKED / NOT_FOUND / ERROR. rank is 1-based position in
    the Naver blog search results, or None if not RANKED.
    """
    target_blog_id, target_log_no = extract_blog_id_lognum(target_url)
    if not target_blog_id or not target_log_no:
        return None, "ERROR"

    try:
        client_id, client_secret = _get_credentials()
    except NaverAPIError:
        return None, "ERROR"

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }

    start = 1
    while start <= max_rank:
        display = min(PAGE_SIZE, max_rank - start + 1)
        params = {"query": keyword, "display": display, "start": start, "sort": "sim"}
        try:
            resp = requests.get(SEARCH_URL, headers=headers, params=params, timeout=10)
        except requests.RequestException:
            return None, "ERROR"

        if resp.status_code != 200:
            return None, "ERROR"

        items = resp.json().get("items", [])
        if not items:
            break

        for i, item in enumerate(items):
            blog_id, log_no = extract_blog_id_lognum(item.get("link", ""))
            if blog_id == target_blog_id and log_no == target_log_no:
                return start + i, "RANKED"

        start += display
        time.sleep(0.05)  # be gentle with the API

    return None, "NOT_FOUND"
