"""假 torch.distributed：init_process_group / all_to_all_single / 等。

all_to_all_single 用数学自洽构造 receive：rank r 的 receive 第 s 段应等于
来自 rank s 的 send 第 r 段 = iter*w*w + s*w + r。该值可从本 rank 的 send
内容（send 第 t 段 = iter*w*w + rank*w + t）反推 iter/w，再结合当前 rank 构造，
无需真实跨 rank 通信。
"""
import torch as _t

_initialized = False


def init_process_group(backend=None, rank=None, world_size=None, timeout=None):
    global _initialized
    _initialized = True


def all_to_all_single(output, input_tensor, **kwargs):
    segs = input_tensor.segments
    w = len(segs)                       # world_size
    epp = segs[0][1]                    # elements_per_peer
    rank = _t._current_rank
    val0 = segs[0][0]                   # = iter*w*w + rank*w + 0
    iter_ = (val0 - rank * w) / (w * w)  # 反推 iteration
    # receive 第 s 段 = iter*w*w + s*w + rank（与脚本内 expected 公式一致）
    output.segments = [(iter_ * w * w + s * w + rank, epp) for s in range(w)]


def is_initialized():
    return _initialized


def destroy_process_group():
    global _initialized
    _initialized = False
