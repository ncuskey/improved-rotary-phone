#!/usr/bin/env python3
"""
Analyze pricing patterns across eBay, Amazon, and AbeBooks platforms.
Identifies market segmentation, pricing premiums, and platform characteristics.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import statistics

def load_catalog_data():
    """Load all books with multi-platform pricing data."""
    catalog_db = Path.home() / ".isbn_lot_optimizer" / "catalog.db"
    conn = sqlite3.connect(catalog_db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            isbn,
            title,
            authors,
            condition,
            estimated_price,
            ebay_sold_count,
            sold_comps_median,
            abebooks_min_price,
            abebooks_avg_price,
            abebooks_seller_count,
            abebooks_has_new,
            abebooks_has_used,
            signed,
            edition,
            metadata_json
        FROM books
        WHERE estimated_price IS NOT NULL
    """)

    books = []
    for row in cursor.fetchall():
        metadata = json.loads(row[14]) if row[14] else {}
        raw = metadata.get('raw', {})

        # Extract Amazon data from metadata JSON
        amazon_rank = raw.get('AmazonSalesRank')
        amazon_count = raw.get('AmazonCount')
        binding = raw.get('Binding')
        edition = raw.get('Edition', '') or row[13] or ''

        books.append({
            'isbn': row[0],
            'title': row[1],
            'authors': row[2],
            'condition': row[3],
            'binding': binding,
            'estimated_price': row[4],
            'sold_comps_median': row[6],  # eBay sold median
            'ebay_sold_count': row[5],
            'abebooks_min_price': row[7],
            'abebooks_avg_price': row[8],
            'abebooks_seller_count': row[9],
            'abebooks_has_new': row[10],
            'abebooks_has_used': row[11],
            'is_signed': row[12],
            'is_first_edition': 'first' in edition.lower() if edition else False,
            'amazon_rank': amazon_rank,
            'amazon_count': amazon_count,
        })

    conn.close()
    return books

