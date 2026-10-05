# model-strategy

Claude Code / Codex のモデル・effort（推論に割く労力）・委譲方針を決めるプラグイン。必要な品質を満たしながら、会話履歴の反復処理、相談の往復、エージェントの起動と結果統合を含む総利用量を抑える。

9uiLe 氏の [`model-strategy` 0.5.0](https://github.com/9uiLe/plugins)（MIT）を、このマーケットプレイスの配置規約に合わせて移植したもの。出典と権利表示は [`NOTICE.md`](./NOTICE.md) にある。

## 利用する場面

- タスクに合うモデルと effort を選ぶ
- 長い会話や繰り返しの相談による消費を抑える
- メイン、実装担当、アドバイザーの担当範囲を決める
- 操作の割当と受け入れ判断を監査可能な形で記録する

通常のコーディング依頼だけでは自動起動しない。モデル選択・利用量・委譲方針を明示的に相談するか、`model-effort-guide` を指定して使う。

## インストール

上流の `model-strategy@9uile-plugins` を入れたままだと、スキル名 `model-strategy:model-effort-guide` とエージェント名が重複する。先に上流をアンインストールしてから入れる。

```text
/plugin uninstall model-strategy@9uile-plugins
/plugin marketplace add sei-lit/sei-plugin
/plugin install model-strategy@sei-plugin
```

## 基本的な依頼

```text
model-effort-guide を使って、このタスクに合うモデル・effort・委譲方針を決めてください。
```

推奨だけを求めた場合は、担当とモデル、判断理由、会話を区切る条件を返す。実行も求めた場合は、開始時に方針を共有して作業を進め、成果物・検証結果・未解決事項を報告する。ユーザーが指定したモデル・effort・アドバイザー利用を優先する。

## 構成

| パス | 内容 |
| --- | --- |
| `skills/model-effort-guide/SKILL.md` | スキル本体。会話管理、担当とモデルの選択、依頼と受け入れ、待機、報告の手順 |
| `skills/model-effort-guide/references/` | 価格・effort・ルーティング規則・コンテキスト管理・Codex 対応・高保証モードの参照資料（下表） |
| `skills/model-effort-guide/scripts/route-policy.mjs` | 操作分類（`route`）と割当監査（`audit`）、引用検証（`verify-evidence`）の正本 |
| `skills/model-effort-guide/scripts/*-statusline.sh` | コンテキスト使用率と委譲先タスクのステータスライン表示 |
| `skills/model-effort-guide/tests/` | `route-policy.mjs` と参照資料 02/07 の同期テスト、statusline のテスト。`node --test skills/model-effort-guide/tests/*.test.mjs` で実行 |
| `agents/` | Claude Code 向けエージェント定義（下表） |

### エージェント

| Agent | モデル | 用途 |
| --- | --- | --- |
| `haiku-scout` | Haiku | 探索・独立検証 |
| `sonnet-implementer` | Sonnet | 仕様が確定した実装 |
| `judge` | Opus | 高保証モードの独立判定 |
| `judge-fable` | Fable 5 | 高保証モードの難しい判断や、Opus judge で解決できない問題の独立判定 |

Codex では利用可能なモデルと委譲機能に応じて担当を選ぶ（`references/07-codex.md`）。

### 参照資料

| 資料 | 読む場面 |
| --- | --- |
| [価格](./skills/model-effort-guide/references/00-pricing.md) | モデル・キャッシュ・バッチ処理の料金と適用条件を確認する |
| [effort](./skills/model-effort-guide/references/01-effort-levels.md) | 推論量とモデルごとの対応を選ぶ |
| [ルーティング規則](./skills/model-effort-guide/references/02-decision-matrix.md) | 厳密な分類や実装依頼の条件を確認する |
| [コンテキスト・往復・待機](./skills/model-effort-guide/references/03-cost-levers.md) | 入力の増加、反復呼び出し、計測方法を調べる |
| [大規模コードベース](./skills/model-effort-guide/references/04-large-codebase.md) | 探索範囲と戻り値を絞る |
| [リポジトリ索引](./skills/model-effort-guide/references/05-repo-index.md) | 必要な情報を取り出す索引を設計する |
| [コンテキスト監視](./skills/model-effort-guide/references/06-context-monitor.md) | 状態表示を設定し、計測の限界を確認する |
| [Codex](./skills/model-effort-guide/references/07-codex.md) | モデル・effort・委譲を Codex で適用する |
| [高保証モード](./skills/model-effort-guide/references/08-conductor-mode.md) | 割当監査・独立判定・範囲警告を設定する |

## 上流との差分

- 配置: 上流はプラグインルート直下に `references/` `scripts/` `tests/` を置くが、ここではマーケットプレイスの規約（1 スキル 1 ディレクトリ）に合わせて `skills/model-effort-guide/` 配下へ移した。本文中の相対パスはこのディレクトリ基準で読む。
- **hook は同梱しない。** 上流の `hooks/route-warn.mjs`（探索操作への委譲検討の警告）と `hooks/scope-guard.mjs`（高保証モードでの範囲外書き込み警告）、およびその `hooks.json` とテストは含めていない。これらは Grep / Glob / Bash / Edit / Write のたびに Node を起動する PreToolUse hook で、スキル本体の動作には不要なため。参照資料 07 と 08 が scope-guard に触れている箇所は「上流にある任意機能」として読む。必要なら上流から `hooks/` を持ち込み、`hooks/hooks.json` を配置すれば有効になる。

## Orca でアドバイザーを利用する

Orca と公式 `orchestration` スキルを利用できる環境が必要。Orca はこのプラグインには同梱されていない。

`model-effort-guide` が相談範囲と判断基準を定め、`orchestration` がエージェントの起動・待機・完了処理を担う。通常のアドバイザー利用に高保証モードの設定は不要。

作業内容に次の依頼を添える。モデルと effort は用途に合わせて指定する。

```text
model-effort-guide と orchestration スキルを利用し、Codex gpt-6-astra（effort: medium）をアドバイザーとして使ってください。
あなたが作業と最終判断を担当し、重要な設計判断・リスク・見落としをまとめて相談してください。

相談には目的・制約・検討案・具体的な質問・必要なファイルや差分を渡し、回答は重要な指摘・根拠・推奨案・未解決事項に絞ってください。
指摘は事実や検証結果に照らして採否を判断し、新しい証拠・重大な未解決点・結論に影響する変更がある場合だけ、同じ相手へ差分をまとめて再相談してください。
同じ論点で新しい根拠が出なくなったら往復を終え、採否と理由、残る未解決事項を記録してください。

待機は公式 orchestration の現行ガイドに従い、完了通知や待機機能を使ってください。sleep・端末読込・状態確認だけでモデルを繰り返し呼び出さず、待機中は結果に依存しない作業を進めてください。
最後に、成果物と検証結果、重要な指摘の採否と理由、未解決事項を簡潔に報告してください。
```

## 高保証モード（任意）

割当と受け入れ判断の記録が必要な場合は、監査可能なルーティングや独立判定を明示的に依頼する。高保証モード（conductor mode）では、操作ごとの割当マニフェストと変更可能範囲の基準線を保存し、必要に応じて judge に独立判定を委譲する。

`route-policy.mjs` が詳細な分類の正本。`route` で操作を分類し、`audit` で割当を監査する。条件と手順は [ルーティング規則](./skills/model-effort-guide/references/02-decision-matrix.md) と [高保証モード](./skills/model-effort-guide/references/08-conductor-mode.md) を参照する。

## 使用状況の表示

`scripts/context-statusline.sh` はメインセッションのコンテキスト使用率を、`scripts/subagent-statusline.sh` は委譲先タスクの状態を表示する。設定方法と測定上の限界は [コンテキスト監視](./skills/model-effort-guide/references/06-context-monitor.md) を参照する。
