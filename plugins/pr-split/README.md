# pr-split

作りきった機能ブランチの最終 diff を、実際の依存グラフから導出した「木」構造の
スタック PR 群へ分割するプラグイン。

## 解く問題

大きな機能を 1 ブランチで作りきってから細かい PR に割ると、普通は線形スタックになる。
線形スタックは途中の PR をレビューで直すたびに後続全部の rebase が要り、15 段を超えると
管理不能になる。一方で分割をやめると 1 PR が巨大になり、AI レビューにも人間レビューにも
必要なコンテキストを渡せない。

pr-split は分割の出力を「浅い木」に変える:

```
main ── pr1: 契約（interface・モデル・中央ファイル）
          ├─ pr2: View 実装      ←─ 兄弟は並列。互いに rebase 不要
          ├─ pr3: ロジック実装
          └─ pr4: つなぎこみ（DI 登録等。pr3 の子）
```

- 分割は**完成した diff からの事後導出**。事前の計画や予測は持ち込まない
- 各ノードは「単体でビルド・テストが通る」ことを `verify` で機械検証してから PR にする
- リポジトリ固有知識（中央ファイル・verify コマンド・PR 本文規則・粒度の教師例）は
  対象リポジトリの `.pr-split/config.md` に置き、プラグイン本体は汎用に保つ

## 構成

| パス | 内容 |
| --- | --- |
| `skills/pr-split/SKILL.md` | AI 向けの工程定義（diff 分析 → 木の設計 → 承認 → 生成 → 検証 → PR 作成） |
| `skills/pr-split/scripts/pr-split.sh` | 決定的なエンジン。`validate` / `apply` / `verify` / `prs` の 4 サブコマンド |
| `skills/pr-split/references/plan-schema.md` | plan.json / config.md のスキーマと実例、よくある失敗 |
| `skills/pr-split/tests/pr-split-test.sh` | self-contained な受け入れテスト（一時リポジトリ + gh スタブ。`./pr-split-test.sh` で実行） |

前提ツール: git / jq / gh（PR 作成時のみ）。bash は macOS 標準の 3.2 系で動く。

## 制約（既知）

- 1 ファイル = 1 ノード（ハンク分割はしない）
- 合流ノード（複数の枝に依存するつなぎこみ）は単一親の木で表現できないため、
  該当区間だけ部分的に線形化する
- レビュー指摘後の枝の再導出は未自動化（source ブランチと手で同期する）
- マージは merge commit 前提（squash / rebase merge は子 PR の diff を壊す）
