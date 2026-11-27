# 評価からスキルを直す手順

人がページに付けた評価（良い・悪い）と、`check_artifact.py` の点を突き合わせ、食い違う所だけを直す。
決まりも数も、食い違い（以下「ずれ」）が出たときだけ変える。ずれが無ければ、ケースを足すだけで終える。

## 流れ

| 段 | すること | 出るもの |
| --- | --- | --- |
| 1 | 評価の記録の `status: open` の行から、ケースを作る | 1 件 1 フォルダ。行は `used` になる |
| 2 | 新しいケースの `rules` に、評価が指す決まりの ID を書く | case.json |
| 3 | 今の版で全ケースを採点し、結果を保存する | 前の JSON |
| 4 | ずれを読む。無ければここで終わる | ずれの一覧 |
| 5 | ずれの原因の決まりか数を直す | limits.json・検査・SKILL.md の差分 |
| 6 | 全ケースで採点し直し、新しいずれが無いことを見る | `--compare` の終了コード 0 |
| 7 | 変更の記録に 1 行書く | CHANGELOG.md |

定期の実行が受け持つのは 1〜4 と、5 の案（変える ID と数、`--limits` で試した点）まで。スキルを変える 5〜7 は PR で行う。

## 置き場所

場所は環境変数で渡す。実物のページは社内の中身を含むので、ケースはリポジトリに置かない。

| もの | 場所 |
| --- | --- |
| 評価の記録 | `$READABLE_ARTIFACT_FEEDBACK`（1 行 1 件の JSON。`verdict` は good・bad・mixed、`quote` は言われたことそのまま、`before`・`after` はページのファイル、`status` は open・used） |
| 実物のケース | `$READABLE_ARTIFACT_CASES`（手元） |
| 採点の結果 | `$READABLE_ARTIFACT_RUNS`（手元。日付ごとの JSON） |
| 公開できるケース | `skills/readable-artifact/tests/cases/`（題材を書き換えた悪い例と良い例。テストが使う） |
| 数 | `skills/readable-artifact/limits.json` |

## コマンド

`S` はスキルのディレクトリ（Claude Code では `${CLAUDE_PLUGIN_ROOT}/skills/readable-artifact`）。

```bash
check() { python3 "$S/scripts/check_artifact.py" "$@"; }   # bash と zsh のどちらでも動く形
mkdir -p "$READABLE_ARTIFACT_CASES" "$READABLE_ARTIFACT_RUNS"
# 1. ケースを作る
check --add-cases "$READABLE_ARTIFACT_FEEDBACK" --cases "$READABLE_ARTIFACT_CASES"
# 3. 採点して保存する（ずれがあると終了コード 1）
check --cases "$READABLE_ARTIFACT_CASES" --cases "$S/tests/cases" --json > "$READABLE_ARTIFACT_RUNS/$(date +%F)-before.json"
check --cases "$READABLE_ARTIFACT_CASES" --cases "$S/tests/cases"          # 人が読む形
# 5. 数を試す（limits.json を写して 1 か所変えたもの）
check --cases "$READABLE_ARTIFACT_CASES" --cases "$S/tests/cases" --limits /path/to/trial-limits.json
# 6. 直した後に比べる（前に無かったずれがあると終了コード 1）
check --cases "$READABLE_ARTIFACT_CASES" --cases "$S/tests/cases" --compare "$READABLE_ARTIFACT_RUNS/<日付>-before.json"
python3 -m unittest discover -s "$S/tests"
```

## ケースの形

`<ケース ID>/case.json` と、ページの写し（`before.html`・`after.html`）。

- `feedback`: 評価の記録の 1 行。`pages`: ページごとの `file`・`label`・元のパス・作ったときの点。`missing`: 写せなかったファイル。
- `label`: 評価は記録の target のページに付く。bad なら `before`、good と mixed なら `after` に付き、もう片方は `unrated`。
  bad で `before` が空の記録は、評価の付いたページが無いケースになる。
- `rules`: 作ったときは `null`。評価の言葉が指す決まりの ID を書く（例: 「図が無いと分からない」→ `shape`・`figure-first`、
  「文字が多い」→ `section-prose`・`page-prose`）。どの検査も扱わない観点なら `[]` と書き、`feedback.note` に観点を残す。
  同じ観点が 2 件たまったら、検査を足す案を出す。

## ずれ

判定は readability の点で行う（publish は人の評価と関係しない）。境目は limits.json の `gap.boundary`。

| key | 意味 | 直す向き |
| --- | --- | --- |
| `bad-high` | bad のページが境目以上 | 検査が見逃した。見逃した決まりを厳しくするか、検査を足す |
| `bad-rule-pass` | bad のページで、`rules` の決まりが合格 | その決まりの数か判定が甘い |
| `good-low` | good のページが境目未満 | 検査が厳しすぎる |
| `good-rule-fail` | good のページで不合格の決まり | その決まりが邪魔をした。誤って鳴っていないかを見る |
| `rules-unset` | 評価の付いたケースの `rules` が未記入 | 2 を行う |

`mixed` と `unrated` のページは点を出すだけで、ずれに数えない。`unrated` のページが低い点のときは、
人に評価を聞く候補として報告に書く。

## 直すとき

- 数だけを変える: limits.json の値と、SKILL.md の「文の量の上限」の表の同じ ID の行を変える。テストが両者の一致を確かめる。
  ほかの文書は数を書かずに表か limits.json を指しているので、直すのはこの 2 か所だけ。
- 判定を変える: `check_artifact.py` の検査を直し、`tests/test_check_artifact.py` にその場合のテストを足す。
- 検査の無い決まり（SKILL.md の文だけの決まり）を変えたときは、同じ依頼からページを作り直して前後を比べる。
  1 回ごとに費用がかかるので、決まりの文を変えたときだけ行う。
- 同じ検査を回しながら直したページは、その検査で 100 点になって当然。good のページの 100 点を、検査が正しい証拠にしない。

## 変更の記録

`skills/readable-artifact/CHANGELOG.md` の先頭に 1 行足す。プラグインの版は docs/plugin-guide.md の手順で patch を上げる。

```
- 2026-01-10 `section-prose` 300 → 280。きっかけ: 「節が長い」と言われた bad のページが合格していた（1 件）。ずれ 3 → 1、新しいずれ 0
```

きっかけの評価は一般化して書く（公開リポジトリなので、評価の言葉そのものや、実物の題を書かない）。
