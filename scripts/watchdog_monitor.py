#!/usr/bin/env python3
"""
Watchdog monitor for BookFinder scrapes and web server.
Sends iMessage alerts when things go wrong.
"""

import subprocess
import sqlite3
import time
import os
from pathlib import Path
from datetime import datetime


def send_imessage_alert(message):
    """Send urgent alert via iMessage."""
    phone = os.getenv('YOUR_PHONE_NUMBER', '+12087201241')

    applescript = f'''
    tell application "Messages"
        set targetService to 1st account whose service type = iMessage
        set targetBuddy to participant "{phone}" of targetService
        send "{message}" to targetBuddy
    end tell
    '''

    try:
        subprocess.run(['osascript', '-e', applescript], timeout=10)
        return True
    except:
        return False


def check_scraper_processes():
    """Check if scraper processes are running."""
    result = subprocess.run(
        ['ps', 'aux'],
        capture_output=True,
        text=True
    )

    catalog_running = 'collect_bookfinder_prices.py --source catalog' in result.stdout
    metadata_running = 'collect_bookfinder_prices.py --source metadata_cache' in result.stdout

    return {
        'catalog': catalog_running,
        'metadata': metadata_running
    }


def check_server_status():
    """Check if web server is running."""
    result = subprocess.run(
        ['ps', 'aux'],
        capture_output=True,
        text=True
    )

    # Check for uvicorn server
    server_running = 'uvicorn' in result.stdout and 'isbn_web.main' in result.stdout

    return server_running


def get_latest_completion_time():
    """Get timestamp of latest completed ISBN."""
    db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT scraped_at FROM bookfinder_progress
        WHERE status = 'completed'
        ORDER BY scraped_at DESC LIMIT 1
    """)

    result = cursor.fetchone()
    conn.close()

    if result:
        return result[0]
    return None


def check_for_stalls():
    """Check if scraper has stalled (no progress in 30 minutes)."""
    latest = get_latest_completion_time()

    if not latest:
        return False

    # Parse timestamp
    try:
        from datetime import datetime
        latest_dt = datetime.fromisoformat(latest)
        now = datetime.now()

        # If no progress in 30 minutes, consider it stalled
        minutes_since = (now - latest_dt).total_seconds() / 60

        return minutes_since > 30
    except:
        return False


def check_error_logs():
    """Check recent logs for critical errors."""
    log_files = [
        '/tmp/bookfinder_scraper_*.log'
    ]

    errors = []

    # Get most recent log files
    import glob
    for pattern in log_files:
        files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
        if files:
            latest_log = files[0]

            try:
                # Check last 50 lines for ERROR level
                result = subprocess.run(
                    ['tail', '-50', latest_log],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                for line in result.stdout.split('\n'):
                    if 'ERROR' in line and 'HTTP 401' not in line:
                        errors.append(line)
            except:
                pass

    return errors


def main():
    """Main watchdog monitoring loop."""
    print("🐕 Watchdog monitoring started")
    print("Checking every 5 minutes for issues...")

    # Track previous states
    prev_catalog_running = True
    prev_metadata_running = True
    prev_server_running = True
    stall_alert_sent = False

    while True:
        # Check scraper processes
        processes = check_scraper_processes()

        # Alert if catalog scrape stopped
        if not processes['catalog'] and prev_catalog_running:
            send_imessage_alert("⚠️ ALERT: Catalog scrape has stopped!")
            print(f"[{datetime.now()}] ALERT: Catalog scrape stopped")

        # Alert if metadata scrape stopped
        if not processes['metadata'] and prev_metadata_running:
            send_imessage_alert("⚠️ ALERT: Metadata scrape has stopped!")
            print(f"[{datetime.now()}] ALERT: Metadata scrape stopped")

        # Check for scraper restarts (stopped -> running)
        if processes['catalog'] and not prev_catalog_running:
            send_imessage_alert("✅ Catalog scrape has restarted")
            print(f"[{datetime.now()}] INFO: Catalog scrape restarted")

        if processes['metadata'] and not prev_metadata_running:
            send_imessage_alert("✅ Metadata scrape has restarted")
            print(f"[{datetime.now()}] INFO: Metadata scrape restarted")

        # Check server status
        server_running = check_server_status()

        if not server_running and prev_server_running:
            send_imessage_alert("⚠️ ALERT: Web server has stopped!")
            print(f"[{datetime.now()}] ALERT: Web server stopped")

        if server_running and not prev_server_running:
            send_imessage_alert("✅ Web server has restarted")
            print(f"[{datetime.now()}] INFO: Web server restarted")

        # Check for stalls
        if check_for_stalls():
            if not stall_alert_sent:
                send_imessage_alert("⚠️ ALERT: Scraper appears stalled (no progress in 30+ min)")
                print(f"[{datetime.now()}] ALERT: Scraper stalled")
                stall_alert_sent = True
        else:
            stall_alert_sent = False

        # Check for errors in logs
        errors = check_error_logs()
        if errors and len(errors) > 5:
            send_imessage_alert(f"⚠️ ALERT: Multiple errors detected in logs ({len(errors)} errors)")
            print(f"[{datetime.now()}] ALERT: {len(errors)} errors in logs")

        # Update previous states
        prev_catalog_running = processes['catalog']
        prev_metadata_running = processes['metadata']
        prev_server_running = server_running

        # Status report
        status = []
        if processes['catalog']:
            status.append("✅ Catalog")
        else:
            status.append("❌ Catalog")

        if processes['metadata']:
            status.append("✅ Metadata")
        else:
            status.append("❌ Metadata")

        if server_running:
            status.append("✅ Server")
        else:
            status.append("❌ Server")

        print(f"[{datetime.now()}] Status: {' | '.join(status)}")

        # Wait 5 minutes
        time.sleep(300)


if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()

    try:
        main()
    except KeyboardInterrupt:
        print("\n🐕 Watchdog monitoring stopped")
