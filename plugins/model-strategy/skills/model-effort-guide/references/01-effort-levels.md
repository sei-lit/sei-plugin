# effort パラメータの使い分け

> **典拠**: platform.claude.com — Effort Parameter / Model Migration Guide / Models overview（claude-api skill 経由、2026-10-06 時点キャッシュ）。§1 のモデル別対応表と Claude Code の既定は code.claude.com/docs/en/model-config で 2026-10-08 に確認。

## §1 effort とは

`output_config.effort` はモデルの「思考の深さと総トークン消費」を制御するパラメータ。**低い effort = ツール呼び出しが少なく統合され、前置きが減り、確認が簡潔になる** = output 課金が直接減る。

- Claude Code CLI が受理する値: `low` / `medium` / `high` / `xhigh` / `max`
- モデル別対応（典拠: code.claude.com/docs/en/model-config「Adjust effort level」、2026-10-08 確認。**表にないモデルは effort 非対応**）:

| モデル | 対応レベル | Claude Code 既定 | API 既定 |
| --- | --- | --- | --- |
| Opus 5.5 / Haiku 5.5 | `low` / `medium` / `high` / `xhigh` / `max` | **`medium`** | `medium` |
| Sonnet 5.5 | `low` / `medium` / `high` / `xhigh` / `max` | **`medium`** | `high` |
| Fable 5.1 / Fable 5 / Opus 5 / Sonnet 5 / Opus 4.8 | `low` / `medium` / `high` / `xhigh` / `max` | `high` | `high` |
| Opus 4.7 | `low` / `medium` / `high` / `xhigh` / `max` | `xhigh` | `high` |
| Opus 4.6 / Sonnet 4.6 | `low` / `medium` / `high` / `max`（`xhigh` 非対応） | `high` | `high` |
| Haiku 4.5 / Opus 4.5 以前 | 非対応（表に列挙されていない） | — | — |

- 非対応レベルを指定した場合、Claude Code は「指定以下で最も高い対応レベル」へフォールバックする（例: Opus 4.6 で `xhigh` → `high` 実行）。組織側でレベル上限が設定されている場合もある
- ユーザー設定のトップレベル `effortLevel` は Opus 5.5 には適用されない（model-config の記載）。Opus 5.5 の effort は `/model` などで明示する
- 同じレベル名でもモデルによって思考量が違う。旧モデルで決めたレベルをそのまま引き継がず、移行時に測り直す

## §2 レベル別ガイド

| Level | 用途 | コスト感 |
| --- | --- | --- |
| `max` | 正確性がコストより重要な最難関タスク。過剰思考のリスクあり、収穫逓減 | 最大 |
| `xhigh` | 長時間のコーディング・エージェント作業。Opus 5.5 / Sonnet 5.5 では効果を測ってから使う | 大 |
| `high` | 品質とトークン効率のバランスが良い。旧世代では知的タスクの推奨最低ライン | 中 |
| `medium` | **Opus 5.5 / Sonnet 5.5 / Haiku 5.5 のエージェント的コーディングの起点** | 小 |
| `low` | サブエージェント・単純タスク・チャット・レイテンシ重視 | 最小 |

## §3 モデル別の重要な知見 (典拠: Migration Guide)

### Opus 5.5
- API・Claude Code とも既定は `medium`（Opus 5 以前は `high`）。Anthropic の評価では Opus 5.5 の `medium` が Opus 5 の `high` を上回り、いくつかのコーディング評価では `low` でも近い結果をより安く出す
- 同じレベルでは Opus 5 より 1 ターンあたりの思考が長い（特に `xhigh` / `max`）。Opus 5 の設定を引き継ぐと output が増える
- thinking はオフにできない（`disabled` は 400）。思考量を減らしたいときはプロンプトで指示するより effort を下げる
- `medium` を起点に隣のレベルを試し、`xhigh` / `max` は品質向上を測れた作業に限る

### Fable 5.1
- **thinking は常時オン**（オフにできない）。思考トークンも output 課金される
- Fable 系は `low` でも旧世代の `xhigh` 級の品質が出ることが多い（公式記載）。高 effort ではルーチン作業に対して過剰なコンテキスト収集・熟考をしがち
- 1 回の難しいリクエストが数分以上かかることがある。時間がかかりすぎる場合は effort を下げる
- Claude Code 既定は `high` のまま。サブスクでも Pro は usage credits（`00-pricing.md` §4）なので、**`medium` 起点、`xhigh` / `max` は最難関のみ**に限るのが効率的

### Sonnet 5.5
- レベルが Sonnet 5 から再調整されている。起点はエージェント的コーディング・複数ステップのツール利用で `medium`、チャット・生成・分類・抽出で `low`
- Anthropic の評価では、多くのエージェント的コーディングで Sonnet 5.5 の `medium` が Sonnet 5 の `high` を上回り、コストは 5 分の 1 未満
- `medium` 以上ではほぼ毎回思考してから返答する。`low` では単純な依頼の思考を省くが、長いエージェント作業で途中確認を挟んだり検証を省いたりしやすい
- `thinking: disabled` は 400。thinking を切りたい経路は `between_tools`（`high` 以下でのみ可）を使う

### Haiku 5.5
- Haiku 系で初めて effort に対応。既定は `medium`
- `low`: チャット・短いツール作業・大量の単純処理。長いエージェント作業では検索や確認を省いて早く終えることがある
- `medium`: エージェント的コーディングを含むほとんどの作業の起点
- `high`: 知識作業・長めのエージェント作業・厳密な指示追従
- `xhigh` / `max`: 思考と返答が大きく伸びる。使う前に Sonnet 5.5 とコスト・品質を比べる

### 旧世代（Opus 4.8 / Sonnet 5 / Sonnet 4.6）
- Opus 4.8: `high` を起点に上下を試すのが公式推奨。高 effort が往復回数を減らして総コストが下がることもある
- Sonnet 5: adaptive thinking がデフォルトでオン。定型用途は `thinking: disabled` か effort `low` を明示する
- Sonnet 4.6: デフォルトが `high` なので、チャット的・定型的な用途では `low` / `medium` に下げる

## §4 Claude Code での設定方法

- メインセッション: `/model` でモデルと effort を選択（例: Opus (medium)）
- サブエージェント: agents 定義の frontmatter `model:` でモデル指定（effort はモデル既定に従う。`haiku-scout` / `sonnet-implementer` は Haiku 5.5 / Sonnet 5.5 の Claude Code 既定 `medium` で動く）
- 迷ったら: **メインは Opus 5.5 の `medium`**（既定のまま）、サブエージェントは `low`〜`medium` から始め、品質不足を感じた経路だけ上げる
