"""既存データに section='food_daily' を自動割当し、
ドラッグストア・ツルハドラッグを既存 ExpenseGroup「食品・日用品」へ追加する。

冪等：すでに section が設定されているカテゴリ、すでにグループ所属のカテゴリは触らない。
データが存在しない環境（テスト DB / 新規セットアップ）では何もしない。
"""
from __future__ import annotations

from django.db import migrations


# 食品・日用品 大分類に振り分ける店舗系カテゴリ名（既知のもの）
FOOD_DAILY_NAMES = [
    'イオン・マックスバリュー',
    'マックスバリュー',
    'スーパー・百貨店',
    'スーパー・ 百貨店',  # 全角空白入り表記の揺れ吸収
    'コンビニ',
    'Co-op',
    'ドラッグストア',
    'ツルハドラッグ',
]

# ExpenseGroup に追加するカテゴリ
GROUP_NAME = '食品・日用品'
ADD_TO_GROUP_NAMES = ['ドラッグストア', 'ツルハドラッグ']


def assign_food_daily(apps, schema_editor):
    Category = apps.get_model('ledger', 'Category')
    ExpenseGroup = apps.get_model('ledger', 'ExpenseGroup')
    ExpenseGroupCategory = apps.get_model('ledger', 'ExpenseGroupCategory')

    # 1. 既知の食品・日用品カテゴリに section を割当（既存値が other のものだけ）
    Category.objects.filter(
        name__in=FOOD_DAILY_NAMES,
        section='other',
    ).update(section='food_daily')

    # 2. ExpenseGroup「食品・日用品」が存在すれば、ドラッグストア類を追加
    group = ExpenseGroup.objects.filter(name=GROUP_NAME).first()
    if group is None:
        return  # 環境にグループがなければスキップ

    for cat_name in ADD_TO_GROUP_NAMES:
        cat = Category.objects.filter(name=cat_name, kind='expense').first()
        if cat is None:
            continue
        # ExpenseGroupCategory.category は OneToOne。既に他グループ所属なら触らない。
        if ExpenseGroupCategory.objects.filter(category=cat).exists():
            continue
        ExpenseGroupCategory.objects.create(group=group, category=cat)


def reverse_noop(apps, schema_editor):
    """巻き戻しはデータの自動削除をしない（手動で管理）。"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0007_category_section'),
    ]

    operations = [
        migrations.RunPython(assign_food_daily, reverse_noop),
    ]
