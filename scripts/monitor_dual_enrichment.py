#!/usr/bin/env python3
"""
Monitor both ISBN and Series Lot enrichment progress and send iMessage updates.
"""

import re
import subprocess
import os
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import sqlite3

# Load environment variables
load_dotenv()

# Suppress matplotlib backend warnings
import warnings
warnings.filterwarnings('ignore')

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ISBN_LOG = "/tmp/isbn_enrichment_full.log"
SERIES_LOG = "/tmp/series_lot_enrichment_optimized.log"
STATE_FILE = "/tmp/dual_enrichment_monitor_state.json"


def send_imessage(message, phone_number, attachment_path=None):
    """Send iMessage using AppleScript with optional attachment."""
    # Escape quotes for AppleScript (newlines work fine in AppleScript strings)
    message = message.replace('"', '\\"')

    if attachment_path and Path(attachment_path).exists():
        # Send message first, then attachment in separate call
        # This ensures both get sent to the same conversation
        applescript_message = f'''
        tell application "Messages"
            set targetService to 1st account whose service type = iMessage
            set targetBuddy to participant "{phone_number}" of targetService
            send "{message}" to targetBuddy
        end tell
        '''

        applescript_attachment = f'''
        tell application "Messages"
            set targetService to 1st account whose service type = iMessage
            set targetBuddy to participant "{phone_number}" of targetService
            set theAttachment to POSIX file "{attachment_path}"
            send theAttachment to targetBuddy
        end tell
        '''

        # Send message
        try:
            result = subprocess.run(
                ['osascript', '-e', applescript_message],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                print(f"❌ Failed to send message: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ Error sending message: {e}")
            return False

        # Send attachment
        try:
            result = subprocess.run(
                ['osascript', '-e', applescript_attachment],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                print(f"✅ iMessage with attachment sent successfully!")
                return True
            else:
                print(f"⚠️  Message sent but attachment failed: {result.stderr}")
                return True  # Message was sent at least
        except Exception as e:
            print(f"⚠️  Message sent but attachment failed: {e}")
            return True  # Message was sent at least
    else:
        # AppleScript without attachment
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


def parse_isbn_enrichment():
    """Parse ISBN enrichment progress from database."""
    try:
        # Query database for actual progress
        import sqlite3
        db_path = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'

        if not db_path.exists():
            return None

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get enriched ISBNs count (ISBNs with market data)
        cursor.execute("""
            SELECT COUNT(*)
            FROM cached_books
            WHERE last_enrichment_at IS NOT NULL
        """)
        enriched = cursor.fetchone()[0]

        conn.close()

        # Get total from log file if available
        total = None
        if Path(ISBN_LOG).exists():
            try:
                with open(ISBN_LOG, 'r') as f:
                    content = f.read()
                total_match = re.search(r'Found (\d+) ISBNs needing', content)
                if total_match:
                    total = int(total_match.group(1))
            except:
                pass

        # If we couldn't get total from log, use a reasonable fallback
        if not total:
            total = 18756  # Known value

        # Check if process is running
        try:
            result = subprocess.run(['pgrep', '-f', 'enrich_metadata_cache_market_data.py'],
                                    capture_output=True, text=True)
            is_running = bool(result.stdout.strip())
        except:
            is_running = False

        status = 'Running' if is_running else 'Stopped'
        progress_pct = (enriched / total * 100) if total > 0 else 0

        return {
            'total': total,
            'enriched': enriched,
            'progress_pct': progress_pct,
            'status': status,
        }

    except Exception as e:
        print(f"Error querying ISBN enrichment: {e}")
        return None


def parse_series_enrichment():
    """Parse series lot enrichment progress from database."""
    try:
        # Query database for actual progress
        import sqlite3
        db_path = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'

        if not db_path.exists():
            return None

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get total series from catalog
        catalog_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
        if catalog_path.exists():
            catalog_conn = sqlite3.connect(str(catalog_path))
            catalog_cursor = catalog_conn.cursor()
            catalog_cursor.execute("SELECT COUNT(*) FROM series")
            total = catalog_cursor.fetchone()[0]
            catalog_conn.close()
        else:
            total = 12770  # Fallback to known value

        # Get enriched series count and total lots
        cursor.execute("""
            SELECT
                COUNT(DISTINCT series_id) as series_enriched,
                COUNT(*) as total_lots
            FROM series_lot_comps
        """)
        enriched, total_lots = cursor.fetchone()

        conn.close()

        # Check if process is still running
        try:
            result = subprocess.run(['pgrep', '-f', 'enrich_series_lot_market_data.py'],
                                    capture_output=True, text=True)
            is_running = bool(result.stdout.strip())
        except:
            is_running = False

        status = 'Running' if is_running else 'Stopped/Complete'

        # Calculate progress percentage
        progress_pct = (enriched / total * 100) if total > 0 else 0

        # Estimate rate (will be rough without time tracking)
        # For now, use a placeholder - could be enhanced with timestamp tracking
        rate = 0  # Not available from DB alone
        eta_hours = 0  # Not available without rate

        return {
            'total': total,
            'enriched': enriched,
            'total_lots': total_lots,
            'progress_pct': progress_pct,
            'rate': rate,
            'eta_hours': eta_hours,
            'status': status,
        }

    except Exception as e:
        print(f"Error querying series enrichment: {e}")
        return None


def format_eta(hours):
    """Format ETA in a readable way."""
    if hours is None or hours <= 0:
        return None

    if hours < 1:
        minutes = hours * 60
        return f"{minutes:.0f}m"
    elif hours < 24:
        return f"{hours:.1f}h"
    else:
        days = hours / 24
        remaining_hours = hours % 24
        if remaining_hours < 1:
            return f"{days:.1f}d"
        else:
            return f"{days:.0f}d {remaining_hours:.0f}h"


def format_update_message(isbn_stats, series_stats):
    """Format combined progress message."""
    timestamp = datetime.now().strftime('%I:%M %p')

    message_parts = ["📊 Enrichment Update\n"]

    # Series lot enrichment (main focus)
    if series_stats:
        message_parts.append(f"🎯 Series Lot Enrichment:")
        message_parts.append(f"Series: {series_stats['enriched']:,}/{series_stats['total']:,} ({series_stats['progress_pct']:.1f}%)")
        message_parts.append(f"Lots Found: {series_stats.get('total_lots', 0):,}")

        if series_stats.get('rate') and series_stats['rate'] > 0:
            rate_per_min = series_stats['rate'] * 60
            message_parts.append(f"Speed: {rate_per_min:.1f}/min")

        if series_stats.get('eta_hours'):
            eta_str = format_eta(series_stats['eta_hours'])
            if eta_str:
                message_parts.append(f"ETA: {eta_str}")

        message_parts.append(f"Status: {series_stats['status']}\n")

    # ISBN enrichment (secondary)
    if isbn_stats:
        message_parts.append(f"📚 ISBN Enrichment:")
        message_parts.append(f"ISBNs: {isbn_stats.get('enriched', 0):,}/{isbn_stats['total']:,} ({isbn_stats.get('progress_pct', 0):.1f}%)")

        if isbn_stats.get('rate') and isbn_stats['rate'] > 0:
            rate_per_min = isbn_stats['rate'] * 60
            message_parts.append(f"Speed: {rate_per_min:.1f}/min")

        if isbn_stats.get('eta_hours'):
            eta_str = format_eta(isbn_stats['eta_hours'])
            if eta_str:
                message_parts.append(f"ETA: {eta_str}")

        message_parts.append(f"Status: {isbn_stats['status']}\n")

    message_parts.append(f"Time: {timestamp}")

    return "\n".join(message_parts)


def get_last_reported_state():
    """Get the last reported state."""
    try:
        if Path(STATE_FILE).exists():
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {
        'series_enriched': 0,
        'isbn_enriched': 0,
        'timestamp': None
    }


def save_reported_state(series_enriched, isbn_enriched, series_rate=None, isbn_rate=None):
    """Save the reported state."""
    try:
        state = {
            'series_enriched': series_enriched,
            'isbn_enriched': isbn_enriched,
            'timestamp': datetime.now().isoformat()
        }
        if series_rate is not None:
            state['series_rate'] = series_rate
        if isbn_rate is not None:
            state['isbn_rate'] = isbn_rate

        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Warning: Could not save state: {e}")


def should_send_update(series_stats, last_state):
    """Determine if we should send an update."""
    if not series_stats:
        return False

    current_enriched = series_stats.get('enriched', 0)
    last_enriched = last_state.get('series_enriched', 0)

    # Always send if completed
    if series_stats['status'] == 'Complete':
        return True

    # Send if this is first run
    if last_enriched == 0 and current_enriched > 0:
        return True

    # Send if we've enriched at least 50 more series (about 30 min at current rate)
    if current_enriched - last_enriched >= 50:
        return True

    return False


def generate_progress_chart(series_stats, isbn_stats):
    """Generate a mobile-optimized progress chart."""
    try:
        # Create figure
        plt.style.use('seaborn-v0_8-darkgrid')
        fig, ax = plt.subplots(figsize=(8, 5), dpi=100)

        # Data for the chart
        labels = []
        current_values = []
        total_values = []

        if series_stats:
            labels.append('Series Lot\nEnrichment')
            current_values.append(series_stats.get('enriched', 0))
            total_values.append(series_stats['total'])

        if isbn_stats:
            labels.append('ISBN\nEnrichment')
            current_values.append(isbn_stats.get('enriched', 0))
            total_values.append(isbn_stats['total'])

        if not labels:
            return None

        x = range(len(labels))
        width = 0.6

        # Calculate percentages
        percentages = [(curr / total * 100) if total > 0 else 0
                       for curr, total in zip(current_values, total_values)]

        # Create bars
        bars = ax.bar(x, percentages, width, alpha=0.8,
                      color=['#4A90E2', '#E24A4A'])

        # Customize
        ax.set_ylabel('Progress (%)', fontsize=12, fontweight='bold')
        ax.set_title('Enrichment Progress', fontsize=14, fontweight='bold', pad=15)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=11)
        ax.set_ylim(0, 100)
        ax.grid(True, alpha=0.3, axis='y')

        # Add percentage labels on bars
        for i, (bar, pct, curr, total) in enumerate(zip(bars, percentages, current_values, total_values)):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 2,
                    f'{pct:.1f}%',
                    ha='center', va='bottom', fontsize=12, fontweight='bold')
            ax.text(bar.get_x() + bar.get_width()/2., height/2,
                    f'{curr:,}/{total:,}',
                    ha='center', va='center', fontsize=9, color='white',
                    fontweight='bold')

        # Add 100% reference line
        ax.axhline(y=100, color='green', linestyle='--', alpha=0.3, linewidth=1.5)

        plt.tight_layout()

        # Save to temp file
        chart_path = '/tmp/enrichment_progress_update.png'
        plt.savefig(chart_path, dpi=100, bbox_inches='tight', facecolor='white')
        plt.close()

        return chart_path

    except Exception as e:
        print(f"Warning: Could not generate chart: {e}")
        return None


