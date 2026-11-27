#!/usr/bin/env python3
"""dev-task-flow の「最後の差分の確かめ」を、PR の作成・ready・完了の報告の直前に確かめる PreToolUse hook。

dev-task-flow を開いたセッションで、次のどれかのコマンドを実行する直前にだけ判定する。
  gh pr create / gh pr ready（--undo を除く）/ orca orchestration send --type worker_done
止めるのは、最後にコードを変えたあとに self-review を当てていないときと、今のブランチを含むスタック
（名前の末尾の番号だけが違うブランチ）で、下の段が隣の上の段に入っていないとき。

Stop hook にしなかった理由: ワーカーは裏の処理を待つたびにターンを終えるので、Stop で判定すると
ターンの終わりのほとんどで止め、そのたびに self-review を当て直させることになる（記録に当てて数えた）。
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SKIP_ENV = "DEV_FLOW_FINAL_CHECK_SKIP"
OFF_ENV = "DEV_FLOW_FINAL_CHECK"

# コマンドの位置（行頭か ; & | ( の後ろ、頭の VAR=value は飛ばす）にあるときだけ数える。
# grep や echo の引数、コミットメッセージの中に同じ文字列があるだけでは止めない
_CMD_START = r"(?:^|[;&|(\n])\s*(?P<env>(?:\w+=(?:\"[^\"]*\"|'[^']*'|\S*)\s+)*)"
_PR_CREATE = re.compile(_CMD_START + r"gh\s+pr\s+create\b")
_PR_READY = re.compile(_CMD_START + r"gh\s+pr\s+ready\b(?P<rest>[^;&|\n]*)")
_WORKER_DONE = re.compile(_CMD_START + r"orca\s+orchestration\s+send\b(?P<rest>[^;&|\n]*)")
_SKIP = re.compile(SKIP_ENV + r"=(?:\"(?P<dq>[^\"]*)\"|'(?P<sq>[^']*)'|(?P<bare>[^\s;&|]*))")

# Edit・Write でコードとして数える拡張子。.md などの文書や PR の本文は数えない
_CODE_FILE = re.compile(
    r"\.(swift|kt|kts|java|scala|ts|tsx|js|jsx|mjs|cjs|vue|svelte|py|rb|go|rs|c|cc|cpp|h|hpp|m|mm|cs|php|dart|sh)$"
    r"|Package\.swift$")
# Bash での書き換えは、書き込みの先がコードのファイルのときだけ数える。コードのパスが出てくるだけの行
# （`git diff -- A.swift > /tmp/d.txt` や、パスを含むコミットメッセージを printf で書いた行）は数えない。
# .py と .sh を外したのは、`python3 x.py > out.txt` のようにスクリプトを実行しただけの行を書き換えと数えないため
_BASH_CODE_PATH = re.compile(
    r"[\w./-]+\.(?:swift|kt|kts|java|scala|ts|tsx|js|jsx|mjs|cjs|vue|svelte|rb|go|rs|c|cc|cpp|h|hpp|m|mm|cs|php|dart)\b"
    r"|[\w./-]*Package\.swift")
_BASH_REDIRECT_TARGET = re.compile(r"(?:>>?|\btee(?:\s+-a)?)\s*[\"']?([^\s\"';&|)]+)")
_BASH_SCRIPT_WRITE = re.compile(r"open\([^)]*['\"][wa]['\"]|\.write\(|\.write_text\(")
_PYTHON_CODE_ARG = re.compile(
    r"python3?(?:\s+-\w+)*\s+-\s+(?:\S+\s+)*?([\w./-]+\.(?:swift|kt|kts|java|scala|ts|tsx|js|jsx|mjs|cjs|vue|svelte|rb|go|rs|c|cc|cpp|h|hpp|m|mm|cs|php|dart))\s*<<")
_SLASH_COMMAND = re.compile(r"<command-name>/(?:[\w-]+:)?([\w-]+)</command-name>")
_SKILL_FILE = re.compile(r"skills/([\w-]+)/SKILL\.md$")
_STACK_BRANCH = re.compile(r"^(?P<base>.+?(?:pr|/|-|_))(?P<n>\d+)$")

GIT_TIMEOUT_SEC = 5


def trigger(command):
    """止める判定をするコマンドなら (名前, コマンドの頭の VAR=value の並び) を返す。そうでなければ None"""
    m = _PR_CREATE.search(command)
    if m:
        return "gh pr create", m.group("env")
    m = _PR_READY.search(command)
    if m and "--undo" not in m.group("rest"):
        return "gh pr ready", m.group("env")
    m = _WORKER_DONE.search(command)
    if m and re.search(r"--type(?:=|\s+)[\"']?worker_done\b", m.group("rest")):
        return "worker_done", m.group("env")
    return None


def skip_reason(env_prefix):
    """引き金のコマンドの頭に付けた抜け道の理由。変数が無ければ None、あっても理由が空なら ""。
    コマンド全体からは探さない。報告の本文に拒否の文を引用しただけで通らないようにするため"""
    m = _SKIP.search(env_prefix)
    if not m:
        return None
    return (m.group("dq") or m.group("sq") or m.group("bare") or "").strip()


def _skill_of(name, inp):
    """Skill ツールで開いたスキル、または SKILL.md を Read で読んだスキルの名前（プラグインの接頭辞を外す）"""
    if name == "Skill":
        return str(inp.get("skill", "")).split(":")[-1]
    if name == "Read":
        m = _SKILL_FILE.search(str(inp.get("file_path", "")))
        return m.group(1) if m else ""
    return ""


def _outside(path, roots):
    """作業しているリポジトリの外の絶対パスか。PR の本文や補助のスクリプトを置く一時ディレクトリを数えないため。
    /tmp などの場所の名前で外さないのは、リポジトリそのものが一時ディレクトリにあることがあるため（eval の作業場所など）"""
    if not roots or not os.path.isabs(path):
        return False
    real = os.path.realpath(path)
    return not any(real == r or real.startswith(r.rstrip("/") + "/") for r in roots)


def _is_code_edit(name, inp, roots=()):
    if name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = str(inp.get("file_path") or inp.get("notebook_path") or "")
        return bool(_CODE_FILE.search(path)) and not _outside(path, roots)
    if name != "Bash":
        return False
    c = str(inp.get("command", ""))
    code_paths = [m.group(0) for m in _BASH_CODE_PATH.finditer(c) if not _outside(m.group(0), roots)]
    if not code_paths:
        return False
    if re.search(r"\bsed\s+(?:-\w+\s+)*-i", c):
        return True
    if any(_BASH_CODE_PATH.fullmatch(t) and not _outside(t, roots) for t in _BASH_REDIRECT_TARGET.findall(c)):
        return True
    # python の heredoc で、コードのファイルを読んで書き戻す形。パスが文字列の値か、スクリプトの引数のときだけ数える
    # （文の中にファイル名が出てくる本文や、別のファイルを書く fixture の生成を数えないため）
    if not _BASH_SCRIPT_WRITE.search(c):
        return False
    literal = any(_BASH_CODE_PATH.fullmatch(t) and not _outside(t, roots) for t in re.findall(r"[\"']([^\"'\s]+)[\"']", c))
    argument = any(not _outside(t, roots) for t in _PYTHON_CODE_ARG.findall(c))
    return literal or argument


def _user_slash_commands(message):
    """利用者が打ったスラッシュコマンドの名前。ツールの結果に出た同じ文字列は数えない"""
    content = message.get("content")
    if isinstance(content, str):
        texts = [content]
    elif isinstance(content, list) and not any(isinstance(x, dict) and x.get("type") == "tool_result" for x in content):
        texts = [str(x.get("text", "")) for x in content if isinstance(x, dict) and x.get("type") == "text"]
    else:
        texts = []
    return [m.group(1) for t in texts for m in _SLASH_COMMAND.finditer(t)]


def read_history(transcript_path, roots=()):
    """記録を頭から読み、(dev-task-flow を開いたか, 最後のコードの変更の位置, 最後の self-review の位置) を返す"""
    flow, last_edit, last_review, i = False, -1, -1, 0
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            message = d.get("message") if isinstance(d.get("message"), dict) else {}
            if d.get("type") == "user":
                for skill in _user_slash_commands(message):
                    i += 1
                    if skill == "dev-task-flow":
                        flow = True
                    if skill == "self-review":
                        last_review = i
                continue
            if d.get("type") != "assistant":
                continue
            for x in message.get("content") or []:
                if not isinstance(x, dict) or x.get("type") != "tool_use":
                    continue
                i += 1
                name, inp = x.get("name"), x.get("input") if isinstance(x.get("input"), dict) else {}
                skill = _skill_of(name, inp)
                if skill == "dev-task-flow":
                    flow = True
                if skill == "self-review":
                    last_review = i
                if _is_code_edit(name, inp, roots):
                    last_edit = i
    return flow, last_edit, last_review


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=GIT_TIMEOUT_SEC)


def work_roots(cwd):
    """コードの変更として数える場所。hook の cwd と、その git のルート"""
    if not cwd or not os.path.isdir(cwd):
        return []
    roots = [os.path.realpath(cwd)]
    top = _git(cwd, "rev-parse", "--show-toplevel")
    if top.returncode == 0 and top.stdout.strip():
        roots.append(os.path.realpath(top.stdout.strip()))
    return roots


def stack_gaps(cwd):
    """今のブランチを含むスタックで、下の段が隣の上の段に入っていない組を返す。

    スタックは、名前の末尾の番号だけが違うローカルブランチ（feature/x-pr1, feature/x-pr2 や stack/1, stack/2）の連番の組。
    今のブランチを含む組に限るのは、ほかの worktree のブランチ（別のワーカーのスタック）も for-each-ref に出るため。
    upstream が消えた段（[gone]。マージして remote のブランチを消したもの）は、squash で包含が崩れるので見ない。
    """
    repos = [Path(cwd)] + sorted(p.parent for p in Path(cwd).glob("*/.git"))
    gaps = []
    for repo in repos:
        head = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        if head.returncode != 0:
            continue
        current = head.stdout.strip()
        cm = _STACK_BRANCH.match(current)
        if not cm:
            continue
        refs = _git(repo, "for-each-ref", "--format=%(refname:short)\t%(upstream:track)", "refs/heads/")
        if refs.returncode != 0:
            continue
        steps = {}
        for row in refs.stdout.splitlines():
            branch, _, track = row.partition("\t")
            m = _STACK_BRANCH.match(branch)
            if m and m.group("base") == cm.group("base"):
                steps[int(m.group("n"))] = (branch, "gone" in track)
        for n in sorted(steps):
            if n + 1 not in steps:
                continue
            (lower, lower_gone), (upper, _) = steps[n], steps[n + 1]
            if lower_gone:
                continue
            if _git(repo, "merge-base", "--is-ancestor", lower, upper).returncode == 1:
                gaps.append((str(repo), lower, upper))
    return gaps


def deny_reason(what, needs_review, gaps):
    found = []
    if needs_review:
        found.append("最後にコードを変えたあとに self-review を当てていない")
    for repo, lower, upper in gaps:
        found.append(f"スタックの {lower} が {upper} に入っていない（{repo}）")
    return "\n".join([
        f"dev-task-flow の最後の差分の確かめ（{what} の前）: " + "。".join(found) + "。",
        "次にすること:",
        "1. 最後のコミットまでの差分に self-review を当て、指摘を直す。PR が複数なら PR ごとに当てる",
        "2. スタックは、直した段より上の段すべてへ下から順に伝える（merge か restack）。"
        "隣り合う段ごとに `git merge-base --is-ancestor <下の段> <上の段>` が成功することと、各段のテストが通ることを確かめる",
        "3. PR の本文や報告に書く動作確認・QA の結果が、今の head に対するものかを見直す。前の head の結果なら、そう書くか、やり直す",
        f"この判定が誤っているとき（self-review を Skill ツール以外で当てた、下の段が squash でマージ済み、など）だけ、"
        f"コマンドの頭に {SKIP_ENV}=\"<理由>\" を付けて実行し直す。理由は空にしない",
    ])


def decide(data):
    """hook の入力から、止める理由を返す。止めないときは None"""
    if os.environ.get(OFF_ENV, "").lower() in ("0", "off", "false"):
        return None
    if data.get("tool_name") != "Bash":
        return None
    command = str((data.get("tool_input") or {}).get("command", ""))
    found = trigger(command)
    if not found:
        return None
    what, env_prefix = found
    reason = skip_reason(env_prefix)
    if reason:
        return None
    path = data.get("transcript_path")
    if not path or not Path(path).is_file():
        return None
    cwd = data.get("cwd") or "."
    flow, last_edit, last_review = read_history(path, work_roots(cwd))
    if not flow:
        return None
    needs_review = last_edit > last_review
    gaps = stack_gaps(cwd)
    if not (needs_review or gaps):
        return None
    text = deny_reason(what, needs_review, gaps)
    if reason == "":
        text += f"\n（{SKIP_ENV} の理由が空だったので通さなかった）"
    return text


def main():
    # 判定できないとき（入力が読めない、記録が無い、git が固まった、想定しない形）は、作業を止めずに通す
    try:
        reason = decide(json.load(sys.stdin))
    except Exception as e:
        print(f"final_diff_check: 判定できなかったので通した（{e!r}）", file=sys.stderr)
        return
    if reason:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}, ensure_ascii=False))


if __name__ == "__main__":
    main()
