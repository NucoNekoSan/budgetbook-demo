# Windows 未署名版インストール手順

この手順は、BudgetBook の無料公開 Windows 未署名版を利用する一般ユーザー向けです。

## インストール前に確認すること

次の条件をすべて満たす場合だけ、未署名版の利用を検討してください。

- インストーラーを公式 GitHub Release からダウンロードした: <https://github.com/NucoNekoSan/budgetbook-demo/releases>
- Release に Windows インストーラーが未署名であることが明記されている
- ダウンロードしたインストーラーの SHA256 が、添付された `.sha256` ファイルと一致している
- Windows の「発行元不明」、SmartScreen、ブラウザ、ウイルス対策ソフトの警告が出る可能性を理解している

警告が想定外の場合、SHA256 が一致しない場合、または警告に不安がある場合は、インストールしないでください。

Windows SmartScreen、評価ベースの保護、ウイルス対策、ブラウザのダウンロード保護、その他のOS保護機能を全体的に無効化することは推奨しません。

## ダウンロードするファイル

同じ GitHub Release から次のファイルをダウンロードしてください。

- `BudgetBook-Setup-0.1.0-rc.1-Windows-x64.exe`
- `BudgetBook-Setup-0.1.0-rc.1-Windows-x64.exe.sha256`
- `BudgetBook-0.1.0-rc.1-Windows-x64.manifest.json`

通常利用では JSON manifest は必須ではありませんが、artifact のサイズ、SHA256、platform、version、署名有無を記録しています。

今後の Release で version が変わった場合は、その Release に添付されているファイル名に読み替えてください。

## SHA256 を確認する

ダウンロードしたファイルがあるフォルダーで PowerShell を開き、次を実行します。

```powershell
Get-FileHash .\BudgetBook-Setup-0.1.0-rc.1-Windows-x64.exe -Algorithm SHA256
Get-Content .\BudgetBook-Setup-0.1.0-rc.1-Windows-x64.exe.sha256
```

2つのハッシュ値が完全に一致している必要があります。英字の大文字・小文字の違いは無視して構いません。

`v0.1.0-rc.1` の期待値は次の通りです。

```text
b1743e59079fad39e5b16c4409c482ae4a4794d45dbc857a99561718eac853a2
```

## インストールする

`BudgetBook-Setup-0.1.0-rc.1-Windows-x64.exe` を実行します。

このbuildは未署名のため、Windows またはセキュリティソフトが「発行元不明」や「一般的にダウンロードされていないアプリ」等の警告を表示する場合があります。続行を判断する前に、GitHub Release の配付元と SHA256 を再確認してください。警告の意味が分からない場合は、インストールを中止してください。

## 初回起動

インストール後、スタートメニューまたはインストーラー完了画面から BudgetBook を起動します。

BudgetBook は `127.0.0.1` にだけ bind するローカルサーバーを起動し、ブラウザを開きます。アプリをインターネットへ公開する動作は行いません。

初回起動時の動作:

1. `%APPDATA%\BudgetBook` に runtime file を作成する
2. ローカル SQLite database を作成する
3. 初回セットアップ画面を開く
4. 利用者自身が最初の管理者ユーザーを作成する

インストーラーには、ユーザー、家計データ、デモデータ、`.env`、database は同梱されません。

## データ保存場所

BudgetBook の runtime data は次の場所に保存されます。

```text
%APPDATA%\BudgetBook
```

このフォルダーには、生成された `.env`、ローカル SQLite database、関連 runtime file が保存されます。

## アンインストール時の動作

BudgetBook をアンインストールすると、インストールされたアプリ本体は削除されます。

ただし、家計データの誤削除を防ぐため、`%APPDATA%\BudgetBook` は意図的に残ります。

すべてのローカルデータも削除したい場合は、必要なデータを先にバックアップし、BudgetBook をアンインストールした後で `%APPDATA%\BudgetBook` を手動削除してください。

## トラブルシューティング

- ブラウザが開かない: スタートメニューから BudgetBook を再起動し、既に BudgetBook のwindowまたはprocessが起動していないか確認してください
- セットアップ画面が再表示される: 現在のruntime databaseにユーザーが存在しません。想定した Windows user account と `%APPDATA%\BudgetBook` を使っているか確認してください
- セキュリティ警告が出る: 公式 GitHub Release から取得したことと SHA256 を再確認してください。不安があればインストールしないでください
- SHA256 が一致しない: ダウンロードしたファイルを削除し、インストールしないでください

## セキュリティ参考情報

Microsoft の Windows app/browser reputation protection 説明:

<https://support.microsoft.com/windows/app-browser-control-in-the-windows-security-app-8f68fb65-ebb4-3cfb-4bd7-ef0f376f3dc3>

BudgetBook の未署名配付方針:

[UNSIGNED_SELF_RISK_DISTRIBUTION.md](UNSIGNED_SELF_RISK_DISTRIBUTION.md)
