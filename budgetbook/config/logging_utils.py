"""JSON formatter for Django logging.

依存追加なし。stdout に 1 行 1 JSON で書き出すため Cloudflare Logs /
Loki / journalctl などのログ集約と相性が良い。
"""
from __future__ import annotations

import json
import logging
import time


_RESERVED_LOG_RECORD_FIELDS = {
    'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
    'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
    'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
    'processName', 'process', 'message', 'asctime', 'taskName',
}


class JsonFormatter(logging.Formatter):
    """logging.LogRecord を JSON 1 行に整形する。

    `extra={...}` で渡された任意フィールドは追加情報として保持する。
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'ts': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(record.created))
                  + f'.{int(record.msecs):03d}Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        if record.exc_info:
            payload['exc'] = self.formatException(record.exc_info)
        if record.stack_info:
            payload['stack'] = self.formatStack(record.stack_info)
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_RECORD_FIELDS or key.startswith('_'):
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except TypeError:
                payload[key] = repr(value)
        return json.dumps(payload, ensure_ascii=False)