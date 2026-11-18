#!/bin/bash
# stub 容器入口：在执行检查器前就位全部仿真证据，纯文件系统/PATH，无 monkeypatch。
# 需要 --cap-add SYS_ADMIN（仅用于 bind-mount /proc 文件）。
set -eu

PROFILE="${STUB_PROFILE:-a2}"
STUB_DIR="${STUB_DIR:-/opt/kvpool-stub}"
PROFILE_DIR="$STUB_DIR/profiles/$PROFILE"
WORKDIR="${WORKDIR:-/workspace}"

err() { echo "stub entrypoint 错误: $*" >&2; exit 1; }
[ -d "$PROFILE_DIR" ] || err "档位目录不存在: $PROFILE_DIR（STUB_PROFILE=$PROFILE）"

# 1) /proc 文件 bind-mount（需 SYS_ADMIN）：/proc/meminfo、/proc/1/cgroup、/proc/sys/vm/drop_caches
mount_proc() {
    local target="$1" src="$2"
    cp -f "$src" /tmp/stub_"$(basename "$target")" 2>/dev/null || true
    mount --bind "/tmp/stub_"$(basename "$target")"" "$target" 2>/dev/null \
        || err "bind-mount $target 失败：请用 --cap-add SYS_ADMIN 运行容器"
}
mount_proc /proc/meminfo "$PROFILE_DIR/meminfo.txt"
# /proc/1/cgroup 标记 docker，确保 is_docker_runtime() 的 cgroup 回退命中
printf '0::/docker/0123456789abcdef\n' > /tmp/stub_cgroup
mount --bind /tmp/stub_cgroup /proc/1/cgroup 2>/dev/null \
    || err "bind-mount /proc/1/cgroup 失败：请用 --cap-add SYS_ADMIN 运行容器"
# --fix 会写 /proc/sys/vm/drop_caches；mount 一个可写副本，避免 Read-only fs 报错
cp -f "$PROFILE_DIR/drop_caches.txt" /tmp/stub_drop_caches 2>/dev/null || true
mount --bind /tmp/stub_drop_caches /proc/sys/vm/drop_caches 2>/dev/null || true

# 2) Docker 标识与 HCCN 入口
touch /.dockerenv
cp -f "$PROFILE_DIR/hccn.conf" /etc/hccn.conf

# 3) Ascend 驱动/CANN 目录与版本文件
mkdir -p /usr/local/Ascend/driver/tools /usr/local/Ascend/ascend-toolkit/latest
cp -f "$PROFILE_DIR/driver_version.info" /usr/local/Ascend/driver/version.info
cp -f "$PROFILE_DIR/ascend_toolkit_install.info" \
    /usr/local/Ascend/ascend-toolkit/latest/ascend_toolkit_install.info

# 4) /dev/davinci* 设备文件（DOCKER-001 计数）
while IFS= read -r dev; do
    [ -n "$dev" ] && touch "$dev" 2>/dev/null || true
done < "$PROFILE_DIR/davinci_devices.txt"

# 5) Python 包元数据：用 dist-info 让 importlib.metadata.version 命中
python3 - "$PROFILE_DIR/packages.json" <<'PY'
import json, sys, subprocess, sysconfig, os
pkgs = json.load(open(sys.argv[1]))
lib = sysconfig.get_paths()["purelib"]
for name, ver in pkgs.items():
    esc = name.replace("-", "_")
    d = os.path.join(lib, f"{esc}-{ver}.dist-info")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "METADATA"), "w").write(f"Metadata-Version: 2.1\nName: {esc}\nVersion: {ver}\n")
    open(os.path.join(d, "RECORD"), "w").write(f"{esc}.py\n")
PY

cd "$WORKDIR"

# 6) artifacts 脚本"提供依赖"机制（不修改 artifacts 源文件，原脚本真实运行）：
#    A3 场景：mem_scan.py 走 /proc/kpageflags + sysfs NUMA；hccs_test_a3.py 走假 torch
#    A2 不触发这两条路径（A2 用 /proc/meminfo 大页、无 HCCS 动态）
if [ "$PROFILE" = "a3" ] || [ "$PROFILE" = "a3-64k" ]; then IS_A3=1; else IS_A3=0; fi
if [ "$IS_A3" = "1" ] && [ -d "$WORKDIR/artifacts" ]; then
    MS_SYSFS="$PROFILE_DIR/memscan_sysfs"
    if [ -d "$MS_SYSFS" ]; then
        # bind-mount 伪造 sysfs NUMA 拓扑（覆盖视图，不写源文件）
        mount --bind "$MS_SYSFS/memory" /sys/devices/system/memory 2>/dev/null || true
        mount --bind "$MS_SYSFS/node"   /sys/devices/system/node   2>/dev/null || true
        # 运行时生成 /proc/kpageflags 伪造数据：按容器实际页大小计算 PFN/偏移，
        # 避免 aarch64 64K 主机页与 4K 假设错位导致 mem_scan 读到全 0。
        python3 "$WORKDIR/stub/gen_kpageflags.py" /tmp/stub_kpageflags             || err "生成 kpageflags 失败"
        mount --bind /tmp/stub_kpageflags /proc/kpageflags 2>/dev/null || true
    fi
    # 假 torch/torch_npu/torch.distributed：让原版 hccs_test_a3.py 真实运行
    if [ -d "$STUB_DIR/fake_modules" ]; then
        export PYTHONPATH="$STUB_DIR/fake_modules${PYTHONPATH:+:$PYTHONPATH}"
    fi
fi

exec "$@"