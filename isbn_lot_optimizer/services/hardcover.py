import os
import time
import json
import threading
from typing import Any, Dict, Optional, List
import requests


HARDCOVER_GRAPHQL_ENDPOINT = "https://api.hardcover.app/graphql"
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
            "authorization": self.token,
            "user-agent": self.user_agent,
        }
        payload = {"query": query, "variables": variables or {}}
        for attempt in range(3):
            resp = requests.post(self.endpoint, headers=headers, data=json.dumps(payload), timeout=30)
            if resp.status_code == 429:
                time.sleep(2 + attempt)  # backoff on throttle
                continue
            if not resp.ok:
                raise RuntimeError(f"Hardcover HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            if "errors" in data and data["errors"]:
                # Surface first error
                raise RuntimeError(f"Hardcover GraphQL error: {data['errors']}")
            return data
        raise RuntimeError("Hardcover request failed after retries")

    # search Book by ISBN (per_page=1)
    def find_book_by_isbn(self, isbn: str) -> Dict[str, Any]:
        query = """
        query FindBookByIsbn($q: String!, $pp: Int!, $page: Int!) {
          search(query: $q, query_type: "Book", per_page: $pp, page: $page) {
            results {
              found
              page
              out_of
              hits {
                document {
                  title
                  author_names
                  isbns
                  slug
                  series_names
                  featured_series {
                    details
                    position
                    unreleased
                    id
                    series {
                      id
                      name
                      slug
                      books_count
                      primary_books_count
                    }
                  }
                }
              }
            }
            ids
            query_type
          }
        }
        """
        variables = {"q": isbn, "pp": 1, "page": 1}
        return self._post(query, variables)

    # search Series by name or slug; depending on index, books may not be embedded
    def search_series(self, name_or_slug: str, per_page: int = 50, page: int = 1) -> Dict[str, Any]:
        query = """
        query SeriesSearch($q: String!, $pp: Int!, $page: Int!) {
          search(query: $q, query_type: "Series", per_page: $pp, page: $page) {
            results {
              found
              page
              out_of
              hits {
                document {
                  id
                  name
                  slug
                  books_count
                  primary_books_count
                }
              }
            }
            query_type
          }
        }
        """
        variables = {"q": name_or_slug, "pp": per_page, "page": page}
        return self._post(query, variables)

    # fallback: pull books by series name as Book search, then filter client-side to the target series
    def search_books_by_series_name(self, series_name: str, per_page: int = 50, page: int = 1) -> Dict[str, Any]:
        query = """
        query BooksBySeriesName($q: String!, $pp: Int!, $page: Int!) {
          search(query: $q, query_type: "Book", per_page: $pp, page: $page) {
            results {
              found
              page
              out_of
              hits {
                document {
                  title
                  author_names
                  isbns
                  slug
                  series_names
                  featured_series {
                    details
                    position
                    series { id name slug }
                  }
                }
              }
            }
            query_type
          }
        }
        """
        variables = {"q": series_name, "pp": per_page, "page": page}
        return self._post(query, variables)

    # helpers to parse the known shapes
    @staticmethod
    def parse_book_hit(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            hits = data["data"]["search"]["results"]["hits"]
            if not hits:
                return None
            doc = hits[0]["document"]
            featured = doc.get("featured_series") or {}
            series_obj = (featured.get("series") or {}) if isinstance(featured, dict) else {}
            pos_raw = None
            if isinstance(featured, dict):
                pos_raw = featured.get("position") or featured.get("details")
            try:
                pos = float(pos_raw) if pos_raw is not None else None
            except Exception:
                pos = None
            series_names = doc.get("series_names") or []
            series_name = series_obj.get("name") or (series_names[0] if series_names else None)
            return {
                "title": doc.get("title"),
                "authors": doc.get("author_names") or [],
                "isbns": doc.get("isbns") or [],
                "slug": doc.get("slug"),
                "series_name": series_name,
                "series_slug": series_obj.get("slug"),
                "series_id_hc": series_obj.get("id"),
                "series_position": pos,
            }
        except Exception:
            return None

    @staticmethod
    def parse_book_hits_for_series_peers(data: Dict[str, Any], target_series_name: str) -> List[Dict[str, Any]]:
        def norm(s: Optional[str]) -> str:
            return " ".join((s or "").lower().split())

        want = norm(target_series_name)
        try:
            hits = data["data"]["search"]["results"]["hits"] or []
        except Exception:
            hits = []
        peers: List[Dict[str, Any]] = []
        for h in hits:
            doc = h.get("document") or {}
            fs = doc.get("featured_series") or {}
            sname = None
            if isinstance(fs, dict):
                sname = (fs.get("series") or {}).get("name")
            if not sname:
                # fall back to series_names array
                names = doc.get("series_names") or []
                sname = next((n for n in names if norm(n) == want), None)
            if not sname or norm(sname) != want:
                continue
            pos_raw = fs.get("position") if isinstance(fs, dict) else None
            if pos_raw is None and isinstance(fs, dict):
                pos_raw = fs.get("details")
            try:
                pos = float(pos_raw) if pos_raw is not None else None
            except Exception:
                pos = None
            # prefer ISBN-13
            isbns_list = doc.get("isbns") or []
            isbn13s = [x for x in isbns_list if isinstance(x, str) and len(x) == 13]
            peers.append(
                {
                    "title": doc.get("title"),
                    "authors": doc.get("author_names") or [],
                    "isbn13s": isbn13s,
                    "position": pos,
                    "slug": doc.get("slug"),
                }
            )
        # sort peers
        if peers:
            have_ord = sum(1 for p in peers if isinstance(p.get("position"), (int, float))) >= int(0.7 * len(peers))
            if have_ord:
                peers.sort(key=lambda p: (p.get("position") is None, p.get("position")))
            else:
                peers.sort(key=lambda p: (p.get("title") or "").lower())
        return peers
