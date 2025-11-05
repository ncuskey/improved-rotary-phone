#!/usr/bin/env python3
"""
Model Evaluation Suite for ML price prediction models.

Provides comprehensive evaluation metrics, error analysis, and model comparison tools.
"""

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, mean_absolute_percentage_error


@dataclass
class EvaluationMetrics:
    """Container for evaluation metrics."""
    mae: float
    rmse: float
    r2: float
    mape: float
    median_absolute_error: float
    n_samples: int

    def __str__(self) -> str:
        return (
            f"MAE:  ${self.mae:.2f}\n"
            f"RMSE: ${self.rmse:.2f}\n"
            f"R²:   {self.r2:.3f}\n"
            f"MAPE: {self.mape:.1%}\n"
            f"MedAE: ${self.median_absolute_error:.2f}\n"
            f"Samples: {self.n_samples}"
        )


@dataclass
class ErrorAnalysis:
    """Container for error analysis results."""
    worst_predictions: List[Tuple[float, float, float]]  # (true, pred, error)
    best_predictions: List[Tuple[float, float, float]]
    overestimations: List[Tuple[float, float, float]]
    underestimations: List[Tuple[float, float, float]]
    error_percentiles: Dict[int, float]


class ModelEvaluator:
    """
    Comprehensive model evaluation suite.

    Provides:
    - Standard metrics (MAE, RMSE, R², MAPE)
    - Segmented analysis (by price range, category, etc.)
    - Error analysis (worst/best predictions, over/under-estimation)
    - Model comparison
    - Performance reports
    """

    @staticmethod
    def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> EvaluationMetrics:
        """
        Compute standard evaluation metrics.

        Args:
            y_true: True target values
            y_pred: Predicted values

        Returns:
            EvaluationMetrics object with all metrics
        """
        # Handle edge cases
        if len(y_true) == 0:
            return EvaluationMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0)

        # Compute metrics
        mae = mean_absolute_error(y_true, y_pred)
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        r2 = r2_score(y_true, y_pred)

        # MAPE (avoid division by zero)
        mask = y_true != 0
        if np.any(mask):
            mape = mean_absolute_percentage_error(y_true[mask], y_pred[mask])
        else:
            mape = 0.0

        # Median absolute error
        median_ae = np.median(np.abs(y_true - y_pred))

        return EvaluationMetrics(
            mae=float(mae),
            rmse=float(rmse),
            r2=float(r2),
            mape=float(mape),
            median_absolute_error=float(median_ae),
            n_samples=len(y_true)
        )

    @staticmethod
    def analyze_errors(
        y_true: np.ndarray,
        y_pred: np.ndarray,
        top_n: int = 10
    ) -> ErrorAnalysis:
        """
        Analyze prediction errors in detail.

        Args:
            y_true: True target values
            y_pred: Predicted values
            top_n: Number of top errors to return

        Returns:
            ErrorAnalysis object with detailed error breakdowns
        """
        errors = y_pred - y_true
        abs_errors = np.abs(errors)

        # Sort by absolute error
        error_indices = np.argsort(abs_errors)

        # Worst predictions (highest absolute error)
        worst_idx = error_indices[-top_n:][::-1]
        worst = [(float(y_true[i]), float(y_pred[i]), float(errors[i]))
                 for i in worst_idx]

        # Best predictions (lowest absolute error)
        best_idx = error_indices[:top_n]
        best = [(float(y_true[i]), float(y_pred[i]), float(errors[i]))
                for i in best_idx]

        # Overestimations (predicted > true)
        over_mask = errors > 0
        if np.any(over_mask):
            over_errors = errors[over_mask]
            over_true = y_true[over_mask]
            over_pred = y_pred[over_mask]
            over_indices = np.argsort(over_errors)[-top_n:][::-1]
            overestimations = [
                (float(over_true[i]), float(over_pred[i]), float(over_errors[i]))
                for i in over_indices
            ]
        else:
            overestimations = []

        # Underestimations (predicted < true)
        under_mask = errors < 0
        if np.any(under_mask):
            under_errors = errors[under_mask]
            under_true = y_true[under_mask]
            under_pred = y_pred[under_mask]
            under_indices = np.argsort(np.abs(under_errors))[-top_n:][::-1]
            underestimations = [
                (float(under_true[i]), float(under_pred[i]), float(under_errors[i]))
                for i in under_indices
            ]
        else:
            underestimations = []

        # Error percentiles
        percentiles = {
            10: float(np.percentile(abs_errors, 10)),
            25: float(np.percentile(abs_errors, 25)),
            50: float(np.percentile(abs_errors, 50)),
            75: float(np.percentile(abs_errors, 75)),
            90: float(np.percentile(abs_errors, 90)),
            95: float(np.percentile(abs_errors, 95)),
            99: float(np.percentile(abs_errors, 99)),
        }

        return ErrorAnalysis(
            worst_predictions=worst,
            best_predictions=best,
            overestimations=overestimations,
            underestimations=underestimations,
            error_percentiles=percentiles
        )

    @staticmethod
    def segment_by_price_range(
        y_true: np.ndarray,
        y_pred: np.ndarray,
        ranges: Optional[List[Tuple[float, float]]] = None
    ) -> Dict[str, EvaluationMetrics]:
        """
        Evaluate performance across different price ranges.

        Args:
            y_true: True target values
            y_pred: Predicted values
            ranges: List of (min, max) price ranges. If None, uses default ranges.

        Returns:
            Dict mapping range labels to metrics
        """
        if ranges is None:
            # Default price ranges for books
            ranges = [
                (0, 10),
                (10, 20),
                (20, 50),
                (50, 100),
                (100, float('inf'))
            ]

        results = {}
        for min_price, max_price in ranges:
            # Find samples in this range
            mask = (y_true >= min_price) & (y_true < max_price)

            if not np.any(mask):
                continue

            # Compute metrics for this segment
            segment_true = y_true[mask]
            segment_pred = y_pred[mask]
            metrics = ModelEvaluator.compute_metrics(segment_true, segment_pred)

            # Create label
            if max_price == float('inf'):
                label = f"${min_price:.0f}+"
            else:
                label = f"${min_price:.0f}-${max_price:.0f}"

            results[label] = metrics

        return results

    @staticmethod
    def compare_models(
        y_true: np.ndarray,
        predictions: Dict[str, np.ndarray]
    ) -> Dict[str, EvaluationMetrics]:
        """
        Compare multiple models on the same test set.

        Args:
            y_true: True target values
            predictions: Dict mapping model names to their predictions

        Returns:
            Dict mapping model names to their metrics
        """
        results = {}
        for model_name, y_pred in predictions.items():
            metrics = ModelEvaluator.compute_metrics(y_true, y_pred)
            results[model_name] = metrics

        return results

    @staticmethod
    def generate_report(
        y_true: np.ndarray,
        y_pred: np.ndarray,
        model_name: str = "Model",
        include_error_analysis: bool = True,
        include_segmentation: bool = True
    ) -> str:
        """
        Generate comprehensive evaluation report.

        Args:
            y_true: True target values
            y_pred: Predicted values
            model_name: Name of the model
            include_error_analysis: Whether to include detailed error analysis
            include_segmentation: Whether to include price range segmentation

        Returns:
            Formatted report string
        """
        report = []
        report.append("=" * 80)
        report.append(f"{model_name.upper()} EVALUATION REPORT")
        report.append("=" * 80)

        # Overall metrics
        report.append("\nOVERALL METRICS")
        report.append("-" * 80)
        metrics = ModelEvaluator.compute_metrics(y_true, y_pred)
        report.append(str(metrics))

        # Segmentation by price range
        if include_segmentation:
            report.append("\n" + "=" * 80)
            report.append("PERFORMANCE BY PRICE RANGE")
            report.append("=" * 80)

            segments = ModelEvaluator.segment_by_price_range(y_true, y_pred)
            for range_label, segment_metrics in segments.items():
                report.append(f"\n{range_label}:")
                report.append(f"  MAE:  ${segment_metrics.mae:.2f}")
                report.append(f"  RMSE: ${segment_metrics.rmse:.2f}")
                report.append(f"  R²:   {segment_metrics.r2:.3f}")
                report.append(f"  Samples: {segment_metrics.n_samples}")

        # Error analysis
        if include_error_analysis:
            report.append("\n" + "=" * 80)
            report.append("ERROR ANALYSIS")
            report.append("=" * 80)

            error_analysis = ModelEvaluator.analyze_errors(y_true, y_pred, top_n=5)

            # Error percentiles
            report.append("\nError Percentiles:")
            for pct, error in error_analysis.error_percentiles.items():
                report.append(f"  {pct}th: ${error:.2f}")

            # Worst predictions
            report.append("\nWorst 5 Predictions:")
            for i, (true, pred, error) in enumerate(error_analysis.worst_predictions, 1):
                report.append(f"  {i}. True: ${true:.2f}, Pred: ${pred:.2f}, Error: ${error:+.2f}")

            # Best predictions
            report.append("\nBest 5 Predictions:")
            for i, (true, pred, error) in enumerate(error_analysis.best_predictions, 1):
                report.append(f"  {i}. True: ${true:.2f}, Pred: ${pred:.2f}, Error: ${error:+.2f}")

            # Overestimations
            if error_analysis.overestimations:
                report.append("\nTop 3 Overestimations:")
                for i, (true, pred, error) in enumerate(error_analysis.overestimations[:3], 1):
                    report.append(f"  {i}. True: ${true:.2f}, Pred: ${pred:.2f}, Over by: ${error:.2f}")

            # Underestimations
            if error_analysis.underestimations:
                report.append("\nTop 3 Underestimations:")
                for i, (true, pred, error) in enumerate(error_analysis.underestimations[:3], 1):
                    report.append(f"  {i}. True: ${true:.2f}, Pred: ${pred:.2f}, Under by: ${abs(error):.2f}")

        report.append("\n" + "=" * 80)

        return "\n".join(report)

    @staticmethod
    def generate_comparison_report(
        y_true: np.ndarray,
        predictions: Dict[str, np.ndarray]
    ) -> str:
        """
        Generate model comparison report.

        Args:
            y_true: True target values
            predictions: Dict mapping model names to their predictions

        Returns:
            Formatted comparison report
        """
        report = []
        report.append("=" * 80)
        report.append("MODEL COMPARISON REPORT")
        report.append("=" * 80)

        # Compute metrics for all models
        results = ModelEvaluator.compare_models(y_true, predictions)

        # Sort by MAE (best first)
        sorted_models = sorted(results.items(), key=lambda x: x[1].mae)

        # Create comparison table
        report.append("\nModel                     MAE      RMSE     R²      MAPE    Samples")
        report.append("-" * 80)

        for model_name, metrics in sorted_models:
            report.append(
                f"{model_name:20s}  ${metrics.mae:6.2f}  ${metrics.rmse:6.2f}  "
                f"{metrics.r2:6.3f}  {metrics.mape:5.1%}  {metrics.n_samples:7d}"
            )

        # Best model
        best_model, best_metrics = sorted_models[0]
        report.append("\n" + "=" * 80)
        report.append(f"BEST MODEL: {best_model}")
        report.append(f"  MAE: ${best_metrics.mae:.2f}")
        report.append(f"  Improvement over worst: {((sorted_models[-1][1].mae - best_metrics.mae) / sorted_models[-1][1].mae * 100):.1f}%")
        report.append("=" * 80)

        return "\n".join(report)
