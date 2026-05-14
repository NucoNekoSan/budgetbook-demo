from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Account',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='作成日時')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新日時')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='口座名')),
                ('opening_balance', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='初期残高')),
                ('is_active', models.BooleanField(default=True, verbose_name='有効')),
                ('notes', models.TextField(blank=True, verbose_name='メモ')),
            ],
            options={
                'verbose_name': '口座',
                'verbose_name_plural': '口座',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='作成日時')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新日時')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='カテゴリ名')),
                ('kind', models.CharField(choices=[('income', '収入'), ('expense', '支出')], max_length=10, verbose_name='区分')),
                ('is_active', models.BooleanField(default=True, verbose_name='有効')),
                ('notes', models.TextField(blank=True, verbose_name='メモ')),
            ],
            options={
                'verbose_name': 'カテゴリ',
                'verbose_name_plural': 'カテゴリ',
                'ordering': ['kind', 'name'],
            },
        ),
        migrations.CreateModel(
            name='Transaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='作成日時')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新日時')),
                ('date', models.DateField(verbose_name='日付')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12, validators=[MinValueValidator(Decimal('0.01'))], verbose_name='金額')),
                ('description', models.CharField(max_length=120, verbose_name='摘要')),
                ('memo', models.TextField(blank=True, verbose_name='メモ')),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='ledger.account', verbose_name='口座')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='ledger.category', verbose_name='カテゴリ')),
            ],
            options={
                'verbose_name': '取引',
                'verbose_name_plural': '取引',
                'ordering': ['-date', '-id'],
            },
        ),
    ]
