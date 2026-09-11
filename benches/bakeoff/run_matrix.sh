#!/usr/bin/env bash
# TASK-015A：bake-off 全矩阵驱动（可断点续跑；每一步的产物落在 ~/.cache/zace-bakeoff/）
#
# 用法：
#   bash benches/bakeoff/run_matrix.sh lane1      # e5-small 基线 + 截断 A/B + bge-m3
#   bash benches/bakeoff/run_matrix.sh lane2      # bge-small-zh-v1.5 + arctic-embed-xs
#
# 纪律：**唯一变量是 embedding provider**；本脚本不传任何排序/装填参数
# （`run` 子命令只用 --model / --repo / --golden / --max-input-tokens）。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="$ROOT/.venv/bin/python"
SCRIPT="benches/bakeoff/embed_compare.py"
LOGDIR="$HOME/.cache/zace-bakeoff/logs"
mkdir -p "$LOGDIR"

AIBOX=/home/xuwenzheng/4_AIBOX/gitlab/minicpm/aibox-super-sdk
CAM=/home/xuwenzheng/0_project/main/linux-mtk-mw-cameraservice

# 注意：三个仓库的 golden 目录与仓库一一对应（runner 一次只接受一个 --repo）
run_one() {  # model repo_path repo_name golden [extra args...]
  local model="$1" repo="$2" name="$3" golden="$4"; shift 4
  echo "=== [$(date +%H:%M:%S)] $model @ $name $*"
  ( cd "$ROOT" && "$PY" "$SCRIPT" run --model "$model" --repo "$repo" --repo-name "$name" \
      --golden "$golden" "$@" ) 2>&1 | tee -a "$LOGDIR/${LANE}.log"
  echo "--- exit=$? [$(date +%H:%M:%S)]"
}

case "${1:-}" in
  lane1)
    LANE=lane1
    run_one multilingual-e5-small "$ROOT"                 zace  benches/golden/zace
    run_one multilingual-e5-small "$AIBOX"                aibox benches/golden/aibox-super-sdk
    run_one multilingual-e5-small "$CAM"                  cam   benches/golden/linux-mtk-mw-cameraservice
    # A2 截断 A/B（仅对最终推荐模型；先跑 e5 的 2048 变体）
    run_one multilingual-e5-small "$ROOT"  zace-t2048  benches/golden/zace                    --max-input-tokens 2048
    run_one multilingual-e5-small "$AIBOX" aibox-t2048 benches/golden/aibox-super-sdk          --max-input-tokens 2048
    run_one multilingual-e5-small "$CAM"   cam-t2048   benches/golden/linux-mtk-mw-cameraservice --max-input-tokens 2048
    # 上界参考（多语言大模型，代价优先）：先主靶场 aibox，再 zace，最后 cam
    run_one bge-m3-int8 "$AIBOX" aibox benches/golden/aibox-super-sdk
    run_one bge-m3-int8 "$ROOT"  zace  benches/golden/zace
    run_one bge-m3-int8 "$CAM"   cam   benches/golden/linux-mtk-mw-cameraservice
    ;;
  lane2)
    LANE=lane2
    run_one bge-small-zh-v1.5 "$ROOT"  zace  benches/golden/zace
    run_one bge-small-zh-v1.5 "$AIBOX" aibox benches/golden/aibox-super-sdk
    run_one bge-small-zh-v1.5 "$CAM"   cam   benches/golden/linux-mtk-mw-cameraservice
    run_one arctic-embed-xs "$ROOT"  zace  benches/golden/zace
    run_one arctic-embed-xs "$AIBOX" aibox benches/golden/aibox-super-sdk
    run_one arctic-embed-xs "$CAM"   cam   benches/golden/linux-mtk-mw-cameraservice
    ;;
  *)
    echo "usage: bash benches/bakeoff/run_matrix.sh {lane1|lane2}" >&2
    exit 2
    ;;
esac
echo "=== lane done [$(date +%H:%M:%S)]"
