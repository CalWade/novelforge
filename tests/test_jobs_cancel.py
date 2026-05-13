"""CancelToken 协议与默认实现."""
from __future__ import annotations

import pytest


def test_null_token_never_cancels():
    from src.jobs.cancel import NullCancelToken
    t = NullCancelToken()
    t.check()
    assert not t.is_cancelled()


def test_thread_event_token_check_raises_after_cancel():
    from src.jobs.cancel import ThreadEventToken, GenrePipelineAborted
    t = ThreadEventToken()
    t.check()
    t.cancel()
    assert t.is_cancelled()
    with pytest.raises(GenrePipelineAborted):
        t.check()


def test_thread_event_token_idempotent_cancel():
    from src.jobs.cancel import ThreadEventToken
    t = ThreadEventToken()
    t.cancel()
    t.cancel()
    assert t.is_cancelled()
