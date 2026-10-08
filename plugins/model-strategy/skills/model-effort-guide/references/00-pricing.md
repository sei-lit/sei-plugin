# モデル価格とコスト構造

> **典拠**: platform.claude.com — Pricing / Models overview / Model deprecations / Release notes、code.claude.com/docs/en/model-config、support.claude.com「Claude Fable models on your plan」（いずれも 2026-10-08 に公式ページで確認）。最新値は `https://platform.claude.com/docs/en/about-claude/pricing` を参照すること。
>
> **サブスクリプションとの関係**: Claude Code のサブスク利用では、Fable 系だけが §4 の条件で扱いが異なる。他モデルはサブスク枠内。本書の API 価格は「usage credits の単価」および「委譲でどれだけ枠消費を減らせるか」の基準として読む。

## §1 価格表 (per 1M tokens、2026-10-08 公式ページ照合済み)

現行モデル（Claude Code のエイリアスの解決先）:

| Model | Model ID | Claude Code エイリアス | 公開日 | Context | Input | Output | Output 単価 (Opus 5.5=1) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Claude Fable 5.1 | `claude-fable-5-1` | `fable` | 2026-09-01 | 1M | $10.00 | $50.00 | 2.5x |
| Claude Opus 5.5 | `claude-opus-5-5` | `opus`（全プランの既定モデル） | 2026-09-22 | 1M | $4.00 | $20.00 | 1x |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | `sonnet` | 2026-09-28 | 1M | $2.00 | $10.00 | 0.5x |
| Claude Haiku 5.5（プロンプト 100K 以下） | `claude-haiku-5-5` | `haiku` | 2026-10-07 | 1M | $0.10 | $0.50 | 0.025x |
| Claude Haiku 5.5（プロンプト 100K 超） | 同上 | 同上 | 同上 | 1M | $0.50 | $2.50 | 0.125x |

旧世代（引き続き利用可能）:

| Model | Model ID | Context | Input | Output |
| --- | --- | --- | --- | --- |
| Claude Fable 5 | `claude-fable-5` | 1M | $10.00 | $50.00 |
| Claude Opus 5 / 4.8 / 4.7 / 4.6 | `claude-opus-5` など | 1M | $5.00 | $25.00 |
| Claude Sonnet 5 | `claude-sonnet-5` | 1M | $2.00 | $10.00 |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | 1M | $3.00 | $15.00 |
| Claude Haiku 4.5 | `claude-haiku-4-5` | 200K | $1.00 | $5.00 |

- Sonnet 5 の $2/$10 は導入時に 2026-08-31 までの intro 価格とされていたが、2026-08-10 に標準価格へ変更された。$3/$15 への値上げは行われない
- Haiku 4.5 の最短廃止日は 2026-10-15。Sonnet 4.5 は 2026-09-30 に非推奨化され、2026-11-30 に廃止予定
- Haiku 5.5 は 4.6 以降のモデルで唯一、プロンプト長で単価が変わる。100K トークンを超えると input・output とも 5 倍になる
- エイリアスの解決先は Anthropic API の場合。Bedrock / Google Cloud / Foundry / Claude Platform on AWS では `sonnet` `haiku` が旧モデルに解決される（model-config 参照）

### トークナイザと実効コスト

Opus 4.7 以降のモデル（Fable 5 / 5.1、Opus 4.7〜5.5、Sonnet 5 / 5.5、Haiku 5.5）は同じ系統の新トークナイザを使い、Sonnet 4.6 / Haiku 4.5 以前より同じ文章で約 30% 多くトークン化される。この系統の中で移行するならトークン数はほぼ変わらない。

- Fable 5.1 対 Opus 5.5: トークン数は同等なので、名目どおり **約 2.5 倍**
- Haiku 5.5 対 Haiku 4.5: 名目では 1/10 だが、トークン数が約 1.3 倍になるため実効では **約 1/7.7**
- Sonnet 5.5 対 Sonnet 4.6: 名目では 2/3 だが、実効では **約 0.87 倍**

## §2 コスト構造の直感

エージェント的な作業（コーディング・調査）では **output トークンが支配的**。thinking トークンも output として課金される。つまり:

