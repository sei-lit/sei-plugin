# Codex CLI・ChatGPT (GPT 系モデル) のコスト最適化

> **典拠**: developers.openai.com — API Pricing / API Models / Prompt Caching / API Changelog、learn.chatgpt.com — Models / Pricing / Changelog（旧 developers.openai.com/codex/models・/codex/pricing の移転先）、github.com/openai/codex の `codex-rs/models-manager/models.json`（2026-10-06 更新分）。いずれも 2026-10-08 に確認。openai.com の発表記事と help.openai.com は取得できず未確認。§3 の `agents.<name>` 機構の記述は 2026-07-02 確認。最新値は https://learn.chatgpt.com/docs/models および https://developers.openai.com/api/docs/pricing を参照すること。
>
> 本書は `00`〜`04` の原則（高価なモデルは「判断」に、安価なモデルは「作業量」に。単価最適化と量制御は別レバー）を Codex CLI に写像する。原則そのものは環境非依存。

## §1 モデルと価格 (per 1M tokens、API Standard・入力 272K 以下。2026-10-08 公式表で確認)

現行世代は **GPT-6 ファミリー**（2026-09-03 に Astra、09-22 に Sol / Luna、09-29 に GPT-6.1 Sol を公開）。公式の使い分けは「GPT-6.1 Sol = 複雑・エージェント的な作業、Luna = 範囲の決まった反復作業」。

| Model | 位置づけ | Input | Cached input | Cache write | Output | 入力 272K 超 (in / cached / out) |
| --- | --- | --- | --- | --- | --- | --- |
| `gpt-6-astra` | 最上位。最も高価 | $10.00 | $1.00 | $12.50 | $50.00 | $20 / $2 / $75 |
| `gpt-6.1-sol` | **フラッグシップ**。Codex のモデル選択の先頭 | $2.00 | $0.10 | $2.50 | $10.00 | $4 / $0.20 / $15 |
| `gpt-6-sol` | 6.1 Sol の前版 | $2.00 | $0.20 | $2.50 | $10.00 | $4 / $0.40 / $15 |
| `gpt-6-luna` | 高速・最安 | $0.10 | $0.01 | $0.125 | $0.50 | $0.20 / $0.02 / $0.75 |
| `gpt-5.6-sol` | 前世代。**期間限定価格**（2026-11-21 まで以上。終了後の価格は未記載） | $4.00 | $0.40 | $5.00 | $20.00 | $8 / $0.80 / $30 |
| `gpt-5.6-terra` | 前世代（07-30 に 20% 値下げ） | $2.00 | $0.20 | $2.50 | $12.00 | $4 / $0.40 / $18 |
| `gpt-5.6-luna` | 前世代（07-30 に 80% 値下げ） | $0.20 | $0.02 | $0.25 | $1.20 | $0.40 / $0.04 / $1.80 |
| `gpt-5.5` | 前世代 | $5.00 | $0.50 | — | $30.00 | — |
| `gpt-5.4` / `-mini` / `-nano` | 前世代（API のみ） | $2.50 / $0.75 / $0.20 | $0.25 / $0.075 / $0.02 | — | $15 / $4.50 / $1.25 | — |

- コンテキスト: Codex では GPT-6 / GPT-5.6 系とも既定 272K、最大 872K。API では 1.05M、最大出力 128K
- データ所在地指定（regional）・FedRAMP エンドポイントは 2026-03-05 以降のモデルで 10% 増
- 「Fast」モード（07-30 に Priority Processing を置き換え）は GPT-5.6 Sol で API 単価 2 倍。Codex の倍率は §4
- 公式 docs の config 例は `model = "gpt-6.1-sol"`
- **Claude 系との対応**（役割ベースの目安）: gpt-6-astra ≈ Fable 帯（最難関の判断）、gpt-6.1-sol ≈ Opus 帯（判断・主力）、gpt-6-luna ≈ Haiku 帯（探索・定型）。gpt-6.1-sol は Opus 5.5 の半額、gpt-6-luna は Haiku 5.5 と同額

