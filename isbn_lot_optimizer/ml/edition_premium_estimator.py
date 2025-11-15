"""
Edition Premium Calibration Model.

Uses BookFinder paired edition data to predict realistic first edition premiums,
avoiding confounding factors in sold listings data.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional, Tuple

import joblib
import numpy as np


class EditionPremiumEstimator:
    """
    Estimates first edition price premium using ML model trained on BookFinder data.

    The main ML model trained on sold_listings can't reliably predict first edition
    premiums due to confounding factors (condition, selection bias, etc.). This
    specialized model uses BookFinder's within-ISBN comparisons to learn realistic
    edition premiums.
    """

    def __init__(self, model_dir: Optional[Path] = None):
        """
        Initialize edition premium estimator.

        Args:
            model_dir: Directory containing edition premium model files.
                      Defaults to isbn_lot_optimizer/models/edition_premium/
        """
        if model_dir is None:
            package_dir = Path(__file__).parent.parent
            model_dir = package_dir / "models" / "edition_premium"

        self.model_dir = Path(model_dir)
        self.model = None
        self.scaler = None
        self.metadata = {}

        self._load_model()

    def _load_model(self) -> None:
        """Load trained model, scaler, and metadata from disk."""
        model_path = self.model_dir / "model_v1.pkl"
        scaler_path = self.model_dir / "scaler_v1.pkl"
        metadata_path = self.model_dir / "metadata_v1.json"

        if not model_path.exists():
            return

        try:
            self.model = joblib.load(model_path)
            if scaler_path.exists():
                self.scaler = joblib.load(scaler_path)

            if metadata_path.exists():
                with open(metadata_path, "r") as f:
                    self.metadata = json.load(f)

        except Exception as e:
            print(f"Warning: Failed to load edition premium model: {e}")
            self.model = None

    def is_ready(self) -> bool:
        """Check if model is loaded and ready."""
        return self.model is not None

    def estimate_premium(
        self,
        isbn: str,
        baseline_price: float,
        catalog_db_path: Optional[Path] = None,
        cache_db_path: Optional[Path] = None
    ) -> Tuple[float, str]:
        """
        Estimate first edition premium for a book.

        Args:
            isbn: Book ISBN
            baseline_price: Base price without first edition premium
            catalog_db_path: Path to catalog.db with BookFinder data
            cache_db_path: Path to metadata_cache.db

        Returns:
            Tuple of (premium_dollars, explanation)
        """
        if not self.is_ready():
            # Fall back to conservative 3% heuristic
            return baseline_price * 0.03, "Using 3% heuristic (model not available)"

        # Default database paths
        if catalog_db_path is None:
            catalog_db_path = Path.home() / ".isbn_lot_optimizer" / "catalog.db"
        if cache_db_path is None:
            cache_db_path = Path.home() / ".isbn_lot_optimizer" / "metadata_cache.db"

        # Extract features from BookFinder data
        features = self._extract_features(isbn, catalog_db_path, cache_db_path)

        if features is None:
            # No BookFinder data available
            return baseline_price * 0.03, "Using 3% heuristic (no BookFinder data)"

        try:
            # Predict premium percentage
            X = np.array([features])
            if self.scaler is not None:
                X = self.scaler.transform(X)

            premium_pct = self.model.predict(X)[0]

            # Convert percentage to dollars
            premium_dollars = baseline_price * (premium_pct / 100.0)

            # Sanity check: premium should be between -10% and +100%
            if premium_pct < -10.0:
                premium_pct = -10.0
                premium_dollars = baseline_price * -0.10
            elif premium_pct > 100.0:
                premium_pct = 100.0
                premium_dollars = baseline_price * 1.00

            explanation = f"ML calibration: {premium_pct:+.1f}% premium"
            return round(premium_dollars, 2), explanation

        except Exception as e:
            return baseline_price * 0.03, f"Using 3% heuristic (prediction error: {e})"

    def _extract_features(
        self,
        isbn: str,
        catalog_db_path: Path,
        cache_db_path: Path
    ) -> Optional[list]:
        """
        Extract edition premium features for an ISBN.

        Returns:
            List of feature values in correct order, or None if insufficient data
        """
        try:
            catalog_conn = sqlite3.connect(catalog_db_path)
            cache_conn = sqlite3.connect(cache_db_path)

            # Get BookFinder pricing statistics
            cursor = catalog_conn.cursor()
            cursor.execute("""
                SELECT
                    AVG(CASE WHEN is_first_edition = 1 THEN price + COALESCE(shipping, 0) END) as first_ed_avg,
                    AVG(CASE WHEN is_first_edition = 0 OR is_first_edition IS NULL
                        THEN price + COALESCE(shipping, 0) END) as non_first_ed_avg,
                    MIN(CASE WHEN is_first_edition = 1 THEN price + COALESCE(shipping, 0) END) as first_ed_min,
                    MAX(CASE WHEN is_first_edition = 1 THEN price + COALESCE(shipping, 0) END) as first_ed_max,
                    MIN(CASE WHEN is_first_edition = 0 OR is_first_edition IS NULL
                        THEN price + COALESCE(shipping, 0) END) as non_first_ed_min,
                    MAX(CASE WHEN is_first_edition = 0 OR is_first_edition IS NULL
                        THEN price + COALESCE(shipping, 0) END) as non_first_ed_max,
                    COUNT(CASE WHEN is_first_edition = 1 THEN 1 END) as first_ed_count,
                    COUNT(CASE WHEN is_first_edition = 0 OR is_first_edition IS NULL THEN 1 END) as non_first_ed_count
                FROM bookfinder_offers
                WHERE isbn = ?
            """, (isbn,))
            bf_row = cursor.fetchone()

            catalog_conn.close()

            if not bf_row or not bf_row[0] or not bf_row[1]:
                cache_conn.close()
                return None

            first_ed_avg, non_first_ed_avg = bf_row[0], bf_row[1]
            first_ed_min, first_ed_max = bf_row[2], bf_row[3]
            non_first_ed_min, non_first_ed_max = bf_row[4], bf_row[5]
            first_ed_count, non_first_ed_count = bf_row[6], bf_row[7]

            # Get metadata
            cache_cursor = cache_conn.cursor()
            cache_cursor.execute("""
                SELECT publication_year, page_count, binding
                FROM cached_books
                WHERE isbn = ?
            """, (isbn,))
            meta_row = cache_cursor.fetchone()

            cache_conn.close()

            # Build feature vector (must match training order)
            features = [
                # BookFinder pricing features (14 features)
                first_ed_avg,
                non_first_ed_avg,
                first_ed_avg / non_first_ed_avg if non_first_ed_avg > 0 else 1.0,  # price_ratio
                first_ed_avg - non_first_ed_avg,  # price_difference
                first_ed_min or first_ed_avg,
                first_ed_max or first_ed_avg,
                non_first_ed_min or non_first_ed_avg,
                non_first_ed_max or non_first_ed_avg,
                (first_ed_max or first_ed_avg) - (first_ed_min or first_ed_avg),  # first_ed_price_range
                (non_first_ed_max or non_first_ed_avg) - (non_first_ed_min or non_first_ed_avg),  # non_first_ed_price_range
                first_ed_count,
                non_first_ed_count,
                first_ed_count + non_first_ed_count,  # total_offer_count
                first_ed_count / (first_ed_count + non_first_ed_count),  # first_ed_offer_ratio
            ]

            # Add metadata features (7 features)
            if meta_row:
                pub_year, page_count, binding = meta_row

                if pub_year:
                    features.extend([
                        pub_year,
                        2024 - pub_year,  # book_age
                        1.0 if pub_year >= 2015 else 0.0,  # is_recent
                        1.0 if pub_year < 1980 else 0.0,  # is_classic
                    ])
                else:
                    features.extend([0, 0, 0.0, 0.0])

                if page_count and page_count > 0:
                    features.extend([
                        page_count,
                        1.0 if page_count > 500 else 0.0,  # is_long_book
                    ])
                else:
                    features.extend([0, 0.0])

                if binding:
                    features.append(1.0 if 'hard' in binding.lower() else 0.0)  # is_hardcover
                else:
                    features.append(0.0)
            else:
                # No metadata - use defaults
                features.extend([0, 0, 0.0, 0.0, 0, 0.0, 0.0])

            return features

        except Exception as e:
            print(f"Error extracting edition premium features: {e}")
            return None


# Global singleton instance
_global_edition_premium_estimator: Optional[EditionPremiumEstimator] = None


def get_edition_premium_estimator(model_dir: Optional[Path] = None) -> EditionPremiumEstimator:
    """
    Get or create global edition premium estimator instance.

    Args:
        model_dir: Optional model directory (only used on first call)

    Returns:
        EditionPremiumEstimator instance
    """
    global _global_edition_premium_estimator

    if _global_edition_premium_estimator is None:
        _global_edition_premium_estimator = EditionPremiumEstimator(model_dir)

    return _global_edition_premium_estimator
