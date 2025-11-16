#!/usr/bin/env python3
"""
Recent Scans Analyzer

Analyzes the last N scans to show how the system made decisions and routed books.
Perfect for iterative testing: scan 10-20 books, analyze, adjust, repeat.

Usage:
    python scripts/analyze_recent_scans.py --last 20
    python scripts/analyze_recent_scans.py --last 20 --series-only
    python scripts/analyze_recent_scans.py --since "2024-11-16"
"""

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class RecentScansAnalyzer:
    """Analyzes recent scan decisions and routing logic."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize with database connection."""
        if db_path is None:
            db_path = Path.home() / ".isbn_lot_optimizer" / "books.db"
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

    def get_recent_scans(
        self,
        limit: Optional[int] = None,
        since_date: Optional[str] = None,
        series_only: bool = False
    ) -> List[Dict]:
        """Get recent scans from scan_history."""
        query = """
        SELECT
            scan_history.id,
            scan_history.isbn,
            scan_history.scanned_at,
            scan_history.decision,
            scan_history.title,
            scan_history.authors,
            scan_history.estimated_price,
            scan_history.probability_label,
            scan_history.probability_score,
            books.metadata_json,
            books.estimated_price as current_price,
            books.status as current_status
        FROM scan_history
        LEFT JOIN books ON scan_history.isbn = books.isbn
        WHERE 1=1
        """

        params = []

        if since_date:
            query += " AND scan_history.scanned_at >= ?"
            params.append(since_date)

        query += " ORDER BY scan_history.scanned_at DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor = self.conn.execute(query, params)

        scans = []
        for row in cursor.fetchall():
            scan = dict(row)

            # Parse metadata to extract series info
            if scan['metadata_json']:
                try:
                    metadata = json.loads(scan['metadata_json'])
                    scan['series_name'] = metadata.get('series_name') or metadata.get('series')
                    scan['series_position'] = metadata.get('series_index')
                except:
                    scan['series_name'] = None
                    scan['series_position'] = None
            else:
                scan['series_name'] = None
                scan['series_position'] = None

            # Filter if series_only requested
            if series_only and not scan['series_name']:
                continue

            scans.append(scan)

        return scans

    def analyze_decisions(self, scans: List[Dict]) -> Dict:
        """Analyze decision patterns from scans."""
        analysis = {
            'total_scans': len(scans),
            'by_decision': defaultdict(int),
            'by_probability': defaultdict(int),
            'series_books': [],
            'non_series_books': [],
            'accepts': [],
            'rejects': [],
            'avg_price': 0,
            'price_range': (0, 0),
            'series_count': 0,
        }

        prices = []
        series_groups = defaultdict(list)

        for scan in scans:
            # Count decisions
            decision = scan.get('decision') or scan.get('current_status', 'UNKNOWN')
            analysis['by_decision'][decision] += 1

            # Count probability labels
            prob_label = scan.get('probability_label', 'Unknown')
            analysis['by_probability'][prob_label] += 1

            # Track prices
            price = scan.get('estimated_price') or scan.get('current_price', 0)
            if price:
                prices.append(price)

            # Separate series vs non-series
            if scan['series_name']:
                analysis['series_books'].append(scan)
                series_groups[scan['series_name']].append(scan)
            else:
                analysis['non_series_books'].append(scan)

            # Track accepts and rejects
            if decision == 'ACCEPT':
                analysis['accepts'].append(scan)
            elif decision == 'REJECT':
                analysis['rejects'].append(scan)

        # Calculate price stats
        if prices:
            analysis['avg_price'] = sum(prices) / len(prices)
            analysis['price_range'] = (min(prices), max(prices))

        analysis['series_count'] = len(series_groups)
        analysis['series_groups'] = dict(series_groups)

        return analysis

    def identify_lot_opportunities(self, series_groups: Dict[str, List[Dict]]) -> List[Dict]:
        """Identify series that could be bundled into lots."""
        opportunities = []

        for series_name, books in series_groups.items():
            if len(books) < 2:
                continue  # Need at least 2 books for a lot

            # Sort by position
            sorted_books = sorted(
                books,
                key=lambda b: b.get('series_position') or 999
            )

            # Calculate total value
            total_value = sum(
                b.get('estimated_price') or b.get('current_price', 0)
                for b in sorted_books
            )

            # Check positions
            positions = [b.get('series_position') for b in sorted_books if b.get('series_position')]
            if positions:
                max_pos = max(positions)
                have_set = set(positions)
                missing = [i for i in range(1, int(max_pos) + 1) if i not in have_set]
                completion = len(have_set) / max_pos * 100 if max_pos else 0
            else:
                missing = []
                completion = 0

            opportunities.append({
                'series_name': series_name,
                'book_count': len(sorted_books),
                'books': sorted_books,
                'total_value': total_value,
                'avg_value': total_value / len(sorted_books),
                'positions': positions,
                'missing': missing,
                'completion': completion
            })

        # Sort by value
        opportunities.sort(key=lambda x: x['total_value'], reverse=True)

        return opportunities

    def close(self):
        """Close database connection."""
        self.conn.close()


