#!/usr/bin/env python3
"""hooks/final_diff_check.py の受け入れテスト。標準ライブラリと git だけで動く。

hook と同じ入口で確かめる: Claude Code の PreToolUse の入力（JSON）を stdin に渡し、stdout と終了コードを見る。

USAGE: python3 -m unittest discover -s <このディレクトリ> -p 'test_*.py'
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HOOK = PLUGIN_ROOT / "hooks" / "final_diff_check.py"


def tool_use(name, **inp):
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "toolu_x", "name": name, "input": inp}]}}


def slash_command(name):
    return {"type": "user", "message": {"role": "user", "content":
            f"<command-message>{name}</command-message>\n<command-name>/{name}</command-name>"}}


def tool_result(text):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_x", "content": text}]}}


FLOW = tool_use("Skill", skill="dev-flow:dev-task-flow")
REVIEW = tool_use("Skill", skill="self-review")


class HookRunner(unittest.TestCase):
    dir: Path

    def edit_code(self, root=None):
        path = Path(root or self.dir) / "repo" / "Sources" / "App" / "ViewModel.swift"
        return tool_use("Edit", file_path=str(path), old_string="a", new_string="b")

    def run_hook(self, events, command, tool_name="Bash", cwd=None, env=None, raw=None):
        transcript = self.dir / "transcript.jsonl"
        transcript.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events), encoding="utf-8")
        data = {
            "session_id": "abc123",
            "transcript_path": str(transcript),
            "cwd": str(cwd or self.dir),
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": {"command": command, "description": "", "timeout": 120000, "run_in_background": False},
            "tool_use_id": "toolu_01ABC123",
        }
        r = subprocess.run([sys.executable, "-I", str(HOOK)], input=raw if raw is not None else json.dumps(data),
                           capture_output=True, text=True, env={**os.environ, **(env or {})})
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["hookSpecificOutput"] if r.stdout.strip() else None

    def assertDenied(self, out, *phrases):
        self.assertIsNotNone(out, "止めるはずが通した")
        self.assertEqual(out["permissionDecision"], "deny")
        for p in phrases:
            self.assertIn(p, out["permissionDecisionReason"])


class Hook(HookRunner):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    # ---- 止める場面

    def test_blocks_pr_create_when_code_changed_without_self_review(self):
        out = self.run_hook([FLOW, self.edit_code()], 'gh pr create --title "t" --body "b"')
        self.assertDenied(out, "self-review を当てていない", "gh pr create",
                          "最後のコミットまでの差分に self-review", "上の段すべてへ下から順に", "今の head")

    def test_blocks_when_code_changed_after_the_last_self_review(self):
        self.assertDenied(self.run_hook([FLOW, self.edit_code(), REVIEW, self.edit_code()], "gh pr create --fill"))

    def test_blocks_gh_pr_ready(self):
        self.assertDenied(self.run_hook([FLOW, self.edit_code()], "gh pr ready 12"), "gh pr ready")

    def test_blocks_worker_done(self):
        out = self.run_hook([FLOW, self.edit_code()], 'orca orchestration send --from s --type worker_done --body "done"')
        self.assertDenied(out, "worker_done")

    def test_blocks_trigger_after_cd_and_env_prefix(self):
        self.assertDenied(self.run_hook([FLOW, self.edit_code()], 'cd repo && GH_PROMPT_DISABLED=1 gh pr create --fill'))

    def test_blocks_when_flow_was_opened_by_slash_command(self):
        self.assertDenied(self.run_hook([slash_command("dev-flow:dev-task-flow"), self.edit_code()], "gh pr create --fill"))

    def test_counts_code_rewritten_by_sed_in_bash(self):
        sed = tool_use("Bash", command="sed -i '' 's/a/b/' Sources/App/ViewModel.swift")
        self.assertDenied(self.run_hook([FLOW, REVIEW, sed], "gh pr create --fill"))

    def test_update_self_review_is_not_counted_as_self_review(self):
        other = tool_use("Skill", skill="update-self-review")
        self.assertDenied(self.run_hook([FLOW, self.edit_code(), other], "gh pr create --fill"))

    def test_blocks_when_skip_reason_is_empty(self):
        out = self.run_hook([FLOW, self.edit_code()], 'DEV_FLOW_FINAL_CHECK_SKIP="" gh pr create --fill')
        self.assertDenied(out, "理由が空")

    # ---- 止めない場面

    def test_passes_session_that_did_not_open_dev_task_flow(self):
        self.assertIsNone(self.run_hook([self.edit_code()], "gh pr create --fill"))

    def test_flow_name_inside_a_tool_result_does_not_count_as_opening_it(self):
        self.assertIsNone(self.run_hook([tool_result("<command-name>/dev-flow:dev-task-flow</command-name>"), self.edit_code()],
                                        "gh pr create --fill"))

    def test_passes_when_no_code_was_changed(self):
        doc = tool_use("Edit", file_path=str(self.dir / "repo" / "README.md"), old_string="a", new_string="b")
        body = tool_use("Bash", command="cat > /tmp/pr-body.md <<'EOF'\nbody\nEOF")
        self.assertIsNone(self.run_hook([FLOW, doc, body], "gh pr create --body-file /tmp/pr-body.md"))

    def test_passes_after_self_review_on_the_last_change(self):
        self.assertIsNone(self.run_hook([FLOW, self.edit_code(), REVIEW], "gh pr create --fill"))

    def test_self_review_via_plugin_name_or_slash_command_counts(self):
        self.assertIsNone(self.run_hook([FLOW, self.edit_code(), tool_use("Skill", skill="user-skills:self-review")], "gh pr create --fill"))
        self.assertIsNone(self.run_hook([FLOW, self.edit_code(), slash_command("self-review")], "gh pr create --fill"))
        read = tool_use("Read", file_path="/home/u/.claude/skills/self-review/SKILL.md")
        self.assertIsNone(self.run_hook([FLOW, self.edit_code(), read], "gh pr create --fill"))

    def test_running_a_python_script_is_not_a_code_change(self):
        run = tool_use("Bash", command="python3 scripts/report.py > out.txt")
        self.assertIsNone(self.run_hook([FLOW, REVIEW, run], "gh pr create --fill"))

    def test_commands_that_only_mention_code_paths_are_not_code_changes(self):
        for command in ["git diff -- Sources/App/ViewModel.swift > /tmp/d.txt",
                        "printf '%s\\n' 'test: ViewModel.swift の待ちをやめる' > /tmp/msg.txt && git commit -F /tmp/msg.txt",
                        "python3 - <<'EOF'\nopen('/tmp/x/body.md','w').write('/tmp/x/Gen.swift')\nEOF",
                        "python3 - /tmp/x/body.md <<'EOF'\nimport sys\np=sys.argv[1]; s=open(p).read()\n"
                        "open(p,'w').write(s + '- guard（Presenter.swift）: 閉じている途中なら表示しない')\nEOF",
                        "node scripts/validate.mjs && python3 - <<'EOF'\nopen('fixtures/a.json','w').write('{}')\nEOF"]:
            with self.subTest(command=command):
                self.assertIsNone(self.run_hook([FLOW, REVIEW, tool_use("Bash", command=command)], "gh pr create --fill"))

    def test_writing_files_outside_the_working_repository_is_not_a_code_change(self):
        for path in ["/tmp/work/check.py", "/private/tmp/claude-1/proj/abc/scratchpad/gen.swift"]:
            with self.subTest(path=path):
                self.assertIsNone(self.run_hook([FLOW, REVIEW, tool_use("Write", file_path=path, content="x")], "gh pr create --fill"))

    def test_repository_inside_a_temp_or_scratchpad_directory_still_counts(self):
        work = self.dir / "scratchpad" / "work"
        work.mkdir(parents=True)
        self.assertIsNotNone(self.run_hook([FLOW, REVIEW, self.edit_code(work)], "gh pr create --fill", cwd=work))

    def test_bash_writes_into_code_files_are_code_changes(self):
        for command in ["cat > Sources/App/New.swift <<'EOF'\nstruct New {}\nEOF",
                        "echo 'let x = 1' >> Sources/App/ViewModel.swift",
                        "python3 - <<'EOF'\np='Sources/App/ViewModel.swift'\ns=open(p).read()\nopen(p,'w').write(s.replace('a','b'))\nEOF",
                        "python3 -I - Sources/App/ViewModel.swift <<'EOF'\nimport sys\np=sys.argv[1]; s=open(p).read()\nopen(p,'w').write(s)\nEOF"]:
            with self.subTest(command=command):
                self.assertIsNotNone(self.run_hook([FLOW, REVIEW, tool_use("Bash", command=command)], "gh pr create --fill"))

    def test_passes_unrelated_commands(self):
        events = [FLOW, self.edit_code()]
        for command in ["git status", "gh pr view 12", "gh pr ready 12 --undo", "make test",
                        'orca orchestration send --type escalation --subject "Blocked"',
                        "orca orchestration ask --question 'q'",
                        "grep -rn 'gh pr create' docs/",
                        'git commit -m "docs: gh pr create の前に確かめる"']:
            with self.subTest(command=command):
                self.assertIsNone(self.run_hook(events, command))

    def test_passes_tools_other_than_bash(self):
        self.assertIsNone(self.run_hook([FLOW, self.edit_code()], "gh pr create --fill", tool_name="Edit"))

    def test_skip_with_reason_passes(self):
        out = self.run_hook([FLOW, self.edit_code()], 'DEV_FLOW_FINAL_CHECK_SKIP="self-review は Read で読んで当てた" gh pr create --fill')
        self.assertIsNone(out)

    def test_skip_variable_quoted_in_the_body_does_not_pass(self):
        command = 'orca orchestration send --type worker_done --body "DEV_FLOW_FINAL_CHECK_SKIP=x と書いてあった"'
        self.assertDenied(self.run_hook([FLOW, self.edit_code()], command))

    def test_skip_applies_to_the_trigger_after_cd(self):
        command = 'cd repo && DEV_FLOW_FINAL_CHECK_SKIP="下の段は squash でマージ済み" gh pr create --fill'
        self.assertIsNone(self.run_hook([FLOW, self.edit_code()], command))

    def test_turned_off_by_environment_variable(self):
        self.assertIsNone(self.run_hook([FLOW, self.edit_code()], "gh pr create --fill", env={"DEV_FLOW_FINAL_CHECK": "off"}))

    # ---- 壊れたとき（作業を止めない）

    def test_broken_input_passes_silently(self):
        for raw in ["", "not json", "[]", json.dumps({"tool_name": "Bash", "tool_input": "gh pr create"})]:
            with self.subTest(raw=raw):
                self.assertIsNone(self.run_hook([], "", raw=raw))

    def test_missing_transcript_passes(self):
        data = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "transcript_path": str(self.dir / "none.jsonl"),
                "cwd": str(self.dir), "tool_input": {"command": "gh pr create --fill"}}
        self.assertIsNone(self.run_hook([], "", raw=json.dumps(data)))

    def test_broken_transcript_lines_are_skipped(self):
        transcript = self.dir / "t.jsonl"
        transcript.write_text("{broken\n" + json.dumps(FLOW) + "\n[1]\n" + json.dumps(self.edit_code()) + "\n", encoding="utf-8")
        data = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "transcript_path": str(transcript),
                "cwd": str(self.dir), "tool_input": {"command": "gh pr create --fill"}}
        self.assertIsNotNone(self.run_hook([], "", raw=json.dumps(data)))


class HooksJson(HookRunner):
    """hooks.json に書いたコマンド（python を起動する前にシェルで絞る）を、そのまま通しても同じ判定になる"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        config = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.command = config["hooks"]["PreToolUse"][0]["hooks"][0]["command"]

    def tearDown(self):
        self.tmp.cleanup()

    def run_entry(self, events, command):
        transcript = self.dir / "transcript.jsonl"
        transcript.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events), encoding="utf-8")
        data = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "transcript_path": str(transcript),
                "cwd": str(self.dir), "tool_input": {"command": command}}
        r = subprocess.run(["/bin/sh", "-c", self.command], input=json.dumps(data, ensure_ascii=False),
                           capture_output=True, text=True, env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT)})
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_entry_command_blocks_and_passes_like_the_script(self):
        self.assertIn('"deny"', self.run_entry([FLOW, self.edit_code()], "gh pr create --fill"))
        self.assertIn('"deny"', self.run_entry([FLOW, self.edit_code()], "orca orchestration send --type worker_done --body x"))
        self.assertEqual(self.run_entry([FLOW, self.edit_code()], "make test"), "")
        self.assertEqual(self.run_entry([FLOW, self.edit_code(), REVIEW], "gh pr create --fill"), "")


