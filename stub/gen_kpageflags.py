"""运行时生成 /proc/kpageflags 伪造数据（容器启动时调用）。

按容器实际 os.sysconf("SC_PAGE_SIZE") 计算 target range 起点 PFN 与写入偏移，
避免 aarch64 64K 主机页与构建时 4K 假设错位导致 mem_scan.py 读到全 0。

写入路径由 argv[1] 指定（默认 /tmp/stub_kpageflags），供 entrypoint bind-mount
到 /proc/kpageflags。target range 区段（32GB）全部填 KPF_BUDDY flag。
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

MEMSCAN_TARGET_ADDR = 0x29580000000   # mem_scan.py RANGES[0]
MEMSCAN_BLOCK_SIZE = 0x80000000       # 2GB
MEMSCAN_BLOCKS = 16                   # 16 × 2GB = 32GB free

KPF_BUDDY = 10


def main() -> None:
    page_size = os.sysconf("SC_PAGE_SIZE")
    target_pfn = MEMSCAN_TARGET_ADDR // page_size
    pages = MEMSCAN_BLOCKS * (MEMSCAN_BLOCK_SIZE // page_size)
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/stub_kpageflags")
    flag = struct.pack("<Q", 1 << KPF_BUDDY)
    with open(out, "wb") as f:
        f.seek(target_pfn * 8)
        f.write(flag * pages)
    print(
        f"kpageflags: page_size={hex(page_size)} target_pfn={target_pfn} "
        f"blocks={MEMSCAN_BLOCKS} pages={pages} -> {out}"
    )


if __name__ == "__main__":
    main()
