## 概要

<!-- この PR で何が変わるか、1-3 行で -->

## 関連 issue

<!-- 例: Closes #123, Refs #456 -->

## 変更内容

- [ ] ...
- [ ] ...

## テスト

<!-- どう確認したか -->

- [ ] `cd budgetbook && python manage.py test ledger` が pass
- [ ] `python manage.py makemigrations --check` が clean
- [ ] (該当する場合) DB migration の影響を docs/ に記載

## チェックリスト

- [ ] CHANGELOG.md `[Unreleased]` に変更を追記
- [ ] 関連する仕様書 (`docs/specs/`) を更新
- [ ] セキュリティ影響を確認 (秘密情報の混入なし、destructive migration なし)
- [ ] 個人情報 / 実データを含まない (`grep` で確認)

## 補足

<!-- レビュアー向けの注意点、設計判断の理由など -->
