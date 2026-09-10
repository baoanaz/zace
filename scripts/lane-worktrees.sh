#!/usr/bin/env bash
# 创建 / 清理泳道工作区（git worktree）。每个泳道一个独立目录，多个 AI 会话可同时开工互不干扰。
#
# 用法：
#   bash scripts/lane-worktrees.sh create    # 创建 zace-lane-a .. zace-lane-f（在仓库同级目录）
#   bash scripts/lane-worktrees.sh remove    # 删除全部泳道工作区（不动任何分支与提交）
#   bash scripts/lane-worktrees.sh status    # 查看当前工作区列表
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$(dirname "$ROOT")"
LANES=(a b c d e f)
CMD="${1:-create}"

case "$CMD" in
  create)
    for L in "${LANES[@]}"; do
      WT="$BASE/zace-lane-$L"
      if [ -e "$WT" ]; then
        echo "跳过（已存在）：$WT"
        continue
      fi
      git -C "$ROOT" worktree add --detach "$WT" >/dev/null
      echo "已创建：$WT"
    done
    echo
    echo "下一步：每个泳道开一个 AI 会话，工作目录设为对应的 zace-lane-* 路径，"
    echo "然后粘贴 docs/plan/dispatch.md 里对应泳道的提示词。"
    ;;
  remove)
    for L in "${LANES[@]}"; do
      WT="$BASE/zace-lane-$L"
      if [ ! -e "$WT" ]; then
        echo "不存在：$WT"
        continue
      fi
      git -C "$ROOT" worktree remove --force "$WT"
      echo "已删除：$WT"
    done
    echo "（分支与提交未受影响；如需删除泳道分支：git branch | grep 'task-' 自查后手动删除）"
    ;;
  status)
    git -C "$ROOT" worktree list
    ;;
  *)
    echo "用法：$0 create|remove|status" >&2
    exit 2
    ;;
esac
