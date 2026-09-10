#!/bin/bash
# 作りきったブランチの最終状態（base との diff）を、plan の親子指定に従って
# 「木」構造のブランチ群へ分割する汎用エンジン。
#
# 各ノードのブランチは「最終状態から担当ファイルを取り出した 1 コミット」で作る。
# 途中の作業履歴は保持しない（作りきってから分割するスタイルでは、途中コミットが
# 複数 PR にまたがるため cherry-pick では木を組めない）。
#
# 前提ツール: git / jq / gh（prs のみ）。bash は macOS 標準の 3.2 系で動く
# （連想配列 / mapfile / 負のインデックスは使わない）。
#
# USAGE:
#   pr-split.sh validate [plan.json]   # plan の整合性と diff の被覆を検査
#   pr-split.sh apply    [plan.json]   # ブランチ木を作成
#   pr-split.sh verify   [plan.json]   # 各ノードのブランチで verify_command を実行
#   pr-split.sh prs      [plan.json]   # push + gh pr create（base = 親ブランチ）
#
# plan.json（既定 .pr-split/plan.json、リポジトリルート相対）のスキーマ:
#   {
#     "source": "<最終状態を持つ ref。省略時は現在のブランチ>",
#     "base": "<分割の比較先。省略時 origin/main>",
#     "branch_prefix": "<ブランチ名の接頭辞。省略時は source のブランチ名>",
#     "verify_command": "<ノード検証コマンド。全ノードが個別指定を持つ場合のみ省略可>",
#     "nodes": [
#       { "n": 1, "slug": "contract", "title": "コミット/PR タイトル", "parent": null,
#         "files": ["path/to/file", ...],
#         "body_file": ".pr-split/bodies/1.md",
#         "verify_command": "..." }
#     ]
#   }
#   - ブランチ名は <branch_prefix>-pr<n>-<slug> になる
#   - nodes は n の昇順で書く。parent は親ノードの n（null = base 直下）で、parent < n
#   - base..source の全変更ファイルを、ちょうど 1 つのノードに割り当てる
#   - body_file は prs でのみ必須。verify_command はノード側が plan 全体の値に優先する
#
# 環境変数:
#   DRY_RUN  1 で git / gh の書き込みを行わず予定を表示する
#   FORCE    1 で apply が既存の同名ブランチを削除して作り直す
#   NODE     verify を 1 ノード（n 指定）に絞る
#   DRAFT    1 で prs が --draft を付ける
set -euo pipefail

DRY_RUN="${DRY_RUN:-0}"
FORCE="${FORCE:-0}"
NODE="${NODE:-}"
DRAFT="${DRAFT:-0}"

COMMAND="${1:-}"
PLAN="${2:-.pr-split/plan.json}"

# 依存を持たない最小のログ関数（このスクリプトはプラグインとして任意のリポジトリで
# 動くので、プロジェクト側のログライブラリに依存しない）
log_error()  { printf '[ERROR] %s\n' "$*" >&2; }
log_warn()   { printf '[WARN]  %s\n' "$*" >&2; }
log_step()   { printf '> %s\n' "$*" >&2; }
log_detail() { printf '    %s\n' "$*" >&2; }
log_ok()     { printf 'OK: %s\n' "$*" >&2; }

usage() {
    sed -n '/^# USAGE:/,/^# plan.json/p' "${BASH_SOURCE[0]}" | sed '$d;s/^# \{0,1\}//'
}

case "${COMMAND}" in
    validate|apply|verify|prs) ;;
    *) usage >&2; exit 1 ;;
esac

command -v jq >/dev/null || { log_error "jq が必要です"; exit 1; }
git rev-parse --show-toplevel >/dev/null 2>&1 || { log_error "git リポジトリ内で実行してください"; exit 1; }
cd "$(git rev-parse --show-toplevel)"

