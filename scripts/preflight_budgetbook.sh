#!/usr/bin/env bash
set -euo pipefail

# BudgetBook production preflight check.
# Run this on the Ubuntu host from the repository root after docker compose up -d.

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SERVICE_NAME="${SERVICE_NAME:-budgetbook}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8010}"

cd "${PROJECT_DIR}"

echo "[1/8] docker compose config"
docker compose config --quiet

echo "[2/8] docker compose ps"
docker compose ps

echo "[3/8] Django system checks"
docker compose exec -T "${SERVICE_NAME}" python manage.py check
docker compose exec -T "${SERVICE_NAME}" python manage.py makemigrations --check
docker compose exec -T "${SERVICE_NAME}" python manage.py migrate --check

echo "[4/8] SQLite integrity and runtime PRAGMAs"
docker compose exec -T "${SERVICE_NAME}" python manage.py shell -c '
from django.db import connection

cursor = connection.cursor()
values = {
    "integrity_check": cursor.execute("PRAGMA integrity_check").fetchone()[0],
    "journal_mode": cursor.execute("PRAGMA journal_mode").fetchone()[0],
    "foreign_keys": cursor.execute("PRAGMA foreign_keys").fetchone()[0],
    "busy_timeout": cursor.execute("PRAGMA busy_timeout").fetchone()[0],
}

for key, value in values.items():
    print(f"{key}={value}")

if values["integrity_check"] != "ok":
    raise SystemExit("SQLite integrity_check failed")
if str(values["journal_mode"]).lower() != "wal":
    raise SystemExit("SQLite journal_mode is not WAL")
if int(values["foreign_keys"]) != 1:
    raise SystemExit("SQLite foreign_keys is not enabled")
if int(values["busy_timeout"]) < 1000:
    raise SystemExit("SQLite busy_timeout is too low")
'

echo "[5/8] accounting integrity"
docker compose exec -T "${SERVICE_NAME}" python manage.py check_accounting_integrity

echo "[6/8] application data smoke"
docker compose exec -T "${SERVICE_NAME}" python manage.py shell -c "from django.contrib.auth import get_user_model; from ledger.models import Account, Category, Transaction, Transfer; print('users=', get_user_model().objects.count()); print('accounts=', Account.objects.count()); print('categories=', Category.objects.count()); print('transactions=', Transaction.objects.count()); print('transfers=', Transfer.objects.count())"

echo "[7/8] HTTP smoke and CSRF login POST"
BASE_URL="${BASE_URL}" python - <<'PY'
import http.cookiejar
import os
import re
import urllib.parse
import urllib.request

base_url = os.environ["BASE_URL"].rstrip("/")
cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))


def request(path, method="GET", data=None, headers=None):
    url = base_url + path
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    return opener.open(req, timeout=15)


login = request("/accounts/login/")
login_body = login.read().decode("utf-8", errors="replace")
print(f"/accounts/login/={login.status}")
if login.status != 200:
    raise SystemExit("login page did not return 200")

static = request("/static/css/style.css", method="HEAD")
print(f"/static/css/style.css={static.status}")
if static.status != 200:
    raise SystemExit("static css did not return 200")

match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', login_body)
if not match:
    raise SystemExit("csrf token not found in login page")

token = match.group(1)
headers = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": base_url,
    "Referer": base_url + "/accounts/login/",
}
post = request(
    "/accounts/login/",
    method="POST",
    data={
        "username": "__preflight_invalid_user__",
        "password": "__preflight_invalid_password__",
        "csrfmiddlewaretoken": token,
    },
    headers=headers,
)
post_body = post.read().decode("utf-8", errors="replace")
print(f"login_post_with_origin={post.status}")
if post.status == 403 or "CSRF" in post_body or "CSRF検証に失敗" in post_body:
    raise SystemExit("login POST failed CSRF validation")
PY

echo "[8/8] recent error log scan"
if docker compose logs --since=10m "${SERVICE_NAME}" | grep -E "ERROR|Traceback| 500 | 502 " ; then
  echo "recent application errors were found" >&2
  exit 1
fi

echo "preflight: ok"
