#!/usr/bin/env bash
#
# model-strategy: コンテキスト量ステータスライン
#
# 現在のコンテキスト使用率を表示し、内訳を確認する判断材料にする。
# 詳細は references/06-context-monitor.md を参照。
#
# 配線 (ユーザー/プロジェクトの settings.json):
#   {
#     "statusLine": {
#       "type": "command",
#       "command": "/absolute/path/to/model-strategy/skills/model-effort-guide/scripts/context-statusline.sh"
#     }
#   }
#
# 警告閾値は環境変数 MODEL_STRATEGY_CTX_WARN (既定 75 = 使用率%) で変更可。
#
set -euo pipefail

warn_at="${MODEL_STRATEGY_CTX_WARN:-75}"
input="$(cat)"

if ! command -v jq >/dev/null 2>&1; then
  printf 'model-strategy statusline: jq が必要です (例: brew install jq)\n'
  exit 0
fi

# タブ区切りで値を取り出す (model 表示名に空白が含まれうるため IFS=tab)
IFS=$'\t' read -r pct used size cost model < <(
  printf '%s' "$input" | jq -r '
    [ (.context_window.used_percentage   // 0)
    , (.context_window.total_input_tokens // 0)
    , (.context_window.context_window_size // 200000)
    , (.cost.total_cost_usd              // 0)
    , (.model.display_name               // "model")
    ] | @tsv'
)

pct_int="${pct%.*}"; pct_int="${pct_int:-0}"
used_k=$(( used / 1000 ))
size_k=$(( size / 1000 ))

# 10 セグメントのバー
filled=$(( pct_int / 10 )); (( filled > 10 )) && filled=10; (( filled < 0 )) && filled=0
empty=$(( 10 - filled ))
bar=""
for ((i=0; i<filled; i++)); do bar+="▓"; done
for ((i=0; i<empty;  i++)); do bar+="░"; done

# 色: 緑 <50% / 黄 50-warn% / 赤 >=warn%。モデルごとのウィンドウに対する使用率。
reset=$'\033[0m'
if (( pct_int >= warn_at )); then
  color=$'\033[31m'; nudge="  ⚠ コンテキスト内訳を確認"
elif (( pct_int >= 50 )); then
  color=$'\033[33m'; nudge=""
else
  color=$'\033[32m'; nudge=""
fi

cost_fmt=$(printf '%.2f' "$cost" 2>/dev/null || echo "$cost")

printf '%s ⊙ ctx %s%s%% %s %dk/%dk  $%s%s%s\n' \
  "$model" "$color" "$pct_int" "$bar" "$used_k" "$size_k" "$cost_fmt" "$nudge" "$reset"
