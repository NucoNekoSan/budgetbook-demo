# BudgetBook 本番用イメージ
# - 非 root ユーザで gunicorn 実行
# - 起動時 entrypoint で collectstatic を必ず実行（静的アセットの取り込み漏れ防止）
# - migrate は DJANGO_AUTO_MIGRATE=1 のときだけ自動。本番では手動実行推奨
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 非 root ユーザを作成（uid/gid 1000 想定。必要なら build-arg で上書き可）
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd --gid ${APP_GID} appuser \
 && useradd --uid ${APP_UID} --gid ${APP_GID} --create-home --shell /bin/bash appuser

WORKDIR /app

# 依存だけ先にインストール（キャッシュ効率化）
COPY budgetbook/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# アプリ本体（.dockerignore で .env / db.sqlite3 / backup / staticfiles / .git / .claude を除外）
COPY budgetbook/ /app/
# entrypoint script
COPY scripts/entrypoint.sh /usr/local/bin/budgetbook-entrypoint
RUN chmod +x /usr/local/bin/budgetbook-entrypoint

# 永続化ディレクトリを用意し、非 root から書き込めるよう所有権を付与
RUN mkdir -p /app/data /app/backup /app/staticfiles \
 && chown -R appuser:appuser /app

USER appuser

EXPOSE 8010

# Python 標準ライブラリだけで healthcheck（curl を入れない）
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys;\
r=urllib.request.urlopen('http://127.0.0.1:8010/accounts/login/',timeout=3);\
sys.exit(0 if r.status<500 else 1)" || exit 1

ENTRYPOINT ["budgetbook-entrypoint"]
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8010", \
     "--workers", "3", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
