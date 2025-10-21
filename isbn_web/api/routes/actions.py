"""API routes for bulk actions (import, refresh, etc.)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile, BackgroundTasks
from fastapi.responses import JSONResponse

from isbn_lot_optimizer.service import BookService
from shared.utils import read_isbn_csv

from ..dependencies import get_book_service
from ..sse_manager import sse_manager

router = APIRouter()


def _progress_callback(task_id: str):
    """Create a progress callback that sends SSE events."""
    def callback(done: int, total: int, label: str = ""):
        # Run async send in event loop
        asyncio.create_task(
            sse_manager.send_event(task_id, {
                "done": done,
                "total": total,
                "percent": int((done / total * 100)) if total > 0 else 0,
                "label": label,
                "status": "in_progress",
            })
        )
    return callback


async def _import_csv_task(
    task_id: str,
    file_path: Path,
    condition: str,
    service: BookService,
):
    """Background task for CSV import with progress tracking."""
    try:
        # Send start event
        await sse_manager.send_event(task_id, {
            "done": 0,
            "total": 0,
            "percent": 0,
            "label": "Reading CSV...",
            "status": "started",
        })

        # Read ISBNs from CSV
        isbns = read_isbn_csv(file_path)
        total = len(isbns)

        # Send progress updates
        for idx, isbn in enumerate(isbns, start=1):
            try:
                service.scan_isbn(isbn, condition=condition)
            except Exception:
                # Continue on error
                pass

            # Send progress event
            await sse_manager.send_event(task_id, {
                "done": idx,
                "total": total,
                "percent": int((idx / total * 100)),
                "label": f"Imported {idx}/{total} books",
                "status": "in_progress",
            })

        # Send completion event
        await sse_manager.send_event(task_id, {
            "done": total,
            "total": total,
            "percent": 100,
            "label": f"Imported {total} books",
            "status": "complete",
        })

    except Exception as e:
        # Send error event
        await sse_manager.send_event(task_id, {
            "error": str(e),
            "status": "error",
        })

    finally:
        # Cleanup temp file
        try:
            file_path.unlink()
        except Exception:
            pass


@router.post("/import-csv")
async def import_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    condition: str = Form("Good"),
    service: BookService = Depends(get_book_service),
):
    """
    Import books from a CSV file.

    Returns a task_id that can be used to subscribe to progress updates via SSE.
    """
    # Create task ID for progress tracking
    task_id = sse_manager.create_task()

    # Save uploaded file to temp location
    temp_path = Path(f"/tmp/isbn_import_{task_id}.csv")
    with temp_path.open("wb") as f:
        content = await file.read()
        f.write(content)

    # Start background task
    background_tasks.add_task(_import_csv_task, task_id, temp_path, condition, service)

    return JSONResponse({
        "task_id": task_id,
        "message": "Import started",
    })


@router.post("/refresh-metadata")
async def refresh_metadata(
    background_tasks: BackgroundTasks,
    limit: Optional[int] = Form(None),
    service: BookService = Depends(get_book_service),
):
    """
    Refresh metadata for books in the database.

    Returns a task_id for progress tracking.
    """
    task_id = sse_manager.create_task()

    async def task():
        try:
            books = service.list_books()
            if limit:
                books = books[:limit]

            total = len(books)

            await sse_manager.send_event(task_id, {
                "done": 0,
                "total": total,
                "percent": 0,
                "label": "Starting metadata refresh...",
                "status": "started",
            })

            for idx, book in enumerate(books, start=1):
                try:
                    service.refresh_book_market(book.isbn)
                except Exception:
                    pass

                await sse_manager.send_event(task_id, {
                    "done": idx,
                    "total": total,
                    "percent": int((idx / total * 100)),
                    "label": f"Refreshed {idx}/{total} books",
                    "status": "in_progress",
                })

            await sse_manager.send_event(task_id, {
                "done": total,
                "total": total,
                "percent": 100,
                "label": "Metadata refresh complete",
                "status": "complete",
            })

        except Exception as e:
            await sse_manager.send_event(task_id, {
                "error": str(e),
                "status": "error",
            })

    background_tasks.add_task(task)

    return JSONResponse({
        "task_id": task_id,
        "message": "Metadata refresh started",
    })
