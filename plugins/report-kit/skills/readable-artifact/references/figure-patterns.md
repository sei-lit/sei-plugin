# 図の雛形

写して、部品の名前と座標だけを替えて使う。例の題材は「通知の配信を、夜間のバッチからキューに移す」。
すべての雛形は `tests/cases/labels-without-lines/after.html` に入っていて、`check_artifact.py` と `render_check.py` を通る。

目次:

1. 共通の CSS（色の変数・図の箱・横に動く箱）
2. 部品どうしの関係: インラインの SVG
3. 前と後: 左右に並べる（HTML と CSS）
4. 順番のある流れ（HTML と CSS）
5. 時期（HTML と CSS）
6. 選択肢の比較: 表
7. 確かさのラベルと、根拠の折りたたみ
8. 画像を埋め込む

## 1. 共通の CSS

色はすべて `:root` の変数にし、暗いテーマで定義し直す。図の中の色も、この変数から取る。
`--chg` は「変わる所」、`--gone` は「なくなる所」に使い、それ以外には使わない。

```css
:root {
  --bg: #f5f6f8; --surface: #ffffff; --fg: #1d2430; --muted: #5d6878; --line: #d6dbe3;
  --accent: #2459a6; --accent-soft: #e5edf9;
  --chg: #b4521d; --chg-soft: #fbeadf;
  --gone: #8a8f98;
  --ok: #2b7a55; --ok-soft: #e2f2ea;
  --font-text: "Noto Sans JP", "Hiragino Sans", system-ui, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #14181f; --surface: #1b212b; --fg: #e5e9ef; --muted: #9ba6b5; --line: #303a47;
    --accent: #84b1ef; --accent-soft: #1e2d44;
    --chg: #f2a774; --chg-soft: #3b291c;
    --gone: #7d8694;
    --ok: #75cfa5; --ok-soft: #183128;
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  /* 上の @media の中と同じ値を、そのまま写す */
}
body {
  background: var(--bg); color: var(--fg); font-family: var(--font-text); line-height: 1.7;
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px));
  padding-block: 24px 48px;
}
figure { margin: 0; display: flex; flex-direction: column; gap: 10px; min-width: 0;
  background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
figcaption { color: var(--muted); font-size: 13px; }
.scroll { overflow-x: auto; }
```

決まり:

- 図は必ず `<figure>` で包み、`<figcaption>` に「何を見ればよいか」を `caption` の上限（SKILL.md の表）の中で書く。検査は `<figure>`・`<svg>`・`<table>`・`<img>`・`<pre class="mermaid">`・`role="img"` を図として数え、`<div class="fig">` は数えない。
- 幅の決まった図（SVG・表・コード）は `.scroll` の中に入れる。ページ全体を横に動かさない。

## 2. 部品どうしの関係: インラインの SVG

3 つ以上の部品の依存・呼び出し・包含は、箱と矢印で描く。手順:

1. **層を決める。** 呼ぶ側を上、呼ばれる側を下にする（データの流れなら左から右）。同じ層の部品は同じ y に置く。
2. **格子を決める。** 箱の高さは 40、層の間は 100、箱の間の横の隙間は 40。x は 20 から始める。
3. **箱の幅を決める。** 文字の幅（日本語は 1 字 13px、英数字は 1 字 8px）に 24 を足し、同じ層では最も広い箱に揃える。
4. **viewBox を決める。** 幅 = 最も右の箱の右端 + 20、高さ = 最も下の箱の下端 + 20。幅は 960 までにする（超えるなら層を分ける）。
5. **矢印を引く。** 箱の下の辺の中央から、相手の箱の上の辺の中央へ。矢印の向きは「依存する側 → 依存される側」に揃え、凡例か図の説明で 1 回だけ言う。
6. **矢印に名前を付ける。** 意味が 1 つでないとき（「呼ぶ」「書く」「読む」）、線の中ほどに `d-note` の文字を置く。
7. **変わる所だけ色を付ける。** 変わる箱と矢印に `is-chg`、なくなる箱と矢印に `is-gone` を付ける。ほかは灰色のまま。
8. **幅を決める。** `.scroll` の中に入れ、SVG に viewBox の幅の 0.8 倍の `min-width` を付ける（13px の文字がスマホで 10px より小さくならない）。

