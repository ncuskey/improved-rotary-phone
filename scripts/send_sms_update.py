#!/usr/bin/env python3
"""
Send SMS updates via Twilio about BookFinder scraping progress.
"""

import os
import sqlite3
from pathlib import Path
from datetime import datetime
from twilio.rest import Client


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

    # Recent completions (last hour)
    cursor.execute("""
        SELECT COUNT(*) FROM bookfinder_progress
        WHERE status = 'completed'
        AND scraped_at > datetime('now', '-1 hour')
    """)
    recent_completions = cursor.fetchone()[0]

    conn.close()

    return {
        'total_catalog': total_catalog,
        'completed': completed,
        'failed': failed,
        'remaining': total_catalog - completed - failed,
        'total_offers': total_offers,
        'recent_completions': recent_completions,
        'progress_pct': (completed / total_catalog * 100) if total_catalog > 0 else 0,
    }


def send_sms(message, to_phone):
    """Send SMS via Twilio."""
    # Get credentials from environment
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')

    # Support both Auth Token and API Key authentication
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    api_key_sid = os.getenv('TWILIO_SID')
    api_key_secret = os.getenv('TWILIO_SECRET')

    from_phone = os.getenv('TWILIO_PHONE_NUMBER')  # Need to add this

    if not account_sid:
        print("❌ Missing TWILIO_ACCOUNT_SID in .env file")
        return False

    if not from_phone:
        print("❌ Missing TWILIO_PHONE_NUMBER in .env file")
        print("   Add your Twilio phone number (format: +1234567890)")
        return False

    # Use API Key if available, otherwise Auth Token
    if api_key_sid and api_key_secret:
        print("Using Twilio API Key authentication")
        client = Client(api_key_sid, api_key_secret, account_sid)
    elif auth_token:
        print("Using Twilio Auth Token authentication")
        client = Client(account_sid, auth_token)
    else:
        print("❌ Missing authentication credentials")
        print("   Need either: TWILIO_AUTH_TOKEN")
        print("   Or: TWILIO_SID + TWILIO_SECRET (API Key)")
        return False

    try:

        message = client.messages.create(
            body=message,
            from_=from_phone,
            to=to_phone
        )

        print(f"✅ SMS sent successfully (SID: {message.sid})")
        return True
    except Exception as e:
        print(f"❌ Failed to send SMS: {e}")
        return False


def format_progress_message(stats):
    """Format progress stats into SMS message."""
    message = f"""📊 BookFinder Scraper Update

✅ Completed: {stats['completed']:,} ({stats['progress_pct']:.1f}%)
📦 Offers: {stats['total_offers']:,}
⏳ Remaining: {stats['remaining']:,}
⚡ Last hour: {stats['recent_completions']} ISBNs

Time: {datetime.now().strftime('%I:%M %p')}
"""
    return message


if __name__ == '__main__':
    import sys
    import argparse

    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description='Send BookFinder progress via SMS')
    parser.add_argument('--to', required=True, help='Phone number to send to (e.g., +1234567890)')
    parser.add_argument('--test', action='store_true', help='Send test message')

    args = parser.parse_args()

    if args.test:
        message = "🔔 BookFinder SMS notifications are now active! You'll receive updates at key milestones."
    else:
        stats = get_progress_stats()
        message = format_progress_message(stats)

    send_sms(message, args.to)
