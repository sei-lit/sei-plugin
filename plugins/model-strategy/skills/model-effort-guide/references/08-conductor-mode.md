# conductor mode (v0.3.0)

> **前提**: 本書は `02-decision-matrix.md` の R4 (デフォルト・判断) を、`MODEL_STRATEGY_MODE=conductor` のときにさらに分割する追補である。ルールの正本は引き続き `scripts/route-policy.mjs` (`routeOperation` の `deriveR4Subtype` / `auditManifest`)。本書はその機序の解説と、機械検査が証明する範囲・証明しない範囲の明記に専念する。

conductor mode は、メインセッション (conductor) が Sonnet 級など判断に不向きなモデルであっても、R4 のうち「判断そのもの」を `judge` (Opus/Fable) へ委譲し、conductor は判断パケットの構成・実行の指揮・R4-ctx (会話文脈が本体の操作) に専念できるようにする運用モードである。既定は `judge-main` (メインが自ら R4 判断も担う) であり、conductor mode は明示 opt-in のみ。tier 推定からの自動切替はしない。

## §0 高保証 opt-in 時のマニフェストと出口監査

本節は、ユーザーが高保証のマニフェスト監査または conductor mode を明示的に指定した場合だけ適用する。通常の監査・レビュー依頼だけでは適用せず、conductor も自動有効化しない。マニフェスト監査だけを指定した場合は `judge-main` のまま本節を使い、§2〜§9 の conductor 固有手順は適用しない。

ルーティング確定後・実行開始前に予定担当を表示し、完了時に実効担当・状態・逸脱注記を突合して再掲する。表示は委譲対象 (R1〜R3) の件数に応じて簡潔にする:

- 0 件: 全て R0/R4 となった条件を添えた 1 行サマリ。
- 1 件: `割当: [R1] 構成調査 → haiku-scout (Haiku) ｜ [R4] 設計・受入 → メイン (<セッションの実モデル>)` の形式。
- 2 件以上: 作業 / ルール / 予定担当 / 実効担当 / 状態の表。完了時は差し戻し・逸脱注記も反映する。

モデル名は実際の担当モデルを記録する。マニフェストには操作記述子と予定担当 (`plannedAssignee`)、実効担当 (`actualAssignee`)、状態、逸脱理由 (`deviationNote`) を記録し、形式は `scripts/route-policy.mjs` の `auditManifest` に合わせる。

タスク完了時にマニフェストを JSON 化し、次で監査する (`PLUGIN_ROOT` は本プラグインのルート)。findings は完了報告に含める。Node.js が使えない場合は予定・実効担当と該当規則を手動で突合し、機械監査を実行できなかったことを記録する。

```bash
node "$PLUGIN_ROOT/skills/model-effort-guide/scripts/route-policy.mjs" audit < manifest.json
```

conductor で基準線ファイルを生成した場合は、監査と実効担当の記録後、§7 の手順で当該ファイルを削除する。

## §1 モード宣言

- `MODEL_STRATEGY_MODE` env: `conductor` | `judge-main` の閉じた enum。未設定は `judge-main`
- スキルはセッションモデルが Sonnet 級のとき conductor を**提案**してよいが、自動切替はしない (判断は常にユーザー)
- 委譲マニフェストに次の 3 フィールドを記録する:
  - `mode`: 実効モード (`conductor` | `judge-main`)
  - `modeSource`: `env` (環境変数由来) | `user-instruction` (会話内の明示指示) | `default` (未設定によるフォールバック)
  - `sessionModel`: セッションの実モデル名 (固定文字列で書かず、実際のモデル名を記入する。`03-cost-levers.md` 等と同じ規約)
- `mode`/`modeSource`/`sessionModel` のいずれかが欠落・enum 外であれば finding `MISSING_MODE_FIELDS`。`mode` を省略したマニフェストはどのモードの検査を適用するか決められないため、マニフェスト監査だけを使う場合も `mode: "judge-main"` を記録する
- 実効モードとセッションモデルの乖離を検出する finding `MODE_MODEL_MISMATCH`: `mode=conductor` かつ `sessionModel` が `opus`/`fable` を含む (conductor で高価なメインを使う意味が薄い)、または `mode=judge-main` かつ `sessionModel` が `sonnet` を含む (安いメインが judge を介さず自ら R4 判断をしている懸念)。小文字比較の部分一致で機械判定する

## §2 R4 の 3 分割

`deriveR4Subtype` (`route-policy.mjs`) が、R4 と判定された操作記述子の `ctxClass` / `packet` / `dependsOn` から機械導出する。conductor の自由分類は許さない。

