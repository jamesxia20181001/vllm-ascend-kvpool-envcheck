"""假 torch 模块（纯 Docker stub，无 monkeypatch）。

让原版 artifacts/hccs_test_a3.py 在 x86 stub 容器内真实运行（import 不报错、
数据校验通过、输出 {"ok": true}）。仅实现该脚本用到的封闭接口面：
  full / cat / empty_like / equal / float32 / npu.set_device / npu.device_count
  / npu.synchronize / multiprocessing(spawn,get_context,SimpleQueue)
"""
float32 = "float32"


class Tensor:
    """轻量假 tensor：用 (value, count) 段列表记录内容，足够支持 equal 比较。"""
    __slots__ = ("segments",)

    def __init__(self, segments):
        self.segments = segments  # list[(float, int)]

    def __repr__(self):
        return f"FakeTensor({self.segments})"


_current_rank = 0


class _NPU:
    def set_device(self, rank):
        global _current_rank
        _current_rank = int(rank)

    def device_count(self):
        # 与脚本 --world-size 保持一致，使 main() 的可见性校验通过
        import sys
        argv = sys.argv
        for i, a in enumerate(argv):
            if a == "--world-size" and i + 1 < len(argv):
                try:
                    return int(argv[i + 1])
                except ValueError:
                    pass
        return 4

    def synchronize(self):
        pass


npu = _NPU()


def full(shape, val, dtype=None, device=None):
    n = shape[0] if isinstance(shape, (tuple, list)) else int(shape)
    return Tensor([(float(val), n)])


def cat(blocks):
    segs = []
    for b in blocks:
        segs.extend(b.segments)
    return Tensor(segs)


def empty_like(t):
    # 占位，all_to_all_single 会重写其 segments
    return Tensor(list(t.segments))


def equal(a, b):
    return a.segments == b.segments


from . import multiprocessing as multiprocessing  # noqa: E402,F401