- 「考える量・書く量」が多い作業ほどモデル単価差がそのまま効く
- 同じ実装作業を Opus 5.5 → Sonnet 5.5 に委譲すると output 課金が 20→10 で **50% 減**、Haiku 5.5 なら **97.5% 減**（プロンプト 100K 以下の場合）
- input 側はプロンプトキャッシュで大きく圧縮できる（§3、`03-cost-levers.md`）
- `haiku-scout` に渡す依頼と読み込ませる範囲は 100K トークン以下に収める。超えると Haiku 5.5 の単価が 5 倍になり、Sonnet 5.5 との差が 4 倍まで縮む

### 概算例: output 100万トークン分の作業

| 担当 | コスト |
| --- | --- |
| Fable 5.1 | $50 |
| Opus 5.5 | $20 |
| Sonnet 5.5 | $10 |
| Haiku 5.5 | $0.50（100K 超のプロンプトでは $2.50） |

## §3 キャッシュ・バッチ・fast mode の価格

| 項目 | 価格 |
| --- | --- |
| キャッシュ書き込み (5分 TTL) | base input の 1.25 倍 |
| キャッシュ書き込み (1時間 TTL) | base input の 2 倍 |
| キャッシュ読み取り | base input の 0.1 倍。ただし **Fable 5.1 は 0.025 倍**（$0.25）、**Opus 5.5 / Sonnet 5.5 は 0.05 倍**（$0.20 / $0.10） |
| Batches API | 全トークン 50% off（非対話・最大24h、API 直叩きのみ。Fable 5.1 なら $5/$25、Opus 5.5 なら $2/$10） |
| fast mode（research preview、Claude API のみ） | Opus 5.5: $8/$40、Opus 5 / 4.8: $10/$50。Batch とは併用不可 |
| `inference_geo: "us"` | 4.6 以降のモデルで全単価 1.1 倍 |

Fable 5.1 / Opus 5.5 / Sonnet 5.5 はキャッシュ読み取りが旧世代より安いため、長い会話を同じモデルで続ける場合の input コストは旧世代より下がる。

## §4 Fable のサブスクリプション提供条件

Fable 5 / 5.1 はサブスクリプションでの扱いがプランとシートで異なる（support.claude.com の 2026-09-02 付の記事を 2026-10-08 に確認）。

| プラン / シート | Fable 5 / 5.1 の扱い |
| --- | --- |
| Pro | プラン枠に含まれない。usage credits のみ |
| Max 5x / 20x | **週の利用上限の 50% まで**プラン枠で使える（上限への上乗せではない）。超えたら usage credits か別モデルへ切り替え |
| Team premium シート | Max と同じ |
| Team standard シート | usage credits |
| Enterprise（シート制）premium シート | Max と同じ |
| Enterprise（シート制）standard シート | 組織が有効化している場合のみ usage credits |
| Enterprise（従量制）・API | API 標準単価 |

- usage credits は API 標準単価（$10/$50）で課金される
- Claude Code の `/model` では、credits が必要な場合 Fable の行に「Requires usage credits」と表示される。対話セッションでは課金前に確認が出るが、`-p` と Agent SDK では**確認なしで credits を消費する**
- セーフガードの分類器が一部リクエストを拒否することがあり、通常のコーディングでも誤検知が起こりうる。Fable 前提のワークフローを組まない
- 経緯: Fable 5 は 2026-06-09 提供開始 → 06-12 一時停止 → 07-01 再提供。全有料プランで週上限の 50% まで含める措置は 2026-07-19 に終了し、Pro と Team standard シートは credits 制になった。Fable 5.1（09-01 公開）はこの措置の対象外

**運用への含意**（詳細は `02-decision-matrix.md` §7）: Pro では Fable は常に API 単価で、Max でも Fable を使った分だけ週の枠が減る。Opus 5.5 は公式発表で「ほとんどの作業で Fable 5.1 と同水準」とされ、単価は 2.5 分の 1。Fable は「Opus 5.5 で解けなかった判断タスク」に限定し、定型・実装は Opus / Sonnet / Haiku に流す。
