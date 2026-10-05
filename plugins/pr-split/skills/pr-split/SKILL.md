---
name: pr-split
description: 作りきったブランチの最終 diff を、依存グラフ由来の「木」構造のスタック PR 群へ分割する。「PR に分割して」「pr-split して」「スタックに切って」「この diff を複数 PR にして」、英語では "split this into stacked PRs" の要求時、または機能実装が完成して PR 化する段階で使用。
---

# pr-split: 完成ブランチからの木構造 PR 分割

## 目的

大きな機能を 1 ブランチで作りきってから細かい PR に割ると、普通は線形スタックになり、
途中の PR をレビューで直すたびに後続全部の rebase が要る。このスキルは分割の出力を
「実際の依存関係から導出した浅い木」（根 = 契約、枝 = 並列な実装群、葉 = つなぎこみ）
に変え、修正の波及を木の深さまでに抑える。

分割はすべて完成した diff からの事後導出で行う。事前の計画や予測は持ち込まない。
plan（どのファイルをどのノードに割るか）の設計と PR 本文の生成が AI の仕事で、
git / gh の操作は同梱スクリプトに任せる:

- Claude Code: `${CLAUDE_PLUGIN_ROOT}/skills/pr-split/scripts/pr-split.sh`
- その他のエージェント: プラグインルート相対 `skills/pr-split/scripts/pr-split.sh`

以下 `pr-split.sh` と表記する。前提ツールは git / jq / gh。
前提条件: 分割対象の最終状態がコミット済みで、動作確認が済んでいること。
途中の作業履歴は分割時に作り直される（各ノード = 最終状態からの 1 コミット）。

## 手順

### 1. プロジェクト設定を読む（無ければ作る）

対象リポジトリの `.pr-split/config.md` を読む。これは木の設計精度と PR 本文の質を
決めるリポジトリ固有知識の置き場で、雛形は
`skills/pr-split/references/plan-schema.md`（Claude Code では
`${CLAUDE_PLUGIN_ROOT}/skills/pr-split/references/plan-schema.md`）にある。内容:

- **中央ファイル**の列挙（ほぼ全変更が触るビルド設定・モジュール登録・DI 集約など）
- **verify コマンド**（PR 単体の受け入れ条件に相当するビルド/テストコマンド）
- **PR 本文の必須項目**（リポジトリの PR テンプレート・運用規則に合わせる）
- **粒度の教師例**（過去に評価の高かった分割の PR 番号と切り方）

**無ければこのステップで作る**: リポジトリの CLAUDE.md・PR テンプレート・
CONTRIBUTING・ビルド設定から推論して `.pr-split/config.md` に書き出し、
ユーザーに確認してもらう。一度書けば次回以降の分割が同じ前提で動く。
config.md はコミットしない運用（gitignore や `.git/info/exclude`）でもよい。

### 2. diff を把握して依存グラフを作る

```bash
git fetch origin main
git diff --name-status --no-renames "$(git merge-base origin/main HEAD)" HEAD
```

全変更ファイルの中身（新規の型定義か、実装か、登録・配線か）を確認し、
「どのファイルがどのファイルの型・シンボルを参照するか」を把握する。
rename は追跡しない（削除 + 追加の 2 ファイルとして別ノードに割り当ててよい）。

### 3. 木を設計する

各ノード = 1 PR。「1 PR = 独立して説明・テスト・マージできる 1 つの契約変更」を主基準に、
config.md の教師例の粒度に合わせる。木の形のルール:

- **根（契約ノード）**: 他ノードが依存する公開面（interface・モデル型）と
  **中央ファイル**をここに置く。中央ファイルを兄弟ノードに分けると、後から
  マージする側が必ずコンフリクトする
- **枝**: 契約にしか依存しない実装群（View 系 / ロジック系 / リソース）は兄弟として
  並列に生やす。兄弟同士でファイル・シンボルを参照させない
- **葉（つなぎこみノード）**: DI 登録・ルーティング・エントリポイントへの接続など
  「これを入れると機能がアプリから到達可能になる」変更は最後の葉に置く。
  途中の枝に置くと、未完成の機能が接続可能な状態で main に入る
- **合流（複数の枝に依存するノード）は部分的に線形化する**: parent は 1 つしか
  指定できないので、複数の枝の型を必要とするノードは、依存する枝の一方の末尾に
  もう一方の枝を続けて積み（その区間だけ線形にする）、その先端を親にする。
  幅を取れるのは互いに合流しない枝の間だけ
- 深さより幅を優先する。本質的な依存（コンパイルが通らない）以外で親子にしない

### 4. plan の作成と承認

`.pr-split/plan.json` に書く（スキーマは `pr-split.sh` のヘッダコメントと
references/plan-schema.md）。`verify_command` は config.md の verify コマンドを使う。

```bash
pr-split.sh validate
```

が通ったら、表示された木をユーザーに見せて承認を得る。**承認前に apply しない。**

### 5. ブランチ生成と検証

```bash
pr-split.sh apply     # 木の作成（FORCE=1 で作り直し）
pr-split.sh verify    # 各ノードのブランチで verify_command 実行
```

**verify が全ノード通るまで PR を作らない。** 失敗したノードは割り当ての誤り
（依存先が兄弟にある等）なので、plan を直して `FORCE=1` で apply からやり直す。
1 ノードだけ再検証するなら `NODE=<n> pr-split.sh verify`。

### 6. PR 本文と作成

各ノードの本文を `.pr-split/bodies/<n>.md` に書き、plan の `body_file` に指定する。
本文は config.md の必須項目に従う。最低限入れるべきは:

1. 仕様・設計の参照先（リンク）と、このノードが実装する範囲
2. この PR で確定する契約（公開面）の一覧
3. マージしただけで挙動が変わるか（接続済みか、追加のみで未接続か）
4. レビュアーが読む順

```bash
pr-split.sh prs       # push + gh pr create（DRAFT=1 で draft）
```

base は親ノードのブランチ（根は main）に自動でなる。

## 運用上の注意

- マージは根から順に merge commit で行う（squash / rebase merge だと親ブランチが
  main の祖先にならず、子の diff に親の変更が再出現する）。親がマージされて head
  ブランチが消えると、GitHub が子 PR の base を自動で main へ付け替える
- **push 済みブランチへの force-push は禁止**。レビュー履歴とレビュー中の diff 表示が
  壊れるため、`git push --force` / `--force-with-lease` を自分の判断で実行しない
- main が進んだときの追従は、source ブランチを rebase してから `FORCE=1` で apply
  し直すのが基本（木は生成物なので作り直しが正）。ただし push 済みブランチを
  作り直すと push 時に force-push が要るため、この方法は **push 前のノードにしか
  使えない**。push 済みノードを直す必要が出たら、そのノードブランチへの
  追加コミットで修正する
- レビュー指摘の反映は、指摘対象のノードブランチに直接コミットし、その内容を
  source ブランチにも反映して source と木の同期を保つ（再導出の自動化は未対応）
- 線形スタック用の既存ツール（rebase --update-refs 前提のスクリプト等）は木に
  使えないことが多い。併存させる場合は挙動を確認する

## 参考資料

plan / config.md のスキーマ詳細と実例は `skills/pr-split/references/plan-schema.md` を参照
（Claude Code では `${CLAUDE_PLUGIN_ROOT}/skills/pr-split/references/plan-schema.md`）。
