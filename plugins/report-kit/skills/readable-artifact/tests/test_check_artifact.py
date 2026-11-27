#!/usr/bin/env python3
"""check_artifact.py の受け入れテスト。標準ライブラリだけで動く。
境目の数は limits.json から作る（数を変えてもテストを直さずに済むように）。

USAGE: python3 -m unittest discover -s <このディレクトリ> -p 'test_*.py'
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import check_artifact  # noqa: E402

L = check_artifact.load_limits()
SCRIPT = HERE.parent / "scripts" / "check_artifact.py"
CASES = HERE / "cases"

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


class PublicCases(unittest.TestCase):
    """tests/cases の悪い例が、評価が指す決まりで不合格になり、良い例がすべて合格になる"""

    def test_every_case_names_the_rules_its_feedback_is_about(self):
        for d in sorted(x for x in CASES.iterdir() if (x / "case.json").is_file()):
            case = json.loads((d / "case.json").read_text(encoding="utf-8"))
            self.assertTrue(case["rules"], d.name)
            self.assertEqual({p["label"] for p in case["pages"]}, {"bad", "good"}, d.name)

    def test_cases_have_no_gap_between_checker_and_human_verdict(self):
        out = check_artifact.score_cases([CASES], L)
        self.assertGreaterEqual(len(out["cases"]), 2)
        self.assertEqual(out["gaps"], [])

    def test_good_pages_score_full_and_bad_pages_score_lower(self):
        for c in check_artifact.score_cases([CASES], L)["cases"]:
            scores = {p["label"]: p["scores"]["readability"] for p in c["pages"]}
            self.assertEqual(scores["good"], 100, c["id"])
            self.assertLess(scores["bad"], scores["good"], c["id"])


class SkillDocMatchesLimits(unittest.TestCase):
    """SKILL.md の上限の表の、上限の列の数が、limits.json の数と同じ"""

    def test_each_row_has_the_same_numbers_as_limits(self):
        doc = (HERE.parent / "SKILL.md").read_text(encoding="utf-8")
        rows = dict(re.findall(r"^\| `([\w-]+)` \|[^|]*\|([^|]*)\|\s*$", doc, flags=re.M))  # 上限の列だけ
        readability = [cid for cid, group, _, _ in check_artifact.CHECKS if group == "readability"]
        self.assertEqual(sorted(rows), sorted(readability))
        for cid, row in rows.items():
            in_doc = {int(n) for n in re.findall(r"(?<![A-Za-z\d])\d+", row)}
            in_limits = set(L[cid].values())
            self.assertEqual(in_doc, in_limits, f"SKILL.md の {cid} の行: 表 {sorted(in_doc)} / limits.json {sorted(in_limits)}")


def write_feedback(path, records):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def record(verdict, before="", after="", status="open"):
    return {"at": "2026-01-10T10:00:00+09:00", "skill": "readable-artifact", "verdict": verdict, "quote": "q",
            "target": "t", "before": before, "after": after, "note": "", "status": status}


class AddCases(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bad = str(CASES / "labels-without-lines" / "before.html")
        self.good = str(CASES / "labels-without-lines" / "after.html")

    def pages(self, case_id):
        case = json.loads((self.tmp / "cases" / case_id / "case.json").read_text(encoding="utf-8"))
        return {p["file"]: p["label"] for p in case["pages"]}

    def test_verdict_goes_to_before_when_bad_and_after_when_good(self):
        fb = self.tmp / "fb.jsonl"
        write_feedback(fb, [record("bad", before=self.bad, after=self.good), record("good", before=self.bad, after=self.good)])
        check_artifact.add_cases(fb, self.tmp / "cases", L)
        self.assertEqual(self.pages("2026-01-10-01"), {"before.html": "bad", "after.html": "unrated"})
        self.assertEqual(self.pages("2026-01-10-02"), {"before.html": "unrated", "after.html": "good"})

    def test_bad_verdict_without_before_leaves_only_an_unrated_page(self):
        fb = self.tmp / "fb.jsonl"
        write_feedback(fb, [record("bad", after=self.good)])
        check_artifact.add_cases(fb, self.tmp / "cases", L)
        self.assertEqual(self.pages("2026-01-10-01"), {"after.html": "unrated"})

    def test_only_open_lines_become_cases_and_only_their_status_changes(self):
        fb = self.tmp / "fb.jsonl"
        recs = [record("bad", before=self.bad, status="used"), record("bad", before=self.bad)]
        write_feedback(fb, recs)
        made = check_artifact.add_cases(fb, self.tmp / "cases", L)
        self.assertEqual(made, [("2026-01-10-02", True)])
        lines = [json.loads(x) for x in fb.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(lines, [recs[0], {**recs[1], "status": "used"}])

    def test_case_records_scores_at_creation(self):
        fb = self.tmp / "fb.jsonl"
        write_feedback(fb, [record("bad", before=self.bad)])
        check_artifact.add_cases(fb, self.tmp / "cases", L)
        case = json.loads((self.tmp / "cases" / "2026-01-10-01" / "case.json").read_text(encoding="utf-8"))
        self.assertLess(case["pages"][0]["scores_at_creation"]["readability"], 100)
        self.assertIsNone(case["rules"])
        self.assertEqual(case["feedback"]["quote"], "q")


class Gaps(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def make(self, case_id, rules, pages):
        d = self.tmp / case_id
        d.mkdir()
        for name, label, src in pages:
            (d / name).write_text((CASES / "labels-without-lines" / src).read_text(encoding="utf-8"), encoding="utf-8")
        case = {"id": case_id, "rules": rules, "pages": [{"file": n, "label": lb} for n, lb, _ in pages]}
        (d / "case.json").write_text(json.dumps(case), encoding="utf-8")

    def keys(self):
        return [g["key"] for g in check_artifact.score_cases([self.tmp], L)["gaps"]]

    def test_page_judged_good_but_failing_a_rule_is_a_gap(self):
        self.make("c", ["shape"], [("p.html", "good", "before.html")])
        self.assertIn("good-low:c/p.html", self.keys())
        self.assertIn("good-rule-fail:c/p.html:shape", self.keys())

    def test_page_judged_bad_but_passing_its_rule_is_a_gap(self):
        self.make("c", ["shape"], [("p.html", "bad", "after.html")])
        self.assertEqual(self.keys(), ["bad-high:c/p.html", "bad-rule-pass:c/p.html:shape"])

    def test_rated_case_with_unset_rules_is_reported(self):
        self.make("c", None, [("p.html", "bad", "before.html")])
        self.assertEqual(self.keys(), ["rules-unset:c"])

    def test_empty_rules_means_no_check_covers_the_feedback(self):
        self.make("c", [], [("p.html", "bad", "before.html")])
        self.assertEqual(self.keys(), [])

    def test_unrated_pages_are_scored_but_never_a_gap(self):
        self.make("c", [], [("p.html", "unrated", "before.html")])
        self.assertEqual(self.keys(), [])

    def test_compare_fails_only_on_gaps_that_were_not_there_before(self):
        self.make("c", ["shape"], [("p.html", "good", "before.html")])
        old = self.tmp.parent / (self.tmp.name + "-old.json")
        run = lambda *a: subprocess.run([sys.executable, str(SCRIPT), "--cases", str(self.tmp), *a], capture_output=True, text=True)
        first = run("--json")
        self.assertEqual(first.returncode, 1)
        old.write_text(first.stdout, encoding="utf-8")
        self.assertEqual(run("--compare", str(old)).returncode, 0)
        self.make("d", ["shape"], [("p.html", "good", "before.html")])
        self.assertEqual(run("--compare", str(old)).returncode, 1)


class Readability(unittest.TestCase):
    def test_lead_allows_three_points_and_one_meta_line(self):
        ok = THEME + "<h1>題</h1><p>1 月 10 日時点。</p><ul><li>一つ。</li><li>二つ。</li><li>三つ。</li></ul>"
        self.assertTrue(check(ok, "lead")["pass"])

    def test_lead_rejects_four_points(self):
        ng = THEME + "<h1>題</h1><ul>" + "<li>要点。</li>" * (L["lead"]["max_points"] + 1) + "</ul>"
        self.assertFalse(check(ng, "lead")["pass"])

    def test_lead_rejects_too_many_sentences_in_one_point(self):
        ng = THEME + "<h1>題</h1><ul><li>" + "文。" * (L["lead"]["point_max_sentences"] + 1) + "</li></ul>"
        self.assertFalse(check(ng, "lead")["pass"])

    def test_table_of_contents_is_not_counted_as_lead(self):
        toc = THEME + "<h1>題</h1><ul><li>結論。</li></ul><ol>" + '<li><a href="#s">節</a></li>' * 6 + "</ol>"
        self.assertTrue(check(toc, "lead")["pass"])

    def test_section_prose_over_limit_fails(self):
        ng = page("<h2>節</h2><figure><table><tr><td>a</td></tr></table></figure><p>" + "あ" * (L["section-prose"]["max_chars"] + 1) + "</p>")
        self.assertFalse(check(ng, "section-prose")["pass"])

    def test_text_in_closed_details_is_not_counted(self):
        ok = page("<h2>節</h2><figure><svg viewBox='0 0 100 50'></svg></figure><details><summary>根拠</summary><p>"
                  + "あ" * (L["page-prose"]["max_chars"] + 1) + "</p></details>")
        self.assertTrue(check(ok, "section-prose")["pass"])
        self.assertTrue(check(ok, "page-prose")["pass"])

    def test_long_section_without_figure_fails(self):
        ng = page("<h2>節</h2><p>" + "あ" * (L["figure-first"]["needs_figure_over"] + 1) + "</p>")
        self.assertFalse(check(ng, "figure-first")["pass"])

    def test_prose_before_first_figure_fails(self):
        ng = page("<h2>節</h2><p>" + "あ" * (L["figure-first"]["before_figure_max"] + 1) + "</p><figure><table><tr><td>a</td></tr></table></figure>")
        self.assertFalse(check(ng, "figure-first")["pass"])

    def test_div_figure_is_not_counted_as_figure(self):
        ng = page('<h2>節</h2><div class="fig"><p>' + "あ" * (L["figure-first"]["needs_figure_over"] + 1) + "</p></div>")
        self.assertFalse(check(ng, "figure-first")["pass"])

    def test_caption_with_too_many_sentences_fails(self):
        text = "文。" * (L["caption"]["max_sentences"] + 1)
        ng = page(f"<h2>節</h2><figure><svg viewBox='0 0 100 50'></svg><figcaption>{text}</figcaption></figure>")
        self.assertFalse(check(ng, "caption")["pass"])

    def test_bullet_with_too_many_sentences_fails(self):
        text = "文。" * (L["bullet"]["max_sentences"] + 1)
        ng = page(f"<h2>節</h2><ul><li>{text}</li></ul>")
        self.assertFalse(check(ng, "bullet")["pass"])

    def test_decimal_version_is_not_a_sentence_end(self):
        ok = page("<h2>節</h2><ul><li>版 8.7.0 を待つ。</li></ul>")
        self.assertTrue(check(ok, "bullet")["pass"])

    def test_table_cell_with_too_many_sentences_fails(self):
        text = "文。" * (L["cell"]["max_sentences"] + 1)
        ng = page(f"<h2>節</h2><figure><div class='scroll'><table><tr><td>{text}</td></tr></table></div></figure>")
        self.assertFalse(check(ng, "cell")["pass"])

    def test_same_wording_in_lead_and_body_fails(self):
        s = "キューに移すと送るまでの遅れが一時間からほぼ零になる"
        ng = THEME + f"<h1>題</h1><ul><li>{s}。</li></ul><h2>節</h2><p>{s}。</p>"
        self.assertFalse(check(ng, "repeat")["pass"])

    def test_labels_without_lines_fail(self):
        chips = "".join(f'<span class="tag">部品{i}</span>' for i in range(L["shape"]["chips_min"]))
        ng = page(f"<h2>節</h2><div>{chips}</div>")
        self.assertFalse(check(ng, "shape")["pass"])

    def test_labels_next_to_a_drawn_diagram_pass(self):
        chips = "".join(f'<span class="tag">部品{i}</span>' for i in range(L["shape"]["chips_min"]))
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
        wide = L["scroll-box"]["svg_max_width"] + 1
        ng = page(f'<h2>節</h2><figure><svg viewBox="0 0 {wide} 200"></svg></figure>')
        ok = page(f'<h2>節</h2><figure><div class="scroll"><svg viewBox="0 0 {wide} 200"></svg></div></figure>')
        self.assertFalse(check(ng, "scroll-box")["pass"])
        self.assertTrue(check(ok, "scroll-box")["pass"])


if __name__ == "__main__":
    unittest.main()
