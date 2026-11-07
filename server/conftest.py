"""Each test represents an independent rate-limit window."""
import pytest


@pytest.fixture(autouse=True)
def isolated_rate_buckets():
    from server.app import RATE_LIMITER
    with RATE_LIMITER.lock:
        RATE_LIMITER.entries.clear()
    yield
    with RATE_LIMITER.lock:
        RATE_LIMITER.entries.clear()
