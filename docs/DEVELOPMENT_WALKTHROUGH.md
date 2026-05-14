

# BudgetBook 開発手順ガイド — 初学者向け完全解説

## はじめに

このドキュメントでは、BudgetBook（家計簿Webアプリ）がどのような手順で開発されたかを、
プログラミング初学者にもわかるように解説します。

BudgetBook は**Django（ジャンゴ）**という Python の Web フレームワークで作られた、
収入と支出を記録・管理するための家計簿アプリケーションです。

---

## 使っている技術（技術スタック）

| 技術 | 役割 | 初学者向け説明 |
|------|------|---------------|
| **Python** | プログラミング言語 | アプリの「頭脳」を書く言語。読みやすさが特徴 |
| **Django 5.2** | Web フレームワーク | Web アプリを効率よく作るための「骨組みキット」。ログイン機能やデータベース操作を最初から備えている |
| **SQLite** | データベース | データを保存する「倉庫」。ファイル1つ（db.sqlite3）で動く手軽さが魅力 |
| **HTMX** | フロントエンド | ページ全体を再読み込みせずに一部だけ更新する技術。JavaScript をほぼ書かずに動的なUIを実現 |
| **Chart.js** | グラフ描画 | 棒グラフや折れ線グラフをブラウザに描くライブラリ |
| **WhiteNoise** | 静的ファイル配信 | CSS や画像ファイルを本番環境でも効率よくユーザーに届ける仕組み |
| **django-axes** | ログイン保護 | ログイン試行回数を制限し、ブルートフォース攻撃を防ぐ |
| **python-dotenv** | 環境変数管理 | パスワードなどの秘密情報を `.env` ファイルで安全に管理する |

---

## ディレクトリ構成

開発を理解するために、まずファイルの全体像を把握しましょう。

```
budgetbook/                          ← プロジェクトのルートフォルダ
├── .env                             ← 秘密情報（SECRET_KEY等）を保存するファイル
├── .env.example                     ← .env のテンプレート（本体はGitに載せない）
│
├── budgetbook/                      ← Django プロジェクト本体
│   ├── manage.py                    ← Django の管理コマンドを実行するファイル
│   ├── requirements.txt             ← 必要なライブラリ一覧
│   ├── db.sqlite3                   ← データベースファイル（自動生成）
│   │
│   ├── config/                      ← プロジェクト設定フォルダ（建物の管理室）
│   │   ├── __init__.py              ← Python パッケージの印
│   │   ├── settings.py              ← 全体の設定（DB接続、言語、タイムゾーン等）
│   │   ├── urls.py                  ← 「どのURLで何を表示するか」のルート定義
│   │   ├── wsgi.py                  ← 本番サーバー用の接続口（同期）
│   │   └── asgi.py                  ← 本番サーバー用の接続口（非同期）
│   │
│   ├── ledger/                      ← 家計簿アプリ本体（機能を実装する部屋）
│   │   ├── apps.py                  ← アプリの基本設定
│   │   ├── models.py                ← データ構造の定義（設計図）
│   │   ├── views.py                 ← 画面表示とビジネスロジック（頭脳）
│   │   ├── forms.py                 ← 入力フォームの定義と検証
│   │   ├── urls.py                  ← アプリ内のURL設計
│   │   ├── admin.py                 ← 管理画面のカスタマイズ
│   │   ├── templatetags/
│   │   │   └── ledger_extras.py     ← テンプレート用カスタムフィルター（¥表示）
│   │   ├── management/commands/
│   │   │   └── seed_budget_data.py  ← 初期データ投入コマンド
│   │   ├── migrations/              ← データベース変更の履歴
│   │   │   ├── 0001_initial.py      ← 初回：テーブル作成
│   │   │   └── 0002_integer_amounts.py ← 金額を整数型に変更
│   │   └── tests/                   ← 自動テスト
│   │       ├── test_views.py
│   │       ├── test_forms.py
│   │       ├── test_auth.py
│   │       ├── test_annual.py
│   │       └── test_settings.py
│   │
│   ├── templates/                   ← HTML テンプレート（画面の見た目）
│   │   ├── base.html                ← 全ページ共通の骨格
│   │   ├── registration/
│   │   │   └── login.html           ← ログイン画面
│   │   └── ledger/
│   │       ├── dashboard.html       ← メインの家計簿画面
│   │       ├── annual.html          ← 年間サマリー画面
│   │       ├── expense_breakdown.html ← 支出構成画面
│   │       ├── settings.html        ← 設定画面
│   │       └── partials/            ← 部品テンプレート（HTMX で部分更新用）
│   │           ├── dashboard_content.html
│   │           ├── transaction_form_panel.html
│   │           ├── transaction_bundle.html
│   │           ├── transaction_delete_confirm.html
│   │           ├── account_list.html
│   │           ├── account_form.html
│   │           ├── category_list.html
│   │           ├── category_form.html
│   │           └── category_options.html
│   │
│   └── static/
│       ├── css/
│       │   └── style.css            ← デザイン（スタイルシート）
│       ├── js/                      ← チャート初期化スクリプト（外部ファイル化済み）
│       │   ├── budget_chart.js      ← Y軸設定等の共通ヘルパー
│       │   ├── dashboard_chart.js   ← ダッシュボード日別推移チャート
│       │   ├── annual_chart.js      ← 年間推移チャート
│       │   └── expense_chart.js     ← 支出構成ドーナツチャート
│       └── vendor/
│           └── chart.umd.min.js     ← Chart.js v4.5.1（ローカル配置）
```