def print_scan_analysis(scans: List[Dict], analysis: Dict):
    """Print formatted scan analysis."""
    print(f"\n{'='*80}")
    print(f"RECENT SCANS ANALYSIS")
    print(f"{'='*80}\n")

    print(f"Total Scans: {analysis['total_scans']}")
    if scans:
        first_scan = scans[-1]['scanned_at']
        last_scan = scans[0]['scanned_at']
        print(f"Date Range: {first_scan} to {last_scan}")

    print(f"\n{'-'*80}")
    print("DECISION BREAKDOWN")
    print(f"{'-'*80}\n")

    for decision, count in sorted(analysis['by_decision'].items()):
        pct = count / analysis['total_scans'] * 100
        print(f"  {decision:15} {count:3} ({pct:5.1f}%)")

    print(f"\n{'-'*80}")
    print("CONFIDENCE BREAKDOWN")
    print(f"{'-'*80}\n")

    for prob_label, count in sorted(analysis['by_probability'].items()):
        pct = count / analysis['total_scans'] * 100
        print(f"  {prob_label:15} {count:3} ({pct:5.1f}%)")

    print(f"\n{'-'*80}")
    print("PRICING")
    print(f"{'-'*80}\n")

    print(f"  Average Price: ${analysis['avg_price']:.2f}")
    print(f"  Range: ${analysis['price_range'][0]:.2f} - ${analysis['price_range'][1]:.2f}")

    print(f"\n{'-'*80}")
    print("SERIES ANALYSIS")
    print(f"{'-'*80}\n")

    print(f"  Series Books: {len(analysis['series_books'])} ({len(analysis['series_books'])/analysis['total_scans']*100:.1f}%)")
    print(f"  Non-Series Books: {len(analysis['non_series_books'])} ({len(analysis['non_series_books'])/analysis['total_scans']*100:.1f}%)")
    print(f"  Unique Series: {analysis['series_count']}")

    if analysis['series_groups']:
        print(f"\n  Series Detected:")
        for series_name, books in sorted(
            analysis['series_groups'].items(),
            key=lambda x: len(x[1]),
            reverse=True
        ):
            positions = [b.get('series_position') for b in books if b.get('series_position')]
            if positions:
                pos_str = ", ".join(f"#{int(p)}" for p in sorted(positions))
                print(f"    - {series_name}: {len(books)} books ({pos_str})")
            else:
                print(f"    - {series_name}: {len(books)} books (positions unknown)")


