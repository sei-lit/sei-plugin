#!/usr/bin/env python3
"""render_check.py の受け入れテスト。Chrome か Chromium が無い環境では飛ばす（1 件に 20〜30 秒かかる）。

USAGE: python3 -m unittest discover -s <このディレクトリ> -p 'test_*.py'
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "render_check.py"
CHROME = next((c for c in [os.environ.get("CHROME"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                           shutil.which("google-chrome"), shutil.which("chromium")] if c and os.path.exists(c)), None)

BROKEN = """<title>t</title><style>
:root { --bg: #fff; --fg: #111; }
body { background: var(--bg); color: var(--fg); }
.wide { width: 900px; }
</style>
<div class="wide">横に広い箱</div>
<svg viewBox="0 0 300 100" width="300" role="img" aria-label="重なり">
  <rect x="10" y="10" width="60" height="40" fill="var(--bg)" stroke="var(--fg)"/>
  <text x="20" y="35" font-size="14" fill="var(--fg)">箱からはみ出す長い名前</text>
  <text x="20" y="80" font-size="14" fill="var(--fg)">重なる文字</text>
  <text x="30" y="82" font-size="14" fill="var(--fg)">重なる文字</text>
</svg>"""


def render(page_path, out):
    r = subprocess.run([sys.executable, str(SCRIPT), str(page_path), "--out", str(out), "--chrome", CHROME],
                       capture_output=True, text=True, timeout=300)
    return r.returncode, json.loads((out / "report.json").read_text(encoding="utf-8"))


@unittest.skipUnless(CHROME, "Chrome が無い")
class RenderCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_good_case_page_has_no_problems_and_four_screenshots(self):
        code, report = render(HERE / "cases" / "labels-without-lines" / "after.html", self.tmp)
        self.assertEqual(code, 0, report)
        self.assertEqual(sorted(report), ["desktop-dark", "desktop-light", "phone-dark", "phone-light"])
        self.assertEqual(report["phone-light"]["width"], 390)
        for key in report:
            self.assertTrue((self.tmp / f"{key}.png").exists())

    def test_broken_page_reports_overflow_and_svg_text_problems(self):
        page = self.tmp / "broken.html"
        page.write_text(BROKEN, encoding="utf-8")
        code, report = render(page, self.tmp / "out")
        kinds = {p["kind"] for p in report["phone-light"]["problems"]}
        self.assertEqual(code, 1)
        self.assertTrue({"page-overflow", "svg-text-overflow", "svg-text-overlap"} <= kinds, kinds)


if __name__ == "__main__":
    unittest.main()
