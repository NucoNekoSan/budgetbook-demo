
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# .env のロード順序 (v1.14.1):
# 1. BUDGETBOOK_ENV_FILE 環境変数で明示指定（最優先、Docker 等で使用）
# 2. ~/.budgetbook-secrets/.env （ユーザホーム、OneDrive 同期外）
# 3. BASE_DIR/.env （プロジェクト同梱、移行用フォールバック）
#
# SECRET_KEY 等の機微情報を OneDrive / Git / クラウドストレージ上に
# 置かないため、新規環境では (1) または (2) を推奨。(3) は既存運用との
# 互換性のために残しているが、いずれ廃止する。
_explicit_env = os.environ.get('BUDGETBOOK_ENV_FILE')
_home_env = Path.home() / '.budgetbook-secrets' / '.env'
_base_env = BASE_DIR / '.env'
for _candidate in (_explicit_env, _home_env, _base_env):
    if _candidate and Path(_candidate).is_file():
        load_dotenv(_candidate, override=True)
        break

_MISSING = object()


def _require_env(key: str) -> str:
    value = os.environ.get(key, _MISSING)
    if value is _MISSING:
        raise RuntimeError(
            f'環境変数 {key} が設定されていません。'
            f' プロジェクトルートの .env.example を .env にコピーして値を設定してください。'
        )
    return value


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None or raw == '':
        return default
    return raw.strip().lower() in ('true', '1', 'yes', 'on')


SECRET_KEY = _require_env('SECRET_KEY')
DEBUG = _env_bool('DEBUG')
ALLOWED_HOSTS: list[str] = [
    h.strip() for h in os.environ.get('ALLOWED_HOSTS', '').split(',') if h.strip()
]

# ---------------------------------------------------------------------------
# HTTPS / 公開モード
# ENABLE_HTTPS は Django 側 SSL redirect / HSTS 用。
# SECURE_COOKIES は Cloudflare Tunnel 配下でも cookie Secure を有効化するため独立させる。
# ---------------------------------------------------------------------------
_HTTPS = _env_bool('ENABLE_HTTPS')
_SECURE_COOKIES = _env_bool('SECURE_COOKIES', _HTTPS)

# ---------------------------------------------------------------------------
# Demo mode (public ポートフォリオ / self-host distribution 用)
# DEMO_MODE=1 で「デモデータです」バナー表示 + mutation ブロック (read-only)
# DEMO_ALLOW_WRITES=1 で DEMO_MODE 中でも書き込み許可（preview / sandbox 用）
# DEMO_AUTO_LOGIN=1 で demo ユーザーで自動ログイン（demo サイト用）
# 全てデフォルト OFF — 通常のセルフホスト時は非 demo として動作
# ---------------------------------------------------------------------------
DEMO_MODE = _env_bool('DEMO_MODE')
DEMO_ALLOW_WRITES = _env_bool('DEMO_ALLOW_WRITES')
DEMO_AUTO_LOGIN = _env_bool('DEMO_AUTO_LOGIN')

# ---------------------------------------------------------------------------
# Demo mode (public ポートフォリオ / self-host distribution 用)
# DEMO_MODE=1 で「デモデータです」バナー表示 + mutation ブロック (read-only)
# DEMO_ALLOW_WRITES=1 で DEMO_MODE 中でも書き込み許可（preview / sandbox 用）
# DEMO_AUTO_LOGIN=1 で demo ユーザーで自動ログイン（demo サイト用）
# 全てデフォルト OFF — 通常のセルフホスト時は非 demo として動作
# ---------------------------------------------------------------------------
DEMO_MODE = _env_bool('DEMO_MODE')
DEMO_ALLOW_WRITES = _env_bool('DEMO_ALLOW_WRITES')
DEMO_AUTO_LOGIN = _env_bool('DEMO_AUTO_LOGIN')

