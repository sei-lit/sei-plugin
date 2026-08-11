# プラグインシステムの仕組み(入門ガイド)

このドキュメントは、Claude Code のプラグインシステムがどう成り立っているかを初学者向けに解説します。

## 1. 階層関係

Claude Code のエコシステムは、大きく次のような階層になっています。

```
マーケットプレイス (marketplace)
└── プラグイン (plugin) ×N
    ├── スキル (skill)     … Markdown で書かれた手順書。会話の文脈に応じて自動的に読み込まれる
    ├── コマンド (command)  … "/foo" のように明示的に呼び出すスラッシュコマンド
    ├── エージェント (agent) … 特定の役割・ツール制限を持つサブエージェント定義
    └── フック (hook)      … ツール実行の前後などに自動発火する処理
```

- **マーケットプレイス**は「どのプラグインが存在するか」を列挙するカタログです。
  実体は `.claude-plugin/marketplace.json` という1つのJSONファイルです。
- **プラグイン**は、スキル・コマンド・エージェント・フックなどをまとめた配布単位です。
  1つのマーケットプレイスに複数のプラグインを登録できます。
- **スキル**はプラグインの中に複数入れられる、最も基本的な構成要素です。
  このリポジトリの `skill-kit` プラグインには `new-skill` という1つのスキルが入っています。
- コマンド・エージェント・フックは今回のテンプレートには含まれていませんが、
  同じプラグインディレクトリ配下に `commands/` `agents/` `hooks/` のような形で追加していけます。

利用者から見ると、「マーケットプレイスを追加する」→「その中のプラグインをインストールする」→
「プラグインの中のスキルが会話中に自動的に使われる」という流れになります。

## 2. marketplace.json のフィールド解説

`.claude-plugin/marketplace.json` の実例(このリポジトリのもの):

```json
{
  "name": "sei-plugin",
  "owner": {
    "name": "sei-lit"
  },
  "metadata": {
    "description": "Original skills by sei-lit. ...",
    "version": "0.1.0"
  },
  "plugins": [
    {
      "name": "skill-kit",
      "source": "./plugins/skill-kit",
      "description": "Meta-plugin for growing an original skill collection...",
      "version": "0.1.0",
      "category": "productivity",
      "tags": ["skill-authoring", "scaffolding", "meta"]
    }
  ]
}
```

- `name`: マーケットプレイス自体の識別子。`/plugin marketplace add` 等で参照される。
- `owner`: マーケットプレイスの所有者情報。
- `metadata.description` / `metadata.version`: マーケットプレイス全体の説明とバージョン。
- `plugins`: 配下のプラグインの一覧。各要素が1つのプラグインに対応する。
  - `source`: プラグイン本体があるディレクトリへの相対パス。
  - `version`: このマーケットプレイスが把握しているプラグインのバージョン
    (プラグイン自身の `plugin.json` の `version` と一致させておく)。
  - `category` / `tags`: 検索・分類用のメタ情報。

## 3. plugin.json のフィールド解説

`plugins/skill-kit/.claude-plugin/plugin.json` の実例:

```json
{
  "name": "skill-kit",
  "version": "0.1.0",
  "description": "Meta-plugin for growing an original skill collection...",
  "author": {
    "name": "sei-lit"
  },
  "homepage": "https://github.com/sei-lit/sei-plugin/tree/main/plugins/skill-kit",
  "repository": "https://github.com/sei-lit/sei-plugin",
  "license": "MIT",
  "keywords": ["skill-authoring", "scaffolding", "meta", "provider-agnostic"]
}
```

- `name` / `version` / `description`: プラグイン自身の識別子・バージョン・説明。
  `version` はマーケットプレイス側の `plugins[].version` と同期させる。
- `author` / `homepage` / `repository` / `license`: 配布情報。
- `keywords`: 検索用のタグ。

Codex 向けの `plugins/skill-kit/.codex-plugin/plugin.json` は基本的に同じ内容ですが、
`"skills": "./skills/"` という追加フィールドを持ちます。これは Codex CLI がスキルディレクトリの
場所を機械的に見つけるためのものです。Claude Code 側は `skills/` ディレクトリを規約(暗黙のルール)
として自動的に探すため、この明示的なフィールドを必要としません。このように、同じプラグインでも
「実行系ごとに必要な配線情報」を別ファイルに分離しておくことで、片方の仕様変更がもう片方に影響しない
ようにできます。

## 4. SKILL.md の frontmatter 仕様と発動の仕組み

各スキルは `skills/<skill-name>/SKILL.md` というファイルで、先頭に YAML frontmatter を持ちます。

```yaml
---
name: new-skill
description: このマーケットプレイスに新しいオリジナルスキルを追加するときの雛形生成と手順ガイド。「新しいスキルを作りたい」「スキルを追加して」「add a skill」「scaffold a skill」の要求時に使用。
---
```

必須フィールドは2つだけです。

- `name`: スキルの識別子。ディレクトリ名と一致させる。
- `description`: **スキルがいつ発動すべきかを表す文章**。

`description` が重要なのは、Claude Code はすべてのスキルの `description` を常に把握しており、
ユーザーの発言や会話の文脈がその `description` に合致すると判断したときに、
該当する SKILL.md の本文を読み込んで手順に従う、という仕組みになっているからです。
つまり `description` は「この本を読むべきタイミングを書いた背表紙」のような役割を持ちます。
トリガーとなる語句(日本語・英語どちらも)を具体的に書いておくほど、
意図した場面で正しく発動しやすくなります。

## 5. プロバイダー非依存にするための指針

このリポジトリのスキルは、Claude Code 専用ではなく、Codex など他のエージェントからも
利用できることを意図しています。そのための指針は以下の3点です。

1. **スキル本体は素の Markdown で書く**
   特定製品にしかない機能(内部API・特殊なツール名など)を前提にした手順にしない。
   「人間が読んでもそのまま実行できる手順書」として成立させる。
2. **配線はプロバイダーごとのディレクトリに隔離する**
   Claude Code 固有の設定は `.claude-plugin/`、Codex 向けの設定は `.codex-plugin/` に置き、
   スキル本文(`skills/`)には持ち込まない。こうすることで、片方のプロバイダーの仕様が変わっても
   スキル本体を書き直さずに済む。
3. **ツール名やファイルパスの書き方に注意する**
   `Task` や `Agent` のような特定プロダクト固有のツール名に依存する手順を書く場合は、
   「Claude Code では X、Codex では Y」のように両方の実行系での対応を併記する。
   ファイル参照はプラグインルートからの相対パス(論理パス)で書き、Claude Code では
   `${CLAUDE_PLUGIN_ROOT}` という環境変数で解決できることを併記しておく。

## 6. バージョニングと更新フロー

- プラグイン作者側は、スキルを追加・変更するたびに以下を更新する。
  1. `plugins/<plugin>/.claude-plugin/plugin.json` の `version`(patch を上げる)。
  2. `plugins/<plugin>/.codex-plugin/plugin.json` の `version`(同じ値に合わせる)。
  3. ルートの `marketplace.json` の該当エントリの `version` と、`metadata.version`。
- 利用者側は、マーケットプレイスを最新化するコマンド(例: `/plugin marketplace update sei-plugin`)
  を実行することで、プラグインの更新を取得できる。バージョン番号が一致していることで、
  「マーケットプレイスが把握しているバージョン」と「実際にインストールされるプラグインのバージョン」の
  食い違いを防げる。