> **ポイント**: Django は「プロジェクト（config/）」の中に「アプリ（ledger/）」を作る構造です。
> プロジェクトは建物全体、アプリはその中の「部屋」と考えるとわかりやすいでしょう。

---

## 開発ステップ — 順を追った解説

### ステップ 1: プロジェクトの土台を作る

#### 1-1. 仮想環境の作成

```bash
python -m venv .venv          # 仮想環境を作る
.venv\Scripts\activate        # 仮想環境を有効化（Windows）
```

**なぜ仮想環境を使うのか？**

仮想環境とは「このプロジェクト専用のPython環境」のことです。
パソコンに直接ライブラリを入れると、他のプロジェクトと干渉することがあります。
仮想環境を使えば、プロジェクトごとに独立した環境が持てます。

#### 1-2. ライブラリのインストール

```bash
pip install Django django-axes django-htmx python-dotenv whitenoise
```

インストールするライブラリは `requirements.txt` に記録しておきます：

```
Django>=5.2,<5.3
django-axes>=7.0,<8
django-htmx>=1.27,<1.28
python-dotenv>=1.1,<2
whitenoise>=6.7,<7
```

**バージョン指定のルール:**
- `>=5.2,<5.3` は「5.2以上、5.3未満」を意味します
- こうすることで、メジャーアップデートによる破壊的変更を防ぎつつ、バグ修正は受け取れます

#### 1-3. Django プロジェクトの作成

```bash
django-admin startproject config .   # プロジェクトを作成（設定フォルダ名を config に）
python manage.py startapp ledger     # 家計簿アプリを作成
```

**`config` という名前について:**
Django のデフォルトではプロジェクト名がそのまま設定フォルダ名になりますが、
`config` にリネームするのは実務でよくあるパターンです。
「設定ファイルが入っている場所」であることが名前から明確になります。

#### 1-4. 環境変数の設定（.env ファイル）

```bash
# .env.example をコピーして .env を作る
cp .env.example .env
```

`.env` ファイルには以下のような秘密情報を書きます：

```
SECRET_KEY=ランダムな秘密の文字列
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
```

**なぜ .env ファイルを使うのか？**
- `SECRET_KEY`（暗号化のカギ）をソースコードに直書きすると、GitHubに公開したとき漏洩します
- `.env` はGitの管理対象から外す（`.gitignore` に追加）ので安全です
- 開発環境と本番環境で違う値を使い分けられます

---

### ステップ 2: データベースの設計（models.py）

**これがアプリの最も重要な部分です。**「何のデータを、どう保存するか」を決めます。

#### 設計の考え方

家計簿に必要なデータを整理すると：

1. **口座（Account）**: お金を管理する場所（現金、銀行口座など）
2. **カテゴリ（Category）**: 取引の分類（食費、給与など）
3. **取引（Transaction）**: 実際の収入・支出の記録

この3つのモデル（データの設計図）を作ります。

#### 共通の親モデル：TimeStampedModel

```python
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField('作成日時', auto_now_add=True)
    updated_at = models.DateTimeField('更新日時', auto_now=True)

    class Meta:
        abstract = True
```

