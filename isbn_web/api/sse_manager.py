"""Server-Sent Events (SSE) manager for real-time progress updates."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict
from uuid import uuid4


class SSEManager:
    """Manages SSE connections and broadcasts progress updates."""

    def __init__(self):
        self._connections: Dict[str, asyncio.Queue] = {}

    def create_task(self) -> str:
        """Create a new task and return its ID."""
        task_id = str(uuid4())
        self._connections[task_id] = asyncio.Queue()
        return task_id

    async def send_event(self, task_id: str, data: Dict[str, Any]) -> None:
        """Send an event to a specific task."""
        if task_id in self._connections:
            await self._connections[task_id].put(data)

    async def subscribe(self, task_id: str):
        """Subscribe to events for a specific task (generator for SSE)."""
        if task_id not in self._connections:
            self._connections[task_id] = asyncio.Queue()

        queue = self._connections[task_id]

        try:
            while True:
                # Wait for next event with timeout
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {
                        "event": "progress",
                        "data": json.dumps(data),
                    }

                    # If completion event, break
                    if data.get("status") == "complete":
                        break

                except asyncio.TimeoutError:
                    # Send keepalive ping
                    yield {
                        "event": "ping",
                        "data": json.dumps({"status": "alive"}),
                    }

        finally:
            # Cleanup
            if task_id in self._connections:
                del self._connections[task_id]

    def cleanup_task(self, task_id: str) -> None:
        """Remove a task and its connection."""
        if task_id in self._connections:
            del self._connections[task_id]


# Global SSE manager instance
sse_manager = SSEManager()