### 提供終了

| モデル | 内容 |
| --- | --- |
| `gpt-5.3-codex-spark` | 2026-09-14 に Codex（デスクトップアプリ・CLI・IDE 拡張）から提供終了 |
| `gpt-5.4` / `gpt-5.4-mini` | 2026-08-31 に ChatGPT サインインの Codex から提供終了。後継は GPT-6 Sol / GPT-6 Luna |
| `gpt-5.5` | **2026-10-14** に ChatGPT・ChatGPT Work・Codex の全プランから提供終了。API には残る |
| `gpt-5.2` / `gpt-5.3-codex` | ChatGPT サインインの Codex では非推奨（終了日の記載なし） |

いずれも API と API キーで使う Codex には影響しない。

## §2 reasoning effort (モデル別に確認する。2026-10-08 確認)

effort の対応レベルと既定は**モデル別に記載・確認する**（config.toml の `model_reasoning_effort` / `/model` で設定）。「全モデル共通の enum・共通の既定」を前提にしない。

| モデル | 対応レベル（Codex CLI） | 既定（CLI 同梱カタログ） |
| --- | --- | --- |
| `gpt-6.1-sol` / `gpt-6-astra` | `low` / `medium` / `high` / `xhigh` / `max` / `ultra` | `low` |
| `gpt-6-sol` | `low`〜`ultra` | `medium` |
| `gpt-6-luna` | `low`〜`max`（`ultra` なし） | `medium` |
| `gpt-5.6-sol` | `low`〜`ultra` | `low` |
| `gpt-5.6-terra` | `low`〜`ultra` | `medium` |
| `gpt-5.6-luna` | `low`〜`max` | `medium` |
| `gpt-5.5` | `low`〜`xhigh` | `medium` |

- docs の表記は Light / Medium / High / Extra High / Max / Ultra で、Light が CLI の `low` に当たる。docs は Luna を High、Astra を Light/Low から始めるよう勧めている
- `max` は最難関問題向けの最大思考深度。`ultra` は**サブエージェントを並列に動かす** Codex 専用のモードで、API の effort 値には無い。分割可能な大規模タスク専用であり「もっと深い思考」の上位互換ではない
- API の effort は Astra / 6.1 Sol が `low`〜`max`、Luna が `none`〜`max`
- サーバー側のカタログが同梱カタログを上書きすることがある。既定に依存する運用では `/model` セレクタで確認する。config.toml に `max` / `ultra` を直書きできるかは実機で確認する
- 6.1 Sol と Astra の既定は `low` で、Claude Code の既定（Opus 5.5 は `medium`）より低い。上げ忘れに注意
- 使い分けは `01-effort-levels.md` の考え方がそのまま通用する: 設計・監査は `high`〜`max`、日常タスクは `medium`、探索・定型は `low`

## §3 実行体制: Codex での委譲

Codex CLI にもマルチエージェント機構がある（`features.multi_agent`、デフォルト有効。`spawn_agent` / `wait_agent`、同時 6 スレッド・ネスト深さ 1）。委譲の鉄則（`02-decision-matrix.md` §8）はそのまま適用する。

| 手段 | 用途 |
| --- | --- |
| `agents.<name>.config_file` + `description` | 役割別エージェント定義。**安いモデル（gpt-6-luna）の探索役/実装役**を定義しておくのが sonnet-implementer / haiku-scout 相当 |
| `/model`（対話中） | メインのモデル・effort を切替（設定は永続化される） |
| `codex exec -m <model>` | 非対話の一括処理を安いモデルの別実行に切り出す |
| `--profile <name>`（`$CODEX_HOME/<name>.config.toml`） | 「深い作業用（gpt-6.1-sol + high）」「定型用（gpt-6-luna + low）」等のプリセット切替 |