| サブタイプ | 定義 | 担当 |
| --- | --- | --- |
| **R4-ctx** | `ctxClass` が閉じた許可リスト `CTX_CLASSES = ["commit-authoring", "user-communication"]` に所属する (会話文脈が本体の操作: commit 作成・ユーザー向け報告文) | conductor 残留 (main) |
| **R4a (closed)** | ctx でなく、判断パケットの必須 6 フィールド (`question` / `options` / `evidencePointers` / `constraints` / `acceptanceCriteria` / `impactScope`) が全て非空、かつ `dependsOn` (他 R4 行への依存宣言) が空 | `judge` |
| **R4b (adaptive)** | ctx でなく、パケットを書き切れない、または `dependsOn` が非空 | `session-escalation` (上位セッションへのタスク昇格を提案し、conductor は作業を止める) |

- `ctxClass` が `CTX_CLASSES` の enum 外の値であれば finding `INVALID_CTX_CLASS` を発火させたうえで、**判断型として扱う** (subtype は R4a/R4b の評価に落ちる)。自己分類の一語で `CONDUCTOR_EXECUTED_R4` (§8) を回避できる抜け道を塞ぐための設計
- パケット完結性の判定は R3 の `missingSpecFields` と同型の非空チェック (`nonEmptyString`)
- judge の「証拠不足」差し戻しが同一 R4a 行で 2 回連続した場合、conductor はその行を R4b へ昇格させる。これは `route-policy.mjs` が状態を追跡して自動判定するものではなく、**conductor が判断履歴を見て自ら行うプロトコル上の義務**である (route-policy.mjs はステートレスな単発 JSON I/O であり、複数回の呼び出しにまたがる履歴を保持しない)

## §3 judge / judge-fable

- `agents/judge.md` (`model: opus`) が R4a の判定担当。`agents/judge-fable.md` (`model: fable`) は同一プロトコルの**静的な別定義** — `judge` 呼び出し時の model override には依存しない (override はキャッシュ無効化・適用漏れの不確実性を持つため)。使用条件は `02-decision-matrix.md` §7 (Opus judge で 2 回失敗 / アーキテクチャ設計級の最難関判断)
- judge は Read/Grep/Glob を持ち、**ファイル証拠は judge 自身が一次ソースを読む**。conductor がパケットで運ぶのは会話にしか存在しない文脈 (ユーザー意図・交渉履歴・却下済み選択肢と理由) + 型付き証拠ポインタ (locator + 可能なら revision) + 出力 schema。conductor の**解釈**とパケットの**事実**は別フィールドとし、両者を混同しない
- judge 呼び出し不能時 (ツール不可・モデル非対応・エラー) は **fail-closed**: conductor は R4a を代行せず、停止してユーザーに問う。「judge が使えないので conductor が代わりに判断する」という迂回は許さない
- **上方委譲の禁止事項** (両方とも R4a に使用禁止):
  - `/model` による一時昇格: セッション全体のキャッシュを無効化し、コストがセッション長に比例してしまう。R4b の明示的セッション昇格 (ユーザーへの提案を経た `/model` 昇格または高価メインでの再開) 専用
  - fork subagent (`subagent_type: fork`): 親モデルを継承する機構であるため、そもそも上方委譲の手段になり得ない

## §4 受け入れの再ルーティング

タスクの「受け入れ」は独立した 1 操作として、P0→R4 で改めてルーティングする (実装タスクの一部として conductor が素通りで判定しない)。

- 確定済みコマンド (テスト・lint・ビルド) の実行結果を事実として確認するだけの受け入れ → R2
- 受け入れ基準 ↔ 実装差分 (diff) ↔ R2 検証記録の**三者突合**という意味解釈を要する受け入れ → R4a。diff はパケットで運ばず、judge がリポジトリで直接読む

diff を生んだタスクの受け入れは、この述語の性質上、必ず R4a に落ちる。したがって「終端の受け入れは常に judge を通る」という判定ゲートは、特別な追加ルールとしてではなく、**通常のルーティング規則を適用した帰結として無条件に成立する**。この機序が、§5 で述べる事前層の限界 (well-formed and traceable までしか証明しない) を補う唯一の semantic 保証点である。

## §5 R3 仕様の機械検査 — 証明範囲は well-formed and traceable まで

R3 行スキーマを次の 2 フィールドで拡張する:

- `contractRef`: タスク受け入れ基準への参照。必須。欠落 → finding `DANGLING_SPEC` (受け入れ基準を参照しない宙吊り仕様の検出)
- `verificationRef`: 完了時に必須。マニフェスト内の R2 行 `id` を参照する。参照先が存在しない、または参照先の `rule` が `R2` でない場合 → finding `UNFALSIFIABLE_VERIFICATION` (「目視で確認」の排除。反証可能な検証記録への参照を強制する)

`verify-evidence` サブコマンド (`route-policy.mjs verify-evidence`): stdin `{items:[{file, line, quote}]}` を受け取り、各 `quote` が `file` に文字どおり (exact substring) 存在するかを検査する。存在すれば実際の行番号と申告 `line` とのズレ (`lineDrift`) を返し、存在しなければ `found: false` を返す。幻覚引用・stale 引用の機械検出。

