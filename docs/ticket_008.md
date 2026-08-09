# Ticket 008 — Google Drive Connector and Folder Sync

## Status

Implemented in the FastAPI backend. The connector now covers the full OAuth2 code-exchange flow (no more placeholder callback), encrypted refresh-token storage, multi-folder registration, full folder listing with pagination, per-file download (including export of Google-native files), and an S3 storage placeholder ready to be wired to real uploads.

## What is done

**OAuth flow**
- `GET /api/v1/google-drive/connect?user_id=<id>` redirects the user to Google's consent screen with `access_type=offline`, `prompt=consent`, and `state=user_id`.
- `GET /api/v1/google-drive/callback?code=...&state=...` exchanges the authorization code server-side for a refresh token via `POST https://oauth2.googleapis.com/token` (`grant_type=authorization_code`) and stores the refresh token encrypted.
- `POST https://oauth2.googleapis.com/token` refresh flow (`grant_type=refresh_token`) mints short-lived access tokens before every Drive call.

**Configuration (app/core/settings.py)**
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REDIRECT_URI`
- `GOOGLE_OAUTH_SCOPES` = `https://www.googleapis.com/auth/drive.readonly`

**Data models (app/models/tables.py) + migrations `0002_google_drive_oauth.py` / `0003_gmail_oauth.py`**
- `OAuthToken` — **shared** encrypted token store for all Google connectors (`connector_type` = `drive`/`gmail`), holding both access and refresh tokens, unique per `(user_id, connector_type)`. Migration 0003 creates it, copies Drive tokens over, and drops the old `google_drive_oauth_tokens` table.
- `GoogleDriveFolderConfig` — many folders per user/project; stores the Drive `folder_id`.
- `GoogleDriveSyncState` — per user/folder sync bookkeeping (`next_page_token`, `sync_token`).

**Folder registration & sync (app/services/google_drive_sync.py)**
- `POST /api/v1/google-drive/folders?user_id=&project_id=&folder_id=&folder_name=` registers a folder (idempotent).
- `POST /api/v1/google-drive/sync/{folder_config_id}?user_id=` runs a sync:
  1. Resolves the refresh token and obtains an access token.
  2. `_list_folder_files` — paginated `GET /drive/v3/files?q='<folder_id>' in parents and trashed=false` with `supportsAllDrives`/`includeItemsFromAllDrives`, walking all `nextPageToken` pages.
  3. Creates `Document` rows (`source=drive`, `source_ref=Drive file id`, `status=pending`), deduped per `(project_id, source, source_ref)`.
  4. Downloads every file (`_download_file`) and hands the bytes to the storage layer (`_store_document_content`).
  5. Returns `created_documents` and `downloaded_files` counts.

**Downloading (app/services/google_drive_sync.py)**
- Binary files: `GET /drive/v3/files/{id}?alt=media`.
- Google-native files are exported to a portable format first:
  - Docs / Slides / Rich text / Drawings → PDF
  - Sheets → CSV
- Unsupported Google types are skipped (empty content).

**S3 storage placeholder (app/services/google_drive_sync.py)**
- `_store_document_content(project_id, document_id, filename, content)` is currently a **placeholder** — it performs no I/O and just returns the future S3 key `projects/{project_id}/documents/{document_id}/{filename}`.
- Real wiring will go through `app/storage/s3_storage.py` (`S3StorageService`), which already builds the same key layout. Note it uploads from a local file path, so either add a bytes variant or write to a temp file first.

**Supporting changes**
- `backend/app/main.py` — registered the `google-drive` router.
- `backend/pyproject.toml` / `backend/uv.lock` — added `cryptography` and `requests`.

## Architecture decisions

1. **User OAuth over service account** — OAuth2 browser flow per user; tokens are per-user, not shared. First version is read-only Drive scope.
2. **Encrypted token storage in the DB** — the refresh token is encrypted with a Fernet key derived from `JWT_SECRET` (base64-url-safe, zero-padded to 32 bytes) and base64-encoded on top. No token in plain text, no external secret store yet.
3. **One folder → one project** — each `GoogleDriveFolderConfig` maps a folder to exactly one project; a folder can be registered for multiple projects.
4. **Manual sync trigger** — `/sync` is called explicitly; no scheduler/background queue yet.
5. **Full download per sync** — the sync lists **all pages** and downloads every file every run. The `next_page_token`/`sync_token` columns exist for a future `changes.list` incremental sync but are not used yet.
6. **Download in memory** — file bytes are held as `bytes` and passed to storage; large folders could exhaust memory.
7. **S3 deferred** — storage is a placeholder by design so the sync pipeline can be built and tested without AWS credentials.

