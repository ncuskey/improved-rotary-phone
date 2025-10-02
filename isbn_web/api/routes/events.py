"""Server-Sent Events (SSE) routes for real-time progress updates."""
from __future__ import annotations

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from ..sse_manager import sse_manager

router = APIRouter()


@router.get("/{task_id}")
async def subscribe_to_task(task_id: str):
    """
    Subscribe to Server-Sent Events for a specific task.

    This endpoint provides real-time progress updates for long-running operations
    like CSV imports, metadata refreshes, and lot generation.
    """
    return EventSourceResponse(sse_manager.subscribe(task_id))
