#!/bin/bash
# 宿主机入口：遍历 workloads 下各 .gz，在 Docker 容器内通过 auto_run.sh 执行
# 若设置 DOCKER_CONTAINER，则用 docker exec 在容器内跑；未设置则在本机直接跑（适用于脚本在容器内执行）
# 目录结构预期：workloads/<bench>/<id>/ 下存在 .gz
# 用法：
#   DOCKER_CONTAINER=gem5-ggy ./run_cpts.sh           # 宿主机：在容器内跑每个 cpt
#   ./run_cpts.sh --list                              # 只显示 workloads 目录结构
#   ./run_cpts.sh --dry-run [--foreground]            # 只列出将要运行的 cpt
#   DOCKER_CONTAINER=gem5-ggy ./run_cpts.sh --foreground  # 顺序前台执行
#   DOCKER_CONTAINER=gem5-ggy ./run_cpts.sh --batch-size 5 # 后台每批最多 5 个，跑完再提交下一批
# 环境变量：
#   DOCKER_CONTAINER  容器名（如 gem5-ggy）；设置后则在容器内执行 auto_run.sh
#   CONTAINER_GEM5    容器内 GEM5 根目录（默认 /gem5），需与挂载一致
#   GEM5_HOME         宿主机上 GEM5 目录（默认脚本所在目录）
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 宿主机 GEM5 目录（脚本所在目录或显式设置）
GEM5_HOME="${GEM5_HOME:-$SCRIPT_DIR}"
# 容器内 GEM5 根目录（仅在使用 DOCKER_CONTAINER 时用于转换路径）
CONTAINER_GEM5="${CONTAINER_GEM5:-/gem5}"

WORKLOADS_DIR="${WORKLOADS_DIR:-${GEM5_HOME}/workloads}"
LOG_DIR="${GEM5_HOME}/cpt_logs"
M5OUT_SAVED="${M5OUT_SAVED:-${GEM5_HOME}/m5out_saved}"
BUILD_TARGET="build/RISCV/gem5.opt"
CONFIG_FILE="${GEM5_HOME}/configs/example/kmhv3.py"

export GCB_RESTORER=""

DRY_RUN=false
FOREGROUND=false
LIST_ONLY=false
BATCH_SIZE="${BATCH_SIZE:-5}"
RUN_LIMIT=""
for arg in "$@"; do
    case "$arg" in
        --dry-run)    DRY_RUN=true ;;
        --foreground) FOREGROUND=true ;;
        --list)       LIST_ONLY=true ;;
        --batch-size=*) BATCH_SIZE="${arg#--batch-size=}" ;;
        --limit=*)    RUN_LIMIT="${arg#--limit=}" ;;
        --help|-h)
            echo "用法: $0 [--dry-run] [--foreground] [--list] [--limit=N]"
            echo "  --dry-run    只列出要运行的 cpt，不执行"
            echo "  --foreground 顺序前台执行，不后台（便于调试）"
            echo "  --list       只显示 workloads 目录结构后退出"
            echo "  --limit=N    只运行前 N 个 cpt（用于试跑）"
            echo "  --batch-size N 后台模式：每批最多同时跑 N 个（默认 ${BATCH_SIZE}，也可用环境变量 BATCH_SIZE 覆盖）"
            echo "环境变量（宿主机入口时建议设置）:"
            echo "  DOCKER_CONTAINER  容器名（如 gem5-ggy），设置后则在容器内执行"
            echo "  CONTAINER_GEM5    容器内 GEM5 根目录（默认 /gem5）"
            echo "  GEM5_HOME         宿主机 GEM5 目录（默认脚本所在目录）"
            echo "  WORKLOADS_DIR     cpt 根目录（默认 \$GEM5_HOME/workloads）"
            echo "  M5OUT_SAVED       m5out 保存根目录（默认 \$GEM5_HOME/m5out_saved）"
            exit 0
            ;;
    esac
