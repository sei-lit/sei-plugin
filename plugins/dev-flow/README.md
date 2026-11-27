# dev-flow

実装を伴う開発タスク（機能開発・仕様実装・改善・リファクタリング）を、短い依頼から
最終報告まで個別指示なしで進めるための実行フローをまとめたプラグイン。

## 何が入っているか

- `skills/dev-task-flow/` — 規模判定 → 目標探索 → 委譲と設計相談 → 実装 → 検証 →
  self-review と PR → 最終報告、の順序と規模ごとに実行する手順だけを持つスキル。
  各手順の中身は下の依存スキルに任せ、このスキルには複製しない。
- `hooks/` — 最後の差分の確かめを機械で行う PreToolUse hook（Claude Code だけ。Codex には効かない）。
  受け入れテストは `tests/`（`python3 -m unittest discover -s plugins/dev-flow/tests`）。

## hook（最後の差分の確かめ）

dev-task-flow を開いたセッションで、PR の作成・ready・完了の報告のコマンドを実行する直前にだけ判定し、
足りないものがあればそのコマンドを拒否して、次にすることを返す。

| 場面 | 判定 |
| --- | --- |
| `gh pr create`・`gh pr ready`・`orca orchestration send --type worker_done` の直前で、最後にコードを変えたあとに self-review を当てていない | 止める |
| 同じ直前で、今のブランチを含むスタック（`feature/x-pr1`・`feature/x-pr2` や `stack/1`・`stack/2` のように末尾の番号だけが違うブランチ）の下の段が、隣の上の段に入っていない | 止める |
| dev-task-flow を開いていないセッション | 止めない |
| コードを変えていない（文書・PR の本文の書き換え、作業しているリポジトリの外への書き込み、コミット、スクリプトの実行、コードのパスが出てくるだけのコマンド） | 止めない |
| 最後のコードの変更のあとに self-review を当てた | 止めない |
| 上の 3 つ以外のコマンド（`gh pr view`・`gh pr ready --undo`・worker_done 以外の `orca orchestration send`、`grep` やコミットメッセージの中に同じ文字列があるだけのもの）と、Bash 以外のツール | 止めない |
| 判定できない（入力や記録が読めない、`python3` が無い、git が 5 秒で返らない） | 止めない |

- self-review は、Skill ツールでの起動（`self-review`・`<プラグイン>:self-review`）、`/self-review`、`skills/self-review/SKILL.md` の Read を数える
- 誤って止めたとき: コマンドの頭に `DEV_FLOW_FINAL_CHECK_SKIP="<理由>"` を付けて実行し直すと通る（理由が空なら通さない）
- コードの変更として数えるのは、コードの拡張子のファイルへの Edit・Write と、書き込み先がコードのファイルの Bash（`sed -i`、`>`・`>>`・`tee`、python でパスを文字列か引数で渡して書き戻すもの）。作業しているリポジトリ（hook の cwd と、その git のルート）の外の絶対パス（PR の本文や補助のスクリプトを置く一時ディレクトリなど）は数えない。そのため、途中で別のリポジトリへ移って直した分も数えない
- hook そのものを止めたいとき: settings の `env` に `"DEV_FLOW_FINAL_CHECK": "off"` を書く（全部のセッションで止まる）

### ほかのセッションへの影響

プラグインの hook は、プラグインを有効にした全部のセッション（サブエージェントを含む）で動く。

- dev-task-flow を開いていないセッションでは止めない。Bash を実行するたびに hook のシェルが 1 回動く。
  入力に `gh pr` か `orchestration send` が無ければ python を起動せずに終わる（手元の macOS で中央値 13 ms）。
  該当するコマンドでは記録を頭から読む（50 MB の記録で約 0.5 秒）
- dev-task-flow を開いたセッションでは、ほかのスキル（pr-creator など）から `gh pr create` を実行する場合も同じ判定で止める
- 同じコマンドに別の PreToolUse hook（review-checklist など）があるときは、どれか 1 つが拒否すればコマンドは実行されない
- サブエージェントに任せたコードの変更は、親のセッションの記録に Edit として残らないので数えない

## 依存するスキル

dev-task-flow はパスではなくスキル名で次のスキルを参照する。このプラグインには含まないので、
別途入れておく。

| スキル | 置き場所 |
| --- | --- |
| goal-exploration（`cases.md` の回帰ケースを含む） | 個人スキル（このマーケットプレイスには未収録） |
| self-review | 個人スキル（このマーケットプレイスには未収録） |
| model-effort-guide | このマーケットプレイスの `model-strategy` プラグイン |
| good-code-review | このマーケットプレイスの `book-skills` プラグイン |
| pr-split | このマーケットプレイスの `pr-split` プラグイン |
| orchestration（Orca） | Orca が配布するスキル |
| pr-creator | このマーケットプレイスには未収録 |
| incremental-commit / review-checklist / PR 前レビュー | 対象プロジェクト側にあれば使う |

## 使い方

```
/plugin install dev-flow@sei-plugin
```

インストール後は `dev-flow:dev-task-flow` として読み込まれる。実装を伴う依頼を受けたときに
description の条件で自動的に発動するほか、`/dev-flow:dev-task-flow` で明示的に呼び出せる。