- **Claude Code の hook (`hooks/route-warn.mjs`) は Codex では動作しない**: PreToolUse hook + `hooks/hooks.json` の自動ロードは Claude Code 固有の機構であり、Codex CLI 側に同等の自動介入は無い。R1 相当の直接実行を避ける運用は、`agents.<name>` への委譲を手動で徹底することで代替する
- `agents.<name>` の役割定義例 (config.toml。探索役 `scout` = R1/R2 相当、実装役 `implementer` = R3 相当。この名前は `route-policy.mjs` の Codex 側担当名と同じ):

  ```toml
  [agents.scout]
  config_file = "scout.config.toml"  # model = "gpt-6-luna", model_reasoning_effort = "low"
  description = "R1/R2: 探索・列挙・既知検証手順の実行のみ。判断・実装はしない"

  [agents.implementer]
  config_file = "implementer.config.toml"  # model = "gpt-6-luna", model_reasoning_effort = "high"。品質が足りなければ gpt-6.1-sol + low
  description = "R3: 構造化仕様 4 フィールドを受けて実装する。仕様にない判断はしない"
  ```

## §4 サブスクリプション (ChatGPT プラン)

典拠: learn.chatgpt.com/docs/pricing・/docs/models（2026-10-08 確認）。

| プラン | 月額 | Codex で使えるモデル |
| --- | --- | --- |
| Free / Go | $0 / $8 | GPT-6 Luna（Standard 速度、デスクトップアプリ） |
| Plus | $20 | GPT-6.1 Sol / GPT-6 Sol / GPT-6 Luna など |
| Pro | $100 / $200 / $500 の 3 段階 | 同上。Astra の Ultrafast は $500 のみ |
| Business | $20/ユーザー（年払い）、$25（月払い）、2 名から | 同上 |
| Enterprise / Edu | 個別見積 | GPT-6.1 Sol と GPT-6 Luna は管理者が有効化するまで使えない |

- GPT-6.1 Sol と GPT-6 Sol は Codex と ChatGPT Work で使え、通常の Chat には出ない
- GPT-5.6 Sol / Terra / Luna は移行期間中は引き続き使える

**Plus / Business（Standard）の 5 時間あたりのローカルメッセージ数**:

| モデル | 5 時間あたり |
| --- | --- |
| GPT-6 Astra | 5〜45 |
| GPT-6.1 Sol | 15〜160 |
| GPT-6 Sol | 15〜150 |
| GPT-6 Luna | 350〜3,000 |

- Pro は現在 5 時間上限なし（週の上限はかかりうる）。クラウドタスクはローカルより多く枠を消費する

**credits の消費レート**（per 1M tokens、input / cached / output。追加購入分と Business・Enterprise の従量課金で使う）:

| モデル | Input | Cached | Output |
| --- | --- | --- | --- |
| GPT-6 Astra | 250 | 25 | 1,250 |
| GPT-6.1 Sol | 50 | 2.5 | 250 |
| GPT-6 Sol | 50 | 5 | 250 |
| GPT-6 Luna | 2.5 | 0.25 | 12.5 |
| GPT-5.6 Sol | 100 | 10 | 500 |
| GPT-5.6 Terra | 50 | 5 | 300 |
| GPT-5.6 Luna | 5 | 0.5 | 30 |
| GPT-5.5 | 125 | 12.5 | 750 |

- どのモデルも §1 の API 単価のちょうど 25 倍になっている（GPT-5.6 Sol は期間限定価格の 25 倍）。モデル間の比は API 単価の比と同じ
- credits ではキャッシュ書き込みを別に課金しない
- 速度の倍率: Fast はプラン枠で 2.5 倍・credits で 2 倍、Astra Ultrafast はプラン枠で 8 倍・credits で 6 倍
- **含意**: 枠温存の構図は Claude サブスクと同じ。GPT-6 Luna は GPT-6.1 Sol の 20 分の 1 の消費なので、「gpt-6.1-sol は判断だけ、作業量は gpt-6-luna へ」で消費速度を大きく下げられる。Astra は 6.1 Sol の 5 倍消費するため、最難関の判断に限る

## §5 プロンプトキャッシュ

