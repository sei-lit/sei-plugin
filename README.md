# sei-plugin

オリジナルスキル集。プロバイダー非依存(Claude Code / Codex など、どのAIエージェントからも使える)。

## これは何か

このリポジトリは Claude Code の**マーケットプレイス**であり、同時にその配下に**プラグイン**を1つ以上含む
モノレポです。マーケットプレイスは「プラグインのカタログ(索引)」、プラグインは「スキル・コマンド等をまとめた
配布単位」という関係になっています。

```
plugin/
├── .claude-plugin/
│   └── marketplace.json        # マーケットプレイス定義(プラグインの索引)
├── README.md
├── LICENSE
├── docs/
│   └── plugin-guide.md         # プラグイン機構の学習用ドキュメント
└── plugins/
    └── skill-kit/               # プラグイン: skill-kit
        ├── .claude-plugin/
        │   └── plugin.json      # Claude Code 向けプラグイン定義
        ├── .codex-plugin/
        │   └── plugin.json      # Codex 向けプラグイン定義
        ├── README.md
        └── skills/
            └── new-skill/
                └── SKILL.md      # スキル本体(素のMarkdown)
```

## インストール方法(利用者向け)

このリポジトリが GitHub 上の public リポジトリとして公開されていることが前提です。

Claude Code 上で以下を実行する。

```
/plugin marketplace add sei-lit/sei-plugin
/plugin install skill-kit@sei-plugin
```

## 設計原則

1. **スキル本体は素の Markdown で書く** — どの AI エージェント(Claude Code、Codex、その他)からも
   読める、プレーンな手順書として記述する。特定プロダクトの内部APIに依存させない。
2. **配線はプロバイダーごとのディレクトリに隔離する** — Claude Code 固有の配線は `.claude-plugin/` に、
   Codex 向けの配線は `.codex-plugin/` に分離し、スキル本体(`skills/`)には持ち込まない。
3. **1スキル1ディレクトリ、長文資料は `references/` に分割する** — SKILL.md は概要と手順の見出しに
   留め、詳細な仕様書や長いサンプルは `references/*.md` に切り出す(プログレッシブ・ディスクロージャー)。

## スキルの増やし方

新しいスキルを追加したいときは `/skill-kit:new-skill` を使う。雛形の生成からバージョン更新までの
手順が案内される。

## 公開手順

GitHub の public リポジトリ https://github.com/sei-lit/sei-plugin として公開されている。
変更を公開するには commit して push するだけでよい。

```bash
git add -A && git commit -m "..." && git push
```

利用者側には `/plugin marketplace update sei-plugin` で更新が届く
(バージョンをピン留めしているため、`plugin.json` / `marketplace.json` の version を上げること)。
