#!/usr/bin/env python3
"""Artifact 用の HTML を手元の Chrome で描画し、4 枚のスクリーンショットと、崩れの一覧を出す。

Usage:
  python3 render_check.py <page.html> --out <出力のディレクトリ> [--chrome <Chrome の実行ファイル>]

  幅 1280（PC）と 390（スマホ）、明るいテーマと暗いテーマの 4 通りで描く。
  出力: desktop-light.png, desktop-dark.png, phone-light.png, phone-dark.png, report.json
  report.json に、横のはみ出し・切れた文字・SVG の文字の重なりと枠からのはみ出しを書く。
  崩れが 1 つでもあれば終了コード 1 を返す。

公開時の骨組み（doctype、viewport、余白の初期化）を包んでから描くので、公開後の見た目に近い。
mermaid のブロックは公開先が描くもので、手元では描画されない（文字のまま残る）。
"""
import argparse
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# 公開時に付く骨組みの再現。:root の上下の余白は、スマホのアプリの外では 0 になる
SKELETON_HEAD = """<!doctype html><html data-theme="{theme}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>:root{{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}
body{{margin:0;font:14px system-ui,-apple-system,sans-serif}}img{{max-width:100%}}[hidden]{{display:none!important}}</style>
</head><body>"""

PROBE = r"""<script>
(function () {
  function name(el) {
    var s = el.tagName.toLowerCase();
    if (el.id) s += "#" + el.id;
    if (el.classList && el.classList.length) s += "." + Array.from(el.classList).slice(0, 2).join(".");
    return s;
  }
  function scrolls(el) {
    for (var a = el.parentElement; a; a = a.parentElement) {
      var o = getComputedStyle(a).overflowX;
      if (o === "auto" || o === "scroll" || o === "hidden" || o === "clip") return true;
    }
    return false;
  }
  function inter(a, b) {
    var w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
    var h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    return w > 1 && h > 1 ? w * h : 0;
  }
  function run() {
    var W = document.documentElement.clientWidth, r = {width: W, problems: []};
    r.pageOverflow = document.documentElement.scrollWidth - W;
    if (r.pageOverflow > 1) r.problems.push({kind: "page-overflow", detail: "ページが横に " + r.pageOverflow + "px はみ出す"});
    document.querySelectorAll("body *").forEach(function (el) {
      if (el.closest("svg") && el.tagName.toLowerCase() !== "svg") return;
      var b = el.getBoundingClientRect();
      if (b.width && b.right > W + 1 && !scrolls(el))
        r.problems.push({kind: "wide", detail: name(el) + " の右端が画面の外（" + Math.round(b.right) + "px）"});
      var cs = getComputedStyle(el);
      if ((cs.overflowX === "hidden" || cs.overflowX === "clip" || cs.textOverflow === "ellipsis") && el.scrollWidth > el.clientWidth + 1 && el.textContent.trim())
        r.problems.push({kind: "clipped", detail: name(el) + " の文字が切れている: " + el.textContent.trim().slice(0, 30)});
    });
    document.querySelectorAll("svg").forEach(function (svg, si) {
      var sb = svg.getBoundingClientRect();
      var texts = Array.from(svg.querySelectorAll("text")).map(function (t) { return {t: t, b: t.getBoundingClientRect()}; });
      var shapes = Array.from(svg.querySelectorAll("rect, circle, ellipse")).map(function (s) { return s.getBoundingClientRect(); });
      var min = Infinity;
      texts.forEach(function (x, i) {
        var label = (x.t.textContent || "").trim().slice(0, 24);
        if (x.b.height) min = Math.min(min, x.b.height / 1.25);
        if (x.b.left < sb.left - 1 || x.b.right > sb.right + 1 || x.b.top < sb.top - 1 || x.b.bottom > sb.bottom + 1)
          r.problems.push({kind: "svg-text-outside", detail: "図 " + (si + 1) + " の「" + label + "」が図の外に出る"});
        var cx = (x.b.left + x.b.right) / 2, cy = (x.b.top + x.b.bottom) / 2;
        var box = shapes.filter(function (s) { return s.left <= cx && cx <= s.right && s.top <= cy && cy <= s.bottom; })
                        .sort(function (a, b) { return a.width * a.height - b.width * b.height; })[0];
        if (box && (x.b.left < box.left - 1 || x.b.right > box.right + 1))
          r.problems.push({kind: "svg-text-overflow", detail: "図 " + (si + 1) + " の「" + label + "」が箱からはみ出す"});
        for (var j = i + 1; j < texts.length; j++)
          if (inter(x.b, texts[j].b) > 4)
            r.problems.push({kind: "svg-text-overlap", detail: "図 " + (si + 1) + " の「" + label + "」と「" + (texts[j].t.textContent || "").trim().slice(0, 24) + "」が重なる"});
      });
      if (min < 9 && min !== Infinity && !scrolls(svg))
        r.problems.push({kind: "svg-text-small", detail: "図 " + (si + 1) + " の文字が " + min.toFixed(1) + "px まで縮む（横に動く箱に入れて min-width を付ける）"});
    });
    r.mermaid = document.querySelectorAll("pre.mermaid, code.language-mermaid").length;
    r.height = Math.ceil(document.documentElement.scrollHeight);
    var out = parent.document.getElementById("report");
    if (out) out.textContent = JSON.stringify(r);
  }
  var go = function () { setTimeout(run, 300); };
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(go); else window.addEventListener("load", go);
})();
</script>"""

