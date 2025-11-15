#!/usr/bin/env python3
"""
Continuous Training Monitor - Polls for new training data and triggers retraining.

Checks every 10 minutes for new quality books. If found, triggers full model retraining
via the orchestrator script.

Usage:
    # Run in foreground (for testing)
    python3 scripts/continuous_training_monitor.py

    # Run in background (daemon mode)
    python3 scripts/continuous_training_monitor.py --daemon

    # Check status
    python3 scripts/continuous_training_monitor.py --status

    # Stop daemon
    python3 scripts/continuous_training_monitor.py --stop
"""

import argparse
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.training_detector import TrainingDataDetector
from scripts.retrain_all_models import TrainingOrchestrator


class ContinuousTrainingMonitor:
    """Continuously monitors for new training data and triggers retraining."""

    def __init__(
        self,
        check_interval_seconds: int = 600,  # 10 minutes
        min_quality_score: float = 0.6,
        min_new_books: int = 1,
    ):
        """
        Initialize the monitor.

        Args:
            check_interval_seconds: Time between checks (default: 600s = 10min)
            min_quality_score: Minimum quality score for training (default: 0.6)
            min_new_books: Minimum new books to trigger training (default: 1)
        """
        self.check_interval = check_interval_seconds
        self.min_quality_score = min_quality_score
        self.min_new_books = min_new_books
        self.detector = TrainingDataDetector()
        self.orchestrator = TrainingOrchestrator()
        self.running = True
        self.pid_file = Path.home() / ".isbn_lot_optimizer" / "training_monitor.pid"
        self.log_file = Path.home() / ".isbn_lot_optimizer" / "training_monitor.log"

    def start(self, daemon: bool = False):
        """
        Start the monitoring loop.

        Args:
            daemon: If True, run as background daemon
        """
        if daemon:
            self._daemonize()

        # Write PID file
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.pid_file, "w") as f:
            import os
            f.write(str(os.getpid()))

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        self._log("=" * 70)
        self._log("Continuous Training Monitor Started")
        self._log("=" * 70)
        self._log(f"Check interval: {self.check_interval}s ({self.check_interval/60:.1f} minutes)")
        self._log(f"Min quality score: {self.min_quality_score}")
        self._log(f"Min new books: {self.min_new_books}")
        self._log()

        # Main monitoring loop
        check_count = 0
        training_count = 0

        try:
            while self.running:
                check_count += 1
                self._log(f"[Check #{check_count}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                # Check for new training data
                try:
                    new_books = self.detector.get_new_training_books_count(self.min_quality_score)
                    self._log(f"  New quality books: {new_books}")

                    if new_books >= self.min_new_books:
                        self._log(f"  ✅ Triggering training run #{training_count + 1}...")
                        self._log()

                        # Run training
                        result = self.orchestrator.run_full_training()

                        if result["success"]:
                            training_count += 1
                            elapsed = result["elapsed_seconds"]
                            self._log()
                            self._log(f"  ✅ Training completed successfully ({elapsed:.1f}s)")
                            self._log(f"  Backup version: {result['backup_version']}")
                        else:
                            self._log()
                            self._log(f"  ❌ Training failed: {result.get('error', 'Unknown error')}")
                            self._log("  Will retry on next check cycle")

                        self._log()
                    else:
                        self._log(f"  💤 No new data (need {self.min_new_books}, have {new_books})")

                except Exception as e:
                    self._log(f"  ❌ Error during check: {e}")
                    import traceback
                    self._log(traceback.format_exc())

                self._log()

                # Wait for next check
                if self.running:
                    self._log(f"  Next check in {self.check_interval}s...")
                    time.sleep(self.check_interval)

        except Exception as e:
            self._log(f"Fatal error: {e}")
            import traceback
            self._log(traceback.format_exc())
        finally:
            self._cleanup()

    def _daemonize(self):
        """Fork the process to run as a daemon."""
        import os

        # First fork
        try:
            pid = os.fork()
            if pid > 0:
                # Parent process exits
                sys.exit(0)
        except OSError as e:
            print(f"Fork #1 failed: {e}")
            sys.exit(1)

        # Decouple from parent environment
        os.chdir("/")
        os.setsid()
        os.umask(0)

        # Second fork
        try:
            pid = os.fork()
            if pid > 0:
                # Parent process exits
                sys.exit(0)
        except OSError as e:
            print(f"Fork #2 failed: {e}")
            sys.exit(1)

        # Redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()

        # Open log file for stdout/stderr
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_file, "a") as f:
            os.dup2(f.fileno(), sys.stdout.fileno())
            os.dup2(f.fileno(), sys.stderr.fileno())

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self._log()
        self._log("=" * 70)
        self._log("Received shutdown signal")
        self._log("=" * 70)
        self.running = False

    def _cleanup(self):
        """Clean up resources on exit."""
        self._log("Cleaning up...")

        # Remove PID file
        if self.pid_file.exists():
            self.pid_file.unlink()

        self._log("Monitor stopped")
        self._log("=" * 70)
        self._log()

    def _log(self, message: str = ""):
        """Log a message to stdout and log file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if message:
            log_line = f"[{timestamp}] {message}"
        else:
            log_line = ""

        print(log_line)

        # Also write to log file if it exists
        if self.log_file.exists() or self.log_file.parent.exists():
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a") as f:
                f.write(log_line + "\n")

    @staticmethod
    def get_status():
        """Check if monitor is running and print status."""
        pid_file = Path.home() / ".isbn_lot_optimizer" / "training_monitor.pid"
        log_file = Path.home() / ".isbn_lot_optimizer" / "training_monitor.log"

        print("=" * 70)
        print("Continuous Training Monitor - Status")
        print("=" * 70)
        print()

        # Check PID file
        if not pid_file.exists():
            print("Status: NOT RUNNING")
            print("  (PID file not found)")
            return

        # Read PID
        with open(pid_file) as f:
            pid = int(f.read().strip())

        # Check if process is running
        import os
        try:
            os.kill(pid, 0)  # Signal 0 just checks if process exists
            print("Status: RUNNING")
            print(f"  PID: {pid}")
        except OSError:
            print("Status: STOPPED (stale PID file)")
            print(f"  PID: {pid} (not running)")

        print()

        # Show recent log entries
        if log_file.exists():
            print("Recent log entries:")
            print("-" * 70)
            with open(log_file) as f:
                lines = f.readlines()
                for line in lines[-20:]:  # Last 20 lines
                    print(f"  {line.rstrip()}")
        else:
            print("No log file found")

        print()
        print("=" * 70)

    @staticmethod
    def stop_daemon():
        """Stop the running daemon."""
        pid_file = Path.home() / ".isbn_lot_optimizer" / "training_monitor.pid"

        if not pid_file.exists():
            print("Monitor is not running (PID file not found)")
            return

        # Read PID
        with open(pid_file) as f:
            pid = int(f.read().strip())

        # Send TERM signal
        import os
        try:
            print(f"Stopping monitor (PID {pid})...")
            os.kill(pid, signal.SIGTERM)
            print("Sent SIGTERM signal")

            # Wait for process to exit
            time.sleep(2)

            # Check if still running
            try:
                os.kill(pid, 0)
                print("⚠ Process still running, sending SIGKILL...")
                os.kill(pid, signal.SIGKILL)
            except OSError:
                print("✅ Monitor stopped successfully")

        except OSError as e:
            print(f"Error stopping monitor: {e}")
            print("Process may have already stopped")

        # Clean up PID file
        if pid_file.exists():
            pid_file.unlink()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Continuous training monitor for ML models"
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as background daemon",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check monitor status",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop running daemon",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=600,
        help="Check interval in seconds (default: 600 = 10 minutes)",
    )
    parser.add_argument(
        "--min-quality",
        type=float,
        default=0.6,
        help="Minimum quality score (default: 0.6)",
    )
    parser.add_argument(
        "--min-books",
        type=int,
        default=1,
        help="Minimum new books to trigger training (default: 1)",
    )

    args = parser.parse_args()

    # Handle status check
    if args.status:
        ContinuousTrainingMonitor.get_status()
        return

    # Handle stop command
    if args.stop:
        ContinuousTrainingMonitor.stop_daemon()
        return

    # Start monitor
    monitor = ContinuousTrainingMonitor(
        check_interval_seconds=args.interval,
        min_quality_score=args.min_quality,
        min_new_books=args.min_books,
    )

    monitor.start(daemon=args.daemon)


if __name__ == "__main__":
    main()
