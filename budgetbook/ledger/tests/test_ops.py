"""運用補助機能のテスト: healthz / AuditLog 保管期間管理 / 構造化ログ / レート制限。"""
from __future__ import annotations

import gzip
import io
import json
import logging
from datetime import date, timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from config.logging_utils import JsonFormatter
from config.middleware import RateLimitMiddleware, _SlidingWindow
from ledger.models import Account, AuditLog, Category, MonthlyClosing


class HealthzTest(TestCase):
    def test_healthz_returns_ok_without_login(self):
        client = Client()
        resp = client.get(reverse('ledger:healthz'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')
        body = resp.json()
        self.assertEqual(body['status'], 'ok')
        # never_cache 指示: Cache-Control に no-store などが付くこと
        cache_control = resp.get('Cache-Control', '')
        self.assertTrue(
            any(token in cache_control for token in ('no-store', 'no-cache', 'max-age=0')),
            f'unexpected Cache-Control: {cache_control}',
        )

    def test_healthz_only_accepts_get(self):
        client = Client()
        resp = client.post(reverse('ledger:healthz'))
        self.assertEqual(resp.status_code, 405)


class PruneAuditLogsCommandTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='audit-keeper', password='pass')

    def _make_log(self, *, days_old: int):
        log = AuditLog.objects.create(
            user=self.user,
            action=AuditLog.Action.CREATE,
            target_model='Transaction',
            target_id='1',
            target_repr='dummy',
            summary='dummy',
            metadata={'days_old': days_old},
        )
        AuditLog.objects.filter(pk=log.pk).update(
            created_at=timezone.now() - timedelta(days=days_old),
        )
        return log

    def test_dry_run_reports_without_deleting(self):
        old = self._make_log(days_old=400)
        recent = self._make_log(days_old=10)
        out = StringIO()
        call_command('prune_audit_logs', '--keep-days=365', '--dry-run', stdout=out)
        self.assertIn('Found 1 AuditLog', out.getvalue())
        self.assertIn('--dry-run', out.getvalue())
        self.assertTrue(AuditLog.objects.filter(pk=old.pk).exists())
        self.assertTrue(AuditLog.objects.filter(pk=recent.pk).exists())

    def test_prune_deletes_old_rows(self):
        old = self._make_log(days_old=400)
        recent = self._make_log(days_old=10)
        out = StringIO()
        call_command('prune_audit_logs', '--keep-days=365', stdout=out)
        self.assertIn('Deleted 1', out.getvalue())
        self.assertFalse(AuditLog.objects.filter(pk=old.pk).exists())
        self.assertTrue(AuditLog.objects.filter(pk=recent.pk).exists())

    def test_prune_with_archive_writes_jsonl_gz(self):
        self._make_log(days_old=400)
        self._make_log(days_old=380)
        out = StringIO()
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            call_command(
                'prune_audit_logs',
                '--keep-days=365',
                f'--archive-dir={tmp}',
                stdout=out,
            )
            from pathlib import Path
            archives = list(Path(tmp).glob('audit_log_until_*.jsonl.gz'))
            self.assertEqual(len(archives), 1)
            with gzip.open(archives[0], 'rt', encoding='utf-8') as fh:
                rows = [json.loads(line) for line in fh]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['target_model'], 'Transaction')

    def test_keep_days_must_be_positive(self):
        with self.assertRaises(Exception):
            call_command('prune_audit_logs', '--keep-days=0')


class SelfCheckCommandTest(TestCase):
    def test_self_check_runs_clean(self):
        out = StringIO()
        # テスト DB は backup ディレクトリが存在しないので warnings 想定
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            from pathlib import Path
            (Path(tmp) / 'db-2026-05-04-120000.sqlite3').touch()
            try:
                call_command('self_check', f'--backup-dir={tmp}', stdout=out)
            except SystemExit as exc:
                self.fail(f'self_check failed unexpectedly: {exc} | output={out.getvalue()}')
        output = out.getvalue()
        self.assertIn('self_check', output)
        self.assertNotIn('ERROR:', output)

    def test_self_check_warns_when_backup_missing(self):
        out = StringIO()
        try:
            call_command('self_check', '--backup-dir=/nonexistent/path/xyz', stdout=out)
        except SystemExit:
            self.fail('warnings should not raise SystemExit')
        self.assertIn('backup directory not found', out.getvalue())


