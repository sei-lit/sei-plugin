# Codex CLI (GPT 系モデル) のコスト最適化

> **典拠**: developers.openai.com — Codex Models / Codex Pricing / API Pricing / Prompt Caching / Config Reference、github.com/openai/codex（モデル表・価格・effort は 2026-07-23 に公式ページで再確認。§3〜§5 の機構情報は 2026-07-02 確認）。最新値は https://developers.openai.com/codex/models および https://developers.openai.com/api/docs/pricing を参照すること。
>
> 本書は `00`〜`04` の原則（高価なモデルは「判断」に、安価なモデルは「作業量」に。単価最適化と量制御は別レバー）を Codex CLI に写像する。原則そのものは環境非依存。

## §1 モデルと価格 (per 1M tokens, API 従量課金時。2026-07-23 公式表で確認)

現行世代は **GPT-5.6 ファミリー（Sol / Terra / Luna）**。公式の使い分けは「Sol = 複雑・オープンエンドな作業（迷ったら Sol）、Terra = 日常作業の主力、Luna = 明確で反復的な作業」。

| Model | 位置づけ | Input | Cached input | Output |
| --- | --- | --- | --- | --- |
| `gpt-5.6-sol` | **フラッグシップ**（最難関コーディング・リサーチ。公式「迷ったら Sol」） | $5.00 | $0.50 | $30.00 |
| `gpt-5.6-terra` | 日常作業の主力（GPT-5.5 競合性能を低コストで） | $2.50 | $0.25 | $15.00 |
| `gpt-5.6-luna` | 高速・低価格、ファミリー最安 | $1.00 | $0.10 | $6.00 |
| `gpt-5.5` | **前世代**フロンティア | $5.00 | $0.50 | $30.00 |
| `gpt-5.4` | 前世代 | $2.50 | $0.25 | $15.00 |
| `gpt-5.4-mini` | 軽量タスク・サブエージェント用（API 最安帯） | $0.75 | $0.075 | $4.50 |
| `gpt-5.4-nano` | 最安・定型変換 | $0.20 | $0.02 | $1.25 |
| `gpt-5.3-codex-spark` | リアルタイム反復（research preview, Pro 限定） | — | — | — |

- long context 時: Sol $10.00/$1.00/$45.00、Terra $5.00/$0.50/$22.50、Luna $2.00/$0.20/$9.00
- モデル未指定時は公式の推奨モデルが使われる（config 例は `model = "gpt-5.6"`。CLI 既定の Power 設定は gpt-5.6-sol + medium reasoning）
- gpt-5.2 / gpt-5.3-codex / gpt-5.1 系は ChatGPT サインインでは非推奨・段階廃止（API キーでは一部残存）
- **Claude 系との対応**（役割ベースの目安）: gpt-5.6-sol ≈ Opus/Fable 帯（判断）、gpt-5.6-terra ≈ Sonnet 帯（実装）、gpt-5.6-luna / gpt-5.4-mini/nano ≈ Haiku 帯（探索・定型）

## §2 reasoning effort (モデル別に確認する。2026-07-23 確認)

effort の対応レベルと既定は**モデル別に記載・確認する**（config.toml の `model_reasoning_effort` / `/model` で設定）。「全モデル共通の enum・共通の既定」を前提にしない。

| モデル | 確認済みレベル | 既定 | 確認手段 |
| --- | --- | --- | --- |
| `gpt-5.6-sol` | `low` / `medium` / `high` / `xhigh` （Extra high） / `max` / `ultra` | `medium` | 公式 models ページの CLI セレクタ（2026-07-23） |
| `gpt-5.6-terra` / `gpt-5.6-luna` | 公式ページに個別記載なし | 未確認 | ルーティング前に `/model` セレクタで capability probe |
| 5.5 / 5.4 系（前世代） | `minimal`〜`xhigh`（2026-07-02 時点の記載） | `medium` | 継続利用時は probe で再確認 |

