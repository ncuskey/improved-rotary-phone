import os
import time
import json
import threading
from typing import Any, Dict, Optional, List
from urllib import request as urlrequest, error as urlerror


HARDCOVER_GRAPHQL_ENDPOINT = "https://api.hardcover.app/v1/graphql"
HARDCOVER_API_TOKEN = os.environ.get("HARDCOVER_API_TOKEN", "").strip()


class _RateLimiter:
    """
    Simple token-bucket rate limiter.
    Default: 1 req/sec with burst capacity 5.
    """

    def __init__(self, rate_per_sec: float = 1.0, burst: int = 5):
        self.tokens = burst
        self.capacity = burst
        self.rate = rate_per_sec
        self.lock = threading.Lock()
        self.last_refill = time.monotonic()

    def acquire(self):
        """
        Block until a token is available without holding the lock during sleep.
        Avoid recursion and ensure the lock isn't held across sleep to prevent deadlocks.
        """
        while True:
            now = time.monotonic()
            with self.lock:
                elapsed = now - self.last_refill
                refill = elapsed * self.rate
                if refill >= 1:
                    self.tokens = min(self.capacity, self.tokens + int(refill))
                    self.last_refill = now
                if self.tokens > 0:
                    self.tokens -= 1
                    return
                # compute wait outside lock
                wait = max(1.0 / self.rate, 0.1)
            time.sleep(wait)


_limiter = _RateLimiter(rate_per_sec=1.0, burst=5)


class HardcoverClient:
    def __init__(
        self,
        endpoint: str = HARDCOVER_GRAPHQL_ENDPOINT,
        token: Optional[str] = None,
        user_agent: str = "LotHelper/SeriesResolver",
    ):
        self.endpoint = endpoint
        self.token = token or HARDCOVER_API_TOKEN
        if not self.token:
            raise RuntimeError("HARDCOVER_API_TOKEN missing. Set env var before using HardcoverClient.")
        self.user_agent = user_agent

    def _post(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        _limiter.acquire()
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.token}",  # Hardcover API requires "Bearer " prefix
            "user-agent": self.user_agent,
        }
        payload = {"query": query, "variables": variables or {}}
        body = json.dumps(payload).encode("utf-8")
        for attempt in range(3):
            req = urlrequest.Request(self.endpoint, data=body, headers=headers, method="POST")
            try:
                with urlrequest.urlopen(req, timeout=30) as resp:
                    resp_text = resp.read().decode("utf-8")
            except urlerror.HTTPError as e:
                if getattr(e, "code", None) == 429:
                    time.sleep(2 + attempt)  # backoff on throttle
                    continue
                err_text = ""
                try:
                    err_text = e.read().decode("utf-8", errors="ignore")  # type: ignore[attr-defined]
                except Exception:
                    pass
                raise RuntimeError(f"Hardcover HTTP {getattr(e, 'code', 'error')}: {err_text[:200]}")
            except urlerror.URLError as e:
                raise RuntimeError(f"Hardcover network error: {e}")
            try:
                data = json.loads(resp_text)
            except Exception:
                raise RuntimeError(f"Hardcover invalid JSON response: {resp_text[:200]}")
            if "errors" in data and data["errors"]:
                # Surface first error
                raise RuntimeError(f"Hardcover GraphQL error: {data['errors']}")
            return data
        raise RuntimeError("Hardcover request failed after retries")

    # search Book by ISBN (per_page=1)
    def find_book_by_isbn(self, isbn: str) -> Dict[str, Any]:
        query = """
        query FindBookByIsbn($q: String!, $queryType: String!, $pp: Int!, $page: Int!) {
          search(query: $q, query_type: $queryType, per_page: $pp, page: $page) {
            ids
            query_type
            page
            per_page
            results
          }
        }
        """
        variables = {"q": isbn, "queryType": "book", "pp": 1, "page": 1}
        return self._post(query, variables)

    # search Series by name or slug; depending on index, books may not be embedded
    def search_series(self, name_or_slug: str, per_page: int = 50, page: int = 1) -> Dict[str, Any]:
        query = """
        query SeriesSearch($q: String!, $queryType: String!, $pp: Int!, $page: Int!) {
          search(query: $q, query_type: $queryType, per_page: $pp, page: $page) {
            ids
            query_type
            page
            per_page
            results
          }
        }
        """
        variables = {"q": name_or_slug, "queryType": "series", "pp": per_page, "page": page}
        return self._post(query, variables)

    # fallback: pull books by series name as Book search, then filter client-side to the target series
    def search_books_by_series_name(self, series_name: str, per_page: int = 50, page: int = 1) -> Dict[str, Any]:
        query = """
        query BooksBySeriesName($q: String!, $queryType: String!, $pp: Int!, $page: Int!) {
          search(query: $q, query_type: $queryType, per_page: $pp, page: $page) {
            ids
            query_type
            page
            per_page
            results
          }
        }
        """
        variables = {"q": series_name, "queryType": "book", "pp": per_page, "page": page}
        return self._post(query, variables)

    # helpers to parse the known shapes
    @staticmethod
    def parse_book_hit(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            # The 'results' field from GraphQL is a JSON string containing Typesense response
            results_str = data.get("data", {}).get("search", {}).get("results")
            if not results_str:
                return None

            # Parse the JSON string
            results = json.loads(results_str) if isinstance(results_str, str) else results_str

            # Typesense returns: {found, hits: [{document: {...}, ...}], ...}
            hits = results.get("hits", [])
            if not hits:
                return None

            doc = hits[0].get("document", {})

            # Extract series information from series_names array
            series_names = doc.get("series_names", [])
            series_name = series_names[0] if series_names else None

            # Try to extract position from title if it contains series info
            # (Typesense doesn't return structured series data in basic search)
            series_position = None

            return {
                "title": doc.get("title"),
                "authors": doc.get("author_names", []),
                "isbns": doc.get("isbns", []),
                "slug": doc.get("slug"),
                "series_name": series_name,
                "series_slug": None,  # Not available in Typesense search
                "series_id_hc": None,  # Not available in Typesense search
                "series_position": series_position,
            }
        except Exception as e:
            return None

    @staticmethod
    def parse_book_hits_for_series_peers(data: Dict[str, Any], target_series_name: str) -> List[Dict[str, Any]]:
        def norm(s: Optional[str]) -> str:
            return " ".join((s or "").lower().split())

        want = norm(target_series_name)
        try:
            # Parse Typesense results JSON
            results_str = data.get("data", {}).get("search", {}).get("results")
            if not results_str:
                return []

            results = json.loads(results_str) if isinstance(results_str, str) else results_str
            hits = results.get("hits", [])
        except Exception:
            hits = []

        peers: List[Dict[str, Any]] = []
        for h in hits:
            doc = h.get("document", {})

            # Check series_names array for matching series
            names = doc.get("series_names", [])
            sname = next((n for n in names if norm(n) == want), None)

            if not sname or norm(sname) != want:
                continue

            # Position not available in Typesense search - would need separate query
            pos = None

            # prefer ISBN-13
            isbns_list = doc.get("isbns", [])
            isbn13s = [x for x in isbns_list if isinstance(x, str) and len(x) == 13]

            peers.append(
                {
                    "title": doc.get("title"),
                    "authors": doc.get("author_names", []),
                    "isbn13s": isbn13s,
                    "position": pos,
                    "slug": doc.get("slug"),
                }
            )

        # sort peers by title since position not available
        if peers:
            peers.sort(key=lambda p: (p.get("title") or "").lower())

        return peers