**解説:**
- `auto_now_add=True` → データが作られた瞬間の日時を自動記録
- `auto_now=True` → データが更新されるたびに日時を自動更新
- `abstract = True` → このモデル自体はデータベースのテーブルにならない「設計の雛形」
- 3つのモデル全てがこれを継承することで、作成日・更新日のコードを重複して書かずに済む（**DRY原則**）

#### Account（口座）モデル

```python
class Account(TimeStampedModel):
    name = models.CharField('口座名', max_length=100, unique=True)
    opening_balance = models.IntegerField('初期残高', default=0,
                                          validators=[MinValueValidator(0)])
    is_active = models.BooleanField('有効', default=True)
    notes = models.TextField('メモ', blank=True)
```

**各フィールドの意味:**
- `name`: 口座の名前。`unique=True` で同名の口座は作れない
- `opening_balance`: 使い始めの残高。マイナスにはできない（`MinValueValidator(0)`）
- `is_active`: 口座を使わなくなったとき、削除せず「無効」にするためのフラグ
- `notes`: 任意のメモ。`blank=True` なので空でもOK

**設計のポイント — ソフトデリート:**
口座を削除すると、その口座に紐づく過去の取引データが壊れます。
代わりに `is_active=False` にして「見えなくする」設計を採用しています。
これを**ソフトデリート**と呼びます。

#### Category（カテゴリ）モデル

```python
class Category(TimeStampedModel):
    class Kind(models.TextChoices):
        INCOME = 'income', '収入'
        EXPENSE = 'expense', '支出'

    name = models.CharField('カテゴリ名', max_length=100, unique=True)
    kind = models.CharField('区分', max_length=10, choices=Kind.choices)
    is_active = models.BooleanField('有効', default=True)
    notes = models.TextField('メモ', blank=True)
```

**解説:**
- `TextChoices` → 選択肢を定義するクラス。`kind` は 'income' か 'expense' のどちらかしか入らない
- これにより「給与」は収入、「食費」は支出と明確に区別される
- 一度作ったカテゴリの `kind` は変更できない設計（後述の forms.py で制御）

#### Transaction（取引）モデル

```python
class Transaction(TimeStampedModel):
    date = models.DateField('日付')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, verbose_name='口座')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, verbose_name='カテゴリ')
    amount = models.IntegerField('金額', validators=[MinValueValidator(1)])
    description = models.CharField('摘要', max_length=120)
    memo = models.TextField('メモ', blank=True)

    class Meta:
        ordering = ['-date', '-id']  # 新しい取引から表示
```

**重要な概念 — ForeignKey（外部キー）:**
- `ForeignKey` は「このデータは別のテーブルの特定のデータと繋がっている」という関係を表します
- 取引は必ず1つの口座と1つのカテゴリに紐づきます
- `on_delete=models.PROTECT` → 取引で使われている口座やカテゴリを削除しようとするとエラーになる安全装置

**なぜ IntegerField（整数型）なのか？:**
- 日本円には「銭」がないので小数は不要
- 最初は `DecimalField`（小数対応）で作りましたが、マイグレーション0002で `IntegerField` に修正
- 整数型の方が計算が速く、浮動小数点の丸め誤差も起きない

**ordering について:**
- `['-date', '-id']` はデータの並び順を指定
- `-` は降順（大きい方から）を意味
- 日付が新しいものから表示し、同じ日付なら後から登録したものが先に来る

---

### ステップ 3: マイグレーション（データベースへの反映）

モデルを定義しただけではデータベースは変わりません。
マイグレーションで設計をデータベースに反映します。

```bash
python manage.py makemigrations    # 変更内容をマイグレーションファイルに記録
python manage.py migrate           # データベースに反映
```

**マイグレーションの履歴:**

| ファイル | 内容 | 解説 |
|---------|------|------|
| `0001_initial.py` | Account, Category, Transaction を作成 | 金額は `DecimalField`（小数2桁）で作成。最初の設計 |
| `0002_integer_amounts.py` | 金額を `IntegerField` に変更 | 日本円に小数は不要と気づいて修正。開発初期の設計見直しは自然なこと |

**マイグレーションとは何か？**
- データベースの「変更履歴」です
- Git がコードの変更履歴を残すように、マイグレーションは DB 構造の変更履歴を残します
- チーム開発では、他のメンバーがこのファイルを実行するだけで同じ DB 構造を再現できます

