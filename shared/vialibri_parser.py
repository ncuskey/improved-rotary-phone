"""
viaLibri HTML parser for extracting book pricing and availability data.

Parses search results from viaLibri to extract:
- Multiple seller prices from various marketplaces
- Book metadata (author, title, description)
- Seller information
- Condition and attributes
"""

import re
import statistics
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup


def _extract_price(price_text: str) -> Optional[float]:
    """
    Extract numeric price from text like "$104", "US$ 12.99", etc.

    Args:
        price_text: Raw price text

    Returns:
        Float price or None if unable to parse
    """
    if not price_text:
        return None

    # Remove currency symbols, whitespace, and commas
    price_text = price_text.replace('US$', '').replace('$', '').replace(',', '').strip()

    try:
        return float(price_text)
    except (ValueError, AttributeError):
        return None


def parse_vialibri_html(html: str) -> Dict[str, Any]:
    """
    Parse viaLibri search results HTML to extract book listings.

    Args:
        html: Raw HTML from viaLibri search results page (after JavaScript rendering)

    Returns:
        Dict with structure:
        {
            "listings": [
                {
                    "author": str,
                    "title": str,
                    "description": str,
                    "seller": str,
                    "seller_location": str,
                    "prices": [
                        {
                            "marketplace": str,
                            "price": float,
                            "price_display": str
                        },
                        ...
                    ]
                },
                ...
            ],
            "stats": {
                "total_listings": int,
                "total_price_points": int,
                "min_price": float,
                "max_price": float,
                "median_price": float,
                "mean_price": float
            }
        }
    """
    soup = BeautifulSoup(html, 'lxml')

    # Find all book listings
    book_elements = soup.find_all('div', class_='book--search-result')

    listings = []
    all_prices = []

    for book in book_elements:
        listing = {}

        # Extract author
        author_elem = book.find('div', class_='book__author')
        listing['author'] = author_elem.get_text(strip=True) if author_elem else None

        # Extract title
        title_elem = book.find('div', class_='book__title')
        listing['title'] = title_elem.get_text(strip=True) if title_elem else None

        # Extract description (includes publisher, year, condition, attributes)
        desc_elem = book.find('div', class_='book__description-text')
        listing['description'] = desc_elem.get_text(strip=True) if desc_elem else None

        # Extract seller info
        dealer_elem = book.find('div', class_='book-dealer')
        if dealer_elem:
            # Seller name is in a span with title attribute
            seller_span = dealer_elem.find('span', title=True)
            if seller_span:
                listing['seller'] = seller_span.get('title', '').split('(')[0].strip()
            else:
                listing['seller'] = dealer_elem.get_text(strip=True).replace('Bookseller:', '').strip()

            # Seller location
            location_elem = dealer_elem.find('span', class_='book-dealer__location')
            listing['seller_location'] = location_elem.get_text(strip=True).strip('()') if location_elem else None
        else:
            listing['seller'] = None
            listing['seller_location'] = None

        # Extract prices from different marketplaces
        listing['prices'] = []
        price_links = book.find_all('div', class_='book-link')
        for link in price_links:
            marketplace_elem = link.find('span', class_='book-link__name')
            price_elem = link.find('span', class_='book-link__price')

            if marketplace_elem and price_elem:
                price_display = price_elem.get_text(strip=True)
                price_value = _extract_price(price_display)

                if price_value:
                    listing['prices'].append({
                        'marketplace': marketplace_elem.get_text(strip=True),
                        'price': price_value,
                        'price_display': price_display
                    })
                    all_prices.append(price_value)

        listings.append(listing)

    # Calculate statistics
    stats = {
        'total_listings': len(listings),
        'total_price_points': len(all_prices),
        'min_price': min(all_prices) if all_prices else None,
        'max_price': max(all_prices) if all_prices else None,
        'median_price': statistics.median(all_prices) if all_prices else None,
        'mean_price': statistics.mean(all_prices) if all_prices else None
    }

    return {
        'listings': listings,
        'stats': stats
    }


def extract_ml_features(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract machine learning features from viaLibri data.

    Similar to other parsers - extracts numeric features useful for price prediction.

    Args:
        data: Parsed viaLibri data from parse_vialibri_html()

    Returns:
        Dict of ML features
    """
    stats = data.get('stats', {})

    return {
        'vialibri_count': stats.get('total_listings', 0),
        'vialibri_price_points': stats.get('total_price_points', 0),
        'vialibri_min': stats.get('min_price'),
        'vialibri_max': stats.get('max_price'),
        'vialibri_median': stats.get('median_price'),
        'vialibri_mean': stats.get('mean_price'),
        'vialibri_has_data': stats.get('total_listings', 0) > 0
    }
