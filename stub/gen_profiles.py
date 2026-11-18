"""生成 A2 / A3 仿真档位的模拟数据文件（纯 Docker stub，无 monkeypatch）。

输出到 stub/profiles/<a2|a3>/ 下，供镜像内的假 npu-smi / hccn_tool / uname
和 entrypoint 的 /proc/meminfo bind-mount 在运行时读取。

格式严格对齐 kvpool_envcheck.py 的解析器：
- parse_npu_topology / parse_npu_processes  -> npu_smi_info.txt
- parse_hccs_state / parse_hccs_topology    -> npu_smi_hccs_<npu>_<chip>.txt, npu_smi_topo_<npu>_<chip>.txt
- probe_roce_npu_state                      -> hccn_tool_<npu>_<field>.txt
- read_proc_meminfo                         -> meminfo.txt
- HDK: driver version.info + npu-smi Driver Version
- CANN: ascend_toolkit_install.info
- kernel: uname -r
- importlib.metadata: dist-info METADATA
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent

# A2: 910B4 ×2，单 die，2MB 静态大页，4.19 内核
A2_NPUS = [
    {"id": 0, "name": "910B4-1", "health": "OK", "power": "100.0", "temp": "42"},
    {"id": 1, "name": "910B4-1", "health": "OK", "power": "92.1", "temp": "41"},
]
A2_ROCE = [
    {"id": 0, "ip": "10.30.126.22", "netmask": "255.255.0.0"},
    {"id": 1, "ip": "10.30.126.23", "netmask": "255.255.0.0"},
]

# A3: Ascend910 ×2，每卡 2 die，4 die 全可见，HCCS 静态就绪
A3_NPUS = [
    {"id": 0, "name": "Ascend910", "health": "OK", "power": "350.0", "temp": "45"},
    {"id": 1, "name": "Ascend910", "health": "OK", "power": "348.2", "temp": "44"},
]
A3_ROCE = [
    {"id": 0, "ip": "10.30.126.30", "netmask": "255.255.0.0"},
    {"id": 1, "ip": "10.30.126.31", "netmask": "255.255.0.0"},
]

ROCE_MTU = 8192

# target range 0x29580000000（mem_scan.py RANGES[0]）；block idx = addr // block_size，页大小无关
MEMSCAN_TARGET_ADDR = 0x29580000000
MEMSCAN_BLOCK_SIZE = 0x80000000  # 2GB 内存块
MEMSCAN_BLOCKS = 16              # 16 × 2GB = 32GB free，满足 32768MB 纳管


def gen_memscan_sysfs(profile_dir: Path) -> None:
    """生成 mem_scan.py 依赖的伪造 sysfs NUMA 拓扑（A3 用，页大小无关）。

    产出 memscan_sysfs/：
    - memory/block_size_bytes（2GB）
    - node/node0/memory{idx} 空文件，idx = target_addr // block_size（与页大小无关）

    kpageflags.bin 不在此生成：其 PFN/偏移依赖运行时页大小，改由
    stub/gen_kpageflags.py 在容器启动时按实际 os.sysconf("SC_PAGE_SIZE") 生成，
    避免 aarch64 64K 主机页与 4K 假设错位导致 mem_scan 读到全 0。
    """
    p = profile_dir
    sysfs = p / "memscan_sysfs"
    (sysfs / "node" / "node0").mkdir(parents=True, exist_ok=True)
    (sysfs / "memory").mkdir(parents=True, exist_ok=True)
    (sysfs / "memory" / "block_size_bytes").write_text(f"{MEMSCAN_BLOCK_SIZE:x}\n", encoding="ascii")
    block_base_idx = MEMSCAN_TARGET_ADDR // MEMSCAN_BLOCK_SIZE
    for i in range(MEMSCAN_BLOCKS):
        (sysfs / "node" / "node0" / f"memory{block_base_idx + i}").write_text("", encoding="ascii")


def npu_smi_info(npus, chips_per_npu: int) -> str:
    """生成 `npu-smi info` 输出，对齐 parse_npu_topology。

    格式取自 tests/test_kvpool_envcheck.py 的 A2/A3 固定桩：
    - 设备表行 `| <npu_id> <name> |` 设定 NPU 与名称
    - die 行 `| <chip_id> <phy_id> | <bus> | ...` 追加到上一个 NPU
    """
    lines = ["+--------------------------------------------------------------------------------+"]
    lines.append("| NPU   Name                | Health        | Power(W)    Temp(C) |")
    lines.append("+--------------------------------------------------------------------------------+")
    bus = 0
    # 多 die：每个 die 行前重复 NPU 名称行以设定 parse_npu_topology 的 current
    # 格式取自 tests/test_kvpool_envcheck.py 的 A3 固定桩（名称行/die 行交替写法）
    for n in npus:
        lines.append(f"| {n['id']:<5} {n['name']:<20} | {n['health']:<13} | {n['power']:<11} {n['temp']:<7}|")
        if chips_per_npu > 1:
            for chip in range(chips_per_npu):
                if chip > 0:
                    lines.append(f"| {n['id']:<5} {n['name']:<20} | {n['health']:<13} | {n['power']:<11} {n['temp']:<7}|")
                phy = n["id"] * chips_per_npu + chip + 8
                lines.append(f"| {chip:<5} {phy:<20} | 0000:{8 + bus:02X}:00.0  | 0           0 |")
                bus += 1
    lines.append("+--------------------------------------------------------------------------------+")
    lines.append("| NPU     Chip              | Process id    | Process name                   |")
    lines.append("+--------------------------------------------------------------------------------+")
    return "\n".join(lines) + "\n"


def npu_smi_hccs(npu_id: int, chip_id: int) -> str:
    """生成 `npu-smi info -t hccs -i <n> -c <c>` 输出，对齐 parse_hccs_state。

    格式取自 tests/test_kvpool_envcheck.py 固定桩：2 链路全就绪。
    """
    return (
        f"hccs health status : OK\n"
        f"hccs lane mode : [4 4]\n"
        f"hccs link lane list : [1111 1111]\n"
        f"hccs link speed : [224 224]\n"
        f"hccs retry count : [0 0]\n"
        f"hccs error count : [0 0]\n"
        f"hccs first error lane : NA\n"
    )


def npu_smi_topo(npu_id: int, chip_id: int, phy_ids: list) -> str:
    """生成 `npu-smi info -t topo -i <n> -c <c>` 输出，对齐 parse_hccs_topology。

    格式取自 tests/test_kvpool_envcheck.py 固定桩：同卡 die 间 SIO，
    跨卡 die 间 HCCS_SW。phy_ids 必须是全部可见 die 的物理 ID
    （与 npu_smi_info 里的 Phy-ID 一致，如 [8,9,10,11]）。
    """
    header = "  " + " ".join(f"Phy-ID{p:<6}" for p in phy_ids)
    lines = [header]
    # 同卡判定：物理 ID 整除 2 相同视为同卡（每卡 2 die，连续编号）
    for src in phy_ids:
        cells = []
        for dst in phy_ids:
            if src == dst:
                cells.append("X      ")
            elif src // 2 == dst // 2:  # 同卡
                cells.append("SIO    ")
            else:
                cells.append("HCCS_SW")
        lines.append(f"Phy-ID{src:<6}" + " ".join(cells) + "  ")
    return "\n".join(lines) + "\n"


def hccn_tool_ip(n) -> str:
    return f"ip : {n['ip']}\nnetmask : {n['netmask']}\n"


def hccn_tool_link() -> str:
    return "link status : UP\n"


def hccn_tool_health() -> str:
    return "net health status : Success\n"


def hccn_tool_mtu() -> str:
    return f"mtu : {ROCE_MTU}\n"


def hccn_tool_stat() -> str:
    return (
        "mac_rx_fcs_err_pkt_num : 0\n"
        "roce_rx_err_pkt_num : 0\n"
        "roce_tx_err_pkt_num : 0\n"
        "roce_verification_err_num : 0\n"
        "roce_qp_status_err_num : 0\n"
    )


def hccn_tool_ping() -> str:
    return "3 packets transmitted, 3 received, 0.00% packet loss\n"


def write_profile(profile_dir: Path, npus, roce, chips_per_npu: int, kernel: str,
                  packages: dict) -> None:
    p = profile_dir
    p.mkdir(parents=True, exist_ok=True)
    total_dies = len(npus) * chips_per_npu
    (p / "npu_smi_info.txt").write_text(npu_smi_info(npus, chips_per_npu), encoding="utf-8")
    (p / "meminfo.txt").write_text(
        "MemTotal:       268435456 kB\n"
        "HugePages_Total:    32768\n"
        "HugePages_Free:     32768\n"
        "HugePages_Rsvd:        0\n"
        "Hugepagesize:       2048 kB\n",
        encoding="ascii",
    )
    (p / "uname_r.txt").write_text(kernel + "\n", encoding="utf-8")
    (p / "driver_version.info").write_text(
        "HDK Version : 25.5.0\nDriver Version : 25.5.0\n", encoding="utf-8")
    (p / "board_info.txt").write_text(
        "HDK Version : 25.5.0\nDriver Version : 25.5.0\n", encoding="utf-8")
    (p / "ascend_toolkit_install.info").write_text(
        "CANN Toolkit version : 9.1.0\n", encoding="utf-8")
    (p / "hccn.conf").write_text("hccn_mode=0\n", encoding="utf-8")
    (p / "drop_caches.txt").write_text("3\n", encoding="ascii")
    (p / "packages.json").write_text(
        __import__("json").dumps(packages, ensure_ascii=False), encoding="utf-8")
    # HCCS（A3 用；A2 无 HCCS 也不影响——A2 不查 hccs）
    # 物理 ID 与 npu_smi_info 的 die 行一致：每卡 2 die，连续编号自 8 起
    phy_ids = [n["id"] * chips_per_npu + c + 8 for n in npus for c in range(chips_per_npu)]
    for n in npus:
        for c in range(chips_per_npu):
            (p / f"npu_smi_hccs_{n['id']}_{c}.txt").write_text(
                npu_smi_hccs(n["id"], c), encoding="utf-8")
            (p / f"npu_smi_topo_{n['id']}_{c}.txt").write_text(
                npu_smi_topo(n["id"], c, phy_ids), encoding="utf-8")
    # ROCE
    for n in roce:
        (p / f"hccn_tool_{n['id']}_ip.txt").write_text(hccn_tool_ip(n), encoding="utf-8")
        (p / f"hccn_tool_{n['id']}_link.txt").write_text(hccn_tool_link(), encoding="utf-8")
        (p / f"hccn_tool_{n['id']}_net_health.txt").write_text(hccn_tool_health(), encoding="utf-8")
        (p / f"hccn_tool_{n['id']}_mtu.txt").write_text(hccn_tool_mtu(), encoding="utf-8")
        (p / f"hccn_tool_{n['id']}_stat.txt").write_text(hccn_tool_stat(), encoding="utf-8")
        (p / f"hccn_tool_{n['id']}_ping.txt").write_text(hccn_tool_ping(), encoding="utf-8")
    # davinci 设备名清单（entrypoint 据此 mknod）
    dev_names = [f"/dev/davinci{n['id']}" for n in npus]
    (p / "davinci_devices.txt").write_text("\n".join(dev_names) + "\n", encoding="utf-8")


def main() -> None:
    a2_pkgs = {"memfabric-hybrid": "1.0.0", "memcache-hybrid": "1.0.0"}
    a3_pkgs = {"memfabric-hybrid": "1.0.0", "memcache-hybrid": "1.0.0"}
    write_profile(ROOT / "profiles" / "a2", A2_NPUS, A2_ROCE, 1,
                  "4.19.90-2112.6.0.20.ky10.aarch64", a2_pkgs)
    write_profile(ROOT / "profiles" / "a3", A3_NPUS, A3_ROCE, 2,
                  "6.6.0-77.0.0.35.an23.aarch64", a3_pkgs)
    # A3 走 mem_scan.py 路径，需伪造其依赖的 sysfs NUMA 拓扑（页大小无关）。
    # /proc/kpageflags 由 stub/gen_kpageflags.py 在容器运行时按实际页大小生成。
    gen_memscan_sysfs(ROOT / "profiles" / "a3")
    print("generated profiles under", ROOT / "profiles")


if __name__ == "__main__":
    main()
