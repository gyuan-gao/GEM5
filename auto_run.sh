#!/bin/bash
# 文件名：auto_run.sh
# 设计在 gem5-ggy 容器内、从 /gem5 目录执行（如：docker exec -it gem5-ggy bash，然后 cd /gem5 && ./auto_run.sh）
# 用法：
#   ./auto_run.sh [--first-run] [--raw | --cpt [FILE]]
#   ./auto_run.sh --first-run   # 首次执行：创建环境、编译、再按当前模式运行
#   ./auto_run.sh               # 默认：编译 + raw-cpt（裸二进制 .bin）
#   ./auto_run.sh --raw         # 显式：raw checkpoint
#   ./auto_run.sh --cpt [FILE]  # 单个 checkpoint .gz（默认 FILE 见下 CPT_FILE）
#   ./auto_run.sh --run-only --cpt FILE   # 仅运行：不编译，只跑指定 cpt（供 run_cpts.sh 调用）
# 环境变量：GEM5_HOME、M5OUT_SAVED 未设置时容器内默认 /gem5、/gem5/m5out_saved
export CONDA_PLUGINS_AUTO_ACCEPT_TOS=true
set -e  # 遇到错误立即退出

# 环境变量：容器内通常在 /gem5 下执行，未设置时默认 /gem5
GEM5_HOME="${GEM5_HOME:-/gem5}"
export NEMU_HOME="${GEM5_HOME}/nemu"
SPEC_FILE="${GEM5_HOME}/ext/xs_env/gem5-py38.txt"
CONFIG_FILE="${GEM5_HOME}/configs/example/kmhv3.py"
BUILD_TARGET="build/RISCV/gem5.opt"

# raw 模式：裸二进制 .bin（--raw-cpt 必须用 .bin，不能是 .gz）
RAW_BINARY="${GEM5_HOME}/ready-to-run/coremark-2-iteration.bin"
# cpt 模式：单个 checkpoint .gz 文件（--generic-rv-cpt=/path/to/checkpoint.gz，不加 --raw-cpt）
CPT_FILE="${GEM5_HOME}/workloads/500.perlbench_r_10G/0/_0_0.003745_memory_.gz"

# 解析参数：运行模式 + 是否首次 + 是否仅运行（不编译）+ 是否由调用方已激活 conda
RUN_MODE="raw"
FIRST_RUN=false
RUN_ONLY=false
SKIP_CONDA=false
CPT_FILE_OVERRIDE=""
for arg in "$@"; do
    case "$arg" in
        --first-run) FIRST_RUN=true ;;
        --raw)       RUN_MODE="raw" ;;
        --cpt)       RUN_MODE="cpt" ;;
        --run-only)  RUN_ONLY=true ;;
        --skip-conda) SKIP_CONDA=true ;;
        --cpt=*)     RUN_MODE="cpt"; CPT_FILE_OVERRIDE="${arg#--cpt=}" ;;
        --help|-h)
            echo "用法: $0 [--first-run] [--raw | --cpt [FILE]] [--run-only [--skip-conda] --cpt FILE]"
            echo "  --first-run  首次执行（创建 py38 环境、编译 nemu 等）"
            echo "  --raw        使用 raw checkpoint（裸二进制 .bin），默认"
            echo "  --cpt [FILE] 使用单个 checkpoint .gz（FILE 默认见脚本内 CPT_FILE）"
            echo "  --run-only --cpt FILE  仅运行该 cpt，不编译（供 run_cpts.sh 调用）"
            echo "  --skip-conda  调用方已激活 conda 时使用，本脚本不再 source/activate"
            exit 0
            ;;
        -*)
            echo "未知参数: $arg" >&2
            exit 1
            ;;
        *)
            if [[ "$RUN_MODE" == "cpt" && -z "$CPT_FILE_OVERRIDE" && -n "$arg" ]]; then
                CPT_FILE_OVERRIDE="$arg"
            elif [[ -n "$arg" ]]; then
                echo "未知参数: $arg" >&2
                exit 1
            fi
            ;;
    esac
done
if [[ -n "$CPT_FILE_OVERRIDE" ]]; then
    CPT_FILE="$CPT_FILE_OVERRIDE"
fi
# 调试：确认实际使用的 checkpoint 路径（便于排查“所有 cpt 结果相同”问题）
if [[ "$RUN_MODE" == "cpt" ]]; then
    echo "[DEBUG] CPT_FILE=${CPT_FILE} GEM5_CPT_PATH=${GEM5_CPT_PATH:-<unset>}" >&2
fi

# 新版本切片/裸机程序可不使用 GCPT 恢复器，设为空即跳过
export GCB_RESTORER=""

