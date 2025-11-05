"""
Intelligent prediction routing for platform-specific ML models.

Routes predictions to specialist models when appropriate data is available,
falling back to unified model when necessary.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Tuple
import joblib
import numpy as np

from isbn_lot_optimizer.ml.feature_extractor import PlatformFeatureExtractor
from shared.models import BookMetadata, EbayMarketStats, BookScouterResult

logger = logging.getLogger(__name__)


class PredictionRouter:
    """
    Routes book price predictions to the best available model.

    Uses platform-specific specialist models when high-quality data is available,
    otherwise falls back to unified model.

    Current specialists:
    - AbeBooks: MAE $0.29, R² 0.863 (98.4% catalog coverage)
    """

    def __init__(self, model_dir: Optional[Path] = None):
        """
        Initialize prediction router with models.

        Args:
            model_dir: Directory containing model files (default: ~/ISBN/isbn_lot_optimizer/models)
        """
        if model_dir is None:
            model_dir = Path.home() / "ISBN" / "isbn_lot_optimizer" / "models"

        self.model_dir = Path(model_dir)
        self.extractor = PlatformFeatureExtractor()

        # Load unified model (fallback)
        self.unified_model = joblib.load(self.model_dir / "price_v1.pkl")
        self.unified_scaler = joblib.load(self.model_dir / "scaler_v1.pkl")

        # Load AbeBooks specialist
        try:
            abebooks_dir = self.model_dir / "stacking"
            self.abebooks_model = joblib.load(abebooks_dir / "abebooks_model.pkl")
            self.abebooks_scaler = joblib.load(abebooks_dir / "abebooks_scaler.pkl")
            self.has_abebooks_specialist = True
            logger.info("AbeBooks specialist model loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load AbeBooks specialist: {e}")
            self.has_abebooks_specialist = False

        # Track routing statistics
        self.stats = {
            'total_predictions': 0,
            'abebooks_routed': 0,
            'unified_fallback': 0,
        }

    def predict(
        self,
        metadata: Optional[BookMetadata],
        market: Optional[EbayMarketStats],
        bookscouter: Optional[BookScouterResult],
        condition: str = "Good",
        abebooks: Optional[Dict] = None,
        bookfinder: Optional[Dict] = None,
        sold_listings: Optional[Dict] = None,
    ) -> Tuple[float, str, Dict]:
        """
        Predict book price using best available model.

        Args:
            metadata: Book metadata
            market: eBay market statistics
            bookscouter: BookScouter data
            condition: Book condition
            abebooks: AbeBooks pricing data
            bookfinder: BookFinder aggregator data
            sold_listings: Sold listings data

        Returns:
            Tuple of (predicted_price, model_used, routing_info)
        """
        self.stats['total_predictions'] += 1

        # Check if we can route to AbeBooks specialist
        if self._can_use_abebooks(abebooks):
            try:
                price = self._predict_abebooks(
                    metadata, market, bookscouter, condition,
                    abebooks, bookfinder, sold_listings
                )
                self.stats['abebooks_routed'] += 1

                routing_info = {
                    'model': 'abebooks_specialist',
                    'model_mae': 0.29,
                    'features': 28,
                    'confidence': 'high',
                }

                return price, 'abebooks_specialist', routing_info

            except Exception as e:
                logger.warning(f"AbeBooks specialist failed, falling back to unified: {e}")

        # Fallback to unified model
        price = self._predict_unified(
            metadata, market, bookscouter, condition,
            abebooks, bookfinder, sold_listings
        )
        self.stats['unified_fallback'] += 1

        routing_info = {
            'model': 'unified',
            'model_mae': 3.36,
            'features': 91,
            'confidence': 'medium',
        }

        return price, 'unified', routing_info

    def _can_use_abebooks(self, abebooks: Optional[Dict]) -> bool:
        """
        Check if book has sufficient AbeBooks data for specialist model.

        Requires:
        - AbeBooks specialist loaded
        - AbeBooks data present
        - Average price > 0
        """
        if not self.has_abebooks_specialist:
            return False

        if not abebooks:
            return False

        avg_price = abebooks.get('abebooks_avg_price', 0)
        if avg_price <= 0:
            return False

        return True

    def _predict_abebooks(
        self,
        metadata: Optional[BookMetadata],
        market: Optional[EbayMarketStats],
        bookscouter: Optional[BookScouterResult],
        condition: str,
        abebooks: Dict,
        bookfinder: Optional[Dict],
        sold_listings: Optional[Dict],
    ) -> float:
        """Predict using AbeBooks specialist model."""
        # Extract platform-specific features
        features = self.extractor.extract_for_platform(
            platform='abebooks',
            metadata=metadata,
            market=market,
            bookscouter=bookscouter,
            condition=condition,
            abebooks=abebooks,
            bookfinder=bookfinder,
            sold_listings=sold_listings,
        )

        # Get feature names for platform
        feature_names = PlatformFeatureExtractor.get_platform_feature_names('abebooks')

        # Build feature vector
        X = np.array([features.values])

        # Scale and predict
        X_scaled = self.abebooks_scaler.transform(X)
        prediction = self.abebooks_model.predict(X_scaled)[0]

        return max(0.01, prediction)  # Ensure positive price

    def _predict_unified(
        self,
        metadata: Optional[BookMetadata],
        market: Optional[EbayMarketStats],
        bookscouter: Optional[BookScouterResult],
        condition: str,
        abebooks: Optional[Dict],
        bookfinder: Optional[Dict],
        sold_listings: Optional[Dict],
    ) -> float:
        """Predict using unified model."""
        # Extract all features
        features = self.extractor.extract(
            metadata=metadata,
            market=market,
            bookscouter=bookscouter,
            condition=condition,
            abebooks=abebooks,
            bookfinder=bookfinder,
            sold_listings=sold_listings,
        )

        # Build feature vector
        X = np.array([features.values])

        # Scale and predict
        X_scaled = self.unified_scaler.transform(X)
        prediction = self.unified_model.predict(X_scaled)[0]

        return max(0.01, prediction)  # Ensure positive price

    def get_routing_stats(self) -> Dict:
        """Get routing statistics."""
        total = self.stats['total_predictions']
        if total == 0:
            return self.stats.copy()

        stats_with_pct = self.stats.copy()
        stats_with_pct['abebooks_pct'] = round(100 * self.stats['abebooks_routed'] / total, 2)
        stats_with_pct['unified_pct'] = round(100 * self.stats['unified_fallback'] / total, 2)

        return stats_with_pct

    def reset_stats(self):
        """Reset routing statistics."""
        self.stats = {
            'total_predictions': 0,
            'abebooks_routed': 0,
            'unified_fallback': 0,
        }


def get_prediction_router() -> PredictionRouter:
    """
    Get singleton prediction router instance.

    Returns:
        PredictionRouter instance
    """
    if not hasattr(get_prediction_router, '_instance'):
        get_prediction_router._instance = PredictionRouter()

    return get_prediction_router._instance
