"""Keyword ranking and scoring for eBay listing title optimization.

This module analyzes eBay marketplace data to extract and score keywords that
perform well in eBay search. It's designed to help generate SEO-optimized titles
that maximize keyword scores while remaining readable.

The scoring algorithm uses 4 factors:
1. Frequency (40%): How often the keyword appears in competitor titles
2. Price Signal (30%): Average price of listings containing the keyword
3. Sales Velocity (20%): Sold/total ratio for listings with the keyword
4. Competition (10%): Active/sold ratio (lower is better)

Example usage:
    from isbn_lot_optimizer.keyword_analyzer import KeywordAnalyzer

    analyzer = KeywordAnalyzer()
    keywords = analyzer.analyze_keywords_for_isbn("9780553381702")

    # Print top 10 keywords
    for kw in keywords[:10]:
        print(f"{kw.word}: {kw.score:.1f} (appears {kw.frequency}x)")
"""

from __future__ import annotations

import logging
import re
import statistics
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from shared.timing import timer

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

# eBay Browse API URLs
BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

# Common English stopwords to filter out (not valuable for SEO)
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "he", "in", "is", "it", "its", "of", "on", "that", "the",
    "to", "was", "will", "with", "this", "these", "those", "their",
    "there", "where", "when", "who", "which", "why", "what", "how",
    "can", "could", "would", "should", "may", "might", "must",
    "am", "been", "being", "have", "had", "do", "does", "did",
    "all", "any", "both", "each", "few", "more", "most", "other",
    "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "just", "but", "or", "if",
    "because", "also", "into", "through", "during", "before",
    "after", "above", "below", "up", "down", "out", "off", "over",
    "under", "again", "further", "then", "once",
}

# Low-value eBay-specific words
EBAY_STOPWORDS = {
    "new", "used", "free", "shipping", "fast", "ship", "lot", "set",
    "bundle", "collection", "books", "book", "novel", "pb", "hc",
    "paperback", "hardcover", "hb", "ex", "condition", "good", "very",
    "excellent", "acceptable", "like", "brand", "pre", "owned",
    "preowned", "pre-owned", "isbn", "edition", "first", "1st",
}

# Combine all stopwords
ALL_STOPWORDS = STOPWORDS | EBAY_STOPWORDS

# Cache for keyword analysis (24-hour TTL)
_keyword_cache: Dict[str, Tuple[List[KeywordScore], float]] = {}
_KEYWORD_CACHE_TTL = 86400  # 24 hours in seconds


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class KeywordScore:
    """A keyword with its calculated score (1-10)."""

    word: str
    score: float  # 1-10 scale
    frequency: int  # Number of times it appears in titles
    avg_price: float  # Average price of listings with this keyword
    sales_velocity: Optional[float]  # Sold/total ratio (if available)
    competition: Optional[float]  # Active/sold ratio (if available)

    # Individual factor scores (before weighting)
    frequency_score: float
    price_score: float
    velocity_score: float
    competition_score: float


@dataclass
class ListingData:
    """Raw eBay listing data for keyword extraction."""

    title: str
    price: float
    item_id: str
    is_sold: bool = False


# ============================================================================
# Keyword Analyzer
# ============================================================================