---

### ステップ 4: 設定ファイルの構成（settings.py）

Django の動作を決める中央設定ファイルです。

#### セキュリティ設定

```python
SECRET_KEY = _require_env('SECRET_KEY')        # 暗号化キー（.envから取得）
DEBUG = os.environ.get('DEBUG', 'False')...     # デバッグモード（本番ではFalse必須）
ALLOWED_HOSTS = [...]                           # アクセス許可するホスト名
```

**`_require_env()` 関数の工夫:**
```python
def _require_env(key: str) -> str:
    value = os.environ.get(key, _MISSING)
    if value is _MISSING:
        raise RuntimeError(f'環境変数 {key} が設定されていません。...')
    return value
```
- 必須の環境変数が未設定なら、わかりやすいエラーメッセージで止まる
- 「なぜか動かない」という問題の原因特定が容易になる

#### 登録するアプリとミドルウェア

```python
INSTALLED_APPS = [
    'django.contrib.admin',        # 管理画面
    'django.contrib.auth',         # ログイン認証
    'django.contrib.contenttypes', # コンテンツタイプ管理
    'django.contrib.sessions',     # セッション管理
    'django.contrib.messages',     # メッセージ表示
    'django.contrib.staticfiles',  # 静的ファイル管理
    'django_htmx',                 # HTMX 連携
    'ledger',                      # 家計簿アプリ
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',       # セキュリティチェック
    'whitenoise.middleware.WhiteNoiseMiddleware',           # 静的ファイル配信
    # ... 省略 ...
    'django_htmx.middleware.HtmxMiddleware',               # HTMX リクエスト判定
]
```

**ミドルウェアとは？**
- リクエスト（ブラウザからの要求）とレスポンス（サーバーからの応答）の間に挟まる「処理の関所」
- セキュリティチェック、セッション管理、CSRF防御などを自動的に行ってくれる

#### 日本語・タイムゾーン設定

```python
LANGUAGE_CODE = 'ja'              # 管理画面やエラーメッセージが日本語に
TIME_ZONE = 'Asia/Tokyo'          # 日本時間
USE_TZ = True                     # タイムゾーンを意識した時刻管理
```

#### Cookie のセキュリティ設定

```python
CSRF_COOKIE_HTTPONLY = False       # HTMXからCSRFトークンを読み取るためFalse
SESSION_COOKIE_HTTPONLY = True     # セッションCookieはJSからアクセス不可（安全）
SESSION_COOKIE_SAMESITE = 'Lax'   # 他サイトからのリクエストではCookieを送らない
CSRF_COOKIE_SAMESITE = 'Lax'      # CSRF Cookieも同様
```

---

### ステップ 5: URL 設計（urls.py）

「どの URL にアクセスしたら、何が表示されるか」を定義します。

#### ルート URL（config/urls.py）

```python
urlpatterns = [
    path('admin/', admin.site.urls),                 # /admin/ → Django管理画面
    path('accounts/login/', LoginView.as_view(...)),  # /accounts/login/ → ログイン画面
    path('accounts/logout/', LogoutView.as_view()),   # /accounts/logout/ → ログアウト処理
    path('', include('ledger.urls')),                 # それ以外 → 家計簿アプリへ
]
```

**`include()` の役割:**
- ledger アプリのURLをまとめて読み込む
- URL定義を分割管理できるので、プロジェクトが大きくなっても整理しやすい

#### アプリ URL（ledger/urls.py）

```python
app_name = 'ledger'   # 名前空間。テンプレートで {% url 'ledger:dashboard' %} と書ける

urlpatterns = [
    # --- メイン画面 ---
    path('', views.dashboard, name='dashboard'),                    # トップページ = ダッシュボード
    path('categories/options/', views.category_options, ...),       # カテゴリ動的取得（HTMX用）

    # --- 取引の操作 ---
    path('transactions/export/', views.transaction_export, ...),    # CSV ダウンロード
    path('transactions/new/', views.transaction_create, ...),       # 新規登録
    path('transactions/<int:pk>/edit/', views.transaction_update, ...),   # 編集
    path('transactions/<int:pk>/delete/', views.transaction_delete, ...), # 削除

    # --- 年間サマリー ---
    path('annual/', views.annual, name='annual'),

    # --- 設定画面（口座・カテゴリ管理） ---
    path('settings/', views.settings_page, name='settings'),
    path('settings/accounts/new/', views.account_create, ...),
    path('settings/accounts/<int:pk>/edit/', views.account_update, ...),
    path('settings/accounts/<int:pk>/toggle/', views.account_toggle, ...),
    path('settings/categories/new/', views.category_create, ...),
    path('settings/categories/<int:pk>/edit/', views.category_update, ...),
    path('settings/categories/<int:pk>/toggle/', views.category_toggle, ...),
]
```

