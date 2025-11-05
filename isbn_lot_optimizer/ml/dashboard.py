#!/usr/bin/env python3
"""
ML Monitoring Dashboard.

Provides web-based visualization of model performance, drift alerts, and trends.
"""

from typing import Dict, List, Optional, Any
from pathlib import Path
import json
from datetime import datetime, timedelta
from .monitor import ModelMonitor


class MonitoringDashboard:
    """
    Web-based monitoring dashboard.

    Generates HTML dashboards with performance metrics, drift alerts, and trends.
    """

    def __init__(self, monitor: ModelMonitor):
        """
        Initialize dashboard.

        Args:
            monitor: ModelMonitor instance
        """
        self.monitor = monitor

    def get_dashboard_data(
        self,
        model_name: Optional[str] = None,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get dashboard data for API endpoint.

        Args:
            model_name: Optional model filter
            hours: Hours to look back

        Returns:
            Dict with dashboard data
        """
        # Get metrics
        metrics = self.monitor.compute_metrics(model_name, hours)

        # Get alerts
        alerts = self.monitor.get_recent_alerts(hours, model_name=model_name)

        # Get time series data (hourly buckets)
        time_series = self._get_time_series(model_name, hours)

        return {
            "metrics": metrics.__dict__ if metrics else None,
            "alerts": [
                {
                    "timestamp": alert.timestamp,
                    "model_name": alert.model_name,
                    "drift_type": alert.drift_type,
                    "severity": alert.severity,
                    "metric": alert.metric,
                    "baseline_value": alert.baseline_value,
                    "current_value": alert.current_value,
                    "deviation_pct": alert.deviation_pct,
                    "message": alert.message
                }
                for alert in alerts
            ],
            "time_series": time_series,
            "generated_at": datetime.now().isoformat()
        }

    def _get_time_series(
        self,
        model_name: Optional[str],
        hours: int
    ) -> Dict[str, List]:
        """
        Get time series data for charts.

        Args:
            model_name: Optional model filter
            hours: Hours to look back

        Returns:
            Dict with time series arrays
        """
        import sqlite3

        window_start = datetime.now() - timedelta(hours=hours)

        conn = sqlite3.connect(self.monitor.db_path)
        cursor = conn.cursor()

        # Build query
        query = """
            SELECT
                timestamp, prediction, error, latency_ms
            FROM prediction_logs
            WHERE timestamp >= ?
        """
        params = [window_start.isoformat()]

        if model_name:
            query += " AND model_name = ?"
            params.append(model_name)

        query += " ORDER BY timestamp"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "timestamps": [],
                "predictions": [],
                "errors": [],
                "latencies": []
            }

        return {
            "timestamps": [row[0] for row in rows],
            "predictions": [row[1] for row in rows],
            "errors": [row[2] if row[2] is not None else None for row in rows],
            "latencies": [row[3] for row in rows]
        }

    def generate_html(
        self,
        model_name: Optional[str] = None,
        hours: int = 24
    ) -> str:
        """
        Generate HTML dashboard.

        Args:
            model_name: Optional model filter
            hours: Hours to look back

        Returns:
            HTML string
        """
        data = self.get_dashboard_data(model_name, hours)
        metrics = data["metrics"]
        alerts = data["alerts"]
        time_series = data["time_series"]

        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ML Monitoring Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f5f5f5;
            padding: 20px;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        h1 {{
            color: #333;
            margin-bottom: 10px;
        }}

        .subtitle {{
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }}

        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .card {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}

        .card h2 {{
            font-size: 14px;
            color: #666;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .metric-value {{
            font-size: 32px;
            font-weight: bold;
            color: #333;
        }}

        .metric-label {{
            font-size: 12px;
            color: #999;
            margin-top: 5px;
        }}

        .alert {{
            background: white;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
            border-left: 4px solid #ff9800;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}

        .alert.warning {{
            border-left-color: #ff9800;
        }}

        .alert.critical {{
            border-left-color: #f44336;
        }}

        .alert-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }}

        .alert-badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
            text-transform: uppercase;
        }}

        .alert-badge.warning {{
            background: #fff3cd;
            color: #856404;
        }}

        .alert-badge.critical {{
            background: #f8d7da;
            color: #721c24;
        }}

        .alert-message {{
            color: #333;
            margin-bottom: 5px;
        }}

        .alert-details {{
            font-size: 12px;
            color: #666;
        }}

        .chart-container {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}

        .no-data {{
            text-align: center;
            color: #999;
            padding: 40px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>ML Monitoring Dashboard</h1>
        <div class="subtitle">
            Model: {metrics['model_name'] if metrics else 'N/A'} |
            Window: Last {hours} hours |
            Generated: {data['generated_at'][:19]}
        </div>
"""

        if metrics:
            # Metrics grid
            html += """
        <div class="grid">
            <div class="card">
                <h2>Predictions</h2>
                <div class="metric-value">{:,}</div>
                <div class="metric-label">Total predictions</div>
            </div>
            <div class="card">
                <h2>Mean Prediction</h2>
                <div class="metric-value">${:.2f}</div>
                <div class="metric-label">± ${:.2f}</div>
            </div>
""".format(
                metrics['n_predictions'],
                metrics['mean_prediction'],
                metrics['std_prediction']
            )

            if metrics['mae'] is not None:
                html += """
            <div class="card">
                <h2>MAE</h2>
                <div class="metric-value">${:.2f}</div>
                <div class="metric-label">n={:,} with ground truth</div>
            </div>
            <div class="card">
                <h2>RMSE</h2>
                <div class="metric-value">${:.2f}</div>
                <div class="metric-label">Root mean squared error</div>
            </div>
""".format(
                    metrics['mae'],
                    metrics['n_with_ground_truth'],
                    metrics['rmse']
                )

            html += """
            <div class="card">
                <h2>Latency (Mean)</h2>
                <div class="metric-value">{:.1f}ms</div>
                <div class="metric-label">P95: {:.1f}ms</div>
            </div>
""".format(
                metrics['mean_latency_ms'],
                metrics['p95_latency_ms']
            )

            if metrics['mean_confidence_std']:
                html += """
            <div class="card">
                <h2>Confidence</h2>
                <div class="metric-value">±${:.2f}</div>
                <div class="metric-label">Mean prediction std</div>
            </div>
""".format(metrics['mean_confidence_std'])

            html += """
        </div>
"""

        # Alerts section
        if alerts:
            html += """
        <div class="card">
            <h2>Recent Alerts ({} alerts)</h2>
            <div style="margin-top: 15px;">
""".format(len(alerts))

            for alert in alerts[:10]:  # Show top 10
                html += """
                <div class="alert {severity}">
                    <div class="alert-header">
                        <span class="alert-badge {severity}">{severity}</span>
                        <span style="font-size: 12px; color: #999;">{timestamp}</span>
                    </div>
                    <div class="alert-message">{message}</div>
                    <div class="alert-details">
                        Baseline: {baseline:.2f} → Current: {current:.2f}
                        ({deviation:+.1f}% change)
                    </div>
                </div>
""".format(
                    severity=alert['severity'],
                    timestamp=alert['timestamp'][:19],
                    message=alert['message'],
                    baseline=alert['baseline_value'],
                    current=alert['current_value'],
                    deviation=alert['deviation_pct']
                )

            html += """
            </div>
        </div>
"""

        # Time series charts
        if time_series['timestamps']:
            # Predictions over time
            html += """
        <div class="chart-container">
            <h2>Predictions Over Time</h2>
            <div id="predictions-chart"></div>
        </div>
"""

            # Errors over time (if available)
            errors = [e for e in time_series['errors'] if e is not None]
            if errors:
                html += """
        <div class="chart-container">
            <h2>Prediction Errors Over Time</h2>
            <div id="errors-chart"></div>
        </div>
"""

            # Latency over time
            html += """
        <div class="chart-container">
            <h2>Latency Over Time</h2>
            <div id="latency-chart"></div>
        </div>
"""

        if not metrics:
            html += """
        <div class="card">
            <div class="no-data">
                No data available for the selected time window.
            </div>
        </div>
"""

        html += """
    </div>

    <script>
        // Predictions chart
        const predictionsData = [{
            x: """ + json.dumps(time_series['timestamps']) + """,
            y: """ + json.dumps(time_series['predictions']) + """,
            type: 'scatter',
            mode: 'lines+markers',
            name: 'Prediction',
            line: {color: '#2196F3'}
        }];

        Plotly.newPlot('predictions-chart', predictionsData, {
            margin: {t: 10},
            height: 300,
            xaxis: {title: 'Timestamp'},
            yaxis: {title: 'Predicted Price ($)'}
        }, {responsive: true});

        // Errors chart
        const errorsTimestamps = [];
        const errorsValues = [];
        """ + json.dumps(time_series['timestamps']) + """.forEach((ts, i) => {
            const error = """ + json.dumps(time_series['errors']) + """[i];
            if (error !== null) {
                errorsTimestamps.push(ts);
                errorsValues.push(error);
            }
        });

        if (errorsValues.length > 0) {
            const errorsData = [{
                x: errorsTimestamps,
                y: errorsValues,
                type: 'scatter',
                mode: 'lines+markers',
                name: 'Error',
                line: {color: '#f44336'}
            }];

            Plotly.newPlot('errors-chart', errorsData, {
                margin: {t: 10},
                height: 300,
                xaxis: {title: 'Timestamp'},
                yaxis: {title: 'Error ($)', zeroline: true}
            }, {responsive: true});
        }

        // Latency chart
        const latencyData = [{
            x: """ + json.dumps(time_series['timestamps']) + """,
            y: """ + json.dumps(time_series['latencies']) + """,
            type: 'scatter',
            mode: 'lines+markers',
            name: 'Latency',
            line: {color: '#4CAF50'}
        }];

        Plotly.newPlot('latency-chart', latencyData, {
            margin: {t: 10},
            height: 300,
            xaxis: {title: 'Timestamp'},
            yaxis: {title: 'Latency (ms)'}
        }, {responsive: true});
    </script>
</body>
</html>
"""

        return html


def create_dashboard_route(app, monitor: ModelMonitor):
    """
    Add dashboard route to FastAPI app.

    Args:
        app: FastAPI application
        monitor: ModelMonitor instance

    Example:
        from fastapi import FastAPI, Query
        from fastapi.responses import HTMLResponse

        app = FastAPI()
        monitor = ModelMonitor()
        dashboard = MonitoringDashboard(monitor)

        @app.get("/ml/dashboard", response_class=HTMLResponse)
        async def ml_dashboard(
            model: str = Query(None, description="Model name filter"),
            hours: int = Query(24, description="Hours to look back")
        ):
            return dashboard.generate_html(model_name=model, hours=hours)

        @app.get("/ml/metrics")
        async def ml_metrics(
            model: str = Query(None, description="Model name filter"),
            hours: int = Query(24, description="Hours to look back")
        ):
            return dashboard.get_dashboard_data(model_name=model, hours=hours)
    """
    from fastapi import Query
    from fastapi.responses import HTMLResponse

    dashboard = MonitoringDashboard(monitor)

    @app.get("/ml/dashboard", response_class=HTMLResponse)
    async def ml_dashboard(
        model: str = Query(None, description="Model name filter"),
        hours: int = Query(24, description="Hours to look back")
    ):
        """Web-based ML monitoring dashboard."""
        return dashboard.generate_html(model_name=model, hours=hours)

    @app.get("/ml/metrics")
    async def ml_metrics(
        model: str = Query(None, description="Model name filter"),
        hours: int = Query(24, description="Hours to look back")
    ):
        """Get ML monitoring metrics as JSON."""
        return dashboard.get_dashboard_data(model_name=model, hours=hours)

    return app
