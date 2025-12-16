FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# 更换阿里云源
RUN sed -i 's@//archive.ubuntu.com/@//mirrors.aliyun.com/@g' /etc/apt/sources.list && \
    sed -i 's@//security.ubuntu.com/@//mirrors.aliyun.com/@g' /etc/apt/sources.list && \
    rm -f /etc/apt/sources.list.d/* && \
    echo "deb https://mirrors.aliyun.com/ubuntu/ jammy main restricted universe multiverse" > /etc/apt/sources.list.d/aliyun.list && \
    echo "deb https://mirrors.aliyun.com/ubuntu/ jammy-updates main restricted universe multiverse" >> /etc/apt/sources.list.d/aliyun.list && \
    echo "deb https://mirrors.aliyun.com/ubuntu/ jammy-security main restricted universe multiverse" >> /etc/apt/sources.list.d/aliyun.list && \
    echo "deb https://mirrors.aliyun.com/ubuntu/ jammy-backports main restricted universe multiverse" >> /etc/apt/sources.list.d/aliyun.list

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        build-essential \
        cmake \
        git \
        m4 \
        scons \
        zlib1g \
        zlib1g-dev \
        libprotobuf-dev \
        protobuf-compiler \
        libprotoc-dev \
        libgoogle-perftools-dev \
        python3-dev \
        libboost-all-dev \
        pkg-config \
        libsqlite3-dev \
        zstd \
        libzstd-dev \
        wget && \
    rm -rf /var/lib/apt/lists/*

# 安装 Miniconda
ENV MINICONDA_HOME=/opt/miniconda3
ENV PATH="${MINICONDA_HOME}/bin:${PATH}"
RUN set -eux; \
    update-ca-certificates; \
    MINICONDA_URL_PRIMARY="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"; \
    MINICONDA_URL_MIRROR="https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Linux-x86_64.sh"; \
    (wget -nv -S --https-only --tries=3 --timeout=30 "${MINICONDA_URL_PRIMARY}" -O /tmp/miniconda.sh || \
     wget -nv -S --https-only --tries=3 --timeout=30 "${MINICONDA_URL_MIRROR}" -O /tmp/miniconda.sh); \
    bash /tmp/miniconda.sh -b -u -p "${MINICONDA_HOME}"; \
    rm -f /tmp/miniconda.sh; \
    conda clean -afy



