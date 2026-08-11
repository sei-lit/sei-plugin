# skill-kit

オリジナルスキル集を育てていくためのメタプラグイン。

## 何が入っているか

- `skills/new-skill/` — このマーケットプレイスに新しいスキルを追加するための雛形生成・手順ガイド。
  スキルのディレクトリ構成、SKILL.md の frontmatter の書き方、`references/` への分割、
  プロバイダー非依存の書き方、バージョン更新の手順までをまとめている。

## new-skill スキルの使い方

Claude Code 上でこのプラグインをインストールした状態で、次のように呼びかける。

```
/skill-kit:new-skill
```

または「新しいスキルを作りたい」「スキルを追加して」のように自然文で依頼すると、
`description` のトリガー条件に合致して自動的に発動する。手順に従って
`skills/<skill-name>/SKILL.md` を作成し、`plugin.json` / `marketplace.json` の
バージョンを更新していく。
