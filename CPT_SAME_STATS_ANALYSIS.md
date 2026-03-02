# 不同 checkpoint 得到相同 stats 的原因分析

## 1. 已确认的事实

- **传参正确**：日志里 `[DEBUG] CPT_FILE=...` 和 gem5 命令行里的 `--generic-rv-cpt=...` 对 0、106、113 分别是不同路径，且 `Unserializing physical memory from file ...` 也指向对应文件。
- **加载的是不同文件**：0 用 `.../0/_0_0.003745_memory_.gz`，106 用 `.../106/_106_0.007491_memory_.gz`，113 用 `.../113/_113_0.067416_memory_.gz`。
- **仿真流程一致**：
  - 日志有 "Entering event queue @ **8612558154**. Starting simulation..." → GCPT 恢复后 **curTick 都是 8612558154**（与哪个 cpt 无关）。
  - 接着 "Will trigger stat dump and reset" → 跑满 **warmup_insts_no_switch = 20M** 条后做一次 stat dump/reset。
  - 最后 "Exiting @ tick ... because **a thread reached the max instruction count**" → 再跑到 **maxinsts = 40M** 退出。
- **最终 stats 的含义**：是 **reset 之后** 的那一段（从 20M 到 40M，即再跑约 20M 条）的统计，所以 `simInsts ≈ 20000003`、`simTicks ≈ 8.6e9` 对所有 cpt 都相同。

## 2. 为何“结果一模一样”

可能原因只有两类：

### A. 多个 .gz 文件内容相同（或等效）

- 若 0、106、113 的 .gz 实际是同一份数据（或只改名、内容一致），则恢复出的内存/状态相同，之后执行的 20M 条完全一样 → stats 必然相同。
- **验证**：在宿主机或容器内对几个 cpt 做哈希比较，例如：
  ```bash
  cd /home/gaoguangyuan/GEM5/workloads/500.perlbench_r_10G
  md5sum 0/*.gz 106/*.gz 113/*.gz
  # 若三个 md5 相同，说明是同一份文件
  ```

### B. GCPT 恢复逻辑导致“等效同一起点”

- 若 GCPT 格式里 **curTick / 已执行指令数** 没有按 cpt 区分（或恢复时被忽略/写死），则所有 cpt 恢复后都从 **同一 curTick**（如 8612558154）开始。
- 若 **CPU 状态（PC、寄存器等）** 不是从各自 .gz 里恢复，而是来自 restorer/固定地址，则不同 .gz 只带来不同内存，但“从同一条指令开始跑 20M 条” → 若 restorer 或入口一致，行为仍可能相同或高度相似。
- 需要查：GCPT 反序列化（如 `physical.cc`、xiangshan 相关 restore）里是否用到了 **每个 cpt 自己的** tick/指令数/CPU 状态；若没有，就是设计上“所有 slice 同一起点”，stats 相同就可以解释。

## 3. 建议的下一步

1. **先做文件一致性检查**（上面 md5sum）。若 md5 不同，再查恢复逻辑。
2. **若 md5 不同**：在 gem5/xiangshan 里查 GCPT 恢复路径，确认：
   - curTick 从哪里来（每个 cpt 是否带自己的 tick？）；
   - CPU/线程状态（PC、已执行指令数等）是否从当前 .gz 恢复。
3. **若希望“不同 cpt 跑不同长度”**：需要配置或代码支持“按 cpt 的已执行指令数/目标指令数”设置不同的 `maxinsts` 或仿真区间，而不是统一 40M + 20M warmup。

## 4. 脚本与配置侧（当前无误）

- `run_cpts.sh` 通过 `GEM5_CPT_PATH` 传入的路径正确，日志中已确认。
- `auto_run.sh` 解析 `--cpt` 并传给 gem5 的 `--generic-rv-cpt` 正确。
- 问题不在“传错 cpt 路径”，而在 **GCPT 恢复后 curTick/已执行指令数是否随 cpt 区分**。

## 5. 验证结果：三个 .gz 文件内容不同

```bash
0:   f064c6ceba144881c10a44ce20910ee3  0/_0_0.003745_memory_.gz
106: bef58af5638a7384029464e3821cb600  106/_106_0.007491_memory_.gz
113: 6f4ab272b3e1e123bcc88da6038fe665  113/_113_0.067416_memory_.gz
```

**结论**：不是“同一份 cpt 复制多份”，而是 **GCPT 恢复逻辑** 没有按 cpt 区分“起始 curTick / 已执行指令数”，导致恢复后仿真的逻辑起点相同（都是 8612558154 + 20M warmup 后的统计），所以 stats 一致。需要在 gem5/xiangshan 的 GCPT 反序列化或 workload 初始化里，让 curTick 和 CPU 的“已执行指令数”从**当前 .gz 的元数据**恢复，而不是固定值。
