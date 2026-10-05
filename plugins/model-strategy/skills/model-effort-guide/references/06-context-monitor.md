# コンテキストと委譲先の状態表示

同梱スクリプトは Claude Code から標準入力で受け取ったJSONを表示する。自動でモデルを変更したり、会話を消去・圧縮したりはしない。

## §1 メインの表示

`scripts/context-statusline.sh` は現在のコンテキスト使用率、入力量、ウィンドウサイズ、提供されたコスト値を1行に表示する。

```text
Claude ⊙ ctx 78% ▓▓▓▓▓▓▓░░░ 156k/200k  $1.92  ⚠ コンテキスト内訳を確認
```

| 表示 | JSON項目 |
| --- | --- |
| 使用率と10区画のバー | `context_window.used_percentage` |
| 入力量 / ウィンドウサイズ | `context_window.total_input_tokens` / `context_window.context_window_size` |
| コスト | `cost.total_cost_usd` |
| モデル名 | `model.display_name` |

使用率が50%未満なら緑、50%以上なら黄、警告閾値以上なら赤で表示する。閾値は `MODEL_STRATEGY_CTX_WARN` で指定し、既定は75%。固定の token 数ではなく、モデルのウィンドウに対する使用率を使う。

現行仕様では `total_input_tokens` は現在の入力コンテキスト量を表し、通常入力・キャッシュ作成・キャッシュ読み取りの合計に相当する。項目の意味と利用可能性は実行中のClaude Codeの仕様を確認する。[公式 statusline 仕様](https://code.claude.com/docs/en/statusline#context-window-fields)（2026-09-10確認）。

## §2 設定

Bash と `jq` が必要。利用するスクリプトの実在する絶対パスを、Claude Code のユーザーまたはプロジェクト設定に指定する。

```json
{
  "statusLine": {
    "type": "command",
    "command": "/absolute/path/to/model-strategy/skills/model-effort-guide/scripts/context-statusline.sh"
  }
}
```

リポジトリのチェックアウトを使う場合は `plugins/model-strategy/skills/model-effort-guide/scripts/` 内を指定する。インストール先のパスにバージョンが含まれる場合は、更新後も設定先が存在することを確認する。空白を含むパスはコマンド文字列内で引用する。

## §3 警告の読み方

警告は入力の内訳を確認するきっかけとして使う。

- 開始時から大きい場合は、ツール・常駐指示・メモリを調べる
- 作業中に増えた場合は、読み込んだファイル・ログ・議論が継続に必要かを確認する
- 作業の区切りで必要な状態を保存し、会話の継続・圧縮・分離を選ぶ

使用率だけで clear や compact を実行しない。具体的な判断基準は [コンテキスト管理](./03-cost-levers.md#§2-コンテキストの内訳と会話の区切り) と [大規模探索](./04-large-codebase.md) を参照する。

## §4 表示の限界

表示は入力JSONに依存する。メインのスクリプトは使用率・入力・コストが未提供なら0、ウィンドウサイズが未提供なら200kを表示するため、セッション開始直後などの値を確定値として扱わない。`jq` がなければ案内メッセージを表示する。

使用率はメインの会話を表し、委譲先全体の利用量ではない。コスト値も請求書や利用枠の残量を示すものではない。全体の比較には対象範囲を明示した利用記録を使う。

## §5 計測との使い分け

状態表示は会話を管理するための判断材料、利用記録の集計は施策を評価するための資料として使う。ログや計測機能から取得できる通常入力・キャッシュ作成・読み取り・出力を分け、同じ応答を重複集計しない。計測方法は [利用量の評価](./03-cost-levers.md#§1-計測とキャッシュ) を参照する。

## §6 関連資料

- [公式 statusline 仕様](https://code.claude.com/docs/en/statusline): 入力JSONと設定
- [コンテキスト・往復・待機](./03-cost-levers.md): 会話の区切りと効果測定
- [大規模コードベース](./04-large-codebase.md): 探索範囲と回答の絞り込み

## §7 委譲先の表示

`scripts/subagent-statusline.sh` は `tasks[]` を読み、タスクごとに1行のNDJSON `{"id":"<task id>","content":"<row body>"}` を返す。名前・モデル・状態・tokenCountの提供値を表示し、`columns`（既定80）で文字数を切り詰める。

```json
{
  "subagentStatusLine": {
    "type": "command",
    "command": "/absolute/path/to/model-strategy/skills/model-effort-guide/scripts/subagent-statusline.sh"
  }
}
```

この設定は `subagentStatusLine` に対応するClaude Code環境で使う。パスと依存ツールはメインの表示と同じ。`tasks[]` の未提供フィールドは表示できず、IDがない項目はスキップする。`jq` がない場合は何も出力しない。タスクの表示値だけから全モデルの課金額や利用枠を推定しない。
