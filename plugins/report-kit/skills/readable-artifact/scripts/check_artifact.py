#!/usr/bin/env python3
"""Artifact 用の HTML を、読みやすさの決まりと公開の決まりで検査する（標準ライブラリだけで動く）。

Usage:
  python3 check_artifact.py <page.html> [--json]

  検査ごとに、合格した単位（節・箇条書き・表のセルなど）の割合を出し、
  2 つの群（readability = 読みやすさ、publish = 公開の決まり）ごとに 0〜100 の点にする。
  1 つでも不合格の検査があれば終了コード 1 を返す。

しきい値は SKILL.md の「文の量の上限」と同じ値にしてある。片方を変えたらもう片方も変える。
"""
import argparse
import json
import re
import sys
from html.parser import HTMLParser

# --- しきい値（SKILL.md と同じ） ----------------------------------------------
LEAD_MAX_POINTS = 3          # 先頭の要点の項目数
LEAD_POINT_MAX_CHARS = 60    # 要点 1 項目の文字数（1 文まで）
LEAD_META_MAX_LINES = 1      # 要点の外に置ける行（日付・出典）
LEAD_META_MAX_CHARS = 80
SECTION_PROSE_MAX = 300      # 1 つの節の、図・表・折りたたみの外の文字数
SECTION_NEEDS_FIGURE = 120   # これを超える節は図か表を持つ
BEFORE_FIGURE_MAX = 60       # 節の中で、最初の図・表より前に置ける文字数
CAPTION_MAX_CHARS = 100      # 図の説明（figcaption）は 2 文まで・この文字数まで
CAPTION_MAX_SENTENCES = 2
BULLET_MAX_CHARS = 80        # 箇条書き 1 項目は 1 文まで・この文字数まで
CELL_MAX_CHARS = 60          # 表のセル 1 つは 1 文まで・この文字数まで
PAGE_PROSE_MAX = 2000        # 折りたたみの外の、ページ全体の文字数
DUP_MIN_CHARS = 20           # この長さ以上の同じ文・同じ言い回しを繰り返しとみなす
CHIPS_MIN = 8                # 線の無い節に、これ以上の短いラベルが並んだら「並べただけ」
ARROWS_MIN = 3               # 図の無い節の文に、これ以上の矢印があれば「流れを文で書いた」
SVG_SCROLL_WIDTH = 400       # viewBox の幅がこれを超える SVG は横に動く箱に入れる（スマホで文字が縮みすぎる）
DATA_URI_MAX = 400_000       # data: の URL 1 つの長さ（base64 で約 300KB）

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
    root = [b for b in find_blocks(css, r"(?<![\w\]\)-]):root\s*\{")]
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


def check_lead(p):
    lead = p.sections[0]["nodes"]
    lis = [n for n in p.blocks(lead) if n.tag == "li"]
    others = [n for n in p.blocks(lead) if n.tag != "li"]
    units = [(len(lis) <= LEAD_MAX_POINTS, f"要点が {len(lis)} 項目（{LEAD_MAX_POINTS} まで）"),
             (len(others) <= LEAD_META_MAX_LINES, f"要点の外の文が {len(others)} 個（{LEAD_META_MAX_LINES} まで）")]
    units += [(chars(n.inner_text()) <= LEAD_POINT_MAX_CHARS and sentences(n.inner_text()) <= 1,
               f"要点 {chars(n.inner_text())} 字・{sentences(n.inner_text())} 文: {short(n.inner_text())}") for n in lis]
    units += [(chars(n.inner_text()) <= LEAD_META_MAX_CHARS, f"先頭の文 {chars(n.inner_text())} 字: {short(n.inner_text())}") for n in others]
    if not lis and len(p.sections) > 1:
        units.append((False, "先頭（最初の h2 より前）に要点の箇条書きが無い"))
    return units


