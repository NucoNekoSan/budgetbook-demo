"""5xx エラー時のメール通知（レート制限付き）。

仕様: docs/specs/v1.10.0_observability.md

設計判断:
- メール本文に取引データ・cookie・session・リクエストボディは含めない。
- トレースバックは先頭 5 行のみ。
- 同じ (path, exception_class) の組は 5 分に 1 回まで。プロセス内メモリで保持。
- 送信は別スレッドで fire-and-forget。失敗してもアプリは止まらない。
"""
from __future__ import annotations

import logging
import socket
import threading
import traceback
from datetime import datetime, timedelta, timezone
from typing import Iterable

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

_RATE_WINDOW = timedelta(minutes=5)
_TRACEBACK_HEAD_LINES = 5
_recent_send_lock = threading.Lock()
_recent_send: dict[tuple[str, str], datetime] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _should_send(path: str, exc_class: str) -> bool:
    key = (path, exc_class)
    now = _now()
    with _recent_send_lock:
        prev = _recent_send.get(key)
        if prev and now - prev < _RATE_WINDOW:
            return False
        _recent_send[key] = now
        # 古いエントリのクリーンアップ（メモリ肥大化防止）
        cutoff = now - _RATE_WINDOW * 4
        stale = [k for k, t in _recent_send.items() if t < cutoff]
        for k in stale:
            _recent_send.pop(k, None)
    return True


def _safe_traceback_head(exc_info) -> str:
    if not exc_info:
        return '(no traceback)'
    try:
        lines = traceback.format_exception(*exc_info)
        # format_exception の各要素は複数行を含むので結合してから先頭 N 行
        joined = ''.join(lines).splitlines()
        return '\n'.join(joined[:_TRACEBACK_HEAD_LINES])
    except Exception:
        return '(traceback unavailable)'


def build_error_payload(*, path: str, method: str, status: int, exc_info, when: datetime | None = None) -> tuple[str, str]:
    """件名と本文を組み立てる。リクエストボディや個人情報は含めない。"""
    when = when or _now()
    exc_class = 'UnknownError'
    exc_msg = ''
    if exc_info and exc_info[0]:
        exc_class = exc_info[0].__name__
        try:
            exc_msg = str(exc_info[1])[:200] if exc_info[1] else ''
        except Exception:
            exc_msg = '(unprintable)'

    subject = f'[BudgetBook] {status} {exc_class} at {path}'
    body = (
        f'時刻: {when.isoformat()}\n'
        f'ホスト: {socket.gethostname()}\n'
        f'メソッド: {method}\n'
        f'パス: {path}\n'
        f'ステータス: {status}\n'
        f'例外: {exc_class}: {exc_msg}\n'
        f'\n'
        f'トレースバック（先頭 {_TRACEBACK_HEAD_LINES} 行）:\n'
        f'{_safe_traceback_head(exc_info)}\n'
    )
    return subject, body


def _send_async(subject: str, body: str, recipients: Iterable[str]) -> None:
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'budgetbook@localhost'),
            recipient_list=list(recipients),
            fail_silently=True,
        )
    except Exception as e:  # pragma: no cover - 通知失敗で本体を壊さない
        logger.warning('Error mail send failed: %s', e)


def notify(*, path: str, method: str, status: int, exc_info) -> bool:
    """5xx 通知を試みる。レート制限で抑止された場合は False。"""
    recipients = list(getattr(settings, 'ERROR_NOTIFY_TO', []) or [])
    if not recipients:
        return False
    exc_class = exc_info[0].__name__ if exc_info and exc_info[0] else 'UnknownError'
    if not _should_send(path, exc_class):
        return False
    subject, body = build_error_payload(
        path=path, method=method, status=status, exc_info=exc_info,
    )
    threading.Thread(
        target=_send_async,
        args=(subject, body, recipients),
        daemon=True,
    ).start()
    return True


def _reset_rate_limit_for_tests() -> None:
    """テスト用: プロセス内のレート制限をクリア。"""
    with _recent_send_lock:
        _recent_send.clear()