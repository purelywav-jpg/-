#!/usr/bin/env bash
# Runs the daily rank check once. Wire this into cron for automatic daily
# execution, e.g. (crontab -e):
#   0 9 * * * /path/to/naver-blog-rank-tracker/scripts/run_daily_check.sh >> /path/to/naver-blog-rank-tracker/data/cron.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
python3 rank_checker.py
