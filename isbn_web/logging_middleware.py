"""Comprehensive HTTP request/response logging middleware."""
from __future__ import annotations

import json
import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Setup request logger
LOG_DIR = Path.home() / ".isbn_lot_optimizer"
LOG_DIR.mkdir(parents=True, exist_ok=True)
REQUEST_LOG = LOG_DIR / "http_requests.log"

request_logger = logging.getLogger("isbn_web.requests")
if not request_logger.handlers:
    request_logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        REQUEST_LOG,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    request_logger.addHandler(handler)
    request_logger.propagate = False


class HTTPLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all HTTP requests and responses.

    Logs include:
    - Request method, path, query params
    - Request headers (sanitized)
    - Response status code
    - Response time
    - Client IP address
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        # Start timing
        start_time = time.time()

        # Extract request info
        method = request.method
        path = request.url.path
        query = str(request.url.query) if request.url.query else ""
        client_ip = request.client.host if request.client else "unknown"

        # Sanitize headers (remove sensitive data)
        headers = dict(request.headers)
        sensitive_headers = {"authorization", "cookie", "x-api-key"}
        for key in sensitive_headers:
            if key in headers:
                headers[key] = "[REDACTED]"

        # Log request
        request_logger.info(
            f"→ {method} {path}" +
            (f"?{query}" if query else "") +
            f" | IP: {client_ip}"
        )

        # Process request
        try:
            response = await call_next(request)
            status_code = response.status_code
            error = None
        except Exception as e:
            status_code = 500
            error = str(e)
            request_logger.error(
                f"✗ {method} {path} | ERROR: {error}"
            )
            raise

        # Calculate duration
        duration = time.time() - start_time

        # Log response
        status_emoji = "✓" if 200 <= status_code < 300 else "⚠" if 300 <= status_code < 400 else "✗"
        request_logger.info(
            f"{status_emoji} {method} {path} | "
            f"Status: {status_code} | "
            f"Time: {duration:.3f}s"
        )

        # Add timing header
        response.headers["X-Response-Time"] = f"{duration:.3f}s"

        return response


def log_custom_event(event_type: str, **data):
    """
    Log a custom event with arbitrary data.

    Usage:
        log_custom_event("book_scan", isbn="9781234567890", result="accept")
    """
    try:
        event_data = json.dumps(data, ensure_ascii=False)
        request_logger.info(f"📍 {event_type} | {event_data}")
    except Exception as e:
        request_logger.error(f"Failed to log custom event: {e}")
