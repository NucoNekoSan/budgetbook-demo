"""ExpenseGroup「食品・日用品」を作成し、ドラッグストア類を所属させる。

0008 では既存グループを前提にしていたが、グループが未作成の環境向けに
明示的にグループを生成する補助マイグレーション。冪等。
"""
from __future__ import annotations

from django.db import migrations


GROUP_NAME = '食品・日用品'
ADD_TO_GROUP_NAMES = [
    'ドラッグストア',
    'ツルハドラッグ',
    'イオン・マックスバリュー',
    'マックスバリュー',
    'スーパー・百貨店',
    'スーパー・ 百貨店',
    'コンビニ',
    'Co-op',
]


def ensure_food_daily_group(apps, schema_editor):
    Category = apps.get_model('ledger', 'Category')
    ExpenseGroup = apps.get_model('ledger', 'ExpenseGroup')
    ExpenseGroupCategory = apps.get_model('ledger', 'ExpenseGroupCategory')

    group, _created = ExpenseGroup.objects.get_or_create(
        name=GROUP_NAME,
        defaults={'is_active': True, 'sort_order': 0},
    )

    for cat_name in ADD_TO_GROUP_NAMES:
        cat = Category.objects.filter(name=cat_name, kind='expense').first()
        if cat is None:
            continue
        # OneToOne なので既に他グループに居れば触らない
        if ExpenseGroupCategory.objects.filter(category=cat).exists():
            continue
        ExpenseGroupCategory.objects.create(group=group, category=cat)


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0008_assign_food_daily_section'),
    ]

    operations = [
        migrations.RunPython(ensure_food_daily_group, reverse_noop),
    ]