**URL設計のポイント:**
- `<int:pk>` は「整数の主キー（ID）」を受け取る部分。`transactions/3/edit/` なら「ID=3の取引を編集」
- `app_name = 'ledger'` により名前空間を設定。テンプレートやビューで `ledger:dashboard` のように参照できる
- RESTful な設計思想に沿っており、URL を見ただけで「何をするページか」がわかる

---

### ステップ 6: フォームの定義（forms.py）

ユーザーからの入力を受け取り、検証するための仕組みです。

#### TransactionForm（取引フォーム）

```python
class TransactionForm(forms.ModelForm):
    kind = forms.ChoiceField(
        choices=Category.Kind.choices,
        label='種別',
        widget=forms.Select(attrs={
            'hx-get': reverse_lazy('ledger:category_options'),
            'hx-target': '#id_category',
            'hx-swap': 'innerHTML',
            'hx-trigger': 'change',
        }),
    )
```

**HTMX連携の仕組み:**
1. ユーザーが「種別」を「収入」から「支出」に変更する
2. `hx-trigger="change"` → 変更を検知
3. `hx-get` → サーバーに「支出カテゴリの一覧をください」とリクエスト
4. `hx-target="#id_category"` → 返ってきた選択肢でカテゴリのドロップダウンを更新
5. `hx-swap="innerHTML"` → ドロップダウンの中身を差し替える

これにより、ページを再読み込みせずにカテゴリの選択肢が動的に変わります。

**バリデーション（入力チェック）:**
```python
def clean(self):
    kind = cleaned.get('kind')
    category = cleaned.get('category')
    if kind and category and category.kind != kind:
        raise forms.ValidationError(
            '種別とカテゴリが一致しません。種別を変更したときはカテゴリを再選択してください。'
        )
```
- 「支出」を選んだのに「給与」（収入カテゴリ）を選ぶような矛盾を防ぐ
- サーバー側でも必ず検証する（ブラウザの検証だけでは改ざんを防げない）

#### AccountForm（口座フォーム）

```python
class AccountForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['opening_balance'].widget.attrs['readonly'] = True
```

**初期残高が編集後は変更不可な理由:**
- 初期残高は残高計算の基準点。後から変えると過去の残高がすべて狂う
- `clean_opening_balance()` でサーバー側でも元の値を返すようにしている（ブラウザの readonly は信頼しない）

#### CategoryForm（カテゴリフォーム）

```python
def __init__(self, *args, **kwargs):
    if self.instance and self.instance.pk:
        self.fields['kind'].widget.attrs['disabled'] = True

def clean_kind(self):
    if self.instance and self.instance.pk:
        return self.instance.kind   # 既存カテゴリは元のkindを保持
    return self.cleaned_data['kind']
```

**区分（kind）が変更不可な理由:**
- 「食費」を支出から収入に変えると、過去の取引データの意味が変わってしまう
- `disabled` でUI上無効化しつつ、`clean_kind()` でサーバー側でも保護する二重防御

---

### ステップ 7: ビュー（views.py）— アプリの中核ロジック

ビューはHTTPリクエストを受け取り、適切なレスポンスを返す「司令塔」です。

#### ヘルパー関数（補助ツール）

```python
def parse_month(month_str):     # "2026-04" → date(2026, 4, 1) に変換
def shift_month(target, offset): # 月を前後に移動（1月の前月→12月も正しく処理）
def month_end(target):           # その月の末日を取得
def clamp_future_month(target):  # 未来の月は今月に制限
def parse_filters(params):       # 検索・フィルター条件を解析
```

**`clamp_future_month` の意義:**
未来の月にはデータがないので、アクセスしても空のページになります。
ユーザーの混乱を防ぐため、未来の月へのアクセスは今月にリダイレクトします。

#### dashboard() — メインのダッシュボード

