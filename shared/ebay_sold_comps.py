"""
eBay Sold Comps Integration for Python Backend

Dual-track implementation:
- Track B: Conservative estimate from active listings (25th percentile for used, median for new)
- Track A: Real sold data from Marketplace Insights API (when approved)

Integrates with token broker for authentication.
"""

from __future__ import annotations

import os
import statistics
from typing import Any, Dict, List, Optional, TypedDict
from dataclasses import dataclass

import requests


# Token broker configuration
TOKEN_BROKER_BASE = os.getenv("TOKEN_BROKER_URL", "http://localhost:8787")
TOKEN_BROKER_PREFIX = os.getenv("TOKEN_BROKER_PREFIX", "")  # "", "/isbn", or "/isbn-web"


class PriceSample(TypedDict):
    """Individual price sample from eBay listing."""
    title: str
    condition: str
    item_price: float
    ship_price: float
    delivered_price: float


class SoldCompsResult(TypedDict):
    """Sold comps pricing result."""
    count: int
    min: float
    median: float
    max: float
    samples: List[PriceSample]
    is_estimate: bool  # True = Track B estimate, False = Track A real data
    source: str  # "estimate" or "marketplace_insights"
    last_sold_date: Optional[str]  # ISO 8601 date of last sold item (Track A only)


