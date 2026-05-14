# BudgetBook ファイル別詳解 — 全ファイルの役割と実装解説

## 目次

1. [設定ファイル（config/）](#1-設定ファイルconfig)
2. [モデル（ledger/models.py）](#2-モデルledgermodelspy)
3. [フォーム（ledger/forms.py）](#3-フォームledgerformspy)
4. [ビュー（ledger/views.py）](#4-ビューledgerviewspy)
5. [URL設定（urls.py）](#5-url設定urlspy)
6. [テンプレート（templates/）](#6-テンプレートtemplates)
7. [スタイルシート（static/css/style.css）](#7-スタイルシートstaticcsstylecss)
8. [管理画面（ledger/admin.py）](#8-管理画面ledgeradminpy)
9. [テンプレートフィルター（templatetags/ledger_extras.py）](#9-テンプレートフィルターtemplatetagsledger_extraspy)
10. [管理コマンド（management/commands/seed_budget_data.py）](#10-管理コマンドmanagementcommandsseed_budget_datapy)
11. [マイグレーション（migrations/）](#11-マイグレーションmigrations)
12. [アプリ設定（ledger/apps.py）](#12-アプリ設定ledgerappspy)
13. [エントリポイント（manage.py, wsgi.py, asgi.py）](#13-エントリポイントmanagepy-wsgipy-asgipy)
14. [依存関係（requirements.txt）](#14-依存関係requirementstxt)

---

## 1. 設定ファイル（config/）

### config/settings.py

**役割:** Django アプリケーション全体の設定を管理する中枢ファイル。
データベースの場所、使用するアプリ、セキュリティ設定、言語設定など、
あらゆる動作の基盤を定義します。

#### コード全文と詳細解説

```python
import os
from pathlib import Path
from dotenv import load_dotenv
```

- `os`: 環境変数を読み取るための標準ライブラリ
- `Path`: ファイルパスを安全に組み立てるためのクラス（OS間の差異を吸収）
- `load_dotenv`: `.env` ファイルから環境変数を読み込む外部ライブラリ

---

```python
BASE_DIR = Path(__file__).resolve().parent.parent
```

- **BASE_DIR**: プロジェクトのルートディレクトリのパス
- `__file__` → このファイル自身（settings.py）のパス
- `.resolve()` → 絶対パスに変換
- `.parent.parent` → 2階層上（settings.py → config/ → budgetbook/）
- 他の設定で「プロジェクトルートからの相対位置」を指定する基準点になる

---

```python
load_dotenv(BASE_DIR / '.env', override=True)
```

- プロジェクトルートの `.env` ファイルを読み込む
- `override=True` → 既存の環境変数があっても `.env` の値で上書き
- これにより `.env` ファイルに書いた `SECRET_KEY` などが `os.environ` から取得できるようになる

---

```python
_MISSING = object()

def _require_env(key: str) -> str:
    value = os.environ.get(key, _MISSING)
    if value is _MISSING:
        raise RuntimeError(
            f'環境変数 {key} が設定されていません。'
            f' プロジェクトルートの .env.example を .env にコピーして値を設定してください。'
        )
    return value
```

- **_MISSING**: 環境変数が未設定かどうかを判定するためのセンチネル値（番兵）
- なぜ `None` ではなく `object()` を使うのか？ → 環境変数の値が空文字 `""` の場合と「未設定」を区別するため
- `_require_env()`: 必須の環境変数が設定されていなければ、何をすべきかを伝えるエラーメッセージで停止する
- **初学者向け**: 「.env.example をコピーして値を設定してください」という親切なエラーメッセージがポイント

---

```python
SECRET_KEY = _require_env('SECRET_KEY')
DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')
ALLOWED_HOSTS: list[str] = [
    h.strip() for h in os.environ.get('ALLOWED_HOSTS', '').split(',') if h.strip()
]
```

- **SECRET_KEY**: Django の暗号化処理に使われるランダムな文字列。漏洩するとセッションの偽造などが可能になるため最重要機密
- **DEBUG**: 開発中は `True`（詳細なエラー画面を表示）、本番では必ず `False`（エラーの詳細を外部に見せない）
- **ALLOWED_HOSTS**: このサーバーにアクセスできるホスト名のリスト。セキュリティのためにホワイトリスト方式

---

```python
INSTALLED_APPS = [
    'django.contrib.admin',        # 管理画面
    'django.contrib.auth',         # ユーザー認証（ログイン/ログアウト）
    'django.contrib.contenttypes', # モデルのメタデータ管理
    'django.contrib.sessions',     # セッション管理（ログイン状態の保持）
    'django.contrib.messages',     # ワンタイムメッセージ
    'django.contrib.staticfiles',  # CSS/JS/画像の管理
    'axes',                        # ログイン試行回数制限
    'django_htmx',                 # HTMX リクエストの自動検出
    'ledger',                      # 家計簿アプリ本体
]
```

- Django に「どのアプリを使うか」を教える設定
- 上6つは Django 標準の機能、下3つがこのプロジェクト固有

---

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'axes.middleware.AxesMiddleware',
]
```

- **ミドルウェア**: リクエストとレスポンスの間で自動実行される処理の連鎖
- 上から順番に実行され、セキュリティチェック → セッション管理 → CSRF防御 → 認証確認 と進む
- `WhiteNoiseMiddleware`: 静的ファイル（CSS等）を効率的に配信。本番環境で別途 Nginx を用意しなくてもOK
- `HtmxMiddleware`: リクエストが HTMX からかどうかを `request.htmx` で判定可能にする
- `AxesMiddleware`: ログイン試行回数を監視し、上限超過時にロックアウトする
- **順序が重要**: SecurityMiddleware は最初に、WhiteNoise はその直後に置く必要がある

---

```python
ROOT_URLCONF = 'config.urls'
```

- URL設計の起点となるファイルを指定

---

```python
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]
```

- `DIRS`: テンプレートファイルの検索場所。`templates/` フォルダを見に行く
- `APP_DIRS: True`: 各アプリの `templates/` フォルダも自動で探索
- `context_processors`: テンプレートに自動で渡される変数（ログインユーザー情報など）

---

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

- SQLite を使用。データベースは `db.sqlite3` という1つのファイル
- 開発・個人利用なら SQLite で十分。本格的なサービスでは PostgreSQL 等に変更可能

---

```python
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
```

- パスワードの強度チェック:
  1. ユーザー名と似すぎていないか
  2. 最低文字数を満たしているか（デフォルト8文字）
  3. よくあるパスワード（password, 123456等）ではないか
  4. 数字だけではないか

---

```python
LANGUAGE_CODE = 'ja'
TIME_ZONE = 'Asia/Tokyo'
USE_I18N = True     # 国際化対応ON
USE_TZ = True       # タイムゾーン対応ON
```

- 日本語・日本時間でアプリが動作する

---

```python
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}
```

- `STATIC_URL`: CSSやJSにアクセスするURLの接頭辞
- `STATICFILES_DIRS`: 開発時に静的ファイルを探す場所
- `STATIC_ROOT`: `collectstatic` コマンドで本番用に集約する先
- `CompressedStaticFilesStorage`: gzip圧縮して配信（通信量削減）

---

```python
CSRF_COOKIE_HTTPONLY = False    # HTMX用: JSからCSRFトークンを読める必要がある
SESSION_COOKIE_HTTPONLY = True  # セッションCookieはJSから読めない（安全）
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
```

- **CSRF**: 外部サイトからのなりすましリクエストを防ぐ仕組み
- `CSRF_COOKIE_HTTPONLY = False` は HTMX が CSRF トークンをリクエストヘッダに含めるために必要

---

```python
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'
```

- ログインしていない状態でアクセス → `/accounts/login/` にリダイレクト
- ログイン成功 → トップページ（ダッシュボード）に遷移
- ログアウト → ログインページに戻る

---

### config/urls.py

**役割:** アプリケーション全体の URL ルーティング（道案内）の起点。

```python
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', LoginView.as_view(
        template_name='registration/login.html',
        redirect_authenticated_user=True,
    ), name='login'),
    path('accounts/logout/', LogoutView.as_view(), name='logout'),
    path('', include('ledger.urls')),
]
```

**各行の解説:**
- `admin/`: Django 標準の管理画面へのルート
- `accounts/login/`: Django の認証ビューを使用。`redirect_authenticated_user=True` で、ログイン済みユーザーがログインページを開くと自動でダッシュボードに飛ぶ
- `accounts/logout/`: ログアウト処理（POST メソッドで実行）
- `''` (空文字): それ以外の全URL は `ledger.urls` で定義されたルートに委譲

---

### config/wsgi.py / config/asgi.py

**役割:** 本番環境でWebサーバー（Gunicorn, Daphne等）と Django を接続するための入口ファイル。

```python
# wsgi.py — 同期通信用
import os
from django.core.wsgi import get_wsgi_application
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
application = get_wsgi_application()

# asgi.py — 非同期通信用（WebSocket等に対応）
import os
from django.core.asgi import get_asgi_application
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
application = get_asgi_application()
```

- 開発サーバー（`runserver`）では自動的に使われるため、通常は編集不要
- 本番デプロイ時に Gunicorn 等がこの `application` オブジェクトを呼び出す

---

## 2. モデル（ledger/models.py）

**役割:** データベースに保存するデータの構造（スキーマ）を定義する、アプリの基盤。

### TimeStampedModel（抽象基底モデル）

```python
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField('作成日時', auto_now_add=True)
    updated_at = models.DateTimeField('更新日時', auto_now=True)

    class Meta:
        abstract = True
```

| 要素 | 説明 |
|------|------|
| `created_at` | データが初めて保存された日時。`auto_now_add=True` で自動設定され、以後変更されない |
| `updated_at` | データが最後に更新された日時。`auto_now=True` で保存のたびに自動更新 |
| `abstract = True` | このモデル自体はデータベースにテーブルを作らない。他のモデルが「継承」して使う設計 |

**なぜ抽象モデルを使うのか？**
Account, Category, Transaction の3つ全てに作成日・更新日が必要です。
各モデルに同じフィールドを3回書く代わりに、共通部分を1か所にまとめています（DRY原則）。

### Account（口座モデル）

```python
class Account(TimeStampedModel):
    name = models.CharField('口座名', max_length=100, unique=True)
    opening_balance = models.IntegerField(
        '初期残高', default=0, validators=[MinValueValidator(0)],
    )
    is_active = models.BooleanField('有効', default=True)
    notes = models.TextField('メモ', blank=True)

    class Meta:
        verbose_name = '口座'
        verbose_name_plural = '口座'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name
```

| フィールド | 型 | 制約 | 説明 |
|-----------|-----|------|------|
| `name` | 文字列（100文字以内） | ユニーク | 口座名。同名は不可 |
| `opening_balance` | 整数 | 0以上 | 使い始めの残高 |
| `is_active` | 真偽値 | - | 有効/無効のフラグ |
| `notes` | テキスト | 空でもOK | 自由記述のメモ |

**Meta クラスの設定:**
- `verbose_name`: 管理画面での表示名
- `ordering = ['name']`: 口座名の昇順で並べる（デフォルトの並び順）

**`__str__` メソッド:**
- Python の「このオブジェクトを文字列にしたらどう表示するか」の定義
- 管理画面やデバッグ時に口座名が表示される

### Category（カテゴリモデル）

```python
class Category(TimeStampedModel):
    class Kind(models.TextChoices):
        INCOME = 'income', '収入'
        EXPENSE = 'expense', '支出'

    name = models.CharField('カテゴリ名', max_length=100, unique=True)
    kind = models.CharField('区分', max_length=10, choices=Kind.choices)
    is_active = models.BooleanField('有効', default=True)
    notes = models.TextField('メモ', blank=True)

    class Meta:
        verbose_name = 'カテゴリ'
        verbose_name_plural = 'カテゴリ'
        ordering = ['kind', 'name']

    def __str__(self) -> str:
        return f'{self.get_kind_display()} | {self.name}'
```

**TextChoices の仕組み:**
- `Kind.INCOME` の値は `'income'`、表示名は `'収入'`
- データベースには `'income'` が保存され、画面には `'収入'` と表示される
- `choices` を使うことで、想定外の値が保存されるのを防ぐ

**`get_kind_display()` メソッド:**
- Django が `choices` を持つフィールドに自動生成するメソッド
- `'income'` → `'収入'` のように、コード値を日本語表示名に変換

**ordering = ['kind', 'name']:**
- まず kind で並べ（expense が先、income が後）、その中で名前順

### Transaction（取引モデル）

```python
class Transaction(TimeStampedModel):
    date = models.DateField('日付')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, verbose_name='口座')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, verbose_name='カテゴリ')
    amount = models.IntegerField('金額', validators=[MinValueValidator(1)])
    description = models.CharField('摘要', max_length=120)
    memo = models.TextField('メモ', blank=True)

    class Meta:
        verbose_name = '取引'
        verbose_name_plural = '取引'
        ordering = ['-date', '-id']

    def __str__(self) -> str:
        return f'{self.date} {self.description} {self.amount}'

    @property
    def kind(self) -> str:
        return self.category.kind
```

**ForeignKey（外部キー）の詳解:**

```
Transaction ──→ Account    （多対1の関係）
Transaction ──→ Category   （多対1の関係）
```

- 1つの口座に対して複数の取引がある（1対多）
- 1つのカテゴリに対して複数の取引がある（1対多）
- `on_delete=models.PROTECT`: 取引が紐づいている口座/カテゴリの削除を禁止
  - これがないと、口座を消した瞬間にその口座の取引データが壊れる

**`@property` デコレーター:**
- `kind` プロパティにより、`transaction.kind` で直接カテゴリの種別にアクセスできる
- 内部的には `transaction.category.kind` を返しているだけ
- プロパティを使うことで、外部からはフィールドのようにアクセスでき、コードが読みやすくなる

---

## 3. フォーム（ledger/forms.py）

**役割:** ユーザーからの入力データを受け取り、バリデーション（検証）を行う。
HTMLフォームの生成とデータの整合性チェックを担当します。

### DateInput（日付入力ウィジェット）

```python
class DateInput(forms.DateInput):
    input_type = 'date'
```

- ブラウザ標準の日付ピッカーを使うためのカスタムウィジェット
- `input_type = 'date'` により `<input type="date">` が出力される

### TransactionForm（取引フォーム）

```python
class TransactionForm(forms.ModelForm):
    kind = forms.ChoiceField(
        choices=Category.Kind.choices,
        label='種別',
        widget=forms.Select(attrs={
            'class': 'form-input',
            'hx-get': reverse_lazy('ledger:category_options'),
            'hx-target': '#id_category',
            'hx-swap': 'innerHTML',
            'hx-trigger': 'change',
        }),
    )

    field_order = ['date', 'account', 'kind', 'category', 'amount', 'description', 'memo']
```

**`kind` フィールドの特殊性:**
- `kind` は Transaction モデルにはないフィールド（フォーム専用）
- 収入/支出を切り替えるUIのために存在
- HTMX 属性をウィジェットに直接埋め込んでおり、種別を変えるとカテゴリの選択肢が自動で変わる

**HTMX 属性の動作:**
1. `hx-trigger="change"` → ユーザーが種別を変更したら
2. `hx-get="..."` → サーバーにGETリクエストを送信
3. サーバーが該当する種別のカテゴリ一覧を HTML で返す
4. `hx-target="#id_category"` → カテゴリ選択欄の中身を
5. `hx-swap="innerHTML"` → 差し替える

**`field_order`:**
- フォームのフィールド表示順序を指定
- 日付 → 口座 → 種別 → カテゴリ → 金額 → 摘要 → メモ の順

**`__init__` メソッド（初期化ロジック）:**
```python
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.fields['account'].queryset = Account.objects.filter(is_active=True).order_by('name')
    for field in self.fields.values():
        field.help_text = ''

    if self.data.get('kind') in Category.Kind.values:
        kind = self.data['kind']
    elif self.instance and self.instance.pk:
        kind = self.instance.category.kind
    else:
        kind = Category.Kind.EXPENSE

    self.fields['kind'].initial = kind
    self.fields['category'].queryset = Category.objects.filter(
        is_active=True, kind=kind
    ).order_by('name')
```

- 口座の選択肢を「有効な口座のみ」に絞る
- ヘルプテキストを除去（UIをすっきりさせる）
- kind の決定優先順位:
  1. POST されたデータの kind（フォーム送信時）
  2. 既存取引の種別（編集時）
  3. デフォルト値（支出）
- カテゴリの選択肢を kind に基づいて絞り込む

**`clean` メソッド（カスタムバリデーション）:**
```python
def clean(self):
    cleaned = super().clean()
    kind = cleaned.get('kind')
    category = cleaned.get('category')
    if kind and category and category.kind != kind:
        raise forms.ValidationError(
            '種別とカテゴリが一致しません。種別を変更したときはカテゴリを再選択してください。'
        )
    return cleaned
```

- 種別（収入/支出）とカテゴリの整合性チェック
- 例: 種別が「支出」なのにカテゴリが「給与」（収入カテゴリ）→ エラー
- HTMX でカテゴリは動的に絞られるが、ブラウザのデベロッパーツールで改ざんできるため、サーバー側でも必ず検証

### AccountForm（口座フォーム）

```python
class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['name', 'opening_balance', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '例: 三菱UFJ、現金'}),
            'opening_balance': forms.NumberInput(attrs={'class': 'form-input', 'step': '1', 'min': '0'}),
            'notes': forms.Textarea(attrs={'class': 'form-input', 'rows': 2, 'placeholder': '任意メモ'}),
        }
```

**初期残高の保護:**
```python
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    if self.instance and self.instance.pk:
        self.fields['opening_balance'].widget.attrs['readonly'] = True
        self.fields['opening_balance'].help_text = '初期残高は残高計算に影響するため変更できません。'

def clean_opening_balance(self):
    if self.instance and self.instance.pk:
        return self.instance.opening_balance    # 元の値を返す
    return self.cleaned_data['opening_balance']
```

**二重防御のパターン:**
1. UI層: `readonly` 属性でブラウザ上では編集不可に見せる
2. サーバー層: `clean_opening_balance()` で、たとえ送信データが改ざんされても元の値を返す
3. なぜ両方必要か？ → ブラウザの `readonly` はデベロッパーツールで簡単に外せるため

**名前の一意性チェック:**
```python
def clean_name(self):
    name = self.cleaned_data['name']
    qs = Account.objects.filter(name=name)
    if self.instance and self.instance.pk:
        qs = qs.exclude(pk=self.instance.pk)    # 自分自身は除外
    if qs.exists():
        raise forms.ValidationError(f'「{name}」は既に使われています。別の名前を入力してください。')
    return name
```

- 同名の口座がないかチェック
- 編集時は「自分自身」を除外して判定（自分の現在の名前と一致するのはOK）

### CategoryForm（カテゴリフォーム）

```python
class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'kind', 'notes']
```

**区分（kind）の変更禁止:**
```python
def __init__(self, *args, **kwargs):
    if self.instance and self.instance.pk:
        self.fields['kind'].widget.attrs['disabled'] = True

def clean_kind(self):
    if self.instance and self.instance.pk:
        return self.instance.kind     # 既存カテゴリは元の kind を返す
    return self.cleaned_data['kind']
```

- `disabled` はUI上で選択不可にする（`readonly` より強力で、値も送信されない）
- `clean_kind()` で既存カテゴリの kind は絶対に変更させない
- 理由: 「食費」を支出→収入に変えると、過去の取引の意味が壊れる

---

## 4. ビュー（ledger/views.py）

**役割:** HTTPリクエストを受け取り、モデルからデータを取得し、テンプレートでレンダリングして返す
アプリケーションの「司令塔」。ビジネスロジックの中核を担います。

### ヘルパー関数群

#### parse_month() — 月のパース

```python
def parse_month(month_str: str | None) -> date:
    today = date.today()
    if not month_str:
        return date(today.year, today.month, 1)
    try:
        year, month = month_str.split('-')
        return date(int(year), int(month), 1)
    except (TypeError, ValueError):
        return date(today.year, today.month, 1)
```

- URL パラメータの `month=2026-04` を `date(2026, 4, 1)` に変換
- 不正な値が来ても今月を返す（エラーにならない安全設計）

#### shift_month() — 月の移動

```python
def shift_month(target: date, offset: int) -> date:
    year = target.year + ((target.month - 1 + offset) // 12)
    month = ((target.month - 1 + offset) % 12) + 1
    return date(year, month, 1)
```

- 月をoffset分だけ前後に移動
- 1月の1ヶ月前→前年12月、12月の1ヶ月後→翌年1月、を正しく処理
- 算術演算で年またぎも対応（ライブラリに頼らない効率的な計算）

#### clamp_future_month() — 未来月のクランプ

```python
def clamp_future_month(target: date) -> date:
    today = date.today()
    current_month = date(today.year, today.month, 1)
    return min(target, current_month)
```

- 指定された月が未来なら今月に強制変更
- URL を手動で書き換えて未来の月にアクセスされるのを防ぐ

#### parse_filters() — フィルター条件の解析

```python
def parse_filters(params: dict) -> dict:
    filters = {}
    q = params.get('q', '').strip()
    if q:
        filters['q'] = q
    account = params.get('account', '').strip()
    if account:
        try:
            filters['account'] = int(account)
        except (TypeError, ValueError):
            pass
    # ...同様に category
    return filters
```

- URL パラメータから検索条件を安全に抽出
- 空文字や不正な値は無視して、有効な条件だけを辞書で返す

### _build_daily_trend() — 当月の日別推移データの構築

```python
def _build_daily_trend(target_month: date) -> list[dict]:
    start = target_month
    end = shift_month(target_month, 1)
    num_days = monthrange(target_month.year, target_month.month)[1]
    rows = (
        Transaction.objects
        .filter(date__gte=start, date__lt=end)
        .values('date')
        .annotate(
            income=Coalesce(Sum('amount', filter=Q(category__kind='income')),
                            Value(0, output_field=IntegerField())),
            expense=Coalesce(Sum('amount', filter=Q(category__kind='expense')),
                             Value(0, output_field=IntegerField())),
        )
        .order_by('date')
    )
```

**Django ORM の高度なクエリ:**
- `.values('date')`: 日付ごとにグループ化（SQLite 互換性のため `TruncDate` ではなく直接参照）
- `Sum('amount', filter=Q(...))`: 条件付き合計（収入だけ、支出だけを集計）
- `Coalesce(..., Value(0, output_field=IntegerField()))`: 合計が NULL（データなし）の場合は 0 を返す
- これにより1回のSQLクエリで当月分の日別収支データを取得

**データが欠落する日の補完:**
```python
by_day = {row['date']: row for row in rows}
result = []
for d in range(1, num_days + 1):
    key = date(target_month.year, target_month.month, d)
    row = by_day.get(key)
    inc = row['income'] if row else 0
    exp = row['expense'] if row else 0
    result.append({'label': f'{d}日', 'income': inc, 'expense': exp, 'net': inc - exp})
```

- 取引がない日はデータベースから返ってこない
- 当月の全日数分のデータを確実に用意するため、欠落日は0で埋める

### get_dashboard_context() — ダッシュボード用データの組み立て

この関数が最も複雑で、ダッシュボードに必要な全データを集約します:

1. **月間収支の集計**: 当月の収入合計・支出合計・差額
2. **カテゴリ別支出**: 支出上位8カテゴリ
3. **口座残高**: 各口座の月末時点の残高（`初期残高 + 収入 - 支出`）
4. **取引一覧**: フィルター・ページネーション適用済み
5. **月ナビゲーション**: 前月・次月へのリンクパラメータ
6. **フィルター状態**: 現在の絞り込み条件

**口座残高の計算:**
```python
account_balances = list(
    Account.objects.filter(is_active=True)
    .annotate(
        income_total=Coalesce(
            Sum('transaction__amount', filter=Q(
                transaction__category__kind='income',
                transaction__date__lte=month_end(target_month),
            )),
            Value(0),
        ),
        expense_total=Coalesce(
            Sum('transaction__amount', filter=Q(
                transaction__category__kind='expense',
                transaction__date__lte=month_end(target_month),
            )),
            Value(0),
        ),
    )
)

for account in account_balances:
    account.current_balance = account.opening_balance + account.income_total - account.expense_total
```

- `transaction__amount`: Account から Transaction への逆参照（ForeignKey の逆引き）
- `month_end(target_month)` までの取引を集計することで、その月末時点の残高を算出

### dashboard() — ダッシュボードビュー

```python
@login_required
@require_http_methods(['GET'])
def dashboard(request):
    target_month = clamp_future_month(parse_month(request.GET.get('month')))
    page = request.GET.get('page', 1)
    filters = parse_filters(request.GET)
    context = get_dashboard_context(target_month, page=page, filters=filters)

    if request.htmx:
        return render(request, 'ledger/partials/dashboard_content.html', context)
    context.update(build_form_context(target_month))
    return render(request, 'ledger/dashboard.html', context)
```

**HTMX レスポンスの分岐:**
- 通常のリクエスト（初回ページ読み込み）→ 完全なページ（base.html 含む）を返す
- HTMX リクエスト（月の切替、フィルター操作）→ 部品テンプレートだけ返す
- これにより、画面の再描画が最小限になり、スムーズな操作感を実現

### transaction_create() / transaction_update() — 取引の作成・更新

```python
@login_required
@require_http_methods(['GET', 'POST'])
def transaction_create(request):
    if request.method == 'POST':
        form = TransactionForm(request.POST)
        if form.is_valid():
            form.save()
            if request.htmx:
                return render_dashboard_bundle(request, target_month, '取引を保存しました。')
            return redirect(...)
        status = 422 if request.htmx else 200
        return render(request, '.../transaction_form_panel.html', context, status=status)

    context = build_form_context(target_month)
    return render(request, '.../transaction_form_panel.html', context)
```

**処理フロー:**
1. GET リクエスト → 空のフォーム（新規）or 値が入ったフォーム（編集）を表示
2. POST リクエスト → フォームデータを検証
   - 成功 → データ保存、ダッシュボードとフォームを更新
   - 失敗 → エラー付きフォームを再表示（HTTP 422）

### transaction_delete() — 取引の削除

```python
@login_required
@require_http_methods(['GET', 'POST'])
def transaction_delete(request, pk):
    transaction = get_object_or_404(Transaction..., pk=pk)

    if request.method == 'POST':
        transaction.delete()
        if request.htmx:
            return render_dashboard_bundle(request, target_month, '取引を削除しました。')
        return redirect(...)

    return render(request, '.../transaction_delete_confirm.html', {...})
```

**2ステップ削除パターン:**
1. GET → 削除確認画面を表示（「本当に削除しますか？」）
2. POST → 実際に削除を実行
- 確認ステップがあることで、誤操作による削除を防ぐ

### transaction_export() — CSV エクスポート

```python
def transaction_export(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="kakeibo-{month_param(target_month)}.csv"'
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow(['日付', '種別', '口座', 'カテゴリ', '金額', '摘要', 'メモ'])
    for tx in transactions:
        writer.writerow([...])
```

- `Content-Disposition: attachment` → ブラウザにダウンロードさせる
- `\ufeff`（BOM）→ Excel で開いたときの文字化け防止
- ファイル名に月を含めて管理しやすく（例: `kakeibo-2026-04.csv`）

### category_options() — カテゴリ選択肢の動的取得

```python
@login_required
@require_http_methods(['GET'])
def category_options(request):
    kind = request.GET.get('kind', Category.Kind.EXPENSE)
    if kind not in Category.Kind.values:
        kind = Category.Kind.EXPENSE
    categories = Category.objects.filter(is_active=True, kind=kind).order_by('name')
    return render(request, 'ledger/partials/category_options.html', {'categories': categories})
```

- HTMX から呼ばれる専用エンドポイント
- 指定された種別（income/expense）に合うカテゴリの `<option>` タグを返す
- 不正な kind が送られてもデフォルト値で安全に処理

### 設定画面関連のビュー

#### settings_page() — 設定画面の表示

```python
def settings_page(request):
    context = _settings_context()
    context['account_form'] = AccountForm()
    context['category_form'] = CategoryForm()
    return render(request, 'ledger/settings.html', context)
```

#### account_create() / category_create() — 口座・カテゴリの作成

```python
def account_create(request):
    if request.method == 'POST':
        form = AccountForm(request.POST)
        if form.is_valid():
            form.save()
            return _render_account_list(request, '口座を追加しました。')
        # バリデーションエラー → フォーム付きでリスト再表示
        return render(..., status=422)
    return _render_account_list(request)
```

#### account_update() / category_update() — 口座・カテゴリの編集

```python
def account_update(request, pk):
    account = get_object_or_404(Account, pk=pk)
    if request.method == 'POST':
        form = AccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            return _render_account_list(request, f'「{account.name}」を更新しました。')
        # バリデーションエラー → 編集フォームを開いたまま再表示（422）
        ...
    # GET → 対象行を編集フォームに差し替えた一覧を返す
    ...
```

- 一覧テンプレート内で対象行をインライン編集フォームに差し替えるパターン
- 「更新する」ボタンの最終確認ダイアログはテンプレート側（JS）で表示
- バリデーション失敗時は `status=422` で編集フォームを保持したまま再描画

#### account_toggle() / category_toggle() — 有効/無効切替

```python
def account_toggle(request, pk):
    account = get_object_or_404(Account, pk=pk)
    account.is_active = not account.is_active
    account.save(update_fields=['is_active'])
    label = '有効' if account.is_active else '無効'
    return _render_account_list(request, f'「{account.name}」を{label}にしました。')
```

- `not account.is_active` で True/False を反転
- `update_fields=['is_active']` → 変更したフィールドだけをDBに書き込む（効率的）
- 取引が紐づいていて削除できないデータは、無効化で一覧から隠す運用に使う

#### account_delete() / category_delete() — 口座・カテゴリの削除

```python
def account_delete(request, pk):
    account = get_object_or_404(Account, pk=pk)
    name = account.name
    try:
        account.delete()
    except ProtectedError:
        return _render_account_list(
            request,
            f'「{name}」には取引が紐づいているため削除できません。先に取引を削除するか、無効化してください。',
        )
    return _render_account_list(request, f'「{name}」を削除しました。')
```

- 編集フォーム内の「削除」ボタンから POST で呼び出される
- `Account` / `Category` は `Transaction` から `on_delete=PROTECT` で参照されているため、紐づく取引があると `ProtectedError` が発生
- 例外を捕捉して「削除できない旨」のフラッシュメッセージを返し、データの整合性を守る
- 取引が残っている場合の運用導線として、`*_toggle` による無効化を案内する

### annual() — 年間サマリー

```python
def annual(request):
    year = clamp_future_year(parse_year(request.GET.get('year')))
    months = _build_annual_summary(year)

    total_income = sum(m['income'] for m in months)
    total_expense = sum(m['expense'] for m in months)
    total_net = total_income - total_expense

    next_year = year + 1 if year < today.year else None
```

- 未来の年は閲覧不可（`clamp_future_year`）
- 12ヶ月分のデータを構築し、年間合計も計算
- 次年のリンクは今年以降は非表示

---

## 5. URL設定（urls.py）

### config/urls.py（ルートURL）

上述の config/urls.py セクションを参照。

### ledger/urls.py（アプリURL）

```python
from django.urls import path
from . import views

app_name = 'ledger'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('categories/options/', views.category_options, name='category_options'),
    path('transactions/export/', views.transaction_export, name='transaction_export'),
    path('transactions/new/', views.transaction_create, name='transaction_create'),
    path('transactions/<int:pk>/edit/', views.transaction_update, name='transaction_update'),
    path('transactions/<int:pk>/delete/', views.transaction_delete, name='transaction_delete'),
    path('annual/', views.annual, name='annual'),
    path('settings/', views.settings_page, name='settings'),
    path('settings/accounts/new/', views.account_create, name='account_create'),
    path('settings/accounts/<int:pk>/edit/', views.account_update, name='account_update'),
    path('settings/accounts/<int:pk>/toggle/', views.account_toggle, name='account_toggle'),
    path('settings/accounts/<int:pk>/delete/', views.account_delete, name='account_delete'),
    path('settings/categories/new/', views.category_create, name='category_create'),
    path('settings/categories/<int:pk>/edit/', views.category_update, name='category_update'),
    path('settings/categories/<int:pk>/toggle/', views.category_toggle, name='category_toggle'),
    path('settings/categories/<int:pk>/delete/', views.category_delete, name='category_delete'),
]
```

**URL 設計の詳解:**

| URL | メソッド | 機能 | 名前 |
|-----|---------|------|------|
| `/` | GET | ダッシュボード表示 | `dashboard` |
| `/categories/options/` | GET | カテゴリ選択肢取得（HTMX用） | `category_options` |
| `/transactions/export/` | GET | CSV ダウンロード | `transaction_export` |
| `/transactions/new/` | GET/POST | 取引の新規作成 | `transaction_create` |
| `/transactions/<id>/edit/` | GET/POST | 取引の編集 | `transaction_update` |
| `/transactions/<id>/delete/` | GET/POST | 取引の削除（確認 → 実行） | `transaction_delete` |
| `/annual/` | GET | 年間サマリー | `annual` |
| `/settings/` | GET | 設定画面 | `settings` |
| `/settings/accounts/new/` | GET/POST | 口座の追加 | `account_create` |
| `/settings/accounts/<id>/edit/` | GET/POST | 口座の編集 | `account_update` |
| `/settings/accounts/<id>/toggle/` | POST | 口座の有効/無効切替 | `account_toggle` |
| `/settings/accounts/<id>/delete/` | POST | 口座の削除（取引が紐づく場合は保護） | `account_delete` |
| `/settings/categories/new/` | GET/POST | カテゴリの追加 | `category_create` |
| `/settings/categories/<id>/edit/` | GET/POST | カテゴリの編集 | `category_update` |
| `/settings/categories/<id>/toggle/` | POST | カテゴリの有効/無効切替 | `category_toggle` |
| `/settings/categories/<id>/delete/` | POST | カテゴリの削除（取引が紐づく場合は保護） | `category_delete` |

**`app_name = 'ledger'` の意味:**
- URL の名前空間を設定
- テンプレートで `{% url 'ledger:dashboard' %}` と書ける
- 将来別のアプリを追加しても URL 名が衝突しない

---

## 6. テンプレート（templates/）

### base.html — 全ページ共通の骨格

```html
{% load django_htmx %}
{% load static %}
<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}BudgetBook{% endblock %}</title>
    <link rel="stylesheet" href="{% static 'css/style.css' %}">
    {% htmx_script %}
    <script src="{% static 'vendor/chart.umd.min.js' %}" defer></script>
    <script src="{% static 'js/budget_chart.js' %}" defer></script>
    {% block extra_js %}{% endblock %}
  </head>
  <body hx-headers='{"x-csrftoken": "{{ csrf_token }}"}'>
```

**重要なポイント:**
- CSS を `<script>` より前に配置し、スタイルが先に読み込まれるようにしている
- `{% htmx_script %}`: HTMX の JavaScript を自動的に読み込む
- Chart.js は CDN を使わず `static/vendor/` にローカル配置（オフライン動作・CSP 対応のため）
- `budget_chart.js` は Y 軸設定などの共通ヘルパーを定義する `BudgetChart` オブジェクトを提供
- `{% block extra_js %}`: 各ページ固有のチャートスクリプトを読み込むブロック
- `defer`: スクリプトを HTML 解析後に実行（ページ表示を妨げない）
- `hx-headers`: body 全体に CSRF トークンを設定。HTMX の全リクエストに自動付与される

**ナビゲーション:**
```html
<nav class="site-nav">
  <a href="{% url 'ledger:dashboard' %}" class="site-nav__link">家計簿</a>
  <a href="{% url 'ledger:annual' %}" class="site-nav__link">年間</a>
  <a href="{% url 'ledger:settings' %}" class="site-nav__link">設定</a>
  <form method="post" action="{% url 'logout' %}" class="site-nav__logout">
    {% csrf_token %}
    <button type="submit" ...>{{ user.username }} : ログアウト</button>
  </form>
</nav>
```

- ログアウトは GET ではなく POST で実行（セキュリティ上の理由）
- `{{ user.username }}` でログイン中のユーザー名を表示

### registration/login.html — ログイン画面

```html
<!doctype html>
<html lang="ja">
```

- `base.html` を継承せず、独自の完全な HTML として定義
- 理由: ログイン画面にはナビゲーションが不要なため
- 画面中央にログインカードを配置するシンプルなデザイン

### ledger/dashboard.html — ダッシュボード

```html
{% extends 'base.html' %}

{% block content %}
  <div id="flash" class="flash"></div>
  <div class="layout">
    <section id="dashboard-content">
      {% include 'ledger/partials/dashboard_content.html' %}
    </section>
    <aside id="form-panel" class="panel">
      {% include 'ledger/partials/transaction_form_panel.html' %}
    </aside>
  </div>
{% endblock %}
```

**2カラムレイアウトの構造:**
- 左側 (`#dashboard-content`): 集計データ、グラフ、取引一覧
- 右側 (`#form-panel`): 取引入力フォーム（常時表示）
- `{% include ... %}` で部品テンプレートを読み込む
- HTMX は `#dashboard-content` や `#form-panel` を ID で指定して部分更新

### partials/dashboard_content.html — ダッシュボードの中身

このファイルが最も大きく、以下のセクションで構成されます：

1. **月ナビゲーション**（前月/次月ボタン）
2. **サマリーカード**（収入・支出・差額）
3. **カテゴリ別支出一覧**
4. **日別収支推移グラフ**（Chart.js）
5. **口座残高一覧**
6. **取引一覧**（テーブル）
7. **フィルターバー**（検索・絞り込み）
8. **ページネーション**

**月ナビゲーションのHTMX:**
```html
<button
  class="btn btn--ghost"
  hx-get="{% url 'ledger:dashboard' %}?{{ previous_month_query }}"
  hx-target="#dashboard-content"
  hx-swap="innerHTML"
  hx-push-url="true"
>← 前月</button>
```

- `hx-push-url="true"`: ブラウザの URL を更新（ブックマーク可能にする）
- ページ全体の再読み込みなしに月を切り替えられる

**Chart.js のグラフ初期化（`static/js/dashboard_chart.js`）:**

チャート初期化スクリプトは CSP 導入準備のため、インラインではなく外部 JS ファイルに分離しています。

```javascript
(function() {
  function initTrendChart() {
    var el = document.getElementById('trend-chart');
    if (!el || typeof Chart === 'undefined' || typeof BudgetChart === 'undefined') return;
    if (window._trendChart) {
      window._trendChart.destroy();    // 既存のチャートを破棄（メモリリーク防止）
    }
    var raw = JSON.parse(document.getElementById('daily-trend-data').textContent);
    window._trendChart = new Chart(el, {...});
  }

  // defer スクリプトの実行タイミングに対応
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTrendChart);
  } else {
    initTrendChart();
  }

  // HTMX による部分更新後の再初期化
  document.addEventListener('htmx:load', function(e) {
    if (e.detail.elt.querySelector && e.detail.elt.querySelector('#trend-chart')) {
      initTrendChart();
    }
  });
})();
```

- `window._trendChart.destroy()`: HTMX で月を切り替えると新しいグラフが作られるが、古いグラフを破棄しないとメモリリークする
- `readyState` チェック: `defer` 属性付きスクリプトは DOM 解析後に実行されるが、`DOMContentLoaded` が既に発火済みの場合がある。この分岐で両方のタイミングに対応
- `htmx:load` イベント: HTMX が新しいコンテンツを読み込んだ後にグラフを再初期化
- `json_script` フィルター: Python のデータを安全に JavaScript に渡す（XSS 対策済み）

### partials/transaction_form_panel.html — 取引フォーム

```html
<form
  hx-post="{{ form_action }}"
  hx-target="#form-panel"
  hx-swap="innerHTML"
  class="form-grid"
>
  <input type="hidden" name="month" value="{{ month_param }}">
  {% for field in form %}
    <div class="field">
      <label for="{{ field.id_for_label }}">{{ field.label }}</label>
      {{ field }}
      {% if field.errors %}
        <ul class="errors">...</ul>
      {% endif %}
    </div>
  {% endfor %}
</form>
```

- `hx-post`: フォーム送信を HTMX で処理（ページ遷移なし）
- `{{ form_action }}`: 新規作成URL か編集URL が動的に設定される
- `{% for field in form %}`: フォームのフィールドをループで表示
- 隠しフィールド `month` で現在表示中の月を送信

### partials/transaction_bundle.html — OOB 同時更新

```html
<div id="flash" hx-swap-oob="innerHTML">
  <div class="flash__message">{{ flash_message }}</div>
</div>

<div id="dashboard-content" hx-swap-oob="innerHTML">
  {% include 'ledger/partials/dashboard_content.html' %}
</div>

<div id="form-panel" class="panel" hx-swap-oob="outerHTML">
  {% include 'ledger/partials/transaction_form_panel.html' %}
</div>

<div></div>
```

**hx-swap-oob（Out of Band swap）の仕組み:**
- 通常の HTMX レスポンスは1つの要素しか更新できない
- `hx-swap-oob` を使うと、レスポンスに含まれる複数の要素をそれぞれの ID に基づいて同時更新
- 空の `<div></div>` は HTMX の元のターゲット（フォームパネル）用のダミー要素

**更新される3つの領域:**
1. `#flash`: フラッシュメッセージ（「取引を保存しました」）
2. `#dashboard-content`: ダッシュボードの数値やグラフの再計算
3. `#form-panel`: フォームのクリア（次の入力に備える）

### partials/transaction_delete_confirm.html — 削除確認

```html
<div class="list-item delete-preview">
  <div>
    <div><strong>{{ transaction.description }}</strong></div>
    <div class="meta">{{ transaction.date }} / {{ transaction.account.name }} / ...</div>
  </div>
  <strong>{{ transaction.amount|yen }}</strong>
</div>

<form hx-post="{{ delete_action }}" hx-target="#form-panel" hx-swap="innerHTML">
  <button class="btn btn--danger" type="submit">削除する</button>
  <button class="btn btn--ghost" type="button" hx-get="{{ cancel_url }}" ...>戻る</button>
</form>
```

- 削除対象の取引内容をプレビュー表示
- 「削除する」ボタンで実際の削除を実行
- 「戻る」ボタンでフォームパネルを元に戻す（HTMX でキャンセル）

### partials/account_list.html — 口座管理

```html
{% for acct in accounts %}
  {% if edit_account_pk == acct.pk %}
    <!-- 編集モード: インライン編集フォームを表示 -->
    <tr>
      <td colspan="4">
        {% include 'ledger/partials/account_form.html' ... %}
      </td>
    </tr>
  {% else %}
    <!-- 表示モード: 口座情報を表示 -->
    <tr class="{% if not acct.is_active %}row--inactive{% endif %}">
      <td><strong>{{ acct.name }}</strong></td>
      <td>{{ acct.opening_balance|yen }}</td>
      <td>{% if acct.is_active %}<span class="chip chip--income">有効</span>{% endif %}</td>
      <td>
        <button ... hx-get="{% url 'ledger:account_update' acct.pk %}">編集</button>
        <button ... hx-post="{% url 'ledger:account_toggle' acct.pk %}">
          {% if acct.is_active %}無効にする{% else %}有効にする{% endif %}
        </button>
      </td>
    </tr>
  {% endif %}
{% endfor %}
```

- 一覧と編集フォームが同じテーブル内でインライン切替
- 編集ボタンを押すと、その行がフォームに変わる（ページ遷移なし）
- 無効な口座は `row--inactive` クラスで半透明表示
- 一覧行には「編集」と「無効／有効切替」のみを置き、削除は編集フォーム内の「削除」ボタンから行う（カテゴリ側も同じ方針）

### partials/category_options.html — カテゴリ動的選択肢

```html
<option value="">---------</option>
{% for category in categories %}
  <option value="{{ category.pk }}">{{ category.name }}</option>
{% endfor %}
```

- HTMX から呼ばれ、`<select>` の中身（`<option>` タグ群）を返す
- 種別を変更するたびに、このテンプレートが呼ばれてカテゴリ選択肢が差し替わる

---

## 7. スタイルシート（static/css/style.css）

**役割:** アプリケーション全体のデザイン・レイアウト・レスポンシブ対応を定義。

### CSS変数（デザイントークン）

```css
:root {
  --bg: #f6f7fb;           /* ページ全体の背景色 */
  --panel: #ffffff;        /* カード・パネルの背景色 */
  --line: #e3e7ef;         /* ボーダー（区切り線）の色 */
  --text: #1f2937;         /* メインのテキスト色 */
  --muted: #6b7280;        /* 補助テキスト・ラベルの色 */
  --primary: #2563eb;      /* メインの強調色（青）*/
  --primary-soft: #dbeafe; /* 青の薄い版（フォーカス時など）*/
  --success: #166534;      /* 成功・収入を示す色（緑）*/
  --success-soft: #dcfce7; /* 緑の薄い版（収入カードの背景）*/
  --danger: #b91c1c;       /* 警告・支出を示す色（赤）*/
  --danger-soft: #fee2e2;  /* 赤の薄い版（支出カードの背景）*/
  --warning-soft: #fef3c7; /* 注意を示す色（黄）*/
  --shadow: 0 10px 30px rgba(15, 23, 42, 0.08);  /* パネルの影 */
  --radius: 18px;          /* 角丸の大きさ */
}
```

### 主要コンポーネント

| コンポーネント | クラス名 | 説明 |
|---------------|---------|------|
| レイアウト | `.layout` | PC:2カラム、タブレット:1カラム のグリッド |
| パネル | `.panel` | 白いカード型のコンテナ。影と角丸 |
| サマリーカード | `.cards`, `.card` | 収入・支出・差額の3枚カード |
| ボタン | `.btn` | 基本ボタン。`--primary`, `--danger`, `--ghost` の3バリエーション |
| フォーム入力 | `.form-input` | テキスト入力、セレクト等の共通スタイル |
| テーブル | `.table-wrap`, `table` | スクロール可能なテーブル |
| チップ | `.chip` | カテゴリの種別（収入/支出）を示すバッジ |
| フラッシュ | `.flash__message` | 4秒で自動消滅するメッセージ |
| フィルター | `.filter-bar` | 検索・絞り込みフォーム |
| グラフ | `.chart-container` | Chart.js の描画領域（高さ固定280px）|

### レスポンシブブレークポイント

```
981px以上（PC）
  → 2カラムレイアウト、カード3列並び

980px以下（タブレット）
  → 1カラム化、カード1列、ボタンサイズ拡大（min-height:44px）
  → フィルターバーを縦配置
  → テーブルに最小幅480px設定（横スクロール可能）

768px以下（スマートフォン）
  → ヘッダーを縦配置、余白をさらに縮小
  → カード・テーブルのフォントサイズ縮小
  → グラフの高さを200pxに
```

---

## 8. 管理画面（ledger/admin.py）

**役割:** Django 標準の管理画面（/admin/）をカスタマイズして、
データを直接操作しやすくする。

```python
@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'opening_balance', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name',)
```

- `@admin.register(Account)`: Account モデルを管理画面に登録
- `list_display`: 一覧画面で表示する列（口座名、初期残高、有効フラグ、更新日時）
- `list_filter`: サイドバーに絞り込みフィルターを表示（有効/無効で絞り込み）
- `search_fields`: 検索バーで口座名を検索可能にする

```python
@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('date', 'description', 'account', 'category', 'amount')
    list_filter = ('category__kind', 'account', 'category', 'date')
    search_fields = ('description', 'memo')
    autocomplete_fields = ('account', 'category')
    date_hierarchy = 'date'
```

- `category__kind`: 外部キーを辿ってカテゴリの種別でフィルターできる
- `autocomplete_fields`: 口座・カテゴリを文字入力で検索して選択できるUI
- `date_hierarchy`: 管理画面の上部に年 → 月 → 日のナビゲーションを追加

---

## 9. テンプレートフィルター（templatetags/ledger_extras.py）

**役割:** テンプレート内で使えるカスタムフィルターを提供。
金額を日本円表記にフォーマットする。

```python
from django import template

register = template.Library()

@register.filter
def yen(value):
    if value in (None, ''):
        return '¥0'
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return value
    return f'¥{amount:,}'
```

**使用例（テンプレート内）:**
```html
{% load ledger_extras %}
{{ income|yen }}        → ¥250,000
{{ expense|yen }}       → ¥180,000
{{ 0|yen }}             → ¥0
{{ None|yen }}          → ¥0
```

**エラーハンドリングの意図:**
- `None` や空文字 → `¥0` を返す（テンプレートが壊れない）
- 数値に変換できない値 → そのまま返す（最低限の表示を維持）
- テンプレートフィルターでエラーが発生すると画面全体が壊れるため、防御的に書かれている

---

## 10. 管理コマンド（management/commands/seed_budget_data.py）

**役割:** アプリの初期設定として、よく使う口座とカテゴリをデータベースに投入する。

```python
class Command(BaseCommand):
    help = '家計簿アプリ向けの初期口座・カテゴリを投入します。'

    def handle(self, *args, **options):
        accounts = ['現金', '普通預金']
        income_categories = ['給与', '副収入', '臨時収入']
        expense_categories = ['食費', '日用品', '住居費', '水道光熱費',
                              '通信費', '交通費', '医療費', '娯楽費', '教育費', '雑費']

        for name in accounts:
            Account.objects.get_or_create(name=name)

        for name in income_categories:
            Category.objects.get_or_create(name=name, defaults={'kind': Category.Kind.INCOME})

        for name in expense_categories:
            Category.objects.get_or_create(name=name, defaults={'kind': Category.Kind.EXPENSE})

        self.stdout.write(self.style.SUCCESS('初期データの投入が完了しました。'))
```

**実行方法:**
```bash
python manage.py seed_budget_data
```

**`get_or_create` の動作:**
- 引数の条件（`name=name`）に一致するデータがあれば → 何もしない（取得のみ）
- 一致するデータがなければ → `defaults` の値も含めて新規作成
- 何度実行しても重複データが作られない（**冪等性**がある）

**`defaults` パラメータ:**
- 検索条件には含めず、新規作成時にだけ使われる値
- 例: `name='給与'` で検索し、なければ `kind='income'` を付けて作成

---

## 11. マイグレーション（migrations/）

**役割:** データベースの構造変更を記録・管理するバージョン管理システム。

### 0001_initial.py — 初回マイグレーション

**作成されるテーブル:**
- Account（口座）: `opening_balance` は `DecimalField(max_digits=12, decimal_places=2)`
- Category（カテゴリ）: `kind` に `choices=[('income', '収入'), ('expense', '支出')]`
- Transaction（取引）: `amount` は `DecimalField(max_digits=12, decimal_places=2)`

### 0002_integer_amounts.py — 金額フィールドの型変更

```python
operations = [
    migrations.AlterField(
        model_name="account",
        name="opening_balance",
        field=models.IntegerField(default=0, validators=[MinValueValidator(0)]),
    ),
    migrations.AlterField(
        model_name="transaction",
        name="amount",
        field=models.IntegerField(validators=[MinValueValidator(1)]),
    ),
]
```

**変更内容:**
- `DecimalField` → `IntegerField` への変更
- 理由: 日本円に小数は不要。整数型にすることで計算精度の問題を回避

---

## 12. アプリ設定（ledger/apps.py）

```python
class LedgerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ledger'
    verbose_name = '家計簿'
```

- `default_auto_field`: 自動生成される主キー（ID）の型を `BigAutoField`（8バイト整数）に設定
- `name`: Django がこのアプリを認識するための名前
- `verbose_name`: 管理画面で表示されるアプリの日本語名

---

## 13. エントリポイント（manage.py, wsgi.py, asgi.py）

### manage.py

```python
#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
```

- Django の管理コマンドを実行するための入口
- `python manage.py runserver`, `python manage.py migrate` 等のコマンドはこのファイルを通して実行される
- `DJANGO_SETTINGS_MODULE` で設定ファイルの場所を指定

---

## 14. 依存関係（requirements.txt）

```
Django>=5.2,<5.3
django-axes>=7.0,<8
django-htmx>=1.27,<1.28
python-dotenv>=1.1,<2
whitenoise>=6.7,<7
```

| パッケージ | バージョン制約 | 用途 |
|-----------|--------------|------|
| Django | 5.2.x | Web フレームワーク本体 |
| django-axes | 7.x | ログイン試行回数制限（ブルートフォース防御） |
| django-htmx | 1.27.x | HTMX リクエストの判定支援 |
| python-dotenv | 1.x | `.env` ファイルの読み込み |
| whitenoise | 6.7.x | 静的ファイルの効率配信 |

**バージョン制約の読み方:**
- `>=5.2,<5.3` → 5.2.0 以上 5.3.0 未満（5.2.x の最新パッチを使用）
- マイナーバージョンを固定することで、互換性を壊す変更を避けつつバグ修正は受け取れる