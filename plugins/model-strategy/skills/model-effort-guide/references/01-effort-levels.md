# effort パラメータの使い分け

> **典拠**: platform.claude.com — Effort Parameter / Model Migration Guide (claude-api skill 経由、2026-06-04 時点キャッシュ)。§1 のモデル別対応表と既定は code.claude.com/docs/en/model-config で 2026-07-23 に再検証済み。

## §1 effort とは

`output_config.effort` はモデルの「思考の深さと総トークン消費」を制御するパラメータ。**低い effort = ツール呼び出しが少なく統合され、前置きが減り、確認が簡潔になる** = output 課金が直接減る。

- 現行 Claude Code CLI が受理する値: `low` / `medium` / `high` / `xhigh` / `max`（`claude --help` で確認、2026-07-23）
- モデル別対応（典拠: code.claude.com/docs/en/model-config「Adjust effort level」、2026-07-23 確認。**表にないモデルは effort 非対応**）:

| モデル | 対応レベル | Claude Code 既定 |
| --- | --- | --- |
| Fable 5 | `low` / `medium` / `high` / `xhigh` / `max` | `high` |
| Sonnet 5 / Opus 4.8 / Opus 4.7 | `low` / `medium` / `high` / `xhigh` / `max` | `high`（**Opus 4.7 のみ `xhigh`**） |
| Opus 4.6 / Sonnet 4.6 | `low` / `medium` / `high` / `max`（`xhigh` 非対応） | `high` |
| Haiku 4.5 / Opus 4.5 以前 | 非対応（表に列挙されていない） | — |

- 非対応レベルを指定した場合、Claude Code は「指定以下で最も高い対応レベル」へフォールバックする（例: Opus 4.6 で `xhigh` → `high` 実行）。組織側でレベル上限が設定されている場合もある

## §2 レベル別ガイド

| Level | 用途 | コスト感 |
| --- | --- | --- |
| `max` | 正確性がコストより重要な最難関タスク。過剰思考のリスクあり、収穫逓減 | 最大 |
| `xhigh` | コーディング・エージェント的長時間タスクの本命 (Opus 4.7/4.8) | 大 |
| `high` | **品質とトークン効率のスイートスポット**。知的タスクの推奨最低ライン | 中 |
| `medium` | コスト重視で知性を少し妥協できる定常作業 | 小 |
| `low` | サブエージェント・単純タスク・レイテンシ重視 | 最小 |

## §3 モデル別の重要な知見 (典拠: Migration Guide)

### Opus 4.8
- 「反射的に xhigh」ではなく **`high` を起点に上下を試す**のが公式推奨
- **effort とコストの関係は単調ではない**: エージェント作業では高 effort が往復回数を減らし、総コストがむしろ下がることがある。逆に `medium` で同等品質がより短時間で出るタスクもある
- 自分のタスクで `medium` / `high` / `xhigh` をスイープして経路ごとに固定するのが正攻法

### Fable 5
- **`low` でも従来モデルの `xhigh`〜`max` を超える品質が出ることが多い**(公式記載)。Fable 5 を使うときほど effort を下げる余地がある
- 高 effort ではルーチン作業に対して過剰なコンテキスト収集・熟考をしがち。正しく完了するのに時間がかかりすぎる場合は effort を下げる
- **thinking は常時オン**(オフにできない)。思考トークンも output 課金されるため、同じタスクでも他モデルよりトークン消費が多くなりやすい。サブスクでも Fable 5 は usage credits（API 単価。`00-pricing.md` §4）なので、**コスト温存の観点でも既定を `high` ではなく `medium`〜`high` に置き、`xhigh`/`max` は最難関のみに限定**するのが効率的
- 単発の難問なら「Fable 5 (low〜medium)」が「Opus 4.8 (xhigh)」より安く良い結果になるケースがある。迷ったら両者を同一タスクで比較して経路を固定する

### Sonnet 5
- Sonnet 帯で初めて `xhigh` に対応。`medium` ≈ Sonnet 4.6 の `high`、`high` ≈ Sonnet 4.6 の `max` に相当(公式マッピング)
- adaptive thinking がデフォルトでオン(4.6 はオフ)。thinking 分の output 課金が増えるので、定型用途は `thinking: disabled` か effort `low` を明示する

### Sonnet 4.6
- デフォルトが `high` なので、チャット的・定型的な用途では明示的に `low`/`medium` に下げないと過剰消費する

## §4 Claude Code での設定方法

- メインセッション: `/model` でモデルと effort を選択 (例: Opus (high))
- サブエージェント: agents 定義の frontmatter `model:` でモデル指定(effort はモデル既定に従う)
- 迷ったら: **メイン high、サブエージェント low〜medium** から始めて、品質不足を感じた経路だけ上げる
