"""Cancel token 协议：让长任务可以协作式取消。

- `CancelToken` 是 Protocol
- `ThreadEventToken` 是线程默认实现
- `NullCancelToken` 是 CLI / 测试用的无操作实现
"""
from __future__ import annotations

import threading
from typing import Protocol


class GenrePipelineAborted(Exception):
    """Cancel token 触发 check() 时抛出，worker 捕获后把 state → aborted."""


class CancelToken(Protocol):
    def check(self) -> None: ...
    def is_cancelled(self) -> bool: ...


class ThreadEventToken:
    def __init__(self) -> None:
        self._e = threading.Event()

    def cancel(self) -> None:
        self._e.set()

    def check(self) -> None:
        if self._e.is_set():
            raise GenrePipelineAborted()

    def is_cancelled(self) -> bool:
        return self._e.is_set()


class NullCancelToken:
    def cancel(self) -> None:
        pass

    def check(self) -> None:
        pass

    def is_cancelled(self) -> bool:
        return False