- `max` は最難関問題向けの最大思考深度。`ultra`（5.6-sol）は単一エージェント実行を超えるモードで、**サブエージェントへの自動タスク委譲**を含む — 分割可能な大規模タスク専用であり「もっと深い思考」の上位互換ではない
- **設定経路の注意**: `max` / `ultra` は公式 models ページの CLI セレクタ（`/model`）で確認されたレベル。config.toml の `model_reasoning_effort` は現行 Config Reference では `minimal`〜`xhigh` のみ記載のため、`max`/`ultra` を使う場合は `/model` セレクタ経由を基本とし、config 直書きの可否は実機で probe する
- `minimal` は 5.6 系の公式セレクタに存在しない（前世代のみの記載）
- Codex の既定（medium）は Claude Code の `high`/`xhigh` 既定より低い。上げ忘れより下げ忘れに注意
- 使い分けは `01-effort-levels.md` の考え方がそのまま通用する: 設計・監査は `high`〜`max`、日常タスクは `medium`、探索・定型は `low`
- `xhigh` 以上は「難問専用」であってデフォルト格上げ用ではない（レイテンシ非依存の難問のみ）

## §3 実行体制: Codex での委譲

Codex CLI にもマルチエージェント機構がある（`features.multi_agent`、デフォルト有効。`spawn_agent` / `wait_agent`、同時 6 スレッド・ネスト深さ 1）。委譲の鉄則（`02-decision-matrix.md` §3）はそのまま適用する。

| 手段 | 用途 |
| --- | --- |
| `agents.<name>.config_file` + `description` | 役割別エージェント定義。**安いモデル（gpt-5.6-luna / gpt-5.4-mini）+ 低 effort の探索役/実装役**を定義しておくのが sonnet-implementer / haiku-scout 相当 |
| `/model`（対話中） | メインのモデル・effort を切替（設定は永続化される） |
| `codex exec -m <model>` | 非対話の一括処理を安いモデルの別実行に切り出す |
| `--profile <name>`（`$CODEX_HOME/<name>.config.toml`） | 「深い作業用 （gpt-5.6-sol + high）」「定型用 （gpt-5.6-luna + low）」等のプリセット切替 |

- **Claude Code の hook (`hooks/route-warn.mjs`) は Codex では動作しない**: PreToolUse hook + `hooks/hooks.json` の自動ロードは Claude Code 固有の機構であり、Codex CLI 側に同等の自動介入は無い。R1 相当の直接実行を避ける運用は、`agents.<name>` への委譲を手動で徹底することで代替する
- `agents.<name>` の役割定義例 (config.toml。探索役 `scout` = R1/R2 相当、実装役 `implementer` = R3 相当。この名前は `route-policy.mjs` の Codex 側担当名と同じ。effort は §2 の probe 注記のとおり Terra/Luna の対応レベル未確認のため、実機で `/model` セレクタから確認してから指定する):

  ```toml
  [agents.scout]
  config_file = "scout.config.toml"  # model = "gpt-5.6-luna", model_reasoning_effort = "low" (要 probe)
  description = "R1/R2: 探索・列挙・既知検証手順の実行のみ。判断・実装はしない"

  [agents.implementer]
  config_file = "implementer.config.toml"  # model = "gpt-5.6-terra", model_reasoning_effort = "medium" (要 probe)
  description = "R3: 構造化仕様 4 フィールドを受けて実装する。仕様にない判断はしない"
  ```

## §4 サブスクリプション制限 (ChatGPT プラン)

- Plus / Pro / Business / Enterprise の Codex 利用はプラン内クレジット制。**モデルが安いほど同じクレジットで多くこなせる**（API 単価比の目安: gpt-5.6-luna は gpt-5.6-sol の 1/5。例示 [2026-07-02 時点]: gpt-5.4-mini は gpt-5.5 の約 4〜5 倍のタスク量）
- Pro は 5x / 20x ティアで枠が拡大。`gpt-5.3-codex-spark` は Pro 限定
- API キー認証での従量課金も可能（§1 の単価）。枠を使い切った際の逃がし先になる
- **含意**: 枠温存の構図は Claude サブスクと同じ。「gpt-5.6-sol は判断だけ、作業量は luna / mini / nano へ」で消費速度を数分の一にできる