class HealthzVerboseTest(TestCase):
    def test_verbose_reports_db_write_ok(self):
        resp = self.client.get(reverse('ledger:healthz') + '?verbose=1')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['db_write'], 'ok')
        self.assertEqual(body['accounting'], 'no_closings')

    def test_verbose_with_clean_closing_reports_ok(self):
        Account.objects.create(name='ヘルス口座', opening_balance=0)
        Category.objects.create(name='ヘルス費', kind=Category.Kind.EXPENSE)
        MonthlyClosing.objects.create(
            month=date(2026, 4, 1),
            opening_carry=0, income=0, expense=0, net=0,
            closing_balance=0, account_balances=[],
        )
        resp = self.client.get(reverse('ledger:healthz') + '?verbose=1')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['accounting'], 'ok')


class JsonFormatterTest(TestCase):
    def test_json_formatter_emits_extra_fields(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name='budgetbook.audit', level=logging.INFO, pathname='', lineno=1,
            msg='audit', args=None, exc_info=None,
        )
        record.event = 'audit'
        record.action = 'create'
        record.user_id = 42
        emitted = formatter.format(record)
        payload = json.loads(emitted)
        self.assertEqual(payload['level'], 'INFO')
        self.assertEqual(payload['logger'], 'budgetbook.audit')
        self.assertEqual(payload['event'], 'audit')
        self.assertEqual(payload['action'], 'create')
        self.assertEqual(payload['user_id'], 42)
        self.assertIn('ts', payload)

    def test_audit_emits_structured_log(self):
        user = User.objects.create_user(username='log', password='pass')
        client = Client()
        client.login(username='log', password='pass')
        account = Account.objects.create(name='ログ口座', opening_balance=0)
        category = Category.objects.create(name='ログ費', kind=Category.Kind.EXPENSE)

        with self.assertLogs('budgetbook.audit', level='INFO') as cm:
            resp = client.post(reverse('ledger:transaction_create'), {
                'date': '2026-04-01',
                'account': account.pk,
                'kind': Category.Kind.EXPENSE,
                'category': category.pk,
                'amount': 100,
                'description': '構造化ログ',
                'memo': '',
                'month': '2026-04',
            })
        self.assertEqual(resp.status_code, 302)
        # extra フィールドが record に乗っていること
        records_with_event = [r for r in cm.records if getattr(r, 'event', None) == 'audit']
        self.assertTrue(records_with_event, f'no audit record: {cm.output}')
        rec = records_with_event[0]
        self.assertEqual(rec.action, 'create')
        self.assertEqual(rec.target_model, 'Transaction')
        self.assertEqual(rec.username, 'log')


class RateLimitTest(TestCase):
    def test_sliding_window_blocks_after_max_events(self):
        win = _SlidingWindow(max_events=3, window_seconds=60)
        self.assertTrue(win.hit('1.2.3.4'))
        self.assertTrue(win.hit('1.2.3.4'))
        self.assertTrue(win.hit('1.2.3.4'))
        self.assertFalse(win.hit('1.2.3.4'))
        # 別 IP は影響を受けない
        self.assertTrue(win.hit('5.6.7.8'))

    def test_middleware_returns_429_when_exceeded(self):
        calls = {'n': 0}

        def fake_get_response(req):
            calls['n'] += 1
            from django.http import HttpResponse
            return HttpResponse('ok')

        with override_settings(
            RATE_LIMIT_ENABLED=True,
            RATE_LIMIT_MAX_EVENTS=2,
            RATE_LIMIT_WINDOW_SECONDS=60,
            SECURE_PROXY_SSL_HEADER=None,
        ):
            mw = RateLimitMiddleware(fake_get_response)
            from django.test import RequestFactory
            rf = RequestFactory()
            r1 = mw(rf.get('/some/'))
            r2 = mw(rf.get('/some/'))
            r3 = mw(rf.get('/some/'))
            self.assertEqual(r1.status_code, 200)
            self.assertEqual(r2.status_code, 200)
            self.assertEqual(r3.status_code, 429)

    def test_middleware_exempts_healthz_and_static(self):
        from django.test import RequestFactory
        from django.http import HttpResponse

        def fake_get_response(req):
            return HttpResponse('ok')

        with override_settings(
            RATE_LIMIT_ENABLED=True,
            RATE_LIMIT_MAX_EVENTS=1,
            RATE_LIMIT_WINDOW_SECONDS=60,
            SECURE_PROXY_SSL_HEADER=None,
        ):
            mw = RateLimitMiddleware(fake_get_response)
            rf = RequestFactory()
            for path in ['/healthz', '/static/css/style.css']:
                r1 = mw(rf.get(path))
                r2 = mw(rf.get(path))
                self.assertEqual(r1.status_code, 200, path)
                self.assertEqual(r2.status_code, 200, path)