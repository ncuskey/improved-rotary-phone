#!/usr/bin/env python3
"""Analyze the 20 scanned books with full valuation logic"""

import requests
import json
import sqlite3
from typing import Optional, Tuple

# ISBNs from the database
ISBNS = [
    "9780134093413",  # Campbell Biology
    "9780345299062",  # XPD
    "9780385497466",  # The Brethren
    "9780316154062",  # Void Moon
    "9780385424714",  # The Client
    "9780385517232",  # The Innocent Man
    "9780385515047",  # The Appeal
    "9780316565103",  # The First Gentleman
    "9780385545990",  # Camino Ghosts
    "9780385472944",  # The Runaway Jury
    "9780385548953",  # The Exchange
    "9780399593543",  # Blue Moon (Jack Reacher)
    "9780385340588",  # 61 Hours (Jack Reacher)
    "9780399593512",  # Past Tense (Jack Reacher)
    "9780399593574",  # No Middle Name (Jack Reacher)
    "9780316734943",  # The Closers
    "9780316563796",  # The Waiting
    "9780316069359",  # The Fifth Witness
    "9780316563765",  # Resurrection Walk
    "9780316069519",  # The Gods of Guilt
]

BASE_URL = "https://lothelper.clevergirl.app"
PURCHASE_PRICE = 5.0  # Default assumption

def get_series_context(isbn: str, series_name: Optional[str]) -> Tuple[bool, int]:
    """Check if book is part of an ongoing series we're collecting"""
    if not series_name:
        return False, 0

    # Query the database for other books in this series
    try:
        conn = sqlite3.connect('/Users/nickcuskey/.isbn_lot_optimizer/catalog.db')
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM books WHERE series_name = ? AND isbn != ?",
            (series_name, isbn)
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0, count
    except Exception as e:
        print(f"  [Warning] Could not check series: {e}")
        return False, 0

def calculate_fees(price: float, platform: str) -> Tuple[float, float]:
    """Calculate fees and net proceeds"""
    if platform == "ebay":
        fees = price * 0.1325 + 0.30
    elif platform == "amazon":
        fees = price * 0.15 + 1.80
    else:
        fees = 0
    return fees, price - fees

def make_decision(eval_data: dict, is_series: bool, books_in_series: int) -> Tuple[str, str]:
    """Make buy/don't buy decision"""
    score = eval_data.get('probability_score') or 0
    label = (eval_data.get('probability_label') or '').lower()

    # Calculate profits
    ebay_price = eval_data.get('estimated_price')
    amazon_price = eval_data.get('bookscouter', {}).get('amazon_lowest_price')
    buyback = eval_data.get('bookscouter', {}).get('best_price') or 0
    amazon_rank = eval_data.get('bookscouter', {}).get('amazon_sales_rank')

    ebay_profit = None
    amazon_profit = None
    buyback_profit = None

    if ebay_price:
        _, ebay_net = calculate_fees(ebay_price, "ebay")
        ebay_profit = ebay_net - PURCHASE_PRICE

    if amazon_price:
        _, amazon_net = calculate_fees(amazon_price, "amazon")
        amazon_profit = amazon_net - PURCHASE_PRICE

    if buyback > 0:
        buyback_profit = buyback - PURCHASE_PRICE

    best_profit = max([p for p in [ebay_profit, amazon_profit, buyback_profit] if p is not None], default=None)

    # Determine platform
    best_platform = "None"
    if best_profit:
        if amazon_profit == best_profit:
            best_platform = "Amazon"
        elif ebay_profit == best_profit:
            best_platform = "eBay"
        elif buyback_profit == best_profit:
            best_platform = "Buyback"

    # RULE 1: Guaranteed buyback
    if buyback_profit and buyback_profit > 0:
        vendor = eval_data.get('bookscouter', {}).get('best_vendor', 'vendor')
        if is_series:
            return "BUY ✅", f"Guaranteed ${buyback_profit:.2f} via {vendor} + Series"
        return "BUY ✅", f"Guaranteed ${buyback_profit:.2f} via {vendor}"

    # RULE 1.5: Series completion
    if is_series and books_in_series > 0:
        if best_profit and best_profit >= 3.0 and score >= 50:
            return "BUY ✅", f"Series ({books_in_series} books) + ${best_profit:.2f}"
        if books_in_series >= 3 and best_profit and best_profit >= 1.0:
            return "BUY ✅", f"Near-complete ({books_in_series} books) + ${best_profit:.2f}"
        if books_in_series >= 3 and best_profit and best_profit >= -2.0 and score >= 60:
            return "BUY ✅", f"Strategic completion ({books_in_series} books)"

    # RULE 2: Strong profit ($10+)
    if best_profit and best_profit >= 10:
        if 'high' in label or score >= 60:
            return "BUY ✅", f"Strong: ${best_profit:.2f} via {best_platform}"
        return "BUY ✅", f"${best_profit:.2f} via {best_platform}"

    # RULE 3: Moderate profit ($5-10)
    if best_profit and best_profit >= 5:
        if 'high' in label or score >= 70:
            return "BUY ✅", f"Good confidence + ${best_profit:.2f} via {best_platform}"
        if amazon_rank and amazon_rank < 100000:
            return "BUY ✅", f"Fast-moving + ${best_profit:.2f} via {best_platform}"
        return "DON'T BUY ❌", f"Only ${best_profit:.2f} - needs higher confidence"

    # RULE 4: Small profit
    if best_profit and best_profit > 0:
        if 'high' in label and score >= 80:
            return "BUY ✅", "High confidence offsets low margin"
        return "DON'T BUY ❌", f"Only ${best_profit:.2f} - too thin"

    # RULE 5: Loss
    if best_profit and best_profit <= 0:
        return "DON'T BUY ❌", f"Loss: -${abs(best_profit):.2f}"

    # RULE 6: No pricing
    if 'high' in label and score >= 80:
        return "BUY ✅", "High confidence, verify pricing"

    return "DON'T BUY ❌", "Insufficient data"

