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

    # Amazon pricing features (Phase 3: specialist model improvements)
    "amazon_lowest_price",
    "amazon_trade_in_price",
    "amazon_price_per_rank",
    "amazon_competitive_density",

    "ebay_sold_count",
    "ebay_active_median",

    # eBay pricing features (Phase 2: specialist model improvements)
    "ebay_sold_min",
    "ebay_sold_median",
    "ebay_sold_max",
    "ebay_sold_price_spread",
    "ebay_active_vs_sold_ratio",

    # AbeBooks pricing (NEW - competitive market data)
    "abebooks_min_price",
    "abebooks_avg_price",
    "abebooks_seller_count",
    "abebooks_condition_spread",
    "abebooks_has_new",
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
    "bookfinder_avg_price",          # Average price across all offers
    "bookfinder_total_offers",       # Total number of offers
    "bookfinder_price_volatility",   # Price range as % of average (market uncertainty)
    "bookfinder_signed_count",       # Number of signed copies available
    "bookfinder_has_signed",         # Boolean: any signed copies available
    "bookfinder_signed_lowest",      # Lowest price for signed copies
    "bookfinder_first_edition_count",# Number of first editions available
    "bookfinder_first_ed_lowest",    # Lowest price for first editions
    "bookfinder_avg_desc_length",    # Average description length (quality signal)
    "bookfinder_detailed_pct",       # % of offers with detailed descriptions

    # Phase 2.3: BookFinder premium differentials
    "bookfinder_signed_premium_pct",   # Signed book premium percentage
    "bookfinder_first_ed_premium_pct", # First edition premium percentage

    # Sold listings data (Serper Google Search results)
    # NOTE: Price features removed (Phase 1) to prevent data leakage
    "serper_sold_count",              # Number of sold listings found
    "serper_sold_has_signed",         # Boolean: any signed copies in sold listings
    "serper_sold_signed_pct",         # % of sold listings that are signed
    "serper_sold_hardcover_pct",      # % of sold listings that are hardcover
    "serper_sold_ebay_pct",           # % of sold listings from eBay

    # Phase 2.4: Author-level aggregates

    # Book attributes
    "page_count",
    "age_years",
    "log_ratings",
    "rating",

    # Phase 2.1: Temporal features
    "is_recent",           # Published within 3 years
    "is_backlist",         # Published 3-10 years ago
    "decade_sin",          # Cyclical decade encoding (sin)
    "decade_cos",          # Cyclical decade encoding (cos)
    "age_squared",         # Quadratic age transformation
    "log_age",             # Log-scaled age

    # Phase 2.2: Series completion features

    # Condition (one-hot encoded)
    "is_very_good",
    "is_good",

    # Book attributes (physical characteristics)
    "is_hardcover",
    "is_mass_market",
    "is_signed",
    "is_first_edition",

    # Category flags
    "is_textbook",
    "is_fiction",

    # Derived features
    "demand_score",
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
        sold_listings: Optional[Dict] = None,
        author_aggregates: Optional[Dict] = None,
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
            sold_listings: Sold listings data from Serper (count, avg price, features)
            author_aggregates: Author-level statistics (Phase 2.4)

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

        # Amazon pricing features (Phase 3: specialist model improvements)
        if bookscouter and bookscouter.amazon_lowest_price:
            features["amazon_lowest_price"] = bookscouter.amazon_lowest_price
        else:
            features["amazon_lowest_price"] = 0
            missing.append("amazon_lowest_price")

        if bookscouter and hasattr(bookscouter, 'amazon_trade_in_price') and bookscouter.amazon_trade_in_price:
            features["amazon_trade_in_price"] = bookscouter.amazon_trade_in_price
        else:
            features["amazon_trade_in_price"] = 0

        # Amazon derived competitive features
        amazon_rank_log = features["log_amazon_rank"]
        amazon_price = features["amazon_lowest_price"]
        amazon_count = features["amazon_count"]

        # Price per rank: lower rank books should command higher prices
        if amazon_price > 0 and amazon_rank_log > 0:
            features["amazon_price_per_rank"] = amazon_price / amazon_rank_log
        else:
            features["amazon_price_per_rank"] = 0

        # Competitive density: high seller count + good rank = competitive market
        if amazon_count > 0 and amazon_rank_log > 0:
            features["amazon_competitive_density"] = amazon_count / amazon_rank_log
        else:
            features["amazon_competitive_density"] = 0

        if market:
            features["ebay_sold_count"] = market.sold_count if market.sold_count is not None else 0
            features["ebay_active_count"] = market.active_count if market.active_count else 0
            features["ebay_active_median"] = market.active_median_price if market.active_median_price else 0
            features["sell_through_rate"] = market.sell_through_rate if market.sell_through_rate else 0

            # eBay sold comps pricing features (Phase 2: specialist model improvements)
            features["ebay_sold_min"] = market.sold_comps_min if hasattr(market, 'sold_comps_min') and market.sold_comps_min else 0
            features["ebay_sold_median"] = market.sold_comps_median if hasattr(market, 'sold_comps_median') and market.sold_comps_median else 0
            features["ebay_sold_max"] = market.sold_comps_max if hasattr(market, 'sold_comps_max') and market.sold_comps_max else 0

            # Derived pricing features
            if features["ebay_sold_max"] and features["ebay_sold_min"]:
                features["ebay_sold_price_spread"] = features["ebay_sold_max"] - features["ebay_sold_min"]
            else:
                features["ebay_sold_price_spread"] = 0

            # Active vs sold ratio (market premium indicator)
            if features["ebay_sold_median"] and features["ebay_active_median"]:
                features["ebay_active_vs_sold_ratio"] = features["ebay_active_median"] / features["ebay_sold_median"]
            else:
                features["ebay_active_vs_sold_ratio"] = 0

            if market.sold_count is None or market.sold_count == 0:
                missing.append("ebay_sold_count")
            if not market.active_median_price:
                missing.append("ebay_active_median")
            if not features["ebay_sold_median"]:
                missing.append("ebay_sold_median")
        else:
            features["ebay_sold_count"] = 0
            features["ebay_active_count"] = 0
            features["ebay_active_median"] = 0
            features["sell_through_rate"] = 0
            features["ebay_sold_min"] = 0
            features["ebay_sold_median"] = 0
            features["ebay_sold_max"] = 0
            features["ebay_sold_price_spread"] = 0
            features["ebay_active_vs_sold_ratio"] = 0
            missing.extend(["ebay_sold_count", "ebay_active_count", "ebay_active_median", "sell_through_rate",
                          "ebay_sold_median"])

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
            # Original features
            features["bookfinder_lowest_price"] = bookfinder.get('bookfinder_lowest_price', 0)
            features["bookfinder_source_count"] = bookfinder.get('bookfinder_source_count', 0)
            features["bookfinder_new_vs_used_spread"] = bookfinder.get('bookfinder_new_vs_used_spread', 0)

            # Enhanced pricing features
            features["bookfinder_avg_price"] = bookfinder.get('bookfinder_avg_price', 0)
            features["bookfinder_total_offers"] = bookfinder.get('bookfinder_total_offers', 0)
            features["bookfinder_price_volatility"] = bookfinder.get('bookfinder_price_volatility', 0)

            # Collectibility signals
            features["bookfinder_signed_count"] = bookfinder.get('bookfinder_signed_count', 0)
            features["bookfinder_has_signed"] = bookfinder.get('bookfinder_has_signed', 0)
            features["bookfinder_signed_lowest"] = bookfinder.get('bookfinder_signed_lowest', 0)
            features["bookfinder_first_edition_count"] = bookfinder.get('bookfinder_first_edition_count', 0)
            features["bookfinder_has_first_edition"] = bookfinder.get('bookfinder_has_first_edition', 0)
            features["bookfinder_first_ed_lowest"] = bookfinder.get('bookfinder_first_ed_lowest', 0)
            features["bookfinder_oldworld_count"] = bookfinder.get('bookfinder_oldworld_count', 0)

            # Quality signals
            features["bookfinder_avg_desc_length"] = bookfinder.get('bookfinder_avg_desc_length', 0)
            features["bookfinder_detailed_pct"] = bookfinder.get('bookfinder_detailed_pct', 0)

            # Phase 2.3: Premium differentials
            features["bookfinder_signed_premium_pct"] = bookfinder.get('bookfinder_signed_premium_pct', 0)
            features["bookfinder_first_ed_premium_pct"] = bookfinder.get('bookfinder_first_ed_premium_pct', 0)

            if not features["bookfinder_lowest_price"]:
                missing.append("bookfinder_lowest_price")
            if not features["bookfinder_source_count"]:
                missing.append("bookfinder_source_count")
        else:
            # Defaults when no BookFinder data
            features["bookfinder_lowest_price"] = 0
            features["bookfinder_source_count"] = 0
            features["bookfinder_new_vs_used_spread"] = 0
            features["bookfinder_avg_price"] = 0
            features["bookfinder_total_offers"] = 0
            features["bookfinder_price_volatility"] = 0
            features["bookfinder_signed_count"] = 0
            features["bookfinder_has_signed"] = 0
            features["bookfinder_signed_lowest"] = 0
            features["bookfinder_first_edition_count"] = 0
            features["bookfinder_has_first_edition"] = 0
            features["bookfinder_first_ed_lowest"] = 0
            features["bookfinder_oldworld_count"] = 0
            features["bookfinder_avg_desc_length"] = 0
            features["bookfinder_detailed_pct"] = 0
            features["bookfinder_signed_premium_pct"] = 0
            features["bookfinder_first_ed_premium_pct"] = 0
            missing.extend(["bookfinder_lowest_price", "bookfinder_source_count"])

        # Sold listings data (Serper Google Search results)
        # NOTE: Price features removed to prevent data leakage
        # Only using non-price statistics: volume, platform distribution, format indicators
        if sold_listings:
            features["serper_sold_count"] = sold_listings.get('serper_sold_count', 0)
            features["serper_sold_has_signed"] = sold_listings.get('serper_sold_has_signed', 0)
            features["serper_sold_signed_pct"] = sold_listings.get('serper_sold_signed_pct', 0)
            features["serper_sold_hardcover_pct"] = sold_listings.get('serper_sold_hardcover_pct', 0)
            features["serper_sold_ebay_pct"] = sold_listings.get('serper_sold_ebay_pct', 0)

            if not features["serper_sold_count"]:
                missing.append("serper_sold_count")
        else:
            features["serper_sold_count"] = 0
            features["serper_sold_has_signed"] = 0
            features["serper_sold_signed_pct"] = 0
            features["serper_sold_hardcover_pct"] = 0
            features["serper_sold_ebay_pct"] = 0
            missing.append("serper_sold_count")

        # Phase 2.4: Author-level aggregates
        if author_aggregates:
            features["author_book_count"] = author_aggregates.get('author_book_count', 0)
            features["log_author_catalog_size"] = author_aggregates.get('log_author_catalog_size', 0)
            features["author_avg_sold_price"] = author_aggregates.get('author_avg_sold_price', 0)
            features["log_author_avg_price"] = author_aggregates.get('log_author_avg_price', 0)
            features["author_avg_sales_velocity"] = author_aggregates.get('author_avg_sales_velocity', 0)
            features["author_collectibility_score"] = author_aggregates.get('author_collectibility_score', 0)
            features["author_popularity_score"] = author_aggregates.get('author_popularity_score', 0)
            features["author_avg_rating"] = author_aggregates.get('author_avg_rating', 0)
        else:
            # Defaults when no author data available
            features["author_book_count"] = 1  # Assume single book
            features["log_author_catalog_size"] = 0
            features["author_avg_sold_price"] = 15.0  # Market average
            features["log_author_avg_price"] = math.log1p(15.0)
            features["author_avg_sales_velocity"] = 5.0  # Low-mid velocity
            features["author_collectibility_score"] = 0.2  # Low collectibility
            features["author_popularity_score"] = 1.0  # Low popularity
            features["author_avg_rating"] = 3.5  # Neutral rating
            missing.append("author_book_count")

        # Book attributes
        if metadata:
            features["page_count"] = metadata.page_count if metadata.page_count else 300  # Default median
            features["age_years"] = 2025 - (metadata.published_year if metadata.published_year else 2020)
            features["log_ratings"] = math.log1p(metadata.ratings_count if metadata.ratings_count else 0)
            features["rating"] = metadata.average_rating if metadata.average_rating else 0
            features["has_list_price"] = 1 if metadata.list_price else 0
            features["list_price"] = metadata.list_price if metadata.list_price else 0

            # Enhanced temporal features (Phase 2.1)
            age = features["age_years"]
            # Age category indicators
            features["is_new_release"] = 1 if age <= 1 else 0  # Published this year or last
            features["is_recent"] = 1 if age <= 3 else 0  # Published within 3 years
            features["is_backlist"] = 1 if 3 < age <= 10 else 0  # 3-10 years old
            features["is_classic"] = 1 if age > 50 else 0  # Over 50 years old

            # Decade cyclical encoding (captures periodic patterns)
            pub_year = metadata.published_year if metadata.published_year else 2020
            decade = (pub_year // 10) % 10  # 0-9 representing last digit of decade
            features["decade_sin"] = math.sin(2 * math.pi * decade / 10)
            features["decade_cos"] = math.cos(2 * math.pi * decade / 10)

            # Age-based value decay (older books may have different pricing dynamics)
            features["age_squared"] = age ** 2
            features["log_age"] = math.log1p(age)

            # Series completion features (Phase 2.2)
            series_name = getattr(metadata, 'series_name', None)
            series_index = getattr(metadata, 'series_index', None)
            features["has_series"] = 1 if series_name else 0
            if series_name and series_index is not None:
                # Assuming series typically have 3-10 books, normalize position
                # Lower index = earlier in series, may have collector value
                series_idx = series_index
                features["series_index"] = series_idx
                features["is_series_start"] = 1 if series_idx == 1 else 0  # First book premium
                features["is_series_middle"] = 1 if 1 < series_idx <= 5 else 0
                features["is_series_late"] = 1 if series_idx > 5 else 0
                # Log transform for diminishing returns on later books
                features["log_series_index"] = math.log1p(series_idx)
            else:
                features["series_index"] = 0
                features["is_series_start"] = 0
                features["is_series_middle"] = 0
                features["is_series_late"] = 0
                features["log_series_index"] = 0

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
            # Default temporal features
            features["is_new_release"] = 0
            features["is_recent"] = 1  # Default to recent
            features["is_backlist"] = 0
            features["is_classic"] = 0
            features["decade_sin"] = 0
            features["decade_cos"] = 1
            features["age_squared"] = 25
            features["log_age"] = math.log1p(5)
            # Default series features
            features["has_series"] = 0
            features["series_index"] = 0
            features["is_series_start"] = 0
            features["is_series_middle"] = 0
            features["is_series_late"] = 0
            features["log_series_index"] = 0
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
    - eBay: Market signals, pricing data, demand, condition (20 features)
    - AbeBooks: AbeBooks pricing, book attributes, competition (31 features)
    - Amazon: Amazon pricing, rank, book attributes, categories (18 features)
    """

    # Platform-specific feature subsets
    EBAY_FEATURES = [
        # Market signals (eBay-specific)
        "ebay_sold_count",
        "ebay_active_median",

        # eBay pricing features (Phase 2: specialist model improvements)
        "ebay_sold_min",
        "ebay_sold_median",
        "ebay_sold_max",
        "ebay_sold_price_spread",
        "ebay_active_vs_sold_ratio",

        # Book attributes
        "page_count",
        "age_years",
        "log_ratings",
        "rating",

        # Condition (critical for eBay)
        "is_very_good",
        "is_good",

        # Physical characteristics
        "is_hardcover",
        "is_mass_market",
        "is_signed",
        "is_first_edition",

        # Category flags
        "is_textbook",
        "is_fiction",

        # Derived features
        "demand_score",
    ]

    ABEBOOKS_FEATURES = [
        # AbeBooks pricing signals
        "abebooks_min_price",
        "abebooks_avg_price",
        "abebooks_seller_count",
        "abebooks_condition_spread",
        "abebooks_has_new",
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

        # Condition
        "is_very_good",
        "is_good",

        # Physical characteristics
        "is_hardcover",
        "is_mass_market",
        "is_signed",
        "is_first_edition",
    ]

    AMAZON_FEATURES = [
        # Amazon signals
        "log_amazon_rank",
        "amazon_count",

        # Amazon pricing features (Phase 3: specialist model improvements)
        "amazon_lowest_price",
        "amazon_trade_in_price",
        "amazon_price_per_rank",
        "amazon_competitive_density",

        # Book attributes
        "page_count",
        "age_years",
        "log_ratings",
        "rating",

        # Condition
        "is_very_good",
        "is_good",

        # Physical characteristics
        "is_hardcover",
        "is_mass_market",
        "is_signed",
        "is_first_edition",

        # Category flags (important for Amazon)
        "is_textbook",
        "is_fiction",
    ]

    # NEW: Biblio features (antiquarian book marketplace)
    BIBLIO_FEATURES = [
        # BookFinder collectibility signals (critical for antiquarian)
        "bookfinder_signed_count",
        "bookfinder_has_signed",
        "bookfinder_signed_lowest",
        "bookfinder_first_edition_count",
        "bookfinder_first_ed_lowest",
        "bookfinder_avg_desc_length",
        "bookfinder_detailed_pct",

        # BookFinder pricing
        "bookfinder_lowest_price",
        "bookfinder_avg_price",
        "bookfinder_source_count",
        "bookfinder_price_volatility",

        # Book attributes
        "page_count",
        "age_years",
        "log_ratings",
        "rating",

        # Physical characteristics (critical for rare books)
        "is_hardcover",
        "is_signed",
        "is_first_edition",

        # Condition
        "is_very_good",
        "is_good",
    ]

    # NEW: Alibris features (independent booksellers marketplace)
    ALIBRIS_FEATURES = [
        # BookFinder collectibility signals
        "bookfinder_signed_count",
        "bookfinder_has_signed",
        "bookfinder_signed_lowest",
        "bookfinder_first_edition_count",
        "bookfinder_first_ed_lowest",
        "bookfinder_avg_desc_length",
        "bookfinder_detailed_pct",

        # BookFinder pricing
        "bookfinder_lowest_price",
        "bookfinder_avg_price",
        "bookfinder_source_count",
        "bookfinder_price_volatility",

        # Book attributes
        "page_count",
        "age_years",
        "log_ratings",
        "rating",

        # Physical characteristics
        "is_hardcover",
        "is_signed",
        "is_first_edition",

        # Condition
        "is_very_good",
        "is_good",
    ]

    # NEW: Zvab features (German antiquarian marketplace)
    ZVAB_FEATURES = [
        # BookFinder collectibility signals
        "bookfinder_signed_count",
        "bookfinder_has_signed",
        "bookfinder_signed_lowest",
        "bookfinder_first_edition_count",
        "bookfinder_first_ed_lowest",
        "bookfinder_avg_desc_length",
        "bookfinder_detailed_pct",

        # BookFinder pricing
        "bookfinder_lowest_price",
        "bookfinder_avg_price",
        "bookfinder_source_count",
        "bookfinder_price_volatility",

        # Book attributes
        "page_count",
        "age_years",
        "log_ratings",
        "rating",

        # Physical characteristics
        "is_hardcover",
        "is_signed",
        "is_first_edition",

        # Condition
        "is_very_good",
        "is_good",
    ]

    def extract_for_platform(
        self,
        platform: str,
        metadata: Optional[BookMetadata],
        market: Optional[EbayMarketStats],
        bookscouter: Optional[BookScouterResult],
        condition: str = "Good",
        abebooks: Optional[Dict] = None,
        bookfinder: Optional[Dict] = None,
        sold_listings: Optional[Dict] = None,
    ) -> FeatureVector:
        """
        Extract platform-specific features.

        Args:
            platform: Platform name ('ebay', 'abebooks', 'amazon', 'biblio', 'alibris', 'zvab')
            metadata: Book metadata
            market: eBay market statistics
            bookscouter: BookScouter data
            condition: Book condition
            abebooks: AbeBooks pricing data
            bookfinder: BookFinder aggregator data
            sold_listings: Sold listings data from Serper

        Returns:
            FeatureVector with platform-specific features only
        """
        # First extract all features
        full_features = self.extract(metadata, market, bookscouter, condition, abebooks, bookfinder, sold_listings)

        # Get platform-specific feature subset
        if platform.lower() == 'ebay':
            selected_features = self.EBAY_FEATURES
        elif platform.lower() == 'abebooks':
            selected_features = self.ABEBOOKS_FEATURES
        elif platform.lower() == 'amazon':
            selected_features = self.AMAZON_FEATURES
        elif platform.lower() == 'biblio':
            selected_features = self.BIBLIO_FEATURES
        elif platform.lower() == 'alibris':
            selected_features = self.ALIBRIS_FEATURES
        elif platform.lower() == 'zvab':
            selected_features = self.ZVAB_FEATURES
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
        elif platform.lower() == 'biblio':
            return PlatformFeatureExtractor.BIBLIO_FEATURES.copy()
        elif platform.lower() == 'alibris':
            return PlatformFeatureExtractor.ALIBRIS_FEATURES.copy()
        elif platform.lower() == 'zvab':
            return PlatformFeatureExtractor.ZVAB_FEATURES.copy()
        else:
            raise ValueError(f"Unknown platform: {platform}")


def get_bookfinder_features(isbn: str, db_path: str) -> Optional[Dict]:
    """
    Query BookFinder aggregator features from database.

    Extracts comprehensive pricing and collectibility signals from bookfinder_offers.

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

        # Comprehensive feature extraction with Phase 2.3 premium calculations
        cursor.execute("""
            SELECT
                -- Basic pricing
                MIN(price + COALESCE(shipping, 0)) as lowest_price,
                AVG(price + COALESCE(shipping, 0)) as avg_price,
                MAX(price + COALESCE(shipping, 0)) as highest_price,
                COUNT(*) as total_offers,
                COUNT(DISTINCT vendor) as source_count,

                -- Condition spread
                MIN(CASE WHEN condition='New' THEN price + COALESCE(shipping, 0) END) as min_new,
                MIN(CASE WHEN condition='Used' THEN price + COALESCE(shipping, 0) END) as min_used,

                -- Collectibility signals (NEW)
                SUM(CASE WHEN is_signed = 1 THEN 1 ELSE 0 END) as signed_count,
                MIN(CASE WHEN is_signed = 1 THEN price + COALESCE(shipping, 0) END) as signed_lowest_price,
                SUM(CASE WHEN is_first_edition = 1 THEN 1 ELSE 0 END) as first_edition_count,
                MIN(CASE WHEN is_first_edition = 1 THEN price + COALESCE(shipping, 0) END) as first_ed_lowest_price,
                SUM(CASE WHEN is_oldworld = 1 THEN 1 ELSE 0 END) as oldworld_count,

                -- Description richness (proxy for quality)
                AVG(LENGTH(COALESCE(description, ''))) as avg_description_length,
                SUM(CASE WHEN LENGTH(COALESCE(description, '')) > 100 THEN 1 ELSE 0 END) as detailed_offers_count,

                -- Phase 2.3: Premium differential data
                AVG(CASE WHEN is_signed = 1 THEN price + COALESCE(shipping, 0) END) as signed_avg_price,
                AVG(CASE WHEN is_signed = 0 OR is_signed IS NULL THEN price + COALESCE(shipping, 0) END) as unsigned_avg_price,
                AVG(CASE WHEN is_first_edition = 1 THEN price + COALESCE(shipping, 0) END) as first_ed_avg_price,
                AVG(CASE WHEN is_first_edition = 0 OR is_first_edition IS NULL THEN price + COALESCE(shipping, 0) END) as non_first_ed_avg_price

            FROM bookfinder_offers
            WHERE isbn = ?
        """, (isbn,))

        row = cursor.fetchone()
        conn.close()

        if row and row[0]:  # Has data
            min_new = row[5] or 0
            min_used = row[6] or 0
            spread = (min_new - min_used) if (min_new > 0 and min_used > 0) else 0

            lowest_price = row[0]
            avg_price = row[1] or 0
            highest_price = row[2] or 0

            # Price volatility (range as % of average)
            price_volatility = ((highest_price - lowest_price) / avg_price) if avg_price > 0 else 0

            # Phase 2.3: Premium differential calculations
            signed_avg = row[14] or 0
            unsigned_avg = row[15] or 0
            first_ed_avg = row[16] or 0
            non_first_ed_avg = row[17] or 0

            # Signed book premium percentage
            signed_premium_pct = ((signed_avg - unsigned_avg) / unsigned_avg * 100) if unsigned_avg > 0 and signed_avg > 0 else 0
            # First edition premium percentage
            first_ed_premium_pct = ((first_ed_avg - non_first_ed_avg) / non_first_ed_avg * 100) if non_first_ed_avg > 0 and first_ed_avg > 0 else 0

            return {
                # Original features
                'bookfinder_lowest_price': lowest_price,
                'bookfinder_source_count': row[4],
                'bookfinder_new_vs_used_spread': spread,

                # NEW: Enhanced pricing features
                'bookfinder_avg_price': avg_price,
                'bookfinder_total_offers': row[3],
                'bookfinder_price_volatility': price_volatility,

                # NEW: Collectibility signals
                'bookfinder_signed_count': row[7] or 0,
                'bookfinder_has_signed': 1 if row[7] and row[7] > 0 else 0,
                'bookfinder_signed_lowest': row[8] or 0,
                'bookfinder_first_edition_count': row[9] or 0,
                'bookfinder_has_first_edition': 1 if row[9] and row[9] > 0 else 0,
                'bookfinder_first_ed_lowest': row[10] or 0,
                'bookfinder_oldworld_count': row[11] or 0,

                # NEW: Quality signals
                'bookfinder_avg_desc_length': row[12] or 0,
                'bookfinder_detailed_pct': (row[13] / row[3]) if row[3] > 0 else 0,

                # Phase 2.3: Premium differentials
                'bookfinder_signed_premium_pct': signed_premium_pct,
                'bookfinder_first_ed_premium_pct': first_ed_premium_pct,
            }

        return None

    except Exception as e:
        # Database may not have bookfinder_offers table yet
        return None


def get_sold_listings_features(isbn: str, db_path: str) -> Optional[Dict]:
    """
    Query sold listings NON-PRICE features from database.

    NOTE: Price features removed to prevent data leakage.
    Only extracts market demand indicators: volume, platform distribution, format indicators.

    Args:
        isbn: ISBN to query
        db_path: Path to catalog database

    Returns:
        Dict with sold listings NON-PRICE features, or None if no data available
    """
    import sqlite3

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Aggregate sold listings data (NON-PRICE STATISTICS ONLY)
        cursor.execute("""
            SELECT
                COUNT(*) as count,
                SUM(CASE WHEN signed = 1 THEN 1 ELSE 0 END) as signed_count,
                SUM(CASE WHEN cover_type = 'Hardcover' THEN 1 ELSE 0 END) as hardcover_count,
                SUM(CASE WHEN platform = 'ebay' THEN 1 ELSE 0 END) as ebay_count
            FROM sold_listings
            WHERE isbn = ? AND price IS NOT NULL
        """, (isbn,))

        row = cursor.fetchone()
        conn.close()

        if row and row[0] and row[0] > 0:  # Has sold listings
            count = row[0]
            signed_count = row[1] or 0
            hardcover_count = row[2] or 0
            ebay_count = row[3] or 0

            return {
                'serper_sold_count': count,
                'serper_sold_has_signed': 1 if signed_count > 0 else 0,
                'serper_sold_signed_pct': (signed_count / count) if count > 0 else 0,
                'serper_sold_hardcover_pct': (hardcover_count / count) if count > 0 else 0,
                'serper_sold_ebay_pct': (ebay_count / count) if count > 0 else 0,
            }

        return None

    except Exception as e:
        # Database may not have sold_listings table yet
        return None


def get_author_aggregates(canonical_author: str, db_path: str) -> Optional[Dict]:
    """
    Query author-level aggregate features from database.

    Phase 2.4: Extract author-specific patterns to capture author brand value
    (e.g., Stephen King vs unknown author).

    Args:
        canonical_author: Canonical author name to query
        db_path: Path to catalog database

    Returns:
        Dict with author aggregate features, or None if no data available
    """
    import sqlite3
    import math

    if not canonical_author or canonical_author == "Unknown":
        return None

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Aggregate statistics across all books by this author
        cursor.execute("""
            SELECT
                COUNT(*) as book_count,
                AVG(COALESCE(sold_comps_median, 0)) as avg_sold_price,
                AVG(COALESCE(sold_count, 0)) as avg_sales_velocity,
                AVG(COALESCE(ratings_count, 0)) as avg_ratings_count,
                AVG(COALESCE(average_rating, 0)) as avg_rating,
                SUM(CASE WHEN bookfinder_has_signed = 1 THEN 1 ELSE 0 END) as signed_book_count,
                SUM(CASE WHEN bookfinder_has_first_edition = 1 THEN 1 ELSE 0 END) as first_ed_book_count
            FROM books
            WHERE canonical_author = ? AND sold_comps_median IS NOT NULL
        """, (canonical_author,))

        row = cursor.fetchone()
        conn.close()

        if row and row[0] and row[0] > 0:  # Has books by this author
            book_count = row[0]
            avg_sold_price = row[1] or 0
            avg_sales_velocity = row[2] or 0
            avg_ratings_count = row[3] or 0
            avg_rating = row[4] or 0
            signed_book_count = row[5] or 0
            first_ed_book_count = row[6] or 0

            # Author collectibility score (weighted combination of signals)
            signed_pct = (signed_book_count / book_count) if book_count > 0 else 0
            first_ed_pct = (first_ed_book_count / book_count) if book_count > 0 else 0
            # Normalize price to 0-1 scale (assume $100 as high-end)
            price_normalized = min(avg_sold_price / 100.0, 1.0)

            collectibility_score = (
                signed_pct * 0.3 +
                first_ed_pct * 0.3 +
                price_normalized * 0.4
            )

            # Author popularity score (log-scaled ratings * sales velocity)
            popularity_score = math.log1p(avg_ratings_count) * avg_sales_velocity

            return {
                'author_book_count': book_count,
                'log_author_catalog_size': math.log1p(book_count),
                'author_avg_sold_price': avg_sold_price,
                'log_author_avg_price': math.log1p(avg_sold_price),
                'author_avg_sales_velocity': avg_sales_velocity,
                'author_collectibility_score': collectibility_score,
                'author_popularity_score': popularity_score,
                'author_avg_rating': avg_rating,
            }

        return None

    except Exception as e:
        # Database may not have required columns yet
        return None