```python
@login_required
@require_http_methods(['GET'])
def dashboard(request):
    target_month = clamp_future_month(parse_month(request.GET.get('month')))
    context = get_dashboard_context(target_month, page=page, filters=filters)

    if request.htmx:
        return render(request, 'ledger/partials/dashboard_content.html', context)
    return render(request, 'ledger/dashboard.html', context)
```

**ポイント:**
- `@login_required` → ログインしていない人はログインページにリダイレクト
- `request.htmx` → HTMXからのリクエストかどうかを判定
  - HTMX リクエスト → 部品テンプレート（部分更新用）だけ返す
  - 通常リクエスト → ページ全体を返す
- これにより、月の切り替えやフィルター操作でページ全体が再描画されない

**ダッシュボードで表示する情報:**
1. 収入合計・支出合計・差額（3つのサマリーカード）
2. カテゴリ別の支出ランキング（上位8件）
3. 当月の日別収支推移グラフ
4. 口座残高一覧
5. 取引一覧（ページネーション付き、20件ずつ）
6. 検索・フィルター機能

#### transaction_create() — 取引の新規登録

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

**リクエストメソッドの使い分け:**
- `GET` → フォームの表示（「データを見せて」）
- `POST` → データの送信・保存（「データを保存して」）

**HTTP 422 ステータスコード:**
- バリデーションエラー時に 422（Unprocessable Entity）を返す
- HTMX はステータスコードを見て成功/失敗を判断するため

**`render_dashboard_bundle` の仕組み:**
取引の保存後、1回のレスポンスで3か所を同時更新する：
1. フラッシュメッセージ（「保存しました」）
2. ダッシュボードの中身（集計の再計算）
3. フォーム（入力欄をクリア）

これは `hx-swap-oob`（Out of Band swap）という HTMX の高度な機能です。

#### transaction_export() — CSV ダウンロード

```python
response = HttpResponse(content_type='text/csv; charset=utf-8')
response.write('\ufeff')  # UTF-8 BOM
writer = csv.writer(response)
writer.writerow(['日付', '種別', '口座', 'カテゴリ', '金額', '摘要', 'メモ'])
```

**BOM（Byte Order Mark）の重要性:**
- `\ufeff` は「このファイルはUTF-8ですよ」とExcelに伝える印
- これがないと、Excelで日本語が文字化けする
- 小さな配慮ですが、実務では非常に重要

#### annual() — 年間サマリー

12ヶ月分のデータを集計し、年間の収支を一覧表示します。
各月のセルをクリックすると、その月のダッシュボードに飛べる導線設計です。

#### settings 関連のビュー

口座とカテゴリの追加・編集・有効/無効切替を管理します。

**toggle（切替）パターン:**
```python
def account_toggle(request, pk):
    account = get_object_or_404(Account, pk=pk)
    account.is_active = not account.is_active     # True ↔ False を反転
    account.save(update_fields=['is_active'])      # is_active だけを更新（効率的）
```

#### 設定画面の使い方（利用者視点）

口座とカテゴリの管理は画面上部ナビゲーションの「設定」から行います。

- **追加**: 一覧上部の「+ 追加」ボタンを押すと、口座／カテゴリの追加フォームが開きます。
- **編集**: 各行の「編集」ボタンを押すと、一覧の上に編集フォームが表示されます。
- **更新**: 編集フォームの「更新する」を押すと「この口座／カテゴリの内容を更新します。よろしいですか？」の確認ダイアログが表示され、OK で保存、キャンセルで変更を送信せずフォームに戻ります。
- **削除**: 削除は編集フォーム内の「削除」ボタンから行います。確認ダイアログを経てから削除され、関連する取引が登録されている場合は保護のため削除できず、その旨のメッセージが表示されます。
- **無効化／有効化**: 一時的に使わない口座・カテゴリは、一覧各行の「無効にする／有効にする」ボタンで切替できます（データは残したまま非表示にできます）。

---

### ステップ 8: テンプレート（HTML）— 画面の見た目

#### テンプレート継承の仕組み

```
base.html          ← ヘッダー、ナビゲーション、共通スクリプト
  ├── dashboard.html    ← ダッシュボード固有のレイアウト
  ├── annual.html       ← 年間サマリー固有のレイアウト
  ├── settings.html     ← 設定画面固有のレイアウト
  └── login.html        ← ログイン画面（独自のHTMLで、base.htmlを継承しない）
```

