#!/usr/bin/env python3
"""
Visualize enrichment progress over time.
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from collections import defaultdict
import numpy as np

# Set style
plt.style.use('seaborn-v0_8-darkgrid')

def get_series_lot_progress():
    """Get series lot enrichment progress over time."""
    db_path = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'

    if not db_path.exists():
        return None

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Get series enriched over time (bucketed by hour)
    cursor.execute("""
        SELECT
            datetime(scraped_at, 'unixepoch', 'start of hour') as hour,
            COUNT(DISTINCT series_id) as series_count,
            COUNT(*) as lots_count
        FROM series_lot_comps
        WHERE scraped_at IS NOT NULL
        GROUP BY hour
        ORDER BY hour
    """)

    results = cursor.fetchall()
    conn.close()

    if not results:
        return None

    # Convert to cumulative
    hours = []
    cumulative_series = []
    cumulative_lots = []
    series_sum = 0
    lots_sum = 0

    for hour_str, series_count, lots_count in results:
        try:
            hour = datetime.fromisoformat(hour_str)
            hours.append(hour)
            series_sum += series_count
            lots_sum += lots_count
            cumulative_series.append(series_sum)
            cumulative_lots.append(lots_sum)
        except:
            continue

    return {
        'hours': hours,
        'cumulative_series': cumulative_series,
        'cumulative_lots': cumulative_lots,
        'total_series': series_sum,
        'total_lots': lots_sum
    }


def get_isbn_progress():
    """Get ISBN enrichment progress over time."""
    db_path = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'

    if not db_path.exists():
        return None

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Get ISBNs enriched over time (bucketed by hour)
    cursor.execute("""
        SELECT
            datetime(last_enrichment_at, 'start of hour') as hour,
            COUNT(*) as isbn_count
        FROM cached_books
        WHERE last_enrichment_at IS NOT NULL
        GROUP BY hour
        ORDER BY hour
    """)

    results = cursor.fetchall()
    conn.close()

    if not results:
        return None

    # Convert to cumulative
    hours = []
    cumulative_isbns = []
    isbn_sum = 0

    for hour_str, isbn_count in results:
        try:
            hour = datetime.fromisoformat(hour_str)
            hours.append(hour)
            isbn_sum += isbn_count
            cumulative_isbns.append(isbn_sum)
        except:
            continue

    return {
        'hours': hours,
        'cumulative_isbns': cumulative_isbns,
        'total_isbns': isbn_sum
    }


def create_visualizations():
    """Create comprehensive enrichment visualizations."""
    print("Fetching enrichment data...")

    series_data = get_series_lot_progress()
    isbn_data = get_isbn_progress()

    if not series_data and not isbn_data:
        print("No enrichment data available yet")
        return

    # Create figure with subplots
    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3)

    # 1. Series Lot Enrichment - Cumulative Progress
    if series_data:
        ax1 = fig.add_subplot(gs[0, 0])
        ax1.plot(series_data['hours'], series_data['cumulative_series'],
                 'b-', linewidth=2, label='Series Enriched')
        ax1.fill_between(series_data['hours'], series_data['cumulative_series'],
                         alpha=0.3, color='blue')
        ax1.set_title('Series Lot Enrichment - Cumulative Progress', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Time')
        ax1.set_ylabel('Series Enriched', color='b')
        ax1.tick_params(axis='y', labelcolor='b')
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')

        # Add lots found on secondary axis
        ax1_twin = ax1.twinx()
        ax1_twin.plot(series_data['hours'], series_data['cumulative_lots'],
                      'g--', linewidth=2, label='Lots Found', alpha=0.7)
        ax1_twin.set_ylabel('Lots Found', color='g')
        ax1_twin.tick_params(axis='y', labelcolor='g')

        # Add legend
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax1_twin.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

    # 2. ISBN Enrichment - Cumulative Progress
    if isbn_data:
        ax2 = fig.add_subplot(gs[0, 1])
        ax2.plot(isbn_data['hours'], isbn_data['cumulative_isbns'],
                 'r-', linewidth=2, label='ISBNs Enriched')
        ax2.fill_between(isbn_data['hours'], isbn_data['cumulative_isbns'],
                         alpha=0.3, color='red')
        ax2.set_title('ISBN Enrichment - Cumulative Progress', fontsize=14, fontweight='bold')
        ax2.set_xlabel('Time')
        ax2.set_ylabel('ISBNs Enriched', color='r')
        ax2.tick_params(axis='y', labelcolor='r')
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
        ax2.legend(loc='upper left')

    # 3. Series Lot Enrichment - Rate per Hour
    if series_data and len(series_data['hours']) > 1:
        ax3 = fig.add_subplot(gs[1, 0])

        # Calculate rate (items per hour)
        rates = []
        for i in range(1, len(series_data['cumulative_series'])):
            delta_series = series_data['cumulative_series'][i] - series_data['cumulative_series'][i-1]
            rates.append(delta_series)

        # Use hours[1:] since we skip the first point
        if rates:
            ax3.bar(series_data['hours'][1:], rates, width=0.03, alpha=0.7, color='steelblue')
            ax3.set_title('Series Enrichment Rate (per hour)', fontsize=14, fontweight='bold')
            ax3.set_xlabel('Time')
            ax3.set_ylabel('Series per Hour')
            ax3.grid(True, alpha=0.3, axis='y')
            ax3.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
            plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha='right')

    # 4. ISBN Enrichment - Rate per Hour
    if isbn_data and len(isbn_data['hours']) > 1:
        ax4 = fig.add_subplot(gs[1, 1])

        # Calculate rate
        rates = []
        for i in range(1, len(isbn_data['cumulative_isbns'])):
            delta_isbns = isbn_data['cumulative_isbns'][i] - isbn_data['cumulative_isbns'][i-1]
            rates.append(delta_isbns)

        if rates:
            ax4.bar(isbn_data['hours'][1:], rates, width=0.03, alpha=0.7, color='coral')
            ax4.set_title('ISBN Enrichment Rate (per hour)', fontsize=14, fontweight='bold')
            ax4.set_xlabel('Time')
            ax4.set_ylabel('ISBNs per Hour')
            ax4.grid(True, alpha=0.3, axis='y')
            ax4.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
            plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45, ha='right')

    # 5. Combined Progress - Percentage Complete
    ax5 = fig.add_subplot(gs[2, :])

    if series_data:
        series_total = 12770  # Total series
        series_pct = [(count / series_total * 100) for count in series_data['cumulative_series']]
        ax5.plot(series_data['hours'], series_pct, 'b-', linewidth=2.5,
                label='Series Lot Enrichment', marker='o', markersize=4, alpha=0.8)

    if isbn_data:
        isbn_total = 18756  # Total ISBNs
        isbn_pct = [(count / isbn_total * 100) for count in isbn_data['cumulative_isbns']]
        ax5.plot(isbn_data['hours'], isbn_pct, 'r-', linewidth=2.5,
                label='ISBN Enrichment', marker='s', markersize=4, alpha=0.8)

    ax5.set_title('Combined Progress - Percentage Complete', fontsize=14, fontweight='bold')
    ax5.set_xlabel('Time')
    ax5.set_ylabel('Progress (%)')
    ax5.set_ylim(0, 100)
    ax5.grid(True, alpha=0.3)
    ax5.legend(loc='upper left', fontsize=11)
    ax5.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
    plt.setp(ax5.xaxis.get_majorticklabels(), rotation=45, ha='right')

    # Add horizontal line at 100%
    ax5.axhline(y=100, color='green', linestyle='--', alpha=0.3, linewidth=1)

    # Main title
    fig.suptitle('📊 Enrichment Progress Dashboard', fontsize=18, fontweight='bold', y=0.995)

    # Save figure
    output_path = Path.home() / 'Desktop' / 'enrichment_progress.png'
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"\n✅ Visualization saved to: {output_path}")

    # Also display
    plt.show()

    # Print summary stats
    print("\n" + "="*60)
    print("ENRICHMENT SUMMARY")
    print("="*60)

    if series_data:
        print(f"\n📚 Series Lot Enrichment:")
        print(f"   Total Series Enriched: {series_data['total_series']:,}")
        print(f"   Total Lots Found: {series_data['total_lots']:,}")
        if series_data['total_series'] > 0:
            avg_lots = series_data['total_lots'] / series_data['total_series']
            print(f"   Average Lots per Series: {avg_lots:.1f}")

    if isbn_data:
        print(f"\n📖 ISBN Enrichment:")
        print(f"   Total ISBNs Enriched: {isbn_data['total_isbns']:,}")

    print("\n" + "="*60)


if __name__ == '__main__':
    create_visualizations()
