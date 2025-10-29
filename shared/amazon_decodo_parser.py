"""
Parser for Decodo amazon_product API responses.

Converts Decodo's structured JSON to BookScouterResult-compatible format.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional


class DecodoParseError(RuntimeError):
    """Raised when Decodo response parsing fails."""


def parse_decodo_amazon_product(
    response_data: Dict[str, Any],
    isbn_10: str,
    isbn_13: str
) -> Dict[str, Any]:
    """
    Parse Decodo amazon_product response to BookScouterResult format.

    Args:
        response_data: Raw Decodo API response JSON
        isbn_10: ISBN-10 for the book
        isbn_13: ISBN-13 for the book

    Returns:
        Dict compatible with BookScouterResult structure

    Raises:
        DecodoParseError: If response structure is invalid
    """
    try:
        # Navigate to the parsed results
        if "results" not in response_data or not response_data["results"]:
            raise DecodoParseError("No results in Decodo response")

        result_item = response_data["results"][0]

        # Check status
        if result_item.get("status_code") != 200:
            error_msg = result_item.get("content", {}).get("errors", "Unknown error")
            raise DecodoParseError(f"Decodo returned non-200 status: {error_msg}")

        content = result_item.get("content", {})
        if "results" not in content:
            raise DecodoParseError("No parsed results in content")

        parsed = content["results"]

        # Extract sales rank (overall Books rank)
        sales_rank = _extract_sales_rank(parsed)

        # Extract seller count (if we have pricing data)
        seller_count = _extract_seller_count(parsed)

        # Extract page count from product details
        page_count = _extract_page_count(parsed)

        # Extract publication year
        pub_year = _extract_publication_year(parsed)

        # Build result dict
        return {
            "isbn_10": isbn_10,
            "isbn_13": isbn_13,
            "offers": [],  # Decodo doesn't provide vendor offers in amazon_product
            "best_price": 0.0,
            "best_vendor": None,
            "total_vendors": 0,
            "amazon_sales_rank": sales_rank,
            "amazon_count": seller_count,
            "amazon_lowest_price": parsed.get("price"),
            "amazon_trade_in_price": None,
            "raw": {
                "status": "success",
                "source": "decodo_amazon_product",
                "data": {
                    "title": parsed.get("title"),
                    "rating": parsed.get("rating"),
                    "reviews_count": parsed.get("reviews_count"),
                    "page_count": page_count,
                    "publication_year": pub_year,
                    "asin": parsed.get("asin"),
                    "product_details": parsed.get("product_details", {})
                }
            }
        }

    except KeyError as e:
        raise DecodoParseError(f"Missing required field in Decodo response: {e}") from e
    except Exception as e:
        raise DecodoParseError(f"Failed to parse Decodo response: {e}") from e


def _extract_sales_rank(parsed: Dict[str, Any]) -> Optional[int]:
    """
    Extract overall Books sales rank from sales_rank array.

    Decodo returns an array of ranks:
    [
        {"rank": 9129, "ladder": [{"name": "Books"}]},
        {"rank": 46, "ladder": [{"name": "Children's Dragon Stories"}]},
        ...
    ]

    We want the overall "Books" rank (first one).
    """
    sales_rank_data = parsed.get("sales_rank", [])

    if not sales_rank_data:
        return None

    # Look for overall Books rank
    for rank_item in sales_rank_data:
        ladder = rank_item.get("ladder", [])
        if ladder and any("Books" in str(step.get("name", "")) for step in ladder):
            return rank_item.get("rank")

    # Fallback: return first rank if no Books category found
    if sales_rank_data:
        return sales_rank_data[0].get("rank")

    return None


def _extract_seller_count(parsed: Dict[str, Any]) -> Optional[int]:
    """
    Extract number of sellers from pricing data.

    Note: amazon_product target doesn't include full pricing.
    Use amazon_pricing target for detailed seller counts.
    For now, estimate from other_sellers field.
    """
    # Check if other_sellers data is available
    other_sellers = parsed.get("other_sellers", [])
    if other_sellers:
        return len(other_sellers)

    # Check pricing array (if amazon_pricing was used)
    pricing = parsed.get("pricing", [])
    if pricing:
        return len(pricing)

    # Default: assume at least 1 seller if price exists
    if parsed.get("price"):
        return 1

    return None


def _extract_page_count(parsed: Dict[str, Any]) -> Optional[int]:
    """
    Extract page count from product_details.

    Format: "336 pages" or "print_length": "336 pages"
    """
    product_details = parsed.get("product_details", {})

    # Try print_length field
    print_length = product_details.get("print_length", "")
    if print_length:
        match = re.search(r"(\d+)\s*pages", print_length, re.IGNORECASE)
        if match:
            return int(match.group(1))

    return None


def _extract_publication_year(parsed: Dict[str, Any]) -> Optional[int]:
    """
    Extract publication year from product_details.

    Format: "April 28, 2015" or "publication_date": "April 28, 2015"
    """
    product_details = parsed.get("product_details", {})

    pub_date = product_details.get("publication_date", "")
    if pub_date:
        # Extract 4-digit year
        match = re.search(r"\b(19|20)\d{2}\b", pub_date)
        if match:
            return int(match.group(0))

    return None


def parse_decodo_batch_results(
    batch_results: Dict[str, Any],
    isbn_mapping: Dict[str, tuple]
) -> Dict[str, Dict[str, Any]]:
    """
    Parse multiple Decodo results from batch operation.

    Args:
        batch_results: Dict mapping task_id to DecodoResponse object or dict
        isbn_mapping: Dict mapping task_id to (isbn_10, isbn_13) tuple

    Returns:
        Dict mapping ISBN-13 to parsed BookScouterResult dict
    """
    import json

    parsed_results = {}

    for task_id, response_item in batch_results.items():
        if task_id not in isbn_mapping:
            continue

        isbn_10, isbn_13 = isbn_mapping[task_id]

        try:
            # Handle DecodoResponse object (has .body attribute)
            if hasattr(response_item, 'body'):
                response_data = json.loads(response_item.body) if response_item.body else {}
            # Handle dict (direct response data)
            elif isinstance(response_item, dict):
                response_data = response_item
            else:
                raise DecodoParseError(f"Unknown response type: {type(response_item)}")

            parsed = parse_decodo_amazon_product(response_data, isbn_10, isbn_13)
            parsed_results[isbn_13] = parsed
        except DecodoParseError as e:
            print(f"Warning: Failed to parse {isbn_13}: {e}")
            # Store error result
            parsed_results[isbn_13] = {
                "isbn_10": isbn_10,
                "isbn_13": isbn_13,
                "amazon_sales_rank": None,
                "amazon_count": None,
                "amazon_lowest_price": None,
                "raw": {"status": "error", "error": str(e)}
            }
        except Exception as e:
            print(f"Warning: Unexpected error parsing {isbn_13}: {e}")
            parsed_results[isbn_13] = {
                "isbn_10": isbn_10,
                "isbn_13": isbn_13,
                "amazon_sales_rank": None,
                "amazon_count": None,
                "amazon_lowest_price": None,
                "raw": {"status": "error", "error": str(e)}
            }

    return parsed_results
