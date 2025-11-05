#!/usr/bin/env python3
"""
ML Model Monitoring System.

Provides real-time monitoring, drift detection, and performance tracking
for production ML models.
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import numpy as np
from collections import defaultdict
import json


@dataclass
class PredictionLog:
    """Log entry for a single prediction."""
    timestamp: str
    model_name: str
    platform: str
    prediction: float
    confidence_std: Optional[float]
    true_value: Optional[float]
    features: Dict[str, Any]
    latency_ms: float
    error: Optional[float] = None


@dataclass
class MonitoringMetrics:
    """Metrics for a monitoring window."""
    window_start: str
    window_end: str
    model_name: str
    n_predictions: int
    mean_prediction: float
    std_prediction: float
    mean_confidence_std: Optional[float]
    n_with_ground_truth: int
    mae: Optional[float]
    rmse: Optional[float]
    mean_latency_ms: float
    p95_latency_ms: float


@dataclass
class DriftAlert:
    """Alert for detected model drift."""
    timestamp: str
    model_name: str
    drift_type: str  # "feature_drift", "prediction_drift", "performance_drift"
    severity: str  # "warning", "critical"
    metric: str
    baseline_value: float
    current_value: float
    deviation_pct: float
    message: str


class ModelMonitor:
    """
    Production ML model monitoring system.

    Features:
    - Prediction logging with features and ground truth
    - Real-time performance metrics
    - Model drift detection (feature distribution, prediction distribution, performance)
    - Alerting for degraded performance
    - Historical tracking
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize monitor.

        Args:
            db_path: Path to monitoring database. If None, uses default location.
        """
        if db_path is None:
            db_path = Path.home() / ".isbn_lot_optimizer" / "ml_monitoring.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_database()

    @staticmethod
    def _convert_to_json_serializable(obj: Any) -> Any:
        """Convert numpy types to Python types for JSON serialization."""
        if isinstance(obj, dict):
            return {k: ModelMonitor._convert_to_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [ModelMonitor._convert_to_json_serializable(item) for item in obj]
        elif isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    def _init_database(self):
        """Initialize monitoring database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Prediction logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prediction_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                model_name TEXT NOT NULL,
                platform TEXT NOT NULL,
                prediction REAL NOT NULL,
                confidence_std REAL,
                true_value REAL,
                error REAL,
                features TEXT NOT NULL,
                latency_ms REAL NOT NULL
            )
        """)

        # Aggregated metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                model_name TEXT NOT NULL,
                n_predictions INTEGER NOT NULL,
                mean_prediction REAL NOT NULL,
                std_prediction REAL NOT NULL,
                mean_confidence_std REAL,
                n_with_ground_truth INTEGER NOT NULL,
                mae REAL,
                rmse REAL,
                mean_latency_ms REAL NOT NULL,
                p95_latency_ms REAL NOT NULL
            )
        """)

        # Drift alerts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS drift_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                model_name TEXT NOT NULL,
                drift_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                metric TEXT NOT NULL,
                baseline_value REAL NOT NULL,
                current_value REAL NOT NULL,
                deviation_pct REAL NOT NULL,
                message TEXT NOT NULL
            )
        """)

        # Baseline statistics table (for drift detection)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS baselines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT NOT NULL,
                feature_name TEXT,
                statistic_name TEXT NOT NULL,
                statistic_value REAL NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(model_name, feature_name, statistic_name)
            )
        """)

        # Create indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON prediction_logs(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_model ON prediction_logs(model_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_window ON metrics(window_start, window_end)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON drift_alerts(timestamp)")

        conn.commit()
        conn.close()

    def log_prediction(
        self,
        model_name: str,
        platform: str,
        prediction: float,
        features: Dict[str, Any],
        latency_ms: float,
        confidence_std: Optional[float] = None,
        true_value: Optional[float] = None
    ) -> int:
        """
        Log a prediction.

        Args:
            model_name: Name of the model
            platform: Platform (ebay, amazon, abebooks, general)
            prediction: Predicted value
            features: Feature dictionary
            latency_ms: Prediction latency in milliseconds
            confidence_std: Optional confidence standard deviation
            true_value: Optional ground truth value (for evaluation)

        Returns:
            Log entry ID
        """
        timestamp = datetime.now().isoformat()
        error = (prediction - true_value) if true_value is not None else None
        # Convert numpy types to Python types for JSON serialization
        features_serializable = self._convert_to_json_serializable(features)
        features_json = json.dumps(features_serializable)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO prediction_logs
            (timestamp, model_name, platform, prediction, confidence_std,
             true_value, error, features, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, model_name, platform, prediction, confidence_std,
              true_value, error, features_json, latency_ms))

        log_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return log_id

    def update_ground_truth(self, log_id: int, true_value: float):
        """
        Update a prediction log with ground truth value.

        Args:
            log_id: Prediction log ID
            true_value: Ground truth value
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get prediction
        cursor.execute("SELECT prediction FROM prediction_logs WHERE id = ?", (log_id,))
        result = cursor.fetchone()

        if result:
            prediction = result[0]
            error = prediction - true_value

            cursor.execute("""
                UPDATE prediction_logs
                SET true_value = ?, error = ?
                WHERE id = ?
            """, (true_value, error, log_id))

            conn.commit()

        conn.close()

    def compute_metrics(
        self,
        model_name: Optional[str] = None,
        hours: int = 24
    ) -> MonitoringMetrics:
        """
        Compute metrics for recent predictions.

        Args:
            model_name: Optional model to filter by
            hours: Number of hours to look back

        Returns:
            MonitoringMetrics object
        """
        window_end = datetime.now()
        window_start = window_end - timedelta(hours=hours)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Build query
        query = """
            SELECT
                prediction, confidence_std, true_value, error, latency_ms
            FROM prediction_logs
            WHERE timestamp >= ?
        """
        params = [window_start.isoformat()]

        if model_name:
            query += " AND model_name = ?"
            params.append(model_name)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return None

        # Extract data
        predictions = [row[0] for row in rows]
        confidence_stds = [row[1] for row in rows if row[1] is not None]
        errors = [row[3] for row in rows if row[3] is not None]
        latencies = [row[4] for row in rows]

        # Compute metrics
        metrics = MonitoringMetrics(
            window_start=window_start.isoformat(),
            window_end=window_end.isoformat(),
            model_name=model_name or "all",
            n_predictions=len(rows),
            mean_prediction=float(np.mean(predictions)),
            std_prediction=float(np.std(predictions)),
            mean_confidence_std=float(np.mean(confidence_stds)) if confidence_stds else None,
            n_with_ground_truth=len(errors),
            mae=float(np.mean(np.abs(errors))) if errors else None,
            rmse=float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
            mean_latency_ms=float(np.mean(latencies)),
            p95_latency_ms=float(np.percentile(latencies, 95))
        )

        return metrics

    def save_baseline(
        self,
        model_name: str,
        hours: int = 168  # 1 week
    ):
        """
        Save baseline statistics for drift detection.

        Args:
            model_name: Model name
            hours: Number of hours to use for baseline
        """
        window_start = datetime.now() - timedelta(hours=hours)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get predictions and features
        cursor.execute("""
            SELECT prediction, features
            FROM prediction_logs
            WHERE model_name = ? AND timestamp >= ?
        """, (model_name, window_start.isoformat()))

        rows = cursor.fetchall()

        if not rows:
            conn.close()
            return

        # Compute prediction distribution baseline
        predictions = np.array([row[0] for row in rows])
        timestamp = datetime.now().isoformat()

        baselines = [
            (model_name, None, "prediction_mean", float(np.mean(predictions)), timestamp),
            (model_name, None, "prediction_std", float(np.std(predictions)), timestamp),
            (model_name, None, "prediction_p25", float(np.percentile(predictions, 25)), timestamp),
            (model_name, None, "prediction_p50", float(np.percentile(predictions, 50)), timestamp),
            (model_name, None, "prediction_p75", float(np.percentile(predictions, 75)), timestamp),
        ]

        # Compute feature distribution baselines
        feature_stats = defaultdict(list)
        for row in rows:
            features = json.loads(row[1])
            for feature_name, value in features.items():
                if isinstance(value, (int, float)):
                    feature_stats[feature_name].append(value)

        for feature_name, values in feature_stats.items():
            values = np.array(values)
            baselines.extend([
                (model_name, feature_name, "mean", float(np.mean(values)), timestamp),
                (model_name, feature_name, "std", float(np.std(values)), timestamp),
                (model_name, feature_name, "p25", float(np.percentile(values, 25)), timestamp),
                (model_name, feature_name, "p50", float(np.percentile(values, 50)), timestamp),
                (model_name, feature_name, "p75", float(np.percentile(values, 75)), timestamp),
            ])

        # Save baselines (replace existing)
        cursor.execute("DELETE FROM baselines WHERE model_name = ?", (model_name,))
        cursor.executemany("""
            INSERT INTO baselines
            (model_name, feature_name, statistic_name, statistic_value, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, baselines)

        conn.commit()
        conn.close()

    def detect_drift(
        self,
        model_name: str,
        hours: int = 24,
        threshold_pct: float = 20.0
    ) -> List[DriftAlert]:
        """
        Detect model drift by comparing recent statistics to baseline.

        Args:
            model_name: Model name
            hours: Hours to look back for current statistics
            threshold_pct: Threshold percentage for drift alert

        Returns:
            List of drift alerts
        """
        window_start = datetime.now() - timedelta(hours=hours)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get baseline statistics
        cursor.execute("""
            SELECT feature_name, statistic_name, statistic_value
            FROM baselines
            WHERE model_name = ?
        """, (model_name,))

        baselines = {}
        for row in cursor.fetchall():
            key = (row[0], row[1])  # (feature_name, statistic_name)
            baselines[key] = row[2]

        if not baselines:
            conn.close()
            return []

        # Get recent predictions and features
        cursor.execute("""
            SELECT prediction, true_value, error, features
            FROM prediction_logs
            WHERE model_name = ? AND timestamp >= ?
        """, (model_name, window_start.isoformat()))

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return []

        alerts = []
        timestamp = datetime.now().isoformat()

        # Check prediction drift
        predictions = np.array([row[0] for row in rows])
        pred_stats = {
            "prediction_mean": float(np.mean(predictions)),
            "prediction_std": float(np.std(predictions)),
            "prediction_p50": float(np.percentile(predictions, 50)),
        }

        for stat_name, current_value in pred_stats.items():
            baseline_key = (None, stat_name)
            if baseline_key in baselines:
                baseline_value = baselines[baseline_key]

                # Avoid division by zero
                if abs(baseline_value) < 1e-6:
                    continue

                deviation_pct = abs((current_value - baseline_value) / baseline_value * 100)

                if deviation_pct > threshold_pct:
                    severity = "critical" if deviation_pct > threshold_pct * 2 else "warning"
                    alerts.append(DriftAlert(
                        timestamp=timestamp,
                        model_name=model_name,
                        drift_type="prediction_drift",
                        severity=severity,
                        metric=stat_name,
                        baseline_value=baseline_value,
                        current_value=current_value,
                        deviation_pct=deviation_pct,
                        message=f"Prediction distribution drift: {stat_name} changed by {deviation_pct:.1f}%"
                    ))

        # Check performance drift (if we have ground truth)
        errors = [row[2] for row in rows if row[2] is not None]
        if errors:
            current_mae = float(np.mean(np.abs(errors)))
            baseline_key = (None, "mae")

            # Use baseline MAE if available
            if baseline_key in baselines:
                baseline_mae = baselines[baseline_key]
                deviation_pct = abs((current_mae - baseline_mae) / baseline_mae * 100)

                if deviation_pct > threshold_pct:
                    severity = "critical" if deviation_pct > threshold_pct * 2 else "warning"
                    alerts.append(DriftAlert(
                        timestamp=timestamp,
                        model_name=model_name,
                        drift_type="performance_drift",
                        severity=severity,
                        metric="mae",
                        baseline_value=baseline_mae,
                        current_value=current_mae,
                        deviation_pct=deviation_pct,
                        message=f"Performance degradation: MAE increased by {deviation_pct:.1f}%"
                    ))

        # Check feature drift
        feature_stats = defaultdict(list)
        for row in rows:
            features = json.loads(row[3])
            for feature_name, value in features.items():
                if isinstance(value, (int, float)):
                    feature_stats[feature_name].append(value)

        for feature_name, values in feature_stats.items():
            values = np.array(values)
            current_mean = float(np.mean(values))

            baseline_key = (feature_name, "mean")
            if baseline_key in baselines:
                baseline_mean = baselines[baseline_key]

                # Avoid division by zero
                if abs(baseline_mean) < 1e-6:
                    continue

                deviation_pct = abs((current_mean - baseline_mean) / baseline_mean * 100)

                if deviation_pct > threshold_pct:
                    severity = "critical" if deviation_pct > threshold_pct * 2 else "warning"
                    alerts.append(DriftAlert(
                        timestamp=timestamp,
                        model_name=model_name,
                        drift_type="feature_drift",
                        severity=severity,
                        metric=f"{feature_name}_mean",
                        baseline_value=baseline_mean,
                        current_value=current_mean,
                        deviation_pct=deviation_pct,
                        message=f"Feature drift: {feature_name} mean changed by {deviation_pct:.1f}%"
                    ))

        # Save alerts to database
        if alerts:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            for alert in alerts:
                cursor.execute("""
                    INSERT INTO drift_alerts
                    (timestamp, model_name, drift_type, severity, metric,
                     baseline_value, current_value, deviation_pct, message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (alert.timestamp, alert.model_name, alert.drift_type,
                      alert.severity, alert.metric, alert.baseline_value,
                      alert.current_value, alert.deviation_pct, alert.message))

            conn.commit()
            conn.close()

        return alerts

    def get_recent_alerts(
        self,
        hours: int = 24,
        severity: Optional[str] = None,
        model_name: Optional[str] = None
    ) -> List[DriftAlert]:
        """
        Get recent drift alerts.

        Args:
            hours: Hours to look back
            severity: Optional severity filter ("warning", "critical")
            model_name: Optional model filter

        Returns:
            List of drift alerts
        """
        window_start = datetime.now() - timedelta(hours=hours)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = "SELECT * FROM drift_alerts WHERE timestamp >= ?"
        params = [window_start.isoformat()]

        if severity:
            query += " AND severity = ?"
            params.append(severity)

        if model_name:
            query += " AND model_name = ?"
            params.append(model_name)

        query += " ORDER BY timestamp DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        alerts = []
        for row in rows:
            alerts.append(DriftAlert(
                timestamp=row[1],
                model_name=row[2],
                drift_type=row[3],
                severity=row[4],
                metric=row[5],
                baseline_value=row[6],
                current_value=row[7],
                deviation_pct=row[8],
                message=row[9]
            ))

        return alerts

    def generate_report(
        self,
        model_name: Optional[str] = None,
        hours: int = 24
    ) -> str:
        """
        Generate monitoring report.

        Args:
            model_name: Optional model to filter by
            hours: Hours to look back

        Returns:
            Formatted report string
        """
        report = []
        report.append("=" * 80)
        report.append("ML MONITORING REPORT")
        report.append("=" * 80)

        # Metrics
        metrics = self.compute_metrics(model_name, hours)

        if metrics:
            report.append(f"\nMODEL: {metrics.model_name}")
            report.append(f"WINDOW: {metrics.window_start} to {metrics.window_end}")
            report.append("\nPREDICTION METRICS:")
            report.append(f"  Total predictions: {metrics.n_predictions}")
            report.append(f"  Mean prediction: ${metrics.mean_prediction:.2f}")
            report.append(f"  Std prediction: ${metrics.std_prediction:.2f}")

            if metrics.mean_confidence_std:
                report.append(f"  Mean confidence std: ${metrics.mean_confidence_std:.2f}")

            if metrics.n_with_ground_truth > 0:
                report.append(f"\nPERFORMANCE (n={metrics.n_with_ground_truth}):")
                report.append(f"  MAE: ${metrics.mae:.2f}")
                report.append(f"  RMSE: ${metrics.rmse:.2f}")

            report.append(f"\nLATENCY:")
            report.append(f"  Mean: {metrics.mean_latency_ms:.1f}ms")
            report.append(f"  P95: {metrics.p95_latency_ms:.1f}ms")
        else:
            report.append(f"\nNo predictions in the last {hours} hours")

        # Recent alerts
        alerts = self.get_recent_alerts(hours, model_name=model_name)

        if alerts:
            report.append("\n" + "=" * 80)
            report.append("DRIFT ALERTS")
            report.append("=" * 80)

            for alert in alerts:
                report.append(f"\n[{alert.severity.upper()}] {alert.timestamp}")
                report.append(f"  {alert.message}")
                report.append(f"  Baseline: {alert.baseline_value:.2f}, Current: {alert.current_value:.2f}")
        else:
            report.append(f"\nNo drift alerts in the last {hours} hours")

        report.append("\n" + "=" * 80)
        return "\n".join(report)
