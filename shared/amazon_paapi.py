"""
Amazon Product Advertising API (PA-API) client.

Free alternative to Decodo for Amazon data collection.

Features:
- ISBN-10 and ISBN-13 lookup
- Automatic retry with exponential backoff
- Rate limiting (1 req/sec for free tier)
- Structured JSON response
- Extracts all ML-relevant features

Requirements:
- Amazon Associates account
- PA-API credentials (Access Key, Secret Key, Associate Tag)
- amazon-paapi package: pip install amazon-paapi
"""

import os
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

try:
    from amazon.paapi import AmazonAPI
except ImportError:
    print("❌ Error: amazon-paapi package not installed")
    print("Install with: pip install amazon-paapi")
    raise


class AmazonPAAPIClient:
    """
    Client for Amazon Product Advertising API.

    Free tier limits:
    - 1 request per second
    - 8,640 requests per day
    """

    def __init__(
        self,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        associate_tag: Optional[str] = None,
        region: str = "us-east-1"
    ):
        """
        Initialize PA-API client.

        Args:
            access_key: AWS Access Key ID (or use env: AMAZON_ACCESS_KEY)
            secret_key: AWS Secret Access Key (or use env: AMAZON_SECRET_KEY)
            associate_tag: Amazon Associate Tag (or use env: AMAZON_ASSOCIATE_TAG)
            region: AWS region (default: us-east-1 for Amazon.com)
        """
        self.access_key = access_key or os.getenv("AMAZON_ACCESS_KEY")
        self.secret_key = secret_key or os.getenv("AMAZON_SECRET_KEY")
        self.associate_tag = associate_tag or os.getenv("AMAZON_ASSOCIATE_TAG")
        self.region = region

        if not all([self.access_key, self.secret_key, self.associate_tag]):
            raise ValueError(
                "Missing PA-API credentials. Set AMAZON_ACCESS_KEY, "
                "AMAZON_SECRET_KEY, and AMAZON_ASSOCIATE_TAG in environment or .env"
            )

        # Initialize API client
        self.api = AmazonAPI(
            access_key=self.access_key,
            secret_key=self.secret_key,
            tag=self.associate_tag,
            region=self.region.upper().replace("-", "_"),  # US_EAST_1 format
        )

        # Rate limiting
        self._last_request_time = 0.0
        self._min_interval = 1.0  # 1 request per second

    def _rate_limit(self) -> None:
        """Apply rate limiting (1 req/sec for free tier)."""
        now = time.time()
        elapsed = now - self._last_request_time

        if elapsed < self._min_interval:
            sleep_time = self._min_interval - elapsed
            time.sleep(sleep_time)

        self._last_request_time = time.time()

    def lookup_isbn(
        self,
        isbn: str,
        max_retries: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Look up book by ISBN using PA-API.

        Args:
            isbn: ISBN-10 or ISBN-13
            max_retries: Number of retry attempts

        Returns:
            Dict with book data, or None if not found

        Raises:
            Exception: If API request fails after retries
        """
        # Clean ISBN
        isbn_clean = isbn.strip().replace("-", "").replace(" ", "")

        for attempt in range(max_retries):
            try:
                self._rate_limit()

                # Search by ISBN using GetItems
                response = self.api.get_items(
                    item_ids=[isbn_clean],
                    resources=[
                        "ItemInfo.Title",
                        "ItemInfo.ByLineInfo",
                        "ItemInfo.ContentInfo",
                        "ItemInfo.Classifications",
                        "ItemInfo.ProductInfo",
                        "Offers.Listings.Price",
                        "Images.Primary.Large",
                    ]
                )

                if not response or not hasattr(response, 'items') or not response.items:
                    # Try alternate ISBN format (ISBN-10 <-> ISBN-13)
                    if len(isbn_clean) == 13 and attempt == 0:
                        # Try ISBN-10
                        isbn_10 = self._convert_isbn13_to_isbn10(isbn_clean)
                        if isbn_10:
                            return self.lookup_isbn(isbn_10, max_retries=max_retries-1)
                    return None

                # Extract data from first item
                item = response.items[0]
                return self._parse_item(item)

            except Exception as e:
                if "TooManyRequests" in str(e):
                    # Rate limit hit, wait longer
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) * 2  # Exponential backoff
                        time.sleep(wait_time)
                        continue
                elif "ItemNotAccessible" in str(e):
                    # Item exists but not accessible via PA-API
                    return None
                elif attempt < max_retries - 1:
                    # Other error, retry
                    time.sleep(1)
                    continue
                else:
                    # Final attempt failed
                    raise

        return None

    def _parse_item(self, item) -> Dict[str, Any]:
        """
        Parse PA-API item response into standardized format.

        Args:
            item: PA-API item object

        Returns:
            Dict with extracted book data
        """
        data = {
            "asin": None,
            "title": None,
            "authors": None,
            "publisher": None,
            "publication_date": None,
            "binding": None,
            "page_count": None,
            "amazon_sales_rank": None,
            "amazon_lowest_price": None,
            "amazon_rating": None,
            "amazon_ratings_count": None,
            "isbn_10": None,
            "isbn_13": None,
            "image_url": None,
            "fetched_at": datetime.now().isoformat()
        }

        # ASIN
        if hasattr(item, 'asin'):
            data["asin"] = item.asin

        # Title
        if hasattr(item, 'item_info') and hasattr(item.item_info, 'title'):
            if hasattr(item.item_info.title, 'display_value'):
                data["title"] = item.item_info.title.display_value

        # Authors
        if hasattr(item, 'item_info') and hasattr(item.item_info, 'by_line_info'):
            if hasattr(item.item_info.by_line_info, 'contributors'):
                contributors = item.item_info.by_line_info.contributors
                if contributors:
                    authors = [c.name for c in contributors if hasattr(c, 'name')]
                    if authors:
                        data["authors"] = "; ".join(authors)

        # Publisher and publication date
        if hasattr(item, 'item_info') and hasattr(item.item_info, 'content_info'):
            if hasattr(item.item_info.content_info, 'publication_date'):
                pub_date = item.item_info.content_info.publication_date
                if hasattr(pub_date, 'display_value'):
                    data["publication_date"] = pub_date.display_value

        # Binding
        if hasattr(item, 'item_info') and hasattr(item.item_info, 'classifications'):
            if hasattr(item.item_info.classifications, 'binding'):
                if hasattr(item.item_info.classifications.binding, 'display_value'):
                    data["binding"] = item.item_info.classifications.binding.display_value

        # Page count
        if hasattr(item, 'item_info') and hasattr(item.item_info, 'content_info'):
            if hasattr(item.item_info.content_info, 'pages_count'):
                if hasattr(item.item_info.content_info.pages_count, 'display_value'):
                    data["page_count"] = int(item.item_info.content_info.pages_count.display_value)

        # Sales rank (browse node rank)
        if hasattr(item, 'browse_node_info') and hasattr(item.browse_node_info, 'website_sales_rank'):
            rank_info = item.browse_node_info.website_sales_rank
            if hasattr(rank_info, 'sales_rank'):
                data["amazon_sales_rank"] = rank_info.sales_rank

        # Price
        if hasattr(item, 'offers') and hasattr(item.offers, 'listings'):
            if item.offers.listings and len(item.offers.listings) > 0:
                listing = item.offers.listings[0]
                if hasattr(listing, 'price') and hasattr(listing.price, 'amount'):
                    data["amazon_lowest_price"] = listing.price.amount

        # Customer reviews (PA-API v5 doesn't directly provide this, would need separate lookup)
        # For now, leave as None - can be added with additional API call if needed

        # ISBNs
        if hasattr(item, 'item_info') and hasattr(item.item_info, 'external_ids'):
            ext_ids = item.item_info.external_ids
            if hasattr(ext_ids, 'isbns'):
                isbns = ext_ids.isbns
                if hasattr(isbns, 'display_values') and isbns.display_values:
                    for isbn_val in isbns.display_values:
                        if len(isbn_val) == 10:
                            data["isbn_10"] = isbn_val
                        elif len(isbn_val) == 13:
                            data["isbn_13"] = isbn_val

        # Image
        if hasattr(item, 'images') and hasattr(item.images, 'primary'):
            if hasattr(item.images.primary, 'large'):
                if hasattr(item.images.primary.large, 'url'):
                    data["image_url"] = item.images.primary.large.url

        return data

    @staticmethod
    def _convert_isbn13_to_isbn10(isbn13: str) -> Optional[str]:
        """Convert ISBN-13 to ISBN-10."""
        if not isbn13 or len(isbn13) != 13:
            return None

        # ISBN-10 is the middle 9 digits of ISBN-13, plus a check digit
        if not isbn13.startswith("978"):
            return None

        base = isbn13[3:12]

        # Calculate check digit
        check_sum = sum((10 - i) * int(digit) for i, digit in enumerate(base))
        check_digit = (11 - (check_sum % 11)) % 11

        if check_digit == 10:
            check_digit = "X"
        else:
            check_digit = str(check_digit)

        return base + check_digit


def fetch_amazon_data(isbn: str) -> Dict[str, Any]:
    """
    Fetch Amazon data for a single ISBN using PA-API.

    Args:
        isbn: ISBN-10 or ISBN-13

    Returns:
        Dict with Amazon book data and ML features
    """
    client = AmazonPAAPIClient()

    try:
        data = client.lookup_isbn(isbn)

        if not data:
            return {
                "error": "ISBN not found in Amazon catalog",
                "fetched_at": datetime.now().isoformat()
            }

        # Extract ML features
        ml_features = {
            "amazon_sales_rank": data.get("amazon_sales_rank"),
            "amazon_lowest_price": data.get("amazon_lowest_price"),
            "amazon_rating": data.get("amazon_rating"),
            "amazon_ratings_count": data.get("amazon_ratings_count"),
            "page_count": data.get("page_count"),
            "published_year": None,
        }

        # Extract year from publication_date
        if data.get("publication_date"):
            pub_date = data["publication_date"]
            # Try to extract 4-digit year
            import re
            year_match = re.search(r'\b(19|20)\d{2}\b', pub_date)
            if year_match:
                ml_features["published_year"] = int(year_match.group(0))

        data["ml_features"] = ml_features

        return data

    except Exception as e:
        return {
            "error": str(e),
            "fetched_at": datetime.now().isoformat()
        }


def fetch_amazon_bulk(isbns: List[str], progress_callback=None) -> Dict[str, Dict[str, Any]]:
    """
    Fetch Amazon data for multiple ISBNs using PA-API.

    Note: Rate limited to 1 req/sec (free tier), so 100 ISBNs = ~100 seconds.

    Args:
        isbns: List of ISBNs
        progress_callback: Optional callback(current, total)

    Returns:
        Dict mapping ISBN -> data
    """
    results = {}
    total = len(isbns)

    client = AmazonPAAPIClient()

    for i, isbn in enumerate(isbns, 1):
        try:
            data = client.lookup_isbn(isbn)

            if data:
                # Extract ML features
                ml_features = {
                    "amazon_sales_rank": data.get("amazon_sales_rank"),
                    "amazon_lowest_price": data.get("amazon_lowest_price"),
                    "amazon_rating": data.get("amazon_rating"),
                    "amazon_ratings_count": data.get("amazon_ratings_count"),
                    "page_count": data.get("page_count"),
                    "published_year": None,
                }

                # Extract year
                if data.get("publication_date"):
                    import re
                    year_match = re.search(r'\b(19|20)\d{2}\b', data["publication_date"])
                    if year_match:
                        ml_features["published_year"] = int(year_match.group(0))

                data["ml_features"] = ml_features

            results[isbn] = data or {"error": "Not found"}

            if progress_callback:
                progress_callback(i, total)
            elif i % 10 == 0:
                print(f"  Progress: {i}/{total} ISBNs")

        except Exception as e:
            results[isbn] = {"error": str(e)}

    return results


if __name__ == "__main__":
    # Test
    import sys
    from pathlib import Path

    # Load .env
    env_file = Path(__file__).parent.parent / '.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value.strip('"').strip("'")

    print("Testing Amazon PA-API")
    print("=" * 80)

    test_isbn = "9780553381702"  # A Game of Thrones
    print(f"Looking up ISBN: {test_isbn}")
    print()

    try:
        data = fetch_amazon_data(test_isbn)

        if "error" in data:
            print(f"❌ Error: {data['error']}")
        else:
            print("✓ Success!")
            print(f"  Title: {data.get('title')}")
            print(f"  Authors: {data.get('authors')}")
            print(f"  ASIN: {data.get('asin')}")
            print(f"  Sales Rank: {data.get('amazon_sales_rank')}")
            print(f"  Price: ${data.get('amazon_lowest_price', 0):.2f}")
            print(f"  Page Count: {data.get('page_count')}")
            print(f"  Binding: {data.get('binding')}")
            print()
            print("ML Features:")
            for key, value in data.get('ml_features', {}).items():
                print(f"  {key}: {value}")

    except Exception as e:
        print(f"❌ Error: {e}")
        print()
        print("Make sure you have:")
        print("  1. Installed: pip install amazon-paapi")
        print("  2. Set credentials in .env:")
        print("     AMAZON_ACCESS_KEY=...")
        print("     AMAZON_SECRET_KEY=...")
        print("     AMAZON_ASSOCIATE_TAG=...")
