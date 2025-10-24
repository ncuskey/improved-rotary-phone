#!/usr/bin/env python3
"""
Bulk Book Analysis Tool
Fetches book data and runs through the LotHelper valuation process
"""

import requests
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

BASE_URL = "https://lothelper.clevergirl.app"

@dataclass
class ProfitAnalysis:
    ebay_price: Optional[float]
    ebay_fees: Optional[float]
    ebay_net: Optional[float]
    ebay_profit: Optional[float]

    amazon_price: Optional[float]
    amazon_fees: Optional[float]
    amazon_net: Optional[float]
    amazon_profit: Optional[float]

    buyback_offer: Optional[float]
    buyback_profit: Optional[float]

    best_profit: Optional[float]
    best_platform: str

@dataclass
class BookAnalysis:
    isbn: str
    title: Optional[str]
    author: Optional[str]
    series_name: Optional[str]
    series_index: Optional[int]

    estimated_price: Optional[float]
    confidence_score: Optional[float]
    confidence_label: Optional[str]

    amazon_rank: Optional[int]
    amazon_lowest: Optional[float]
    buyback_best: Optional[float]
    buyback_vendor: Optional[str]

    profit: ProfitAnalysis
    recommendation: str
    reason: str
    is_series_book: bool

def calculate_ebay_fees(sale_price: float) -> Tuple[float, float]:
    """Calculate eBay fees: 13.25% + $0.30"""
    fees = sale_price * 0.1325 + 0.30
    net = sale_price - fees
    return fees, net

def calculate_amazon_fees(sale_price: float) -> Tuple[float, float]:
    """Calculate Amazon fees: 15% + $1.80"""
    fees = sale_price * 0.15 + 1.80
    net = sale_price - fees
    return fees, net

def calculate_profits(evaluation: Dict, purchase_price: float = 5.0) -> ProfitAnalysis:
    """Calculate all three profit paths"""
    # eBay path
    ebay_price = evaluation.get('estimated_price')
    ebay_fees, ebay_net, ebay_profit = None, None, None
    if ebay_price:
        ebay_fees, ebay_net = calculate_ebay_fees(ebay_price)
        ebay_profit = ebay_net - purchase_price

    # Amazon path
    amazon_price = evaluation.get('bookscouter', {}).get('amazon_lowest_price')
    amazon_fees, amazon_net, amazon_profit = None, None, None
    if amazon_price:
        amazon_fees, amazon_net = calculate_amazon_fees(amazon_price)
        amazon_profit = amazon_net - purchase_price

    # Buyback path
    buyback_offer = evaluation.get('bookscouter', {}).get('best_price')
    buyback_profit = None
    if buyback_offer:
        buyback_profit = buyback_offer - purchase_price

    # Find best profit
    profits = [p for p in [ebay_profit, amazon_profit, buyback_profit] if p is not None]
    best_profit = max(profits) if profits else None

    # Determine best platform
    best_platform = "None"
    if best_profit:
        if amazon_profit == best_profit:
            best_platform = "Amazon"
        elif ebay_profit == best_profit:
            best_platform = "eBay"
        elif buyback_profit == best_profit:
            best_platform = "Buyback"

    return ProfitAnalysis(
        ebay_price=ebay_price,
        ebay_fees=ebay_fees,
        ebay_net=ebay_net,
        ebay_profit=ebay_profit,
        amazon_price=amazon_price,
        amazon_fees=amazon_fees,
        amazon_net=amazon_net,
        amazon_profit=amazon_profit,
        buyback_offer=buyback_offer,
        buyback_profit=buyback_profit,
        best_profit=best_profit,
        best_platform=best_platform
    )

