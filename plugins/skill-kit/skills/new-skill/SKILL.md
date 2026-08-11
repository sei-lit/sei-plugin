---
name: new-skill
description: このマーケットプレイスに新しいオリジナルスキルを追加するときの雛形生成と手順ガイド。「新しいスキルを作りたい」「スキルを追加して」「add a skill」「scaffold a skill」の要求時に使用。
---

# new-skill: 新規スキルの雛形生成ガイド

## 目的

このスキルは、`plugins/<plugin>/skills/<skill-name>/SKILL.md` の雛形を生成し、関連する
`plugin.json` / `marketplace.json` のバージョン更新までを一貫して行うための手順書です。
スキルを追加するたびに毎回同じ判断(命名・frontmatter・分割・バージョニング)をやり直さずに済むようにします。

## 手順

### 1. スキル名とプラグインを決める

- スキル名は小文字ケバブケース(例: `fetch-weather`, `summarize-pdf`)。動詞始まりを推奨する
  (例: `new-skill` のように「何をするか」が名前から分かるようにする)。
- ディレクトリ名 = frontmatter の `name` になるので、この時点で確定させる。
- どのプラグインに属させるかを決める。
  - 既存プラグイン(例: `skill-kit`)にスキルを追加する場合は、そのプラグイン配下の `skills/` を使う。
  - 新規プラグインを作る場合は `plugins/<new-plugin>/.claude-plugin/plugin.json` と
    `plugins/<new-plugin>/.codex-plugin/plugin.json` を用意し、ルートの `marketplace.json` の
    `plugins` 配列にエントリを追加する。

### 2. `skills/<skill-name>/SKILL.md` を作成する

frontmatter に必須なのは `name` と `description` の2つだけです。

- `name`: ディレクトリ名と完全に一致させる。
- `description`: **いつこのスキルを発動すべきか(トリガー条件)を必ず含める**。
  日本語トリガー語(ユーザーが実際に打ちそうな日本語表現)も併記すること。
  英語トリガー語だけだと日本語での呼びかけに反応できない。

本文はスキルの目的・手順・(必要なら)テンプレートを記述する。

### 3. 長い参考資料は references/ に分割する

SKILL.md 自体は「概要 + 手順の見出し」程度に留め、詳細な仕様書・APIリファレンス・長いサンプルコードなどは
`skills/<skill-name>/references/*.md` に分割する(プログレッシブ・ディスクロージャー)。
SKILL.md からはプラグインルート相対パスで参照する。

```
skills/<skill-name>/
├── SKILL.md
└── references/
    └── detail.md
```

### 4. プロバイダー非依存の原則を守る

スキル本文は「Claude Code 固有機能を前提にしない、素の Markdown 手順書」として書くこと。

- 特定ツール名(`Task`/`Agent` など Claude Code 固有の機能名)に依存する手順を書く場合は、
  「Claude Code では X、Codex では Y」のように両方の実行系での振る舞いを併記する。
- ファイル参照はプラグインルートからの論理パス(`PLUGIN_ROOT` 相対)で書く。
  - Claude Code では実行時に `${CLAUDE_PLUGIN_ROOT}` という環境変数が使えるので、
    例えば `${CLAUDE_PLUGIN_ROOT}/skills/new-skill/references/detail.md` のように書ける。
  - Codex など他のエージェントでは同等の変数がない場合があるため、
    「プラグインルートからの相対パス `skills/new-skill/references/detail.md`」という説明も併記しておくと安全。

### 5. バージョンを更新する

スキルを追加・変更したら、以下の3箇所のバージョンを同期させる。

1. `plugins/<plugin>/.claude-plugin/plugin.json` の `version` を patch (例: `0.1.0` → `0.1.1`) 上げる。
2. `plugins/<plugin>/.codex-plugin/plugin.json` の `version` も同じ値に合わせる。
3. ルートの `.claude-plugin/marketplace.json` について、
   - `plugins` 配列の該当エントリの `version` を同じ値に合わせる。
   - `metadata.version`(マーケットプレイス全体のバージョン)も更新する。

### 6. 動作確認

- ローカルに `claude` CLI があり `claude plugin validate .` が使える場合はそれを実行する。
- 使えない場合は、変更した(または新規作成した)すべての JSON ファイルに対して
  `python3 -m json.tool` を実行し、構文エラーがないことを確認する。

```bash
python3 -m json.tool .claude-plugin/marketplace.json > /dev/null
python3 -m json.tool plugins/<plugin>/.claude-plugin/plugin.json > /dev/null
python3 -m json.tool plugins/<plugin>/.codex-plugin/plugin.json > /dev/null
```

## SKILL.md 雛形

以下をコピーして `skills/<skill-name>/SKILL.md` として保存し、`<...>` の部分を埋める。

```markdown
---
name: <skill-name>
description: <このスキルが何をするか>。<トリガーとなる日本語フレーズ>「<例1>」「<例2>」、<英語トリガー> "<example>" の要求時に使用。
---

# <skill-name>: <一行タイトル>

## 目的

<このスキルが解決する課題を1〜2文で>

## 手順

1. <ステップ1>
2. <ステップ2>
3. <ステップ3>

## 参考資料

詳細な仕様やサンプルは `skills/<skill-name>/references/detail.md` を参照
(Claude Code では `${CLAUDE_PLUGIN_ROOT}/skills/<skill-name>/references/detail.md`)。
```