典拠: developers.openai.com/api/docs/guides/prompt-caching（2026-10-08 確認）。

- **GPT-5.6 以降**: TTL は `prompt_cache_options.ttl` で指定し、値は `"30m"`（既定）のみ。最後の書き込みか再利用から 30 分保持される。キャッシュ書き込みは通常 input の 1.25 倍で課金される
- キャッシュ読み取りは通常 input の 0.1 倍（GPT-6.1 Sol は 0.05 倍）。各 input トークンは「通常・キャッシュ読み取り・キャッシュ書き込み」のどれか 1 つの単価で課金される
- **GPT-5.5 以前**: `prompt_cache_retention` を使う。`in_memory` は 5〜10 分（最長 1 時間）、`24h` は最長 24 時間。ZDR でない組織の既定は `24h`。GPT-5.5 は `24h` のみ
- 自動で効き、明示の cache_control は不要。最小キャッシュ対象プレフィックスは 1,024 トークン、完全プレフィックス一致（2026-07-02 確認）
- **含意**: `03-cost-levers.md` のキャッシュ温存規律（安定プレフィックスを先頭に・揮発情報を後ろに・ツール定義を不変に）は Codex でも同様に効く。AGENTS.md やシステム設定が安定プレフィックスを構成する。30 分を超えて間を空けるとキャッシュ書き込みが再発生する

## §6 決定マトリックス (Codex 版クイックリファレンス)

| タスク種別 | モデル | reasoning effort |
| --- | --- | --- |
| アーキテクチャ設計・技術選定・監査 | gpt-6.1-sol（解けなければ gpt-6-astra） | high〜max |
| 最難関実装・大規模リファクタ | gpt-6.1-sol | high〜xhigh |
| サブエージェント分割が効く大規模タスク | gpt-6.1-sol | ultra（コスト影響を理解した上で） |
| 仕様確定済みの実装 | gpt-6.1-sol（委譲なら gpt-6-luna） | low〜medium（luna は high） |
| コード探索・調査・grep 系 | gpt-6-luna | low |
| ドキュメント整形・定型変換 | gpt-6-luna | low |

> effort 列は「要求する目標値」。モデル別の対応可否は §2 の表で確認してから指定する。

## §7 conductor mode (v0.3.0) の Codex 読み替え

`MODEL_STRATEGY_MODE=conductor` は Claude Code の `main` / `judge` 分離をそのまま Codex に写像できる。ただし前提が異なる点に注意する:

- Claude Code の conductor mode は「安いメイン (Sonnet 帯) + 高いモデルへの R4a 委譲 (judge = Opus/Fable)」という**単価差**が動機になる。Codex の主力は `gpt-6.1-sol` であり、日常運用でメインを gpt-6-luna に固定するのは §1 の役割分担 (Sol=判断・主力, Luna=定型) から外れる
- 対応させる場合の読み替え: conductor = `gpt-6.1-sol` 起点のメイン、judge = `gpt-6-astra` への `spawn_agent`/`agents.<name>` 委譲 (R4a のみ、判断パケットを渡す)。conductor mode を使う利点は Codex では単価差そのものより、**判断をメインの会話コンテキストから隔離できること** (`08-conductor-mode.md` §3 の判断パケット規約と同じ理由) にある
- `judge`/`judge-fable` (Claude Code のサブエージェント定義) は Codex には存在しない。Codex で同等の役割を持たせる場合は `agents.judge` に `gpt-6-astra`（または `gpt-6.1-sol` + high）と `description` で判定専任ロールを定義し、Read 系ツールのみ渡す運用で近似する (本プラグインの `.mjs`/hook 資産は Claude Code 専用のため、判定はメイン側の運用規律で代替する)
- scope-guard 相当の PreToolUse 強制は Codex には存在しない (§3 で述べた `route-warn.mjs` 非対応と同じ理由)。範囲逸脱の検出は `route-policy.mjs auditManifest` の `SCOPE_EXPANSION` (マニフェストの自己申告検査) のみに依存する
