from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase, TestCase

import config.settings as project_settings
from ledger.db import validate_sqlite_pragma_value


class RuntimeSecuritySettingsTest(SimpleTestCase):
    def test_secure_cookie_setting_is_independent_from_https_redirect(self):
        self.assertTrue(hasattr(settings, 'SESSION_COOKIE_SECURE'))
        self.assertTrue(hasattr(settings, 'CSRF_COOKIE_SECURE'))
        env_example = Path(settings.BASE_DIR / '.env.example').read_text(encoding='utf-8')
        self.assertIn('SECURE_COOKIES=1', env_example)
        self.assertIn('TRUST_PROXY_SSL=1', env_example)

    def test_sqlite_runtime_settings_exist(self):
        self.assertGreaterEqual(settings.SQLITE_BUSY_TIMEOUT_MS, 1000)
        self.assertIn(settings.SQLITE_JOURNAL_MODE, {'WAL', 'DELETE', 'TRUNCATE', 'PERSIST', 'MEMORY', 'OFF'})
        self.assertIn(settings.SQLITE_SYNCHRONOUS, {'OFF', 'NORMAL', 'FULL', 'EXTRA'})

    def test_sqlite_pragma_values_are_whitelisted(self):
        self.assertEqual(
            validate_sqlite_pragma_value('wal', {'WAL', 'DELETE'}, 'SQLITE_JOURNAL_MODE'),
            'WAL',
        )
        with self.assertRaises(ValueError):
            validate_sqlite_pragma_value('WAL; DROP TABLE ledger_transaction', {'WAL'}, 'SQLITE_JOURNAL_MODE')

    def test_static_version_reads_git_head_ref(self):
        sha = '1234567890abcdef1234567890abcdef12345678'
        with TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            ref_dir = repo_root / '.git' / 'refs' / 'heads'
            ref_dir.mkdir(parents=True)
            (repo_root / '.git' / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
            (ref_dir / 'main').write_text(f'{sha}\n', encoding='utf-8')

            self.assertEqual(project_settings._git_short_sha(repo_root), sha[:7])

    def test_static_version_reads_detached_git_head(self):
        sha = 'abcdef1234567890abcdef1234567890abcdef12'
        with TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            git_dir = repo_root / '.git'
            git_dir.mkdir()
            (git_dir / 'HEAD').write_text(f'{sha}\n', encoding='utf-8')

            self.assertEqual(project_settings._git_short_sha(repo_root), sha[:7])


class SQLitePragmaTest(TestCase):
    def test_busy_timeout_is_applied_to_sqlite_connection(self):
        if connection.vendor != 'sqlite':
            self.skipTest('sqlite only')
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA busy_timeout')
            self.assertEqual(cursor.fetchone()[0], settings.SQLITE_BUSY_TIMEOUT_MS)

    def test_foreign_keys_are_enabled(self):
        if connection.vendor != 'sqlite':
            self.skipTest('sqlite only')
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA foreign_keys')
            self.assertEqual(cursor.fetchone()[0], 1)