```css
.dep { display: block; width: 100%; height: auto; min-width: 576px; } /* viewBox の幅 720 × 0.8 */
.d-node { fill: var(--surface); stroke: var(--muted); stroke-width: 1.5; }
.d-node.is-chg { fill: var(--chg-soft); stroke: var(--chg); }
.d-node.is-gone { fill: none; stroke: var(--gone); stroke-dasharray: 5 4; }
.d-edge { stroke: var(--muted); stroke-width: 1.5; fill: none; }
.d-edge.is-chg { stroke: var(--chg); stroke-width: 2.5; }
.d-edge.is-gone { stroke: var(--gone); stroke-dasharray: 5 4; }
.d-head { fill: var(--muted); }
.d-head.is-chg { fill: var(--chg); }
.d-label { fill: var(--fg); font-size: 13px; font-family: var(--font-text); }
.d-note { fill: var(--muted); font-size: 12px; font-family: var(--font-text); }
```

```html
<figure>
  <div class="scroll">
    <svg class="dep" viewBox="0 0 720 260" role="img" aria-label="変更後は、API がキューに書き、ワーカーがキューから読んで、メールとプッシュの送信を呼ぶ">
      <defs>
        <!-- id はページの中で 1 つにする（図ごとに名前を変える） -->
        <marker id="dep-a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="d-head"/></marker>
        <marker id="dep-a-chg" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="d-head is-chg"/></marker>
      </defs>
      <!-- 層 0（y=20） -->
      <rect x="20" y="20" width="160" height="40" rx="8" class="d-node"/>
      <text x="100" y="45" text-anchor="middle" class="d-label">API サーバー</text>
      <!-- 層 1（y=120） -->
      <rect x="20" y="120" width="160" height="40" rx="8" class="d-node is-chg"/>
      <text x="100" y="145" text-anchor="middle" class="d-label">キュー</text>
      <rect x="280" y="120" width="160" height="40" rx="8" class="d-node is-chg"/>
      <text x="360" y="145" text-anchor="middle" class="d-label">ワーカー</text>
      <rect x="540" y="120" width="160" height="40" rx="8" class="d-node is-gone"/>
      <text x="620" y="145" text-anchor="middle" class="d-label">夜間のバッチ</text>
      <!-- 層 2（y=200） -->
      <rect x="200" y="200" width="160" height="40" rx="8" class="d-node"/>
      <text x="280" y="225" text-anchor="middle" class="d-label">メール送信</text>
      <rect x="380" y="200" width="160" height="40" rx="8" class="d-node"/>
      <text x="460" y="225" text-anchor="middle" class="d-label">プッシュ送信</text>
      <!-- 矢印: 箱の縁から縁へ -->
      <line x1="100" y1="60" x2="100" y2="118" class="d-edge is-chg" marker-end="url(#dep-a-chg)"/>
      <text x="108" y="94" class="d-note">書く</text>
      <line x1="278" y1="140" x2="182" y2="140" class="d-edge is-chg" marker-end="url(#dep-a-chg)"/>
      <text x="206" y="132" class="d-note">読む</text>
      <line x1="340" y1="160" x2="290" y2="198" class="d-edge"   marker-end="url(#dep-a)"/>
      <line x1="380" y1="160" x2="450" y2="198" class="d-edge"   marker-end="url(#dep-a)"/>
    </svg>
  </div>
  <figcaption>色の付いた 2 つが新しく入る部品。点線の夜間のバッチはなくなる。</figcaption>
</figure>
```

確かめる点（`render_check.py` が検出する）: 文字が箱からはみ出していない、文字どうしが重ならない、文字が図の外に出ない。
矢印の名前は箱や線と重ならない位置（線の右か上に 6〜8px ずらす）に置く。

部品が 12 個を超えるときは、同じ扱いの部品（例: 同じ親に依存するプラグイン 7 つ）を、小さな丸い箱にして縦横に詰め、
そのまとまりから親へ矢印を 1 本だけ引く。部品ごとに線を引くと、線が重なって読めなくなる。25 個を超えるなら、
全体の図には 5〜8 個のまとまりだけを描き、まとまりの中は別の図か表にする。

図の起点（いちばん上の層の箱）は、横に動く箱の中でスマホの幅でも最初に見える位置（左寄せ）に置く。
中央に置いた図は、ページの最後で横に動く箱を中央から見せる 1 行の script を足す。

```html
<script>
document.querySelectorAll(".scroll").forEach(function (el) { el.scrollLeft = (el.scrollWidth - el.clientWidth) / 2; });
</script>
```

mermaid（`<pre class="mermaid">flowchart TD ...</pre>`）でも描ける。座標を決めずに済むが、
手元の `render_check.py` では描画されず、色は mermaid の既定の配色になる。
変わる所の色分けが要る図や、両方のテーマで色を合わせたい図は SVG で描く。

