import time

import fakeredis

from app.storage.session_store import RedisSessionStore, SlidingWindowRateLimiter


def test_session_store_round_trip_and_expiration() -> None:
    redis_client = fakeredis.FakeStrictRedis(decode_responses=True)
    store = RedisSessionStore(redis_client=redis_client)

    payload = {"messages": [{"role": "user", "content": "Hello"}]}
    store.set_session("conversation-1", payload, ttl=1)

    assert store.get_session("conversation-1") == payload

    time.sleep(1.1)

    assert store.get_session("conversation-1") is None


def test_sliding_window_rate_limiter() -> None:
    redis_client = fakeredis.FakeStrictRedis(decode_responses=True)
    limiter = SlidingWindowRateLimiter(redis_client=redis_client)

    assert limiter.allow_request("user-1", limit=2, window_seconds=1)
    assert limiter.allow_request("user-1", limit=2, window_seconds=1)
    assert not limiter.allow_request("user-1", limit=2, window_seconds=1)

    time.sleep(1.1)

    assert limiter.allow_request("user-1", limit=2, window_seconds=1)
