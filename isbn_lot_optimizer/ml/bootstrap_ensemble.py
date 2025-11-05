#!/usr/bin/env python3
"""
Bootstrap Ensemble for Confidence Scoring.

Provides prediction confidence intervals by training multiple models on bootstrap samples.
"""

from typing import List, Tuple, NamedTuple
from pathlib import Path
import joblib
import numpy as np
import xgboost as xgb
from sklearn.preprocessing import StandardScaler


class PredictionWithConfidence(NamedTuple):
    """Prediction result with confidence metrics."""
    mean: float
    std: float
    confidence_interval_90: Tuple[float, float]
    confidence_interval_95: Tuple[float, float]
    individual_predictions: List[float]


class BootstrapEnsemble:
    """
    Bootstrap ensemble for confidence scoring.

    Trains N models on bootstrap samples and uses prediction variance
    as a confidence metric. Lower variance = higher confidence.

    Usage:
        # Training
        ensemble = BootstrapEnsemble(n_models=10)
        ensemble.fit(X_train, y_train, base_model_params)
        ensemble.save('models/bootstrap_ensemble/')

        # Prediction
        ensemble = BootstrapEnsemble.load('models/bootstrap_ensemble/')
        result = ensemble.predict(features)
        print(f"Prediction: ${result.mean:.2f} ± ${result.std:.2f}")
        print(f"90% CI: ${result.confidence_interval_90[0]:.2f} - ${result.confidence_interval_90[1]:.2f}")
    """

    def __init__(self, n_models: int = 10, random_state: int = 42):
        """
        Initialize bootstrap ensemble.

        Args:
            n_models: Number of bootstrap models to train
            random_state: Random seed for reproducibility
        """
        self.n_models = n_models
        self.random_state = random_state
        self.models: List[xgb.XGBRegressor] = []
        self.scaler: StandardScaler = None
        self.trained = False

    def fit(self, X: np.ndarray, y: np.ndarray, model_params: dict = None):
        """
        Train bootstrap ensemble.

        Args:
            X: Training features (n_samples, n_features)
            y: Training targets (n_samples,)
            model_params: XGBoost model parameters
        """
        if model_params is None:
            model_params = {
                'objective': 'reg:squarederror',
                'n_estimators': 200,
                'max_depth': 5,
                'learning_rate': 0.05,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'random_state': self.random_state,
                'n_jobs': -1,
            }

        # Fit scaler on full dataset
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # Train N bootstrap models
        print(f"Training {self.n_models} bootstrap models...")
        np.random.seed(self.random_state)

        for i in range(self.n_models):
            # Bootstrap sample (sample with replacement)
            n_samples = len(X_scaled)
            indices = np.random.choice(n_samples, size=n_samples, replace=True)
            X_boot = X_scaled[indices]
            y_boot = y[indices]

            # Train model
            model = xgb.XGBRegressor(**model_params)
            model.fit(X_boot, y_boot, verbose=False)
            self.models.append(model)

            if (i + 1) % 5 == 0:
                print(f"  Trained {i + 1}/{self.n_models} models")

        self.trained = True
        print(f"Bootstrap ensemble training complete!")

    def predict(self, X: np.ndarray) -> PredictionWithConfidence:
        """
        Predict with confidence intervals.

        Args:
            X: Features for prediction (n_features,) or (1, n_features)

        Returns:
            PredictionWithConfidence with mean, std, and confidence intervals
        """
        if not self.trained:
            raise ValueError("Ensemble not trained. Call fit() first or load() from disk.")

        # Handle single sample
        if X.ndim == 1:
            X = X.reshape(1, -1)

        # Scale features
        X_scaled = self.scaler.transform(X)

        # Get predictions from all models
        predictions = []
        for model in self.models:
            pred = model.predict(X_scaled)[0]
            predictions.append(pred)

        # Compute statistics
        predictions = np.array(predictions)
        mean = np.mean(predictions)
        std = np.std(predictions)

        # Confidence intervals (assuming normal distribution)
        # 90% CI: mean ± 1.645 * std
        # 95% CI: mean ± 1.96 * std
        ci_90 = (mean - 1.645 * std, mean + 1.645 * std)
        ci_95 = (mean - 1.96 * std, mean + 1.96 * std)

        return PredictionWithConfidence(
            mean=float(mean),
            std=float(std),
            confidence_interval_90=ci_90,
            confidence_interval_95=ci_95,
            individual_predictions=predictions.tolist()
        )

    def predict_batch(self, X: np.ndarray) -> List[PredictionWithConfidence]:
        """
        Predict batch with confidence intervals.

        Args:
            X: Features for prediction (n_samples, n_features)

        Returns:
            List of PredictionWithConfidence for each sample
        """
        if not self.trained:
            raise ValueError("Ensemble not trained. Call fit() first or load() from disk.")

        # Scale features
        X_scaled = self.scaler.transform(X)

        # Get predictions from all models (n_models, n_samples)
        all_predictions = []
        for model in self.models:
            preds = model.predict(X_scaled)
            all_predictions.append(preds)

        all_predictions = np.array(all_predictions)  # Shape: (n_models, n_samples)

        # Compute statistics for each sample
        results = []
        for i in range(X_scaled.shape[0]):
            predictions = all_predictions[:, i]
            mean = np.mean(predictions)
            std = np.std(predictions)

            ci_90 = (mean - 1.645 * std, mean + 1.645 * std)
            ci_95 = (mean - 1.96 * std, mean + 1.96 * std)

            results.append(PredictionWithConfidence(
                mean=float(mean),
                std=float(std),
                confidence_interval_90=ci_90,
                confidence_interval_95=ci_95,
                individual_predictions=predictions.tolist()
            ))

        return results

    def save(self, directory: Path):
        """
        Save ensemble to disk.

        Args:
            directory: Directory to save models
        """
        if not self.trained:
            raise ValueError("Cannot save untrained ensemble")

        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        # Save each model
        for i, model in enumerate(self.models):
            model_path = directory / f'model_{i}.pkl'
            joblib.dump(model, model_path)

        # Save scaler
        scaler_path = directory / 'scaler.pkl'
        joblib.dump(self.scaler, scaler_path)

        # Save metadata
        metadata = {
            'n_models': self.n_models,
            'random_state': self.random_state,
            'trained': self.trained,
        }
        metadata_path = directory / 'metadata.pkl'
        joblib.dump(metadata, metadata_path)

        print(f"Saved bootstrap ensemble to {directory}")

    @classmethod
    def load(cls, directory: Path) -> 'BootstrapEnsemble':
        """
        Load ensemble from disk.

        Args:
            directory: Directory containing saved models

        Returns:
            Loaded BootstrapEnsemble
        """
        directory = Path(directory)

        # Load metadata
        metadata_path = directory / 'metadata.pkl'
        metadata = joblib.load(metadata_path)

        # Create ensemble
        ensemble = cls(
            n_models=metadata['n_models'],
            random_state=metadata['random_state']
        )

        # Load models
        ensemble.models = []
        for i in range(metadata['n_models']):
            model_path = directory / f'model_{i}.pkl'
            model = joblib.load(model_path)
            ensemble.models.append(model)

        # Load scaler
        scaler_path = directory / 'scaler.pkl'
        ensemble.scaler = joblib.load(scaler_path)

        ensemble.trained = metadata['trained']

        print(f"Loaded bootstrap ensemble from {directory}")
        return ensemble

    def evaluate(self, X: np.ndarray, y: np.ndarray) -> dict:
        """
        Evaluate ensemble on test data.

        Args:
            X: Test features
            y: True targets

        Returns:
            Dictionary with evaluation metrics
        """
        predictions = self.predict_batch(X)

        means = np.array([p.mean for p in predictions])
        stds = np.array([p.std for p in predictions])

        # Prediction metrics
        mae = np.mean(np.abs(means - y))
        rmse = np.sqrt(np.mean((means - y) ** 2))

        # Calibration: check if true values fall within confidence intervals
        ci_90_coverage = np.mean([
            ci[0] <= true <= ci[1]
            for ci, true in zip([p.confidence_interval_90 for p in predictions], y)
        ])
        ci_95_coverage = np.mean([
            ci[0] <= true <= ci[1]
            for ci, true in zip([p.confidence_interval_95 for p in predictions], y)
        ])

        return {
            'mae': float(mae),
            'rmse': float(rmse),
            'mean_std': float(np.mean(stds)),
            'median_std': float(np.median(stds)),
            'ci_90_coverage': float(ci_90_coverage),
            'ci_95_coverage': float(ci_95_coverage),
            'expected_ci_90_coverage': 0.90,
            'expected_ci_95_coverage': 0.95,
        }