## 3. 前と後: 左右に並べる

今と変更後、案 A と案 B を比べる図。決まり:

- 左右の列で、同じ部品を同じ行に置く。行がずれると、どこが変わったか探すことになる。
- 変わる行だけ `is-chg`（色）、なくなる行は `is-gone`（打ち消し線と点線）、新しい行は反対側を空けて `is-new`。
- スマホの幅でも 2 列のままにする（1 列にすると比べられない）。文字は短くする。

```css
.ba { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 6px 10px; }
.ba-head { font-size: 12px; font-weight: 600; color: var(--muted); }
.ba-cell { border: 1px solid var(--line); border-radius: 8px; padding: 6px 10px; font-size: 14px; min-width: 0; overflow-wrap: anywhere; }
.ba-cell.is-chg, .ba-cell.is-new { background: var(--chg-soft); border-color: var(--chg); }
.ba-cell.is-gone { color: var(--gone); text-decoration: line-through; border-style: dashed; }
.ba-cell.is-empty { border-style: dashed; color: var(--muted); }
```

```html
<figure>
  <div class="ba">
    <span class="ba-head">今</span><span class="ba-head">変更後</span>
    <div class="ba-cell">API サーバーが DB に書く</div><div class="ba-cell">API サーバーが DB に書く</div>
    <div class="ba-cell is-gone">夜間のバッチが 1 日 1 回送る</div><div class="ba-cell is-chg">ワーカーがすぐ送る</div>
    <div class="ba-cell is-empty">（なし）</div><div class="ba-cell is-new">キューに積む</div>
  </div>
  <figcaption>変わるのは送る時期だけで、DB への書き方は変えない。</figcaption>
</figure>
```

部品どうしの線が要る比較（つなぎ方が変わる）は、2 の SVG を左右に 2 枚並べるか、
1 枚の中で変わる線だけを `is-chg` にする（1 枚の方が比べやすい）。

## 4. 順番のある流れ

手順、リクエストの通り道。番号は、順番に意味があるときだけ付ける。
PC では左から右、スマホの幅では上から下に並び替わる。

```css
.flow { list-style: none; margin: 0; padding: 0; display: flex; gap: 28px; flex-wrap: wrap; }
.flow > li { position: relative; flex: 1 1 140px; min-width: 0; border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; font-size: 14px; }
.flow > li.is-chg { background: var(--chg-soft); border-color: var(--chg); }
.flow > li + li::before { content: "→"; position: absolute; left: -22px; top: 50%; transform: translateY(-50%); color: var(--muted); }
.flow-sub { display: block; font-size: 12px; color: var(--muted); }
@media (max-width: 560px) {
  .flow { flex-direction: column; gap: 22px; }
  .flow > li { flex: none; } /* 縦に並べると flex-basis が高さになり、箱が 140px に伸びる */
  .flow > li + li::before { content: "↓"; left: 50%; top: -20px; transform: none; }
}
```

```html
<figure>
  <ol class="flow">
    <li>受け付ける<span class="flow-sub">API サーバー</span></li>
    <li class="is-chg">キューに積む<span class="flow-sub">新しい</span></li>
    <li class="is-chg">取り出して送る<span class="flow-sub">ワーカー</span></li>
    <li>結果を記録する<span class="flow-sub">DB</span></li>
  </ol>
  <figcaption>色の付いた 2 つが、今は夜間のバッチがまとめてしている仕事。</figcaption>
</figure>
```

箱の中は 1 語か 1 句にする。説明が要る段は、図の下に番号つきの表を置く（長ければ折りたたみに入れる）。
段が 6 つを超えて PC の幅で 1 行に収まらないときは、横に並べるときだけ `flex-basis` を 72px に下げる。
スマホの幅の縦並びでも効く場所に書くと、`flex-basis` が箱の高さになる。

```css
@media (min-width: 561px) { .flow.is-long > li { flex-basis: 72px; } }
```

## 5. 時期

横軸に時期、縦に作業。色の付いたマスは「できる時期」か「する時期」かを図の説明で言う。

```css
.tl { display: grid; grid-template-columns: minmax(90px, 160px) repeat(4, minmax(0, 1fr)); gap: 4px; font-size: 13px; }
.tl > span { padding: 5px 4px; border-radius: 6px; text-align: center; min-width: 0; overflow-wrap: anywhere; }
.tl .tl-name { text-align: left; }
.tl .tl-head { font-weight: 600; color: var(--muted); }
.tl .tl-on { background: var(--accent-soft); color: var(--accent); }
.tl .tl-chg { background: var(--chg-soft); color: var(--chg); }
```

