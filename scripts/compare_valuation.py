#!/usr/bin/env python3
"""
Interactive Book Valuation Comparison Tool

Compare system-predicted values with manual valuations to improve algorithms.
Works iteratively: one book at a time with detailed reasoning.

Usage:
    python scripts/compare_valuation.py
    python scripts/compare_valuation.py 9780316769488
"""

import sys
import os
import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from isbn_lot_optimizer.service import BookService


class ValuationComparator:
    """Interactive comparison tool for system vs manual valuations."""

    def __init__(self):
        self.db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
        self.service = BookService(self.db_path)
        self.comparison_file = Path.home() / ".isbn_lot_optimizer" / "valuation_comparisons.csv"
        self.comparisons = []

        # Ensure comparison file exists with headers
        if not self.comparison_file.exists():
            self.comparison_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.comparison_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'isbn', 'title', 'condition', 'edition',
                    'system_price', 'manual_price', 'difference', 'percent_diff',
                    'cost_basis', 'system_profit', 'manual_profit', 'profit_diff',
                    'system_rec', 'manual_rec', 'agreement',
                    'model_used', 'confidence', 'ebay_median', 'best_buyback',
                    'notes'
                ])

    def format_price(self, price: Optional[float]) -> str:
        """Format price for display."""
        if price is None or price == 0:
            return "N/A"
        return f"${price:.2f}"

    def format_list(self, items: list) -> str:
        """Format list items with bullets."""
        if not items:
            return "  (none)"
        return "\n".join(f"  • {item}" for item in items)

    def display_system_evaluation(self, evaluation):
        """Display system's evaluation in detail."""
        print("\n" + "="*70)
        print("SYSTEM EVALUATION")
        print("="*70)

        print(f"\nISBN: {evaluation.isbn}")

        # Extract title and author from metadata
        title = 'Unknown'
        author = 'Unknown'
        if evaluation.metadata:
            title = evaluation.metadata.title or 'Unknown'
            if evaluation.metadata.authors:
                author = ', '.join(evaluation.metadata.authors)
            elif evaluation.metadata.canonical_author:
                author = evaluation.metadata.canonical_author

        print(f"Title: {title}")
        print(f"Author: {author}")
        print(f"Condition: {evaluation.condition}")
        if evaluation.edition:
            print(f"Edition: {evaluation.edition}")

        print(f"\n--- ML PREDICTION ---")
        print(f"Predicted Sale Price: {self.format_price(evaluation.estimated_price)}")

        # Routing info
        if hasattr(evaluation, 'routing_info') and evaluation.routing_info:
            routing = evaluation.routing_info
            print(f"Model Used: {routing.get('model', 'unknown')}")
            print(f"Confidence: {routing.get('confidence', 0):.0%}")
            print(f"Model MAE: {self.format_price(routing.get('model_mae'))}")

        print(f"\n--- MARKET DATA ---")
        if evaluation.market:
            market = evaluation.market
            print(f"eBay Sold Median: {self.format_price(market.sold_comps_median)} ({market.sold_count or 0} comps)")
            if market.sold_comps_min and market.sold_comps_max:
                print(f"eBay Price Range: {self.format_price(market.sold_comps_min)} - {self.format_price(market.sold_comps_max)}")
            if market.sold_comps_last_sold_date:
                print(f"Last Sold: {market.sold_comps_last_sold_date}")
            if market.active_count:
                print(f"Active Listings: {market.active_count}")
        else:
            print("No eBay market data available")

        print(f"\n--- BUYBACK DATA ---")
        if evaluation.bookscouter:
            bs = evaluation.bookscouter
            print(f"Best Buyback: {self.format_price(bs.best_price)} ({bs.best_vendor or 'Unknown'})")
            if bs.amazon_sales_rank:
                print(f"Amazon Rank: #{bs.amazon_sales_rank:,}")
            if bs.amazon_lowest_price:
                print(f"Amazon FBM Lowest: {self.format_price(bs.amazon_lowest_price)}")
        else:
            print("No buyback data available")

        print(f"\n--- RECOMMENDATION ---")
        print(f"Decision: {evaluation.probability_label or 'UNKNOWN'}")
        # Fix: probability_score is already 0-100, not 0-1
        prob_score = evaluation.probability_score or 0
        print(f"Probability Score: {prob_score:.1f}/100")

        if evaluation.justification:
            print(f"\nReasoning:")
            print(self.format_list(evaluation.justification))

        # Channel recommendation if available
        if hasattr(evaluation, 'channel_recommendation') and evaluation.channel_recommendation:
            channel = evaluation.channel_recommendation
            print(f"\nSuggested Channel: {channel.get('channel', 'UNKNOWN')}")
            print(f"Expected Profit: {self.format_price(channel.get('expected_profit'))}")
            if channel.get('expected_days_to_sale'):
                print(f"Expected Days to Sale: {channel.get('expected_days_to_sale')}")

    def get_manual_input(self):
        """Get manual valuation from user."""
        print("\n" + "="*70)
        print("YOUR MANUAL EVALUATION")
        print("="*70)

        # Get cost basis first
        while True:
            try:
                cost_input = input("\nWhat did you pay for this book? $").strip()
                if not cost_input:
                    cost_basis = 0.0
                    print("  (Assuming $0 - free book)")
                    break
                cost_basis = float(cost_input)
                if cost_basis < 0:
                    print("Cost cannot be negative. Try again.")
                    continue
                break
            except ValueError:
                print("Invalid amount. Enter a number (e.g., 2.50) or press Enter for free.")

        while True:
            try:
                price_input = input("\nWhat would you price this at? $").strip()
                if not price_input:
                    manual_price = None
                    break
                manual_price = float(price_input)
                if manual_price < 0:
                    print("Price cannot be negative. Try again.")
                    continue
                break
            except ValueError:
                print("Invalid price. Enter a number (e.g., 15.50) or press Enter for N/A.")

        # Calculate profit if both values available
        if manual_price and cost_basis is not None:
            ebay_fees = manual_price * 0.1325 + 0.30  # 13.25% + $0.30
            manual_profit = manual_price - ebay_fees - cost_basis
            print(f"\n  Your projected profit: ${manual_profit:.2f}")
            print(f"    (${manual_price:.2f} sale - ${ebay_fees:.2f} fees - ${cost_basis:.2f} cost)")

        while True:
            decision = input("\nWould you BUY or REJECT? (B/R): ").strip().upper()
            if decision in ['B', 'R', 'BUY', 'REJECT']:
                manual_rec = 'BUY' if decision in ['B', 'BUY'] else 'REJECT'
                break
            print("Please enter B (buy) or R (reject).")

        notes = input("Why? (optional notes): ").strip()

        return manual_price, manual_rec, notes, cost_basis

    def display_comparison(self, evaluation, manual_price, manual_rec, notes, cost_basis):
        """Display side-by-side comparison."""
        print("\n" + "="*70)
        print("COMPARISON")
        print("="*70)

        system_price = evaluation.estimated_price or 0
        # Handle both uppercase and title case probability labels
        prob_label = (evaluation.probability_label or '').upper()
        system_rec = 'BUY' if prob_label in ['HIGH', 'MEDIUM'] else 'REJECT'

        # Price comparison
        print(f"\nPRICE:")
        print(f"  System: {self.format_price(system_price)}")
        print(f"  Manual: {self.format_price(manual_price)}")

        if manual_price and system_price:
            diff = manual_price - system_price
            pct_diff = (diff / system_price * 100) if system_price > 0 else 0

            if abs(diff) < 0.50:
                status = "✓ Close match"
            elif diff > 0:
                status = f"↑ You valued higher by {abs(pct_diff):.1f}%"
            else:
                status = f"↓ System valued higher by {abs(pct_diff):.1f}%"

            print(f"  Difference: {self.format_price(abs(diff))} ({status})")

        # Profit comparison
        if manual_price and system_price and cost_basis is not None:
            print(f"\nPROFIT ANALYSIS:")
            print(f"  Cost Basis: {self.format_price(cost_basis)}")

            # System profit
            system_fees = system_price * 0.1325 + 0.30
            system_profit = system_price - system_fees - cost_basis
            print(f"  System Profit: {self.format_price(system_profit)}")
            print(f"    ({self.format_price(system_price)} - {self.format_price(system_fees)} fees - {self.format_price(cost_basis)} cost)")

            # Manual profit
            manual_fees = manual_price * 0.1325 + 0.30
            manual_profit = manual_price - manual_fees - cost_basis
            print(f"  Your Profit: {self.format_price(manual_profit)}")
            print(f"    ({self.format_price(manual_price)} - {self.format_price(manual_fees)} fees - {self.format_price(cost_basis)} cost)")

            # Profit difference
            profit_diff = manual_profit - system_profit
            if abs(profit_diff) > 0.01:
                print(f"  Profit Difference: {self.format_price(abs(profit_diff))}")

        # Decision comparison
        print(f"\nDECISION:")
        print(f"  System: {system_rec}")
        print(f"  Manual: {manual_rec}")
        agreement = "✓ AGREE" if system_rec == manual_rec else "✗ DISAGREE"
        print(f"  {agreement}")

        if notes:
            print(f"\nYour Notes: {notes}")

        # Save comparison
        self.save_comparison(
            evaluation, system_price, manual_price, system_rec, manual_rec, notes, cost_basis
        )

    def save_comparison(self, evaluation, system_price, manual_price, system_rec, manual_rec, notes, cost_basis):
        """Save comparison to CSV."""
        diff = (manual_price - system_price) if (manual_price and system_price) else None
        pct_diff = ((diff / system_price * 100) if (diff and system_price > 0) else None)
        agreement = system_rec == manual_rec

        # Calculate profits
        system_profit = None
        manual_profit = None
        profit_diff = None
        if cost_basis is not None:
            if system_price:
                system_fees = system_price * 0.1325 + 0.30
                system_profit = system_price - system_fees - cost_basis
            if manual_price:
                manual_fees = manual_price * 0.1325 + 0.30
                manual_profit = manual_price - manual_fees - cost_basis
            if system_profit is not None and manual_profit is not None:
                profit_diff = manual_profit - system_profit

        # Extract title from metadata
        title = 'Unknown'
        if evaluation.metadata and evaluation.metadata.title:
            title = evaluation.metadata.title

        # Extract routing info
        model_used = ''
        confidence = ''
        if hasattr(evaluation, 'routing_info') and evaluation.routing_info:
            model_used = evaluation.routing_info.get('model', '')
            confidence = evaluation.routing_info.get('confidence', '')

        # Market data
        ebay_median = evaluation.market.sold_comps_median if evaluation.market else None
        best_buyback = evaluation.bookscouter.best_price if evaluation.bookscouter else None

        with open(self.comparison_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                evaluation.isbn,
                title,
                evaluation.condition,
                evaluation.edition,
                system_price,
                manual_price,
                diff,
                pct_diff,
                cost_basis,
                system_profit,
                manual_profit,
                profit_diff,
                system_rec,
                manual_rec,
                agreement,
                model_used,
                confidence,
                ebay_median,
                best_buyback,
                notes
            ])

        print(f"\n✓ Comparison saved to {self.comparison_file}")

    def show_reasoning_mode(self, evaluation):
        """Show detailed breakdown of system reasoning."""
        print("\n" + "="*70)
        print("DETAILED REASONING BREAKDOWN")
        print("="*70)

        # Feature importance if available
        if hasattr(evaluation, 'routing_info') and evaluation.routing_info:
            routing = evaluation.routing_info
            if 'feature_importance' in routing and routing['feature_importance']:
                print("\nTop ML Features Contributing to Price:")
                features = sorted(
                    routing['feature_importance'].items(),
                    key=lambda x: abs(x[1]),
                    reverse=True
                )[:10]
                for feature, importance in features:
                    print(f"  • {feature}: {importance:.3f}")

        # Market data details
        if evaluation.market:
            market = evaluation.market
            print(f"\nMarket Data Quality:")
            print(f"  • Sold comps: {market.sold_count or 0}")
            print(f"  • Active listings: {market.active_count or 0}")
            if hasattr(market, 'sell_through_rate') and market.sell_through_rate:
                print(f"  • Sell-through rate: {market.sell_through_rate:.1%}")
            if hasattr(market, 'signed_listings_detected'):
                print(f"  • Signed listings filtered: {market.signed_listings_detected or 0}")
            if hasattr(market, 'lot_listings_detected'):
                print(f"  • Lot listings filtered: {market.lot_listings_detected or 0}")

        # Metadata quality
        if evaluation.metadata:
            meta = evaluation.metadata
            print(f"\nMetadata Completeness:")
            print(f"  • Title: {'✓' if meta.title else '✗'}")
            print(f"  • Author: {'✓' if meta.authors else '✗'}")
            print(f"  • Published: {meta.published_year or 'Unknown'}")
            print(f"  • Pages: {meta.page_count or 'Unknown'}")
            print(f"  • Rating: {meta.average_rating or 'N/A'} ({meta.ratings_count or 0} ratings)")
            if hasattr(meta, 'series_name') and meta.series_name:
                print(f"  • Series: {meta.series_name} #{meta.series_index or '?'}")

        # Decision logic breakdown
        print(f"\nDecision Logic:")
        if evaluation.bookscouter and evaluation.bookscouter.best_price:
            buyback_profit = evaluation.bookscouter.best_price
            print(f"  RULE 1: Buyback profit = {self.format_price(buyback_profit)}")
            if buyback_profit > 0:
                print(f"    → Would trigger BUY if > $0")

        if evaluation.estimated_price:
            ebay_fees = evaluation.estimated_price * 0.1325 + 0.30
            net_profit = evaluation.estimated_price - ebay_fees
            print(f"  RULE 2: eBay net profit = {self.format_price(net_profit)}")
            if net_profit >= 10:
                print(f"    → Would trigger BUY (≥ $10)")
            elif net_profit >= 5:
                print(f"    → Conditional BUY if confidence > 50%")

        if evaluation.probability_score:
            # probability_score is already 0-100, not 0-1
            print(f"  RULE 3: Confidence = {evaluation.probability_score:.1f}%")
            if evaluation.probability_score >= 70:
                print(f"    → High confidence (≥ 70%)")
            elif evaluation.probability_score >= 50:
                print(f"    → Medium confidence (50-70%)")
            else:
                print(f"    → Low confidence (< 50%)")

    def prompt_for_edition(self) -> tuple:
        """Prompt user for edition attributes.

        Returns:
            Tuple of (edition_string, is_signed, is_first_edition)
        """
        edition_parts = []

        is_signed = input("Is it signed? (y/n) [n]: ").strip().lower() == 'y'
        if is_signed:
            edition_parts.append("Signed")

        is_first = input("Is it a first edition? (y/n) [n]: ").strip().lower() == 'y'
        if is_first:
            edition_parts.append("First Edition")

        edition_str = ", ".join(edition_parts) if edition_parts else None
        return (edition_str, is_signed, is_first)

    def compare_book(self, isbn: str, condition: str = "Good", edition: str = None,
                     signed: bool = False, first_edition: bool = False):
        """Compare a single book."""
        print(f"\nEvaluating ISBN {isbn}...")

        # Get system evaluation with edition info
        try:
            evaluation = self.service.evaluate_isbn(
                isbn,
                condition=condition,
                edition=edition,
                include_market=True,
                signed=signed,
                first_edition=first_edition
            )
        except Exception as e:
            print(f"Error evaluating book: {e}")
            return False

        if not evaluation:
            print("Could not evaluate book. ISBN may be invalid.")
            return False

        # Display system evaluation
        self.display_system_evaluation(evaluation)

        # Get manual input
        manual_price, manual_rec, notes, cost_basis = self.get_manual_input()

        # Show comparison
        self.display_comparison(evaluation, manual_price, manual_rec, notes, cost_basis)

        # Interactive menu
        while True:
            print("\n" + "-"*70)
            choice = input("\n[R]easoning | [N]ext book | [Q]uit: ").strip().upper()

            if choice in ['R', 'REASONING']:
                self.show_reasoning_mode(evaluation)
            elif choice in ['N', 'NEXT']:
                return True
            elif choice in ['Q', 'QUIT']:
                return False
            else:
                print("Invalid choice. Enter R, N, or Q.")

    def run(self, start_isbn: Optional[str] = None):
        """Main interactive loop."""
        print("="*70)
        print("INTERACTIVE BOOK VALUATION COMPARISON")
        print("="*70)
        print("\nCompare system predictions with your manual valuations.")
        print(f"Saving comparisons to: {self.comparison_file}")

        # Start with provided ISBN or prompt
        if start_isbn:
            print(f"\nStarting with ISBN: {start_isbn}")
            condition = input("Condition [Good]: ").strip() or "Good"
            edition, signed, first_ed = self.prompt_for_edition()

            if not self.compare_book(start_isbn, condition, edition, signed, first_ed):
                return

        # Interactive loop
        while True:
            print("\n" + "="*70)
            isbn = input("\nEnter ISBN (or 'q' to quit): ").strip()

            if isbn.lower() in ['q', 'quit', 'exit']:
                break

            if not isbn:
                print("Please enter an ISBN.")
                continue

            # Optional condition
            condition = input("Condition [Good]: ").strip() or "Good"

            # Optional edition attributes
            edition, signed, first_ed = self.prompt_for_edition()

            if not self.compare_book(isbn, condition, edition, signed, first_ed):
                break

        print("\n✓ Session complete!")
        print(f"Review your comparisons: {self.comparison_file}")


def main():
    """Main entry point."""
    start_isbn = sys.argv[1] if len(sys.argv) > 1 else None

    comparator = ValuationComparator()
    comparator.run(start_isbn)


if __name__ == '__main__':
    main()
