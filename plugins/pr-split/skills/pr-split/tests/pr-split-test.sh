#!/bin/bash
# pr-split.sh の受け入れテスト。外部ツールに依存しない（git / jq のみ。gh は
# このファイルが一時ディレクトリに生成するスタブに差し替える）。
#
# 各ケースは /tmp に作った独立の一時リポジトリ（bare origin + clone）で実行する。
# feat ブランチに「作りきった最終状態」を 1 コミットで持たせる:
#   contract.txt (新規) / viewa.txt (新規) / logic.txt (新規) /
#   f.txt (変更) / old.txt (削除)
# 既定の plan はこれを 3 ノードの木に分ける:
#   feat-pr1-contract (contract.txt, f.txt) ← merge-base
#   ├─ feat-pr2-view  (viewa.txt)
#   └─ feat-pr3-logic (logic.txt, old.txt 削除)
#
# USAGE: ./pr-split-test.sh
set -euo pipefail
TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${TEST_DIR}/../scripts/pr-split.sh"

# --- 最小ハーネス ------------------------------------------------------------
# test_ で始まる関数を定義順に実行する。各ケースはサブシェルで動き、set -e の下で
# 失敗したコマンドか fail 呼び出しでそのケースだけが FAIL になる。

fail() { printf 'FAIL: %s: %s\n' "${_CURRENT}" "$*"; exit 1; }

assert_eq() {
    if [ "$1" != "$2" ]; then
        fail "$3 (expected='$1' actual='$2')"
    fi
}

assert_exit() {
    local expected="$1" label="$2"; shift 2
    [ "$1" = "--" ] && shift
    local rc=0
    "$@" >/dev/null 2>&1 || rc=$?
    if [ "${rc}" -ne "${expected}" ]; then
        fail "$label (expected exit ${expected}, got ${rc})"
    fi
}

run_tests() {
    local names name rc passed=0 failed=0
    names="$(declare -F | awk '$3 ~ /^test_/ { print $3 }')"
    for name in ${names}; do
        _CURRENT="${name}"
        CASE_TMP="$(mktemp -d "${TMPDIR:-/tmp}/prsplit.XXXXXX")"
        (
            set -euo pipefail
            export _CURRENT CASE_TMP
            setup_case
            "${name}"
            printf 'PASS: %s\n' "${name}"
        )
        rc=$?
        rm -rf "${CASE_TMP}"
        if [ "${rc}" -eq 0 ]; then passed=$((passed + 1)); else failed=$((failed + 1)); fi
    done
    printf '%d passed, %d failed\n' "${passed}" "${failed}"
    [ "${failed}" -eq 0 ]
}

# --- gh スタブ ---------------------------------------------------------------
# prs が使う 2 呼び出しに応答する:
#   gh pr list --head <b> --state open --json number --jq .[].number
#     → ${GH_STUB_OPEN} の各行 "<branch> <number>" のうち branch が一致する number
#   gh pr create ...
#     → ${GH_STUB_LOG} に呼び出し全体を 1 行追記（アサーション用）
write_gh_stub() {
    mkdir -p "${CASE_TMP}/bin"
    cat > "${CASE_TMP}/bin/gh" <<'EOF'
#!/bin/bash
case "$1 $2" in
    "pr list")
        head=""
        while [ $# -gt 0 ]; do
            if [ "$1" = "--head" ]; then head="$2"; shift; fi
            shift
        done
        printf '%s\n' "${GH_STUB_OPEN:-}" | awk -v b="${head}" 'NF == 2 && $1 == b { print $2 }'
        ;;
    "pr create")
        if [ -n "${GH_STUB_LOG:-}" ]; then
            printf '%s\n' "$*" >> "${GH_STUB_LOG}"
        fi
        printf 'https://example.invalid/pull/0\n'
        ;;
    *)
        echo "gh stub: unsupported: $*" >&2
        exit 1
        ;;
esac
EOF
    chmod +x "${CASE_TMP}/bin/gh"
}

# --- フィクスチャ -----------------------------------------------------------
# 変数: T（一時ディレクトリの物理パス）, R（clone）
setup_case() {
    T="$(cd "${CASE_TMP}" && pwd -P)"
    write_gh_stub
    export PATH="${T}/bin:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
    git init -q --bare "${T}/origin.git"
    git clone -q "${T}/origin.git" "${T}/repo" 2>/dev/null
    R="${T}/repo"
    cd "${R}"
    git config user.email t@t; git config user.name t
    echo base > f.txt; echo old > old.txt
    git add -A; git commit -qm init; git push -q origin HEAD:main
    git checkout -q -B main origin/main
    git checkout -q -b feat
    echo contract > contract.txt
    echo viewa > viewa.txt
    echo logic > logic.txt
    echo changed > f.txt
    git rm -q old.txt
    git add -A; git commit -qm "final state"
    mkdir -p .pr-split
    write_default_plan
}