def check_section_prose(p):
    units = []
    for s in p.sections[1:]:
        c = sum(chars(t.text) for t in p.prose_texts(s["nodes"]))
        units.append((c <= SECTION_PROSE_MAX, f"「{s['title']}」の文 {c} 字（{SECTION_PROSE_MAX} まで）"))
    return units


def check_figure_first(p):
    units = []
    for s in p.sections[1:]:
        nodes = s["nodes"]
        total = sum(chars(t.text) for t in p.prose_texts(nodes))
        figs = [i for i, n in enumerate(nodes) if is_figure(n) and not in_details(n)]
        if not figs:
            units.append((total <= SECTION_NEEDS_FIGURE, f"「{s['title']}」は {total} 字の文だけで、図も表も無い"))
            continue
        before = sum(chars(t.text) for t in p.prose_texts(nodes[:figs[0]]))
        units.append((before <= BEFORE_FIGURE_MAX, f"「{s['title']}」は図・表の前に {before} 字ある（{BEFORE_FIGURE_MAX} まで）"))
    return units


def check_captions(p):
    units = []
    for n in p.nodes:
        if n.tag == "figcaption":
            t = n.inner_text()
            ok = chars(t) <= CAPTION_MAX_CHARS and sentences(t) <= CAPTION_MAX_SENTENCES
            units.append((ok, f"図の説明 {chars(t)} 字・{sentences(t)} 文: {short(t)}"))
    return units


def check_bullets(p):
    units = []
    lead_ids = set(id(n) for n in p.sections[0]["nodes"])
    for n in p.blocks(p.nodes, tags=("li",)):
        if id(n) in lead_ids:
            continue
        t = n.inner_text()
        ok = chars(t) <= BULLET_MAX_CHARS and sentences(t) <= 1
        units.append((ok, f"箇条書き {chars(t)} 字・{sentences(t)} 文: {short(t)}"))
    return units


def check_cells(p):
    units = []
    for n in p.nodes:
        if n.tag == "td" and not in_details(n):
            t = n.inner_text()
            ok = chars(t) <= CELL_MAX_CHARS and sentences(t) <= 1
            units.append((ok, f"表のセル {chars(t)} 字・{sentences(t)} 文: {short(t)}"))
    return units


def check_page_prose(p):
    c = sum(chars(t.text) for t in p.prose_texts(p.nodes)) + sum(
        chars(n.inner_text()) for n in p.nodes if n.tag in ("td", "figcaption") and not in_details(n))
    return [(c <= PAGE_PROSE_MAX, f"折りたたみの外の文 {c} 字（{PAGE_PROSE_MAX} まで。表のセルと図の説明を含む）")]


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


def check_repeats(p):
    units = []
    texts = [re.sub(r"\s+", "", n.inner_text()) for n in p.blocks(p.nodes, tags=("p", "li", "td", "figcaption", "dd"))]
    seen = {}
    for t in texts:
        for s in SENTENCE_END.split(t):
            if len(s) >= DUP_MIN_CHARS:
                seen[s] = seen.get(s, 0) + 1
    units += [(False, f"同じ文が {k} 回: {short(s)}") for s, k in seen.items() if k > 1]
    lead = [re.sub(r"\s+", "", n.inner_text()) for n in p.blocks(p.sections[0]["nodes"])]
    rest_nodes = [n for s in p.sections[1:] for n in s["nodes"]]
    rest = [re.sub(r"\s+", "", n.inner_text()) for n in p.blocks(rest_nodes, tags=("p", "li", "td", "figcaption", "dd"))]
    for l in lead:
        hit = next((r for r in rest if _lcs(l, r) >= DUP_MIN_CHARS), None)
        units.append((hit is None, f"要点と本文で同じ言い回し: {short(l)}"))
    if not units:
        units.append((True, ""))
    return units


def _has_lines(nodes):
    return any(n.tag == "svg" or (n.tag == "pre" and "mermaid" in n.classes()) or n.attrs.get("role") == "img" for n in nodes)