done
if [[ "$BATCH_SIZE" =~ ^[0-9]+$ ]]; then
    :
else
    echo "错误：--batch-size 需要是正整数，当前: $BATCH_SIZE" >&2
    exit 1
fi

# find 默认不跟随符号链接，若 WORKLOADS_DIR 是 symlink 则不会进入其目标目录，导致统计为 0。解析为规范路径。
if [[ -d "$WORKLOADS_DIR" ]]; then
    resolved_workloads="$(realpath "$WORKLOADS_DIR" 2>/dev/null)" || resolved_workloads="$(readlink -f "$WORKLOADS_DIR" 2>/dev/null)"
    [[ -n "$resolved_workloads" ]] && WORKLOADS_DIR="$resolved_workloads"
fi

# 显示 workloads 目录结构（2 层 + 每子目录下前几条文件）
show_workloads_structure() {
    echo "目录: $WORKLOADS_DIR"
    if [[ ! -d "$WORKLOADS_DIR" ]]; then
        echo "  (不存在)"
        return
    fi
    for d1 in "$WORKLOADS_DIR"/*; do
        [[ -e "$d1" ]] || continue
        echo "  $(basename "$d1")/"
        if [[ -d "$d1" ]]; then
            for d2 in "$d1"/*; do
                [[ -e "$d2" ]] || continue
                echo "    $(basename "$d2")/"
                if [[ -d "$d2" ]]; then
                    for f in "$d2"/*; do
                        [[ -e "$f" ]] || continue
                        echo "      $(basename "$f")"
                    done
                else
                    echo "      $(basename "$d2")"
                fi
            done
        fi
    done
    local gz_count
    # -L 跟随符号链接下降（子目录若为 symlink 则默认 find 不进入，统计为 0）
    gz_count=$(find -L "$WORKLOADS_DIR" \( -type f -o -type l \) -name "*.gz" 2>/dev/null | wc -l)
    echo "---"
    echo "当前 .gz 文件数: ${gz_count}"
}

if $LIST_ONLY; then
    show_workloads_structure
    exit 0
fi

if [[ ! -d "$WORKLOADS_DIR" ]]; then
    echo "错误：workloads 目录不存在: $WORKLOADS_DIR"
    echo "可设置: WORKLOADS_DIR=/path/to/cpts $0"
    exit 1
fi

# 使用 Docker 时不在宿主机检查 gem5/auto_run（在容器内执行）
if [[ -z "${DOCKER_CONTAINER:-}" ]]; then
    if [[ ! -f "${GEM5_HOME}/${BUILD_TARGET}" ]]; then
        echo "错误：gem5 未编译，请先运行 auto_run.sh 完成编译: ${GEM5_HOME}/${BUILD_TARGET}"
        exit 1
    fi
    if [[ ! -x "${GEM5_HOME}/auto_run.sh" ]]; then
        echo "错误：未找到可执行脚本 ${GEM5_HOME}/auto_run.sh"
        exit 1
    fi
    export GEM5_HOME
    export M5OUT_SAVED
else
    if ! docker exec "${DOCKER_CONTAINER}" test -d "${CONTAINER_GEM5}" 2>/dev/null; then
        echo "错误：容器 ${DOCKER_CONTAINER} 内不存在目录 ${CONTAINER_GEM5}，请检查挂载与 CONTAINER_GEM5"
        exit 1
    fi
    if ! docker exec "${DOCKER_CONTAINER}" test -x "${CONTAINER_GEM5}/auto_run.sh" 2>/dev/null; then
        echo "错误：容器内未找到可执行脚本 ${CONTAINER_GEM5}/auto_run.sh"
        exit 1
    fi
    echo "在容器内执行: DOCKER_CONTAINER=${DOCKER_CONTAINER}, CONTAINER_GEM5=${CONTAINER_GEM5}"
fi

mkdir -p "$LOG_DIR"
mkdir -p "$M5OUT_SAVED"
echo "日志目录: $LOG_DIR"
echo "m5out 按 workload 保存到: $M5OUT_SAVED"
echo "workloads 目录: $WORKLOADS_DIR"
if [[ -n "${DOCKER_CONTAINER:-}" ]]; then
    echo "执行方式: 在容器 ${DOCKER_CONTAINER} 内运行 (CONTAINER_GEM5=${CONTAINER_GEM5})"
else
    echo "执行方式: 在宿主机直接运行（未设置 DOCKER_CONTAINER）"
fi

# 收集所有 .gz 文件（-L 跟随 symlink 进入子目录）
cpt_files=()
while IFS= read -r f; do
    [[ -n "$f" ]] && cpt_files+=("$f")
done < <(find -L "$WORKLOADS_DIR" \( -type f -o -type l \) -name "*.gz" 2>/dev/null | sort)

if [[ ${#cpt_files[@]} -eq 0 ]]; then
    echo "未在 $WORKLOADS_DIR 下找到任何 .gz checkpoint 文件。"
    echo ""
    echo "当前目录结构："
    show_workloads_structure
    echo ""
    echo "若 cpt 在别处（如容器内挂载），请设置: WORKLOADS_DIR=/gem5/workloads $0"
    exit 0
fi

echo "共找到 ${#cpt_files[@]} 个 checkpoint 文件。"
if [[ -n "$RUN_LIMIT" ]]; then
    if [[ ! "$RUN_LIMIT" =~ ^[0-9]+$ ]]; then
        echo "错误：--limit 需要是正整数，当前: $RUN_LIMIT" >&2
        exit 1
    fi
    cpt_files=("${cpt_files[@]:0:$RUN_LIMIT}")
    echo "仅运行前 ${RUN_LIMIT} 个（--limit=${RUN_LIMIT}）。"
fi
total_cpts=${#cpt_files[@]}

# 生成简短日志文件名：相对 workloads 的路径，/ 替换为 _
log_name() {
    local path="$1"
    local rel="${path#"$WORKLOADS_DIR"}"
    rel="${rel#/}"
    echo "${rel//\//_}"
}

# 将宿主机 cpt 路径转为容器内路径（仅当 DOCKER_CONTAINER 设置时使用）
host_to_container_cpt() {
    local host_cpt="$1"
    local rel="${host_cpt#"$GEM5_HOME"}"
    rel="${rel#/}"
    echo "${CONTAINER_GEM5}/${rel}"
}

run_one() {
    local cpt="$1"
    local logpath="$2"
    local base="$3"
    local outdir="${M5OUT_SAVED}/${base}"
    if $DRY_RUN; then
        if [[ -n "${DOCKER_CONTAINER:-}" ]]; then
            echo "  [dry-run] docker exec ... auto_run.sh --run-only --cpt $(host_to_container_cpt "$cpt") -> $logpath"
        else
            echo "  [dry-run] auto_run.sh --run-only --cpt $cpt -> $logpath, m5out -> $outdir"
        fi
        return 0
    fi
    if [[ -n "${DOCKER_CONTAINER:-}" ]]; then
        local cpt_inside
        cpt_inside="$(host_to_container_cpt "$cpt")"
        # 通过环境变量传入 cpt 路径，避免并发时 bash -c 字符串中变量错用导致所有任务跑同一 checkpoint
        local conda_sh="${CONTAINER_CONDA_SH:-/opt/miniconda3/etc/profile.d/conda.sh}"
        local conda_sh_q
        conda_sh_q="$(printf '%q' "$conda_sh")"
        # 注意：必须让容器内 bash 展开 $GEM5_CPT_PATH，不要用 \"\$GEM5_CPT_PATH\"（容器内会变成字面量 $GEM5_CPT_PATH）
        local inner_cmd="source $conda_sh_q && conda activate py38 && export LD_LIBRARY_PATH=\$CONDA_PREFIX/lib:\${LD_LIBRARY_PATH:-} && export GEM5_HOME=${CONTAINER_GEM5} && export M5OUT_SAVED=${CONTAINER_GEM5}/m5out_saved && cd \${GEM5_HOME} && ./auto_run.sh --run-only --skip-conda --cpt \$GEM5_CPT_PATH"
        if $FOREGROUND; then
            echo "=== 运行(容器): $cpt -> $cpt_inside (m5out 保存到 ${CONTAINER_GEM5}/m5out_saved/...) ==="
            docker exec -i -e GEM5_CPT_PATH="${cpt_inside}" "${DOCKER_CONTAINER}" bash -c "$inner_cmd" 2>&1 | tee "$logpath"
            run_rc=${PIPESTATUS[0]}
            if [[ $run_rc -ne 0 ]]; then
                echo "[退出码 $run_rc] 详见: $logpath" >&2
            fi
        else
            nohup docker exec -i -e GEM5_CPT_PATH="${cpt_inside}" "${DOCKER_CONTAINER}" bash -c "$inner_cmd" > "$logpath" 2>&1 &
            LAST_BG_PID=$!
            echo "  后台 PID $! : $cpt -> $logpath, m5out -> ${CONTAINER_GEM5}/m5out_saved/..."
        fi
    else
        if $FOREGROUND; then
            echo "=== 运行: $cpt (m5out 保存到 $outdir) ==="
            "${GEM5_HOME}/auto_run.sh" --run-only --cpt "${cpt}" 2>&1 | tee "$logpath"
            run_rc=${PIPESTATUS[0]}
            if [[ $run_rc -ne 0 ]]; then
                echo "[退出码 $run_rc] 详见: $logpath" >&2
            fi
        else
            nohup "${GEM5_HOME}/auto_run.sh" --run-only --cpt "${cpt}" > "$logpath" 2>&1 &
            LAST_BG_PID=$!
            echo "  后台 PID $! : $cpt -> $logpath, m5out -> $outdir"
        fi
    fi
}

cd "$GEM5_HOME"
idx=0
batch_inflight=0
batch_pids=()
for cpt in "${cpt_files[@]}"; do
    idx=$((idx + 1))
    base="$(log_name "$cpt")"
    logpath="${LOG_DIR}/${base}.log"
    echo "[${idx}/${total_cpts}] 即将运行: ${base}"
    run_one "$cpt" "$logpath" "$base"
    if ! $FOREGROUND && ! $DRY_RUN; then
        batch_inflight=$((batch_inflight + 1))
        batch_pids+=("${LAST_BG_PID:-}")
        # 控制后台并发：每批最多 BATCH_SIZE 个，跑完这一批再继续提交下一批
        if [[ "$BATCH_SIZE" -gt 0 && "$batch_inflight" -ge "$BATCH_SIZE" ]]; then
            echo "已提交本批 ${batch_inflight} 个任务，等待本批完成后继续..."
            # 显式等待本批 PID，避免 wait 误判
            wait "${batch_pids[@]}" || true
            batch_inflight=0
            batch_pids=()
        else
            sleep 1
        fi
    fi
done
if ! $FOREGROUND && ! $DRY_RUN && [[ "$batch_inflight" -gt 0 ]]; then
    echo "等待最后一批 ${batch_inflight} 个任务完成..."
    wait "${batch_pids[@]}" || true
fi

if $DRY_RUN; then
    echo "dry-run 结束，未执行任何任务。"
elif $FOREGROUND; then
    echo "所有任务（前台）已执行完毕。"
    echo "若某任务很快结束或异常，请查看对应日志: $LOG_DIR"
    if [[ -z "${DOCKER_CONTAINER:-}" ]]; then
        echo "提示：未设置 DOCKER_CONTAINER，任务在宿主机执行。若需在容器内跑请: DOCKER_CONTAINER=gem5-ggy $0 --foreground"
    fi
else
    echo "已提交 ${#cpt_files[@]} 个后台任务，日志见: $LOG_DIR"
fi