class Stack(HookRunner):
    """今のブランチを含むスタック（名前の末尾の番号だけが違うブランチ）で、下の段が上の段に入っているか"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.commit("base")
        self.git("checkout", "-q", "-b", "feature/search-pr1")
        self.commit("pr1")
        self.git("checkout", "-q", "-b", "feature/search-pr2")
        self.commit("pr2")
        self.git("checkout", "-q", "-b", "feature/search-pr3")
        self.commit("pr3")
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)

    def commit(self, name):
        (self.repo / f"{name}.txt").write_text(name)
        self.git("add", ".")
        self.git("commit", "-q", "-m", name)

    def fix_lower_step(self, branch="feature/search-pr1"):
        self.git("checkout", "-q", branch)
        self.commit("fix")

    def check(self, cwd=None):
        return self.run_hook([FLOW, self.edit_code(), REVIEW], "gh pr create --fill", cwd=cwd or self.repo)

    def test_blocks_when_lower_fix_is_not_in_the_upper_step(self):
        self.fix_lower_step()
        out = self.check()
        self.assertIsNotNone(out)
        self.assertIn("feature/search-pr1 が feature/search-pr2 に入っていない", out["permissionDecisionReason"])
        self.assertNotIn("self-review を当てていない", out["permissionDecisionReason"])

    def test_finds_repository_one_level_below_cwd(self):
        self.fix_lower_step()
        self.assertIsNotNone(self.check(cwd=self.repo.parent))

    def test_passes_after_propagating_to_every_upper_step(self):
        self.fix_lower_step()
        self.git("checkout", "-q", "feature/search-pr2")
        self.git("merge", "-q", "--no-edit", "feature/search-pr1")
        self.git("checkout", "-q", "feature/search-pr3")
        self.git("merge", "-q", "--no-edit", "feature/search-pr2")
        self.assertIsNone(self.check())

    def test_blocks_when_propagated_only_one_step(self):
        self.fix_lower_step()
        self.git("checkout", "-q", "feature/search-pr2")
        self.git("merge", "-q", "--no-edit", "feature/search-pr1")
        out = self.check()
        self.assertIn("feature/search-pr2 が feature/search-pr3 に入っていない", out["permissionDecisionReason"])

    def test_passes_when_current_branch_is_not_in_the_stack(self):
        self.fix_lower_step()
        self.git("checkout", "-q", "-b", "feature/other", "main")
        self.assertIsNone(self.check())

    def test_ticket_numbers_in_the_middle_of_a_name_are_not_a_stack(self):
        self.git("checkout", "-q", "-b", "feature/123-login", "main")
        self.commit("login")
        self.git("checkout", "-q", "-b", "feature/124-logout", "main")
        self.commit("logout")
        self.assertIsNone(self.check())

    def test_skips_lower_step_whose_upstream_is_gone(self):
        # 下の段を squash でマージして remote のブランチを消した形。包含は崩れるが、取り込み漏れではない
        self.fix_lower_step()
        self.git("remote", "add", "origin", "https://example.com/r.git")
        self.git("config", "branch.feature/search-pr1.remote", "origin")
        self.git("config", "branch.feature/search-pr1.merge", "refs/heads/feature/search-pr1")
        self.git("checkout", "-q", "feature/search-pr3")
        self.assertIsNone(self.check())


if __name__ == "__main__":
    unittest.main()
