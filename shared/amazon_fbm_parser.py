"""
Amazon FBM (Fulfilled by Merchant) parser for extracting third-party seller data.

Extends amazon_parser.py to specifically identify and extract FBM seller pricing,
filtering out Amazon direct and FBA (Fulfilled by Amazon) listings.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup


class AmazonFBMParseError(RuntimeError):
    """Raised when Amazon FBM HTML parsing fails."""


def parse_amazon_fbm_offers(html: str, isbn: str = None) -> Dict[str, Any]:
    """
    Parse Amazon "Other Sellers" page to extract FBM (third-party) seller data.

    FBM sellers are identified by:
    - NO "Fulfilled by Amazon" badge
    - NO Prime logo
    - Shows merchant name + "Ships from..."
    - Individual shipping costs (not Prime free shipping)

    Args:
        html: Raw HTML from Amazon product or "Other Sellers" page
        isbn: Optional ISBN for context in error messages

    Returns:
        Dict with FBM pricing statistics:
        - fbm_offers: List of individual FBM offers
        - fbm_count: int (number of FBM sellers)
        - fbm_min: float (lowest FBM price)
        - fbm_median: float (median FBM price)
        - fbm_max: float (highest FBM price)
        - fbm_avg_rating: float (average seller rating)

    Raises:
        AmazonFBMParseError: If HTML is invalid or parsing fails
    """
    if not html or len(html) < 100:
        raise AmazonFBMParseError(f"HTML too short or empty for ISBN {isbn}")

    soup = BeautifulSoup(html, "lxml")

    # Check for bot detection
    if "Robot Check" in html or "Type the characters you see in this picture" in html:
        raise AmazonFBMParseError(f"Bot detection triggered for ISBN {isbn}")

    # Extract FBM offers
    fbm_offers = _extract_fbm_offers_from_pricing_json(html)

    if not fbm_offers:
        # Fallback: Try parsing HTML structure
        fbm_offers = _extract_fbm_offers_from_html(soup)

    # Calculate statistics
    result = _calculate_fbm_statistics(fbm_offers)
    result['fbm_offers'] = fbm_offers

    return result


def _extract_fbm_offers_from_pricing_json(html: str) -> List[Dict[str, Any]]:
    """
    Extract FBM offers from Amazon's embedded pricing JSON (most reliable method).

    Amazon embeds pricing data in <script type="application/ld+json"> tags.
    FBM offers lack "seller": {"name": "Amazon.com"} and fulfillment info.
    """
    fbm_offers = []

    # Look for JSON-LD pricing data
    json_pattern = r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>'
    matches = re.findall(json_pattern, html, re.DOTALL | re.IGNORECASE)

    for json_str in matches:
        try:
            import json
            data = json.loads(json_str)

            # Check if this is pricing data
            if isinstance(data, dict) and 'offers' in data:
                offers = data['offers']
                if not isinstance(offers, list):
                    offers = [offers]

                for offer in offers:
                    # Filter for FBM: no Amazon seller, no Prime
                    seller_name = offer.get('seller', {}).get('name', '')
                    availability = offer.get('availability', '')
                    price = offer.get('price') or offer.get('lowPrice')

                    is_amazon = 'amazon' in seller_name.lower()
                    is_prime = 'prime' in availability.lower()

                    if not is_amazon and not is_prime and price:
                        fbm_offers.append({
                            'price': float(price),
                            'seller': seller_name,
                            'condition': offer.get('itemCondition', ''),
                            'availability': availability
                        })
        except (json.JSONDecodeError, ValueError, KeyError):
            continue

    return fbm_offers


def _extract_fbm_offers_from_html(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """
    Extract FBM offers from HTML structure (fallback method).

    Looks for seller offer divs and filters out FBA/Amazon.
    """
    fbm_offers = []

    # Amazon's offer listings use various div structures
    offer_selectors = [
        'div[id^="aod-offer"]',  # "All Offers Display" listings
        'div.a-row.a-spacing-mini',  # Seller listing rows
    ]

    for selector in offer_selectors:
        offers = soup.select(selector)

        for offer_div in offers:
            offer_text = offer_div.get_text().lower()

            # Skip if contains FBA indicators
            if any(indicator in offer_text for indicator in [
                'fulfilled by amazon',
                'prime',
                'amazon.com',
                'sold by amazon'
            ]):
                continue

            # Extract price
            price_elem = offer_div.find('span', class_=re.compile(r'price', re.IGNORECASE))
            if not price_elem:
                continue

            price_text = price_elem.get_text().strip()
            price_match = re.search(r'\$([0-9.]+)', price_text)

            if not price_match:
                continue

            try:
                price = float(price_match.group(1))
            except ValueError:
                continue

            # Extract seller name
            seller_elem = offer_div.find(string=re.compile(r'sold by', re.IGNORECASE))
            seller = 'Unknown'
            if seller_elem:
                seller_parent = seller_elem.find_parent()
                if seller_parent:
                    seller = seller_parent.get_text().replace('Sold by:', '').strip()

            # Extract condition
            condition_elem = offer_div.find(string=re.compile(r'condition', re.IGNORECASE))
            condition = 'Used'
            if condition_elem:
                condition_parent = condition_elem.find_parent()
                if condition_parent:
                    condition = condition_parent.get_text().strip()

            # Extract seller rating
            rating = None
            rating_elem = offer_div.find(string=re.compile(r'%', re.IGNORECASE))
            if rating_elem:
                rating_match = re.search(r'(\d+)%', rating_elem)
                if rating_match:
                    rating = int(rating_match.group(1))

            fbm_offers.append({
                'price': price,
                'seller': seller,
                'condition': condition,
                'rating': rating
            })

    return fbm_offers


def _calculate_fbm_statistics(fbm_offers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate aggregate statistics from FBM offers.
    """
    if not fbm_offers:
        return {
            'fbm_count': 0,
            'fbm_min': None,
            'fbm_median': None,
            'fbm_max': None,
            'fbm_avg_rating': None
        }

    # Extract prices
    prices = [offer['price'] for offer in fbm_offers if offer.get('price')]
    prices.sort()

    # Extract ratings
    ratings = [offer['rating'] for offer in fbm_offers if offer.get('rating')]

    # Calculate statistics
    stats = {
        'fbm_count': len(fbm_offers),
        'fbm_min': min(prices) if prices else None,
        'fbm_max': max(prices) if prices else None,
        'fbm_median': prices[len(prices) // 2] if prices else None,
        'fbm_avg_rating': sum(ratings) / len(ratings) if ratings else None
    }

    return stats


def parse_amazon_fbm_from_decodo(pricing_data: List[Dict]) -> Dict[str, Any]:
    """
    Parse FBM offers from Decodo's amazon_pricing response.

    Decodo returns a list of pricing offers. We need to filter for FBM:
    - delivery != "Ships from Amazon.com" (FBA indicator)
    - seller_link doesn't contain "isAmazonFulfilled=1" (FBA indicator)
    - Seller name != "Amazon.com"

    Args:
        pricing_data: List of pricing offers from Decodo API

    Returns:
        Dict with FBM statistics (same format as parse_amazon_fbm_offers)
    """
    fbm_offers = []

    for offer in pricing_data:
        # Extract seller name (string, not dict)
        seller_name = offer.get('seller', '')
        if isinstance(seller_name, dict):
            seller_name = seller_name.get('name', '')

        # Filter out Amazon direct seller
        is_amazon_seller = 'amazon.com' in seller_name.lower()
        if is_amazon_seller:
            continue

        # Check delivery field for FBA
        delivery = offer.get('delivery', '').lower()
        is_fba_delivery = 'amazon.com' in delivery

        # Check seller_link for FBA indicator
        seller_link = offer.get('seller_link', '')
        is_amazon_fulfilled = 'isamazonfulfilled=1' in seller_link.lower()

        # Skip if FBA
        if is_fba_delivery or is_amazon_fulfilled:
            continue

        # Extract price
        price = offer.get('price') or offer.get('total')
        if not price:
            continue

        try:
            price = float(price)
        except (ValueError, TypeError):
            continue

        # Extract condition and rating
        condition = offer.get('condition', 'Used')
        rating = offer.get('rating_count')  # Changed from seller_rating to rating_count

        if rating:
            try:
                rating = int(rating)
            except (ValueError, TypeError):
                rating = None

        fbm_offers.append({
            'price': price,
            'seller': seller_name,
            'condition': condition,
            'rating': rating
        })

    # Calculate statistics
    return _calculate_fbm_statistics(fbm_offers)