def make_buy_decision(evaluation: Dict, profit: ProfitAnalysis, is_series: bool = False, books_in_series: int = 0) -> Tuple[str, str]:
    """Make buy/don't buy decision based on rules"""
    score = evaluation.get('probability_score', 0) or 0
    label = (evaluation.get('probability_label') or '').lower()
    amazon_rank = evaluation.get('bookscouter', {}).get('amazon_sales_rank')

    best_profit = profit.best_profit
    best_platform = profit.best_platform

    # RULE 1: Guaranteed buyback
    if profit.buyback_profit and profit.buyback_profit > 0:
        vendor = evaluation.get('bookscouter', {}).get('best_vendor', 'vendor')
        if is_series:
            return "BUY", f"Guaranteed ${profit.buyback_profit:.2f} via {vendor} + Series completion"
        return "BUY", f"Guaranteed ${profit.buyback_profit:.2f} profit via {vendor}"

    # RULE 1.5: Series completion
    if is_series and books_in_series > 0:
        if best_profit and best_profit >= 3.0 and score >= 50:
            return "BUY", f"Series ({books_in_series} books) + ${best_profit:.2f} profit"
        if books_in_series >= 3 and best_profit and best_profit >= 1.0:
            return "BUY", f"Near-complete series ({books_in_series} books) + ${best_profit:.2f}"
        if books_in_series >= 3 and best_profit and best_profit >= -2.0 and score >= 60:
            return "BUY", f"Complete series ({books_in_series} books) - strategic buy"

    # RULE 2: Strong profit ($10+)
    if best_profit and best_profit >= 10:
        if label and ('high' in label or score >= 60):
            return "BUY", f"Strong: ${best_profit:.2f} net via {best_platform}"
        return "BUY", f"Net profit ${best_profit:.2f} via {best_platform}"

    # RULE 3: Moderate profit ($5-10)
    if best_profit and best_profit >= 5:
        if label and ('high' in label or score >= 70):
            return "BUY", f"Good confidence + ${best_profit:.2f} via {best_platform}"
        if amazon_rank and amazon_rank < 100000:
            return "BUY", f"Fast-moving + ${best_profit:.2f} via {best_platform}"
        return "DON'T BUY", f"Only ${best_profit:.2f} profit - needs higher confidence"

    # RULE 4: Small profit ($1-5)
    if best_profit and best_profit > 0:
        if label and 'high' in label and score >= 80:
            return "BUY", "Very high confidence offsets low margin"
        return "DON'T BUY", f"Net profit only ${best_profit:.2f} - too thin"

    # RULE 5: Loss
    if best_profit and best_profit <= 0:
        return "DON'T BUY", f"Would lose ${abs(best_profit):.2f} after fees"

    # RULE 6: No pricing data
    if label and 'high' in label and score >= 80:
        return "BUY", "Very high confidence but verify pricing"

    return "DON'T BUY", "Insufficient profit margin or confidence"

def analyze_book(isbn: str, purchase_price: float = 5.0) -> Optional[BookAnalysis]:
    """Fetch and analyze a single book"""
    try:
        # Fetch evaluation
        url = f"{BASE_URL}/api/books/{isbn}/evaluate"
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            print(f"❌ {isbn}: Error {response.status_code}")
            return None

        evaluation = response.json()

        # Extract data
        metadata = evaluation.get('metadata', {})
        bookscouter = evaluation.get('bookscouter', {})

        title = metadata.get('title')
        author = (metadata.get('credited_authors') or metadata.get('authors') or [None])[0]
        series_name = metadata.get('series_name')
        series_index = metadata.get('series_index')

        # Calculate profits
        profit = calculate_profits(evaluation, purchase_price)

        # Make decision
        is_series = series_name is not None
        books_in_series = 0  # Would query DB in real app
        recommendation, reason = make_buy_decision(evaluation, profit, is_series, books_in_series)

        return BookAnalysis(
            isbn=isbn,
            title=title,
            author=author,
            series_name=series_name,
            series_index=series_index,
            estimated_price=evaluation.get('estimated_price'),
            confidence_score=evaluation.get('probability_score'),
            confidence_label=evaluation.get('probability_label'),
            amazon_rank=bookscouter.get('amazon_sales_rank'),
            amazon_lowest=bookscouter.get('amazon_lowest_price'),
            buyback_best=bookscouter.get('best_price'),
            buyback_vendor=bookscouter.get('best_vendor'),
            profit=profit,
            recommendation=recommendation,
            reason=reason,
            is_series_book=is_series
        )

    except Exception as e:
        print(f"❌ {isbn}: {str(e)}")
        return None

