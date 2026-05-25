from django.core.management.base import BaseCommand, CommandError

from ledger.services.audit_integrity import AuditLogChainError, verify_audit_log_chain


class Command(BaseCommand):
    help = 'Verify AuditLog tamper-evident hash chain.'

    def handle(self, *args, **options):
        try:
            checked = verify_audit_log_chain()
        except AuditLogChainError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f'AuditLog hash chain ok ({checked} row(s)).'))
