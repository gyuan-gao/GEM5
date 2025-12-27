#!/bin/bash
# 文件名：run_gem5.sh
# 用法：
#   chmod +x run_gem5.sh
#   ./run_gem5.sh          # 非首次（默认）：仅编译 + 运行裸机程序
#   ./run_gem5.sh --first-run   # 首次执行：完整流程（创建环境、配置、编译、运行）
export CONDA_PLUGINS_AUTO_ACCEPT_TOS=true
set -e  # 遇到错误立即退出

# 环境变量（可根据实际情况调整）
GEM5_HOME="/gem5"
export NEMU_HOME="/gem5/nemu"
SPEC_FILE="${GEM5_HOME}/ext/xs_env/gem5-py38.txt"
CONFIG_FILE="${GEM5_HOME}/configs/example/kmhv3.py"
BINARY="${GEM5_HOME}/ready-to-run/coremark-2-iteration.bin"
BUILD_TARGET="build/RISCV/gem5.opt"

# 解析参数
FIRST_RUN=false
if [[ "$1" == "--first-run" ]]; then
    FIRST_RUN=true
elif [[ -n "$1" && "$1" != "--help" ]]; then
    echo "用法: $0 [--first-run]"
    echo "  默认（无参数）：仅编译并运行裸机程序（适用于非首次）"
    echo "  --first-run    ：完整首次流程（创建环境、配置、编译、运行）"
    exit 1
fi

# 启用 conda（Docker 中常见方式）
source /opt/miniconda3/etc/profile.d/conda.sh

if $FIRST_RUN; then
    echo "=== 首次执行：创建 py38 环境 ==="
    if conda env list | grep -q "py38"; then
        echo "警告：py38 环境已存在，跳过创建。"
    else
        conda create --name py38 --file "${SPEC_FILE}" -y
    fi

    echo "=== 配置 conda（禁用 base 自动激活）==="
    conda config --set auto_activate_base false

    echo "=== 初始化 conda（确保激活正常）==="
    conda init bash  # 或 conda init（根据 shell）

    echo "=== 激活 py38 环境 ==="
    conda activate py38
    echo "=== 编译nemu ==="
    cd /gem5/nemu
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

# 公共步骤：编译 gem5
echo "=== 开始编译 gem5 (RISCV) ==="
cd /gem5
scons "${BUILD_TARGET}" --ignore-style --gold-linker -j$(nproc)

# 公共步骤：运行裸机程序
echo "=== 运行裸机程序 (coremark) ==="
if [[ ! -f "${GEM5_HOME}/${BUILD_TARGET}" ]]; then
    echo "错误：gem5 可执行文件未生成，请检查编译是否成功。"
    exit 1
fi
if [[ ! -f "$BINARY" ]]; then
    echo "错误：裸机程序文件不存在：$BINARY"
    exit 1
fi

./"${BUILD_TARGET}" "${CONFIG_FILE}" --raw-cpt --generic-rv-cpt="${BINARY}"



echo "=== 所有步骤完成 ==="