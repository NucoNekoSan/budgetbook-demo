#!/usr/bin/env bash
# audit_docs_sensitive.sh — public demo repo 用、private 由来の機微情報が
# 誤って混入していないか走査する。
#
# 同型版が private repo (budgetbook) にも存在 (scripts/audit_docs_sensitive.sh)。
# private のものは「自分の機微情報を redact できているか」を見るが、
# 本ファイルは「private から demo に流入していないか」を見る用途。

set -euo pipefail

MODE="full"
VERBOSE=0
for arg in "$@"; do
  case "$arg" in
    --staged)  MODE="staged" ;;
    --verbose) VERBOSE=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

# 検出パターン (private repo の同 sweep + demo 由来の漏れパターン)
PATTERNS=(
  # === 実残債値 (private repo に元々存在、demo に流入する可能性) ===
  # 数値系は \b 境界で部分一致 (例: 127506 内の 12750) を防ぐ
  '\b388,?897\b' '\b99,?436\b' '\b298,?171\b' '\b34,?300\b' '\b184,?907\b' '\b1,?005,?711\b'
  '\b11,?161\b' '\b11,?163\b' '\b5,?445\b' '\b1,?243\b' '\b4,?473\b'
  '\b108,?576\b' '\b497,?473\b' '\b112,?406\b' '\b367,?081\b' '\b12,?970\b' '\b68,?910\b'
  # === 実ドメイン / 実 IP / 実 IPv6 ===
  'home\.nuconeko-garden\.com'
  '192\.168\.1\.(37|40)'                 # 実 LAN IP (placeholder の .10/.x.x は許容)
  '240d:18:7:4200'                       # 実 IPv6 prefix
  # === 実銀行名 / 実居住地由来 / 実リボ口座名 ===
  # 注: 本 script ファイルは自己 bypass されているため literal pattern OK
  '北洋銀行' '札幌市'
  'クレカリボ[ABC]'                       # placeholder: クレジットカードA/B/C
  # === 実 email ===
  'isonohideki@' 'risa19841013'
)

# 走査対象
if [[ "$MODE" == "staged" ]]; then
  mapfile -t TARGETS < <(git diff --cached --name-only --diff-filter=ACMR | grep -E '\.(md|py|html|yml|txt)$' | grep -v '\.venv-mirror' || true)
  if [[ ${#TARGETS[@]} -eq 0 ]]; then
    [[ $VERBOSE -eq 1 ]] && echo "[audit] no staged target files"
    exit 0
  fi
else
  mapfile -t TARGETS < <(
    find docs/ -type f \( -name "*.md" -o -name "*.txt" \) 2>/dev/null
    find budgetbook/ -type f \( -name "*.py" -o -name "*.html" \) 2>/dev/null | grep -v '\.venv-mirror' | grep -v '__pycache__'
    ls *.md 2>/dev/null
  )
fi

PATTERN_UNION=$(IFS='|'; echo "${PATTERNS[*]}")

HITS=0
HIT_LINES=""
for f in "${TARGETS[@]}"; do
  [[ ! -f "$f" ]] && continue
  # bypass: 本スクリプト自体 + 禁止語チェックを書く側のコード
  if [[ "$f" == "scripts/audit_docs_sensitive.sh" ]]; then continue; fi
  if [[ "$f" == "budgetbook/ledger/tests/test_demo_mode.py" ]]; then continue; fi
  while IFS= read -r line; do
    HITS=$((HITS + 1))
    HIT_LINES="${HIT_LINES}${line}"$'\n'
  done < <(grep -EHn "$PATTERN_UNION" "$f" 2>/dev/null || true)
done

if [[ $HITS -eq 0 ]]; then
  [[ $VERBOSE -eq 1 ]] && echo "[audit] clean: 機微情報残存ゼロ (走査対象: ${#TARGETS[@]} ファイル / パターン: ${#PATTERNS[@]} 件)"
  exit 0
fi

echo "[audit] 🚨 private 由来の機微情報を検出しました (${HITS} 件):" >&2
echo "" >&2
echo "$HIT_LINES" >&2
echo "" >&2
echo "対応:" >&2
echo "  - demo 用の架空ラウンド値 (¥500,000 / ¥100,000 等) に置換" >&2
echo "  - 実 LAN IP は 192.168.x.x、実ドメインは example.com、実銀行名は 普通預金A 等に" >&2
echo "  - public repo (本 repo) では bypass せず必ず置換する" >&2
exit 1