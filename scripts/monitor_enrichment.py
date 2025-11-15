#!/usr/bin/env python3
"""
Monitor metadata enrichment progress and send iMessage updates.
Tracks progress from /tmp/enrichment_optimized_full.log
"""

import re
import subprocess
import time
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

LOG_FILE = "/tmp/enrichment_reprocess_all.log"
STATE_FILE = "/tmp/enrichment_monitor_state.json"


def send_imessage(message, phone_number):
    """Send iMessage using AppleScript."""
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


def parse_log_file():
    """Parse enrichment log to extract current progress."""
    if not Path(LOG_FILE).exists():
        return None

    try:
        with open(LOG_FILE, 'r') as f:
            content = f.read()

        # Extract key metrics
        total_match = re.search(r'Found (\d+) ISBNs needing market data enrichment', content)
        total = int(total_match.group(1)) if total_match else None

        # Get all batch completion messages
        batch_completions = re.findall(
            r'\[(\d+)-(\d+)/(\d+)\] Processing batch.*?'
            r'✓ Batch complete: (\d+) ISBNs enriched.*?'
            r'Progress: (\d+)/(\d+) ISBNs \(([\d.]+)%\).*?'
            r'Rate: ([\d.]+) ISBNs/sec.*?'
            r'Total enriched: (\d+) ISBNs',
            content,
            re.DOTALL
        )

        if not batch_completions:
            return {
                'total': total,
                'processed': 0,
                'enriched': 0,
                'progress_pct': 0,
                'rate': 0,
                'status': 'Starting...'
            }

        # Get latest batch stats
        last_batch = batch_completions[-1]
        processed = int(last_batch[4])  # Current progress number
        enriched = int(last_batch[8])    # Total enriched
        progress_pct = float(last_batch[6])
        rate = float(last_batch[7])

        # Check if process is still running
        try:
            result = subprocess.run(['pgrep', '-f', 'enrich_metadata_cache_market_data.py'],
                                    capture_output=True, text=True)
            is_running = bool(result.stdout.strip())
        except:
            is_running = False

        status = 'Running' if is_running else 'Stopped/Complete'

        # Calculate ETA
        remaining = total - processed if total else 0
        eta_hours = (remaining / rate / 3600) if rate > 0 else 0

        # Check for completion message
        if 'ENRICHMENT COMPLETE' in content:
            status = 'Complete'
            # Extract final stats
            success_match = re.search(r'Successfully enriched: (\d+) \(([\d.]+)%\)', content)
            if success_match:
                enriched = int(success_match.group(1))

        return {
            'total': total,
            'processed': processed,
            'enriched': enriched,
            'progress_pct': progress_pct,
            'rate': rate,
            'eta_hours': eta_hours,
            'status': status,
        }

    except Exception as e:
        print(f"Error parsing log: {e}")
        return None


def format_progress_message(stats):
    """Format progress stats into iMessage."""
    if not stats:
        return "📊 Enrichment Monitor: No data available"

    eta_str = f"{stats['eta_hours']:.1f} hours" if stats.get('eta_hours') else "Unknown"

    message = f"""📊 Metadata Enrichment Update

Status: {stats['status']}
Progress: {stats['enriched']:,}/{stats['total']:,} ISBNs ({stats['progress_pct']:.1f}%)
Success Rate: {(stats['enriched']/stats['processed']*100):.1f}% if stats['processed'] > 0 else 0%
Current Speed: {stats['rate']:.2f} ISBNs/sec
ETA: {eta_str}

Time: {datetime.now().strftime('%I:%M %p')}"""

    return message


def get_last_reported_count():
    """Get the last enriched count we reported."""
    try:
        if Path(STATE_FILE).exists():
            import json
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                return state.get('last_enriched', 0)
    except:
        pass
    return 0


def save_reported_count(count):
    """Save the enriched count we just reported."""
    try:
        import json
        with open(STATE_FILE, 'w') as f:
            json.dump({'last_enriched': count, 'timestamp': datetime.now().isoformat()}, f)
    except Exception as e:
        print(f"Warning: Could not save state: {e}")


def should_send_update(stats, last_reported):
    """Determine if we should send an update."""
    if not stats:
        return False

    current_enriched = stats.get('enriched', 0)

    # Always send if completed
    if stats['status'] == 'Complete':
        return True

    # Send if this is first run
    if last_reported == 0 and current_enriched > 0:
        return True

    # Send if we've enriched at least 100 more ISBNs (about 30 min at 0.1 ISBNs/sec)
    if current_enriched - last_reported >= 100:
        return True

    return False


def main():
    """Main monitoring function."""
    print(f"Starting enrichment monitor at {datetime.now()}")

    # Get phone number from environment
    phone = os.getenv('YOUR_PHONE_NUMBER')
    if not phone:
        print("❌ No phone number specified. Set YOUR_PHONE_NUMBER in .env")
        return 1

    # Parse current stats
    stats = parse_log_file()
    if not stats:
        print("⚠️ Could not parse log file")
        return 1

    # Check if we should send update
    last_reported = get_last_reported_count()

    if should_send_update(stats, last_reported):
        message = format_progress_message(stats)
        print(f"Sending update...")
        print(message)

        if send_imessage(message, phone):
            save_reported_count(stats['enriched'])
    else:
        print(f"No significant progress since last report ({last_reported} -> {stats['enriched']})")

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