**base.html の役割:**
```html
<body hx-headers='{"x-csrftoken": "{{ csrf_token }}"}'>
```
- HTMX の全リクエストにCSRFトークンを自動付与
- CSRF（Cross-Site Request Forgery）攻撃を防ぐセキュリティ対策

#### パーシャル（部品）テンプレート

HTMX で部分更新するために、画面を「部品」に分割しています。

| パーシャル | 役割 |
|-----------|------|
| `dashboard_content.html` | ダッシュボードの中身（カード、グラフ、一覧） |
| `transaction_form_panel.html` | 取引入力/編集フォーム |
| `transaction_bundle.html` | 保存成功時に3か所を同時更新するレスポンス |
| `transaction_delete_confirm.html` | 削除確認画面 |
| `account_list.html` | 口座管理の一覧 |
| `account_form.html` | 口座の追加/編集フォーム |
| `category_list.html` | カテゴリ管理の一覧 |
| `category_form.html` | カテゴリの追加/編集フォーム |
| `category_options.html` | カテゴリ選択肢の動的更新用 |

**`transaction_bundle.html` — HTMX の OOB（Out of Band）更新:**
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
```
- 通常 HTMX は1つのターゲットしか更新できない
- `hx-swap-oob` を使うと、1回のレスポンスで複数の要素を同時に更新できる
- これが BudgetBook の HTMX 活用で最も巧妙な部分

---

### ステップ 9: スタイリング（style.css）

#### CSS 変数（カスタムプロパティ）

```css
:root {
    --bg: #f6f7fb;           /* 背景色 */
    --panel: #ffffff;        /* パネルの背景色 */
    --primary: #2563eb;      /* メインカラー（青） */
    --success: #166534;      /* 収入（緑） */
    --danger: #b91c1c;       /* 支出（赤） */
    --radius: 18px;          /* 角丸の大きさ */
}
```

**CSS変数を使う利点:**
- 色を一箇所で管理。デザイン変更時に1か所直せば全体に反映
- 将来ダークテーマを追加するのも容易（変数の値を切り替えるだけ）

#### レスポンシブデザイン

```css
/* 通常（PC）: 2カラムレイアウト */
.layout {
    display: grid;
    grid-template-columns: minmax(0, 1.8fr) minmax(320px, 0.95fr);
}

/* タブレット（980px以下）: 1カラムに */
@media (max-width: 980px) {
    .layout { grid-template-columns: 1fr; }
    .cards { grid-template-columns: 1fr; }
}

/* スマートフォン（768px以下）: さらに簡素化 */
@media (max-width: 768px) {
    .container { padding: 12px; }
    .card__value { font-size: 1.35rem; }
}
```

**レスポンシブの段階:**
1. **PC（981px以上）**: 左に一覧、右にフォームの2カラム
2. **タブレット（980px以下）**: 1カラムに変更、ボタンサイズ拡大（タッチ操作対応）
3. **スマホ（768px以下）**: 余白縮小、文字サイズ調整

#### フラッシュメッセージのアニメーション

```css
@keyframes flash-fade {
    0%   { opacity: 1; }   /* 表示開始 */
    62%  { opacity: 1; }   /* 2.5秒間は表示し続ける */
    100% { opacity: 0; }   /* フェードアウト */
}
.flash__message {
    animation: flash-fade 4s ease-in-out forwards;
}
```

「取引を保存しました」のようなメッセージが4秒後に自動で消えます。

---

### ステップ 10: 初期データ投入（seed_budget_data.py）

```python
class Command(BaseCommand):
    def handle(self, *args, **options):
        accounts = ['現金', '普通預金']
        income_categories = ['給与', '副収入', '臨時収入']
        expense_categories = ['食費', '日用品', '住居費', '水道光熱費',
                              '通信費', '交通費', '医療費', '娯楽費', '教育費', '雑費']

        for name in accounts:
            Account.objects.get_or_create(name=name)
        # ...
```

**`get_or_create` のポイント:**
- 「存在しなければ作成、存在すれば何もしない」
- 何度実行しても重複データが作られない（**冪等性**）
- 安全に再実行できるのが管理コマンドの鉄則

**実行方法:**
```bash
python manage.py seed_budget_data
```

---

### ステップ 11: カスタムテンプレートフィルター（ledger_extras.py）

```python
@register.filter
def yen(value):
    if value in (None, ''):
        return '¥0'
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return value
    return f'¥{amount:,}'    # 1000 → ¥1,000
