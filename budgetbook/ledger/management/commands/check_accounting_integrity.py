from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, ProgrammingError

from ledger.models import MonthlyClosing
from ledger.views import enrich_monthly_closings_with_drift


class Command(BaseCommand):
    help = 'Check accounting integrity for monthly closing snapshots.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--warn-only',
            action='store_true',
            help='Print drift warnings but exit successfully.',
        )

    def handle(self, *args, **options):
        closings = MonthlyClosing.objects.select_related('closed_by').order_by('month')
        try:
            checked = enrich_monthly_closings_with_drift(closings)
        except (OperationalError, ProgrammingError) as exc:
            raise CommandError('Accounting tables are not ready. Run migrations first.') from exc
        drifted = [closing for closing in checked if closing.has_drift]

        if not checked:
            self.stdout.write(self.style.SUCCESS('OK: no monthly closings to check.'))
            return

        if not drifted:
            self.stdout.write(self.style.SUCCESS(f'OK: {len(checked)} monthly closing(s) are consistent.'))
            return

        for closing in drifted:
            self.stdout.write(self.style.ERROR(f'DRIFT: {closing.month:%Y-%m} monthly closing differs from current ledger.'))
            for key, label in (
                ('opening_carry', 'opening_carry'),
                ('income', 'income'),
                ('expense', 'expense'),
                ('net', 'net'),
                ('closing_balance', 'closing_balance'),
            ):
                diff = closing.total_drift[key]
                if diff:
                    self.stdout.write(f'  {label}: {diff:+d}')
            for item in closing.account_drift:
                self.stdout.write(f"  account {item['name']}: {item['difference']:+d}")

        message = f'{len(drifted)} of {len(checked)} monthly closing(s) have drift.'
        if options['warn_only']:
            self.stdout.write(self.style.WARNING(f'WARNING: {message}'))
            return
        raise CommandError(message)
