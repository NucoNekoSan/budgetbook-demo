from __future__ import annotations

import gzip
import json
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ledger.models import AuditLog


class Command(BaseCommand):
    help = (
        'Archive AuditLog rows older than --keep-days into a gzipped JSONL file '
        '(if --archive-dir is given) and then delete them. '
        'Designed for routine retention without losing forensic visibility.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--keep-days', type=int, default=365,
                            help='Rows older than this many days are eligible for pruning. Default: 365.')
        parser.add_argument('--archive-dir', type=str, default='',
                            help='If set, archive eligible rows to <dir>/audit_log_<cutoff>.jsonl.gz before deleting.')
        parser.add_argument('--batch-size', type=int, default=1000,
                            help='Delete batch size to avoid long locks. Default: 1000.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report counts without writing or deleting anything.')

    def handle(self, *args, **options):
        keep_days = options['keep_days']
        if keep_days < 1:
            raise CommandError('--keep-days must be >= 1')

        cutoff = timezone.now() - timedelta(days=keep_days)
        eligible = AuditLog.objects.filter(created_at__lt=cutoff)
        total = eligible.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS(
                f'No AuditLog rows older than {cutoff.isoformat()}.'
            ))
            return

        self.stdout.write(
            f'Found {total} AuditLog row(s) older than {cutoff.isoformat()}.'
        )

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('--dry-run: nothing was archived or deleted.'))
            return

        archive_dir = options['archive_dir']
        if archive_dir:
            target_dir = Path(archive_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            archive_path = target_dir / f'audit_log_until_{cutoff.date().isoformat()}.jsonl.gz'
            self.stdout.write(f'Archiving to {archive_path} ...')
            with gzip.open(archive_path, 'wt', encoding='utf-8') as fh:
                for row in eligible.iterator(chunk_size=500):
                    fh.write(json.dumps({
                        'id': row.pk,
                        'created_at': row.created_at.isoformat(),
                        'user_id': row.user_id,
                        'action': row.action,
                        'target_model': row.target_model,
                        'target_id': row.target_id,
                        'target_repr': row.target_repr,
                        'summary': row.summary,
                        'metadata': row.metadata,
                    }, ensure_ascii=False))
                    fh.write('\n')
            self.stdout.write(self.style.SUCCESS(f'Archive written: {archive_path}'))

        deleted_total = 0
        batch_size = options['batch_size']
        while True:
            ids = list(
                AuditLog.objects.filter(created_at__lt=cutoff)
                .order_by('id').values_list('id', flat=True)[:batch_size]
            )
            if not ids:
                break
            count, _ = AuditLog.objects.filter(id__in=ids).delete()
            deleted_total += count

        self.stdout.write(self.style.SUCCESS(f'Deleted {deleted_total} AuditLog row(s).'))