**この節の機械検査が証明するのは「well-formed (形式が整っている)」と「traceable (参照が解決する)」までであり、semantic correctness (その選択が正しいか) は証明しない。** 仕様中の選択のうち contract・ユーザー入力・リポジトリ事実のいずれにも根拠付けられないものを先行して R4a に出す判断は、`contractRef` の存在や引用の文字どおりの一致から機械的に導出できるものではない。もっともらしい `contractRef` を添えた誤った選択は、これらの機械検査を全て通過しうる。したがってこれは **conductor のプロトコル義務 (自己申告)** であり、機械述語ではない。事前層でこの種の誤仕様を機械的に捕捉できるという主張はしない — semantic な保証は §4 の終端受け入れ R4a のみが提供する backstop であり、事前層の機械検査はそれを補助する traceability チェックに留まる。

## §6 失敗シグナル (event → reroute/replan/block)

観測されたイベントの種類によって扱いを分ける。すべてを judge への短絡 (即 R4a 化) にはしない。

- **検証失敗**: R2 は事実報告のみで完結する。原因仮説の形成が必要になった**最初の時点**で R4 (`02-decision-matrix.md` §3 と整合。「2 回失敗したら」という回数規定は置かない)
- **implementer 差し戻し**: `sonnet-implementer` の報告が `blocked_on_decision` を返した**最初の返却**で、その未決事項を R4 化する (2 回待たない)
- **judge 差し戻し**: 「証拠不足」の差し戻しが同一 R4a 行で **2 回連続**した場合に限り、その行を R4b へ昇格する (§2 参照)
- **スコープ拡大**: マニフェスト凍結時 (実装開始前) に、全 R3 行の変更可能範囲 (glob 和集合) と `contractHash` を `baseline` としてマニフェストに記録する (ライフサイクルは §7)。拡大イベントは 3 種:
  1. 範囲外への `Edit`/`Write`/`NotebookEdit` (§7 の scope-guard hook が実行時に照合する。route-policy の finding ではなく hook の additionalContext 警告)
  2. 凍結後の `producesDiff` 行 (R3 行) 追加 (`addedAfterFreeze: true` かつ `deviationNote` なし → finding `SCOPE_EXPANSION`)
  3. `contractHash` の変化 (`baseline.contractHash` と `currentContractHash` の不一致 → finding `SCOPE_EXPANSION`)

  発生源で分類する: ユーザー起因の追加要求は正当な replan、実装中の発見に依存する追加は judge 相談または replan、**無断の範囲外 diff は audit failure** として `SCOPE_EXPANSION` を記録する。全てを「能力不足シグナル」に一様に畳まない
- テストの再失敗は「検証失敗」と同一性キー (検証コマンド + テスト ID) で統合し、二重計上しない。インフラ障害・権限エラー・既知の flaky はこの能力シグナルから分離する (原因診断が不要なため R4 に落とさない)
- 上記いずれかの失敗シグナルに由来する昇格は、R4a パケット (§2) を経由せず、直接 R4b (セッション昇格提案) に送る — 失敗から回復するための判断を、失敗の当事者である conductor が改めてパケット化する手順を踏ませない

## §7 scope-guard hook

`hooks/scope-guard.mjs` は `hooks/route-warn.mjs` とは**別エントリ**の PreToolUse hook (`Edit|Write|NotebookEdit` matcher)。

- **発火条件**: `MODEL_STRATEGY_MODE=conductor` かつ、基準線ファイル `${CLAUDE_PLUGIN_DATA}/scope-baseline-<session_id>.json` (`{manifestId, globs, contractHash}`) が存在する場合のみ
- **route-warn との差異**: **`agent_id` があってもスキップしない**。route-warn はメインセッションの直接実行だけを対象にする (サブエージェント呼び出し自体が委譲そのものだから) が、scope-guard は逆に `sonnet-implementer` 等サブエージェントの範囲外編集こそ検出対象であるため、`agent_id` の有無を判定に使わない
- 判定: `tool_input` の `file_path`/`notebook_path` が `globs` のいずれにも一致しなければ、`additionalContext` に 1 行警告を注入する (`SCOPE_EXPANSION` の記録と replan/judge 相談を促す)。glob は `*` (1 パス要素内)・`**` (パス区切りをまたぐ) のみサポートする自前変換 (依存追加なし)
- **warn-only・fail-open・重複抑制 (session, file_path)**: route-warn と同機構。deny はしない。基準線ファイルの読み書き失敗時は「基準線なし」として黙る (誤検知の連発を避けるため)。重複抑制状態の読み書き失敗時は抑制なしで警告を出して続行する (route-warn と同じ fail-open の向き)

