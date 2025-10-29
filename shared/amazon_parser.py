"""
Amazon HTML parser for extracting book data from scraped pages.

Parses Amazon product pages to extract sales rank, pricing, ratings, and metadata.
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Any
from bs4 import BeautifulSoup


class AmazonParseError(RuntimeError):
    """Raised when Amazon HTML parsing fails."""


def parse_amazon_html(html: str, isbn: str = None) -> Dict[str, Any]:
    """
    Parse Amazon product page HTML and extract book data.

    Args:
        html: Raw HTML from Amazon product page
        isbn: Optional ISBN for context in error messages

    Returns:
        Dict with extracted fields compatible with BookScouterResult format:
        - amazon_sales_rank: int (Best Sellers Rank)
        - amazon_count: int (number of sellers)
        - amazon_lowest_price: float (lowest available price)
        - amazon_list_price: float (official list price)
        - amazon_rating: float (average rating)
        - amazon_ratings_count: int (total reviews)
        - page_count: int
        - publisher: str
        - publication_date: str

    Raises:
        AmazonParseError: If HTML is invalid or critical fields missing
    """
    if not html or len(html) < 100:
        raise AmazonParseError(f"HTML too short or empty for ISBN {isbn}")

    soup = BeautifulSoup(html, "lxml")

    # Check if page is valid Amazon product page
    if "Robot Check" in html or "Type the characters you see in this picture" in html:
        raise AmazonParseError(f"Bot detection triggered for ISBN {isbn}")

    if "Page Not Found" in html or "404" in html:
        raise AmazonParseError(f"Amazon page not found for ISBN {isbn}")

    result = {
        "amazon_sales_rank": None,
        "amazon_count": None,
        "amazon_lowest_price": None,
        "amazon_list_price": None,
        "amazon_rating": None,
        "amazon_ratings_count": None,
        "page_count": None,
        "publisher": None,
        "publication_date": None,
    }

    # Parse sales rank (BSR)
    result["amazon_sales_rank"] = _parse_sales_rank(soup)

    # Parse seller count and prices
    seller_info = _parse_seller_info(soup)
    result["amazon_count"] = seller_info.get("count")
    result["amazon_lowest_price"] = seller_info.get("lowest_price")

    # Parse list price
    result["amazon_list_price"] = _parse_list_price(soup)

    # Parse ratings
    rating_info = _parse_ratings(soup)
    result["amazon_rating"] = rating_info.get("rating")
    result["amazon_ratings_count"] = rating_info.get("count")

    # Parse product details
    details = _parse_product_details(soup)
    result["page_count"] = details.get("page_count")
    result["publisher"] = details.get("publisher")
    result["publication_date"] = details.get("publication_date")

    return result


def _parse_sales_rank(soup: BeautifulSoup) -> Optional[int]:
    """
    Extract Best Sellers Rank from HTML.

    Looks for patterns like:
    - "#123,456 in Books"
    - "Best Sellers Rank: #789 in Kindle Store"
    """
    # Strategy 1: Look for "Best Sellers Rank" label
    rank_patterns = [
        r"#([\d,]+)\s+in\s+(?:Books|Kindle Store)",
        r"Best Sellers Rank:\s*#([\d,]+)",
        r"Amazon Best Sellers Rank:\s*#([\d,]+)",
    ]

    for pattern in rank_patterns:
        matches = re.findall(pattern, soup.get_text(), re.IGNORECASE)
        if matches:
            # Take first match, remove commas
            rank_str = matches[0].replace(",", "")
            try:
                return int(rank_str)
            except ValueError:
                continue

    # Strategy 2: Look for <span> or <li> with "Best Sellers Rank"
    bsr_elements = soup.find_all(string=re.compile(r"Best Sellers Rank", re.IGNORECASE))
    for elem in bsr_elements:
        # Check parent and siblings for rank number
        parent = elem.find_parent()
        if parent:
            text = parent.get_text()
            match = re.search(r"#([\d,]+)", text)
            if match:
                rank_str = match.group(1).replace(",", "")
                try:
                    return int(rank_str)
                except ValueError:
                    continue

    return None


def _parse_seller_info(soup: BeautifulSoup) -> Dict[str, Optional[Any]]:
    """
    Extract seller count and lowest price.

    Looks for patterns like:
    - "45 used from $5.99"
    - "10 new from $12.95"
    - "Other sellers on Amazon"
    """
    seller_info = {
        "count": None,
        "lowest_price": None
    }

    # Strategy 1: Look for "X new/used from $Y" patterns
    price_patterns = [
        r"(\d+)\s+(?:new|used)\s+from\s+\$([0-9.]+)",
        r"(\d+)\s+seller[s]?\s+from\s+\$([0-9.]+)",
    ]

    text = soup.get_text()
    for pattern in price_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            # Take first match (usually "new" comes before "used")
            count_str, price_str = matches[0]
            try:
                seller_info["count"] = int(count_str)
                seller_info["lowest_price"] = float(price_str)
                break
            except ValueError:
                continue

    # Strategy 2: Look for price in specific elements
    if seller_info["lowest_price"] is None:
        # Check for kindle/digital price
        price_elements = soup.find_all("span", class_=re.compile(r"price", re.IGNORECASE))
        for elem in price_elements:
            price_text = elem.get_text().strip()
            match = re.search(r"\$([0-9.]+)", price_text)
            if match:
                try:
                    seller_info["lowest_price"] = float(match.group(1))
                    break
                except ValueError:
                    continue

    return seller_info


def _parse_list_price(soup: BeautifulSoup) -> Optional[float]:
    """Extract official list price."""
    # Look for "List Price: $XX.XX" or strikethrough prices
    list_price_patterns = [
        r"List Price:\s*\$([0-9.]+)",
        r"Was:\s*\$([0-9.]+)",
    ]

    text = soup.get_text()
    for pattern in list_price_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue

    # Check for strikethrough price elements
    strike_elements = soup.find_all(["s", "del", "strike"])
    for elem in strike_elements:
        price_text = elem.get_text().strip()
        match = re.search(r"\$([0-9.]+)", price_text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue

    return None


def _parse_ratings(soup: BeautifulSoup) -> Dict[str, Optional[Any]]:
    """
    Extract average rating and total reviews count.

    Looks for:
    - "4.5 out of 5 stars"
    - "1,234 ratings"
    """
    rating_info = {
        "rating": None,
        "count": None
    }

    # Strategy 1: Look for "X out of 5 stars"
    rating_pattern = r"([0-9.]+)\s+out of\s+5\s+stars"
    match = re.search(rating_pattern, soup.get_text(), re.IGNORECASE)
    if match:
        try:
            rating_info["rating"] = float(match.group(1))
        except ValueError:
            pass

    # Strategy 2: Look for "X,XXX ratings" or "X reviews"
    count_patterns = [
        r"([\d,]+)\s+ratings?",
        r"([\d,]+)\s+customer reviews?",
    ]

    text = soup.get_text()
    for pattern in count_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            count_str = match.group(1).replace(",", "")
            try:
                rating_info["count"] = int(count_str)
                break
            except ValueError:
                continue

    return rating_info


def _parse_product_details(soup: BeautifulSoup) -> Dict[str, Optional[Any]]:
    """
    Extract product details like page count, publisher, publication date.

    Looks in "Product Details" section for:
    - "Paperback: 256 pages"
    - "Publisher: Penguin (January 1, 2020)"
    """
    details = {
        "page_count": None,
        "publisher": None,
        "publication_date": None
    }

    text = soup.get_text()

    # Parse page count
    page_patterns = [
        r"(?:Paperback|Hardcover|Print Length):\s*(\d+)\s+pages",
        r"(\d+)\s+pages",
    ]

    for pattern in page_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                details["page_count"] = int(match.group(1))
                break
            except ValueError:
                continue

    # Parse publisher
    publisher_pattern = r"Publisher:\s*([^(;\n]+)"
    match = re.search(publisher_pattern, text, re.IGNORECASE)
    if match:
        details["publisher"] = match.group(1).strip()

    # Parse publication date
    date_patterns = [
        r"Publication date:\s*([A-Za-z]+\s+\d+,\s+\d{4})",
        r"Publisher:.*?\(([A-Za-z]+\s+\d+,\s+\d{4})\)",
    ]

    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            details["publication_date"] = match.group(1).strip()
            break

    return details


def parse_amazon_to_bookscouter_format(
    html: str,
    isbn_10: str,
    isbn_13: str
) -> Dict[str, Any]:
    """
    Parse Amazon HTML and convert to BookScouterResult-compatible dict.

    Args:
        html: Raw Amazon HTML
        isbn_10: ISBN-10
        isbn_13: ISBN-13

    Returns:
        Dict compatible with BookScouterResult structure
    """
    parsed = parse_amazon_html(html, isbn_13)

    return {
        "isbn_10": isbn_10,
        "isbn_13": isbn_13,
        "offers": [],  # Amazon doesn't provide vendor offers
        "best_price": 0.0,
        "best_vendor": None,
        "total_vendors": 0,
        "amazon_sales_rank": parsed["amazon_sales_rank"],
        "amazon_count": parsed["amazon_count"],
        "amazon_lowest_price": parsed["amazon_lowest_price"],
        "amazon_trade_in_price": None,
        "raw": {
            "status": "success",
            "source": "decodo_amazon",
            "parsed_fields": parsed
        }
    }
