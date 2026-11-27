# report-kit

報告・調査のまとめ・説明の資料を、読まれるページにするためのプラグイン。

## 何が入っているか

- `skills/readable-artifact/` — Artifact（HTML のページ）を作る・直すときに、何を図にするか、文をどこまで削るか、
  どう確かめるかを決めるスキル。見た目と公開の決まりは組み込みの artifact-design、SVG の描き方は
  artifact-diagramming、グラフは dataviz に任せ、このスキルには複製しない。

| パス | 内容 |
| --- | --- |
| `skills/readable-artifact/SKILL.md` | 書く前に決めること（内容の形ごとの図）、文の量の上限、図の作り方、確かめ方、既にあるページの直し方 |
| `skills/readable-artifact/references/figure-patterns.md` | 写して使う図の雛形（SVG の依存の図、前と後、流れ、時期、比較の表、確かさのラベル、画像） |
| `skills/readable-artifact/references/verify.md` | 描画を見る手段と、見る点 |
| `skills/readable-artifact/references/improving.md` | 人の評価からケースを作り、検査とのずれを見て、決まりか数を直す手順 |
| `skills/readable-artifact/limits.json` | 文の量の上限と、ずれの境目の数。検査はここから読む。SKILL.md の表と同じ数であることをテストで確かめる |
| `skills/readable-artifact/CHANGELOG.md` | スキルの変更の記録（日付・変えた決まりの ID・きっかけ・前後の点） |
| `skills/readable-artifact/scripts/check_artifact.py` | 文の量と公開の決まりの検査。2 つの群（readability・publish）の点と、不合格の決まりの ID を出す。評価の記録からケースを作り（`--add-cases`）、全ケースの点と人の評価のずれを出す（`--cases`、`--compare`） |
| `skills/readable-artifact/scripts/render_check.py` | 手元の Chrome で PC とスマホの幅 × 2 つのテーマを撮り、はみ出しや SVG の文字の重なりを一覧にする |
| `skills/readable-artifact/tests/` | 2 つのスクリプトの受け入れテスト（`python3 -m unittest discover -s skills/readable-artifact/tests`。描画のテストは Chrome が無ければ飛ばす） |
| `skills/readable-artifact/tests/cases/` | 公開できるケース。実物を一般的な題材に書き換えた、悪い例（`before.html`）と良い例（`after.html`）の組。悪い例が評価の指す決まりで不合格、良い例がすべて合格になることをテストで確かめる |

前提: Python 3.9 以降（標準ライブラリだけ）。`render_check.py` は Chrome か Chromium を使い、macOS ではスマホの幅の画像の切り抜きに `sips` を使う。

## 使い方

```
/plugin install report-kit@sei-plugin
```

インストール後は `report-kit:readable-artifact` として読み込まれる。Artifact や HTML の報告を作る・直す依頼で
description の条件により発動するほか、`/report-kit:readable-artifact` で明示的に呼び出せる。

## 制約（既知）

- 文の量の上限は日本語の字数で決めてある。英語のページでは字数が多めに出る。
- 検査は `<figure>`・`<svg>`・`<table>`・`<img>`・`<pre class="mermaid">`・`role="img"` を図として数える。
  `<div>` で作った図は数えないので、この決まりより前に作ったページは、図があっても点が下がる。
  `<div>` の図も数える形は試したが、ラベルを箱に並べただけの図まで図と数え、`shape` が見逃すので採らなかった（CHANGELOG の 0.1.1）。
- 「前と後を左右に並べ、変わる所だけに色を付ける」ことは検査していない。前後を別々の節の文で書いたページは、`figure-first` で止まる。
- `<figure>` の中の文字は、図の説明（figcaption）と表のセルを除いて文の量に数えない。図の中に長い文を書いても検査は止めない。
- mermaid の図は公開先が描くもので、`render_check.py` では描かれない。