### baseline のライフサイクル

- **生成**: conductor かつ R3 行がある場合、実装開始前・R3 委譲前のマニフェスト凍結時に、全 R3 行の変更可能範囲の glob 和集合と、その時点の受け入れ基準を同じ方法でハッシュ化した `contractHash` を確定する。Claude Code が提供する `CLAUDE_PLUGIN_DATA` 配下の `scope-baseline-<session_id>.json` に次の JSON を書き、同じ内容を `manifest.baseline` にも記録する。`session_id` は実際の対象セッション ID、`manifestId` は対象マニフェストの一意 ID を用いる。保存先やセッション ID が取得できない場合は基準線未生成として報告し、共有 `/tmp` 等で代用しない。

  ```json
  {
    "manifestId": "<対象マニフェストの一意 ID>",
    "globs": ["<R3 行の変更可能範囲の glob>"],
    "contractHash": "<凍結時の受け入れ基準のハッシュ>"
  }
  ```

  受け入れ基準が変わった場合は同じ方法で `currentContractHash` を算出し、マニフェストに記録する。監査前に凍結済み baseline を上書きして変化を隠さない。
- **束縛**: ファイル名の `session_id` (セッションに束縛) + 内容の `manifestId` (どのマニフェストの基準線かを一意化)。並行セッションや前タスクの古い基準線による誤発火・見逃しを避ける
- **破棄**: タスク完了時、§0 の監査後に conductor が `${CLAUDE_PLUGIN_DATA}/scope-baseline-<session_id>.json` の `manifestId` と当該タスクの ID の一致を確認し、そのファイルだけを削除する。別セッションや別マニフェストの基準線は削除しない。削除できなかった場合は完了報告に残す
- **不発検出**: 基準線を書く規約自体が守られなければ hook は永久に不発になる (「沈黙のまま死ぬ」故障)。これを検出するため、`mode=conductor` かつ R3 行が存在するのに `baseline` がマニフェストに記録されていない場合、finding `MISSING_BASELINE` を発火する

### 既知の迂回

**Bash 経由のファイル書き込みは観測できない。** `tool_input` に `file_path`/`notebook_path` を持つのは `Edit`/`Write`/`NotebookEdit` のみであり、`Bash` 経由の任意コマンドによるファイル変更 (`sed -i`、リダイレクト等) は matcher の対象外である。scope-guard は「唯一の強制点」ではなく、**部分的な機械照合**にすぎない。この限界を前提に運用すること — scope-guard が警告を出さないことは「範囲外編集がなかった」ことの証明にはならない。

## §8 finding の優先順位

conductor mode で判断型 R4 行 (ctx 以外) の `actualAssignee` が `conductor`/`main` であれば `CONDUCTOR_EXECUTED_R4` が発火する。`deviationNote` による正当化はできない — plannedAssignee/actualAssignee の乖離を許容する既存の `UNDOCUMENTED_DEVIATION` 抑制機構は、この違反には適用しない。同一行の `UNDOCUMENTED_DEVIATION` はこの `CONDUCTOR_EXECUTED_R4` に吸収され、重複報告しない。

R4-ctx としての除外は `ctxClass` が `CTX_CLASSES` enum に所属する場合のみ有効。enum 外の `ctxClass` 主張は `INVALID_CTX_CLASS` を発火させたうえで判断型として扱い、`CONDUCTOR_EXECUTED_R4` の判定対象に含める — 自己分類による回避を許さない (§2)。

## §9 限界のまとめ

本モードが提供する安全性の範囲を、実装が主張しない範囲も含めて明記する。

- **機械検査の証明範囲**: `contractRef`/`verificationRef`/`verify-evidence` を含む route-policy.mjs の機械検査が証明するのは、参照が解決すること (traceable) と引用が文字どおり存在すること (well-formed) までである。仕様上の選択が正しいかどうか (semantic correctness) は証明しない
- **semantic 保証の所在**: semantic な誤りを最終的に捕捉するのは §4 で述べた終端の受け入れ R4a のみである。これは事前層のどの機械検査にも依存しない、ルーティング規則の帰結として存在する backstop であり、事前層の機械検査が semantic 誤りを事前に捕捉するという主張はしない
- **scope-guard の範囲**: Bash 経由の変更を観測できないため、「唯一の強制点」ではなく「部分的な機械照合」である (§7)
- **監査は conductor の自己申告に依存する**: `judgeRef`・`deviationNote`・`addedAfterFreeze`・`baseline` はいずれも conductor がマニフェストに書く自己申告であり、`auditManifest` はその記述の整合性 (欠落・矛盾) を検査するのみで、記述内容そのものの真偽を独立に検証しない。scope-guard hook (§7) はこの自己申告依存を緩和する数少ない機構だが、それ自体も Bash 迂回という既知の限界を持つ