class KeywordAnalyzer:
    """Analyzes eBay marketplace data to score keywords for SEO optimization."""

    def __init__(
        self,
        token_broker_url: str = "http://localhost:8787",
        marketplace_id: str = "EBAY_US",
        min_word_length: int = 3,
        max_keywords: int = 50,
        db_path: Optional[Any] = None,
    ):
        """
        Initialize the keyword analyzer.

        Args:
            token_broker_url: URL of OAuth token broker (not needed for Browse API)
            marketplace_id: eBay marketplace ID
            min_word_length: Minimum length for keywords (default: 3)
            max_keywords: Maximum number of keywords to return (default: 50)
            db_path: Path to catalog database for ePID caching (optional)
        """
        self.marketplace_id = marketplace_id
        self.min_word_length = min_word_length
        self.max_keywords = max_keywords

        # Initialize ePID cache if db_path provided
        self.epid_cache = None
        if db_path:
            try:
                from isbn_lot_optimizer.ebay_product_cache import EbayProductCache
                from pathlib import Path
                self.epid_cache = EbayProductCache(Path(db_path))
            except Exception as e:
                logger.warning(f"Could not initialize ePID cache: {e}")
                self.epid_cache = None

    def analyze_keywords_for_isbn(
        self,
        isbn: str,
        limit: int = 100,
        use_cache: bool = True,
    ) -> List[KeywordScore]:
        """
        Analyze keywords for a given ISBN by examining eBay marketplace data.

        Args:
            isbn: ISBN to analyze
            limit: Number of listings to fetch (default: 100)
            use_cache: Whether to use cached results (default: True)

        Returns:
            List of KeywordScore objects sorted by score (highest first)
        """
        # Check cache first
        if use_cache:
            cache_key = f"{isbn}:{limit}"
            now = time.time()
            if cache_key in _keyword_cache:
                cached_result, expires_at = _keyword_cache[cache_key]
                if expires_at > now:
                    logger.info(f"Using cached keyword analysis for ISBN {isbn}")
                    return cached_result

        logger.info(f"Analyzing keywords for ISBN {isbn} (fetching {limit} listings)")

        # Fetch active listings
        with timer(f"Fetch eBay listings for keyword analysis: {isbn}", log=True, record=True):
            listings = self._fetch_listings_by_isbn(isbn, limit)

        if not listings:
            logger.warning(f"No listings found for ISBN {isbn}")
            return []

        logger.info(f"Found {len(listings)} listings for keyword analysis")

        # Extract and score keywords
        with timer("Extract and score keywords", log=True, record=True):
            keyword_scores = self._score_keywords(listings)

        # Sort by score (descending) and limit
        keyword_scores.sort(key=lambda k: k.score, reverse=True)
        result = keyword_scores[:self.max_keywords]

        # Cache result
        if use_cache:
            cache_key = f"{isbn}:{limit}"
            _keyword_cache[cache_key] = (result, time.time() + _KEYWORD_CACHE_TTL)

        logger.info(f"Extracted {len(result)} keywords (top score: {result[0].score:.1f})")
        return result

    def _fetch_listings_by_isbn(
        self,
        isbn: str,
        limit: int,
    ) -> List[ListingData]:
        """
        Fetch eBay sold listings for a given ISBN from the last 90 days.

        Args:
            isbn: ISBN to search
            limit: Maximum number of results

        Returns:
            List of ListingData objects from sold listings (last 90 days)
        """
        # Get OAuth token from existing market module
        from shared.market import get_app_token
        import datetime

        token = get_app_token()

        # Calculate 90-day date range for sold listings
        now = datetime.datetime.now(datetime.timezone.utc)
        ninety_days_ago = now - datetime.timedelta(days=90)

        # Format as ISO 8601 for eBay API
        date_filter = f"[{ninety_days_ago.strftime('%Y-%m-%dT%H:%M:%S.000Z')}..{now.strftime('%Y-%m-%dT%H:%M:%S.000Z')}]"

        # Fetch sold listings from Browse API with filters
        # Filter: buyingOptions=SOLD and lastSoldDate within last 90 days
        params = {
            "gtin": isbn,
            "limit": str(limit),
            "filter": f"buyingOptions:{{SOLD}},lastSoldDate:{date_filter}"
        }

        response = requests.get(
            BROWSE_URL,
            params=params,
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
            },
            timeout=30,
        )

        if response.status_code != 200:
            logger.error(f"eBay API error: {response.status_code}")
            return []

        data = response.json()
        items = data.get("itemSummaries", [])

        # Try to extract ePID from any listing with product data
        epid_found = None
        product_title = None
        category_id = None

        listings: List[ListingData] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            title = item.get("title", "")
            price_info = item.get("price", {})
            price = price_info.get("value")
            item_id = item.get("itemId", "")

            # Extract ePID from item if present (top-level field in Browse API)
            if not epid_found and "epid" in item:
                epid_found = item["epid"]
                product_title = title  # Use listing title as product title
                logger.info(f"Found ePID {epid_found} for ISBN {isbn}")

            # Extract category ID if available
            if not category_id and "categories" in item:
                categories = item.get("categories", [])
                if categories and len(categories) > 0:
                    # Use the leaf category (last in the list)
                    category_id = categories[-1].get("categoryId")

            if not title or not price:
                continue

            try:
                price_float = float(price)
            except (ValueError, TypeError):
                continue

            listings.append(
                ListingData(
                    title=title,
                    price=price_float,
                    item_id=item_id,
                    is_sold=False,  # Browse API only returns active listings
                )
            )

        # Cache ePID if found
        if epid_found and self.epid_cache:
            try:
                product_url = f"https://www.ebay.com/p/{epid_found}"
                self.epid_cache.store_epid(
                    isbn=isbn,
                    epid=epid_found,
                    product_title=product_title,
                    product_url=product_url,
                    category_id=category_id,
                )
            except Exception as e:
                logger.warning(f"Failed to cache ePID: {e}")

        return listings

    def _extract_keywords(self, titles: List[str]) -> Counter:
        """
        Extract keywords from titles and count frequencies.

        Args:
            titles: List of eBay listing titles

        Returns:
            Counter of word frequencies
        """
        word_counts = Counter()

        for title in titles:
            # Tokenize: lowercase, remove special chars, split on whitespace
            words = re.findall(r'\b[a-z]+\b', title.lower())

            # Filter out stopwords and short words
            filtered_words = [
                w for w in words
                if w not in ALL_STOPWORDS and len(w) >= self.min_word_length
            ]

            word_counts.update(filtered_words)

        return word_counts

    def _score_keywords(self, listings: List[ListingData]) -> List[KeywordScore]:
        """
        Score keywords using 4-factor algorithm.

        Scoring factors:
        1. Frequency (40%): How often the keyword appears
        2. Price Signal (30%): Average price of listings with the keyword
        3. Sales Velocity (20%): Sold/total ratio (if available)
        4. Competition (10%): Active/sold ratio (lower is better)

        Args:
            listings: List of listing data

        Returns:
            List of KeywordScore objects
        """
        if not listings:
            return []

        # Extract keywords and frequencies
        titles = [listing.title for listing in listings]
        word_counts = self._extract_keywords(titles)

        if not word_counts:
            return []

        # Calculate price statistics for each keyword
        keyword_prices: Dict[str, List[float]] = {}
        for listing in listings:
            words = re.findall(r'\b[a-z]+\b', listing.title.lower())
            filtered_words = set(
                w for w in words
                if w not in ALL_STOPWORDS and len(w) >= self.min_word_length
            )

            for word in filtered_words:
                if word not in keyword_prices:
                    keyword_prices[word] = []
                keyword_prices[word].append(listing.price)

        # Get overall statistics for normalization
        max_frequency = word_counts.most_common(1)[0][1]
        all_prices = [listing.price for listing in listings]
        min_price = min(all_prices)
        max_price = max(all_prices)
        price_range = max_price - min_price if max_price > min_price else 1.0

        # Score each keyword
        keyword_scores: List[KeywordScore] = []

        for word, frequency in word_counts.items():
            # Factor 1: Frequency score (0-10, normalized)
            frequency_score = (frequency / max_frequency) * 10

            # Factor 2: Price signal score (0-10, normalized)
            avg_price = statistics.mean(keyword_prices[word])
            # Normalize: higher prices = higher scores
            price_score = ((avg_price - min_price) / price_range) * 10

            # Factor 3: Sales velocity (0-10)
            # Note: Browse API only returns active listings, so this is N/A
            # In a full implementation, we'd fetch sold listings too
            velocity_score = 5.0  # Neutral score since we don't have sold data

            # Factor 4: Competition (0-10, inverse)
            # Note: We don't have sold listings, so use frequency as proxy
            # Higher frequency = more competition = lower score
            competition_score = 10 - frequency_score

            # Calculate weighted final score
            final_score = (
                frequency_score * 0.40 +
                price_score * 0.30 +
                velocity_score * 0.20 +
                competition_score * 0.10
            )

            keyword_scores.append(
                KeywordScore(
                    word=word,
                    score=final_score,
                    frequency=frequency,
                    avg_price=avg_price,
                    sales_velocity=None,  # N/A for Browse API
                    competition=None,  # N/A for Browse API
                    frequency_score=frequency_score,
                    price_score=price_score,
                    velocity_score=velocity_score,
                    competition_score=competition_score,
                )
            )

        return keyword_scores

    def clear_cache(self):
        """Clear the keyword analysis cache."""
        _keyword_cache.clear()
        logger.info("Cleared keyword analysis cache")

    def get_epid(self, isbn: str) -> Optional[str]:
        """
        Get cached ePID for an ISBN.

        This is a convenience method that wraps the ePID cache.

        Args:
            isbn: ISBN-13 to look up

        Returns:
            ePID string if found, None otherwise
        """
        if not self.epid_cache:
            return None

        try:
            return self.epid_cache.get_epid(isbn)
        except Exception as e:
            logger.warning(f"Failed to get ePID from cache: {e}")
            return None