def analyze_book(isbn: str) -> None:
    """Analyze a single book"""
    try:
        # Fetch evaluation
        url = f"{BASE_URL}/api/books/{isbn}/evaluate"
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            print(f"\n❌ {isbn}: API error {response.status_code}")
            return

        data = response.json()
        metadata = data.get('metadata', {})
        bookscouter = data.get('bookscouter', {})

        title = metadata.get('title', 'Unknown')
        author = (metadata.get('credited_authors') or metadata.get('authors') or ['Unknown'])[0]
        series_name = metadata.get('series_name')
        series_index = metadata.get('series_index')

        # Check series context
        is_series, books_in_series = get_series_context(isbn, series_name)

        # Calculate profits
        ebay_price = data.get('estimated_price')
        amazon_price = bookscouter.get('amazon_lowest_price')
        buyback = bookscouter.get('best_price') or 0
        amazon_rank = bookscouter.get('amazon_sales_rank')

        ebay_profit = None
        amazon_profit = None
        buyback_profit = None

        if ebay_price:
            ebay_fees, ebay_net = calculate_fees(ebay_price, "ebay")
            ebay_profit = ebay_net - PURCHASE_PRICE

        if amazon_price:
            amazon_fees, amazon_net = calculate_fees(amazon_price, "amazon")
            amazon_profit = amazon_net - PURCHASE_PRICE

        if buyback > 0:
            buyback_profit = buyback - PURCHASE_PRICE

        # Make decision
        decision, reason = make_decision(data, is_series, books_in_series)

        # Print analysis
        print(f"\n{'='*80}")
        print(f"📚 {title}")
        print(f"   By: {author}")
        print(f"   ISBN: {isbn}")

        if series_name:
            series_text = f"📖 Series: {series_name}"
            if series_index:
                series_text += f" #{series_index}"
            if is_series:
                series_text += f" (You have {books_in_series} other books)"
            print(f"   {series_text}")

        print(f"\n{'-'*80}")

        # Profit breakdown
        if ebay_profit is not None:
            print(f"🛒 eBay:    ${ebay_price:.2f} - ${ebay_fees:.2f} fees = ${ebay_profit:.2f} profit")

        if amazon_profit is not None:
            rank_label = ""
            if amazon_rank:
                if amazon_rank < 50000:
                    rank_label = " (Bestseller)"
                elif amazon_rank < 100000:
                    rank_label = " (High demand)"
            print(f"🛒 Amazon:  ${amazon_price:.2f} - ${amazon_fees:.2f} fees = ${amazon_profit:.2f} profit{rank_label}")
            if amazon_rank:
                print(f"           Rank: #{amazon_rank:,}")

        if buyback_profit is not None and buyback > 0:
            vendor = bookscouter.get('best_vendor', 'vendor')
            print(f"🔄 Buyback: ${buyback:.2f} ({vendor}) = ${buyback_profit:.2f} profit")

        print(f"\n{'-'*80}")

        # Decision
        print(f"{decision}: {reason}")

        score = data.get('probability_score')
        label = data.get('probability_label')
        if score:
            print(f"Confidence: {score:.0f}/100 ({label})")

        # Return for summary
        return {
            'isbn': isbn,
            'title': title,
            'decision': decision,
            'profit': max([p for p in [ebay_profit, amazon_profit, buyback_profit] if p is not None], default=0),
            'is_series': is_series
        }

    except Exception as e:
        print(f"\n❌ {isbn}: {str(e)}")
        return None

def main():
    print("=" * 80)
    print("📚 ANALYZING 20 SCANNED BOOKS WITH NEW VALUATION LOGIC")
    print("=" * 80)
    print(f"\nPurchase Price Assumption: ${PURCHASE_PRICE:.2f}")
    print(f"Total Books: {len(ISBNS)}\n")

    results = []
    for isbn in ISBNS:
        result = analyze_book(isbn)
        if result:
            results.append(result)

    # Summary
    print(f"\n\n{'='*80}")
    print("📊 SUMMARY")
    print(f"{'='*80}")

    buy_count = sum(1 for r in results if "BUY ✅" in r['decision'])
    reject_count = len(results) - buy_count

    print(f"Total Analyzed: {len(results)}")
    print(f"✅ BUY: {buy_count}")
    print(f"❌ DON'T BUY: {reject_count}")
    print(f"Acceptance Rate: {buy_count/len(results)*100:.1f}%")

    total_profit = sum(r['profit'] for r in results if "BUY ✅" in r['decision'])
    print(f"\n💰 Total Potential Profit (BUY only): ${total_profit:.2f}")

    if buy_count > 0:
        avg_profit = total_profit / buy_count
        print(f"📈 Average Profit per BUY: ${avg_profit:.2f}")

    series_count = sum(1 for r in results if r['is_series'])
    if series_count > 0:
        print(f"\n📚 Series Books Found: {series_count}")

if __name__ == "__main__":
    main()
