# kvpool_envcheck 纯 Docker 仿真容器（无 monkeypatch）。
# 在 x86_64 与 aarch64 上均可构建运行，模拟 A2/A3 软硬件环境（含内核版本）。
FROM python:3.12-slim

WORKDIR /workspace

# 仓库整体装入镜像（检查器 + rules + tests + artifacts + stub）
COPY . /workspace

# stub 运行时根：假 npu-smi / hccn_tool / uname 与档位数据
ENV STUB_DIR=/opt/kvpool-stub \
    STUB_PROFILE=a2 \
    WORKDIR=/workspace \
    PATH=/opt/kvpool-stub/bin:/usr/local/bin:/usr/bin:/bin

# 就位仿真证据：
# 1) 生成 A2/A3 档位数据文件（解析器格式，对齐 tests 固定桩；A3 含 mem_scan 内核接口伪造数据）
# 2) 安装假 npu-smi / hccn_tool / uname 与假 torch 模块（让原版 artifacts 脚本真实运行）
RUN python3 /workspace/stub/gen_profiles.py \
    && mkdir -p "${STUB_DIR}/bin" "${STUB_DIR}/profiles" \
    && cp -a /workspace/stub/profiles/. "${STUB_DIR}/profiles/" \
    && cp /workspace/stub/bin/npu-smi /workspace/stub/bin/hccn_tool /workspace/stub/bin/uname /workspace/stub/bin/getconf "${STUB_DIR}/bin/" \
    && chmod +x "${STUB_DIR}/bin/npu-smi" "${STUB_DIR}/bin/hccn_tool" "${STUB_DIR}/bin/uname" "${STUB_DIR}/bin/getconf" \
    && cp -a /workspace/stub/fake_modules "${STUB_DIR}/fake_modules" \
    && chmod +x /workspace/stub/entrypoint.sh

# entrypoint 就位 /proc bind-mount、davinci 设备、dist-info 等，再执行检查器
# 默认运行 A2 / memcache / 单节点 / RoCE 的完整检测
ENTRYPOINT ["/workspace/stub/entrypoint.sh"]
CMD ["python3", "kvpool_envcheck.py", \
     "--hardware", "A2", "--backend", "memcache", \
     "--managed-memory-mb", "32768", \
     "--deployment-mode", "single-node", "--link-type", "roce"]
