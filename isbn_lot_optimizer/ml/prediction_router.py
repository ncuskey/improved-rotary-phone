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
import time

from isbn_lot_optimizer.ml.feature_extractor import PlatformFeatureExtractor
from shared.models import BookMetadata, EbayMarketStats, BookScouterResult

logger = logging.getLogger(__name__)


class PredictionRouter:
    """
    Routes book price predictions to the best available model.

    Uses platform-specific specialist models when high-quality data is available,
    otherwise falls back to unified model.

    Current specialists:
    - AbeBooks: MAE $0.06, R² 0.999 (98.4% catalog coverage)
    - eBay: MAE $3.03, R² 0.469 (72% catalog coverage)
    """

    def __init__(self, model_dir: Optional[Path] = None, monitor=None):
        """
        Initialize prediction router with models.

        Args:
            model_dir: Directory containing model files (default: ~/ISBN/isbn_lot_optimizer/models)
            monitor: Optional ModelMonitor instance for prediction tracking
        """
        if model_dir is None:
            model_dir = Path.home() / "ISBN" / "isbn_lot_optimizer" / "models"

        self.model_dir = Path(model_dir)
        self.extractor = PlatformFeatureExtractor()
        self.monitor = monitor

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

        # Load eBay specialist
        try:
            ebay_dir = self.model_dir / "stacking"
            self.ebay_model = joblib.load(ebay_dir / "ebay_model.pkl")
            self.ebay_scaler = joblib.load(ebay_dir / "ebay_scaler.pkl")
            self.has_ebay_specialist = True
            logger.info("eBay specialist model loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load eBay specialist: {e}")
            self.has_ebay_specialist = False

        # Track routing statistics
        self.stats = {
            'total_predictions': 0,
            'abebooks_routed': 0,
            'ebay_routed': 0,
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
        # Start timing
        start_time = time.time()

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
                    'model_mae': 0.06,
                    'features': 28,
                    'confidence': 'high',
                }

                # Log to monitor if available
                if self.monitor:
                    self._log_prediction(
                        model_name='abebooks_specialist',
                        price=price,
                        metadata=metadata,
                        market=market,
                        bookscouter=bookscouter,
                        condition=condition,
                        abebooks=abebooks,
                        bookfinder=bookfinder,
                        sold_listings=sold_listings,
                        start_time=start_time,
                    )

                return price, 'abebooks_specialist', routing_info

            except Exception as e:
                logger.warning(f"AbeBooks specialist failed, falling back: {e}")

        # Check if we can route to eBay specialist
        if self._can_use_ebay(market):
            try:
                price = self._predict_ebay(
                    metadata, market, bookscouter, condition,
                    abebooks, bookfinder, sold_listings
                )
                self.stats['ebay_routed'] += 1

                routing_info = {
                    'model': 'ebay_specialist',
                    'model_mae': 3.03,
                    'features': 20,
                    'confidence': 'high',
                }

                # Log to monitor if available
                if self.monitor:
                    self._log_prediction(
                        model_name='ebay_specialist',
                        price=price,
                        metadata=metadata,
                        market=market,
                        bookscouter=bookscouter,
                        condition=condition,
                        abebooks=abebooks,
                        bookfinder=bookfinder,
                        sold_listings=sold_listings,
                        start_time=start_time,
                    )

                return price, 'ebay_specialist', routing_info

            except Exception as e:
                logger.warning(f"eBay specialist failed, falling back to unified: {e}")

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

        # Log to monitor if available
        if self.monitor:
            self._log_prediction(
                model_name='unified',
                price=price,
                metadata=metadata,
                market=market,
                bookscouter=bookscouter,
                condition=condition,
                abebooks=abebooks,
                bookfinder=bookfinder,
                sold_listings=sold_listings,
                start_time=start_time,
            )

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

    def _can_use_ebay(self, market: Optional[EbayMarketStats]) -> bool:
        """
        Check if book has sufficient eBay data for specialist model.

        Requires:
        - eBay specialist loaded
        - Market data present
        - Either active median price OR sold comps median available
        """
        if not self.has_ebay_specialist:
            return False

        if not market:
            return False

        # Check for either active or sold comps data
        has_active = hasattr(market, 'active_median_price') and market.active_median_price and market.active_median_price > 0
        has_sold_comps = hasattr(market, 'sold_comps_median') and market.sold_comps_median and market.sold_comps_median > 0

        return has_active or has_sold_comps

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

    def _predict_ebay(
        self,
        metadata: Optional[BookMetadata],
        market: Optional[EbayMarketStats],
        bookscouter: Optional[BookScouterResult],
        condition: str,
        abebooks: Optional[Dict],
        bookfinder: Optional[Dict],
        sold_listings: Optional[Dict],
    ) -> float:
        """Predict using eBay specialist model."""
        # Extract platform-specific features
        features = self.extractor.extract_for_platform(
            platform='ebay',
            metadata=metadata,
            market=market,
            bookscouter=bookscouter,
            condition=condition,
            abebooks=abebooks,
            bookfinder=bookfinder,
            sold_listings=sold_listings,
        )

        # Get feature names for platform
        feature_names = PlatformFeatureExtractor.get_platform_feature_names('ebay')

        # Build feature vector
        X = np.array([features.values])

        # Scale and predict
        X_scaled = self.ebay_scaler.transform(X)
        prediction = self.ebay_model.predict(X_scaled)[0]

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

    def _log_prediction(
        self,
        model_name: str,
        price: float,
        metadata: Optional[BookMetadata],
        market: Optional[EbayMarketStats],
        bookscouter: Optional[BookScouterResult],
        condition: str,
        abebooks: Optional[Dict],
        bookfinder: Optional[Dict],
        sold_listings: Optional[Dict],
        start_time: float,
    ):
        """Log prediction to monitor."""
        try:
            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000

            # Extract key features for monitoring
            features = {
                'condition': condition,
                'has_metadata': metadata is not None,
                'has_market': market is not None,
                'has_bookscouter': bookscouter is not None,
                'has_abebooks': abebooks is not None and abebooks.get('abebooks_avg_price', 0) > 0,
                'has_bookfinder': bookfinder is not None,
                'has_sold_listings': sold_listings is not None,
            }

            # Add numeric features if available
            if metadata:
                features['year'] = metadata.published_year or 0
                features['page_count'] = metadata.page_count or 0

            if market:
                features['active_count'] = market.active_count
                features['sold_count'] = market.sold_count
                features['sold_avg_price'] = market.sold_avg_price or 0
                features['active_avg_price'] = market.active_avg_price or 0

            if abebooks:
                features['abebooks_avg'] = abebooks.get('abebooks_avg_price', 0)
                features['abebooks_count'] = abebooks.get('abebooks_count', 0)

            # Determine platform based on which specialist was used
            if model_name == 'abebooks_specialist':
                platform = 'abebooks'
            elif model_name == 'ebay_specialist':
                platform = 'ebay'
            else:
                platform = 'general'

            # Log to monitor
            self.monitor.log_prediction(
                model_name=model_name,
                platform=platform,
                prediction=price,
                features=features,
                latency_ms=latency_ms,
            )
        except Exception as e:
            # Don't fail predictions if monitoring fails
            logger.warning(f"Failed to log prediction to monitor: {e}")

    def get_routing_stats(self) -> Dict:
        """Get routing statistics."""
        total = self.stats['total_predictions']
        if total == 0:
            return self.stats.copy()

        stats_with_pct = self.stats.copy()
        stats_with_pct['abebooks_pct'] = round(100 * self.stats['abebooks_routed'] / total, 2)
        stats_with_pct['ebay_pct'] = round(100 * self.stats['ebay_routed'] / total, 2)
        stats_with_pct['unified_pct'] = round(100 * self.stats['unified_fallback'] / total, 2)

        return stats_with_pct

    def reset_stats(self):
        """Reset routing statistics."""
        self.stats = {
            'total_predictions': 0,
            'abebooks_routed': 0,
            'ebay_routed': 0,
            'unified_fallback': 0,
        }


def get_prediction_router(monitor=None) -> PredictionRouter:
    """
    Get singleton prediction router instance.

    Args:
        monitor: Optional ModelMonitor instance for prediction tracking

    Returns:
        PredictionRouter instance
    """
    if not hasattr(get_prediction_router, '_instance'):
        get_prediction_router._instance = PredictionRouter(monitor=monitor)

    return get_prediction_router._instance
