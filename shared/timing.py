"""Performance timing utilities for identifying bottlenecks."""
from __future__ import annotations

import functools
import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Optional

logger = logging.getLogger("isbn_lot_optimizer.timing")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("⏱️  %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False


class TimingStats:
    """Collects and displays timing statistics."""

    def __init__(self):
        self.timings: list[tuple[str, float]] = []
        self.start_time: Optional[float] = None

    def start(self) -> None:
        """Start timing collection."""
        self.timings = []
        self.start_time = time.time()

    def record(self, label: str, duration: float) -> None:
        """Record a timing."""
        self.timings.append((label, duration))

    def report(self) -> str:
        """Generate a timing report."""
        if not self.timings:
            return "No timings recorded"

        total = sum(d for _, d in self.timings)
        lines = [
            "=" * 70,
            "PERFORMANCE TIMING REPORT",
            "=" * 70,
        ]

        for label, duration in sorted(self.timings, key=lambda x: x[1], reverse=True):
            pct = (duration / total * 100) if total > 0 else 0
            lines.append(f"  {duration:6.2f}s ({pct:5.1f}%)  {label}")

        lines.append("-" * 70)
        lines.append(f"  {total:6.2f}s (100.0%)  TOTAL")

        if self.start_time:
            elapsed = time.time() - self.start_time
            lines.append(f"  {elapsed:6.2f}s          Wall clock time")

        lines.append("=" * 70)
        return "\n".join(lines)


# Global timing stats instance
_stats = TimingStats()


def get_stats() -> TimingStats:
    """Get the global timing stats instance."""
    return _stats


@contextmanager
def timer(label: str, *, log: bool = True, record: bool = True):
    """
    Context manager for timing a block of code.

    Usage:
        with timer("API call to eBay"):
            result = fetch_ebay_data()
    """
    start = time.time()
    try:
        yield
    finally:
        duration = time.time() - start
        if log:
            logger.info(f"{label}: {duration:.2f}s")
        if record:
            _stats.record(label, duration)


def timed(label: Optional[str] = None, *, log: bool = True, record: bool = True):
    """
    Decorator for timing function execution.

    Usage:
        @timed("My slow function")
        def process_data():
            ...
    """
    def decorator(func: Callable) -> Callable:
        func_label = label or f"{func.__module__}.{func.__name__}"

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            with timer(func_label, log=log, record=record):
                return func(*args, **kwargs)
        return wrapper
    return decorator


def log_timing(label: str, duration: float) -> None:
    """Log a manual timing measurement."""
    logger.info(f"{label}: {duration:.2f}s")
    _stats.record(label, duration)