SIZES = {"desktop": 1280, "phone": 390}
MIN_WINDOW = 500  # headless の Chrome は、これより狭い窓を作れない。狭い幅は iframe で作る


def find_chrome(given):
    cands = [given, os.environ.get("CHROME"),
             "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
             "/Applications/Chromium.app/Contents/MacOS/Chromium",
             shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser")]
    for c in cands:
        if c and os.path.exists(c):
            return c
    sys.exit("Chrome が見つからない。--chrome か環境変数 CHROME で渡す")


def harness(page, theme, width, height, window):
    doc = SKELETON_HEAD.format(theme=theme) + page + PROBE + "</body></html>"
    # sips の切り抜きは中央を残す（--cropOffset 0 0 は中央の指定として扱われる）。iframe を中央に置いて、そのまま切る
    left = (window - width) // 2
    return ('<!doctype html><html><body style="margin:0;background:#888">'
            '<pre id="report" style="display:none"></pre>'
            f'<iframe style="display:block;border:0;margin-left:{left}px;width:{width}px;height:{height}px" '
            f'srcdoc="{html.escape(doc, quote=True)}"></iframe></body></html>')


def chrome(cmd_base, args, timeout=90):
    return subprocess.run(cmd_base + args, capture_output=True, text=True, timeout=timeout)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("page")
    ap.add_argument("--out", required=True)
    ap.add_argument("--chrome")
    a = ap.parse_args()
    page = Path(a.page).read_text(encoding="utf-8")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    exe = find_chrome(a.chrome)
    tmp = Path(tempfile.mkdtemp(prefix="render-check-"))
    base = [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
            f"--user-data-dir={tmp / 'profile'}", "--virtual-time-budget=8000"]
    report = {}
    try:
        for size, width in SIZES.items():
            for theme in ("light", "dark"):
                key = f"{size}-{theme}"
                h = tmp / f"{key}.html"
                win_w = max(width, MIN_WINDOW)
                win_w += (win_w - width) % 2
                # 1 回目: 高さと崩れを測る。2 回目: その高さで撮る
                h.write_text(harness(page, theme, width, 1200, win_w), encoding="utf-8")
                r = chrome(base, [f"--window-size={win_w},1200", "--dump-dom", h.as_uri()])
                start = r.stdout.find('<pre id="report"')
                body = r.stdout[r.stdout.find(">", start) + 1: r.stdout.find("</pre>", start)] if start >= 0 else ""
                try:
                    rep = json.loads(html.unescape(body))
                except ValueError:
                    rep = {"problems": [{"kind": "no-report", "detail": "描画の結果を読めなかった"}], "height": 1200}
                height = min(max(rep.get("height", 1200), 400), 16000)
                h.write_text(harness(page, theme, width, height, win_w), encoding="utf-8")
                png = out / f"{key}.png"
                chrome(base, [f"--window-size={win_w},{height}", f"--screenshot={png}", h.as_uri()])
                if win_w != width and shutil.which("sips"):
                    subprocess.run(["sips", "-c", str(height), str(width), str(png)], capture_output=True)
                report[key] = rep
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = 0
    for key, rep in report.items():
        probs = rep.get("problems", [])
        bad += len(probs)
        print(f"{key}: 高さ {rep.get('height')}px、崩れ {len(probs)} 件" + ("（mermaid は手元では描かれない）" if rep.get("mermaid") else ""))
        for p in probs[:8]:
            print(f"    - {p['detail']}")
        if len(probs) > 8:
            print(f"    - ほか {len(probs) - 8} 件")
    print(f"スクリーンショット: {out}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