## Data models — design rationale

**`OAuthToken`** (tables.py) — the **shared** table for Google OAuth tokens across connectors. Access tokens are short-lived (~1 hour); the **refresh token is the long-lived credential** that can mint new access tokens, so both must be persisted or every sync/call would require a fresh browser consent. A composite unique constraint on `(user_id, connector_type)` allows one identity per user **per connector** (e.g. `drive` and `gmail` side by side), and both tokens are stored **encrypted** (Fernet) so a database leak does not leak credentials. Replaces the Drive-only `GoogleDriveOAuthToken` table from migration 0002.

**`GoogleDriveFolderConfig`** (tables.py:254) — pure **configuration**: which Drive folder belongs to which user and maps to which project. A Drive folder ID is an opaque string (`1AbC...`); without this table the app has no record of "project 3 = folder X" and nothing to sync. Registration is idempotent — dedup on `(user_id, project_id, folder_id)` means calling it twice does not create duplicates.

**`GoogleDriveSyncState`** (tables.py:268) — per `(user, folder)` bookkeeping of **where a sync left off**, so a future sync can resume instead of restarting from zero. Its two columns mean different things:

- `next_page_token` — **page pagination** for `files.list`. A single listing can span many pages; Drive returns a `nextPageToken` that continues from where the listing stopped. This lets a partially-completed listing resume instead of re-querying earlier pages.
- `sync_token` — **change token** for Drive's `changes.list` API. This is Drive's incremental-change cursor: hand it back and Drive returns *only* files that were added/modified/removed since the last sync, instead of re-listing the whole folder.

Today the code only walks all pages in one pass and writes `updated_at`; neither token is actually consumed yet — the columns are reserved for the incremental path.

### Why full download per sync, and what sync_state is for

Incremental change detection is **not implemented yet**, so `sync_folder` brute-forces: list **all** files (all pages), then download **every** file, each run. This is the simplest *correct* version:

- Dedup happens at the **document-row level** (skip when `source="drive"` and `source_ref` already exists), so re-syncs do not duplicate rows.
- But it **re-downloads unchanged bytes every run** — wasteful, yet correct, and fine for small folders.

`sync_state` exists to eliminate that waste later: once `changes.list` + `sync_token` are wired up, a re-sync would fetch only the delta instead of re-listing and re-downloading the whole folder, and `next_page_token` lets an interrupted sync resume.

## How to test

**Automated tests** (from the `backend` folder):

```powershell
uv run pytest tests/test_google_drive_connector.py tests/test_google_drive_sync.py
```

Expected result: 3 passed.

- `test_encrypt_and_decrypt_round_trip` — Fernet round-trip.
- `test_store_and_load_refresh_token` — token upsert/retrieval with decryption.
- `test_register_folder_and_create_documents` — folder registration + paginated listing + document creation + download (requests mocked).

**Manual smoke test** (requires real Google credentials in `infra/.env`):

1. Start the API: `uv run uvicorn app.main:app --reload`.
2. Create a user row in the DB and note its `id` (there is no user API yet).
3. Open `http://localhost:8000/api/v1/google-drive/connect?user_id=1` in a browser, complete consent.
4. Confirm the callback returns `{"message": "Google Drive connected successfully"}`.
5. Register a folder: `POST /api/v1/google-drive/folders?user_id=1&project_id=1&folder_id=<DRIVE_FOLDER_ID>&folder_name=Docs`.
   - The folder id is the path segment in the Drive URL, e.g. `https://drive.google.com/drive/folders/1AbC...`.
6. Sync: `POST /api/v1/google-drive/sync/{folder_config_id}?user_id=1` and confirm `created_documents`/`downloaded_files`.

## Future integration with the Google Picker (Drive Picker) API

The picker runs client-side in the browser and lets a user choose a Drive folder instead of typing a folder ID.

- Enable the **Google Picker API** in the Google Cloud Console alongside Drive, and create a browser **API key** (add your frontend origin to "Authorized JavaScript origins").
- The picker needs the same OAuth **Client ID** (the one already configured) so it can act on the signed-in user's Drive. The existing `drive.readonly` scope is sufficient for picking folders.
- Frontend flow:
  1. Load the Picker with the browser API key + OAuth client id.
  2. On `SELECTED`, read the picked resource — folders come back with `mimeType: application/vnd.google-apps.folder` and an `id`/`name`.
  3. Send that `id`/`name` to the existing `POST /api/v1/google-drive/folders` endpoint (no new backend needed).
  4. Optionally auto-trigger `POST /api/v1/google-drive/sync/{folder_config_id}` after registration.