def print_lot_opportunities(opportunities: List[Dict]):
    """Print lot building opportunities."""
    if not opportunities:
        print(f"\nNo lot opportunities found (need 2+ books per series)")
        return

    print(f"\n{'='*80}")
    print(f"LOT BUILDING OPPORTUNITIES")
    print(f"{'='*80}\n")

    for idx, opp in enumerate(opportunities, 1):
        series = opp['series_name']
        count = opp['book_count']
        total_val = opp['total_value']
        avg_val = opp['avg_value']
        completion = opp['completion']

        print(f"{idx}. {series}")
        print(f"   Books: {count}")
        print(f"   Total Value: ${total_val:.2f} (${avg_val:.2f} avg)")

        if completion > 0:
            print(f"   Completion: {completion:.0f}%")

        if opp['positions']:
            have_str = ", ".join(f"#{int(p)}" for p in sorted(opp['positions']))
            print(f"   Have: {have_str}")

        if opp['missing']:
            missing_str = ", ".join(f"#{m}" for m in opp['missing'][:5])
            if len(opp['missing']) > 5:
                missing_str += f"... (+{len(opp['missing'])-5} more)"
            print(f"   Missing: {missing_str}")

        # Show individual books
        print(f"   Books:")
        for book in opp['books']:
            title = book['title'][:50]
            price = book.get('estimated_price') or book.get('current_price', 0)
            decision = book.get('decision') or book.get('current_status', '?')
            pos = f"#{int(book['series_position'])}" if book.get('series_position') else "?"
            print(f"     {pos:4} {title:50} ${price:6.2f} [{decision}]")

        print()


def print_individual_scans(scans: List[Dict], limit: int = 20):
    """Print individual scan details."""
    print(f"\n{'='*80}")
    print(f"INDIVIDUAL SCAN DETAILS (showing last {min(limit, len(scans))})")
    print(f"{'='*80}\n")

    for scan in scans[:limit]:
        title = scan['title'][:60] if scan['title'] else 'Unknown'
        authors = scan['authors'][:30] if scan['authors'] else 'Unknown'
        price = scan.get('estimated_price') or scan.get('current_price', 0)
        decision = scan.get('decision') or scan.get('current_status', 'UNKNOWN')
        prob = scan.get('probability_label', '?')
        score = scan.get('probability_score', 0)
        series = scan.get('series_name')

        print(f"ISBN: {scan['isbn']}")
        print(f"  Title: {title}")
        print(f"  Author: {authors}")
        if series:
            pos = f"#{int(scan['series_position'])}" if scan.get('series_position') else "?"
            print(f"  Series: {series} ({pos})")
        print(f"  Price: ${price:.2f}")
        print(f"  Decision: {decision} | Confidence: {prob} ({score:.0f}/100)")
        print(f"  Scanned: {scan['scanned_at']}")
        print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze recent scan decisions")
    parser.add_argument('--last', type=int, default=20, help='Number of recent scans to analyze (default: 20)')
    parser.add_argument('--since', type=str, help='Analyze scans since date (YYYY-MM-DD)')
    parser.add_argument('--series-only', action='store_true', help='Only show series books')
    parser.add_argument('--show-all', action='store_true', help='Show all individual scans (not just last 20)')
    parser.add_argument('--db', type=str, help='Database path')

    args = parser.parse_args()

    # Initialize analyzer
    analyzer = RecentScansAnalyzer(db_path=args.db)

    # Get recent scans
    scans = analyzer.get_recent_scans(
        limit=args.last if not args.since else None,
        since_date=args.since,
        series_only=args.series_only
    )

    if not scans:
        print("No scans found matching criteria")
        return 1

    # Analyze decisions
    analysis = analyzer.analyze_decisions(scans)

    # Print main analysis
    print_scan_analysis(scans, analysis)

    # Identify and print lot opportunities
    if analysis['series_groups']:
        opportunities = analyzer.identify_lot_opportunities(analysis['series_groups'])
        print_lot_opportunities(opportunities)

    # Print individual scan details
    show_limit = len(scans) if args.show_all else 20
    print_individual_scans(scans, limit=show_limit)

    analyzer.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
