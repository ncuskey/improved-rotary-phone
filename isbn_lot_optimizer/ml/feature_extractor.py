"""
Feature extraction for ML price estimation.

Converts raw book data (metadata, market stats, etc.) into numerical
feature vectors suitable for machine learning models.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from shared.models import BookMetadata, EbayMarketStats, BookScouterResult


# Feature names in order (critical for model consistency)
FEATURE_NAMES = [
    # Market signals (strongest predictors)
    "log_amazon_rank",
    "amazon_count",
    "ebay_sold_count",
    "ebay_active_count",
    "ebay_active_median",
    "sell_through_rate",

    # AbeBooks pricing (NEW - competitive market data)
    "abebooks_min_price",
    "abebooks_avg_price",
    "abebooks_seller_count",
    "abebooks_condition_spread",
    "abebooks_has_new",
    "abebooks_has_used",
    "abebooks_hardcover_premium",

    # Platform scaling features (cross-platform intelligence)
    "abebooks_scaled_estimate",      # Tier-based eBay estimate from AbeBooks
    "abebooks_competitive_estimate",  # Competition-adjusted estimate
    "abebooks_avg_estimate",         # Simple avg price × 1.9x scaling
    "is_collectible_market",         # Boolean: ultra-cheap AbeBooks = high premium

    # BookFinder aggregator data (meta-search across 20+ vendors)
    "bookfinder_lowest_price",       # Absolute floor price across all vendors
    "bookfinder_source_count",       # Number of vendors offering the book
    "bookfinder_new_vs_used_spread", # Price gap between new and used

    # Book attributes
    "page_count",
    "age_years",
    "log_ratings",
    "rating",
    "has_list_price",
    "list_price",

    # Condition (one-hot encoded)
    "is_new",
    "is_like_new",
    "is_very_good",
    "is_good",
    "is_acceptable",
    "is_poor",

    # Book attributes (physical characteristics)
    "is_hardcover",
    "is_paperback",
    "is_mass_market",
    "is_signed",
    "is_first_edition",

    # Category flags
    "is_textbook",
    "is_fiction",

    # Derived features
    "demand_score",
    "competition_ratio",
    "price_velocity",
]


@dataclass
class FeatureVector:
    """
    Extracted feature vector for ML model.

    Attributes:
        values: numpy array of feature values (length = len(FEATURE_NAMES))
        completeness: fraction of features that are non-zero/non-default (0-1)
        missing_features: list of feature names that are missing or defaulted
    """
    values: np.ndarray
    completeness: float
    missing_features: List[str]
    feature_dict: Dict[str, float]

    def __repr__(self) -> str:
        return f"FeatureVector(completeness={self.completeness:.2f}, features={len(self.values)})"


class FeatureExtractor:
    """
    Extract numerical features from book data for ML model.

    Handles missing data gracefully by using sensible defaults and tracking
    completeness score.
    """

    # High-demand category keywords
    TEXTBOOK_KEYWORDS = ["business", "finance", "medical", "nursing", "law",
                         "science", "technology", "computer", "engineering", "mathematics"]
    FICTION_KEYWORDS = ["fiction", "novel", "mystery", "thriller", "romance", "fantasy"]

    def extract(
        self,
        metadata: Optional[BookMetadata],
        market: Optional[EbayMarketStats],
        bookscouter: Optional[BookScouterResult],
        condition: str = "Good",
        abebooks: Optional[Dict] = None,
        bookfinder: Optional[Dict] = None,
    ) -> FeatureVector:
        """
        Extract features from book data.

        Args:
            metadata: Book metadata (title, author, page count, etc.)
            market: eBay market statistics
            bookscouter: BookScouter data (Amazon, buyback offers)
            condition: Book condition (New, Like New, Very Good, Good, Acceptable, Poor)
            abebooks: AbeBooks pricing data (min, avg, seller count, etc.)
            bookfinder: BookFinder aggregator data (lowest price, source count, spread)

        Returns:
            FeatureVector with extracted features and completeness score
        """
        features = {}
        missing = []

        # Market signals
        if bookscouter and bookscouter.amazon_sales_rank:
            features["log_amazon_rank"] = math.log1p(bookscouter.amazon_sales_rank)
        else:
            features["log_amazon_rank"] = math.log1p(1_000_000)  # Default: very slow
            missing.append("log_amazon_rank")

        if bookscouter and bookscouter.amazon_count:
            features["amazon_count"] = bookscouter.amazon_count
        else:
            features["amazon_count"] = 0
            missing.append("amazon_count")

        if market:
            features["ebay_sold_count"] = market.sold_count if market.sold_count is not None else 0
            features["ebay_active_count"] = market.active_count if market.active_count else 0
            features["ebay_active_median"] = market.active_median_price if market.active_median_price else 0
            features["sell_through_rate"] = market.sell_through_rate if market.sell_through_rate else 0

            if market.sold_count is None or market.sold_count == 0:
                missing.append("ebay_sold_count")
            if not market.active_median_price:
                missing.append("ebay_active_median")
        else:
            features["ebay_sold_count"] = 0
            features["ebay_active_count"] = 0
            features["ebay_active_median"] = 0
            features["sell_through_rate"] = 0
            missing.extend(["ebay_sold_count", "ebay_active_count", "ebay_active_median", "sell_through_rate"])

        # AbeBooks pricing (NEW competitive market data)
        if abebooks:
            features["abebooks_min_price"] = abebooks.get('abebooks_min_price', 0)
            features["abebooks_avg_price"] = abebooks.get('abebooks_avg_price', 0)
            features["abebooks_seller_count"] = abebooks.get('abebooks_seller_count', 0)
            features["abebooks_condition_spread"] = abebooks.get('abebooks_condition_spread', 0)
            features["abebooks_has_new"] = 1 if abebooks.get('abebooks_has_new') else 0
            features["abebooks_has_used"] = 1 if abebooks.get('abebooks_has_used') else 0
            features["abebooks_hardcover_premium"] = abebooks.get('abebooks_hardcover_premium', 0) or 0

            if not features["abebooks_min_price"]:
                missing.append("abebooks_min_price")
            if not features["abebooks_avg_price"]:
                missing.append("abebooks_avg_price")
            if not features["abebooks_seller_count"]:
                missing.append("abebooks_seller_count")
        else:
            features["abebooks_min_price"] = 0
            features["abebooks_avg_price"] = 0
            features["abebooks_seller_count"] = 0
            features["abebooks_condition_spread"] = 0
            features["abebooks_has_new"] = 0
            features["abebooks_has_used"] = 0
            features["abebooks_hardcover_premium"] = 0
            missing.extend(["abebooks_min_price", "abebooks_avg_price", "abebooks_seller_count"])

        # Platform scaling features (cross-platform intelligence)
        # Based on analysis: eBay prices scale 6x over AbeBooks on average, but varies by tier
        abe_min = features["abebooks_min_price"]
        abe_avg = features["abebooks_avg_price"]
        abe_sellers = features["abebooks_seller_count"]

        # Tier-based scaling (discovered from PLATFORM_SCALING_ANALYSIS.md)
        # Ultra-cheap books have highest eBay premiums
        if abe_min > 0:
            if abe_min < 2.0:
                features["abebooks_scaled_estimate"] = abe_min * 8.33
            elif abe_min < 5.0:
                features["abebooks_scaled_estimate"] = abe_min * 3.82
            elif abe_min < 10.0:
                features["abebooks_scaled_estimate"] = abe_min * 1.47
            else:
                features["abebooks_scaled_estimate"] = abe_min * 0.89
        else:
            features["abebooks_scaled_estimate"] = 0
            missing.append("abebooks_scaled_estimate")

        # Competition-adjusted estimate (more sellers = higher premium)
        if abe_min > 0 and abe_sellers > 0:
            if abe_sellers >= 61:
                features["abebooks_competitive_estimate"] = abe_min * 6.03
            elif abe_sellers >= 21:
                features["abebooks_competitive_estimate"] = abe_min * 2.50
            else:
                features["abebooks_competitive_estimate"] = abe_min * 0.96
        else:
            features["abebooks_competitive_estimate"] = 0
            missing.append("abebooks_competitive_estimate")

        # Simple average price scaling (best single predictor: 32.2% within 20%)
        if abe_avg > 0:
            features["abebooks_avg_estimate"] = abe_avg * 1.9
        else:
            features["abebooks_avg_estimate"] = 0
            missing.append("abebooks_avg_estimate")

        # Collectible market indicator (ultra-cheap AbeBooks = likely collectible on eBay)
        features["is_collectible_market"] = 1 if (abe_min > 0 and abe_min < 2.0) else 0

        # BookFinder aggregator data (meta-search pricing across 20+ vendors)
        if bookfinder:
            features["bookfinder_lowest_price"] = bookfinder.get('bookfinder_lowest_price', 0)
            features["bookfinder_source_count"] = bookfinder.get('bookfinder_source_count', 0)
            features["bookfinder_new_vs_used_spread"] = bookfinder.get('bookfinder_new_vs_used_spread', 0)

            if not features["bookfinder_lowest_price"]:
                missing.append("bookfinder_lowest_price")
            if not features["bookfinder_source_count"]:
                missing.append("bookfinder_source_count")
        else:
            features["bookfinder_lowest_price"] = 0
            features["bookfinder_source_count"] = 0
            features["bookfinder_new_vs_used_spread"] = 0
            missing.extend(["bookfinder_lowest_price", "bookfinder_source_count"])

        # Book attributes
        if metadata:
            features["page_count"] = metadata.page_count if metadata.page_count else 300  # Default median
            features["age_years"] = 2025 - (metadata.published_year if metadata.published_year else 2020)
            features["log_ratings"] = math.log1p(metadata.ratings_count if metadata.ratings_count else 0)
            features["rating"] = metadata.average_rating if metadata.average_rating else 0
            features["has_list_price"] = 1 if metadata.list_price else 0
            features["list_price"] = metadata.list_price if metadata.list_price else 0

            if not metadata.page_count:
                missing.append("page_count")
            if not metadata.published_year:
                missing.append("age_years")
            if not metadata.ratings_count:
                missing.append("log_ratings")
            if not metadata.average_rating:
                missing.append("rating")
            if not metadata.list_price:
                missing.append("list_price")
        else:
            features["page_count"] = 300
            features["age_years"] = 5
            features["log_ratings"] = 0
            features["rating"] = 0
            features["has_list_price"] = 0
            features["list_price"] = 0
            missing.extend(["page_count", "age_years", "log_ratings", "rating", "list_price"])

        # Condition (one-hot encoding)
        condition_lower = condition.lower()
        features["is_new"] = 1 if "new" in condition_lower and "like" not in condition_lower else 0
        features["is_like_new"] = 1 if "like new" in condition_lower else 0
        features["is_very_good"] = 1 if "very good" in condition_lower else 0
        features["is_good"] = 1 if condition_lower == "good" else 0
        features["is_acceptable"] = 1 if "acceptable" in condition_lower else 0
        features["is_poor"] = 1 if "poor" in condition_lower else 0

        # Book attributes (physical characteristics)
        if metadata:
            cover_type = getattr(metadata, 'cover_type', None)
            features["is_hardcover"] = 1 if cover_type == "Hardcover" else 0
            features["is_paperback"] = 1 if cover_type == "Paperback" else 0
            features["is_mass_market"] = 1 if cover_type == "Mass Market" else 0
            features["is_signed"] = 1 if getattr(metadata, 'signed', False) else 0
            features["is_first_edition"] = 1 if getattr(metadata, 'printing', None) == "1st" else 0

            if not cover_type:
                missing.extend(["is_hardcover", "is_paperback", "is_mass_market"])
            if not getattr(metadata, 'signed', False):
                missing.append("is_signed")
            if not getattr(metadata, 'printing', None):
                missing.append("is_first_edition")
        else:
            features["is_hardcover"] = 0
            features["is_paperback"] = 0
            features["is_mass_market"] = 0
            features["is_signed"] = 0
            features["is_first_edition"] = 0
            missing.extend(["is_hardcover", "is_paperback", "is_mass_market", "is_signed", "is_first_edition"])

        # Category flags
        if metadata and metadata.categories:
            categories_lower = [cat.lower() for cat in metadata.categories]
            features["is_textbook"] = 1 if any(
                any(keyword in cat for keyword in self.TEXTBOOK_KEYWORDS)
                for cat in categories_lower
            ) else 0
            features["is_fiction"] = 1 if any(
                any(keyword in cat for keyword in self.FICTION_KEYWORDS)
                for cat in categories_lower
            ) else 0
        else:
            features["is_textbook"] = 0
            features["is_fiction"] = 0
            if not metadata or not metadata.categories:
                missing.extend(["is_textbook", "is_fiction"])

        # Derived features
        # Demand score: sold velocity relative to Amazon rank
        if features["ebay_sold_count"] > 0 and features["log_amazon_rank"] > 0:
            features["demand_score"] = features["ebay_sold_count"] / max(1, features["log_amazon_rank"])
        else:
            features["demand_score"] = 0
            missing.append("demand_score")

        # Competition ratio: how much supply vs demand
        if features["ebay_sold_count"] > 0:
            features["competition_ratio"] = features["ebay_active_count"] / features["ebay_sold_count"]
        else:
            features["competition_ratio"] = features["ebay_active_count"]  # All supply, no demand
            if features["ebay_active_count"] == 0:
                missing.append("competition_ratio")

        # Price velocity: how fast prices are moving
        if market and market.active_median_price and market.sold_avg_price:
            features["price_velocity"] = (market.active_median_price - market.sold_avg_price) / max(1, market.sold_avg_price)
        else:
            features["price_velocity"] = 0
            missing.append("price_velocity")

        # Build feature array in correct order
        values = np.array([features[name] for name in FEATURE_NAMES], dtype=np.float32)

        # Calculate completeness (what fraction of features are non-default)
        completeness = 1.0 - (len(missing) / len(FEATURE_NAMES))

        return FeatureVector(
            values=values,
            completeness=completeness,
            missing_features=missing,
            feature_dict=features
        )

    @staticmethod
    def get_feature_names() -> List[str]:
        """Get list of feature names in order."""
        return FEATURE_NAMES.copy()


class PlatformFeatureExtractor(FeatureExtractor):
    """
    Platform-specific feature extractor for stacking models.

    Extracts relevant feature subsets optimized for each platform:
    - eBay: Market signals, demand, condition (27 features)
    - AbeBooks: AbeBooks pricing, book attributes, competition (31 features)
    - Amazon: Amazon rank, book attributes, categories (23 features)
    """

    # Platform-specific feature subsets
    EBAY_FEATURES = [
        # Market signals (eBay-specific)
        "ebay_sold_count",
        "ebay_active_count",
        "ebay_active_median",
        "sell_through_rate",

        # Book attributes
        "page_count",
        "age_years",
        "log_ratings",
        "rating",
        "has_list_price",
        "list_price",

        # Condition (critical for eBay)
        "is_new",
        "is_like_new",
        "is_very_good",
        "is_good",
        "is_acceptable",
        "is_poor",

        # Physical characteristics
        "is_hardcover",
        "is_paperback",
        "is_mass_market",
        "is_signed",
        "is_first_edition",

        # Category flags
        "is_textbook",
        "is_fiction",

        # Derived features
        "demand_score",
        "competition_ratio",
        "price_velocity",
    ]

    ABEBOOKS_FEATURES = [
        # AbeBooks pricing signals
        "abebooks_min_price",
        "abebooks_avg_price",
        "abebooks_seller_count",
        "abebooks_condition_spread",
        "abebooks_has_new",
        "abebooks_has_used",
        "abebooks_hardcover_premium",

        # Platform scaling features
        "abebooks_scaled_estimate",
        "abebooks_competitive_estimate",
        "abebooks_avg_estimate",
        "is_collectible_market",

        # Book attributes
        "page_count",
        "age_years",
        "log_ratings",
        "rating",
        "has_list_price",
        "list_price",

        # Condition
        "is_new",
        "is_like_new",
        "is_very_good",
        "is_good",
        "is_acceptable",
        "is_poor",

        # Physical characteristics
        "is_hardcover",
        "is_paperback",
        "is_mass_market",
        "is_signed",
        "is_first_edition",
    ]

    AMAZON_FEATURES = [
        # Amazon signals
        "log_amazon_rank",
        "amazon_count",

        # Book attributes
        "page_count",
        "age_years",
        "log_ratings",
        "rating",
        "has_list_price",
        "list_price",

        # Condition
        "is_new",
        "is_like_new",
        "is_very_good",
        "is_good",
        "is_acceptable",
        "is_poor",

        # Physical characteristics
        "is_hardcover",
        "is_paperback",
        "is_mass_market",
        "is_signed",
        "is_first_edition",

        # Category flags (important for Amazon)
        "is_textbook",
        "is_fiction",
    ]

    def extract_for_platform(
        self,
        platform: str,
        metadata: Optional[BookMetadata],
        market: Optional[EbayMarketStats],
        bookscouter: Optional[BookScouterResult],
        condition: str = "Good",
        abebooks: Optional[Dict] = None,
    ) -> FeatureVector:
        """
        Extract platform-specific features.

        Args:
            platform: Platform name ('ebay', 'abebooks', or 'amazon')
            metadata: Book metadata
            market: eBay market statistics
            bookscouter: BookScouter data
            condition: Book condition
            abebooks: AbeBooks pricing data

        Returns:
            FeatureVector with platform-specific features only
        """
        # First extract all features
        full_features = self.extract(metadata, market, bookscouter, condition, abebooks)

        # Get platform-specific feature subset
        if platform.lower() == 'ebay':
            selected_features = self.EBAY_FEATURES
        elif platform.lower() == 'abebooks':
            selected_features = self.ABEBOOKS_FEATURES
        elif platform.lower() == 'amazon':
            selected_features = self.AMAZON_FEATURES
        else:
            raise ValueError(f"Unknown platform: {platform}")

        # Extract selected features
        feature_indices = [FEATURE_NAMES.index(name) for name in selected_features]
        platform_values = full_features.values[feature_indices]

        # Filter missing features
        platform_missing = [f for f in full_features.missing_features if f in selected_features]

        # Calculate completeness for platform-specific features
        platform_completeness = 1.0 - (len(platform_missing) / len(selected_features))

        # Build platform-specific feature dict
        platform_dict = {name: full_features.feature_dict[name] for name in selected_features}

        return FeatureVector(
            values=platform_values,
            completeness=platform_completeness,
            missing_features=platform_missing,
            feature_dict=platform_dict
        )

    @staticmethod
    def get_platform_feature_names(platform: str) -> List[str]:
        """Get feature names for a specific platform."""
        if platform.lower() == 'ebay':
            return PlatformFeatureExtractor.EBAY_FEATURES.copy()
        elif platform.lower() == 'abebooks':
            return PlatformFeatureExtractor.ABEBOOKS_FEATURES.copy()
        elif platform.lower() == 'amazon':
            return PlatformFeatureExtractor.AMAZON_FEATURES.copy()
        else:
            raise ValueError(f"Unknown platform: {platform}")


def get_bookfinder_features(isbn: str, db_path: str) -> Optional[Dict]:
    """
    Query BookFinder aggregator features from database.

    Computes 3 features from bookfinder_offers table:
    - bookfinder_lowest_price: Absolute floor price across all vendors
    - bookfinder_source_count: Number of unique vendors offering the book
    - bookfinder_new_vs_used_spread: Price gap between new and used conditions

    Args:
        isbn: ISBN to query
        db_path: Path to catalog database

    Returns:
        Dict with BookFinder features, or None if no data available
    """
    import sqlite3

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                MIN(price + COALESCE(shipping, 0)) as lowest_price,
                COUNT(DISTINCT vendor) as source_count,
                MIN(CASE WHEN condition='New' THEN price + COALESCE(shipping, 0) END) as min_new,
                MIN(CASE WHEN condition='Used' THEN price + COALESCE(shipping, 0) END) as min_used
            FROM bookfinder_offers
            WHERE isbn = ?
        """, (isbn,))

        row = cursor.fetchone()
        conn.close()

        if row and row[0]:  # Has data
            min_new = row[2] or 0
            min_used = row[3] or 0
            # Calculate spread only if both conditions exist
            spread = (min_new - min_used) if (min_new > 0 and min_used > 0) else 0

            return {
                'bookfinder_lowest_price': row[0],
                'bookfinder_source_count': row[1],
                'bookfinder_new_vs_used_spread': spread
            }

        return None

    except Exception as e:
        # Database may not have bookfinder_offers table yet
        return None
