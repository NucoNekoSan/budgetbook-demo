"""PWA: manifest / service worker / offline fallback。

仕様: docs/specs/v1.9.0_pwa.md

- /manifest.webmanifest と /sw.js は **未ログインでもアクセス可能**にする。
  これは PWA インストール時にブラウザがログイン前に取得するため。
- いずれも機微データを含まない。
"""
from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

MANIFEST = {
    'name': 'BudgetBook',
    'short_name': 'BudgetBook',
    'description': '個人家計簿アプリ',
    'lang': 'ja',
    'start_url': '/',
    'scope': '/',
    'display': 'standalone',
    'orientation': 'any',
    'background_color': '#ffffff',
    'theme_color': '#2563eb',
    'icons': [
        {'src': '/static/icons/icon.svg',  'sizes': 'any', 'type': 'image/svg+xml', 'purpose': 'any'},
        {'src': '/static/icons/icon-192.png', 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
        {'src': '/static/icons/icon-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
        {'src': '/static/icons/icon-mask-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
    ],
}


@require_GET
@cache_control(max_age=3600, public=True)
def manifest(request: HttpRequest) -> HttpResponse:
    return HttpResponse(
        json.dumps(MANIFEST, ensure_ascii=False),
        content_type='application/manifest+json',
    )


def _sw_path() -> Path:
    # 開発時は static/js/sw.js を直接読む。
    # 本番では whitenoise の staticfiles/ にも置かれるが、配信は常に
    # この view 経由で root scope を取る。
    return Path(settings.BASE_DIR) / 'static' / 'js' / 'sw.js'


@require_GET
@cache_control(max_age=0, no_cache=True, no_store=True, must_revalidate=True)
def service_worker(request: HttpRequest) -> HttpResponse:
    try:
        body = _sw_path().read_text(encoding='utf-8')
    except FileNotFoundError:
        return HttpResponse('// sw.js not found', status=404, content_type='application/javascript')
    # Service-Worker は staticfiles 経由でも配信できるが、root scope を取るため view 経由で返す。
    resp = HttpResponse(body, content_type='application/javascript')
    resp['Service-Worker-Allowed'] = '/'
    return resp


@require_GET
def offline(request: HttpRequest) -> HttpResponse:
    return render(request, 'ledger/offline.html')