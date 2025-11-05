#!/usr/bin/env python3
"""
Send iMessage updates about BookFinder scraping progress.
"""

import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime


def get_catalog_db_path():
    return Path.home() / '.isbn_lot_optimizer' / 'catalog.db'


def get_metadata_cache_db_path():
    return Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'


def get_scraper_stats(db_path, total_target=None):
    """Get scraping statistics for a specific database."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bookfinder_progress'")
        if not cursor.fetchone():
            # Tables don't exist yet - scraper hasn't started
            conn.close()
            return None

        # Total ISBNs - always use the progress table as source of truth
        cursor.execute("SELECT COUNT(*) FROM bookfinder_progress")
        total = cursor.fetchone()[0]

        # If total_target specified (for metadata_cache before scrape starts), use that
        if total_target is not None and total == 0:
            total = total_target

        # Completed ISBNs
        cursor.execute("SELECT COUNT(*) FROM bookfinder_progress WHERE status = 'completed'")
        completed = cursor.fetchone()[0]

        # Failed ISBNs
        cursor.execute("SELECT COUNT(*) FROM bookfinder_progress WHERE status = 'failed'")
        failed = cursor.fetchone()[0]

        # Total offers
        cursor.execute("SELECT COUNT(*) FROM bookfinder_offers")
        total_offers = cursor.fetchone()[0]

        # Recent completions (last hour)
        cursor.execute("""
            SELECT COUNT(*) FROM bookfinder_progress
            WHERE status = 'completed'
            AND scraped_at > datetime('now', '-1 hour')
        """)
        recent_completions = cursor.fetchone()[0]

        conn.close()

        return {
            'total': total,
            'completed': completed,
            'failed': failed,
            'remaining': total - completed - failed,
            'total_offers': total_offers,
            'recent_completions': recent_completions,
            'progress_pct': (completed / total * 100) if total > 0 else 0,
        }
    except Exception as e:
        # Database error - return None
        return None


def get_progress_stats():
    """Get current scraping statistics for both scrapers."""
    catalog_stats = get_scraper_stats(get_catalog_db_path())

    # metadata_cache.db may not exist yet or tables may not be initialized
    metadata_cache_path = get_metadata_cache_db_path()
    metadata_stats = None
    if metadata_cache_path.exists():
        # We know there are 18,089 ISBNs to scrape from metadata_cache
        metadata_stats = get_scraper_stats(metadata_cache_path, total_target=18089)

    return {
        'catalog': catalog_stats,
        'metadata_cache': metadata_stats,
    }


def send_imessage(message, phone_number):
    """Send iMessage using AppleScript."""
    # Clean phone number - remove any formatting
    clean_number = phone_number.replace('+', '').replace('-', '').replace(' ', '')

    # AppleScript to send iMessage
    applescript = f'''
    tell application "Messages"
        set targetService to 1st account whose service type = iMessage
        set targetBuddy to participant "{phone_number}" of targetService
        send "{message}" to targetBuddy
    end tell
    '''

    try:
        result = subprocess.run(
            ['osascript', '-e', applescript],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            print(f"✅ iMessage sent successfully!")
            return True
        else:
            print(f"❌ Failed to send iMessage: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error sending iMessage: {e}")
        return False


def format_progress_message(stats):
    """Format progress stats into iMessage."""
    catalog = stats['catalog']
    metadata = stats.get('metadata_cache')

    # Start with catalog stats
    message = f"""📊 BookFinder Scraper Update

🔵 CATALOG ({catalog['total']:,} ISBNs)
✅ Completed: {catalog['completed']:,} ({catalog['progress_pct']:.1f}%)
📦 Offers: {catalog['total_offers']:,}
⏳ Remaining: {catalog['remaining']:,}
⚡ Last hour: {catalog['recent_completions']} ISBNs"""

    # Add metadata_cache stats if running
    if metadata:
        message += f"""

🟢 METADATA CACHE ({metadata['total']:,} ISBNs)
✅ Completed: {metadata['completed']:,} ({metadata['progress_pct']:.1f}%)
📦 Offers: {metadata['total_offers']:,}
⏳ Remaining: {metadata['remaining']:,}
⚡ Last hour: {metadata['recent_completions']} ISBNs"""

    message += f"\n\nTime: {datetime.now().strftime('%I:%M %p')}"

    return message


if __name__ == '__main__':
    import sys
    import argparse
    from dotenv import load_dotenv
    import os

    # Load environment variables
    load_dotenv()

    parser = argparse.ArgumentParser(description='Send BookFinder progress via iMessage')
    parser.add_argument('--to', help='Phone number (defaults to YOUR_PHONE_NUMBER from .env)')
    parser.add_argument('--test', action='store_true', help='Send test message')

    args = parser.parse_args()

    # Get phone number
    phone = args.to or os.getenv('YOUR_PHONE_NUMBER')
    if not phone:
        print("❌ No phone number specified. Use --to or set YOUR_PHONE_NUMBER in .env")
        sys.exit(1)

    if args.test:
        message = "🔔 BookFinder iMessage notifications are now active! You'll receive updates at key milestones."
    else:
        stats = get_progress_stats()
        message = format_progress_message(stats)

    send_imessage(message, phone)
