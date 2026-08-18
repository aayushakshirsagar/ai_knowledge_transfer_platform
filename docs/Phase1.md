ticket 006 
6.Ticket 004 - Manual upload ingestion endpoint

- This ticket adds `POST /ingestion/upload` in the backend.
- Accepts multipart file upload plus `project_id`.
- Verifies requesting user has access via `project_assignments`.
- Stores the file in S3 via `S3StorageService`.
- Creates a `documents` row with `source=manual_upload`, `status=pending`, and `file_path` set to the S3 key.
- Enqueues a parse job to a Redis-backed background queue.
- Returns `document_id` synchronously.

- cd backend
- uv run pytest tests/test_ingestion_upload.py -q