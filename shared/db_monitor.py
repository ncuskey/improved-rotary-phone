"""
Database monitoring wrapper for visualization events.

Wraps SQLite connections to intercept INSERT/UPDATE/DELETE operations.
Batches events and sends them asynchronously to minimize performance impact.
"""

import sqlite3
import threading
import time
import re
from typing import Optional, Tuple
import requests
from collections import deque

# Configuration
VIZ_SERVER_URL = "http://localhost:8000/api/viz/emit"
BATCH_SIZE = 50  # Send after this many events
BATCH_INTERVAL = 0.1  # Or send after this many seconds
ENABLED = True  # Can be disabled via env var


class EventBatcher:
    """Batches and sends visualization events asynchronously."""

    def __init__(self):
        self.queue = deque()
        self.lock = threading.Lock()
        self.worker_thread = None
        self.running = False

    def start(self):
        """Start the background worker thread."""
        if not ENABLED or self.running:
            return

        self.running = True
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

    def stop(self):
        """Stop the background worker thread."""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=1.0)

    def add_event(self, event: dict):
        """Add an event to the batch queue."""
        if not ENABLED:
            return

        with self.lock:
            self.queue.append(event)

    def _worker(self):
        """Background worker that sends batched events."""
        last_send = time.time()

        while self.running:
            try:
                # Check if we should send
                with self.lock:
                    queue_size = len(self.queue)
                    time_since_send = time.time() - last_send

                should_send = (
                    queue_size >= BATCH_SIZE or
                    (queue_size > 0 and time_since_send >= BATCH_INTERVAL)
                )

                if should_send:
                    # Grab events to send
                    with self.lock:
                        events = list(self.queue)
                        self.queue.clear()

                    # Send async (non-blocking)
                    try:
                        requests.post(
                            VIZ_SERVER_URL,
                            json={"events": events},
                            timeout=0.5
                        )
                    except Exception:
                        # Silently ignore network errors
                        pass

                    last_send = time.time()
                else:
                    # Sleep briefly to avoid busy loop
                    time.sleep(0.01)

            except Exception:
                # Catch all exceptions to keep worker alive
                time.sleep(0.1)


# Global batcher instance
_batcher = EventBatcher()


class MonitoredCursor:
    """Cursor wrapper that intercepts execute() to monitor database operations."""

    def __init__(self, cursor, conn):
        self._cursor = cursor
        self._conn = conn

    def _extract_isbn_from_sql(self, sql: str, parameters) -> Optional[str]:
        """Try to extract ISBN from SQL statement and parameters."""
        try:
            # Look for isbn in parameters
            if isinstance(parameters, (tuple, list)):
                # For INSERT/UPDATE with positional parameters
                # Try to find isbn= pattern in SQL
                if 'cached_books' in sql.lower() or 'books' in sql.lower() or 'sold_listings' in sql.lower():
                    # Look for WHERE isbn = ? pattern
                    where_match = re.search(r'WHERE\s+isbn\s*=\s*\?', sql, re.IGNORECASE)
                    if where_match and len(parameters) > 0:
                        return str(parameters[-1])  # ISBN is usually last in WHERE clause

            elif isinstance(parameters, dict):
                # For named parameters
                if 'isbn' in parameters:
                    return str(parameters['isbn'])

            return None
        except Exception:
            return None

    def _detect_operation(self, sql: str) -> Tuple[Optional[str], Optional[str]]:
        """Detect operation type and table name from SQL."""
        sql_upper = sql.upper().strip()

        # Detect operation
        if sql_upper.startswith('INSERT'):
            operation = 'insert'
        elif sql_upper.startswith('UPDATE'):
            operation = 'update'
        elif sql_upper.startswith('DELETE'):
            operation = 'delete'
        else:
            return None, None

        # Extract table name
        table_match = re.search(r'(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(\w+)', sql, re.IGNORECASE)
        if table_match:
            table_name = table_match.group(1)
        else:
            table_name = None

        return operation, table_name

    def execute(self, sql, parameters=()):
        """Execute SQL and emit monitoring event if it's a write operation."""
        if ENABLED:
            operation, table_name = self._detect_operation(sql)
            if operation and table_name:
                isbn = self._extract_isbn_from_sql(sql, parameters)

                event = {
                    "type": "db_write",
                    "operation": operation,
                    "table": table_name,
                    "isbn": isbn,
                    "timestamp": time.time()
                }
                _batcher.add_event(event)

        return self._cursor.execute(sql, parameters)

    def executemany(self, sql, seq_of_parameters):
        """Execute SQL multiple times."""
        return self._cursor.executemany(sql, seq_of_parameters)

    def __getattr__(self, name):
        """Delegate all other attributes to the wrapped cursor."""
        return getattr(self._cursor, name)


class MonitoredConnection:
    """Connection wrapper that returns monitored cursors."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        """Return a monitored cursor."""
        return MonitoredCursor(self._conn.cursor(), self._conn)

    def __getattr__(self, name):
        """Delegate all other attributes to the wrapped connection."""
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._conn.__exit__(exc_type, exc_val, exc_tb)


def monitored_connect(
    database: str,
    timeout: float = 5.0,
    **kwargs
) -> sqlite3.Connection:
    """
    Create a SQLite connection with visualization monitoring.

    Drop-in replacement for sqlite3.connect() that automatically
    emits visualization events on every database write.

    Args:
        database: Database file path
        timeout: Connection timeout
        **kwargs: Additional arguments passed to sqlite3.connect()

    Returns:
        SQLite connection with monitoring attached

    Example:
        # Instead of:
        conn = sqlite3.connect('db.db')

        # Use:
        from shared.db_monitor import monitored_connect
        conn = monitored_connect('db.db')
    """
    # Create normal connection
    conn = sqlite3.connect(database, timeout=timeout, **kwargs)

    if not ENABLED:
        return conn

    # Start batcher if not running
    _batcher.start()

    # Return wrapped connection
    return MonitoredConnection(conn)


def enable_monitoring():
    """Enable database monitoring (enabled by default)."""
    global ENABLED
    ENABLED = True
    _batcher.start()


def disable_monitoring():
    """Disable database monitoring (for performance testing)."""
    global ENABLED
    ENABLED = False
    _batcher.stop()
