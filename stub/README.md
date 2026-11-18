# stub — kvpool_envcheck 纯 Docker 仿真环境

在不修改 `kvpool_envcheck.py` / `rules.json` / `tests/` / `artifacts/` 的前提下，
让原本只能在 Atlas A2/A3 ARM 容器内运行的环境检测工具，在普通 **x86_64 或 aarch64**
主机上完整验证运行。**不使用 monkeypatch**，全部通过文件系统、PATH 与伪造依赖实现。

## 原理

检查器对外部环境的依赖收敛在少数入口，stub 用纯 Docker 手段就地满足它们：

| 检查器入口 | stub 实现手段 | 无 monkeypatch |
|---|---|---|
| `subprocess.run(["npu-smi",...])` | PATH 前置假 `npu-smi` 脚本，读档位数据 | ✓ |
| `subprocess.run(["hccn_tool",...])` | PATH 前置假 `hccn_tool` 脚本 | ✓ |
| `subprocess.run(["uname","-r"])` | PATH 前置假 `uname` 脚本 | ✓ |
| `subprocess.run([sys.executable, "mem_scan.py", ...])` | **提供伪造内核接口依赖**：bind-mount `/proc/kpageflags` + sysfs NUMA，原版 mem_scan.py 真实运行 | ✓ |
| `subprocess.Popen([sys.executable, "hccs_test_a3.py", ...])` | **提供伪造模块依赖**：`PYTHONPATH` 前置假 `torch`/`torch_npu`/`torch.distributed`，原版 hccs_test_a3.py 真实运行 | ✓ |
| `shutil.which("npu-smi"/"hccn_tool")` | 假脚本在 PATH 上，which 命中 | ✓ |
| `importlib.metadata.version("memcache-hybrid")` | 安装真实 dist-info（METADATA） | ✓ |
| `Path("/proc/meminfo").read_text()` | **bind-mount** 覆盖（需 SYS_ADMIN） | ✓ |
| `Path("/.dockerenv").exists()` | entrypoint `touch /.dockerenv` | ✓ |
| `Path("/dev").glob("davinci*")` | entrypoint `touch /dev/davinci*` | ✓ |
| `Path("/usr/local/Ascend/...")` | entrypoint 创建目录与版本文件 | ✓ |
| `Path("/etc/hccn.conf").is_file()` | entrypoint 拷入 hccn.conf | ✓ |
| `platform.release()` 回退 | 假 `uname -r` 已覆盖主路径 | ✓ |

### artifacts 脚本：提供依赖而非替换

两个 artifacts 脚本（`mem_scan.py` / `hccs_test_a3.py`）**源文件保持不变**（sha256 与
`manifest.json` 一致），通过提供其运行依赖让原脚本真实运行：

- **mem_scan.py**：依赖 `/proc/kpageflags` + `/sys/devices/system/node/*` 等内核接口。
  sysfs NUMA 拓扑在 A3 档位由 `gen_profiles.py` 生成（页大小无关）；`/proc/kpageflags` 由
  `stub/gen_kpageflags.py` 在容器启动时按实际 `os.sysconf("SC_PAGE_SIZE")` 生成（target range
  区段全 buddy free），bind-mount 覆盖，原脚本读取后真实计算并输出 `Total free: 32GB`。
- **hccs_test_a3.py**：依赖 `torch`/`torch_npu`/`torch.distributed`（Ascend 专用，无 x86
  发行版）。stub 提供假模块（仅实现该脚本用到的封闭接口面），`all_to_all_single` 用
  数学自洽构造正确 receive（all-to-all 数据具有确定性公式），原脚本真实执行其逻辑并
  输出 `{"ok": true}`。

档位数据（A2/A3 的 npu-smi/hccn_tool/拓扑/版本输出 + mem_scan sysfs 拓扑）由
`gen_profiles.py` 生成，格式严格对齐 `tests/test_kvpool_envcheck.py` 的固定桩。
`/proc/kpageflags` 伪造数据由 `stub/gen_kpageflags.py` 在容器启动时生成（依赖运行时页大小）。

## 档位

### A2（缺省）
Atlas A2（910B4 ×2，单 die）+ 麒麟 V10 + **4.19 内核** + 64K 基页 + 2MB 静态大页。
覆盖全部 A2 适用规则：MEM/CANN/HDK/ROCE×2/DOCKER/DEP-MEMCACHE×2，**8 条全 PASS**。

### A3
Atlas A3（Ascend910 ×2，每卡 2 die）+ openEuler + **6.6 内核**。
覆盖 A3 适用规则：MEM/CANN/HDK/KERNEL/HCCS×2/DOCKER/DEP-MEMCACHE×2。
- **单节点 hccs**：8 条全 PASS（KERNEL/LINGQU 不适用）。
- **多节点 hccs**：9 PASS + 1 MANUAL_REQUIRED（LINGQU-001 需人工确认 1520 交换机版本，
  属设计预期，无法自动检测）。

> A3 动态规则（HCCS-002 HCCL all_to_all、ROCE-002 hccn_tool ping）在 stub 内由原版
> artifacts 脚本 + 伪造依赖真实执行，使规则 PASS；但底层 tensor/通信是假实现，
> **不代表真实验证了数据通路**，真实环境需 torch_npu/HCCL 与 Ascend 硬件。

## 构建

```bash
docker build -t kvpool-envcheck-stub -f stub/Dockerfile .
```

