"""
HTML parser for WatchCount.com sold listings.

Extracts eBay sold item data from WatchCount HTML and filters out lot listings.
"""

import re
import statistics
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup

from shared.lot_detector import is_lot, get_lot_detection_reason


def _extract_price(price_text: str) -> Optional[float]:
    """
    Extract numeric price from text like "$12.99", "12.99", etc.

    Args:
        price_text: Raw price text

    Returns:
        Float price or None if unable to parse
    """
    if not price_text:
        return None

    # Remove currency symbols and whitespace
    cleaned = re.sub(r'[^\d.]', '', price_text.strip())

    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _extract_condition(text: str) -> Optional[str]:
    """
    Extract book condition from text.

    Args:
        text: Text that may contain condition keywords

    Returns:
        Standardized condition string or None
    """
    if not text:
        return None

    text_lower = text.lower()

    conditions = {
        "brand new": "New",
        "like new": "Like New",
        "very good": "Very Good",
        "good": "Good",
        "acceptable": "Acceptable",
    }

    for keyword, standard in conditions.items():
        if keyword in text_lower:
            return standard

    return None


def parse_watchcount_html(html: str, isbn: str) -> Dict[str, Any]:
    """
    Parse WatchCount HTML and extract sold item data with lot detection.

    Keeps both individual and lot data - lots are useful for bulk valuation analysis.

    Args:
        html: Raw HTML from WatchCount
        isbn: ISBN being searched (for context)

    Returns:
        Dict with structure:
        {
            "individual_sales": {
                "count": int,
                "avg_price": float,
                "median_price": float,
                "min_price": float,
                "max_price": float,
                "items": [...]
            },
            "lot_sales": {
                "count": int,
                "avg_price": float,
                "avg_price_per_book": float,  # Estimated based on lot size
                "items": [...]  # Includes lot_size and lot_reason fields
            },
            "total_items": int
        }
    """
    soup = BeautifulSoup(html, 'html.parser')

    individual_items = []
    lot_items = []

    # Find sold items table/list
    # WatchCount structure: Look for rows with item data
    # Each row typically contains: title, price, date, seller

    # Strategy 1: Find all links to eBay items (these are the sold listings)
    ebay_links = soup.find_all('a', href=re.compile(r'ebay\.com/itm/'))

    if not ebay_links:
        # Strategy 2: Try alternate selectors
        ebay_links = soup.find_all('a', href=re.compile(r'item=\d+'))

    for link in ebay_links:
        try:
            # Extract title
            title_elem = link
            title = title_elem.get_text(strip=True) if title_elem else ""

            # Skip if no title
            if not title:
                continue

            # Get the parent row/container
            row = link.find_parent('tr') or link.find_parent('div', class_=re.compile(r'item|row'))

            if not row:
                # Fallback: use siblings
                row = link.parent

            # Extract price from row
            price_text = ""
            price_elem = row.find(string=re.compile(r'\$\d+'))
            if price_elem:
                price_text = price_elem.strip()

            price = _extract_price(price_text)

            # Extract condition
            condition = None
            condition_elem = row.find(string=re.compile(r'(?:New|Like New|Very Good|Good|Acceptable)', re.IGNORECASE))
            if condition_elem:
                condition = _extract_condition(condition_elem.string)

            # Extract date (if available)
            date_elem = row.find(string=re.compile(r'\d{1,2}/\d{1,2}/\d{2,4}'))
            date = date_elem.strip() if date_elem else None

            # Build item dict
            item = {
                "title": title,
                "price": price or 0.0,
                "condition": condition,
                "date": date,
                "url": link.get('href', ''),
            }

            # Check if it's a lot
            if is_lot(title):
                from shared.lot_detector import extract_lot_size
                item["lot_reason"] = get_lot_detection_reason(title)
                item["lot_size"] = extract_lot_size(title) or 2  # Default to 2 if can't extract
                lot_items.append(item)
            else:
                individual_items.append(item)

        except Exception as e:
            # Skip items that fail to parse
            print(f"Warning: Failed to parse item: {e}")
            continue

    # Calculate statistics on individual items
    individual_prices = [item["price"] for item in individual_items if item["price"] > 0]

    if individual_prices:
        individual_stats = {
            "count": len(individual_items),
            "avg_price": round(statistics.mean(individual_prices), 2),
            "median_price": round(statistics.median(individual_prices), 2),
            "min_price": round(min(individual_prices), 2),
            "max_price": round(max(individual_prices), 2),
            "items": individual_items
        }
    else:
        individual_stats = {
            "count": 0,
            "avg_price": 0.0,
            "median_price": 0.0,
            "min_price": 0.0,
            "max_price": 0.0,
            "items": []
        }

    # Calculate statistics on lot items
    lot_prices = [item["price"] for item in lot_items if item["price"] > 0]
    lot_price_per_book = []

    for item in lot_items:
        if item["price"] > 0 and "lot_size" in item:
            price_per = item["price"] / item["lot_size"]
            lot_price_per_book.append(price_per)

    if lot_prices:
        lot_stats = {
            "count": len(lot_items),
            "avg_price": round(statistics.mean(lot_prices), 2),
            "avg_price_per_book": round(statistics.mean(lot_price_per_book), 2) if lot_price_per_book else 0.0,
            "items": lot_items
        }
    else:
        lot_stats = {
            "count": 0,
            "avg_price": 0.0,
            "avg_price_per_book": 0.0,
            "items": []
        }

    return {
        "individual_sales": individual_stats,
        "lot_sales": lot_stats,
        "total_items": len(individual_items) + len(lot_items)
    }


