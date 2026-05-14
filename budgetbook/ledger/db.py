from __future__ import annotations

from django.conf import settings
from django.db.backends.signals import connection_created

ALLOWED_SQLITE_JOURNAL_MODES = {'WAL', 'DELETE', 'TRUNCATE', 'PERSIST', 'MEMORY', 'OFF'}
ALLOWED_SQLITE_SYNCHRONOUS = {'OFF', 'NORMAL', 'FULL', 'EXTRA'}


def validate_sqlite_pragma_value(value: str, allowed_values: set[str], setting_name: str) -> str:
    normalized = str(value).upper()
    if normalized not in allowed_values:
        raise ValueError(f'{setting_name} must be one of: {", ".join(sorted(allowed_values))}')
    return normalized


def configure_sqlite_connection(sender, connection, **kwargs) -> None:
    if connection.vendor != 'sqlite':
        return

    busy_timeout = int(getattr(settings, 'SQLITE_BUSY_TIMEOUT_MS', 5000))
    journal_mode = validate_sqlite_pragma_value(
        getattr(settings, 'SQLITE_JOURNAL_MODE', 'WAL'),
        ALLOWED_SQLITE_JOURNAL_MODES,
        'SQLITE_JOURNAL_MODE',
    )
    synchronous = validate_sqlite_pragma_value(
        getattr(settings, 'SQLITE_SYNCHRONOUS', 'NORMAL'),
        ALLOWED_SQLITE_SYNCHRONOUS,
        'SQLITE_SYNCHRONOUS',
    )

    with connection.cursor() as cursor:
        cursor.execute(f'PRAGMA busy_timeout = {busy_timeout}')
        cursor.execute('PRAGMA foreign_keys = ON')

        db_name = str(connection.settings_dict.get('NAME') or '')
        if db_name and db_name != ':memory:':
            cursor.execute(f'PRAGMA journal_mode = {journal_mode}')
            cursor.execute(f'PRAGMA synchronous = {synchronous}')


def install_sqlite_pragmas() -> None:
    connection_created.connect(
        configure_sqlite_connection,
        dispatch_uid='ledger.configure_sqlite_connection',
    )
