from __future__ import annotations

import json
import redis

QUEUE_NAME = "document_parse_queue"


def enqueue_document_parse(redis_client: redis.Redis, document_id: int, project_id: int) -> int:
    payload = json.dumps({"document_id": document_id, "project_id": project_id})
    return redis_client.rpush(QUEUE_NAME, payload)
