docker run -it \
    -v ~/GEM5:/gem5 \
    --name gem5-dev \
    xsgem5-base:latest \
    /bin/bash -c "chmod +x /gem5/auto_run.sh && /gem5/auto_run.sh --first-run || echo '脚本执行失败，但仍进入终端调试' ; exec /bin/bash"