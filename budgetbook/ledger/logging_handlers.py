"""Django logging に attach する 5xx エラーメール handler。

settings.LOGGING で 'ledger.logging_handlers.ErrorMailHandler' を指定する。
ERROR_NOTIFY_TO が空なら何もしない。
"""
from __future__ import annotations

import logging

from .services.error_mail import notify


class ErrorMailHandler(logging.Handler):
    """django.request の ERROR レベル以上を捕捉して 5xx をメール通知。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # django.request logger には request 属性が付く
            request = getattr(record, 'request', None)
            status = int(getattr(record, 'status_code', 500))
            if status < 500:
                return  # 4xx は対象外
            path = getattr(request, 'path', '-') if request else '-'
            method = getattr(request, 'method', '-') if request else '-'
            exc_info = record.exc_info or (None, None, None)
            notify(path=path, method=method, status=status, exc_info=exc_info)
        except Exception:  # pragma: no cover - handler が落ちて連鎖しないように
            self.handleError(record)