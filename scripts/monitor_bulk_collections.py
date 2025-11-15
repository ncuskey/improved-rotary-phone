#!/usr/bin/env python3
"""
Monitor AbeBooks and ZVAB bulk collection progress.
Shows real-time progress, success rates, and estimated completion times.
"""

import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# File paths
ABEBOOKS_FILE = Path("/Users/nickcuskey/ISBN/abebooks_results_full.json")
ZVAB_FILE = Path("/Users/nickcuskey/ISBN/zvab_results_full.json")
STATE_FILE = Path("/tmp/bulk_collections_state.json")

TOTAL_ISBNS = 19385
RATE_LIMIT = 2.5  # seconds between requests


def load_collection_data(file_path):
    """Load collection results from JSON file."""
    try:
        if not file_path.exists():
            return {}
        with open(file_path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return {}


def check_process_running(script_name):
    """Check if a collection script is running."""
    try:
        result = subprocess.run(
            ['pgrep', '-f', script_name],
            capture_output=True,
            text=True
        )
        return bool(result.stdout.strip())
    except:
        return False


def get_last_state():
    """Load last saved state."""
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE) as f:
                return json.load(f)
    except:
        pass
    return {}


def save_state(abebooks_count, zvab_count):
    """Save current state for rate calculation."""
    state = {
        'abebooks_count': abebooks_count,
        'zvab_count': zvab_count,
        'timestamp': datetime.now().isoformat()
    }
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Warning: Could not save state: {e}")


def format_time(seconds):
    """Format time duration in a readable way."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    elif seconds < 86400:
        hours = seconds / 3600
        return f"{hours:.1f}h"
    else:
        days = seconds / 86400
        remaining_hours = (seconds % 86400) / 3600
        if remaining_hours < 1:
            return f"{days:.1f}d"
        else:
            return f"{days:.0f}d {remaining_hours:.0f}h"


def calculate_rate_and_eta(current_count, last_count, time_elapsed_seconds, remaining):
    """Calculate collection rate and ETA."""
    if time_elapsed_seconds <= 0 or current_count <= last_count:
        return None, None

    rate = (current_count - last_count) / time_elapsed_seconds  # items per second
    items_per_min = rate * 60

    if rate > 0 and remaining > 0:
        eta_seconds = remaining / rate
        return items_per_min, eta_seconds

    return items_per_min, None


def print_collection_stats(name, data, is_running, last_count=None, time_elapsed=None):
    """Print statistics for a collection."""
    collected = len(data)
    remaining = TOTAL_ISBNS - collected
    progress_pct = (collected / TOTAL_ISBNS * 100)

    # Calculate success rate
    successful = sum(1 for v in data.values() if v.get('stats', {}).get('count', 0) > 0)
    success_rate = (successful / collected * 100) if collected > 0 else 0

    # Status indicator
    status = "🟢 Running" if is_running else "🔴 Stopped"

    print(f"\n{'='*70}")
    print(f"📚 {name} Collection {status}")
    print(f"{'='*70}")
    print(f"Progress:       {collected:,}/{TOTAL_ISBNS:,} ISBNs ({progress_pct:.1f}%)")
    print(f"With offers:    {successful:,} ({success_rate:.1f}% success rate)")
    print(f"Remaining:      {remaining:,} ISBNs")

    # Calculate rate and ETA if we have previous state
    if last_count is not None and time_elapsed is not None and time_elapsed > 0:
        rate, eta_seconds = calculate_rate_and_eta(collected, last_count, time_elapsed, remaining)

        if rate:
            print(f"Current rate:   {rate:.2f}/min")

        if eta_seconds:
            eta_str = format_time(eta_seconds)
            eta_datetime = datetime.now() + timedelta(seconds=eta_seconds)
            print(f"Est. completion: {eta_str} (around {eta_datetime.strftime('%I:%M %p')})")
    else:
        # Use theoretical rate based on rate limit
        theoretical_time = remaining * RATE_LIMIT
        theoretical_rate = 60 / RATE_LIMIT
        print(f"Theoretical rate: {theoretical_rate:.1f}/min (with {RATE_LIMIT}s rate limit)")
        if remaining > 0:
            eta_str = format_time(theoretical_time)
            print(f"Theoretical ETA: {eta_str}")

    # Progress bar
    bar_width = 50
    filled = int(bar_width * progress_pct / 100)
    bar = '█' * filled + '░' * (bar_width - filled)
    print(f"\n[{bar}] {progress_pct:.1f}%")


def main():
    """Main monitoring function."""
    print(f"\n{'='*70}")
    print(f"📊 Bulk Collection Monitor")
    print(f"{'='*70}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')}")

    # Load current data
    abebooks_data = load_collection_data(ABEBOOKS_FILE)
    zvab_data = load_collection_data(ZVAB_FILE)

    # Check if processes are running
    abebooks_running = check_process_running('collect_abebooks_bulk.py')
    zvab_running = check_process_running('collect_zvab_bulk.py')

    # Load previous state for rate calculation
    last_state = get_last_state()
    time_elapsed = None

    if last_state.get('timestamp'):
        try:
            last_time = datetime.fromisoformat(last_state['timestamp'])
            time_elapsed = (datetime.now() - last_time).total_seconds()
        except:
            pass

    # Print stats for each collection
    print_collection_stats(
        "AbeBooks",
        abebooks_data,
        abebooks_running,
        last_state.get('abebooks_count'),
        time_elapsed
    )

    print_collection_stats(
        "ZVAB",
        zvab_data,
        zvab_running,
        last_state.get('zvab_count'),
        time_elapsed
    )

    # Summary
    total_collected = len(abebooks_data) + len(zvab_data)
    total_possible = TOTAL_ISBNS * 2
    overall_progress = (total_collected / total_possible * 100)

    print(f"\n{'='*70}")
    print(f"📈 Combined Progress")
    print(f"{'='*70}")
    print(f"Total collected: {total_collected:,}/{total_possible:,} ({overall_progress:.1f}%)")
    print(f"AbeBooks:        {len(abebooks_data):,} ({len(abebooks_data)/TOTAL_ISBNS*100:.1f}%)")
    print(f"ZVAB:            {len(zvab_data):,} ({len(zvab_data)/TOTAL_ISBNS*100:.1f}%)")

    # Save current state
    save_state(len(abebooks_data), len(zvab_data))

    print(f"\n{'='*70}\n")


if __name__ == '__main__':
    main()