镜像基于 `python:3.12-slim`（同时支持 x86_64 与 aarch64），构建时生成 A2/A3 档位数据
（含 mem_scan sysfs 拓扑）、安装假命令到 `/opt/kvpool-stub/bin`（PATH 前置）、
假 torch 模块到 `/opt/kvpool-stub/fake_modules`。`/proc/kpageflags` 在容器启动时按实际
页大小生成，确保 4K/64K 主机页均正确对齐。

## 运行

```bash
# A2 缺省场景（单节点 RoCE）— 8 条全 PASS
docker run --rm \
    --cap-add SYS_ADMIN --security-opt apparmor=unconfined \
    kvpool-envcheck-stub

# A3 单节点 HCCS — 8 条全 PASS
docker run --rm \
    --cap-add SYS_ADMIN --security-opt apparmor=unconfined \
    -e STUB_PROFILE=a3 \
    kvpool-envcheck-stub \
    python3 kvpool_envcheck.py --hardware A3 --backend memcache \
      --managed-memory-mb 32768 --deployment-mode single-node --link-type hccs

# A3 多节点 HCCS — 9 PASS + 1 MANUAL_REQUIRED（LINGQU-001 设计预期）
docker run --rm \
    --cap-add SYS_ADMIN --security-opt apparmor=unconfined \
    -e STUB_PROFILE=a3 \
    kvpool-envcheck-stub \
    python3 kvpool_envcheck.py --hardware A3 --backend memcache \
      --managed-memory-mb 32768 --deployment-mode multi-node --link-type hccs

# 落盘结果到主机（--output-dir + 卷挂载）
mkdir -p results
docker run --rm \
    --cap-add SYS_ADMIN --security-opt apparmor=unconfined \
    -e STUB_PROFILE=a3 \
    -v "$PWD/results:/workspace/results" \
    kvpool-envcheck-stub \
    python3 kvpool_envcheck.py --hardware A3 --backend memcache \
      --managed-memory-mb 32768 --deployment-mode single-node --link-type hccs \
      --output-dir /workspace/results
ls results/   # 各一个 .result.json + .report.txt
```

### 权限说明

`--cap-add SYS_ADMIN` 仅为 bind-mount `/proc/meminfo`、`/proc/kpageflags`、`/sys` 所需；
`--security-opt apparmor=unconfined` 在 AppArmor 限制 bind-mount 的发行版上需要。
二者均不影响检查器逻辑本身。

## 自动化 smoke 测试

`stub/smoke_test.sh` 把上述"验证结果"固化为机器断言：构建镜像（若缺失）、按三个场景
运行检查器、用 `stub/assert_result.py` 断言每份 `.result.json` 的 pass/manual/exit 计数，
任一偏离即失败。

```bash
bash stub/smoke_test.sh          # 构建并跑全部场景
IMAGE=myimg bash stub/smoke_test.sh   # 用指定镜像名
```

前置：本机 docker 可用（stub 需 `--cap-add SYS_ADMIN`）。脚本在镜像缺失时自动构建，
每个场景用独立临时目录隔离输出。

## 切换/新增档位

`STUB_PROFILE` 环境变量选档位（缺省 `a2`）。新增档位：仿照 `gen_profiles.py` 中
A2/A3 的数据结构，在 `main()` 里调用 `write_profile()` 生成新档位目录，
然后用 `-e STUB_PROFILE=<name>` 运行。

## 文件

- `stub/Dockerfile` — 仿真容器（python:3.12-slim，多架构）
- `stub/entrypoint.sh` — 容器入口：bind-mount /proc 与 sysfs、就位 davinci/版本/包元数据、A3 设 PYTHONPATH
- `stub/gen_profiles.py` — 生成 A2/A3 档位数据 + A3 mem_scan sysfs 拓扑（`stub/profiles/`，构建产物，不入库）
- `stub/gen_kpageflags.py` — 容器启动时按实际页大小生成 `/proc/kpageflags` 伪造数据（修复 aarch64 64K 页）
- `stub/bin/npu-smi` — 假 npu-smi（读档位数据）
- `stub/bin/hccn_tool` — 假 hccn_tool
- `stub/bin/uname` — 假 uname（仅拦截 -r）
- `stub/fake_modules/torch/` — 假 torch（含 distributed/multiprocessing，让原版 hccs_test_a3.py 真实运行）
- `stub/fake_modules/torch_npu/` — 假 torch_npu（空模块，仅满足 import）
- `stub/smoke_test.sh` — 端到端 smoke：构建镜像并断言三场景的 PASS/MANUAL 计数
- `stub/assert_result.py` — 断言单份 `.result.json` 的 pass/manual/exit 计数（smoke_test 调用，也可独立使用）

## 验证结果

- A2 单节点/多节点 RoCE：`PASS`，退出码 `0`，8 条全 PASS。
- A3 单节点 HCCS：`PASS`，退出码 `0`，8 条全 PASS。
- A3 多节点 HCCS：9 PASS + 1 MANUAL_REQUIRED（LINGQU-001 设计预期），退出码 `20`。
- artifacts 源文件 sha256 与 `manifest.json` 一致（`mem_scan.py`=`7eeffc19...`，
  `hccs_test_a3.py`=`9c2f067a...`），原脚本未被修改、真实运行。
- 镜像内 `python3 -m unittest tests.test_kvpool_envcheck`：49 项全通过
  （entrypoint 仅在执行检查器前生效，单测不受影响）。