# --- plan の読み込み ---------------------------------------------------------
[ -f "${PLAN}" ] || { log_error "plan が見つかりません: ${PLAN}"; exit 1; }
jq empty "${PLAN}" 2>/dev/null || { log_error "plan が JSON として不正です: ${PLAN}"; exit 1; }

SOURCE="$(jq -r '.source // empty' "${PLAN}")"
if [ -z "${SOURCE}" ]; then
    SOURCE="$(git rev-parse --abbrev-ref HEAD)"
    if [ "${SOURCE}" = "HEAD" ]; then
        log_error "HEAD が detached です。plan の source にブランチ名を書いてください"
        exit 1
    fi
fi
BASE="$(jq -r '.base // empty' "${PLAN}")"
BASE="${BASE:-origin/main}"
BRANCH_PREFIX="$(jq -r '.branch_prefix // empty' "${PLAN}")"
BRANCH_PREFIX="${BRANCH_PREFIX:-${SOURCE}}"
PLAN_VERIFY="$(jq -r '.verify_command // empty' "${PLAN}")"

for ref in "${SOURCE}" "${BASE}"; do
    if ! git rev-parse --verify --quiet "${ref}^{commit}" >/dev/null; then
        log_error "ref が見つかりません: ${ref}"
        exit 1
    fi
done
MERGE_BASE="$(git merge-base "${BASE}" "${SOURCE}")"

NODE_COUNT="$(jq '.nodes | length' "${PLAN}")"
if [ "${NODE_COUNT}" -eq 0 ]; then
    log_error "plan に nodes がありません"
    exit 1
fi