- Guard on the backend that the supplied `folder_id` is actually a folder (mimeType `application/vnd.google-apps.folder`) by resolving it via `GET /drive/v3/files/{id}?fields=mimeType` before registering.

## Things to keep in mind

- **Secrets hygiene** — `client_secret_...apps.googleusercontent.com.json` sits in the repo root. Add it to `.gitignore`, and keep credentials in `infra/.env` only. The `_encrypt` key is derived from `JWT_SECRET` — **changing `JWT_SECRET` invalidates all stored refresh tokens** and forces users to re-connect.
- **Redirect URI must match exactly** — `GOOGLE_OAUTH_REDIRECT_URI` must equal one of the registered `redirect_uris` in the Google Console or the code exchange 400s.
- **Refresh token rotation** — Google returns a refresh token only on first consent (`prompt=consent` is set); if a user revokes access the token becomes invalid and re-consent is required.
- **Endpoints are unauthenticated** — `user_id` is passed as a query param (`/connect`, `/sync`, `/folders`). Add real auth + ownership checks before production.
- **No pagination/rate-limit handling on downloads** and sync is synchronous inside the HTTP request — move sync to a background task/queue for large folders.
- **Export fidelity** — Docs→PDF, Sheets→CSV lose some layout; parsing later should account for that.
- **Memory** — downloads are buffered fully in memory; stream to disk or S3 for large files.
- **Incremental sync not implemented** — every sync re-lists and re-downloads everything; `changes.list` + `sync_token` is the planned optimization.
- **Downstream pipeline** — documents are created with `status=pending`; the parsing/embedding/ingestion stage must pick them up and consume the S3-stored bytes.

---

# Gmail Connector — Thread Reading APIs

## What is done

**Endpoints (app/api/gmail.py)**
- `GET /api/gmail/threads` — list email threads.
  - Query params (all optional): `q` (Gmail search syntax, e.g. `from:john@gmail.com`, `is:unread`), `maxResults` (default 20, validated 1–500), `labelIds` (comma-separated, e.g. `INBOX,UNREAD`), `pageToken`.
  - Response: `{"threads": [{"id", "historyId"}], "nextPageToken", "resultSizeEstimate", "total"}`.
- `GET /api/gmail/threads/{thread_id}` — full thread details.
  - Query params: `format` (`full` default, `metadata`, `minimal`).
  - Passes through Gmail's thread payload and adds per-message `decodedContent`.
- Both endpoints accept an optional `user_id` query param (default `1`) to select whose Gmail connection is used — same convention as the Drive endpoints pending real auth.

**Underlying Gmail API calls (app/services/gmail_connector.py)**
- `GET https://gmail.googleapis.com/gmail/v1/users/me/threads` with `maxResults`, `q`, `labelIds`, `pageToken`.
- `GET https://gmail.googleapis.com/gmail/v1/users/me/threads/{threadId}` with `format`.
- All calls carry `Authorization: Bearer <access_token>`.

**Token management**
- `store_tokens` / `get_tokens` / `get_access_token` — both `access_token` and `refresh_token` are stored **encrypted** (Fernet, same `JWT_SECRET`-derived key as the Drive connector) in the **shared `oauth_tokens` table** (row filtered by `connector_type="gmail"`).
- **Automatic refresh on 401** — `_request` refreshes the token once via `POST https://oauth2.googleapis.com/token` (`grant_type=refresh_token`) and retries the original call.
- **429 exponential backoff** — retries up to 3 times (1s, 2s, 4s), honoring the `Retry-After` header when present.
- Error mapping → `{"error": {"code", "message", "details"}}`: 401 expired/invalid token, 403 insufficient scope, 404 not found, 429 rate limit, others pass through the Gmail API message.

**Content decoding**
- `decode_base64_content` base64url-decodes Gmail content. For each message, `body.data` and every `parts[].body.data` are decoded and collected into `decodedContent = {"text": "...", "html": "..."}` (text/plain vs text/html parts).

**Configuration (app/core/settings.py)**
- `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REDIRECT_URI`, `GMAIL_ACCESS_TOKEN_STORAGE` (default `database`), `GMAIL_SCOPES` = `https://www.googleapis.com/auth/gmail.readonly`.

**Data model + migration**
- `OAuthToken` (tables.py) — shared encrypted token store: `user_id`, `connector_type` (`gmail`), `encrypted_access_token`, `encrypted_refresh_token`, `scope`, unique on `(user_id, connector_type)`.
- Migration `0003_gmail_oauth.py` — creates the unified `oauth_tokens` table and drops the old Drive-only token table.

