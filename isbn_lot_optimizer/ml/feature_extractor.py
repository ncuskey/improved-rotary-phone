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
    ) -> FeatureVector:
        """
        Extract features from book data.

        Args:
            metadata: Book metadata (title, author, page count, etc.)
            market: eBay market statistics
            bookscouter: BookScouter data (Amazon, buyback offers)
            condition: Book condition (New, Like New, Very Good, Good, Acceptable, Poor)

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
