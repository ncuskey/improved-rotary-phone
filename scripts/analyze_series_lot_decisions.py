#!/usr/bin/env python3
"""
Series Lot Decision Analyzer

Analyzes how the lot detection system makes decisions for series books,
particularly for prolific authors (Patterson, Child, etc.).

Usage:
    python scripts/analyze_series_lot_decisions.py --author Patterson
    python scripts/analyze_series_lot_decisions.py --series "Alex Cross"
    python scripts/analyze_series_lot_decisions.py --prolific
    python scripts/analyze_series_lot_decisions.py --all
"""

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.author_aliases import canonical_author as normalize_author_name


# Prolific authors with many series
PROLIFIC_AUTHORS = [
    "James Patterson",
    "Lee Child",
    "Jack Reacher",
    "Stephen King",
    "John Grisham",
    "Nora Roberts",
    "Janet Evanovich",
    "Dean Koontz",
    "Danielle Steel",
    "Tom Clancy"
]


class SeriesLotAnalyzer:
    """Analyzes series lot decisions and market intelligence."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize with database connection."""
        if db_path is None:
            db_path = Path.home() / ".isbn_lot_optimizer" / "books.db"
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

    def get_books_by_author(self, author_name: str) -> List[Dict]:
        """Get all books by author with series information."""
        # Normalize author name for searching
        normalized = normalize_author_name(author_name)

        query = """
        SELECT
            isbn,
            title,
            authors,
            metadata_json,
            estimated_price as estimated_sale_price,
            status
        FROM books
        WHERE
            status = 'ACCEPT'
            AND (
                LOWER(authors) LIKE ?
                OR LOWER(authors) LIKE ?
            )
        """

        cursor = self.conn.execute(query, (
            f'%{author_name.lower()}%',
            f'%{normalized.lower()}%'
        ))

        books = []
        for row in cursor.fetchall():
            book = dict(row)
            # Parse metadata JSON if available and extract series info
            if book['metadata_json']:
                try:
                    metadata = json.loads(book['metadata_json'])
                    book['metadata'] = metadata

                    # Extract series information from metadata
                    book['series_name'] = metadata.get('series_name') or metadata.get('series')
                    book['series_position'] = metadata.get('series_index')
                    book['series_id'] = metadata.get('series_id')
                except:
                    book['metadata'] = {}
                    book['series_name'] = None
                    book['series_position'] = None
                    book['series_id'] = None
            else:
                book['metadata'] = {}
                book['series_name'] = None
                book['series_position'] = None
                book['series_id'] = None

            books.append(book)

        # Sort by series name and position
        books.sort(key=lambda b: (
            b.get('series_name') or 'zzz',  # Put no-series books at end
            b.get('series_position') or 999
        ))

        return books

    def get_lots_for_author(self, author_name: str) -> List[Dict]:
        """Get all lots containing books by author."""
        normalized = normalize_author_name(author_name)

        query = """
        SELECT
            id,
            name,
            strategy,
            book_isbns,
            estimated_value,
            probability_score,
            probability_label,
            justification,
            lot_market_value,
            lot_optimal_size,
            lot_per_book_price,
            lot_comps_count,
            use_lot_pricing
        FROM lots
        WHERE
            LOWER(name) LIKE ?
            OR LOWER(name) LIKE ?
        ORDER BY estimated_value DESC
        """

        cursor = self.conn.execute(query, (
            f'%{author_name.lower()}%',
            f'%{normalized.lower()}%'
        ))

        lots = []
        for row in cursor.fetchall():
            lot = dict(row)
            # Parse JSON fields
            if lot['book_isbns']:
                try:
                    lot['book_isbns'] = json.loads(lot['book_isbns'])
                except:
                    lot['book_isbns'] = []
            else:
                lot['book_isbns'] = []
            lots.append(lot)

        return lots

    def get_series_market_data(self, series_name: str) -> Optional[Dict]:
        """Get eBay lot market data for series."""
        query = """
        SELECT
            total_lots_found,
            median_sold_price,
            median_price_per_book,
            most_common_lot_size,
            complete_set_premium
        FROM series_lot_stats
        WHERE LOWER(series_title) = ?
        """

        cursor = self.conn.execute(query, (series_name.lower(),))
        row = cursor.fetchone()

        if row:
            return dict(row)
        return None

    def group_books_by_series(self, books: List[Dict]) -> Dict[str, List[Dict]]:
        """Group books by series."""
        series_groups = defaultdict(list)

        for book in books:
            series = book.get('series_name') or 'No Series'
            series_groups[series].append(book)

        return dict(series_groups)

    def calculate_individual_value(self, books: List[Dict]) -> Tuple[float, float]:
        """Calculate total individual value and average."""
        total = sum(book.get('estimated_sale_price', 0) or 0 for book in books)
        avg = total / len(books) if books else 0
        return total, avg

    def analyze_series(
        self,
        series_name: str,
        books: List[Dict],
        lot_info: Optional[Dict] = None
    ) -> Dict:
        """Analyze a single series and its lot decision."""

        # Sort books by position
        sorted_books = sorted(
            books,
            key=lambda b: b.get('series_position') or 999
        )

        # Calculate values
        individual_total, individual_avg = self.calculate_individual_value(sorted_books)

        # Get market data
        market_data = self.get_series_market_data(series_name)

        # Determine lot value if market data exists
        lot_value = None
        lot_per_book = None
        if market_data and market_data['median_price_per_book']:
            lot_per_book = market_data['median_price_per_book']
            lot_value = lot_per_book * len(sorted_books)
        elif lot_info and lot_info.get('lot_market_value'):
            lot_value = lot_info['lot_market_value']
            lot_per_book = lot_value / len(sorted_books) if sorted_books else 0

        # Make recommendation
        if lot_value and individual_total:
            if lot_value > individual_total:
                recommendation = "LOT"
                profit_diff = lot_value - individual_total
            else:
                recommendation = "INDIVIDUAL"
                profit_diff = individual_total - lot_value
        else:
            recommendation = "INSUFFICIENT_DATA"
            profit_diff = 0

        # Detect series positions and gaps
        positions = [b.get('series_position') for b in sorted_books if b.get('series_position')]
        if positions:
            max_pos = max(positions)
            have_set = set(positions)
            missing = [i for i in range(1, int(max_pos) + 1) if i not in have_set]
            completion_pct = len(have_set) / max_pos * 100 if max_pos else 0
        else:
            missing = []
            completion_pct = 0

        return {
            'series_name': series_name,
            'book_count': len(sorted_books),
            'books': sorted_books,
            'positions': positions,
            'missing_positions': missing,
            'completion_pct': completion_pct,
            'individual_total': individual_total,
            'individual_avg': individual_avg,
            'lot_value': lot_value,
            'lot_per_book': lot_per_book,
            'recommendation': recommendation,
            'profit_diff': profit_diff,
            'market_data': market_data,
            'lot_info': lot_info
        }

    def analyze_author(self, author_name: str) -> Dict:
        """Perform complete analysis for an author."""
        # Get all books and lots
        books = self.get_books_by_author(author_name)
        lots = self.get_lots_for_author(author_name)

        # Group books by series
        series_groups = self.group_books_by_series(books)

        # Map lots to series
        lot_map = {}
        for lot in lots:
            lot_name = lot['name']
            lot_map[lot_name] = lot

        # Analyze each series
        series_analyses = []
        for series_name, series_books in series_groups.items():
            # Find matching lot
            matching_lot = None
            for lot_name, lot in lot_map.items():
                if series_name.lower() in lot_name.lower():
                    matching_lot = lot
                    break

            analysis = self.analyze_series(series_name, series_books, matching_lot)
            series_analyses.append(analysis)

        # Sort by value
        series_analyses.sort(key=lambda x: x['individual_total'], reverse=True)

        return {
            'author': author_name,
            'total_books': len(books),
            'total_series': len(series_groups),
            'series_analyses': series_analyses,
            'lots': lots
        }


