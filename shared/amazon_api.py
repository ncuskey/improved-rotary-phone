"""
Amazon Product Advertising API (PA-API 5.0) client for pricing data.

Fetches current Amazon pricing, sales rank, and availability data for books.
Requires Amazon PA-API credentials (Access Key, Secret Key, Partner Tag).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests


@dataclass
class AmazonPricing:
    """Amazon pricing and market data for a book."""
    isbn: str
    lowest_new_price: Optional[float] = None
    lowest_used_price: Optional[float] = None
    sales_rank: Optional[int] = None
    availability: Optional[str] = None
    offers_count: int = 0
    list_price: Optional[float] = None
    raw: Dict[str, Any] = None

    @property
    def lowest_price(self) -> Optional[float]:
        """Get the absolute lowest price (new or used)."""
        prices = [p for p in [self.lowest_new_price, self.lowest_used_price] if p]
        return min(prices) if prices else None


class AmazonAPIClient:
    """
    Client for Amazon Product Advertising API 5.0.

    Fetches real-time pricing and sales rank data for books.
    Rate limit: 1 request/second with burst of 10 requests.
    """

    BASE_URL = "https://webservices.amazon.com/paapi5/getitems"
    SERVICE = "ProductAdvertisingAPI"
    REGION = "us-east-1"

    def __init__(
        self,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        partner_tag: Optional[str] = None,
        marketplace: str = "www.amazon.com"
    ):
        """
        Initialize Amazon PA-API client.

        Args:
            access_key: AWS Access Key ID (or use AMAZON_ACCESS_KEY env var)
            secret_key: AWS Secret Access Key (or use AMAZON_SECRET_KEY env var)
            partner_tag: Amazon Associate Tag (or use AMAZON_PARTNER_TAG env var)
            marketplace: Amazon marketplace domain (default: www.amazon.com)
        """
        self.access_key = access_key or os.getenv("AMAZON_ACCESS_KEY")
        self.secret_key = secret_key or os.getenv("AMAZON_SECRET_KEY")
        self.partner_tag = partner_tag or os.getenv("AMAZON_PARTNER_TAG")
        self.marketplace = marketplace

        if not all([self.access_key, self.secret_key, self.partner_tag]):
            raise ValueError(
                "Amazon API credentials required. Set AMAZON_ACCESS_KEY, "
                "AMAZON_SECRET_KEY, and AMAZON_PARTNER_TAG environment variables."
            )

    def _create_signature(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        payload: str
    ) -> str:
        """Create AWS Signature Version 4 for PA-API request."""
        # Parse URL components
        host = self.marketplace
        path = "/paapi5/getitems"

        # Create canonical request
        canonical_headers = "\n".join(
            f"{k.lower()}:{v}" for k, v in sorted(headers.items())
        ) + "\n"
        signed_headers = ";".join(sorted(k.lower() for k in headers.keys()))

        payload_hash = hashlib.sha256(payload.encode()).hexdigest()

        canonical_request = f"{method}\n{path}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

        # Create string to sign
        timestamp = headers["X-Amz-Date"]
        date_stamp = timestamp[:8]
        credential_scope = f"{date_stamp}/{self.REGION}/{self.SERVICE}/aws4_request"

        canonical_request_hash = hashlib.sha256(canonical_request.encode()).hexdigest()
        string_to_sign = f"AWS4-HMAC-SHA256\n{timestamp}\n{credential_scope}\n{canonical_request_hash}"

        # Calculate signature
        k_date = hmac.new(
            f"AWS4{self.secret_key}".encode(),
            date_stamp.encode(),
            hashlib.sha256
        ).digest()
        k_region = hmac.new(k_date, self.REGION.encode(), hashlib.sha256).digest()
        k_service = hmac.new(k_region, self.SERVICE.encode(), hashlib.sha256).digest()
        k_signing = hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()

        signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

        return signature

    def get_item_by_isbn(
        self,
        isbn: str,
        resources: Optional[list] = None
    ) -> Optional[AmazonPricing]:
        """
        Fetch pricing and market data for a book by ISBN.

        Args:
            isbn: ISBN-10 or ISBN-13
            resources: List of data resources to request (defaults to pricing + rank)

        Returns:
            AmazonPricing object or None if not found/error
        """
        if resources is None:
            resources = [
                "Offers.Listings.Price",
                "Offers.Listings.Condition",
                "Offers.Summaries.LowestPrice",
                "Offers.Summaries.HighestPrice",
                "ItemInfo.Classifications",
                "BrowseNodeInfo.BrowseNodes.SalesRank"
            ]

        # Prepare request payload
        payload = {
            "ItemIds": [isbn],
            "ItemIdType": "ISBN",
            "Resources": resources,
            "PartnerTag": self.partner_tag,
            "PartnerType": "Associates",
            "Marketplace": self.marketplace
        }

        import json
        payload_str = json.dumps(payload)

        # Prepare headers
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Host": self.marketplace,
            "X-Amz-Date": timestamp,
            "X-Amz-Target": "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.GetItems"
        }

        # Create signature
        signature = self._create_signature("POST", self.BASE_URL, headers, payload_str)

        # Add authorization header
        date_stamp = timestamp[:8]
        credential_scope = f"{date_stamp}/{self.REGION}/{self.SERVICE}/aws4_request"
        signed_headers = ";".join(sorted(k.lower() for k in headers.keys()))

        headers["Authorization"] = (
            f"AWS4-HMAC-SHA256 "
            f"Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

        try:
            response = requests.post(
                self.BASE_URL,
                headers=headers,
                data=payload_str,
                timeout=10
            )

            if response.status_code != 200:
                print(f"Amazon API error: {response.status_code} - {response.text}")
                return None

            data = response.json()
            return self._parse_response(isbn, data)

        except Exception as e:
            print(f"Amazon API request failed: {e}")
            return None

    def _parse_response(self, isbn: str, data: Dict[str, Any]) -> Optional[AmazonPricing]:
        """Parse Amazon PA-API response into AmazonPricing object."""
        try:
            items = data.get("ItemsResult", {}).get("Items", [])
            if not items:
                return None

            item = items[0]

            # Extract pricing
            offers = item.get("Offers", {})
            summaries = offers.get("Summaries", [])

            lowest_new = None
            lowest_used = None
            offers_count = 0

            for summary in summaries:
                condition = summary.get("Condition", {}).get("Value", "")
                price_data = summary.get("LowestPrice", {})

                if price_data:
                    amount = price_data.get("Amount")
                    if amount:
                        price = float(amount)
                        if "New" in condition:
                            lowest_new = price
                        elif "Used" in condition:
                            lowest_used = price

                offers_count += summary.get("OfferCount", 0)

            # Extract list price
            list_price = None
            list_price_data = item.get("ItemInfo", {}).get("TradeInPrice", {}) or \
                             item.get("ItemInfo", {}).get("ManufactureInfo", {}).get("ItemPartNumber", {})
            # Note: List price extraction varies by Amazon's response format

            # Extract sales rank
            sales_rank = None
            browse_nodes = item.get("BrowseNodeInfo", {}).get("BrowseNodes", [])
            for node in browse_nodes:
                if "SalesRank" in node:
                    sales_rank = node["SalesRank"]
                    break

            # Availability
            availability = offers.get("Summaries", [{}])[0].get("Condition", {}).get("Value")

            return AmazonPricing(
                isbn=isbn,
                lowest_new_price=lowest_new,
                lowest_used_price=lowest_used,
                sales_rank=sales_rank,
                availability=availability,
                offers_count=offers_count,
                list_price=list_price,
                raw=data
            )

        except Exception as e:
            print(f"Failed to parse Amazon response: {e}")
            return None


def get_amazon_pricing(isbn: str) -> Optional[AmazonPricing]:
    """
    Convenience function to fetch Amazon pricing for an ISBN.

    Uses environment variables for credentials:
    - AMAZON_ACCESS_KEY
    - AMAZON_SECRET_KEY
    - AMAZON_PARTNER_TAG

    Returns None if credentials not set or request fails.
    """
    try:
        client = AmazonAPIClient()
        return client.get_item_by_isbn(isbn)
    except ValueError:
        # Credentials not set - silently return None
        return None
    except Exception as e:
        print(f"Amazon pricing fetch failed: {e}")
        return None
