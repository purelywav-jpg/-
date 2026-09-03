"""Web dashboard for the Naver blog rank tracker (spec STEP 9 / sections 7,
9, 11, 12, 13). Run with: python app.py  (http://localhost:5000)
"""
from datetime import date

from flask import Flask, jsonify, redirect, render_template, request, url_for

import db
import models
from rank_checker import run_daily_check

app = Flask(__name__)


@app.before_request
def _ensure_db():
    db.init_db()
    db.seed_if_empty()


@app.route("/")
def dashboard():
    today = request.args.get("date") or date.today().isoformat()
    mode = request.args.get("filter", "all")
    summary = models.dashboard_summary(today)
    rows = models.filter_rows(summary["rows"], mode)
    return render_template(
        "dashboard.html", summary=summary, rows=rows, mode=mode, today=today
    )


@app.route("/check", methods=["POST"])
def check_now():
    run_daily_check(check_date=date.today().isoformat())
    return redirect(url_for("dashboard"))


# ------------------------------------------------------------------ posts --
@app.route("/posts")
def posts_list():
    posts = models.list_posts(active_only=True)
    for p in posts:
        p["keywords"] = models.list_keywords_for_post(p["id"])
    return render_template("posts.html", posts=posts)


@app.route("/posts/new", methods=["GET", "POST"])
def post_new():
    if request.method == "POST":
        title = request.form["title"].strip()
        url = request.form["url"].strip()
        keywords = [k.strip() for k in request.form.get("keywords", "").splitlines() if k.strip()]
        if title and url and keywords:
            post_id = models.add_post(title, url, keywords)
            return redirect(url_for("post_detail", post_id=post_id))
    return render_template("post_form.html", post=None)


@app.route("/posts/<int:post_id>/edit", methods=["GET", "POST"])
def post_edit(post_id):
    post = models.get_post(post_id)
    if not post:
        return redirect(url_for("posts_list"))
    if request.method == "POST":
        title = request.form["title"].strip()
        url = request.form["url"].strip()
        models.update_post(post_id, title=title or None, url=url or None)
        return redirect(url_for("post_detail", post_id=post_id))
    return render_template("post_form.html", post=post)


@app.route("/posts/<int:post_id>/delete", methods=["POST"])
def post_delete(post_id):
    models.delete_post(post_id)
    return redirect(url_for("posts_list"))


@app.route("/posts/<int:post_id>")
def post_detail(post_id):
    post = models.get_post(post_id)
    if not post:
        return redirect(url_for("posts_list"))
    months = models.available_months()
    ym = request.args.get("month", months[0])
    year, month = (int(x) for x in ym.split("-"))
    keywords = models.list_keywords_for_post(post_id)
    for k in keywords:
        k["summary"] = models.monthly_summary(post_id, k["id"], year, month)
    return render_template(
        "post_detail.html",
        post=post,
        keywords=keywords,
        months=months,
        ym=ym,
        year=year,
        month=month,
    )


@app.route("/posts/<int:post_id>/keywords/add", methods=["POST"])
def keyword_add(post_id):
    kw = request.form.get("keyword", "").strip()
    if kw:
        models.add_keyword_to_post(post_id, kw)
    return redirect(url_for("post_detail", post_id=post_id))


@app.route("/posts/<int:post_id>/keywords/<int:keyword_id>/delete", methods=["POST"])
def keyword_delete(post_id, keyword_id):
    models.remove_keyword_from_post(post_id, keyword_id)
    return redirect(url_for("post_detail", post_id=post_id))


# ---------------------------------------------------------------- monthly --
@app.route("/monthly")
def monthly():
    months = models.available_months()
    ym = request.args.get("month", months[0])
    year, month = (int(x) for x in ym.split("-"))
    posts = models.list_posts(active_only=True)
    for p in posts:
        kws = models.list_keywords_for_post(p["id"])
        for k in kws:
            k["summary"] = models.monthly_summary(p["id"], k["id"], year, month)
        p["keywords"] = kws
    return render_template(
        "monthly.html", posts=posts, months=months, ym=ym, year=year, month=month
    )


# ------------------------------------------------------------------- api --
@app.route("/api/graph")
def api_graph():
    post_id = request.args.get("post_id", type=int)
    keyword_id = request.args.get("keyword_id", type=int)
    ym = request.args.get("month", date.today().strftime("%Y-%m"))
    year, month = (int(x) for x in ym.split("-"))
    return jsonify(models.graph_series(post_id, keyword_id, year, month))


if __name__ == "__main__":
    db.init_db()
    db.seed_if_empty()
    app.run(host="0.0.0.0", port=5000, debug=True)
