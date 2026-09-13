#!/usr/bin/env bash
# 创建 / 清理泳道工作区（git worktree）+ 认领登记。
#
# 为什么需要它（2026-09-13 教训）：多个 AI 会话如果共用同一个工作目录，
# `git commit` 提交到哪个分支取决于「谁最后切换了 HEAD」——实测导致两次提交错位、
# 一个会话被迫重做工作（见 feature/task-071 的提交信息）。**一个会话必须独占一个工作区。**
#
# 用法：
#   bash scripts/lane-worktrees.sh create                  # 创建 zace-lane-a .. zace-lane-j
#   bash scripts/lane-worktrees.sh claim <lane> <卡号>      # 登记认领（写 .lane-owner，防抢占）
#   bash scripts/lane-worktrees.sh release <lane>           # 释放认领
#   bash scripts/lane-worktrees.sh status                   # 看每个工作区的分支、认领、脏状态
#   bash scripts/lane-worktrees.sh remove <lane>            # 删除单个（必须已合并+干净）
#   bash scripts/lane-worktrees.sh remove-all               # 删除全部空闲工作区
#   bash scripts/lane-worktrees.sh guard                    # 主工作区防误用检查（在 main 且干净）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$(dirname "$ROOT")"
LANES=(a b c d e f g h i j)
CMD="${1:-create}"

lane_dir() { echo "$BASE/zace-lane-$1"; }
lane_owner_file() { echo "$(lane_dir "$1")/.lane-owner"; }

# 主工作区是否处于"可集成"状态（在 main 且工作区干净）
main_is_clean() {
  [ "$(git -C "$ROOT" branch --show-current 2>/dev/null)" = "main" ] \
    && [ -z "$(git -C "$ROOT" status --porcelain)" ]
}

case "$CMD" in
  create)
    for L in "${LANES[@]}"; do
      WT="$(lane_dir "$L")"
      if [ -e "$WT" ]; then
        echo "跳过（已存在）：$WT"
        continue
      fi
      git -C "$ROOT" worktree add --detach "$WT" >/dev/null
      echo "已创建：$WT"
    done
    echo
    echo "下一步（重要）："
    echo "  1) 每个会话认领一个：bash scripts/lane-worktrees.sh claim <lane> TASK-xxx"
    echo "  2) 会话的工作目录必须是自己的 zace-lane-<lane>，且只在那里 commit"
    echo "  3) 主工作区（$ROOT）专用于合并与集成，**不要在它里面改代码**"
    ;;

  claim)
    L="${2:?用法: claim <lane> <卡号>}"; CARD="${3:?用法: claim <lane> <卡号>}"
    WT="$(lane_dir "$L")"
    [ -d "$WT" ] || { echo "工作区不存在：$WT（先跑 create）" >&2; exit 2; }
    OWNER="$(lane_owner_file "$L")"
    if [ -f "$OWNER" ]; then
      echo "警告：lane-$L 已被认领：" >&2
      cat "$OWNER" >&2
      echo "若确认对方已收工，先 release 再 claim。" >&2
      exit 3
    fi
    printf 'card=%s\nowner_pid=%s\nclaimed_at=%s\n' \
      "$CARD" "$$" "$(date -Iseconds)" > "$OWNER"
    echo "lane-$L 已认领 → $CARD"
    ;;

  release)
    L="${2:?用法: release <lane>}"
    OWNER="$(lane_owner_file "$L")"
    if [ -f "$OWNER" ]; then rm -f "$OWNER"; echo "lane-$L 已释放"; else echo "lane-$L 未被认领"; fi
    ;;

  status)
    printf "%-10s %-34s %-26s %s\n" "LANE" "BRANCH" "CLAIMED" "DIRTY"
    for L in "${LANES[@]}"; do
      WT="$(lane_dir "$L")"
      [ -d "$WT" ] || continue
      br=$(git -C "$WT" branch --show-current 2>/dev/null || echo "(detached)")
      if [ -f "$(lane_owner_file "$L")" ]; then
        claimed=$(grep -m1 '^card=' "$(lane_owner_file "$L")" | cut -d= -f2)
      else
        claimed="-"
      fi
      dirty=$(git -C "$WT" status --porcelain 2>/dev/null | wc -l)
      printf "%-10s %-34s %-26s %s\n" "lane-$L" "$br" "$claimed" "$dirty"
    done
    echo
    printf "%-10s %-34s %-26s %s\n" "MAIN" "$(git -C "$ROOT" branch --show-current)" "-" \
      "$(git -C "$ROOT" status --porcelain | wc -l)"
    ;;

  remove)
    L="${2:?用法: remove <lane>}"
    WT="$(lane_dir "$L")"
    [ -d "$WT" ] || { echo "不存在：$WT"; exit 0; }
    # 安全闸：未提交改动或未合并提交一律拒绝
    dirty=$(git -C "$WT" status --porcelain 2>/dev/null | wc -l)
    if [ "$dirty" -ne 0 ]; then
      echo "拒绝删除 lane-$L：有 $dirty 个未提交改动（先提交或 stash）" >&2; exit 4
    fi
    br=$(git -C "$WT" branch --show-current 2>/dev/null || true)
    if [ -n "$br" ] && ! git -C "$ROOT" merge-base --is-ancestor "$br" main 2>/dev/null; then
      echo "拒绝删除 lane-$L：分支 $br 尚未合并进 main" >&2; exit 5
    fi
    [ -f "$(lane_owner_file "$L")" ] && { echo "拒绝删除 lane-$L：仍被认领（先 release）" >&2; exit 6; }
    git -C "$ROOT" worktree remove --force "$WT"
    echo "已删除：$WT"
    ;;

  remove-all)
    for L in "${LANES[@]}"; do
      WT="$(lane_dir "$L")"
      [ -d "$WT" ] || continue
      bash "$0" remove "$L" || echo "跳过 lane-$L（见上方原因）"
    done
    ;;

  guard)
    echo "=== 主工作区用途检查 ==="
    br=$(git -C "$ROOT" branch --show-current)
    dirty=$(git -C "$ROOT" status --porcelain | wc -l)
    echo "分支：$br   未提交改动：$dirty"
    if [ "$br" != "main" ]; then
      echo "❌ 主工作区不在 main —— 若有会话在用它开发，请让它们迁到自己的 lane"
      exit 1
    fi
    if [ "$dirty" -ne 0 ]; then
      echo "⚠️  主工作区有未提交改动 —— 主工作区应专用于集成（合并/推送/评审）"
      exit 1
    fi
    echo "✅ 主工作区状态正确（在 main 且干净）"
    ;;

  *)
    echo "用法：$0 create|claim|release|status|remove <lane>|remove-all|guard" >&2
    exit 2
    ;;
esac