```

**使い方（テンプレート内）:**
```html
{{ income|yen }}   →   ¥250,000 のように表示
```

**堅牢なエラーハンドリング:**
- `None` や空文字が来ても `¥0` を返す
- 数値に変換できない値はそのまま返す
- テンプレートでエラーが起きると画面全体が壊れるため、この防御は重要

---

### ステップ 12: 管理画面のカスタマイズ（admin.py）

```python
@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('date', 'description', 'account', 'category', 'amount')
    list_filter = ('category__kind', 'account', 'category', 'date')
    search_fields = ('description', 'memo')
    autocomplete_fields = ('account', 'category')
    date_hierarchy = 'date'
```

**各設定の意味:**
- `list_display`: 一覧で表示する列
- `list_filter`: サイドバーに絞り込みフィルターを追加
- `search_fields`: 検索バーで検索できるフィールド
- `autocomplete_fields`: 口座・カテゴリを入力補完で選択
- `date_hierarchy`: 日付でドリルダウンできるナビゲーション

---

### ステップ 13: 認証（ログイン機能）

Django の組み込み認証機能をそのまま活用しています。

```python
# config/urls.py
path('accounts/login/', LoginView.as_view(
    template_name='registration/login.html',
    redirect_authenticated_user=True,   # ログイン済みならダッシュボードへ
)),

# config/settings.py
LOGIN_URL = '/accounts/login/'          # 未ログイン時のリダイレクト先
LOGIN_REDIRECT_URL = '/'               # ログイン成功後の遷移先
LOGOUT_REDIRECT_URL = '/accounts/login/'  # ログアウト後の遷移先
```

**なぜ自作しないのか？**
- 認証はセキュリティの根幹。自作するとパスワードの保存方法やセッション管理でミスしやすい
- Django の認証は長年の運用実績がありセキュリティが担保されている
- 車輪の再発明をしない判断は正しい

---

### ステップ 14: テスト

85個のテストケースが5つのファイルに分かれています。

| テストファイル | テスト対象 | テスト内容の例 |
|---------------|-----------|---------------|
| `test_views.py` | 画面表示 | ダッシュボード表示、月移動、CSV出力、検索 |
| `test_forms.py` | フォーム検証 | 種別とカテゴリの不一致チェック |
| `test_auth.py` | 認証 | 未ログインでのアクセス拒否 |
| `test_annual.py` | 年間集計 | 年間サマリーの計算精度 |
| `test_settings.py` | 設定画面 | 口座・カテゴリの CRUD 操作 |

**テストの実行:**
```bash
python manage.py test
```

---

## セットアップ手順のまとめ

```bash
# 1. 仮想環境の作成と有効化
python -m venv .venv
.venv\Scripts\activate              # Windows
# source .venv/bin/activate         # Mac/Linux

# 2. ライブラリのインストール
pip install -r requirements.txt

# 3. 環境変数の設定
cp .env.example .env
# .env を編集して SECRET_KEY を設定

# 4. データベースの作成
python manage.py migrate

# 5. 初期データの投入
python manage.py seed_budget_data

# 6. 管理ユーザーの作成
python manage.py createsuperuser

# 7. 開発サーバーの起動
python manage.py runserver

# ブラウザで http://127.0.0.1:8000/ にアクセス
```

---

## 設計上の優れた判断まとめ

| 設計判断 | なぜ良いか |
|----------|-----------|
| 整数で金額管理 | 日本円に小数は不要。浮動小数点の丸め誤差を回避 |
| ソフトデリート（is_active） | データを壊さずに無効化。過去の取引履歴が残る |
| PROTECT 外部キー | 使用中のデータの誤削除を防止 |
| HTMX | JavaScript を最小限に。HTML ベースで SPA 風の操作感 |
| テンプレート部品化 | HTMX による部分更新に必須。再利用性も高い |
| CSS 変数 | デザインの統一性と変更容易性 |
| BOM 付き CSV | Excel 互換性。実務で地味に大事 |
| 環境変数で秘密管理 | SECRET_KEY をコードに直書きしない。セキュリティの基本 |
| Django 組み込み認証 | 車輪の再発明をしない。セキュリティが担保済み |
| バリデーションの二重防御 | UI（disabled/readonly）とサーバー（clean メソッド）の両方でチェック |
