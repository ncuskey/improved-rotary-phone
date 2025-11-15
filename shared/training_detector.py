"""
Training data detector - checks for new quality training data.

This module tracks which books have been added to the training database
since the last model training run, enabling continuous model retraining.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


class TrainingDataDetector:
    """Detects new training-quality books for model retraining."""

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize the detector.

        Args:
            db_path: Path to metadata_cache.db (defaults to standard location)
        """
        if db_path is None:
            db_path = Path.home() / ".isbn_lot_optimizer" / "metadata_cache.db"
        self.db_path = db_path
        self.state_file = Path.home() / ".isbn_lot_optimizer" / "last_training_state.txt"

    def get_new_training_books_count(self, min_quality_score: float = 0.6) -> int:
        """
        Count books added since last training that meet quality criteria.

        Args:
            min_quality_score: Minimum training_quality_score (0-1.0)

        Returns:
            Count of new quality books

        Quality criteria:
        - training_quality_score >= min_quality_score
        - in_training = 1
        - Added after last_training_timestamp
        """
        last_training_ts = self._get_last_training_timestamp()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Count books that meet quality criteria and were added since last training
        query = """
            SELECT COUNT(*)
            FROM cached_books
            WHERE in_training = 1
              AND training_quality_score >= ?
              AND (last_enrichment_at > ? OR metadata_fetched_at > ?)
        """

        cursor.execute(query, (min_quality_score, last_training_ts, last_training_ts))
        count = cursor.fetchone()[0]

        conn.close()

        return count

    def get_training_statistics(self) -> Dict[str, any]:
        """
        Get detailed statistics about training-eligible books.

        Returns:
            Dictionary with training data statistics
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        stats = {}

        # Total training-eligible books
        cursor.execute("SELECT COUNT(*) FROM cached_books WHERE in_training = 1")
        stats["total_training_books"] = cursor.fetchone()[0]

        # Books by quality score ranges
        cursor.execute("""
            SELECT
                CASE
                    WHEN training_quality_score >= 0.8 THEN 'excellent'
                    WHEN training_quality_score >= 0.6 THEN 'good'
                    WHEN training_quality_score >= 0.4 THEN 'fair'
                    ELSE 'poor'
                END as quality,
                COUNT(*)
            FROM cached_books
            WHERE in_training = 1
            GROUP BY quality
        """)
        stats["by_quality"] = {row[0]: row[1] for row in cursor.fetchall()}

        # New books since last training
        last_training_ts = self._get_last_training_timestamp()
        cursor.execute("""
            SELECT COUNT(*)
            FROM cached_books
            WHERE in_training = 1
              AND (last_enrichment_at > ? OR metadata_fetched_at > ?)
        """, (last_training_ts, last_training_ts))
        stats["new_since_last_training"] = cursor.fetchone()[0]

        # Last training timestamp
        stats["last_training_at"] = last_training_ts

        conn.close()

        return stats

    def mark_training_completed(self):
        """
        Mark that a training run has completed.

        Updates the last_training_timestamp to current time.
        """
        now = datetime.now().isoformat()

        # Write to state file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            f.write(now)

        print(f"✅ Training completion marked at {now}")

    def _get_last_training_timestamp(self) -> str:
        """
        Get the timestamp of the last training run.

        Returns:
            ISO format timestamp, or very old date if never trained
        """
        if not self.state_file.exists():
            # Return a very old date (2000-01-01) if never trained
            return "2000-01-01T00:00:00"

        with open(self.state_file, "r") as f:
            return f.read().strip()


def check_for_new_training_data(min_quality_score: float = 0.6) -> int:
    """
    Convenience function to check for new training data.

    Args:
        min_quality_score: Minimum quality score for training eligibility

    Returns:
        Count of new quality books since last training
    """
    detector = TrainingDataDetector()
    return detector.get_new_training_books_count(min_quality_score)


if __name__ == "__main__":
    # Test the detector
    detector = TrainingDataDetector()

    print("=" * 70)
    print("Training Data Detector - Status Check")
    print("=" * 70)
    print()

    # Get statistics
    stats = detector.get_training_statistics()

    print(f"Total training-eligible books: {stats['total_training_books']}")
    print(f"Last training: {stats['last_training_at']}")
    print()

    print("Books by quality:")
    for quality, count in stats.get('by_quality', {}).items():
        print(f"  {quality:12s}: {count:4d} books")
    print()

    # Check for new books
    new_count = detector.get_new_training_books_count()
    print(f"New books since last training: {new_count}")

    if new_count > 0:
        print(f"✅ Training recommended ({new_count} new quality books)")
    else:
        print("💤 No new training data available")

    print()
    print("=" * 70)
