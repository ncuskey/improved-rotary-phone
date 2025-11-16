"""
ML-based price estimation model.

Main interface for loading and using trained ML models to estimate book prices.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import joblib
import numpy as np

from isbn_lot_optimizer.ml.feature_extractor import FeatureExtractor, FeatureVector
from shared.models import BookMetadata, EbayMarketStats, BookScouterResult

# Phase 1: Platform-specific routing feature flag
USE_ROUTING = os.environ.get("ML_USE_ROUTING", "1") == "1"


@dataclass
class PriceEstimate:
    """
    ML model price prediction with confidence and explainability.

    Attributes:
        price: Predicted price (None if insufficient data)
        confidence: Confidence score 0-1 based on feature completeness and model uncertainty
        prediction_interval: Tuple of (lower, upper) 90% confidence interval
        reason: Human-readable explanation of prediction or why it failed
        feature_importance: Top features that influenced this prediction
        model_version: Version of model used
    """
    price: Optional[float]
    confidence: float
    prediction_interval: Optional[Tuple[float, float]]
    reason: str
    feature_importance: Dict[str, float]
    model_version: str

    def __repr__(self) -> str:
        if self.price:
            return f"PriceEstimate(${self.price:.2f}, confidence={self.confidence:.2f})"
        return f"PriceEstimate(None, reason='{self.reason}')"


class MLPriceEstimator:
    """
    Machine learning-based price estimator.

    Loads a trained model and uses it to predict book prices based on
    extracted features from book metadata and market data.
    """

    def __init__(self, model_dir: Optional[Path] = None, monitor=None):
        """
        Initialize estimator by loading trained model.

        Args:
            model_dir: Directory containing model files. Defaults to
                      isbn_lot_optimizer/models/
            monitor: Optional ModelMonitor instance for prediction tracking
        """
        if model_dir is None:
            # Default to models/ directory in package
            package_dir = Path(__file__).parent.parent
            model_dir = package_dir / "models"

        self.model_dir = Path(model_dir)
        self.feature_extractor = FeatureExtractor()

        # Load model and metadata
        self.model = None
        self.scaler = None
        self.metadata = {}
        self.feature_importance = {}

        # Initialize prediction router if enabled
        self.router = None
        if USE_ROUTING:
            try:
                from isbn_lot_optimizer.ml.prediction_router import get_prediction_router
                self.router = get_prediction_router(monitor=monitor)
            except Exception as e:
                print(f"Warning: Could not initialize prediction router: {e}")

        self._load_model()

    def _load_model(self) -> None:
        """Load trained model, scaler, and metadata from disk."""
        model_path = self.model_dir / "price_v1.pkl"
        scaler_path = self.model_dir / "scaler_v1.pkl"
        metadata_path = self.model_dir / "metadata.json"

        if not model_path.exists():
            # Model not trained yet
            return

        try:
            self.model = joblib.load(model_path)
            if scaler_path.exists():
                self.scaler = joblib.load(scaler_path)

            if metadata_path.exists():
                with open(metadata_path, "r") as f:
                    self.metadata = json.load(f)
                    # Extract feature importance if available
                    if "feature_importance" in self.metadata:
                        self.feature_importance = self.metadata["feature_importance"]

        except Exception as e:
            print(f"Warning: Failed to load ML model: {e}")
            self.model = None

    def is_ready(self) -> bool:
        """Check if model is loaded and ready for predictions."""
        return self.model is not None

    def estimate_price(
        self,
        metadata: Optional[BookMetadata],
        market: Optional[EbayMarketStats],
        bookscouter: Optional[BookScouterResult],
        condition: str = "Good",
        abebooks: Optional[Dict] = None,
        bookfinder: Optional[Dict] = None,
        sold_listings: Optional[Dict] = None,
        signed: bool = False,
        first_edition: bool = False,
    ) -> PriceEstimate:
        """
        Estimate book price using ML model with intelligent routing.

        Args:
            metadata: Book metadata
            market: eBay market statistics
            bookscouter: BookScouter data
            condition: Book condition
            abebooks: AbeBooks pricing data (optional, enables specialist routing)
            bookfinder: BookFinder aggregator data (optional)
            sold_listings: Sold listings data (optional)
            signed: Whether book is signed
            first_edition: Whether book is first edition

        Returns:
            PriceEstimate with prediction and confidence
        """
        # Try platform-specific routing if enabled and data available
        if self.router:
            try:
                price, model_used, routing_info = self.router.predict(
                    metadata=metadata,
                    market=market,
                    bookscouter=bookscouter,
                    condition=condition,
                    abebooks=abebooks,
                    bookfinder=bookfinder,
                    sold_listings=sold_listings,
                    signed=signed,
                    first_edition=first_edition,
                )

                # Return result with routing metadata
                return PriceEstimate(
                    price=round(price, 2),
                    confidence=0.95 if model_used == 'abebooks_specialist' else 0.85 if model_used == 'ebay_specialist' else 0.70,
                    prediction_interval=None,
                    reason=f"Routed to {model_used} (MAE: ${routing_info['model_mae']:.2f})",
                    feature_importance={},
                    model_version=routing_info['model']
                )
            except Exception as e:
                # Fall through to unified model on routing errors
                pass
        if not self.is_ready():
            return PriceEstimate(
                price=None,
                confidence=0.0,
                prediction_interval=None,
                reason="ML model not trained yet",
                feature_importance={},
                model_version="none"
            )

        # Extract features
        features = self.feature_extractor.extract(metadata, market, bookscouter, condition)

        # Check if we have enough features
        if features.completeness < 0.3:
            return PriceEstimate(
                price=None,
                confidence=0.0,
                prediction_interval=None,
                reason=f"Insufficient data for ML prediction (only {features.completeness:.0%} of features available)",
                feature_importance={},
                model_version=self.metadata.get("version", "unknown")
            )

        # Apply feature scaling if available
        X = features.values.reshape(1, -1)
        if self.scaler is not None:
            X = self.scaler.transform(X)

        # Make prediction
        try:
            pred = self.model.predict(X)[0]
            pred = max(3.0, float(pred))  # Floor at $3

            # Calculate confidence based on feature completeness
            confidence = self._calculate_confidence(features)

            # Get prediction interval if model supports it
            interval = self._get_prediction_interval(X, pred, confidence)

            # Get feature importance for this prediction
            importance = self._explain_prediction(features)

            return PriceEstimate(
                price=round(pred, 2),
                confidence=confidence,
                prediction_interval=interval,
                reason=f"ML prediction based on {features.completeness:.0%} of features",
                feature_importance=importance,
                model_version=self.metadata.get("version", "v1")
            )

        except Exception as e:
            return PriceEstimate(
                price=None,
                confidence=0.0,
                prediction_interval=None,
                reason=f"Prediction failed: {str(e)}",
                feature_importance={},
                model_version=self.metadata.get("version", "unknown")
            )

    def _calculate_confidence(self, features: FeatureVector) -> float:
        """
        Calculate prediction confidence based on feature completeness.

        Args:
            features: Extracted feature vector

        Returns:
            Confidence score 0-1
        """
        # Base confidence from feature completeness
        confidence = features.completeness

        # Penalize if critical features are missing
        critical_features = ["log_amazon_rank", "ebay_sold_count", "page_count"]
        missing_critical = sum(1 for f in critical_features if f in features.missing_features)

        if missing_critical > 0:
            confidence *= (1.0 - 0.2 * missing_critical)

        return max(0.0, min(1.0, confidence))

    def _get_prediction_interval(
        self,
        X: np.ndarray,
        point_estimate: float,
        confidence: float
    ) -> Optional[Tuple[float, float]]:
        """
        Calculate 90% prediction interval.

        For models without native interval support, use a heuristic based on
        confidence score.

        Args:
            X: Feature array
            point_estimate: Point prediction
            confidence: Confidence score

        Returns:
            Tuple of (lower, upper) bounds or None
        """
        # Simple heuristic: wider interval for lower confidence
        # Typical book price error is ~$2, expand based on confidence
        margin = 2.0 * (1.0 / max(0.1, confidence))

        lower = max(3.0, point_estimate - margin)
        upper = point_estimate + margin

        return (round(lower, 2), round(upper, 2))

    def _explain_prediction(self, features: FeatureVector) -> Dict[str, float]:
        """
        Get top features that influenced this prediction.

        Args:
            features: Extracted feature vector

        Returns:
            Dict mapping feature name to importance score
        """
        # Use global feature importance from training
        if not self.feature_importance:
            return {}

        # Get top 5 features that are present (non-default)
        present_features = {
            name: importance
            for name, importance in self.feature_importance.items()
            if name not in features.missing_features
        }

        # Sort by importance and take top 5
        sorted_features = sorted(present_features.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_features[:5])

    def get_model_info(self) -> Dict:
        """Get information about loaded model."""
        if not self.is_ready():
            return {"status": "not_trained"}

        return {
            "status": "ready",
            "version": self.metadata.get("version", "v1"),
            "model_type": self.metadata.get("model_type", "unknown"),
            "train_date": self.metadata.get("train_date"),
            "train_samples": self.metadata.get("train_samples"),
            "test_mae": self.metadata.get("test_mae"),
            "test_rmse": self.metadata.get("test_rmse"),
            "feature_count": len(self.feature_extractor.get_feature_names()),
        }


# Global singleton instance
_global_estimator: Optional[MLPriceEstimator] = None


def get_ml_estimator(model_dir: Optional[Path] = None, monitor=None) -> MLPriceEstimator:
    """
    Get or create global ML estimator instance.

    Args:
        model_dir: Optional model directory (only used on first call)
        monitor: Optional ModelMonitor instance for prediction tracking (only used on first call)

    Returns:
        MLPriceEstimator instance
    """
    global _global_estimator

    if _global_estimator is None:
        _global_estimator = MLPriceEstimator(model_dir, monitor=monitor)

    return _global_estimator