def main():
    """Main monitoring function."""
    print(f"Starting dual enrichment monitor at {datetime.now()}")

    # Get phone number from environment
    phone = os.getenv('YOUR_PHONE_NUMBER')
    if not phone:
        print("❌ No phone number specified. Set YOUR_PHONE_NUMBER in .env")
        return 1

    # Parse current stats
    isbn_stats = parse_isbn_enrichment()
    series_stats = parse_series_enrichment()

    if not series_stats and not isbn_stats:
        print("⚠️ Could not parse either log file")
        return 1

    # Check if we should send update
    last_state = get_last_reported_state()

    # Calculate rates and ETAs if we have previous state
    if last_state.get('timestamp'):
        try:
            last_time = datetime.fromisoformat(last_state['timestamp'])
            current_time = datetime.now()
            time_elapsed_seconds = (current_time - last_time).total_seconds()

            if time_elapsed_seconds > 0:
                # Calculate series rate and ETA
                if series_stats:
                    current_series = series_stats.get('enriched', 0)
                    last_series = last_state.get('series_enriched', 0)
                    series_delta = current_series - last_series

                    if series_delta > 0:
                        series_rate = series_delta / time_elapsed_seconds  # series per second
                        remaining_series = series_stats['total'] - current_series
                        eta_seconds = remaining_series / series_rate if series_rate > 0 else 0
                        eta_hours = eta_seconds / 3600

                        series_stats['rate'] = series_rate
                        series_stats['eta_hours'] = eta_hours

                # Calculate ISBN rate and ETA
                if isbn_stats:
                    current_isbn = isbn_stats.get('enriched', 0)
                    last_isbn = last_state.get('isbn_enriched', 0)
                    isbn_delta = current_isbn - last_isbn

                    if isbn_delta > 0:
                        isbn_rate = isbn_delta / time_elapsed_seconds  # ISBNs per second
                        remaining_isbn = isbn_stats['total'] - current_isbn
                        eta_seconds = remaining_isbn / isbn_rate if isbn_rate > 0 else 0
                        eta_hours = eta_seconds / 3600

                        isbn_stats['rate'] = isbn_rate
                        isbn_stats['eta_hours'] = eta_hours
        except Exception as e:
            print(f"Warning: Could not calculate rates: {e}")

    if should_send_update(series_stats, last_state):
        message = format_update_message(isbn_stats, series_stats)
        print(f"Sending update...")
        print(message)

        # Generate progress chart
        chart_path = generate_progress_chart(series_stats, isbn_stats)

        if send_imessage(message, phone, attachment_path=chart_path):
            save_reported_state(
                series_stats.get('enriched', 0) if series_stats else 0,
                isbn_stats.get('enriched', 0) if isbn_stats else 0,
                series_stats.get('rate') if series_stats else None,
                isbn_stats.get('rate') if isbn_stats else None
            )
    else:
        current = series_stats.get('enriched', 0) if series_stats else 0
        last = last_state.get('series_enriched', 0)
        print(f"No significant progress since last report ({last} -> {current})")

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
