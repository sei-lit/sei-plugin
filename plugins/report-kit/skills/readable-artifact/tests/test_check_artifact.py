#!/usr/bin/env python3
"""check_artifact.py の受け入れテスト。標準ライブラリだけで動く。

USAGE: python3 -m unittest discover -s <このディレクトリ> -p 'test_*.py'
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import check_artifact  # noqa: E402

THEME = """<title>t</title><style>
:root { --bg: #fff; --fg: #111; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg: #111; --fg: #eee; color-scheme: dark; } }
:root[data-theme="dark"] { --bg: #111; --fg: #eee; color-scheme: dark; }
body { background: var(--bg); color: var(--fg);
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
.scroll { overflow-x: auto; }
</style>"""
LEAD = "<h1>題</h1><ul><li>結論を書く。</li></ul>"


def check(html, cid):
    return next(c for c in check_artifact.run(html)["checks"] if c["id"] == cid)


def page(body):
    return THEME + LEAD + body


class Fixtures(unittest.TestCase):
    def test_after_passes_every_check(self):
        out = check_artifact.run((HERE / "fixtures" / "after.html").read_text(encoding="utf-8"))
        self.assertEqual([c["id"] for c in out["checks"] if not c["pass"]], [])
        self.assertEqual(out["scores"], {"readability": 100, "publish": 100})

    def test_before_fails_readability_and_scores_lower(self):
        before = check_artifact.run((HERE / "fixtures" / "before.html").read_text(encoding="utf-8"))
        failed = {c["id"] for c in before["checks"] if not c["pass"]}
        self.assertTrue({"lead", "figure-first", "bullet", "shape"} <= failed, failed)
        self.assertLess(before["scores"]["readability"], 80)


class Readability(unittest.TestCase):
    def test_lead_allows_three_points_and_one_meta_line(self):
        ok = THEME + "<h1>題</h1><p>1 月 10 日時点。</p><ul><li>一つ。</li><li>二つ。</li><li>三つ。</li></ul>"
        self.assertTrue(check(ok, "lead")["pass"])

    def test_lead_rejects_four_points(self):
        ng = THEME + "<h1>題</h1><ul>" + "<li>要点。</li>" * 4 + "</ul>"
        self.assertFalse(check(ng, "lead")["pass"])

    def test_lead_rejects_two_sentences_in_one_point(self):
        ng = THEME + "<h1>題</h1><ul><li>一つ目の文。二つ目の文。</li></ul>"
        self.assertFalse(check(ng, "lead")["pass"])

    def test_table_of_contents_is_not_counted_as_lead(self):
        toc = THEME + "<h1>題</h1><ul><li>結論。</li></ul><ol>" + '<li><a href="#s">節</a></li>' * 6 + "</ol>"
        self.assertTrue(check(toc, "lead")["pass"])

    def test_section_prose_over_limit_fails(self):
        ng = page("<h2>節</h2><figure><table><tr><td>a</td></tr></table></figure><p>" + "あ" * 301 + "</p>")
        self.assertFalse(check(ng, "section-prose")["pass"])

    def test_text_in_closed_details_is_not_counted(self):
        ok = page("<h2>節</h2><figure><svg viewBox='0 0 100 50'></svg></figure><details><summary>根拠</summary><p>"
                  + "あ" * 3000 + "</p></details>")
        self.assertTrue(check(ok, "section-prose")["pass"])
        self.assertTrue(check(ok, "page-prose")["pass"])

    def test_long_section_without_figure_fails(self):
        ng = page("<h2>節</h2><p>" + "あ" * 121 + "</p>")
        self.assertFalse(check(ng, "figure-first")["pass"])

    def test_prose_before_first_figure_fails(self):
        ng = page("<h2>節</h2><p>" + "あ" * 61 + "</p><figure><table><tr><td>a</td></tr></table></figure>")
        self.assertFalse(check(ng, "figure-first")["pass"])

    def test_div_figure_is_not_counted_as_figure(self):
        ng = page('<h2>節</h2><div class="fig"><p>' + "あ" * 121 + "</p></div>")
        self.assertFalse(check(ng, "figure-first")["pass"])

    def test_caption_with_three_sentences_fails(self):
        ng = page("<h2>節</h2><figure><svg viewBox='0 0 100 50'></svg><figcaption>一。二。三。</figcaption></figure>")
        self.assertFalse(check(ng, "caption")["pass"])

    def test_bullet_with_two_sentences_fails(self):
        ng = page("<h2>節</h2><ul><li>一つ目。二つ目。</li></ul>")
        self.assertFalse(check(ng, "bullet")["pass"])

    def test_decimal_version_is_not_a_sentence_end(self):
        ok = page("<h2>節</h2><ul><li>版 8.7.0 を待つ。</li></ul>")
        self.assertTrue(check(ok, "bullet")["pass"])

    def test_table_cell_with_two_sentences_fails(self):
        ng = page("<h2>節</h2><figure><div class='scroll'><table><tr><td>一つ目。二つ目。</td></tr></table></div></figure>")
        self.assertFalse(check(ng, "cell")["pass"])

    def test_same_wording_in_lead_and_body_fails(self):
        s = "キューに移すと送るまでの遅れが一時間からほぼ零になる"
        ng = THEME + f"<h1>題</h1><ul><li>{s}。</li></ul><h2>節</h2><p>{s}。</p>"
        self.assertFalse(check(ng, "repeat")["pass"])

    def test_labels_without_lines_fail(self):
        chips = "".join(f'<span class="tag">部品{i}</span>' for i in range(8))
        ng = page(f"<h2>節</h2><div>{chips}</div>")
        self.assertFalse(check(ng, "shape")["pass"])

    def test_labels_next_to_a_drawn_diagram_pass(self):
        chips = "".join(f'<span class="tag">部品{i}</span>' for i in range(8))
        ok = page(f"<h2>節</h2><figure><div class='scroll'><svg viewBox='0 0 600 200'></svg></div></figure><div>{chips}</div>")
        self.assertTrue(check(ok, "shape")["pass"])

    def test_flow_written_with_arrows_fails(self):
        ng = page("<h2>節</h2><p>受付 → キュー → ワーカー → 記録</p>")
        self.assertFalse(check(ng, "shape")["pass"])


class Publish(unittest.TestCase):
    def test_skeleton_tags_fail(self):
        ng = "<!DOCTYPE html><html><head>" + THEME + "</head><body>" + LEAD + "</body></html>"
        self.assertFalse(check(ng, "skeleton")["pass"])

    def test_missing_dark_attribute_block_fails(self):
        ng = THEME.replace(':root[data-theme="dark"] { --bg: #111; --fg: #eee; color-scheme: dark; }', "") + LEAD
        self.assertFalse(check(ng, "theme")["pass"])

    def test_token_defined_only_in_dark_fails(self):
        ng = THEME.replace(':root[data-theme="dark"] { --bg: #111;', ':root[data-theme="dark"] { --extra: #f00; --bg: #111;') + LEAD
        self.assertFalse(check(ng, "theme")["pass"])

    def test_color_literal_outside_root_fails(self):
        ng = THEME.replace(".scroll {", ".x { color: #ff0000; } .scroll {") + LEAD
        self.assertFalse(check(ng, "color-literal")["pass"])

    def test_svg_fill_literal_fails_and_variable_passes(self):
        ng = page('<h2>節</h2><figure><svg viewBox="0 0 100 50"><rect fill="#123456"/></svg></figure>')
        ok = page('<h2>節</h2><figure><svg viewBox="0 0 100 50"><rect fill="var(--fg)"/></svg></figure>')
        self.assertFalse(check(ng, "color-literal")["pass"])
        self.assertTrue(check(ok, "color-literal")["pass"])

    def test_external_image_and_script_fail(self):
        ng = page('<img src="https://example.com/a.png"><script src="https://example.com/x.js"></script>')
        self.assertFalse(check(ng, "external")["pass"])

    def test_allowed_font_and_cdn_pass(self):
        ok = page('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter">'
                  '<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>')
        self.assertTrue(check(ok, "external")["pass"])

    def test_wide_svg_outside_scroll_box_fails(self):
        ng = page('<h2>節</h2><figure><svg viewBox="0 0 720 200"></svg></figure>')
        ok = page('<h2>節</h2><figure><div class="scroll"><svg viewBox="0 0 720 200"></svg></div></figure>')
        self.assertFalse(check(ng, "scroll-box")["pass"])
        self.assertTrue(check(ok, "scroll-box")["pass"])


if __name__ == "__main__":
    unittest.main()