**Files added or updated**
- `app/api/gmail.py`
- `app/services/gmail_connector.py`
- `app/models/tables.py`
- `app/db/migrations/versions/0003_gmail_oauth.py`
- `app/core/settings.py`
- `app/main.py` (registered the `gmail` router)
- `infra/.env` (added Gmail section)
- Tests: `tests/test_gmail_connector.py`, `tests/test_gmail_api.py`

## Architecture decisions

1. **Same pattern as the Drive connector** — raw `requests` with a Bearer header and the shared Fernet/`JWT_SECRET` encryption, rather than the `google-api-python-client` library.
2. **Access + refresh token both persisted** — the requirements treat OAuth as already complete, so the service reads stored tokens; the refresh token is also kept so 401s can be recovered automatically without re-consent.
3. **Lazy refresh on 401** — no access-token expiry tracking; the token is refreshed only when the API actually rejects it, then the request is retried once.
4. **`GMAIL_ACCESS_TOKEN_STORAGE` switch** — currently `database`; the setting exists so a different storage backend can be plugged in later.
5. **`user_id` as a query param** — mirrors the Drive endpoints; replace with real auth/ownership later.
6. **`format` passed straight through** — `minimal`/`metadata` return Gmail's headers-only payload; `decodedContent` is only populated for `full` messages that carry a body.

## How to test

**Automated tests** (from the `backend` folder):

```powershell
uv run pytest tests/test_gmail_connector.py tests/test_gmail_api.py
```

Expected result: 21 passed.

- Connector tests (`test_gmail_connector.py`):
  - `test_store_and_load_tokens` — encrypted token round-trip.
  - `test_tokens_are_encrypted_at_rest` — plaintext never written to the DB.
  - `test_store_tokens_is_upsert` — re-storing updates, does not duplicate rows.
  - `test_decode_base64_content` — base64url decode + bad-input handling.
  - `test_list_threads_builds_params_and_format` — params/headers + response format.
  - `test_get_thread_decodes_body_and_parts` — decodes `body.data` and `parts[].body.data`.
  - `test_401_triggers_token_refresh_and_retry` — refresh happens once, retry uses the new token.
  - `test_refresh_flow_exchanges_refresh_token` — token endpoint payload handling.
  - `test_429_uses_exponential_backoff_and_retries` — sleeps 1s then 2s, then succeeds.
  - `test_403_raises_insufficient_scope` — clear insufficient-scope message.
  - `test_404_raises_thread_not_found` — 404 mapping.
  - `test_no_tokens_raises_401` — missing token surfaces 401.
  - `test_gmail_and_drive_tokens_share_one_table_but_stay_isolated` — both connectors use `oauth_tokens` without colliding.
- API tests (`test_gmail_api.py`):
  - `test_list_threads_parses_query_params`, `test_list_threads_with_defaults`
  - `test_list_threads_maps_gmail_error_to_http_error`, `test_get_thread_maps_404_error`
  - `test_get_thread_passes_format_and_returns_decoded`, `test_get_thread_rejects_empty_thread_id`

**Manual smoke test** (requires seeded tokens + Gmail client creds in `infra/.env`):

1. Start the API: `uv run uvicorn app.main:app --reload`.
2. Seed tokens for a user: `connector.store_tokens(user_id=1, access_token=..., refresh_token=..., scope="https://www.googleapis.com/auth/gmail.readonly")`.
3. List threads: `GET /api/gmail/threads?q=is:unread&maxResults=10&labelIds=INBOX&user_id=1`.
4. Open one thread: `GET /api/gmail/threads/<thread_id>?format=full&user_id=1` and confirm each message has `decodedContent.text` / `.html`.

## Things to keep in mind

- **`JWT_SECRET`-derived Fernet key** — shared with the Drive connector; changing `JWT_SECRET` invalidates stored Gmail tokens too.
- **Read-only scope** — `gmail.readonly`; 403 is surfaced if a narrower or revoked scope is granted.
- **Endpoints are unauthenticated** — `user_id` is a query param; add real auth + ownership checks before production.
- **`decodedContent` only for `full` format** — `metadata`/`minimal` return headers-only payloads.
- **`maxResults` capped at 500** — both server-side validation and Gmail's own limit.
- **Pre-existing test collection errors** — `test_vector_store`, `test_s3_storage`, `test_session_store` fail at import in this env due to missing optional deps (`qdrant_client`, `boto3`, `fakeredis`); unrelated to this ticket.