def parse_watchcount_summary(html: str) -> Dict[str, Any]:
    """
    Parse WatchCount page summary statistics (watchers, total sold, etc).

    Args:
        html: Raw HTML from WatchCount

    Returns:
        Dict with summary stats like total_sold, avg_watchers, etc.
    """
    soup = BeautifulSoup(html, 'html.parser')

    summary = {
        "total_sold": 0,
        "avg_watchers": 0,
        "trend": None,
    }

    # Look for summary statistics in the page
    # WatchCount typically shows: "X items sold" or "Average watchers: Y"

    # Extract total sold count
    sold_text = soup.find(string=re.compile(r'(\d+)\s*items?\s*sold', re.IGNORECASE))
    if sold_text:
        match = re.search(r'(\d+)', sold_text)
        if match:
            summary["total_sold"] = int(match.group(1))

    # Extract average watchers
    watchers_text = soup.find(string=re.compile(r'average.*?(\d+)\s*watchers?', re.IGNORECASE))
    if watchers_text:
        match = re.search(r'(\d+)', watchers_text)
        if match:
            summary["avg_watchers"] = int(match.group(1))

    return summary


if __name__ == "__main__":
    # Test with sample HTML
    sample_html = """
    <html>
    <body>
    <table>
        <tr>
            <td><a href="https://www.ebay.com/itm/123456">A Game of Thrones Hardcover</a></td>
            <td>$14.99</td>
            <td>Very Good</td>
            <td>01/15/2025</td>
        </tr>
        <tr>
            <td><a href="https://www.ebay.com/itm/123457">Lot of 5 Game of Thrones Books</a></td>
            <td>$45.00</td>
            <td>Good</td>
            <td>01/14/2025</td>
        </tr>
        <tr>
            <td><a href="https://www.ebay.com/itm/123458">A Game of Thrones Paperback</a></td>
            <td>$9.99</td>
            <td>Good</td>
            <td>01/13/2025</td>
        </tr>
    </table>
    </body>
    </html>
    """

    print("Testing WatchCount Parser")
    print("-" * 80)

    result = parse_watchcount_html(sample_html, "9780553381702")

    print(f"Results:")
    print(f"  Total items parsed: {result['total_items']}")
    print(f"  Individual sales: {result['individual_sales']['count']}")
    print(f"  Lot sales: {result['lot_sales']['count']}")
    print()

    print("Individual Sales:")
    ind = result['individual_sales']
    print(f"  Avg price: ${ind['avg_price']:.2f}")
    print(f"  Median price: ${ind['median_price']:.2f}")
    print(f"  Price range: ${ind['min_price']:.2f} - ${ind['max_price']:.2f}")
    if ind['items']:
        print("  Items:")
        for item in ind['items']:
            print(f"    - {item['title']}")
            print(f"      ${item['price']:.2f} | {item['condition']}")
    print()

    print("Lot Sales:")
    lots = result['lot_sales']
    print(f"  Avg lot price: ${lots['avg_price']:.2f}")
    print(f"  Avg price per book: ${lots['avg_price_per_book']:.2f}")
    if lots['items']:
        print("  Items:")
        for lot in lots['items']:
            print(f"    - {lot['title']}")
            print(f"      ${lot['price']:.2f} | Size: {lot.get('lot_size', '?')} | Reason: {lot.get('lot_reason', 'N/A')}")