## §5 プロンプトキャッシュ

- cached input は **通常 input の 10%**（90% off）。自動・無料、明示の cache_control は不要
- 最小キャッシュ対象プレフィックス **1,024 トークン**、**完全プレフィックス一致**
- TTL: インメモリ 5〜10 分（最長 1h）。gpt-5.x / codex 系は `prompt_cache_retention: "24h"` で 24 時間保持（非 ZDR 組織はデフォルト）
- **含意**: `03-cost-levers.md` のキャッシュ温存規律（安定プレフィックスを先頭に・揮発情報を後ろに・ツール定義を不変に）は Codex でも同様に効く。AGENTS.md やシステム設定が安定プレフィックスを構成する

## §6 決定マトリックス (Codex 版クイックリファレンス)

| タスク種別 | モデル | reasoning effort |
| --- | --- | --- |
| アーキテクチャ設計・技術選定・監査 | gpt-5.6-sol | high〜max |
| 最難関実装・大規模リファクタ | gpt-5.6-sol / gpt-5.6-terra | high〜xhigh |
| サブエージェント分割が効く大規模タスク | gpt-5.6-sol | ultra（コスト影響を理解した上で） |
| 仕様確定済みの実装 | gpt-5.6-terra（委譲なら gpt-5.6-luna / gpt-5.4-mini） | medium |
| コード探索・調査・grep 系 | gpt-5.6-luna / gpt-5.4-mini | low |
| ドキュメント整形・定型変換 | gpt-5.4-mini / gpt-5.4-nano | low（5.4 系は minimal 可） |
| リアルタイムの高速反復（Pro） | gpt-5.3-codex-spark | — |

> effort 列は「要求する目標値」。モデル別の対応可否・設定経路は §2 の表と probe で確認してから指定する（特に Terra / Luna は対応レベル未確認）。

## §7 conductor mode (v0.3.0) の Codex 読み替え

`MODEL_STRATEGY_MODE=conductor` は Claude Code の `main` / `judge` 分離をそのまま Codex に写像できる。ただし前提が異なる点に注意する:

- Claude Code の conductor mode は「安いメイン (Sonnet 帯) + 高いモデルへの R4a 委譲 (judge = Opus/Fable)」という**単価差**が動機になる。Codex の既定メインは `gpt-5.6-sol` (公式「迷ったら Sol」) であり、日常運用でメインを terra/luna に固定するのは §1 の役割分担 (Sol=判断, Terra=主力, Luna=定型) から外れる
- 対応させる場合の読み替え: conductor = `gpt-5.6-terra` 起点のメイン、judge = `gpt-5.6-sol` への `spawn_agent`/`agents.<name>` 委譲 (R4a のみ、判断パケットを渡す)。conductor mode を使う利点は Codex では単価差そのものより、**判断をメインの会話コンテキストから隔離できること** (`08-conductor-mode.md` §3 の判断パケット規約と同じ理由) にある
- `judge`/`judge-fable` (Claude Code のサブエージェント定義) は Codex には存在しない。Codex で同等の役割を持たせる場合は `agents.judge` に `gpt-5.6-sol` + `description` で判定専任ロールを定義し、Read 系ツールのみ渡す運用で近似する (本プラグインの `.mjs`/hook 資産は Claude Code 専用のため、判定はメイン側の運用規律で代替する)
- scope-guard 相当の PreToolUse 強制は Codex には存在しない (§3 で述べた `route-warn.mjs` 非対応と同じ理由)。範囲逸脱の検出は `route-policy.mjs auditManifest` の `SCOPE_EXPANSION` (マニフェストの自己申告検査) のみに依存する