INSTALLED_APPS = [
    'axes',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_htmx',
    'ledger',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'config.middleware.RateLimitMiddleware',
    'config.middleware.CSPNonceMiddleware',
    'config.middleware.ContentSecurityPolicyMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'config.middleware.DemoAutoLoginMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'axes.middleware.AxesMiddleware',
    'config.middleware.DemoModeWriteBlockMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'config.middleware.csp_nonce',
                'config.middleware.static_version',
                'config.middleware.demo_mode',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('DJANGO_DB_PATH') or (BASE_DIR / 'db.sqlite3'),
    }
}

SQLITE_BUSY_TIMEOUT_MS = int(os.environ.get('SQLITE_BUSY_TIMEOUT_MS', 5000))
SQLITE_JOURNAL_MODE = os.environ.get('SQLITE_JOURNAL_MODE', 'WAL')
SQLITE_SYNCHRONOUS = os.environ.get('SQLITE_SYNCHRONOUS', 'NORMAL')

# ---------------------------------------------------------------------------
# Logging（JSON 構造化ログ）
# DJANGO_LOG_FORMAT=json で本番、それ以外は人読み形式
# ---------------------------------------------------------------------------
_LOG_FORMAT = os.environ.get('DJANGO_LOG_FORMAT', 'json' if not DEBUG else 'plain').lower()
# テスト中はノイズを抑える（明示的に DJANGO_LOG_LEVEL を渡せば従う）
_LOG_LEVEL_DEFAULT = 'CRITICAL' if 'test' in sys.argv else 'INFO'
_LOG_LEVEL = os.environ.get('DJANGO_LOG_LEVEL', _LOG_LEVEL_DEFAULT).upper()
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'config.logging_utils.JsonFormatter',
        },
        'plain': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'stdout': {
            'class': 'logging.StreamHandler',
            'formatter': 'json' if _LOG_FORMAT == 'json' else 'plain',
        },
    },
    'root': {
        'handlers': ['stdout'],
        'level': _LOG_LEVEL,
    },
    'loggers': {
        'django.security': {'handlers': ['stdout'], 'level': _LOG_LEVEL, 'propagate': False},
        'django.request': {'handlers': ['stdout'], 'level': _LOG_LEVEL, 'propagate': False},
        'axes': {'handlers': ['stdout'], 'level': _LOG_LEVEL, 'propagate': False},
        'budgetbook': {'handlers': ['stdout'], 'level': _LOG_LEVEL, 'propagate': False},
    },
}


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'ja'
TIME_ZONE = 'Asia/Tokyo'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
# キャッシュバスター: 環境変数で渡せばデプロイのたびに変わる。
# 未指定なら BASE_DIR の mtime を使い、ファイル変更時に自動的に更新される。
STATIC_VERSION = os.environ.get('STATIC_VERSION') or str(int(BASE_DIR.stat().st_mtime))
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# Security headers（常時有効）
# ---------------------------------------------------------------------------
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
CSP_ENABLED = _env_bool('ENABLE_CSP', True)
CONTENT_SECURITY_POLICY = os.environ.get(
    'CONTENT_SECURITY_POLICY',
    "default-src 'self'; "
    "script-src 'self' 'nonce-__CSP_NONCE__'; "
    "style-src 'self' 'nonce-__CSP_NONCE__'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'",
)

# ---------------------------------------------------------------------------
# Cookie / セッション
# ---------------------------------------------------------------------------
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

SESSION_COOKIE_SECURE = _SECURE_COOKIES
CSRF_COOKIE_SECURE = _SECURE_COOKIES

SESSION_COOKIE_AGE = int(os.environ.get('SESSION_COOKIE_AGE', 86400))

