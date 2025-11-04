"""
Sold listing parser factory - routes URLs to platform-specific parsers.

Provides unified interface for parsing sold listings across all platforms.
Automatically detects platform from URL and delegates to appropriate parser.
"""

import re
from typing import Dict, Any, Optional
from urllib.parse import urlparse


def detect_platform(url: str) -> Optional[str]:
    """
    Detect platform from URL.

    Args:
        url: Listing URL

    Returns:
        Platform name ('ebay', 'abebooks', 'mercari', 'amazon') or None
    """
    parsed = urlparse(url.lower())
    domain = parsed.netloc.replace('www.', '')

    platform_domains = {
        'ebay.com': 'ebay',
        'abebooks.com': 'abebooks',
        'mercari.com': 'mercari',
        'amazon.com': 'amazon',
    }

    for domain_pattern, platform in platform_domains.items():
        if domain_pattern in domain:
            return platform

    return None


def parse_sold_listing(url: str, html: str, snippet: str = "", platform: Optional[str] = None) -> Dict[str, Any]:
    """
    Parse a sold listing from any supported platform.

    Automatically detects platform and delegates to appropriate parser.

    Args:
        url: Listing URL
        html: Raw HTML from listing page
        snippet: Optional search result snippet (fallback data source)
        platform: Optional explicit platform name (skip auto-detection)

    Returns:
        Dict with standardized structure:
        {
            "platform": str,
            "url": str,
            "listing_id": str,
            "title": str,
            "price": float,
            "condition": str,
            "sold_date": str (ISO format),
            "is_lot": bool,
            "success": bool,
            "snippet": str,
            "error": Optional[str]
        }
    """
    # Auto-detect platform if not provided
    if platform is None:
        platform = detect_platform(url)

    if platform is None:
        return {
            "platform": None,
            "url": url,
            "success": False,
            "error": f"Unable to detect platform from URL: {url}"
        }

    # Import and call appropriate parser
    try:
        if platform == 'ebay':
            from shared.ebay_sold_parser import parse_ebay_sold_listing
            return parse_ebay_sold_listing(url, html, snippet)

        elif platform == 'abebooks':
            # AbeBooks doesn't have public sold listings like eBay
            # For now, return unsupported
            return {
                "platform": "abebooks",
                "url": url,
                "success": False,
                "error": "AbeBooks sold listings not yet supported"
            }

        elif platform == 'mercari':
            from shared.mercari_sold_parser import parse_mercari_sold_listing
            return parse_mercari_sold_listing(url, html, snippet)

        elif platform == 'amazon':
            from shared.amazon_sold_parser import parse_amazon_sold_listing
            return parse_amazon_sold_listing(url, html, snippet)

        else:
            return {
                "platform": platform,
                "url": url,
                "success": False,
                "error": f"Parser not implemented for platform: {platform}"
            }

    except Exception as e:
        return {
            "platform": platform,
            "url": url,
            "success": False,
            "error": f"Parser error: {str(e)}"
        }


def get_supported_platforms() -> list:
    """
    Get list of supported platforms.

    Returns:
        List of platform names with parsers
    """
    return ['ebay', 'mercari', 'amazon']


def is_platform_supported(platform: str) -> bool:
    """
    Check if platform has a parser implementation.

    Args:
        platform: Platform name

    Returns:
        True if supported
    """
    return platform in get_supported_platforms()


if __name__ == "__main__":
    # Test platform detection
    test_urls = [
        "https://www.ebay.com/itm/123456789012",
        "https://www.mercari.com/us/item/m12345678901/",
        "https://www.amazon.com/dp/B001234567",
        "https://www.abebooks.com/book/123456",
        "https://example.com/unknown",
    ]

    print("Testing Sold Listing Parser Factory")
    print("=" * 80)
    print()

    print("Platform Detection:")
    for url in test_urls:
        platform = detect_platform(url)
        supported = is_platform_supported(platform) if platform else False
        status = "✓ Supported" if supported else "✗ Unsupported" if platform else "✗ Unknown"
        print(f"  {url}")
        print(f"    → Platform: {platform or 'Unknown'} {status}")
    print()

    # Test parsing with sample HTML
    ebay_html = """
    <html>
    <head><title>Test eBay Listing | eBay</title></head>
    <body>
        <h1 class="product-title">A Game of Thrones Hardcover</h1>
        <span class="price">Sold for $24.99</span>
        <div>Condition: Very Good</div>
        <div>Sold on Jan 15, 2025</div>
    </body>
    </html>
    """

    print("Testing eBay Parser via Factory:")
    result = parse_sold_listing(
        "https://www.ebay.com/itm/123456789012",
        ebay_html
    )
    print(f"  Platform: {result['platform']}")
    print(f"  Success: {result['success']}")
    print(f"  Title: {result.get('title', 'N/A')}")
    print(f"  Price: ${result['price']:.2f}" if result.get('price') else "  Price: N/A")
    print()

    print("Supported Platforms:")
    for platform in get_supported_platforms():
        print(f"  • {platform}")
    print()