# verify_command は既定でファイル存在チェックにする（テストで実ビルドは動かせない）
write_default_plan() {
    cat > .pr-split/plan.json <<'EOF'
{
  "base": "origin/main",
  "verify_command": "test -f contract.txt",
  "nodes": [
    { "n": 1, "slug": "contract", "title": "contract", "parent": null,
      "files": ["contract.txt", "f.txt"] },
    { "n": 2, "slug": "view", "title": "view", "parent": 1,
      "files": ["viewa.txt"] },
    { "n": 3, "slug": "logic", "title": "logic", "parent": 1,
      "files": ["logic.txt", "old.txt"] }
  ]
}
EOF
}

# plan の JSON を jq のフィルタで書き換える
edit_plan() {
    jq "$1" .pr-split/plan.json > .pr-split/plan.json.tmp
    mv .pr-split/plan.json.tmp .pr-split/plan.json
}

# --- validate ----------------------------------------------------------------

test_validate_passes_on_covering_tree_plan() {
    "${SCRIPT}" validate >/dev/null 2>&1
}

test_validate_fails_when_changed_file_is_unassigned() {
    edit_plan '.nodes[2].files = ["logic.txt"]'   # old.txt がどこにも無い
    assert_exit 1 "未割り当てファイルで失敗" -- "${SCRIPT}" validate
}

test_validate_fails_when_file_assigned_twice() {
    edit_plan '.nodes[1].files = ["viewa.txt", "f.txt"]'   # f.txt が pr1 と重複
    assert_exit 1 "二重割り当てで失敗" -- "${SCRIPT}" validate
}

test_validate_fails_when_plan_lists_unchanged_file() {
    edit_plan '.nodes[1].files = ["viewa.txt", "not-changed.txt"]'
    assert_exit 1 "変更されていないファイルで失敗" -- "${SCRIPT}" validate
}

test_validate_fails_when_parent_is_not_a_preceding_node() {
    edit_plan '.nodes[1].parent = 3'   # parent >= n
    assert_exit 1 "parent >= n で失敗" -- "${SCRIPT}" validate
}

test_validate_fails_without_any_verify_command() {
    edit_plan 'del(.verify_command)'
    assert_exit 1 "verify_command 無しで失敗" -- "${SCRIPT}" validate
    # ノード側に全部あれば plan 全体には不要
    edit_plan '.nodes[0].verify_command = "true"
        | .nodes[1].verify_command = "true"
        | .nodes[2].verify_command = "true"'
    "${SCRIPT}" validate >/dev/null 2>&1
}

# --- apply -------------------------------------------------------------------

test_apply_builds_tree_with_correct_parents_and_contents() {
    "${SCRIPT}" apply >/dev/null 2>&1
    local mb pr1 pr2 pr3
    mb="$(git merge-base origin/main feat)"
    pr1="feat-pr1-contract"; pr2="feat-pr2-view"; pr3="feat-pr3-logic"

    assert_eq "${mb}" "$(git rev-parse "${pr1}^")" "pr1 の親は merge-base"
    assert_eq "$(git rev-parse "${pr1}")" "$(git rev-parse "${pr2}^")" "pr2 の親は pr1"
    assert_eq "$(git rev-parse "${pr1}")" "$(git rev-parse "${pr3}^")" "pr3 の親は pr1（pr2 の兄弟）"

    assert_eq "changed" "$(git show "${pr1}:f.txt")" "pr1 に f.txt の変更が入る"
    git cat-file -e "${pr2}:viewa.txt" 2>/dev/null || fail "pr2 に viewa.txt が無い"
    git cat-file -e "${pr2}:logic.txt" 2>/dev/null && fail "pr2 に兄弟の logic.txt が混入した"
    git cat-file -e "${pr3}:old.txt" 2>/dev/null && fail "pr3 で old.txt が削除されていない"
    assert_eq "feat" "$(git rev-parse --abbrev-ref HEAD)" "HEAD が元のブランチに戻る"
}

test_apply_uses_branch_prefix_when_given() {
    edit_plan '.branch_prefix = "20260910-foo"'
    "${SCRIPT}" apply >/dev/null 2>&1
    git rev-parse --verify -q "refs/heads/20260910-foo-pr1-contract" >/dev/null \
        || fail "branch_prefix が使われていない"
}

test_apply_refuses_existing_branch_without_force() {
    git branch feat-pr1-contract
    assert_exit 1 "既存ブランチで失敗" -- "${SCRIPT}" apply
    git rev-parse --verify -q "refs/heads/feat-pr2-view" >/dev/null && fail "pr2 が作られた"
    return 0
}

