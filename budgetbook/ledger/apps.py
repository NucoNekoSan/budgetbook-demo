from django.apps import AppConfig


class LedgerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ledger'
    verbose_name = '家計簿'

    def ready(self) -> None:
        from .db import install_sqlite_pragmas

        install_sqlite_pragmas()
