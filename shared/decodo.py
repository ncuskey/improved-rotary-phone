"""
Decodo Web Scraping API client for Amazon data collection.

Supports both real-time and asynchronous batch requests via Decodo Core plan.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


DEFAULT_BASE_URL = "https://scraper-api.decodo.com/v2"
DEFAULT_TIMEOUT = 150  # 150s limit for real-time requests
DEFAULT_RATE_LIMIT = 30  # Core plan: 30 req/s


class DecodoAPIError(RuntimeError):
    """Raised when the Decodo API returns an unexpected response."""


@dataclass
class DecodoResponse:
    """Response from Decodo API."""
    status_code: int
    body: str  # HTML content for Core plan
    task_id: Optional[str] = None
    error: Optional[str] = None


class DecodoClient:
    """
    Client for Decodo Web Scraping API (Core Plan).

    Supports:
    - Real-time requests (single URL, 150s timeout)
    - Async batch requests (up to 3000 URLs per batch)
    - Rate limiting (30 req/s for Core plan)
    """

    def __init__(
        self,
        username: str,
        password: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        rate_limit: int = DEFAULT_RATE_LIMIT,
    ):
        """
        Initialize Decodo API client.

        Args:
            username: Decodo API username
            password: Decodo API password
            base_url: Base URL for Decodo API
            timeout: Request timeout in seconds
            rate_limit: Max requests per second (Core: 30)
        """
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.rate_limit = rate_limit

        # Session for connection pooling
        self.session = requests.Session()

        # Basic auth header
        credentials = f"{username}:{password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        self.session.headers.update({
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ISBN-Lot-Optimizer/1.0"
        })

        # Rate limiting
        self._last_request_time = 0.0
        self._min_interval = 1.0 / rate_limit  # seconds between requests

    def _rate_limit(self) -> None:
        """Apply rate limiting delay if needed."""
        now = time.time()
        elapsed = now - self._last_request_time

        if elapsed < self._min_interval:
            sleep_time = self._min_interval - elapsed
            time.sleep(sleep_time)

        self._last_request_time = time.time()

    def scrape_realtime(
        self,
        query: str,
        target: str = "amazon_product",
        domain: str = "com",
        parse: bool = True,
        max_retries: int = 3
    ) -> DecodoResponse:
        """
        Scrape Amazon product in real-time (blocking).

        Args:
            query: ISBN/ASIN to look up
            target: Decodo target (default: amazon_product for Pro plan)
            domain: Amazon domain (default: com for Amazon.com)
            parse: Whether to parse response (default: True)
            max_retries: Number of retry attempts on failure

        Returns:
            DecodoResponse with parsed JSON body

        Raises:
            DecodoAPIError: If request fails after retries
        """
        endpoint = f"{self.base_url}/scrape"
        payload = {
            "target": target,
            "query": query,
            "domain": domain,
            "parse": parse
        }

        for attempt in range(max_retries):
            try:
                self._rate_limit()

                response = self.session.post(
                    endpoint,
                    json=payload,
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    data = response.json()
                    # For Pro plan with parse=True, response has "results" not "body"
                    # Store entire JSON as body for downstream parsing
                    import json
                    return DecodoResponse(
                        status_code=200,
                        body=json.dumps(data) if data else ""
                    )
                elif response.status_code == 429:  # Rate limit
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    raise DecodoAPIError(f"Rate limit exceeded after {max_retries} retries")
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    return DecodoResponse(
                        status_code=response.status_code,
                        body="",
                        error=error_msg
                    )

            except requests.Timeout:
                if attempt < max_retries - 1:
                    continue
                return DecodoResponse(
                    status_code=408,
                    body="",
                    error="Request timeout"
                )
            except requests.RequestException as exc:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                raise DecodoAPIError(f"Request failed: {exc}") from exc

        raise DecodoAPIError(f"Failed after {max_retries} retries")

    def queue_batch(
        self,
        queries: List[str],
        target: str = "amazon_product",
        domain: str = "com",
        parse: bool = True
    ) -> List[str]:
        """
        Queue a batch of ISBN/ASIN queries for asynchronous scraping.

        Args:
            queries: List of ISBNs/ASINs to scrape (max 3000 per batch)
            target: Decodo target (default: amazon_product for Pro plan)
            domain: Amazon domain (default: com)
            parse: Whether to parse response (default: True)

        Returns:
            List of task IDs (one per query)

        Raises:
            DecodoAPIError: If batch submission fails
            ValueError: If queries list is empty or too large
        """
        if not queries:
            raise ValueError("queries list cannot be empty")
        if len(queries) > 3000:
            raise ValueError(f"Batch size {len(queries)} exceeds maximum of 3000")

        endpoint = f"{self.base_url}/task/batch"
        payload = {
            "target": target,
            "queries": queries,  # Use 'queries' for batch with query-based targets
            "domain": domain,
            "parse": parse
        }

        try:
            self._rate_limit()

            response = self.session.post(
                endpoint,
                json=payload,
                timeout=30  # Queueing is fast
            )

            if response.status_code == 200:
                data = response.json()
                task_ids = data.get("task_ids", [])
                if not task_ids:
                    # Fallback: try to parse response structure
                    if isinstance(data, list):
                        task_ids = [item.get("task_id") for item in data if "task_id" in item]
                return task_ids
            else:
                raise DecodoAPIError(
                    f"Batch queue failed: HTTP {response.status_code}: {response.text}"
                )

        except requests.RequestException as exc:
            raise DecodoAPIError(f"Batch queue request failed: {exc}") from exc

    def get_task_result(
        self,
        task_id: str,
        max_retries: int = 3
    ) -> Optional[DecodoResponse]:
        """
        Retrieve result for a queued task.

        Args:
            task_id: Task ID from queue_batch()
            max_retries: Number of retry attempts

        Returns:
            DecodoResponse with HTML body, or None if not ready yet

        Raises:
            DecodoAPIError: If request fails
        """
        endpoint = f"{self.base_url}/task/{task_id}/results"

        for attempt in range(max_retries):
            try:
                self._rate_limit()

                response = self.session.get(
                    endpoint,
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()
                    # Check if task is complete (Pro plan uses "results" not "body")
                    if data and ("body" in data or "results" in data):
                        import json
                        return DecodoResponse(
                            status_code=200,
                            body=json.dumps(data),
                            task_id=task_id
                        )
                    else:
                        # Task not ready yet
                        return None
                elif response.status_code == 404:
                    # Task not found or expired
                    return DecodoResponse(
                        status_code=404,
                        body="",
                        task_id=task_id,
                        error="Task not found (may have expired after 24 hours)"
                    )
                elif response.status_code == 202:
                    # Task still processing
                    return None
                else:
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    return DecodoResponse(
                        status_code=response.status_code,
                        body="",
                        task_id=task_id,
                        error=f"HTTP {response.status_code}: {response.text}"
                    )

            except requests.RequestException as exc:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                raise DecodoAPIError(f"Task result request failed: {exc}") from exc

        raise DecodoAPIError(f"Failed to get task result after {max_retries} retries")

    def poll_batch_results(
        self,
        task_ids: List[str],
        poll_interval: int = 30,
        max_polls: int = 60,
        progress_callback = None
    ) -> Dict[str, DecodoResponse]:
        """
        Poll for batch results until all tasks complete or timeout.

        Args:
            task_ids: List of task IDs to poll
            poll_interval: Seconds between poll attempts
            max_polls: Maximum number of poll attempts
            progress_callback: Optional callback(completed, total) for progress updates

        Returns:
            Dict mapping task_id to DecodoResponse
        """
        results: Dict[str, DecodoResponse] = {}
        pending = set(task_ids)

        for poll_num in range(max_polls):
            if not pending:
                break

            # Check pending tasks
            completed_this_round = []

            for task_id in list(pending):
                result = self.get_task_result(task_id)

                if result is not None:
                    results[task_id] = result
                    completed_this_round.append(task_id)

            # Remove completed tasks
            for task_id in completed_this_round:
                pending.remove(task_id)

            # Progress callback
            if progress_callback:
                progress_callback(len(results), len(task_ids))

            # All done?
            if not pending:
                break

            # Wait before next poll
            if poll_num < max_polls - 1:
                time.sleep(poll_interval)

        # Mark remaining tasks as timeout
        for task_id in pending:
            results[task_id] = DecodoResponse(
                status_code=408,
                body="",
                task_id=task_id,
                error=f"Timeout after {max_polls} polls"
            )

        return results

    def close(self):
        """Close the session."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
