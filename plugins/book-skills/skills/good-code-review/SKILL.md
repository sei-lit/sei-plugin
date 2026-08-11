---
name: good-code-review
description: 書籍『Good Code, Bad Code』(Tom Long 著) の「コード品質の6つの柱」に基づいてコードをレビュー・設計チェックする。「Good Code観点でレビューして」「Good Code, Bad Codeの原則でチェック」「6つの柱でレビューして」"review with Good Code, Bad Code principles" の要求時に使用。
---

# good-code-review: 『Good Code, Bad Code』の6つの柱によるコードレビュー

## 出典と正確性

- 出典: Tom Long, *Good Code, Bad Code* (Manning, 2021)。日本語版『Good Code, Bad Code
  ~持続可能な開発のためのソフトウェアエンジニア的思考』(秀和システム, 2023)。
- 本スキルは書籍の手法を読者が自分の言葉で手順化したもので、原文の転載ではない。
- 章構成・6つの柱・4つのゴールの名称は Manning 公式 liveBook の公開目次で裏取り済み。
  細部のチェック項目は読者が日本語版と照合済み(2026-08-11)。

## 判断の最上位基準: 4つのゴール

すべての指摘は、最終的に以下のいずれかのゴールへの影響として説明できなければならない。
どのゴールも脅かさない指摘は好みの問題であり、指摘しないか優先度最低とする。

1. **動くこと** (Code should work)
2. **動き続けること** (Code should keep working) — 変更や環境変化で壊れない
3. **要件変化に適応できること** (Code should be adaptable to changing requirements)
4. **車輪の再発明をしないこと** (Code should not reinvent the wheel)

## レビュー手順

### 1. 対象と変更意図を把握する

差分だけでなく、そのコードが属する抽象化レイヤーと呼び出し側を確認する。
「このコードは何を約束しているか(コード契約)」を先に言語化する。

### 2. 6つの柱で走査する

各柱の詳細チェックリストは `references/pillars-checklist.md` を参照
(Claude Code では `${CLAUDE_PLUGIN_ROOT}/skills/good-code-review/references/pillars-checklist.md`)。

1. **読みやすいコードにする** (Make code readable)
2. **驚きを避ける** (Avoid surprises)
3. **誤用しにくいコードにする** (Make code hard to misuse)
4. **モジュール化されたコードにする** (Make code modular)
5. **再利用・汎用化しやすいコードにする** (Make code reusable and generalizable)
6. **テストしやすいコードにし、適切にテストする** (Make code testable and test it properly)

### 3. 指摘のフォーマット

各指摘に以下を付ける:

```
[柱N: <柱の名前>] <指摘の一文>
影響ゴール: <1-4のどれか>
重大度: high(ゴールを直接損なう) / medium(将来の変更で問題化) / low(改善提案)
根拠: <本書のどの考え方に基づくか。例: 「マジックバリューを返さない」(第6章)>
提案: <具体的な修正案>
```

### 4. バランスを取る

- 良い実践(柱に適合している箇所)も最低1つ挙げる。
- 過度な汎用化・過度な抽象化への指摘も対象。本書は「読みやすさ・単純さを犠牲にした
  将来への備え」を高品質とは見なさない。
- コーディング規約の好みと、柱に基づく指摘を混同しない。

## 発動パターン

- コードやPRを見せられて「Good Code観点で」「6つの柱で」と言われたとき
- 設計案に対して「誤用しにくいか」「テストしやすいか」の観点評価を求められたとき
