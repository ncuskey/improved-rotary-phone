#!/usr/bin/env python3
"""
Monitor BookFinder scraping progress in real-time.

Shows status of both catalog and metadata_cache scrapes.
"""

import sqlite3
import time
from pathlib import Path
from datetime import datetime, timedelta


def get_db_path():
    return Path.home() / '.isbn_lot_optimizer' / 'catalog.db'


def get_progress_stats():
    """Get current scraping statistics."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Total catalog ISBNs
    cursor.execute("SELECT COUNT(DISTINCT isbn) FROM books WHERE isbn IS NOT NULL")
    total_catalog = cursor.fetchone()[0]

    # Completed ISBNs
    cursor.execute("SELECT COUNT(*) FROM bookfinder_progress WHERE status = 'completed'")
    completed = cursor.fetchone()[0]

    # Failed ISBNs
    cursor.execute("SELECT COUNT(*) FROM bookfinder_progress WHERE status = 'failed'")
    failed = cursor.fetchone()[0]

    # Total offers
    cursor.execute("SELECT COUNT(*) FROM bookfinder_offers")
    total_offers = cursor.fetchone()[0]

    # Recent completions (last 10 minutes)
    cursor.execute("""
        SELECT COUNT(*) FROM bookfinder_progress
        WHERE status = 'completed'
        AND scraped_at > datetime('now', '-10 minutes')
    """)
    recent_completions = cursor.fetchone()[0]

    # Average offers per ISBN
    avg_offers = total_offers / completed if completed > 0 else 0

    # Latest completion
    cursor.execute("""
        SELECT isbn, scraped_at FROM bookfinder_progress
        WHERE status = 'completed'
        ORDER BY scraped_at DESC LIMIT 1
    """)
    latest = cursor.fetchone()
    latest_isbn = latest[0] if latest else None
    latest_time = latest[1] if latest else None

    conn.close()

    return {
        'total_catalog': total_catalog,
        'completed': completed,
        'failed': failed,
        'remaining': total_catalog - completed - failed,
        'total_offers': total_offers,
        'avg_offers': avg_offers,
        'recent_completions': recent_completions,
        'latest_isbn': latest_isbn,
        'latest_time': latest_time,
    }


def estimate_completion(completed, total, start_time):
    """Estimate completion time based on current rate."""
    if completed == 0:
        return "Unknown"

    elapsed = time.time() - start_time
    rate = completed / elapsed  # ISBNs per second
    remaining = total - completed

    if rate == 0:
        return "Unknown"

    eta_seconds = remaining / rate
    eta = datetime.now() + timedelta(seconds=eta_seconds)

    return eta.strftime("%Y-%m-%d %H:%M:%S")


def print_report():
    """Print current progress report."""
    stats = get_progress_stats()

    print("\n" + "="*70)
    print(f"BOOKFINDER SCRAPING PROGRESS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    print(f"\n📊 Overall Statistics:")
    print(f"   Total Catalog ISBNs:  {stats['total_catalog']:>6,}")
    print(f"   ✅ Completed:          {stats['completed']:>6,}  ({stats['completed']/stats['total_catalog']*100:>5.1f}%)")
    print(f"   ❌ Failed:             {stats['failed']:>6,}  ({stats['failed']/stats['total_catalog']*100:>5.1f}%)")
    print(f"   ⏳ Remaining:          {stats['remaining']:>6,}  ({stats['remaining']/stats['total_catalog']*100:>5.1f}%)")

    print(f"\n📦 Offers Collected:")
    print(f"   Total Offers:         {stats['total_offers']:>7,}")
    print(f"   Average per ISBN:     {stats['avg_offers']:>7.1f}")

    print(f"\n⚡ Recent Activity:")
    print(f"   Last 10 minutes:      {stats['recent_completions']:>6} ISBNs")
    if stats['recent_completions'] > 0:
        rate_per_hour = stats['recent_completions'] * 6  # 10 min → 1 hour
        print(f"   Current rate:         {rate_per_hour:>6.1f} ISBNs/hour")

    if stats['latest_isbn']:
        print(f"\n🕐 Latest Completion:")
        print(f"   ISBN: {stats['latest_isbn']}")
        print(f"   Time: {stats['latest_time']}")

    print("\n" + "="*70)


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--watch':
        # Continuous monitoring mode
        print("Starting continuous monitoring (Ctrl+C to stop)...")
        try:
            while True:
                print_report()
                time.sleep(60)  # Update every minute
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped.")
    else:
        # Single report
        print_report()