def check_shape(p):
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
        units.append((chips < CHIPS_MIN, f"「{s['title']}」は線の無いまま短いラベルが {chips} 個並んでいる"))
        arrows = sum(len(re.findall(r"→|⇒|->", t.text)) for t in p.prose_texts(nodes))
        units.append((arrows < ARROWS_MIN, f"「{s['title']}」は図が無く、文に矢印が {arrows} 個ある"))
    return units


def check_skeleton(p):
    raw = set(p.b.raw_tags)
    units = [(not p.b.decls, "<!DOCTYPE> を書いている（公開時に付く）")]
    units += [(t not in raw, f"<{t}> を書いている（公開時に付く）") for t in ("html", "head", "body")]
    head = p.html[:8192].lstrip()
    head = re.sub(r"^(<!--.*?-->\s*)+", "", head, flags=re.S)
    units.append((head.lower().startswith("<title"), "ファイルの先頭が <title> でない"))
    units.append((any(n.tag == "style" for n in p.nodes), "<style> が無い"))
    return units


def check_theme(p):
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


def check_color_literals(p):
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


def check_external(p):
    units = []
    for n in p.nodes:
        if n.tag == "script" and n.attrs.get("src"):
            src = n.attrs["src"]
            units.append((src.startswith(SCRIPT_HOSTS), f"許されない場所のスクリプト: {src}"))
        if n.tag == "link" and "stylesheet" in (n.attrs.get("rel") or ""):
            href = n.attrs.get("href") or ""
            units.append((href.startswith(STYLE_HOSTS), f"許されない場所のスタイルシート: {href}"))
        if n.tag in ("img", "source", "video", "audio", "image", "use") or (n.tag == "image"):
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
        units.append((len(m.group(0)) <= DATA_URI_MAX, f"data: の URL が {len(m.group(0)) // 1000}KB（{DATA_URI_MAX // 1000}KB まで）"))
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


def check_scroll_boxes(p):
    names = _scroll_selectors(p.css)
    units = []
    for n in p.nodes:
        wide = n.tag in ("table",) or (n.tag == "pre" and "mermaid" not in n.classes())
        if n.tag == "svg" and not any(a.tag == "svg" for a in n.ancestors()):
            vb = (n.attrs.get("viewbox") or n.attrs.get("viewBox") or "").split()
            wide = len(vb) == 4 and float(vb[2]) > SVG_SCROLL_WIDTH
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
    ("caption", "readability", "図の説明は 2 文まで", check_captions),
    ("bullet", "readability", "箇条書きは 1 項目 1 文", check_bullets),
    ("cell", "readability", "表のセルは 1 文", check_cells),
    ("page-prose", "readability", "ページ全体の文の量", check_page_prose),
    ("repeat", "readability", "同じことを繰り返さない", check_repeats),
    ("shape", "readability", "関係を並べず線で描く", check_shape),
    ("skeleton", "publish", "骨組み（title と style から始める）", check_skeleton),
    ("theme", "publish", "色の変数と 2 つのテーマ", check_theme),
    ("color-literal", "publish", ":root の外で色を直書きしない", check_color_literals),
    ("external", "publish", "外部の読み込み", check_external),
    ("scroll-box", "publish", "スマホの幅で横にはみ出さない", check_scroll_boxes),
]


def run(html):
    p = Page(html)
    results = []
    for cid, group, label, fn in CHECKS:
        r, failed = ratio(fn(p))
        results.append({"id": cid, "group": group, "label": label, "ratio": round(r, 3), "pass": r == 1.0, "failed": failed})
    scores = {}
    for g in ("readability", "publish"):
        rs = [x["ratio"] for x in results if x["group"] == g]
        scores[g] = round(100 * sum(rs) / len(rs))
    return {"scores": scores, "checks": results}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("page")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    with open(a.page, encoding="utf-8") as f:
        out = run(f.read())
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