def analyze_platform_patterns(books):
    """Analyze pricing patterns across platforms."""

    # Filter to books with data from multiple platforms
    multi_platform = []
    ebay_only = []
    amazon_only = []
    abebooks_only = []

    for book in books:
        has_ebay = bool(book['ebay_sold_count'] and book['ebay_sold_count'] > 0)
        has_amazon = bool(book['amazon_count'] and book['amazon_count'] > 0)
        has_abebooks = bool(book['abebooks_min_price'] and book['abebooks_min_price'] > 0)

        platform_count = sum([has_ebay, has_amazon, has_abebooks])

        if platform_count >= 2:
            multi_platform.append(book)
        elif has_ebay:
            ebay_only.append(book)
        elif has_amazon:
            amazon_only.append(book)
        elif has_abebooks:
            abebooks_only.append(book)

    print(f"\n{'='*70}")
    print("PLATFORM COVERAGE ANALYSIS")
    print(f"{'='*70}\n")
    print(f"Total books in catalog: {len(books)}")
    print(f"Books with 2+ platforms: {len(multi_platform)} ({len(multi_platform)/len(books)*100:.1f}%)")
    print(f"eBay only: {len(ebay_only)}")
    print(f"Amazon only: {len(amazon_only)}")
    print(f"AbeBooks only: {len(abebooks_only)}")

    # Analyze pricing patterns for multi-platform books
    print(f"\n{'='*70}")
    print("PRICING PATTERNS (Books with Multiple Platforms)")
    print(f"{'='*70}\n")

    # Compare estimated_price (eBay estimate) vs AbeBooks
    ebay_abebooks = [b for b in multi_platform if b['abebooks_min_price'] and b['abebooks_min_price'] > 0]
    if ebay_abebooks:
        ebay_prices = [b['estimated_price'] for b in ebay_abebooks]
        abebooks_mins = [b['abebooks_min_price'] for b in ebay_abebooks]
        abebooks_avgs = [b['abebooks_avg_price'] for b in ebay_abebooks]

        ratios_min = [e/a for e, a in zip(ebay_prices, abebooks_mins) if a > 0]
        ratios_avg = [e/a for e, a in zip(ebay_prices, abebooks_avgs) if a > 0]

        print(f"eBay vs AbeBooks Comparison (n={len(ebay_abebooks)}):")
        print(f"  eBay avg price:        ${statistics.mean(ebay_prices):.2f}")
        print(f"  AbeBooks min avg:      ${statistics.mean(abebooks_mins):.2f}")
        print(f"  AbeBooks avg avg:      ${statistics.mean(abebooks_avgs):.2f}")
        print(f"  eBay/AbeBooks min ratio: {statistics.mean(ratios_min):.2f}x")
        print(f"  eBay/AbeBooks avg ratio: {statistics.mean(ratios_avg):.2f}x")
        print(f"  eBay premium over AbeBooks min: {(statistics.mean(ratios_min)-1)*100:.1f}%")

    # Compare by condition
    print(f"\n{'='*70}")
    print("PRICING BY CONDITION")
    print(f"{'='*70}\n")

    by_condition = defaultdict(lambda: {
        'ebay': [], 'abebooks_min': [], 'abebooks_avg': []
    })

    for book in ebay_abebooks:
        cond = book['condition'] or 'Unknown'
        by_condition[cond]['ebay'].append(book['estimated_price'])
        if book['abebooks_min_price']:
            by_condition[cond]['abebooks_min'].append(book['abebooks_min_price'])
        if book['abebooks_avg_price']:
            by_condition[cond]['abebooks_avg'].append(book['abebooks_avg_price'])

    for cond in sorted(by_condition.keys()):
        data = by_condition[cond]
        if data['ebay'] and data['abebooks_min']:
            ebay_avg = statistics.mean(data['ebay'])
            abe_min = statistics.mean(data['abebooks_min'])
            abe_avg = statistics.mean(data['abebooks_avg']) if data['abebooks_avg'] else 0
            premium = (ebay_avg / abe_min - 1) * 100 if abe_min > 0 else 0

            print(f"{cond:15s} (n={len(data['ebay']):3d}): "
                  f"eBay ${ebay_avg:6.2f} | AbeBooks ${abe_min:6.2f} (min) ${abe_avg:6.2f} (avg) | "
                  f"Premium: {premium:5.1f}%")

    # Compare by binding
    print(f"\n{'='*70}")
    print("PRICING BY BINDING")
    print(f"{'='*70}\n")

    by_binding = defaultdict(lambda: {
        'ebay': [], 'abebooks_min': [], 'abebooks_avg': []
    })

    for book in ebay_abebooks:
        binding = book['binding'] or 'Unknown'
        by_binding[binding]['ebay'].append(book['estimated_price'])
        if book['abebooks_min_price']:
            by_binding[binding]['abebooks_min'].append(book['abebooks_min_price'])
        if book['abebooks_avg_price']:
            by_binding[binding]['abebooks_avg'].append(book['abebooks_avg_price'])

    for binding in sorted(by_binding.keys()):
        data = by_binding[binding]
        if data['ebay'] and data['abebooks_min']:
            ebay_avg = statistics.mean(data['ebay'])
            abe_min = statistics.mean(data['abebooks_min'])
            abe_avg = statistics.mean(data['abebooks_avg']) if data['abebooks_avg'] else 0
            premium = (ebay_avg / abe_min - 1) * 100 if abe_min > 0 else 0

            print(f"{binding:15s} (n={len(data['ebay']):3d}): "
                  f"eBay ${ebay_avg:6.2f} | AbeBooks ${abe_min:6.2f} (min) ${abe_avg:6.2f} (avg) | "
                  f"Premium: {premium:5.1f}%")

    # Special features analysis
    print(f"\n{'='*70}")
    print("PRICING BY SPECIAL FEATURES")
    print(f"{'='*70}\n")

    signed_books = [b for b in ebay_abebooks if b['is_signed']]
    unsigned_books = [b for b in ebay_abebooks if not b['is_signed']]

    if signed_books and unsigned_books:
        signed_ebay = statistics.mean([b['estimated_price'] for b in signed_books])
        unsigned_ebay = statistics.mean([b['estimated_price'] for b in unsigned_books])
        signed_abe = statistics.mean([b['abebooks_min_price'] for b in signed_books if b['abebooks_min_price']])
        unsigned_abe = statistics.mean([b['abebooks_min_price'] for b in unsigned_books if b['abebooks_min_price']])

        print(f"Signed (n={len(signed_books)}):")
        print(f"  eBay:     ${signed_ebay:.2f}")
        print(f"  AbeBooks: ${signed_abe:.2f}")
        print(f"  Premium:  {(signed_ebay/signed_abe-1)*100:.1f}%")
        print(f"\nUnsigned (n={len(unsigned_books)}):")
        print(f"  eBay:     ${unsigned_ebay:.2f}")
        print(f"  AbeBooks: ${unsigned_abe:.2f}")
        print(f"  Premium:  {(unsigned_ebay/unsigned_abe-1)*100:.1f}%")
        print(f"\nSigned vs Unsigned eBay premium: {(signed_ebay/unsigned_ebay-1)*100:.1f}%")
        print(f"Signed vs Unsigned AbeBooks premium: {(signed_abe/unsigned_abe-1)*100:.1f}%")

    first_ed = [b for b in ebay_abebooks if b['is_first_edition']]
    not_first = [b for b in ebay_abebooks if not b['is_first_edition']]

    if first_ed and not_first:
        first_ebay = statistics.mean([b['estimated_price'] for b in first_ed])
        not_first_ebay = statistics.mean([b['estimated_price'] for b in not_first])
        first_abe = statistics.mean([b['abebooks_min_price'] for b in first_ed if b['abebooks_min_price']])
        not_first_abe = statistics.mean([b['abebooks_min_price'] for b in not_first if b['abebooks_min_price']])

        print(f"\nFirst Edition (n={len(first_ed)}):")
        print(f"  eBay:     ${first_ebay:.2f}")
        print(f"  AbeBooks: ${first_abe:.2f}")
        print(f"  Premium:  {(first_ebay/first_abe-1)*100:.1f}%")
        print(f"\nNot First Edition (n={len(not_first)}):")
        print(f"  eBay:     ${not_first_ebay:.2f}")
        print(f"  AbeBooks: ${not_first_abe:.2f}")
        print(f"  Premium:  {(not_first_ebay/not_first_abe-1)*100:.1f}%")

    # Highest premiums analysis
    print(f"\n{'='*70}")
    print("HIGHEST EBAY PREMIUMS OVER ABEBOOKS")
    print(f"{'='*70}\n")

    premiums = []
    for book in ebay_abebooks:
        if book['abebooks_min_price'] and book['abebooks_min_price'] > 0:
            premium = book['estimated_price'] / book['abebooks_min_price']
            premiums.append((premium, book))

    premiums.sort(key=lambda x: x[0], reverse=True)

    print("Top 20 books with highest eBay/AbeBooks price ratios:\n")
    print(f"{'Ratio':>6s} | {'eBay':>7s} | {'AbeBooks':>8s} | {'Title':<50s} | {'Features'}")
    print("-" * 130)

    for ratio, book in premiums[:20]:
        features = []
        if book['is_signed']:
            features.append('Signed')
        if book['is_first_edition']:
            features.append('1st Ed')
        features_str = ', '.join(features) if features else ''

        title = book['title'][:47] + '...' if len(book['title']) > 50 else book['title']

        print(f"{ratio:6.2f}x | ${book['estimated_price']:6.2f} | ${book['abebooks_min_price']:7.2f} | "
              f"{title:<50s} | {features_str}")

    # Lowest premiums (where AbeBooks is higher)
    print(f"\n{'='*70}")
    print("LOWEST EBAY PREMIUMS (Where AbeBooks is More Expensive)")
    print(f"{'='*70}\n")

    print("Bottom 20 books (eBay cheaper than AbeBooks):\n")
    print(f"{'Ratio':>6s} | {'eBay':>7s} | {'AbeBooks':>8s} | {'Title':<50s}")
    print("-" * 110)

    for ratio, book in premiums[-20:]:
        title = book['title'][:47] + '...' if len(book['title']) > 50 else book['title']
        print(f"{ratio:6.2f}x | ${book['estimated_price']:6.2f} | ${book['abebooks_min_price']:7.2f} | {title:<50s}")

    # Market segmentation insights
    print(f"\n{'='*70}")
    print("MARKET SEGMENTATION INSIGHTS")
    print(f"{'='*70}\n")

    # Books where eBay > 2x AbeBooks (collectible market)
    collectible = [b for b in ebay_abebooks
                   if b['abebooks_min_price'] and b['abebooks_min_price'] > 0
                   and b['estimated_price'] / b['abebooks_min_price'] > 2.0]

    # Books where prices are similar (commodity market)
    commodity = [b for b in ebay_abebooks
                 if b['abebooks_min_price'] and b['abebooks_min_price'] > 0
                 and 0.8 <= b['estimated_price'] / b['abebooks_min_price'] <= 1.2]

    # Books where AbeBooks > eBay (academic/specialized)
    academic = [b for b in ebay_abebooks
                if b['abebooks_min_price'] and b['abebooks_min_price'] > 0
                and b['estimated_price'] / b['abebooks_min_price'] < 0.8]

    print(f"Collectible Market (eBay > 2x AbeBooks): {len(collectible)} books ({len(collectible)/len(ebay_abebooks)*100:.1f}%)")
    print(f"  Avg eBay price:     ${statistics.mean([b['estimated_price'] for b in collectible]):.2f}")
    print(f"  Avg AbeBooks price: ${statistics.mean([b['abebooks_min_price'] for b in collectible]):.2f}")
    print(f"  Avg premium:        {statistics.mean([b['estimated_price']/b['abebooks_min_price'] for b in collectible]):.2f}x")

    print(f"\nCommodity Market (prices similar): {len(commodity)} books ({len(commodity)/len(ebay_abebooks)*100:.1f}%)")
    if commodity:
        print(f"  Avg eBay price:     ${statistics.mean([b['estimated_price'] for b in commodity]):.2f}")
        print(f"  Avg AbeBooks price: ${statistics.mean([b['abebooks_min_price'] for b in commodity]):.2f}")

    print(f"\nAcademic/Specialized (AbeBooks > eBay): {len(academic)} books ({len(academic)/len(ebay_abebooks)*100:.1f}%)")
    if academic:
        print(f"  Avg eBay price:     ${statistics.mean([b['estimated_price'] for b in academic]):.2f}")
        print(f"  Avg AbeBooks price: ${statistics.mean([b['abebooks_min_price'] for b in academic]):.2f}")

    return {
        'total_books': len(books),
        'multi_platform': len(multi_platform),
        'ebay_abebooks_comparable': len(ebay_abebooks),
        'collectible_market': len(collectible),
        'commodity_market': len(commodity),
        'academic_market': len(academic),
    }

if __name__ == "__main__":
    print(f"\n{'='*70}")
    print(f"PLATFORM PRICING ANALYSIS")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")

    books = load_catalog_data()
    results = analyze_platform_patterns(books)

    print(f"\n{'='*70}")
    print("ANALYSIS COMPLETE")
    print(f"{'='*70}\n")
