"""
TICKET-020 - Worker entry point.

Pulls document processing jobs off the Redis queue populated by
app/ingestion/queue.py::enqueue_document_parse() and runs them through the
ingestion pipeline (parse -> chunk -> contextual headers -> embed -> Qdrant upsert).

Queue contract (from app/ingestion/queue.py - matched exactly):
    QUEUE_NAME = "document_parse_queue"
    producer:  redis_client.rpush(QUEUE_NAME, json.dumps({"document_id": ..., "project_id": ...}))

rpush pushes onto the right end of the list, so this worker uses BLPOP
(pop from the left) to process jobs in the same FIFO order they were
enqueued. Do not swap this for BRPOP - that would process newest-first (LIFO).

Run:
    uv run worker
    # or
    uv run python -m app.worker
"""

from __future__ import annotations

import json
import logging
import signal
import sys

import redis

from app.core.settings import settings
from app.ingestion.orchestrator import process_document
from app.ingestion.queue import QUEUE_NAME

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("worker")

# How long BLPOP blocks before looping again to check the shutdown flag.
POLL_TIMEOUT_SECONDS = 5

_shutdown_requested = False


def _handle_shutdown(signum, frame):
    global _shutdown_requested
    logger.info("Shutdown signal received (%s), finishing current job then exiting...", signum)
    _shutdown_requested = True


def _handle_job(raw_payload: bytes) -> None:
    try:
        payload = json.loads(raw_payload)
        document_id = payload["document_id"]
        project_id = payload.get("project_id")
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        # Malformed queue message - log and drop rather than crash the worker.
        logger.error("Dropping malformed queue message %r: %s", raw_payload, exc)
        return

    logger.info("Processing document %s (project %s)", document_id, project_id)
    try:
        process_document(document_id)
    except Exception:
        # process_document already catches and records failures internally,
        # so reaching here means something outside the pipeline's own error
        # handling broke (e.g. a bug in process_document itself). Log and
        # move on - one document must never take the worker down.
        logger.exception("Unhandled error processing document %s", document_id)


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    client = redis.from_url(settings.REDIS_URL)
    logger.info("Worker started, listening on queue '%s'", QUEUE_NAME)

    while not _shutdown_requested:
        try:
            result = client.blpop(QUEUE_NAME, timeout=POLL_TIMEOUT_SECONDS)
        except redis.RedisError as exc:
            logger.error("Redis connection error: %s - retrying in %ss", exc, POLL_TIMEOUT_SECONDS)
            continue

        if result is None:
            continue  # timed out waiting, loop back and check shutdown flag

        _, raw_payload = result
        _handle_job(raw_payload)

    logger.info("Worker shut down cleanly")


if __name__ == "__main__":
    sys.exit(main() or 0)