# ---------------------------------------------------------------------------
# HTTPS 専用設定（ENABLE_HTTPS=1 のときだけ有効）
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT = _HTTPS
if _HTTPS:
    # デフォルトは段階的ロールアウト用に短期 (60 秒)。
    # 本番では .env で SECURE_HSTS_SECONDS を 604800 → 31536000 と段階的に伸ばすこと。
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', 60))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = _env_bool('ENABLE_HSTS_PRELOAD')
    # preload を有効にする場合は SECONDS が 31536000 以上であることを保証する。
    if SECURE_HSTS_PRELOAD and SECURE_HSTS_SECONDS < 31536000:
        raise RuntimeError(
            'ENABLE_HSTS_PRELOAD=1 を有効にする場合、SECURE_HSTS_SECONDS は 31536000 以上に設定してください。'
        )

_trusted = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _trusted.split(',') if o.strip()] if _trusted else []

# ---------------------------------------------------------------------------
# Reverse proxy (Cloudflare Tunnel など)
# TRUST_PROXY_SSL=1 のときだけ X-Forwarded-Proto を信頼して HTTPS と認識する。
# Django 側で SSL リダイレクトはせず、HTTPS 化は Cloudflare 側に委ねる方針。
# ---------------------------------------------------------------------------
if _env_bool('TRUST_PROXY_SSL'):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# ---------------------------------------------------------------------------
# Admin URL（env で変更可能）
# ---------------------------------------------------------------------------
ADMIN_URL_PATH = os.environ.get('ADMIN_URL_PATH', 'admin/')

# ---------------------------------------------------------------------------
# django-axes（ログイン試行回数制限）
# ---------------------------------------------------------------------------
AXES_FAILURE_LIMIT = int(os.environ.get('AXES_FAILURE_LIMIT', 5))
AXES_COOLOFF_TIME = float(os.environ.get('AXES_COOLOFF_TIME', 0.5))  # hours
AXES_LOCKOUT_PARAMETERS = ['username']
AXES_RESET_ON_SUCCESS = True
AXES_ENABLED = 'test' not in sys.argv

# ---------------------------------------------------------------------------
# 二次レート制限（全ビュー、IP 単位）
# axes はログイン専用なので、そこに到達する手前でも閾値を設ける。
# 通常運用では引っかからない値（10 req/s 平均、瞬間 600）。
# テスト時は無効化して 429 が出ないようにする。
# ---------------------------------------------------------------------------
RATE_LIMIT_ENABLED = ('test' not in sys.argv) and _env_bool('RATE_LIMIT_ENABLED', True)
RATE_LIMIT_MAX_EVENTS = int(os.environ.get('RATE_LIMIT_MAX_EVENTS', 600))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get('RATE_LIMIT_WINDOW_SECONDS', 60))

# ---------------------------------------------------------------------------
# 5xx エラーメール通知 (v1.10.0)
# ---------------------------------------------------------------------------
# ERROR_NOTIFY_TO: カンマ区切りで受信者を指定。未設定 / 空なら無効。
# EMAIL_BACKEND / EMAIL_HOST 等は Django 標準の環境変数を尊重する。
# 未設定時は console backend にフォールバック（ローカル開発でログに出るだけ）。
_error_notify_raw = os.environ.get('ERROR_NOTIFY_TO', '').strip()
ERROR_NOTIFY_TO = [a.strip() for a in _error_notify_raw.split(',') if a.strip()]

EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587') or 587)
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = _env_bool('EMAIL_USE_TLS', True)
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'budgetbook@localhost')

if ERROR_NOTIFY_TO:
    LOGGING['handlers']['error_mail'] = {
        'level': 'ERROR',
        'class': 'ledger.logging_handlers.ErrorMailHandler',
    }
    LOGGING['loggers']['django.request']['handlers'] = ['stdout', 'error_mail']

# ---------------------------------------------------------------------------
# v1.11.0: LoanProfile 利息自動計上 (accrue_loan_interest command)
# ---------------------------------------------------------------------------
# このカテゴリ名で完全一致検索する。kind=expense でなければエラー終了。
LOAN_INTEREST_CATEGORY_NAME = os.environ.get(
    'LOAN_INTEREST_CATEGORY_NAME', '金利・手数料',
)