def print_analysis(analysis: Dict, verbose: bool = False):
    """Print formatted analysis report."""
    author = analysis['author']

    print(f"\n{'='*80}")
    print(f"AUTHOR SERIES ANALYSIS: {author}")
    print(f"{'='*80}\n")

    print(f"Total Books Scanned: {analysis['total_books']}")
    print(f"Total Series Detected: {analysis['total_series']}")
    print(f"Current Lots: {len(analysis['lots'])}")

    print(f"\n{'-'*80}")
    print("SERIES BREAKDOWN")
    print(f"{'-'*80}\n")

    for idx, series_analysis in enumerate(analysis['series_analyses'], 1):
        series_name = series_analysis['series_name']
        book_count = series_analysis['book_count']
        completion = series_analysis['completion_pct']

        print(f"{idx}. {series_name}")
        print(f"   - Have: {book_count} books", end="")
        if completion > 0:
            print(f" ({completion:.0f}% complete)")
        else:
            print()

        # Show book positions if available
        if series_analysis['positions'] and verbose:
            positions_str = ", ".join(f"#{int(p)}" for p in sorted(series_analysis['positions']))
            print(f"   - Positions: {positions_str}")

        # Show missing positions
        if series_analysis['missing_positions']:
            missing_count = len(series_analysis['missing_positions'])
            if missing_count <= 10 or verbose:
                missing_str = ", ".join(f"#{m}" for m in series_analysis['missing_positions'][:10])
                if missing_count > 10:
                    missing_str += f"... (+{missing_count - 10} more)"
                print(f"   - Missing: {missing_str}")
            else:
                print(f"   - Missing: {missing_count} books")

        # Show lot status
        if series_analysis['lot_info']:
            lot_name = series_analysis['lot_info']['name']
            strategy = series_analysis['lot_info']['strategy']
            print(f"   - Current Lot: \"{lot_name}\" - {strategy.upper()}")
        else:
            print(f"   - Current Lot: None")

        print(f"\n   DECISION ANALYSIS:")

        # Individual value
        ind_total = series_analysis['individual_total']
        ind_avg = series_analysis['individual_avg']
        print(f"   ✓ Individual Value: ${ind_total:.2f} (${ind_avg:.2f} avg per book)")

        # Lot value
        if series_analysis['lot_value']:
            lot_total = series_analysis['lot_value']
            lot_per = series_analysis['lot_per_book']
            comps = ""
            if series_analysis['market_data']:
                comps_count = series_analysis['market_data'].get('total_lots_found', 0)
                comps = f", {comps_count} eBay comps"
            print(f"   ✓ Lot Market Value: ${lot_total:.2f} (${lot_per:.2f} per book{comps})")
        else:
            print(f"   ✗ Lot Market Value: No data available")

        # Recommendation
        rec = series_analysis['recommendation']
        profit = series_analysis['profit_diff']

        if rec == "LOT":
            print(f"   → RECOMMEND: Sell as LOT (+${profit:.2f} profit)")
        elif rec == "INDIVIDUAL":
            print(f"   → RECOMMEND: Sell INDIVIDUALLY (+${profit:.2f} profit)")
        else:
            print(f"   → RECOMMEND: Insufficient market data")

        # Reasoning
        if series_analysis['market_data'] or series_analysis['lot_info']:
            print(f"\n   REASONING:")

            # Market data insights
            if series_analysis['market_data']:
                md = series_analysis['market_data']
                optimal_size = md.get('most_common_lot_size')
                if optimal_size:
                    print(f"   • Optimal lot size: {optimal_size} books (you have {book_count})")

                premium = md.get('complete_set_premium')
                if premium and completion >= 100:
                    print(f"   • Complete set premium: +{premium:.0%}")
                elif premium and completion < 100:
                    print(f"   • Missing {100-completion:.0f}% of series = no premium")

            # Value comparison
            lot_per = series_analysis.get('lot_per_book')
            if rec == "LOT" and lot_per:
                print(f"   • Per-book pricing higher in lots (${lot_per:.2f} vs ${ind_avg:.2f})")
            elif rec == "INDIVIDUAL":
                if lot_per:
                    print(f"   • Individual pricing higher than lot pricing")
                else:
                    print(f"   • No lot market detected for this series")

        # Opportunities
        if series_analysis['missing_positions'] and completion >= 50 and completion < 100:
            print(f"\n   OPPORTUNITY:")
            missing = series_analysis['missing_positions'][:5]
            missing_str = ", ".join(f"#{m}" for m in missing)
            if len(series_analysis['missing_positions']) > 5:
                missing_str += "..."
            print(f"   ⚠ Acquire books {missing_str} to complete series")

        print()

    # Summary
    print(f"\n{'-'*80}")
    print("SUMMARY")
    print(f"{'-'*80}\n")

    lot_recs = sum(1 for s in analysis['series_analyses'] if s['recommendation'] == 'LOT')
    ind_recs = sum(1 for s in analysis['series_analyses'] if s['recommendation'] == 'INDIVIDUAL')
    no_data = sum(1 for s in analysis['series_analyses'] if s['recommendation'] == 'INSUFFICIENT_DATA')

    print(f"Lots Recommended: {lot_recs} of {analysis['total_series']} series")
    print(f"Individual Sales Recommended: {ind_recs} of {analysis['total_series']} series")
    print(f"Insufficient Data: {no_data} series")

    # Calculate total profit optimization
    total_optimization = sum(
        s['profit_diff'] for s in analysis['series_analyses']
        if s['recommendation'] in ['LOT', 'INDIVIDUAL']
    )
    if total_optimization > 0:
        print(f"\nEstimated Profit Optimization: +${total_optimization:.2f} by following recommendations")

    print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze series lot decisions")
    parser.add_argument('--author', type=str, help='Analyze specific author')
    parser.add_argument('--series', type=str, help='Analyze specific series')
    parser.add_argument('--prolific', action='store_true', help='Analyze all prolific authors')
    parser.add_argument('--all', action='store_true', help='Analyze all authors')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--db', type=str, help='Database path (default: ~/.isbn_lot_optimizer/books.db)')

    args = parser.parse_args()

    # Initialize analyzer
    analyzer = SeriesLotAnalyzer(db_path=args.db)

    # Determine which authors to analyze
    authors_to_analyze = []

    if args.author:
        authors_to_analyze = [args.author]
    elif args.prolific:
        authors_to_analyze = PROLIFIC_AUTHORS
    elif args.all:
        # Get all authors from database
        cursor = analyzer.conn.execute("""
            SELECT DISTINCT authors
            FROM books
            WHERE status = 'ACCEPT' AND series_name IS NOT NULL
        """)
        # Extract first author from each book
        for row in cursor.fetchall():
            author_list = row[0]
            if author_list:
                first_author = author_list.split(',')[0].strip()
                if first_author not in authors_to_analyze:
                    authors_to_analyze.append(first_author)
    else:
        print("Error: Must specify --author, --prolific, or --all")
        parser.print_help()
        return 1

    # Analyze each author
    for author in authors_to_analyze:
        analysis = analyzer.analyze_author(author)

        # Only print if author has books
        if analysis['total_books'] > 0:
            print_analysis(analysis, verbose=args.verbose)

    analyzer.conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