```html
<figure>
  <div class="tl">
    <span class="tl-name"></span><span class="tl-head">1 月</span><span class="tl-head">2 月</span><span class="tl-head">3 月</span><span class="tl-head">4 月</span>
    <span class="tl-name">キューを作る</span><span class="tl-on">作る</span><span></span><span></span><span></span>
    <span class="tl-name">両方で送る</span><span></span><span class="tl-on">並行</span><span class="tl-on">並行</span><span></span>
    <span class="tl-name">バッチを消す</span><span></span><span></span><span></span><span class="tl-chg">消す</span>
  </div>
  <figcaption>色の付いたマスは予定で、決まった日付ではない。</figcaption>
</figure>
```

## 6. 選択肢の比較: 表

行 = 選択肢、列 = 観点。セルは `cell` の上限（SKILL.md の表）まで。推す案の行に印を付け、理由を列の 1 つにする。
観点が 5 つを超えるときは、判断に効く 3〜4 個だけを表に出し、残りは折りたたみに入れる。
列が 2 つの表には `min-width` を付けない（スマホの幅で、2 列目が横に動く箱の外に隠れる）。

```html
<figure>
  <div class="scroll">
    <table>
      <thead><tr><th>案</th><th>成り立つ条件</th><th>壊れやすい所</th><th>判断</th></tr></thead>
      <tbody>
        <tr class="is-pick"><td>キューに移す</td><td>ワーカーを 1 つ動かせる</td><td>二重に送る</td><td>推す（送る時期を選べる）</td></tr>
        <tr><td>バッチを 1 時間ごとにする</td><td>今の仕組みのまま</td><td>最大 1 時間遅れる</td><td>遅れが残る</td></tr>
      </tbody>
    </table>
  </div>
  <figcaption>2 つの案の比較。推す案に色を付けた。</figcaption>
</figure>
```

```css
table { border-collapse: collapse; width: 100%; min-width: 560px; font-size: 14px; }
th, td { text-align: left; vertical-align: top; padding: 8px 10px; border-bottom: 1px solid var(--line); }
tr.is-pick td { background: var(--accent-soft); }
```

## 7. 確かさのラベルと、根拠の折りたたみ

実行して確かめたこと・読んだだけのこと・推定・未確認を、文の後ろのラベルで分ける。
ラベルは 4 種類だけにし、ページの中で言い方を変えない。

```css
.lbl { font-size: 11.5px; font-weight: 600; padding: 1px 7px; border-radius: 4px; white-space: nowrap; }
.lbl.is-run { background: var(--ok-soft); color: var(--ok); }
.lbl.is-read { background: var(--accent-soft); color: var(--accent); }
.lbl.is-guess { background: var(--chg-soft); color: var(--chg); }
.lbl.is-unknown { border: 1px dashed var(--muted); color: var(--muted); }
details { border: 1px solid var(--line); border-radius: 10px; padding: 10px 14px; background: var(--surface); }
summary { cursor: pointer; font-weight: 600; }
```

```html
<li>キューは 1 秒に 500 件を受けられる <span class="lbl is-run">実行した</span></li>
<li>再送は 3 回まで <span class="lbl is-read">設定を読んだ</span></li>
<details>
  <summary>根拠（測定の手順と結果）</summary>
  <p>…細かい根拠はここに書く。上限の字数に数えない…</p>
</details>
```

## 8. 画像を埋め込む

公開先は外の画像を読めない（`<img src="https://…">` は表示されない）。画像は data: の URL で埋め込む。

- スクリーンショットは幅 1200px 以下に縮め、JPEG（写真や画面）か PNG（線と文字だけの図）にする。1 枚は `external` の上限（limits.json の `data_uri_max`。base64 の長さ）以下、ページ全体で 2MB 以下を目安にする。
- macOS では `sips -Z 1200 -s format jpeg -s formatOptions 70 in.png --out out.jpg` で縮め、`base64 -i out.jpg` の結果を `<img src="data:image/jpeg;base64,…">` に入れる。
- 画像の中の文字に説明を任せない。何を見ればよいかを `<figcaption>` に書き、`alt` にも同じことを書く。
- 線と箱で描ける図は、画像にせず SVG で描く（暗いテーマで色が変わらず、拡大しても崩れないため）。