# 启用 conda（--skip-conda 时由调用方如 run_cpts.sh 在容器内已激活，本脚本不再处理）
if ! $SKIP_CONDA; then
    CONDA_SH=""
    for base in "${CONDA_ROOT:-}" /opt/miniconda3 /opt/conda /root/miniconda3 "${HOME:-/root}/miniconda3"; do
        [[ -z "$base" ]] && continue
        if [[ -f "${base}/etc/profile.d/conda.sh" ]]; then
            CONDA_SH="${base}/etc/profile.d/conda.sh"
            break
        fi
    done
    # 通过 conda 可执行路径反推 base（不依赖 conda info --base，在非交互 shell 更可靠）
    if [[ -z "$CONDA_SH" ]]; then
        conda_exe="$(command -v conda 2>/dev/null)"
        if [[ -n "$conda_exe" && "$conda_exe" == */* ]]; then
            # 例如 /opt/miniconda3/bin/conda -> base=/opt/miniconda3（若为函数名则无 /，跳过）
            base="$(dirname "$(dirname "$conda_exe")")"
            if [[ -f "${base}/etc/profile.d/conda.sh" ]]; then
                CONDA_SH="${base}/etc/profile.d/conda.sh"
            fi
        fi
    fi
    if [[ -z "$CONDA_SH" ]] && command -v conda &>/dev/null; then
        base="$(conda info --base 2>/dev/null)" && [[ -n "$base" && -f "${base}/etc/profile.d/conda.sh" ]] && CONDA_SH="${base}/etc/profile.d/conda.sh"
    fi
    if [[ -z "$CONDA_SH" ]]; then
        echo "错误：未找到 conda。若容器内 conda activate 可用，请设置 CONDA_ROOT=\$(conda info --base) 后重试" >&2
        exit 1
    fi
    source "$CONDA_SH"
fi

if $RUN_ONLY; then
    # 仅运行模式：未 --skip-conda 时才激活 py38；已 --skip-conda 则沿用当前环境
    if ! $SKIP_CONDA; then
        if ! conda activate py38 2>/dev/null; then
            echo "错误：无法激活 py38，请先在容器内执行一次: ./auto_run.sh --first-run" >&2
            exit 1
        fi
    fi
    if [[ -z "${CONDA_PREFIX:-}" ]]; then
        echo "错误：未检测到 conda 环境（CONDA_PREFIX 为空），请先激活 py38 或不要使用 --skip-conda" >&2
        exit 1
    fi
elif $FIRST_RUN; then
    echo "=== 首次执行：创建 py38 环境 ==="
    if conda env list | grep -q "py38"; then
        echo "警告：py38 环境已存在，跳过创建。"
    else
        conda create --name py38 --file "${SPEC_FILE}" -y
    fi

    echo "=== 激活 py38 环境（用于安装 ortools）==="
    conda activate py38
    echo "=== 使用 pip 安装 ortools（conda defaults 无此包）==="
    pip install ortools --quiet

    echo "=== 配置 conda（禁用 base 自动激活）==="
    conda config --set auto_activate_base false

    echo "=== 初始化 conda（确保激活正常）==="
    conda init bash  # 或 conda init（根据 shell）

    echo "=== 激活 py38 环境 ==="
    conda activate py38
    echo "=== 编译nemu ==="
    cd "${GEM5_HOME}/nemu"
    make riscv64-xs_defconfig
    make -j$(nproc)
else
    echo "=== 非首次执行：激活已有 py38 环境 ==="
    if ! conda env list | grep -q "py38"; then
        echo "错误：py38 环境不存在，请使用 --first-run 创建。"
        exit 1
    fi
    conda activate py38
fi
# 确保 gem5 运行时能找到 libpython3.8.so
export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${LD_LIBRARY_PATH:-}"

if ! $RUN_ONLY; then
    # 公共步骤：编译 gem5（必须在 GEM5_HOME 下执行）
    echo "=== 开始编译 gem5 (RISCV) ==="
    cd "${GEM5_HOME}"
    scons "${BUILD_TARGET}" --ignore-style --gold-linker -j$(nproc)
fi

# 公共步骤：运行（按模式选择 raw-cpt 或 单个 checkpoint .gz）
# 每个 workload 的 m5out 保存到 m5out_saved/<workload_name>/
M5OUT_SAVED="${M5OUT_SAVED:-${GEM5_HOME}/m5out_saved}"
cd "${GEM5_HOME}"
echo "=== 运行模式: ${RUN_MODE} ==="
if [[ ! -f "${GEM5_HOME}/${BUILD_TARGET}" ]]; then
    echo "错误：gem5 可执行文件未生成，请检查编译是否成功。"
    exit 1
fi

if [[ "$RUN_MODE" == "raw" ]]; then
    if [[ ! -f "$RAW_BINARY" ]]; then
        echo "错误：raw 裸机程序不存在：$RAW_BINARY"
        exit 1
    fi
    workload_name="$(basename "$RAW_BINARY" .bin)"
    outdir="${M5OUT_SAVED}/${workload_name}"
    mkdir -p "${M5OUT_SAVED}"
    echo "=== 运行 raw checkpoint: ${RAW_BINARY} (m5out 保存到 ${outdir}) ==="
    ./"${BUILD_TARGET}" -d "${outdir}" "${CONFIG_FILE}" --raw-cpt --generic-rv-cpt="${RAW_BINARY}"
else
    if [[ ! -f "$CPT_FILE" ]]; then
        echo "错误：checkpoint .gz 文件不存在：$CPT_FILE"
        exit 1
    fi
    # 使用相对 workloads 的路径作为目录名，/ 替换为 _
    rel="${CPT_FILE#"${GEM5_HOME}/workloads"}"
    rel="${rel#/}"
    workload_name="${rel//\//_}"
    workload_name="${workload_name%.gz}"
    [[ -z "$workload_name" ]] && workload_name="$(basename "$CPT_FILE" .gz)"
    outdir="${M5OUT_SAVED}/${workload_name}"
    mkdir -p "${M5OUT_SAVED}"
    echo "=== 运行 checkpoint .gz: ${CPT_FILE} (m5out 保存到 ${outdir}) ==="
    ./"${BUILD_TARGET}" -d "${outdir}" "${CONFIG_FILE}" --generic-rv-cpt="${CPT_FILE}"
fi

echo "=== 所有步骤完成 ==="