def print_analysis(book: BookAnalysis):
    """Print formatted analysis for a book"""
    print(f"\n{'=' * 80}")
    print(f"📚 {book.title or 'Unknown Title'}")
    print(f"   By: {book.author or 'Unknown Author'}")
    print(f"   ISBN: {book.isbn}")

    if book.series_name:
        series_text = f"{book.series_name}"
        if book.series_index:
            series_text += f" #{book.series_index}"
        print(f"   📖 Series: {series_text}")

    print(f"\n{'─' * 80}")

    # Profit breakdown
    if book.profit.ebay_profit is not None:
        print(f"🛒 eBay Route:")
        print(f"   Sale: ${book.profit.ebay_price:.2f}  Fees: -${book.profit.ebay_fees:.2f}")
        print(f"   Net Profit: ${book.profit.ebay_profit:.2f}")

    if book.profit.amazon_profit is not None:
        print(f"\n🛒 Amazon Route:")
        print(f"   Sale: ${book.profit.amazon_price:.2f}  Fees: -${book.profit.amazon_fees:.2f}")
        print(f"   Net Profit: ${book.profit.amazon_profit:.2f}")
        if book.amazon_rank:
            rank_label = "Bestseller" if book.amazon_rank < 50000 else "High demand" if book.amazon_rank < 100000 else "Moderate"
            print(f"   Rank: #{book.amazon_rank:,} ({rank_label})")

    if book.profit.buyback_profit is not None and book.profit.buyback_profit > 0:
        print(f"\n🔄 Buyback Route:")
        print(f"   Offer: ${book.profit.buyback_offer:.2f} ({book.buyback_vendor})")
        print(f"   Net Profit: ${book.profit.buyback_profit:.2f}")

    print(f"\n{'─' * 80}")

    # Best option
    if book.profit.best_profit:
        emoji = "✅" if book.recommendation == "BUY" else "❌"
        print(f"{emoji} {book.recommendation}: {book.reason}")
        print(f"   Best Profit: ${book.profit.best_profit:.2f} via {book.profit.best_platform}")
    else:
        print(f"❌ {book.recommendation}: {book.reason}")

    if book.confidence_score:
        print(f"   Confidence: {book.confidence_score:.0f}/100 ({book.confidence_label})")

def main():
    print("📚 LotHelper Bulk Book Analysis")
    print("=" * 80)
    print("\nEnter ISBNs (one per line, empty line to finish):")
    print("Example: 9780307387899")
    print()

    isbns = []
    while True:
        isbn = input("> ").strip()
        if not isbn:
            break
        isbns.append(isbn)

    if not isbns:
        print("No ISBNs provided. Exiting.")
        return

    print(f"\n\n🔍 Analyzing {len(isbns)} book(s)...\n")

    results = []
    for isbn in isbns:
        analysis = analyze_book(isbn)
        if analysis:
            results.append(analysis)
            print_analysis(analysis)

    # Summary
    print(f"\n\n{'=' * 80}")
    print("📊 SUMMARY")
    print(f"{'=' * 80}")
    print(f"Total Books Analyzed: {len(results)}")

    buy_count = sum(1 for r in results if r.recommendation == "BUY")
    reject_count = len(results) - buy_count
    print(f"✅ Recommended BUY: {buy_count}")
    print(f"❌ Recommended REJECT: {reject_count}")

    total_profit = sum(r.profit.best_profit for r in results if r.profit.best_profit and r.recommendation == "BUY")
    print(f"\n💰 Total Potential Profit (BUY recommendations): ${total_profit:.2f}")

    if buy_count > 0:
        avg_profit = total_profit / buy_count
        print(f"📈 Average Profit per BUY: ${avg_profit:.2f}")

    # Platform breakdown
    platforms = {}
    for r in results:
        if r.recommendation == "BUY":
            platform = r.profit.best_platform
            platforms[platform] = platforms.get(platform, 0) + 1

    if platforms:
        print(f"\n🎯 Best Exit Strategy Distribution:")
        for platform, count in sorted(platforms.items(), key=lambda x: x[1], reverse=True):
            print(f"   {platform}: {count} books")

    # Series opportunities
    series_books = [r for r in results if r.is_series_book]
    if series_books:
        print(f"\n📚 Series Opportunities: {len(series_books)} books")
        series_names = {}
        for r in series_books:
            series_names[r.series_name] = series_names.get(r.series_name, 0) + 1
        for series, count in sorted(series_names.items(), key=lambda x: x[1], reverse=True):
            print(f"   {series}: {count} books")

if __name__ == "__main__":
    main()
