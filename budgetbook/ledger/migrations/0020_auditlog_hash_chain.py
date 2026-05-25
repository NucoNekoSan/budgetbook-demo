import hashlib
import json

from django.db import migrations, models


def audit_hash_payload(row, prev_hash: str) -> dict:
    return {
        'created_at': row.created_at.isoformat() if row.created_at else '',
        'user_id': row.user_id,
        'action': row.action,
        'target_model': row.target_model,
        'target_id': row.target_id,
        'target_repr': row.target_repr,
        'summary': row.summary,
        'metadata': row.metadata,
        'prev_hash': prev_hash,
    }


def compute_audit_hash(row, prev_hash: str) -> str:
    payload = json.dumps(
        audit_hash_payload(row, prev_hash),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        default=str,
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def backfill_audit_hash_chain(apps, schema_editor):
    AuditLog = apps.get_model('ledger', 'AuditLog')
    previous_hash = ''
    for row in AuditLog.objects.order_by('id').iterator(chunk_size=500):
        row.prev_hash = previous_hash
        row.row_hash = compute_audit_hash(row, previous_hash)
        row.save(update_fields=['prev_hash', 'row_hash'])
        previous_hash = row.row_hash


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0019_performance_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='auditlog',
            name='prev_hash',
            field=models.CharField(blank=True, editable=False, max_length=64, verbose_name='前監査ログハッシュ'),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='row_hash',
            field=models.CharField(blank=True, db_index=True, editable=False, max_length=64, verbose_name='監査ログハッシュ'),
        ),
        migrations.RunPython(backfill_audit_hash_chain, migrations.RunPython.noop),
    ]
