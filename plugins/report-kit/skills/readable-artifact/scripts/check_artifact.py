#!/usr/bin/env python3
"""Artifact 用の HTML を、読みやすさの決まりと公開の決まりで検査する（標準ライブラリだけで動く）。

Usage:
  python3 check_artifact.py <page.html> [--json] [--limits <limits.json>]
  python3 check_artifact.py --add-cases <feedback.jsonl> --cases <dir>
  python3 check_artifact.py --cases <dir> [--cases <dir> ...] [--json] [--compare <前の --json の出力>]

  1 つ目の形: 検査（決まり）ごとに、合格した単位（節・箇条書き・表のセルなど）の割合を出し、
  2 つの群（readability = 読みやすさ、publish = 公開の決まり）ごとに 0〜100 の点にする。
  検査の ID（lead、shape など）が決まりの ID で、limits.json の鍵と SKILL.md の表の ID と同じ。
  1 つでも不合格の検査があれば終了コード 1 を返す。
  2 つ目の形: 評価の記録（1 行 1 件の JSON。verdict・before・after・status）の status が open の行から、
  1 件 1 フォルダのケースを作り、その行の status を used にする。
  3 つ目の形: ケースのページをすべて採点し、人の評価と検査のずれを出す。ずれがあれば終了コード 1。
  --compare を付けると、前の出力に無かったずれがあるときだけ 1 を返す。

数（上限と、ずれの境目）はすべて limits.json に置く。改善の手順は references/improving.md。
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

LIMITS_FILE = Path(__file__).resolve().parent.parent / "limits.json"

SCRIPT_HOSTS = ("https://cdnjs.cloudflare.com/", "https://cdn.jsdelivr.net/npm/", "https://unpkg.com/",
                "https://cdn.tailwindcss.com", "https://code.jquery.com/")
STYLE_HOSTS = ("https://fonts.googleapis.com/",)

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# 開いたままで次の兄弟が来たら閉じる要素（ブラウザの暗黙の閉じ方の一部）
AUTO_CLOSE = {"li": {"li"}, "p": {"p", "ul", "ol", "div", "section", "table", "figure", "h1", "h2", "h3", "details"},
              "td": {"td", "th", "tr"}, "th": {"td", "th", "tr"}, "tr": {"tr"}, "option": {"option"}}
HIDDEN_TEXT = {"style", "script", "title", "template", "noscript"}
SENTENCE_END = re.compile(r"[。！？!?]|\.(?=\s|$)")
COLOR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch|color)\(")
OK_PAINT = re.compile(r"^\s*(none|transparent|currentcolor|inherit|context-fill|context-stroke|var\(.*\)|url\(.*\))\s*$", re.I)


class Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs or {}), parent
        self.children, self.text = [], None

    def classes(self):
        return set((self.attrs.get("class") or "").split())

    def ancestors(self):
        n = self.parent
        while n is not None:
            yield n
            n = n.parent

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def inner_text(self, skip=None):
        out = []
        for n in self.walk():
            if n.tag == "#text" and not any(a.tag in HIDDEN_TEXT or (skip and skip(a)) for a in n.ancestors()):
                out.append(n.text)
        return "".join(out)


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.cur = self.root
        self.raw_tags = []   # 文書に書かれた開始タグの名前（骨組みの検査に使う）
        self.decls = []

    def handle_decl(self, decl):
        self.decls.append(decl)

    def handle_starttag(self, tag, attrs):
        self.raw_tags.append(tag)
        closers = [t for t, by in AUTO_CLOSE.items() if tag in by]
        while self.cur.tag in closers:
            self.cur = self.cur.parent
        n = Node(tag, attrs, self.cur)
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.raw_tags.append(tag)
        self.cur.children.append(Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        t = Node("#text", parent=self.cur)
        t.text = data
        self.cur.children.append(t)


def chars(s):
    return len(re.sub(r"\s+", "", s))


def sentences(s):
    s = s.strip()
    if not s:
        return 0
    parts = [p for p in SENTENCE_END.split(s) if chars(p) > 0]
    return max(1, len(parts))


def is_figure(n):
    if n.tag in ("figure", "svg", "table", "img", "canvas"):
        return True
    if n.tag == "pre" and "mermaid" in n.classes():
        return True
    return n.attrs.get("role") == "img"


def in_figure(n):
    return any(is_figure(a) for a in n.ancestors())


def in_details(n):
    """閉じた折りたたみの中か（summary の中は見えるので除く）"""
    chain = [n, *n.ancestors()]
    for i, a in enumerate(chain):
        if a.tag == "details" and "open" not in a.attrs and not any(x.tag == "summary" for x in chain[:i]):
            return True
    return False


def hidden(n):
    return any(a.tag in HIDDEN_TEXT for a in n.ancestors())


def is_nav(n):
    """目次（nav の中か、ページ内へのリンクだけの項目）は文に数えない"""
    if any(a.tag == "nav" for a in n.ancestors()):
        return True
    texts = [t for t in n.walk() if t.tag == "#text" and t.text.strip()]
    return bool(texts) and all(any(a.tag == "a" and (a.attrs.get("href") or "").startswith("#") for a in t.ancestors()) for t in texts)


def ratio(units):
    """units: [(ok, detail)] → (割合, 不合格の詳細)"""
    if not units:
        return 1.0, []
    ok = sum(1 for u, _ in units if u)
    return ok / len(units), [d for u, d in units if not u]


def short(s, n=40):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[:n] + "…"


# --- CSS ----------------------------------------------------------------------

def css_text(root):
    return "\n".join("".join(c.text for c in n.children if c.tag == "#text") for n in root.walk() if n.tag == "style")


def strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def find_blocks(css, pattern):
    """pattern に合うセレクタの直後の { ... } の中身（入れ子を数える）を返す"""
    out = []
    for m in re.finditer(pattern, css):
        i = css.find("{", m.end() - 1)
        if i < 0:
            continue
        depth, j = 0, i
        while j < len(css):
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.append((m.start(), j + 1, css[i + 1:j]))
    return out


def tokens(block):
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);?", block))


def theme_blocks(css):
    root = find_blocks(css, r"(?<![\w\]\)-]):root\s*\{")
    media = []
    for s, e, body in find_blocks(css, r"@media[^{]*prefers-color-scheme\s*:\s*dark[^{]*\{"):
        for s2, e2, inner in find_blocks(body, r':root:not\(\[data-theme=["\']?light["\']?\]\)\s*\{'):
            media.append((s, e, inner))
    attr = find_blocks(css, r':root\[data-theme=["\']?dark["\']?\]\s*\{')
    return root, media, attr


def css_rules(css):
    """入れ子の @media を開いた、(セレクタ, 宣言) の並び"""
    rules = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        sel = m.group(1).strip()
        if sel.startswith("@"):
            sel = sel.split("{")[-1].strip()
        rules.append((sel, m.group(2)))
    return rules


# --- 検査 ---------------------------------------------------------------------

class Page:
    def __init__(self, html):
        self.html = html
        b = TreeBuilder()
        b.feed(html)
        b.close()
        self.b = b
        self.root = b.root
        self.css = strip_comments(css_text(self.root))
        self.nodes = list(self.root.walk())
        self.sections = self._split_sections()

    def _split_sections(self):
        """h2 で区切る。最初の h2 より前は先頭（lead）。各節は文書順のノードの並び"""
        secs = [{"title": "(先頭)", "nodes": []}]
        for n in self.nodes:
            if n.tag == "h2" and not in_figure(n):
                secs.append({"title": short(n.inner_text()), "nodes": [], "h2": n})
                continue
            secs[-1]["nodes"].append(n)
        return secs

    def prose_texts(self, nodes, include_details=False):
        """図・表・見出しの外の文字（文書順）。折りたたみの中は既定で除く"""
        out = []
        for n in nodes:
            if n.tag != "#text" or hidden(n) or in_figure(n) or is_nav(n):
                continue
            if any(a.tag in ("h1", "h2", "h3", "h4") for a in n.ancestors()):
                continue
            if not include_details and in_details(n):
                continue
            out.append(n)
        return out

    def blocks(self, nodes, tags=("p", "li", "dd", "dt", "blockquote")):
        """要素の単位の文（p・li など）。入れ子の li は内側だけを数えない（外側に含める）"""
        seen = set(id(x) for x in nodes)
        out = []
        for n in nodes:
            if n.tag in tags and not in_figure(n) and not in_details(n) and not hidden(n) and not is_nav(n):
                if any(a.tag in tags and id(a) in seen for a in n.ancestors()):
                    continue
                out.append(n)
        return out


def check_lead(p, lim):
    lead = p.sections[0]["nodes"]
    lis = [n for n in p.blocks(lead) if n.tag == "li"]
    others = [n for n in p.blocks(lead) if n.tag != "li"]
    units = [(len(lis) <= lim["max_points"], f"要点が {len(lis)} 項目（{lim['max_points']} まで）"),
             (len(others) <= lim["meta_max_lines"], f"要点の外の文が {len(others)} 個（{lim['meta_max_lines']} まで）")]
    units += [(chars(n.inner_text()) <= lim["point_max_chars"] and sentences(n.inner_text()) <= lim["point_max_sentences"],
               f"要点 {chars(n.inner_text())} 字・{sentences(n.inner_text())} 文: {short(n.inner_text())}") for n in lis]
    units += [(chars(n.inner_text()) <= lim["meta_max_chars"], f"先頭の文 {chars(n.inner_text())} 字: {short(n.inner_text())}") for n in others]
    if not lis and len(p.sections) > 1:
        units.append((False, "先頭（最初の h2 より前）に要点の箇条書きが無い"))
    return units


def check_section_prose(p, lim):
    units = []
    for s in p.sections[1:]:
        c = sum(chars(t.text) for t in p.prose_texts(s["nodes"]))
        units.append((c <= lim["max_chars"], f"「{s['title']}」の文 {c} 字（{lim['max_chars']} まで）"))
    return units


def check_figure_first(p, lim):
    units = []
    for s in p.sections[1:]:
        nodes = s["nodes"]
        total = sum(chars(t.text) for t in p.prose_texts(nodes))
        figs = [i for i, n in enumerate(nodes) if is_figure(n) and not in_details(n)]
        if not figs:
            units.append((total <= lim["needs_figure_over"], f"「{s['title']}」は {total} 字の文だけで、図も表も無い"))
            continue
        before = sum(chars(t.text) for t in p.prose_texts(nodes[:figs[0]]))
        units.append((before <= lim["before_figure_max"], f"「{s['title']}」は図・表の前に {before} 字ある（{lim['before_figure_max']} まで）"))
    return units


def check_captions(p, lim):
    units = []
    for n in p.nodes:
        if n.tag == "figcaption":
            t = n.inner_text()
            ok = chars(t) <= lim["max_chars"] and sentences(t) <= lim["max_sentences"]
            units.append((ok, f"図の説明 {chars(t)} 字・{sentences(t)} 文: {short(t)}"))
    return units


def check_bullets(p, lim):
    units = []
    lead_ids = set(id(n) for n in p.sections[0]["nodes"])
    for n in p.blocks(p.nodes, tags=("li",)):
        if id(n) in lead_ids:
            continue
        t = n.inner_text()
        ok = chars(t) <= lim["max_chars"] and sentences(t) <= lim["max_sentences"]
        units.append((ok, f"箇条書き {chars(t)} 字・{sentences(t)} 文: {short(t)}"))
    return units


def check_cells(p, lim):
    units = []
    for n in p.nodes:
        if n.tag == "td" and not in_details(n):
            t = n.inner_text()
            ok = chars(t) <= lim["max_chars"] and sentences(t) <= lim["max_sentences"]
            units.append((ok, f"表のセル {chars(t)} 字・{sentences(t)} 文: {short(t)}"))
    return units


def check_page_prose(p, lim):
    c = sum(chars(t.text) for t in p.prose_texts(p.nodes)) + sum(
        chars(n.inner_text()) for n in p.nodes if n.tag in ("td", "figcaption") and not in_details(n))
    return [(c <= lim["max_chars"], f"折りたたみの外の文 {c} 字（{lim['max_chars']} まで。表のセルと図の説明を含む）")]


def _lcs(a, b):
    best = 0
    prev = [0] * (len(b) + 1)
    for ca in a:
        cur = [0] * (len(b) + 1)
        for j, cb in enumerate(b, 1):
            if ca == cb:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def check_repeats(p, lim):
    units = []
    texts = [re.sub(r"\s+", "", n.inner_text()) for n in p.blocks(p.nodes, tags=("p", "li", "td", "figcaption", "dd"))]
    seen = {}
    for t in texts:
        for s in SENTENCE_END.split(t):
            if len(s) >= lim["min_chars"]:
                seen[s] = seen.get(s, 0) + 1
    units += [(False, f"同じ文が {k} 回: {short(s)}") for s, k in seen.items() if k > 1]
    lead = [re.sub(r"\s+", "", n.inner_text()) for n in p.blocks(p.sections[0]["nodes"])]
    rest_nodes = [n for s in p.sections[1:] for n in s["nodes"]]
    rest = [re.sub(r"\s+", "", n.inner_text()) for n in p.blocks(rest_nodes, tags=("p", "li", "td", "figcaption", "dd"))]
    for l in lead:
        hit = next((r for r in rest if _lcs(l, r) >= lim["min_chars"]), None)
        units.append((hit is None, f"要点と本文で同じ言い回し: {short(l)}"))
    if not units:
        units.append((True, ""))
    return units


def _has_lines(nodes):
    return any(n.tag == "svg" or (n.tag == "pre" and "mermaid" in n.classes()) or n.attrs.get("role") == "img" for n in nodes)


def check_shape(p, lim):
    """関係を線で描かずにラベルを並べた節と、流れを矢印の文字で書いた節"""
    units = []
    for s in p.sections[1:]:
        nodes = s["nodes"]
        if _has_lines(nodes):
            continue
        groups = {}
        for n in nodes:
            if n.tag == "span" and n.attrs.get("class") and not in_figure(n) and 0 < chars(n.inner_text()) <= 30:
                key = (id(n.parent), n.attrs.get("class").split()[0])
                groups.setdefault(key, []).append(n)
        chips = sum(len(g) for g in groups.values() if len(g) >= 3)
        units.append((chips < lim["chips_min"], f"「{s['title']}」は線の無いまま短いラベルが {chips} 個並んでいる"))
        arrows = sum(len(re.findall(r"→|⇒|->", t.text)) for t in p.prose_texts(nodes))
        units.append((arrows < lim["arrows_min"], f"「{s['title']}」は図が無く、文に矢印が {arrows} 個ある"))
    return units


def check_skeleton(p, lim):
    raw = set(p.b.raw_tags)
    units = [(not p.b.decls, "<!DOCTYPE> を書いている（公開時に付く）")]
    units += [(t not in raw, f"<{t}> を書いている（公開時に付く）") for t in ("html", "head", "body")]
    head = p.html[:8192].lstrip()
    head = re.sub(r"^(<!--.*?-->\s*)+", "", head, flags=re.S)
    units.append((head.lower().startswith("<title"), "ファイルの先頭が <title> でない"))
    units.append((any(n.tag == "style" for n in p.nodes), "<style> が無い"))
    return units


def check_theme(p, lim):
    css = p.css
    root, media, attr = theme_blocks(css)
    units = [(bool(root), ":root の色の定義が無い"),
             (bool(media), '@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {…} } が無い'),
             (bool(attr), ':root[data-theme="dark"] {…} が無い')]
    base = {}
    for _, _, b in root:
        base.update(tokens(b))
    for name, blocks in (("prefers-color-scheme の側", media), ("data-theme の側", attr)):
        for _, _, b in blocks:
            extra = sorted(set(tokens(b)) - set(base))
            units.append((not extra, f"{name}だけで定義した色: {', '.join(extra[:5])}"))
    if media and attr:
        m = {k: v.strip() for _, _, b in media for k, v in tokens(b).items()}
        a = {k: v.strip() for _, _, b in attr for k, v in tokens(b).items()}
        diff = sorted(k for k in set(m) | set(a) if m.get(k) != a.get(k))
        units.append((not diff, f"2 つの暗い色の定義が食い違う: {', '.join(diff[:5])}"))
    body_bg = any(re.search(r"(^|[\s,])body($|[\s,:.])", sel) and re.search(r"background(-color)?\s*:", decl)
                  for sel, decl in css_rules(css))
    units.append((body_bg, "body に背景色が無い"))
    return units


def check_color_literals(p, lim):
    css = p.css
    root, media, attr = theme_blocks(css)
    spans = sorted((s, e) for s, e, _ in root + attr) + sorted((s, e) for s, e, _ in media)
    rest, last = [], 0
    for s, e in sorted(spans):
        if s >= last:
            rest.append(css[last:s])
            last = e
    rest.append(css[last:])
    units = []
    for m in COLOR_LITERAL.finditer("".join(rest)):
        units.append((False, f"CSS の :root の外に色を直書き: {m.group(0)}"))
    for n in p.nodes:
        st = n.attrs.get("style") or ""
        for m in COLOR_LITERAL.finditer(st):
            units.append((False, f"<{n.tag} style> に色を直書き: {m.group(0)}"))
        for attr_name in ("fill", "stroke", "stop-color", "color", "flood-color", "lighting-color"):
            v = n.attrs.get(attr_name)
            if v is not None and not OK_PAINT.match(v):
                units.append((False, f"<{n.tag} {attr_name}=\"{v}\"> 色は CSS 変数から取る"))
    if not units:
        units.append((True, ""))
    return units


def check_external(p, lim):
    units = []
    for n in p.nodes:
        if n.tag == "script" and n.attrs.get("src"):
            src = n.attrs["src"]
            units.append((src.startswith(SCRIPT_HOSTS), f"許されない場所のスクリプト: {src}"))
        if n.tag == "link" and "stylesheet" in (n.attrs.get("rel") or ""):
            href = n.attrs.get("href") or ""
            units.append((href.startswith(STYLE_HOSTS), f"許されない場所のスタイルシート: {href}"))
        if n.tag in ("img", "source", "video", "audio", "image", "use"):
            for k in ("src", "href", "xlink:href"):
                v = n.attrs.get(k)
                if v and re.match(r"^(https?:)?//", v):
                    units.append((False, f"<{n.tag}> が外の画像を読む（data: にする）: {short(v, 60)}"))
        if n.tag in ("iframe", "object", "embed"):
            units.append((False, f"<{n.tag}> は公開先で動かない"))
    for m in re.finditer(r"url\(\s*['\"]?((?:https?:)?//[^'\")]+)", p.css):
        units.append((m.group(1).startswith("https://fonts.gstatic.com/"), f"CSS が外を読む: {m.group(1)}"))
    for m in re.finditer(r"@import\s+(?:url\()?['\"]?([^'\");]+)", p.css):
        units.append((m.group(1).startswith(STYLE_HOSTS), f"@import が外を読む: {m.group(1)}"))
    for m in re.finditer(r"data:[^\"')\s]+", p.html):
        units.append((len(m.group(0)) <= lim["data_uri_max"], f"data: の URL が {len(m.group(0)) // 1000}KB（{lim['data_uri_max'] // 1000}KB まで）"))
    if not units:
        units.append((True, ""))
    return units


def _scroll_selectors(css):
    names = set()
    for sel, decl in css_rules(css):
        if re.search(r"overflow(-x)?\s*:\s*(auto|scroll)", decl):
            for part in sel.split(","):
                last = part.strip().split()[-1] if part.strip() else ""
                names |= {"." + c for c in re.findall(r"\.([\w-]+)", last)}
                m = re.match(r"^([a-z][\w-]*)", last)
                if m:
                    names.add(m.group(1))
    return names


def _scrolls(n, names):
    st = n.attrs.get("style") or ""
    if re.search(r"overflow(-x)?\s*:\s*(auto|scroll)", st):
        return True
    return n.tag in names or any("." + c in names for c in n.classes())


def check_scroll_boxes(p, lim):
    names = _scroll_selectors(p.css)
    units = []
    for n in p.nodes:
        wide = n.tag in ("table",) or (n.tag == "pre" and "mermaid" not in n.classes())
        if n.tag == "svg" and not any(a.tag == "svg" for a in n.ancestors()):
            vb = (n.attrs.get("viewbox") or n.attrs.get("viewBox") or "").split()
            wide = len(vb) == 4 and float(vb[2]) > lim["svg_max_width"]
        if not wide:
            continue
        ok = _scrolls(n, names) or any(_scrolls(a, names) for a in n.ancestors())
        units.append((ok, f"<{n.tag}> が横に動く箱（overflow-x: auto）に入っていない"))
    css = p.css
    gutter = bool(re.search(r"padding-left\s*:\s*max\(\s*16px\s*,\s*env\(safe-area-inset-left", css)) and \
        bool(re.search(r"padding-right\s*:\s*max\(\s*16px\s*,\s*env\(safe-area-inset-right", css))
    units.append((gutter, "左右の余白が max(16px, env(safe-area-inset-*, 0px)) の形でない"))
    return units


CHECKS = [
    ("lead", "readability", "先頭の要点", check_lead),
    ("section-prose", "readability", "節ごとの文の量", check_section_prose),
    ("figure-first", "readability", "節は図か表を先に置く", check_figure_first),
    ("caption", "readability", "図の説明の長さ", check_captions),
    ("bullet", "readability", "箇条書きの長さ", check_bullets),
    ("cell", "readability", "表のセルの長さ", check_cells),
    ("page-prose", "readability", "ページ全体の文の量", check_page_prose),
    ("repeat", "readability", "同じことを繰り返さない", check_repeats),
    ("shape", "readability", "関係を並べず線で描く", check_shape),
    ("skeleton", "publish", "骨組み（title と style から始める）", check_skeleton),
    ("theme", "publish", "色の変数と 2 つのテーマ", check_theme),
    ("color-literal", "publish", ":root の外で色を直書きしない", check_color_literals),
    ("external", "publish", "外部の読み込み", check_external),
    ("scroll-box", "publish", "スマホの幅で横にはみ出さない", check_scroll_boxes),
]


def load_limits(path=None):
    with open(path or LIMITS_FILE, encoding="utf-8") as f:
        return json.load(f)


def run(html, limits=None):
    limits = limits or load_limits()
    p = Page(html)
    results = []
    for cid, group, label, fn in CHECKS:
        r, failed = ratio(fn(p, limits.get(cid, {})))
        results.append({"id": cid, "group": group, "label": label, "ratio": round(r, 3), "pass": r == 1.0, "failed": failed})
    scores = {}
    for g in ("readability", "publish"):
        rs = [x["ratio"] for x in results if x["group"] == g]
        scores[g] = round(100 * sum(rs) / len(rs))
    return {"scores": scores, "checks": results}


# --- ケース（人の評価が付いたページ）と、検査とのずれ ---------------------------

CASE_FILE = "case.json"


def rated_side(verdict):
    """評価が付くのは記録の target のページ。bad は直す前の版（before）、good と mixed は直した後の版（after）"""
    return "before" if verdict == "bad" else "after"


def make_case(rec, line_no, cases_dir, limits):
    case_id = f"{rec.get('at', '')[:10] or 'undated'}-{line_no:02d}"
    d = Path(cases_dir) / case_id
    if (d / CASE_FILE).exists():
        return case_id, False
    d.mkdir(parents=True, exist_ok=True)
    pages, missing = [], []
    for side in ("before", "after"):
        src = rec.get(side) or ""
        if not src:
            continue
        if not os.path.isfile(src):
            missing.append(src)
            continue
        shutil.copyfile(src, d / f"{side}.html")
        label = rec["verdict"] if side == rated_side(rec["verdict"]) else "unrated"
        with open(src, encoding="utf-8") as f:
            scores = run(f.read(), limits)["scores"]
        pages.append({"file": f"{side}.html", "label": label, "source": src, "scores_at_creation": scores})
    # rules は null で作る。評価が指す決まりを読んで書くのは人かエージェント（検査の無い観点なら [] と書く）
    case = {"id": case_id, "feedback": rec, "rules": None, "pages": pages, "missing": missing}
    (d / CASE_FILE).write_text(json.dumps(case, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return case_id, True


def add_cases(feedback_path, cases_dir, limits):
    with open(feedback_path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    out, made = [], []
    for i, line in enumerate(lines, 1):
        rec = json.loads(line) if line.strip() else None
        if not rec or rec.get("status") != "open":
            out.append(line)
            continue
        case_id, created = make_case(rec, i, cases_dir, limits)
        made.append((case_id, created))
        rec["status"] = "used"
        out.append(json.dumps(rec, ensure_ascii=False))
    # 途中で止まっても記録が半分の行で残らないよう、隣に書いてから置き換える
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(feedback_path)), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    os.replace(tmp, feedback_path)
    return made


def case_gaps(case, results, boundary):
    """results: {file: run() の結果}。ずれの一覧。key は点が動いても変わらない（--compare で前後を突き合わせる）"""
    gaps = []
    rated = [pg for pg in case["pages"] if pg["label"] in ("bad", "good")]
    if rated and case.get("rules") is None:
        gaps.append({"key": f"rules-unset:{case['id']}", "detail": "rules が未記入（評価が指す決まりの ID を case.json に書く）"})
    for pg in rated:
        res = results[pg["file"]]
        score = res["scores"]["readability"]
        failed = [c["id"] for c in res["checks"] if not c["pass"]]
        where = f"{case['id']}/{pg['file']}"
        if pg["label"] == "bad":
            if score >= boundary:
                gaps.append({"key": f"bad-high:{where}", "detail": f"bad なのに readability {score}（{boundary} 以上）"})
            gaps += [{"key": f"bad-rule-pass:{where}:{r}", "detail": f"bad なのに {r} が合格"}
                     for r in case.get("rules") or [] if r not in failed]
        else:
            if score < boundary:
                gaps.append({"key": f"good-low:{where}", "detail": f"good なのに readability {score}（{boundary} 未満）"})
            gaps += [{"key": f"good-rule-fail:{where}:{r}", "detail": f"good なのに {r} が不合格"} for r in failed]
    return gaps


def score_cases(dirs, limits):
    cases, gaps = [], []
    for root in dirs:
        for d in sorted(Path(root).iterdir()):
            if not (d / CASE_FILE).is_file():
                continue
            case = json.loads((d / CASE_FILE).read_text(encoding="utf-8"))
            results = {pg["file"]: run((d / pg["file"]).read_text(encoding="utf-8"), limits) for pg in case["pages"]}
            g = case_gaps(case, results, limits["gap"]["boundary"])
            gaps += g
            cases.append({"id": case["id"], "dir": str(d), "rules": case.get("rules"), "gaps": g,
                          "pages": [{"file": pg["file"], "label": pg["label"], "scores": results[pg["file"]]["scores"],
                                     "failed": [c["id"] for c in results[pg["file"]]["checks"] if not c["pass"]]}
                                    for pg in case["pages"]]})
    return {"cases": cases, "gaps": gaps}


def print_cases(out, before=None):
    old = {(c["id"], p["file"]): p["scores"]["readability"] for c in (before or {}).get("cases", []) for p in c["pages"]}
    for c in out["cases"]:
        print(f"{c['id']}  rules: {'(未記入)' if c['rules'] is None else ', '.join(c['rules']) or '(なし)'}")
        for p in c["pages"]:
            s = p["scores"]
            delta = old.get((c["id"], p["file"]))
            delta = "" if delta is None else f" ({s['readability'] - delta:+d})"
            print(f"  {p['file']:<12} {p['label']:<8} readability {s['readability']}{delta} / publish {s['publish']}"
                  f"  NG: {', '.join(p['failed']) or 'なし'}")
    print("ずれ:" + (" なし" if not out["gaps"] else ""))
    for g in out["gaps"]:
        print(f"  - {g['key']}  {g['detail']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("page", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limits", help="数を試しに変えるときの limits.json（既定はスキルの limits.json）")
    ap.add_argument("--cases", action="append", default=[], help="ケースのフォルダを並べたディレクトリ（複数可）")
    ap.add_argument("--add-cases", metavar="FEEDBACK_JSONL")
    ap.add_argument("--compare", metavar="BEFORE_JSON")
    a = ap.parse_args()
    limits = load_limits(a.limits)
    if a.add_cases:
        if len(a.cases) != 1 or a.page:
            ap.error("--add-cases には --cases を 1 つだけ渡す")
        for case_id, created in add_cases(a.add_cases, a.cases[0], limits):
            print(("作った " if created else "既にある ") + str(Path(a.cases[0]) / case_id))
        return
    if a.cases:
        if a.page:
            ap.error("ページと --cases は一緒に渡さない")
        out = score_cases(a.cases, limits)
        before = json.loads(Path(a.compare).read_text(encoding="utf-8")) if a.compare else None
        if before is not None:
            old_keys, new_keys = {g["key"] for g in before["gaps"]}, {g["key"] for g in out["gaps"]}
            out["new_gaps"] = [g for g in out["gaps"] if g["key"] not in old_keys]
            out["resolved_gaps"] = [g for g in before["gaps"] if g["key"] not in new_keys]
        if a.json:
            print(json.dumps(out, ensure_ascii=False, indent=1))
        else:
            print_cases(out, before)
            if before is not None:
                print(f"前と比べて: 新しいずれ {len(out['new_gaps'])} 件、消えたずれ {len(out['resolved_gaps'])} 件")
                for g in out["new_gaps"]:
                    print(f"  + {g['key']}  {g['detail']}")
        sys.exit(1 if (out["new_gaps"] if before is not None else out["gaps"]) else 0)
    if not a.page:
        ap.error("ページか --cases を渡す")
    with open(a.page, encoding="utf-8") as f:
        out = run(f.read(), limits)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        print(f"readability {out['scores']['readability']} / publish {out['scores']['publish']}")
        for c in out["checks"]:
            mark = "ok  " if c["pass"] else "NG  "
            print(f"{mark}{c['group'][:4]} {c['id']:<14} {c['ratio']:.2f}  {c['label']}")
            for d in c["failed"][:6]:
                print(f"        - {d}")
            if len(c["failed"]) > 6:
                print(f"        - ほか {len(c['failed']) - 6} 件")
    sys.exit(0 if all(c["pass"] for c in out["checks"]) else 1)


if __name__ == "__main__":
    main()
