from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from app.services.gmail_connector import GmailAPIError, GmailConnectorService

router = APIRouter(prefix="/api/gmail", tags=["gmail"])

connector = GmailConnectorService()


def _handle_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, GmailAPIError):
        return HTTPException(status_code=exc.code, detail=exc.to_dict())
    return HTTPException(
        status_code=400,
        detail={"error": {"code": 400, "message": "Invalid request", "details": str(exc)}},
    )


@router.get("/threads")
def list_threads(
    user_id: Annotated[int, Query(description="Owner of the Gmail connection")] = 1,
    q: Annotated[str, Query(description="Gmail search syntax, e.g. from:john@gmail.com, is:unread")] = "",
    maxResults: Annotated[int, Query(ge=1, le=500, description="Max threads per page (1-500)")] = 20,
    labelIds: Annotated[str | None, Query(description="Comma-separated label IDs, e.g. INBOX,UNREAD")] = None,
    pageToken: Annotated[str | None, Query(description="Pagination token for the next page")] = None,
) -> dict[str, object]:
    try:
        label_ids = [label.strip() for label in labelIds.split(",") if label.strip()] if labelIds else None
        return connector.list_threads(
            user_id=user_id,
            q=q.strip(),
            max_results=maxResults,
            label_ids=label_ids,
            page_token=pageToken,
        )
    except Exception as exc:
        raise _handle_errors(exc)


@router.get("/threads/{thread_id}")
def get_thread(
    thread_id: str,
    user_id: Annotated[int, Query(description="Owner of the Gmail connection")] = 1,
    format: Annotated[Literal["full", "metadata", "minimal"], Query(description="Message format")] = "full",
) -> dict[str, object]:
    if not thread_id.strip():
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": 400, "message": "threadId is required", "details": "Path parameter cannot be empty"}},
        )
    try:
        return connector.get_thread(user_id=user_id, thread_id=thread_id.strip(), format=format)
    except Exception as exc:
        raise _handle_errors(exc)
