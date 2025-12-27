#!/bin/bash

# 使用说明：
# ./run.sh          # 默认执行 auto_run.sh（带 --first-run）
# ./run.sh --run    # 同上，显式指定运行模式
# ./run.sh --build  # 执行构建脚本（请根据实际情况修改下面的 BUILD_CMD）

# 定义构建命令（请根据您的实际 build 脚本修改此行）
# 示例1：如果您有 /gem5/build.sh
BUILD_CMD="chmod +x /gem5/build.sh && /gem5/build.sh"
# 示例2：如果直接使用 scons 构建
# BUILD_CMD="cd /gem5 && scons build/ARM/gem5.opt -j$(nproc)"

# 定义默认运行命令
RUN_CMD="chmod +x /gem5/auto_run.sh && /gem5/auto_run.sh --first-run"

# 解析参数
MODE="run"  # 默认模式
if [ "$1" = "--build" ]; then
    MODE="build"
elif [ "$1" = "--run" ]; then
    MODE="run"
elif [ -n "$1" ]; then
    echo "未知参数: $1"
    echo "用法: $0 [--build | --run]"
    exit 1
fi

# 判断容器是否已存在
if docker ps -a --format '{{.Names}}' | grep -q "^gem5-dev$"; then
    echo "检测到已存在容器 gem5-dev，正在启动并进入..."
    docker start gem5-dev > /dev/null
    EXEC_CMD="docker exec -it gem5-dev /bin/bash"
else
    echo "首次运行，创建新容器 gem5-dev..."
    EXEC_CMD="docker run -it --name gem5-dev"
fi

# 公共的挂载和镜像部分
COMMON_OPTS="-v ~/GEM5:/gem5 xsgem5-env:latest"

# 根据模式构造要执行的命令
if [ "$MODE" = "build" ]; then
    echo "=== 执行构建模式 ==="
    COMMAND="${BUILD_CMD} || echo '构建脚本执行失败，但仍进入终端调试'; exec /bin/bash"
else
    echo "=== 执行运行模式 ==="
    COMMAND="${RUN_CMD} || echo 'auto_run.sh 执行失败，但仍进入终端调试'; exec /bin/bash"
fi

# 完整执行命令
FULL_CMD="${EXEC_CMD} ${COMMON_OPTS} /bin/bash -c \"${COMMAND}\""

# 执行
eval $FULL_CMD