test_apply_force_recreates_existing_branches() {
    "${SCRIPT}" apply >/dev/null 2>&1
    local before after
    before="$(git rev-parse feat-pr1-contract)"
    # コミット時刻を変えて再作成が別 OID になるようにする
    GIT_COMMITTER_DATE="2030-01-01T00:00:00" FORCE=1 "${SCRIPT}" apply >/dev/null 2>&1
    after="$(git rev-parse feat-pr1-contract)"
    [ "${before}" != "${after}" ] || fail "FORCE=1 で作り直されていない"
}

test_apply_dry_run_creates_nothing() {
    DRY_RUN=1 "${SCRIPT}" apply >/dev/null 2>&1
    git branch --list "feat-pr*" | grep -q . && fail "DRY_RUN でブランチが作られた"
    return 0
}

test_apply_refuses_when_untracked_file_collides_with_assigned_file() {
    # source で削除済みの old.txt は worktree に存在しないので、同じパスに未追跡
    # ファイルを置ける。放置するとブランチ切り替え（old.txt を持つ merge-base へ戻る）で
    # git が上書きを拒否して途中失敗するため、apply は開始前に拒否する
    echo stray > old.txt
    assert_exit 1 "未追跡ファイルとの衝突で失敗" -- "${SCRIPT}" apply
    git branch --list "feat-pr*" | grep -q . && fail "拒否時にブランチが作られた"
    return 0
}

# --- verify ------------------------------------------------------------------

test_verify_runs_command_on_each_branch_and_reports_sibling_isolation() {
    "${SCRIPT}" apply >/dev/null 2>&1
    # 既定の verify_command（test -f contract.txt）は全ノードで通る
    # （contract.txt は root ノードから継承される）
    "${SCRIPT}" verify >/dev/null 2>&1
    # pr3 に兄弟（pr2）のファイルを要求させると失敗する = 枝が隔離されている
    edit_plan '.nodes[2].verify_command = "test -f viewa.txt"'
    assert_exit 1 "兄弟のファイルを要求する verify は失敗" -- "${SCRIPT}" verify
    assert_eq "feat" "$(git rev-parse --abbrev-ref HEAD)" "失敗後も HEAD が元に戻る"
}

test_verify_single_node_via_env() {
    "${SCRIPT}" apply >/dev/null 2>&1
    edit_plan '.nodes[2].verify_command = "false"'
    NODE=2 "${SCRIPT}" verify >/dev/null 2>&1   # 失敗するのは n=3 だけ
    assert_exit 1 "NODE=3 は失敗" -- env NODE=3 "${SCRIPT}" verify
}

# --- prs ---------------------------------------------------------------------

test_prs_creates_prs_with_parent_branch_as_base() {
    "${SCRIPT}" apply >/dev/null 2>&1
    mkdir -p .pr-split/bodies
    printf 'b1\n' > .pr-split/bodies/1.md
    printf 'b2\n' > .pr-split/bodies/2.md
    printf 'b3\n' > .pr-split/bodies/3.md
    edit_plan '.nodes[0].body_file = ".pr-split/bodies/1.md"
        | .nodes[1].body_file = ".pr-split/bodies/2.md"
        | .nodes[2].body_file = ".pr-split/bodies/3.md"'
    GH_STUB_LOG="${T}/gh.log" "${SCRIPT}" prs >/dev/null 2>&1

    grep -q -- "--head feat-pr1-contract --base main" "${T}/gh.log" || fail "pr1 の base が main でない"
    grep -q -- "--head feat-pr2-view --base feat-pr1-contract" "${T}/gh.log" || fail "pr2 の base が pr1 でない"
    grep -q -- "--head feat-pr3-logic --base feat-pr1-contract" "${T}/gh.log" || fail "pr3 の base が pr1 でない"
    # push されている（bare origin に ref がある）
    git -C "${T}/origin.git" rev-parse --verify -q "refs/heads/feat-pr2-view" >/dev/null \
        || fail "pr2 が origin に push されていない"
}

test_prs_fails_without_body_files() {
    "${SCRIPT}" apply >/dev/null 2>&1
    assert_exit 1 "body_file 不足で失敗" -- "${SCRIPT}" prs
}

test_prs_skips_branch_with_existing_open_pr() {
    "${SCRIPT}" apply >/dev/null 2>&1
    mkdir -p .pr-split/bodies
    printf 'b\n' > .pr-split/bodies/1.md
    edit_plan '.nodes[0].body_file = ".pr-split/bodies/1.md"
        | .nodes[1].body_file = ".pr-split/bodies/1.md"
        | .nodes[2].body_file = ".pr-split/bodies/1.md"'
    GH_STUB_LOG="${T}/gh.log" GH_STUB_OPEN="feat-pr1-contract 10" \
        "${SCRIPT}" prs >/dev/null 2>&1
    grep -q -- "--head feat-pr1-contract" "${T}/gh.log" && fail "既存 PR があるのに create された"
    grep -q -- "--head feat-pr2-view" "${T}/gh.log" || fail "pr2 が create されていない"
}

run_tests