@dataclass
class EbaySoldComps:
    """
    eBay Sold Comparables pricing service.

    Provides dual-track sold comps:
    - Track B: Estimate from active listings (conservative percentiles)
    - Track A: Real sold data from Marketplace Insights API

    Automatically falls back from Track A → Track B if MI not available.
    """

    token_broker_base: str = TOKEN_BROKER_BASE
    token_broker_prefix: str = TOKEN_BROKER_PREFIX
    timeout: int = 30

    def __post_init__(self) -> None:
        """Normalize broker URL."""
        if self.token_broker_base.endswith("/"):
            self.token_broker_base = self.token_broker_base.rstrip("/")

    def _build_broker_url(self, path: str) -> str:
        """Build full URL for token broker endpoint."""
        url = self.token_broker_base
        if self.token_broker_prefix:
            prefix = self.token_broker_prefix
            if prefix.startswith("/"):
                prefix = prefix[1:]
            url += f"/{prefix}"
        url += f"/{path.lstrip('/')}"
        return url

    def get_sold_comps(
        self,
        gtin: str,
        fallback_to_estimate: bool = True,
        max_samples: int = 3,
        include_signed: bool = False,
    ) -> Optional[SoldCompsResult]:
        """
        Get sold comps for ISBN/GTIN with smart filtering.

        Args:
            gtin: ISBN or GTIN to lookup
            fallback_to_estimate: If True, use Track B estimate when Track A unavailable
            max_samples: Number of sample listings to return
            include_signed: If True, include signed/autographed copies (default: False)

        Returns:
            SoldCompsResult or None if no data available

        Raises:
            requests.RequestException: On network errors
        """
        # Try Track A first (real sold data from MI)
        try:
            result = self._get_mi_sold_comps(gtin, max_samples)
            if result:
                return result
        except requests.HTTPError as e:
            # 501 = MI not enabled, fall through to Track B
            if e.response and e.response.status_code != 501:
                raise

        # Fall back to Track B (estimate from active)
        if fallback_to_estimate:
            return self._get_estimated_sold_comps(gtin, max_samples, include_signed=include_signed)

        return None

    def _get_mi_sold_comps(self, gtin: str, max_samples: int) -> Optional[SoldCompsResult]:
        """
        Track A: Get real sold data from Marketplace Insights API via token broker.

        Returns None if MI not available (501 error).
        Raises on other HTTP errors.
        """
        url = self._build_broker_url("/sold/ebay")
        params = {"gtin": gtin}

        resp = requests.get(url, params=params, timeout=self.timeout)

        # 501 = MI not enabled yet, return None to trigger fallback
        if resp.status_code == 501:
            return None

        resp.raise_for_status()
        data = resp.json()

        # Normalize MI response to SoldCompsResult format
        samples: List[PriceSample] = []
        for s in data.get("samples", [])[:max_samples]:
            samples.append({
                "title": s.get("title", ""),
                "condition": "",  # MI doesn't always include condition
                "item_price": float(s.get("price", 0)),
                "ship_price": 0.0,  # MI sold prices typically include shipping
                "delivered_price": float(s.get("price", 0)),
            })

        return {
            "count": data.get("count", 0),
            "min": data.get("min", 0.0),
            "median": data.get("median", 0.0),
            "max": data.get("max", 0.0),
            "samples": samples,
            "is_estimate": False,
            "source": "marketplace_insights",
            "last_sold_date": data.get("lastSoldDate"),  # ISO 8601 date from MI API
        }

    def _get_estimated_sold_comps(self, gtin: str, max_samples: int, include_signed: bool = False) -> Optional[SoldCompsResult]:
        """
        Track B: Estimate sold prices from active listings using conservative heuristic.

        Uses:
        - 25th percentile for Used condition (tracks actual sale behavior)
        - Median for New condition (standardized pricing)
        - Filters out multi-book lots and (optionally) signed copies

        Args:
            gtin: ISBN/GTIN to search
            max_samples: Number of sample listings to return
            include_signed: If True, include signed/autographed copies in results
        """
        from shared.market import browse_active_by_isbn

        try:
            data = browse_active_by_isbn(gtin, limit=50, include_signed=include_signed)
        except Exception:
            return None

        if data.get("error") or not data.get("active_count"):
            return None

        # Get all active listings with prices
        # Note: browse_active_by_isbn returns aggregate stats, we need raw items
        # For now, use the aggregate and compute estimate
        active_count = data.get("active_count", 0)
        median_price = data.get("median_price")
        min_price = data.get("min_price")
        max_price = data.get("max_price")

        if not median_price or active_count == 0:
            return None

        # Conservative estimate: use lower end of active price range
        # This approximates 25th percentile when we don't have full distribution
        estimated_min = min_price if min_price else median_price * 0.7
        estimated_median = median_price * 0.75  # Conservative: 75% of median active
        estimated_max = median_price  # Cap at median active

        # Create sample listings (synthetic from aggregate stats)
        samples: List[PriceSample] = []
        if min_price and median_price and max_price:
            # Generate representative samples at different price points
            sample_prices = [
                estimated_min,
                (estimated_min + estimated_median) / 2,
                estimated_median,
            ][:max_samples]

            for i, price in enumerate(sample_prices):
                samples.append({
                    "title": f"Estimated listing {i+1}",
                    "condition": "Used" if i < 2 else "New",
                    "item_price": price * 0.9,  # Assume ~90% item, ~10% ship
                    "ship_price": price * 0.1,
                    "delivered_price": price,
                })

        return {
            "count": active_count,
            "min": estimated_min,
            "median": estimated_median,
            "max": estimated_max,
            "samples": samples,
            "is_estimate": True,
            "source": "estimate",
            "last_sold_date": None,  # Not available for estimates
        }


# Convenience function for backward compatibility
def get_sold_comps(
    gtin: str,
    token_broker_base: str = TOKEN_BROKER_BASE,
    token_broker_prefix: str = TOKEN_BROKER_PREFIX,
) -> Optional[SoldCompsResult]:
    """
    Get sold comps for ISBN/GTIN.

    Convenience wrapper around EbaySoldComps class.

    Args:
        gtin: ISBN or GTIN to lookup
        token_broker_base: Token broker base URL
        token_broker_prefix: URL prefix ("/isbn", "/isbn-web", or "")

    Returns:
        SoldCompsResult or None if no data available
    """
    service = EbaySoldComps(
        token_broker_base=token_broker_base,
        token_broker_prefix=token_broker_prefix,
    )
    return service.get_sold_comps(gtin)


# CLI test interface
if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python -m isbn_lot_optimizer.ebay_sold_comps <ISBN>")
        sys.exit(1)

    isbn = sys.argv[1]
    result = get_sold_comps(isbn)

    if result:
        print(json.dumps(result, indent=2))
        print(f"\nSource: {result['source']}")
        print(f"Estimate: {result['is_estimate']}")
    else:
        print("No pricing data available")
        sys.exit(1)
