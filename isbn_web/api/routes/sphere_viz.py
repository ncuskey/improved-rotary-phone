"""WebSocket endpoint for 3D sphere visualization real-time events."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

if TYPE_CHECKING:
    pass

router = APIRouter()

# Track all connected visualization clients
connected_clients: list[WebSocket] = []


class VizEventBroadcaster:
    """Broadcast visualization events to all connected clients."""

    @staticmethod
    async def broadcast(event: dict):
        """Send event to all connected WebSocket clients."""
        disconnected = []
        for client in connected_clients:
            try:
                if client.client_state == WebSocketState.CONNECTED:
                    await client.send_json(event)
                else:
                    disconnected.append(client)
            except Exception:
                disconnected.append(client)

        # Clean up disconnected clients
        for client in disconnected:
            if client in connected_clients:
                connected_clients.remove(client)

    @staticmethod
    async def book_accessed(isbn: str, title: str | None = None):
        """Broadcast that a book was accessed."""
        await VizEventBroadcaster.broadcast({
            "type": "book_accessed",
            "isbn": isbn,
            "title": title,
            "timestamp": asyncio.get_event_loop().time(),
        })

    @staticmethod
    async def request_received(method: str, path: str):
        """Broadcast that a request was received."""
        await VizEventBroadcaster.broadcast({
            "type": "request_in",
            "method": method,
            "path": path,
            "timestamp": asyncio.get_event_loop().time(),
        })

    @staticmethod
    async def response_sent(method: str, path: str, status_code: int):
        """Broadcast that a response was sent."""
        await VizEventBroadcaster.broadcast({
            "type": "response_out",
            "method": method,
            "path": path,
            "status_code": status_code,
            "timestamp": asyncio.get_event_loop().time(),
        })

    @staticmethod
    async def database_read(operation: str, count: int = 1):
        """Broadcast that a database read occurred."""
        await VizEventBroadcaster.broadcast({
            "type": "db_read",
            "operation": operation,
            "count": count,
            "timestamp": asyncio.get_event_loop().time(),
        })

    @staticmethod
    async def database_write(operation: str, count: int = 1):
        """Broadcast that a database write occurred."""
        await VizEventBroadcaster.broadcast({
            "type": "db_write",
            "operation": operation,
            "count": count,
            "timestamp": asyncio.get_event_loop().time(),
        })

    @staticmethod
    async def data_scraping(source: str, count: int = 1):
        """Broadcast that data scraping/enrichment occurred."""
        await VizEventBroadcaster.broadcast({
            "type": "scraping",
            "source": source,
            "count": count,
            "timestamp": asyncio.get_event_loop().time(),
        })

    @staticmethod
    async def ml_prediction(model: str, count: int = 1):
        """Broadcast that ML prediction occurred."""
        await VizEventBroadcaster.broadcast({
            "type": "ml_prediction",
            "model": model,
            "count": count,
            "timestamp": asyncio.get_event_loop().time(),
        })


@router.post("/api/viz/emit")
async def emit_events(request: Request):
    """
    Receive batched visualization events from db_monitor.

    This endpoint is called by shared.db_monitor.EventBatcher when
    database writes occur, allowing background scripts to send
    visualization events without going through the web API.

    Body: {"events": [{"type": "db_write", "isbn": "...", ...}, ...]}

    Returns: {"status": "ok", "processed": N}
    """
    try:
        data = await request.json()
        events = data.get("events", [])

        # Broadcast each event to connected WebSocket clients
        for event in events:
            await VizEventBroadcaster.broadcast(event)

        return {"status": "ok", "processed": len(events)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.websocket("/ws/viz")
async def visualization_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for 3D visualization.

    Streams real-time events:
    - book_accessed: When a book is referenced
    - request_in: Incoming HTTP request
    - response_out: Outgoing HTTP response
    - db_read: Database read operation
    - db_write: Database write operation
    - scraping: Data scraping/enrichment (AbeBooks, eBay, metadata)
    - ml_prediction: ML model predictions (price, probability)
    """
    await websocket.accept()
    connected_clients.append(websocket)

    try:
        # Send initial connection event
        await websocket.send_json({
            "type": "connected",
            "message": "Visualization stream connected",
            "timestamp": asyncio.get_event_loop().time(),
        })

        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for client messages (like ping/pong)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Echo back to keep connection alive
                await websocket.send_json({"type": "pong", "received": data})
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    finally:
        if websocket in connected_clients:
            connected_clients.remove(websocket)


# Export broadcaster for use in middleware
viz_broadcaster = VizEventBroadcaster()
