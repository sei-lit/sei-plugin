#!/usr/bin/env bash
#
# model-strategy: 委譲先 (サブエージェント) 状態ステータスライン
#
# statusLine とは別のトップレベルキー subagentStatusLine 用スクリプト。
# stdin の tasks[] を読み、タスクごとに 1 行の NDJSON
# {"id":"<task id>","content":"<row body>"} を stdout へ出力する。
# 詳細は references/06-context-monitor.md §7 を参照。
#
# 配線 (ユーザー/プロジェクトの settings.json。statusLine と同じくプラグイン実行
# コンテキストの外で動くため ${CLAUDE_PLUGIN_ROOT} は展開されない — 絶対パス必須):
#   {
#     "subagentStatusLine": {
#       "type": "command",
#       "command": "/absolute/path/to/model-strategy/skills/model-effort-guide/scripts/subagent-statusline.sh"
#     }
#   }
#
set -euo pipefail

input="$(cat)"

if ! command -v jq >/dev/null 2>&1; then
  # jq が無い場合は何も出力しない (デフォルト表示のまま。セッションは妨げない)。
  exit 0
fi

columns="$(printf '%s' "$input" | jq -r '(.columns // 80) | floor')"

printf '%s' "$input" | jq -c '.tasks // [] | .[]' | while IFS= read -r task; do
  id="$(printf '%s' "$task" | jq -r '.id // empty')"
  [[ -z "$id" ]] && continue

  # タブ区切りで値を取り出す (name 等に空白が含まれうるため IFS=tab)。
  IFS=$'\t' read -r name status model tokens < <(
    printf '%s' "$task" | jq -r '
      [ (.name // .type // "agent")
      , (.status // "?")
      , (.model // "")
      , (.tokenCount // "")
      ] | @tsv'
  )

  content="$name"
  [[ -n "$model" ]] && content+=" ($model)"
  content+=" $status"
  [[ -n "$tokens" ]] && content+=" ${tokens}tok"

  # columns 幅を超えないよう切り詰める。
  if (( ${#content} > columns )); then
    content="${content:0:columns}"
  fi

  jq -cn --arg id "$id" --arg content "$content" '{id: $id, content: $content}'
done
