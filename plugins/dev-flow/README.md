# dev-flow

実装を伴う開発タスク（機能開発・仕様実装・改善・リファクタリング）を、短い依頼から
最終報告まで個別指示なしで進めるための実行フローをまとめたプラグイン。

## 何が入っているか

- `skills/dev-task-flow/` — 規模判定 → 目標探索 → 委譲と設計相談 → 実装 → 検証 →
  self-review と PR → 最終報告、の順序と規模ごとに実行する手順だけを持つスキル。
  各手順の中身は下の依存スキルに任せ、このスキルには複製しない。

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
| pr-creator / incremental-commit / review-checklist / PR 前レビュー | 対象プロジェクト側にあれば使う |

## 使い方

```
/plugin install dev-flow@sei-plugin
```

インストール後は `dev-flow:dev-task-flow` として読み込まれる。実装を伴う依頼を受けたときに
description の条件で自動的に発動するほか、`/dev-flow:dev-task-flow` で明示的に呼び出せる。
