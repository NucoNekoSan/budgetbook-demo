from __future__ import annotations

from ledger.models import AuditLog


class AuditLogChainError(ValueError):
    pass


def verify_audit_log_chain() -> int:
    expected_prev_hash = ''
    checked = 0
    for row in AuditLog.objects.order_by('id').iterator(chunk_size=500):
        checked += 1
        if not row.row_hash:
            raise AuditLogChainError(f'AuditLog #{row.pk} has no row_hash.')
        if row.prev_hash != expected_prev_hash:
            raise AuditLogChainError(
                f'AuditLog #{row.pk} prev_hash mismatch: '
                f'expected {expected_prev_hash or "<genesis>"}, got {row.prev_hash or "<genesis>"}'
            )
        expected_hash = row.compute_row_hash()
        if row.row_hash != expected_hash:
            raise AuditLogChainError(
                f'AuditLog #{row.pk} row_hash mismatch: '
                f'expected {expected_hash}, got {row.row_hash}'
            )
        expected_prev_hash = row.row_hash
    return checked
