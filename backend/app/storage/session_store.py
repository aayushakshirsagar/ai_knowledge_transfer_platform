from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

import redis

try:
    from app.core.settings import settings
except Exception:  # pragma: no cover - fallback for tests without env vars
    settings = None


class RedisSessionStore:
    """Simple Redis-backed session store for chat conversation state."""

    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        self.redis = redis_client or self._build_default_client()

    def _build_default_client(self) -> redis.Redis:
        if settings is None:
            raise RuntimeError("A redis client or REDIS_URL must be provided")
        return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

    def _session_key(self, conversation_id: str) -> str:
        return f"session:{conversation_id}"

    def set_session(self, conversation_id: str, data: dict[str, Any], ttl: int) -> None:
        self.redis.setex(self._session_key(conversation_id), ttl, json.dumps(data))

    def get_session(self, conversation_id: str) -> dict[str, Any] | None:
        raw_value = self.redis.get(self._session_key(conversation_id))
        if raw_value is None:
            return None

        try:
            return json.loads(raw_value)
        except (TypeError, json.JSONDecodeError):
            return None


class SlidingWindowRateLimiter:
    """Sliding-window rate limiter implemented with Redis sorted sets."""

    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        self.redis = redis_client or self._build_default_client()

    def _build_default_client(self) -> redis.Redis:
        if settings is None:
            raise RuntimeError("A redis client or REDIS_URL must be provided")
        return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

    def _key(self, user_id: str) -> str:
        return f"rate_limit:{user_id}"

    def allow_request(self, user_id: str, limit: int, window_seconds: int) -> bool:
        now = time.time()
        key = self._key(user_id)
        member = f"{now}:{uuid4().hex}"

        pipeline = self.redis.pipeline()
        pipeline.zremrangebyscore(key, 0, now - window_seconds)
        pipeline.zadd(key, {member: now})
        pipeline.zcard(key)
        pipeline.expire(key, window_seconds)
        _, _, count, _ = pipeline.execute()

        if count > limit:
            self.redis.zrem(key, member)
            return False

        return True
