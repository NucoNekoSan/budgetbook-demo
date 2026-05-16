#!/usr/bin/env bash
# Container entrypoint:
# - Always run collectstatic so /app/staticfiles (bind-mounted host dir) reflects
#   the current static/ assets on every container start.
# - Optionally run migrate when DJANGO_AUTO_MIGRATE=1.
# Both are idempotent; failure aborts startup so we never serve stale assets.
set -euo pipefail

cd /app

echo "[entrypoint] collectstatic"
python manage.py collectstatic --noinput

if [ "${DJANGO_AUTO_MIGRATE:-0}" = "1" ]; then
  echo "[entrypoint] migrate"
  python manage.py migrate --noinput
fi

echo "[entrypoint] exec: $*"
exec "$@"