# ノードのフィールドを添字が揃った配列として持つ（bash 3.2 に連想配列が無いため）
NODE_NS=()
NODE_SLUGS=()
NODE_TITLES=()
NODE_PARENTS=()      # 親の n。base 直下は空文字
NODE_BODYS=()        # body_file。未指定は空文字
NODE_VERIFYS=()      # verify_command。未指定は空文字
i=0
while [ "${i}" -lt "${NODE_COUNT}" ]; do
    NODE_NS+=("$(jq -r ".nodes[${i}].n // empty" "${PLAN}")")
    NODE_SLUGS+=("$(jq -r ".nodes[${i}].slug // empty" "${PLAN}")")
    NODE_TITLES+=("$(jq -r ".nodes[${i}].title // empty" "${PLAN}")")
    NODE_PARENTS+=("$(jq -r ".nodes[${i}].parent // empty" "${PLAN}")")
    NODE_BODYS+=("$(jq -r ".nodes[${i}].body_file // empty" "${PLAN}")")
    NODE_VERIFYS+=("$(jq -r ".nodes[${i}].verify_command // empty" "${PLAN}")")
    i=$((i + 1))
done

branch_for_index() {
    printf '%s-pr%s-%s' "${BRANCH_PREFIX}" "${NODE_NS[$1]}" "${NODE_SLUGS[$1]}"
}

# 親ノード（n 指定）の添字を返す。無ければ空
index_of_n() {
    local n="$1" j=0
    while [ "${j}" -lt "${NODE_COUNT}" ]; do
        if [ "${NODE_NS[${j}]}" = "${n}" ]; then
            printf '%s' "${j}"
            return 0
        fi
        j=$((j + 1))
    done
}

node_files() {
    jq -r ".nodes[$1].files[]" "${PLAN}"
}

# --- validate ----------------------------------------------------------------
# plan 単体の整合性（フィールド・順序・親子・検証コマンドの有無）と、base..source の
# 変更ファイルがちょうど 1 つのノードに割り当てられていることを検査する。
run_validate() {
    local errors=0 prev_n=0 n slug title parent i

    i=0
    while [ "${i}" -lt "${NODE_COUNT}" ]; do
        n="${NODE_NS[${i}]}"
        slug="${NODE_SLUGS[${i}]}"
        title="${NODE_TITLES[${i}]}"
        parent="${NODE_PARENTS[${i}]}"

        if ! [[ "${n}" =~ ^[0-9]+$ ]] || [ "${n}" -le "${prev_n}" ]; then
            log_error "nodes[${i}]: n は正の整数を昇順・重複なしで書いてください（n=${n}）"
            errors=$((errors + 1))
        fi
        if ! [[ "${slug}" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
            log_error "nodes[${i}]: slug が不正です（英小文字・数字・ハイフンのみ）: '${slug}'"
            errors=$((errors + 1))
        fi
        if [ -z "${title}" ]; then
            log_error "nodes[${i}]: title がありません"
            errors=$((errors + 1))
        fi
        if [ -n "${parent}" ]; then
            # parent < n の強制が親→子の作成順（n 昇順）と DAG であることを同時に保証する
            if ! [[ "${parent}" =~ ^[0-9]+$ ]] || [ "${parent}" -ge "${n}" ] 2>/dev/null \
                || [ -z "$(index_of_n "${parent}")" ]; then
                log_error "nodes[${i}]: parent は先行ノードの n を指定してください（parent=${parent}, n=${n}）"
                errors=$((errors + 1))
            fi
        fi
        if [ "$(jq ".nodes[${i}].files | length" "${PLAN}")" -eq 0 ]; then
            log_error "nodes[${i}]: files が空です"
            errors=$((errors + 1))
        fi
        # ビルドシステムを推測した既定コマンドは持たない。検証内容は plan が明示する
        if [ -z "${NODE_VERIFYS[${i}]}" ] && [ -z "${PLAN_VERIFY}" ]; then
            log_error "nodes[${i}]: verify_command がありません（plan 全体かノードのどちらかに書いてください）"
            errors=$((errors + 1))
        fi
        prev_n="${n}"
        i=$((i + 1))
    done

    # rename を追跡すると「旧パスの削除」と「新パスの追加」を別ノードに割れなくなるので
    # 追跡しない（rename は delete + add の 2 ファイルとして扱う）
    local changed assigned dupes unassigned unknown
    changed="$(git diff --name-only --no-renames "${MERGE_BASE}" "${SOURCE}" | sort)"
    assigned="$(jq -r '.nodes[].files[]' "${PLAN}" | sort)"

    if [ -z "${changed}" ]; then
        log_error "${BASE}..${SOURCE} に変更がありません"
        errors=$((errors + 1))
    fi

    dupes="$(printf '%s\n' "${assigned}" | uniq -d)"
    if [ -n "${dupes}" ]; then
        log_error "複数ノードに割り当てられたファイルがあります"
        printf '%s\n' "${dupes}" | while IFS= read -r f; do log_detail "${f}"; done
        errors=$((errors + 1))
    fi

    unassigned="$(comm -23 <(printf '%s\n' "${changed}") <(printf '%s\n' "${assigned}" | uniq))"
    if [ -n "${unassigned}" ]; then
        log_error "どのノードにも割り当てられていない変更ファイルがあります"
        printf '%s\n' "${unassigned}" | while IFS= read -r f; do log_detail "${f}"; done
        errors=$((errors + 1))
    fi

    unknown="$(comm -13 <(printf '%s\n' "${changed}") <(printf '%s\n' "${assigned}" | uniq))"
    if [ -n "${unknown}" ]; then
        log_error "plan にあるが ${BASE}..${SOURCE} で変更されていないファイルがあります"
        printf '%s\n' "${unknown}" | while IFS= read -r f; do log_detail "${f}"; done
        errors=$((errors + 1))
    fi

    if [ "${errors}" -gt 0 ]; then
        log_error "validate: ${errors} 件の問題があります"
        return 1
    fi

    log_step "PR 木（source=${SOURCE} base=${BASE}）"
    print_subtree "" 0
    log_ok "validate: 問題ありません"
}

# parent が $1（n。root は空文字）のノードを深さ $2 のインデントで再帰表示する
print_subtree() {
    local parent_n="$1" depth="$2" i indent=""
    local d=0
    while [ "${d}" -lt "${depth}" ]; do indent="${indent}  "; d=$((d + 1)); done
    i=0
    while [ "${i}" -lt "${NODE_COUNT}" ]; do
        if [ "${NODE_PARENTS[${i}]}" = "${parent_n}" ]; then
            log_detail "${indent}$(branch_for_index "${i}")  (${NODE_TITLES[${i}]}, $(jq ".nodes[${i}].files | length" "${PLAN}") files)"
            print_subtree "${NODE_NS[${i}]}" $((depth + 1))
        fi
        i=$((i + 1))
    done
}

require_clean_tree() {
    # 未追跡ファイルは許容する（.pr-split/ の plan・body がまさに未追跡のため）。
    # ただし割り当てファイルと同パスの未追跡ファイルはブランチ切り替えで踏むので、
    # require_no_untracked_collision が別途拒否する
    if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
        log_error "作業ツリーがクリーンではありません"
        log_detail "コミットしてから実行してください（最終状態は source ref のコミットから取ります）"
        exit 1
    fi
}

require_no_untracked_collision() {
    local collisions
    collisions="$(comm -12 \
        <(git status --porcelain | awk '/^\?\?/ { print substr($0, 4) }' | sort) \
        <(jq -r '.nodes[].files[]' "${PLAN}" | sort))"
    if [ -n "${collisions}" ]; then
        log_error "割り当てファイルと同じパスに未追跡ファイルがあります"
        printf '%s\n' "${collisions}" | while IFS= read -r f; do log_detail "${f}"; done
        log_detail "退避または削除してから実行してください（ブランチ切り替えで上書き対象になります）"
        exit 1
    fi
}

ORIGINAL_BRANCH=""
remember_original_branch() {
    ORIGINAL_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
}
restore_original_branch() {
    [ -z "${ORIGINAL_BRANCH}" ] && return 0
    local current
    current="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")"
    if [ "${current}" != "${ORIGINAL_BRANCH}" ]; then
        git checkout -q "${ORIGINAL_BRANCH}" 2>/dev/null || true
    fi
}

# --- apply -------------------------------------------------------------------
# n 昇順（= 親が先）にブランチを作る。各ノードは親ブランチ（root は merge-base）から
# 切り、担当ファイルを source の内容で上書き（source に無いものは削除）して 1 コミット。
APPLY_CREATED=()
APPLY_OK=0
cleanup_apply() {
    restore_original_branch
    if [ "${APPLY_OK}" != "1" ] && [ "${#APPLY_CREATED[@]}" -gt 0 ]; then
        # 中途半端な木を残すと再実行時に FORCE が要るだけでなく、壊れたブランチを
        # 本物と誤認しうるので、この実行で作った分は失敗時に消す
        log_warn "失敗したため、この実行で作成したブランチを削除します"
        local b
        for b in ${APPLY_CREATED[@]+"${APPLY_CREATED[@]}"}; do
            git branch -q -D "${b}" 2>/dev/null || true
            log_detail "${b}"
        done
    fi
}

run_apply() {
    run_validate
    require_clean_tree
    require_no_untracked_collision

    local i b existing=""
    i=0
    while [ "${i}" -lt "${NODE_COUNT}" ]; do
        b="$(branch_for_index "${i}")"
        if git rev-parse --verify --quiet "refs/heads/${b}" >/dev/null; then
            existing="${existing}${b}"$'\n'
        fi
        i=$((i + 1))
    done
    if [ -n "${existing}" ]; then
        if [ "${FORCE}" = "1" ]; then
            if [ "${DRY_RUN}" != "1" ]; then
                printf '%s' "${existing}" | while IFS= read -r b; do
                    [ -z "${b}" ] && continue
                    git branch -q -D "${b}"
                done
                log_warn "FORCE=1: 既存ブランチを削除して作り直します"
            fi
        else
            log_error "同名のブランチが既に存在します（FORCE=1 で作り直し）"
            printf '%s' "${existing}" | while IFS= read -r b; do
                [ -z "${b}" ] && continue
                log_detail "${b}"
            done
            exit 1
        fi
    fi

    remember_original_branch
    trap cleanup_apply EXIT

    i=0
    while [ "${i}" -lt "${NODE_COUNT}" ]; do
        b="$(branch_for_index "${i}")"
        local parent_n="${NODE_PARENTS[${i}]}" start
        if [ -z "${parent_n}" ]; then
            start="${MERGE_BASE}"
        else
            start="$(branch_for_index "$(index_of_n "${parent_n}")")"
        fi

        if [ "${DRY_RUN}" = "1" ]; then
            log_step "（dry-run）${b} ← ${start}"
            node_files "${i}" | while IFS= read -r f; do log_detail "${f}"; done
            i=$((i + 1))
            continue
        fi

        log_step "${b} ← ${start}"
        git checkout -q -b "${b}" "${start}"

        local f
        while IFS= read -r f; do
            if git cat-file -e "${SOURCE}:${f}" 2>/dev/null; then
                # `git checkout <ref> -- <path>` は index と worktree の両方を更新する
                git checkout -q "${SOURCE}" -- "${f}"
            else
                git rm -q -- "${f}"
            fi
        done < <(node_files "${i}")

        if git diff --cached --quiet; then
            log_error "${b}: 担当ファイルの内容が起点と同一で、空のコミットになります"
            log_detail "親ノードとの分担か files の割り当てを見直してください"
            exit 1
        fi
        git commit -q -m "${NODE_TITLES[${i}]}"
        APPLY_CREATED+=("${b}")
        i=$((i + 1))
    done

    APPLY_OK=1
    if [ "${DRY_RUN}" = "1" ]; then
        log_ok "dry-run のためブランチは作成していません"
    else
        log_ok "${#APPLY_CREATED[@]} ブランチを作成しました"
    fi
}

# --- verify ------------------------------------------------------------------
# 各ノードのブランチをこの worktree で checkout して verify_command を実行する。
# 一時 worktree ではなく現在の worktree を使うのは、ビルドキャッシュを温かいまま
# 使うため（KMP 等ではビルド成果物が worktree あたり GB 単位になる）。
run_verify() {
    require_clean_tree
    require_no_untracked_collision
    remember_original_branch
    trap restore_original_branch EXIT

    local i b cmd failed="" ran=0
    i=0
    while [ "${i}" -lt "${NODE_COUNT}" ]; do
        if [ -n "${NODE}" ] && [ "${NODE_NS[${i}]}" != "${NODE}" ]; then
            i=$((i + 1))
            continue
        fi
        b="$(branch_for_index "${i}")"
        cmd="${NODE_VERIFYS[${i}]:-${PLAN_VERIFY}}"

        if ! git rev-parse --verify --quiet "refs/heads/${b}" >/dev/null; then
            log_error "ブランチがありません（先に apply してください）: ${b}"
            exit 1
        fi

        if [ "${DRY_RUN}" = "1" ]; then
            log_step "（dry-run）${b}"
            log_detail "${cmd}"
            i=$((i + 1))
            ran=$((ran + 1))
            continue
        fi

        log_step "${b}: ${cmd}"
        git checkout -q "${b}"
        # 1 ノードの失敗で止めず全ノードの結果を集計する（どの枝が壊れているかを
        # 一度の実行で把握できないと、ノード数ぶん再実行することになる）
        if bash -c "${cmd}"; then
            log_ok "${b}"
        else
            log_error "verify 失敗: ${b}"
            failed="${failed}${b}"$'\n'
        fi
        ran=$((ran + 1))
        i=$((i + 1))
    done

    if [ -n "${NODE}" ] && [ "${ran}" -eq 0 ]; then
        log_error "NODE=${NODE} に一致するノードがありません"
        exit 1
    fi
    if [ -n "${failed}" ]; then
        log_error "verify に失敗したブランチ:"
        printf '%s' "${failed}" | while IFS= read -r b; do
            [ -z "${b}" ] && continue
            log_detail "${b}"
        done
        exit 1
    fi
    log_ok "verify: ${ran} ノードすべて成功しました"
}

# --- prs ---------------------------------------------------------------------
# 全ブランチを push し、ノードごとに gh pr create する。base は親ブランチ
# （root ノードは plan の base から origin/ を除いたもの）。既に open な PR が
# あるノードはスキップするので、途中失敗後の再実行がそのまま継続になる。
run_prs() {
    command -v gh >/dev/null || { log_error "gh が必要です"; exit 1; }

    local i b missing=""
    i=0
    while [ "${i}" -lt "${NODE_COUNT}" ]; do
        b="$(branch_for_index "${i}")"
        if ! git rev-parse --verify --quiet "refs/heads/${b}" >/dev/null; then
            log_error "ブランチがありません（先に apply してください）: ${b}"
            exit 1
        fi
        if [ -z "${NODE_BODYS[${i}]}" ] || [ ! -f "${NODE_BODYS[${i}]}" ]; then
            missing="${missing}n=${NODE_NS[${i}]}: ${NODE_BODYS[${i}]:-body_file 未指定}"$'\n'
        fi
        i=$((i + 1))
    done
    if [ -n "${missing}" ]; then
        # 一部だけ PR が立つと「本文を後から書く」作業が PR 側に散らばるので、全 body が
        # 揃ってから一括で作る
        log_error "body_file が不足しています"
        printf '%s' "${missing}" | while IFS= read -r m; do
            [ -z "${m}" ] && continue
            log_detail "${m}"
        done
        exit 1
    fi

    local push_branches=()
    i=0
    while [ "${i}" -lt "${NODE_COUNT}" ]; do
        push_branches+=("$(branch_for_index "${i}")")
        i=$((i + 1))
    done

    if [ "${DRY_RUN}" = "1" ]; then
        log_step "（dry-run）push 予定"
        log_detail "git push --atomic -u origin ${push_branches[*]}"
    else
        log_step "push (${#push_branches[@]} ブランチ)"
        git push -q --atomic -u origin "${push_branches[@]}"
    fi

    local base_branch parent_n pr_args existing
    i=0
    while [ "${i}" -lt "${NODE_COUNT}" ]; do
        b="$(branch_for_index "${i}")"
        parent_n="${NODE_PARENTS[${i}]}"
        if [ -z "${parent_n}" ]; then
            base_branch="${BASE#origin/}"
        else
            base_branch="$(branch_for_index "$(index_of_n "${parent_n}")")"
        fi
        pr_args=(pr create --head "${b}" --base "${base_branch}" \
            --title "${NODE_TITLES[${i}]}" --body-file "${NODE_BODYS[${i}]}")
        if [ "${DRAFT}" = "1" ]; then
            pr_args+=(--draft)
        fi

        if [ "${DRY_RUN}" = "1" ]; then
            log_step "（dry-run）gh ${pr_args[*]}"
            i=$((i + 1))
            continue
        fi

        existing="$(gh pr list --head "${b}" --state open --json number --jq '.[].number' 2>/dev/null || echo "")"
        if [ -n "${existing}" ]; then
            log_warn "${b}: open な PR #${existing} が既にあるためスキップします"
            i=$((i + 1))
            continue
        fi

        log_step "${b} → base ${base_branch}"
        gh "${pr_args[@]}" >/dev/null
        i=$((i + 1))
    done
    log_ok "prs 完了"
}

case "${COMMAND}" in
    validate) run_validate ;;
    apply)    run_apply ;;
    verify)   run_verify ;;
    prs)      run_prs ;;
esac
