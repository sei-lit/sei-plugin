# pr-split の plan / config スキーマ

## plan.json（`.pr-split/plan.json`）

分割 1 回ぶんの入力。完成 diff から毎回導出する使い捨てで、コミットしない。

```json
{
  "source": "feat-coin-marathon",
  "base": "origin/main",
  "branch_prefix": "20260910-coin",
  "verify_command": "./gradlew build",
  "nodes": [
    { "n": 1, "slug": "contract", "parent": null,
      "title": "feat: コインマラソンの UseCase interface とモデルを追加",
      "files": [
        "domain/usecase/src/commonMain/kotlin/.../GetMarathonStatusUseCase.kt",
        "domain/model/src/commonMain/kotlin/.../MarathonStatusDomainModel.kt",
        "settings.gradle.kts"
      ],
      "body_file": ".pr-split/bodies/1.md" },
    { "n": 2, "slug": "view", "parent": 1,
      "title": "feat: コインマラソンの画面 Composable を追加",
      "files": ["ui/screens/src/commonMain/kotlin/.../MarathonScreen.kt"],
      "body_file": ".pr-split/bodies/2.md",
      "verify_command": "./gradlew :ui:screens:build" },
    { "n": 3, "slug": "logic", "parent": 1,
      "title": "feat: コインマラソンの UseCase 実装を追加",
      "files": ["domain/usecaseimpl/src/commonMain/kotlin/.../GetMarathonStatusUseCaseImpl.kt"],
      "body_file": ".pr-split/bodies/3.md" },
    { "n": 4, "slug": "wiring", "parent": 3,
      "title": "feat: コインマラソンの ViewModel を DI に登録",
      "files": ["feature/src/commonMain/kotlin/.../MarathonViewModel.kt"],
      "body_file": ".pr-split/bodies/4.md" }
  ]
}
```

| フィールド | 必須 | 意味 |
| --- | --- | --- |
| `source` | - | 最終状態を持つ ref。省略時は現在のブランチ |
| `base` | - | 分割の比較先。省略時 `origin/main`。root ノードの PR の base はここから `origin/` を除いたものになる |
| `branch_prefix` | - | ブランチ名 `<prefix>-pr<n>-<slug>` の接頭辞。省略時は source のブランチ名 |
| `verify_command` | ※ | 各ノードのブランチ上で実行する検証コマンド。※全ノードが個別指定を持つ場合のみ省略可 |
| `nodes[].n` | ✓ | ノード番号。昇順・重複なしの正の整数。PR の説明順・作成順になる |
| `nodes[].slug` | ✓ | ブランチ名の一部。英小文字・数字・ハイフン |
| `nodes[].title` | ✓ | コミットメッセージ兼 PR タイトル |
| `nodes[].parent` | ✓ | 親ノードの n。`null` は base 直下（root）。必ず parent < n |
| `nodes[].files` | ✓ | このノードが担当する変更ファイル。base..source の全変更ファイルを全ノードでちょうど 1 回ずつ割り当てる |
| `nodes[].body_file` | prs 時 | PR 本文の Markdown ファイル |
| `nodes[].verify_command` | - | ノード個別の検証コマンド（plan 全体の値に優先） |

制約の背景:

- **1 ファイル = 1 ノード**（ハンク分割はしない）。1 ファイルを 2 つの PR に割りたく
  なったら、それは実装時にファイルを分けておくべきだったサイン
- **parent < n** が、n 昇順で作れば親が必ず先にあることと、循環が無いことを保証する
- 空コミットになるノード（担当ファイルの内容が親の時点と同一）はエラーになる

## config.md（`.pr-split/config.md`）

リポジトリ固有知識の置き場。分割のたびに使い回す。リポジトリの方針に応じて
コミットしてもよいし、gitignore / `.git/info/exclude` で管理外にしてもよい。

```markdown
# pr-split 設定（<リポジトリ名>）

## 中央ファイル（root ノードに集約する）
ほぼ全変更が触るファイル。兄弟ノードに分けるとマージ時に必ずコンフリクトする。
- settings.gradle.kts（モジュール追加）
- gradle/libs.versions.toml（依存追加）
- <DI やモジュール一覧を集約しているファイル>

## つなぎこみ（葉ノードに置く）
入れた時点で機能が到達可能になる変更。
- <DI 登録のアノテーション・ファクトリ登録>
- <ルーティング・エントリポイントへの追加>

## verify コマンド
- 既定: ./gradlew build
- 軽量版（枝ノード向け）: ./gradlew :<module>:build

## PR 本文の必須項目
- <リポジトリの PR テンプレート・運用規則に合わせて列挙>
- <例: 設計書リンク / 確定する契約の一覧 / リリース影響の分類 / レビュアーが読む順>

## 粒度の教師例
- <評価の高かった過去の分割: PR 番号と切り方のメモ>

## その他の注意
- <既存のスタックツールとの関係、マージ方式の指定など>
```

## よくある失敗と対処

| 症状 | 原因 | 対処 |
| --- | --- | --- |
| validate: 未割り当てファイル | diff の見落とし | 該当ファイルをいずれかのノードに追加 |
| verify が枝ノードで赤い | 依存先が兄弟ノードにある | 依存されるファイルを共通の祖先（多くは root）へ移すか、枝を部分線形化 |
| verify が root で赤い | 契約が実装に依存している（interface が impl の型を参照等） | 契約側の設計を見直すか、該当実装を root に含める |
| マージ後に兄弟がコンフリクト | 中央ファイルを兄弟に分けた | config.md の中央ファイル一覧に追記し、FORCE=1 で分割し直す |
| 空コミットエラー | 親ノードが子の担当ファイルまで先取りした | files の割り当てを見直す |