# ============================================================================
# Utility Functions
# ============================================================================

def calculate_title_score(title: str, keyword_scores: List[KeywordScore]) -> float:
    """
    Calculate the total score for a title based on keyword scores.

    Args:
        title: eBay listing title
        keyword_scores: List of scored keywords

    Returns:
        Total score (sum of all keyword scores in the title)
    """
    # Create lookup dict for fast access
    score_lookup = {kw.word: kw.score for kw in keyword_scores}

    # Tokenize title
    words = re.findall(r'\b[a-z]+\b', title.lower())

    # Sum scores for all words in title
    total_score = 0.0
    for word in words:
        if word in score_lookup:
            total_score += score_lookup[word]

    return total_score


def format_keyword_report(keyword_scores: List[KeywordScore], top_n: int = 20) -> str:
    """
    Format keyword scores into a readable report.

    Args:
        keyword_scores: List of scored keywords
        top_n: Number of top keywords to include

    Returns:
        Formatted string report
    """
    lines = ["Keyword Analysis Report", "=" * 70, ""]
    lines.append(f"{'Rank':<6} {'Keyword':<20} {'Score':<8} {'Freq':<6} {'Avg Price':<10}")
    lines.append("-" * 70)

    for i, kw in enumerate(keyword_scores[:top_n], 1):
        lines.append(
            f"{i:<6} {kw.word:<20} {kw.score:<8.1f} {kw.frequency:<6} ${kw.avg_price:<9.2f}"
        )

    return "\n".join(lines)


# ============================================================================
# CLI Test Interface
# ============================================================================

if __name__ == "__main__":
    import sys
    import logging as log

    # Configure logging
    log.basicConfig(
        level=log.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if len(sys.argv) < 2:
        print("Usage: python -m isbn_lot_optimizer.keyword_analyzer <isbn>")
        print("Example: python -m isbn_lot_optimizer.keyword_analyzer 9780553381702")
        sys.exit(1)

    isbn = sys.argv[1]

    # Analyze keywords
    analyzer = KeywordAnalyzer()
    keywords = analyzer.analyze_keywords_for_isbn(isbn)

    # Print report
    print("\n" + format_keyword_report(keywords, top_n=30))

    # Example title scoring
    if keywords:
        print("\n" + "=" * 70)
        print("Example Title Scoring:")
        print("=" * 70)

        example_titles = [
            "Storm of Swords George R.R. Martin GRRM Fantasy Epic Series Book",
            "A Storm of Swords by George R.R. Martin (Paperback)",
            "Game of Thrones Book 3 ASOIAF Fantasy Novel GRR Martin",
        ]

        for title in example_titles:
            score = calculate_title_score(title, keywords)
            print(f"\nTitle: {title}")
            print(f"Score: {score:.1f}")
