"""假 torch.multiprocessing：在主进程顺序模拟各 rank，避开真实多进程协调。

原脚本用 mp.spawn(worker, nprocs=w) 启动 w 个 rank。假实现顺序调 worker(rank=i)，
每个 worker 自洽完成（假 all_to_all_single 基于 send 内容 + 当前 rank 数学构造
receive），无需真实跨进程数据交换。SimpleQueue 用内存 queue.Queue。
"""
import queue as _queue


class _SimpleQueue:
    def __init__(self):
        self._q = _queue.Queue()

    def put(self, item):
        self._q.put(item)

    def get(self):
        return self._q.get()


class _Ctx:
    def SimpleQueue(self):
        return _SimpleQueue()


_default = _Ctx()


def get_context(method="spawn"):
    return _default


def spawn(fn, args=(), nprocs=1, join=True):
    # mp.spawn 协议：fn(i, *args) for i in range(nprocs)
    for rank in range(nprocs):
        fn(rank, *args)
