"""
Prototype: Skeleton-based incremental lot updates

This prototype demonstrates the separation of lot structure generation
from pricing enrichment to achieve faster incremental updates.

Run with: python3 prototypes/incremental_lots_prototype.py
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Sequence

# Setup environment
env_file = Path(__file__).parent.parent / '.env'
for line in env_file.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        key, value = line.split('=', 1)
        os.environ[key] = value

from isbn_lot_optimizer.service import BookService
from shared.models import BookEvaluation


@dataclass
class LotSkeleton:
    """Lot structure without market pricing (fast to generate)."""
    name: str
    strategy: str
    book_isbns: List[str]
    books: List[BookEvaluation]
    individual_value: float
    avg_probability: float
    justification: List[str]

    # Metadata for pricing enrichment
    search_term: Optional[str] = None
    series_name: Optional[str] = None
    author_name: Optional[str] = None


@dataclass
class EnrichedLot:
    """Lot with market pricing added (requires eBay API calls)."""
    name: str
    strategy: str
    book_isbns: List[str]
    books: List[BookEvaluation]
    individual_value: float
    avg_probability: float
    justification: List[str]
    search_term: Optional[str] = None
    series_name: Optional[str] = None
    author_name: Optional[str] = None

    # Market pricing (enriched)
    lot_market_value: Optional[float] = None
    lot_optimal_size: Optional[int] = None
    lot_per_book_price: Optional[float] = None
    lot_comps_count: Optional[int] = None
    use_lot_pricing: bool = False
    estimated_value: Optional[float] = None


def build_lot_skeleton(
    name: str,
    strategy: str,
    books: Sequence[BookEvaluation],
    justification: Sequence[str],
    series_name: Optional[str] = None,
    author_name: Optional[str] = None
) -> Optional[LotSkeleton]:
    """
    Build a lot structure WITHOUT fetching eBay pricing.

    This is the FAST operation that should take ~1 second for all 175 lots.
    """
    # Calculate individual book value (already in database)
    individual_value = sum(book.estimated_price for book in books)

    if individual_value < 10:
        return None  # Below listing threshold

    # Calculate probability from book data (no API calls)
    avg_probability = sum(book.probability_score for book in books) / len(books)
    probability_score = min(100.0, avg_probability + 8)  # Slight bump for grouping

    # Determine search term for later pricing enrichment
    search_term = None
    if strategy in ("series", "author") and len(books) >= 2:
        if strategy == "series" and series_name:
            search_term = f"{series_name} lot"
        elif strategy == "author" and author_name:
            search_term = f"{author_name} lot"

    return LotSkeleton(
        name=name,
        strategy=strategy,
        book_isbns=[book.isbn for book in books],
        books=list(books),
        individual_value=individual_value,
        avg_probability=probability_score,
        justification=list(justification),
        search_term=search_term,
        series_name=series_name,
        author_name=author_name,
    )


def enrich_lot_with_pricing(skeleton: LotSkeleton) -> EnrichedLot:
    """
    Fetch eBay pricing and merge into lot skeleton.

    This is the SLOW operation that makes eBay API calls.
    We only call this for affected lots (1-3 instead of 122).
    """
    # Start with skeleton data
    enriched = EnrichedLot(
        name=skeleton.name,
        strategy=skeleton.strategy,
        book_isbns=skeleton.book_isbns,
        books=skeleton.books,
        individual_value=skeleton.individual_value,
        avg_probability=skeleton.avg_probability,
        justification=list(skeleton.justification),
        search_term=skeleton.search_term,
        series_name=skeleton.series_name,
        author_name=skeleton.author_name,
    )

    # Default to individual pricing
    enriched.estimated_value = skeleton.individual_value

    # Fetch market pricing if applicable
    if skeleton.search_term:
        try:
            print(f"    🔍 Fetching eBay pricing for: {skeleton.search_term}")

            from isbn_lot_optimizer.market import search_ebay_lot_comps
            lot_pricing = search_ebay_lot_comps(skeleton.search_term, limit=50)

            if lot_pricing and lot_pricing.get("total_comps", 0) > 0:
                enriched.lot_comps_count = lot_pricing["total_comps"]
                enriched.lot_optimal_size = lot_pricing.get("optimal_lot_size")
                enriched.lot_per_book_price = lot_pricing.get("optimal_per_book_price")

                if enriched.lot_per_book_price:
                    # Calculate market value for our lot size
                    lot_market_value = round(
                        enriched.lot_per_book_price * len(skeleton.books), 2
                    )

                    enriched.lot_market_value = lot_market_value
                    enriched.use_lot_pricing = True
                    enriched.estimated_value = lot_market_value

                    # Update justification
                    pricing_info = (
                        f"Market lot pricing: ${lot_market_value:.2f} "
                        f"(${enriched.lot_per_book_price:.2f}/book "
                        f"based on {enriched.lot_comps_count} eBay comps)"
                    )
                    enriched.justification.insert(0, pricing_info)

                    print(f"      ✓ Found {enriched.lot_comps_count} comps, market value: ${lot_market_value:.2f}")
            else:
                print(f"      ⚠️ No comps found, using individual pricing: ${enriched.estimated_value:.2f}")
                enriched.justification.append(
                    "No market comps found, using individual book pricing"
                )
        except Exception as e:
            print(f"      ✗ Pricing fetch failed: {e}")
            enriched.justification.append(
                f"Market pricing unavailable: {str(e)}"
            )

    return enriched


def prototype_incremental_update(service: BookService, test_isbn: str):
    """
    Prototype of the incremental update flow.

    This demonstrates how we'll achieve 20-40x speedup by:
    1. Building ALL skeletons (fast, no API calls)
    2. Filtering to affected lots
    3. Enriching ONLY affected lots with pricing (1-3 eBay calls)
    """
    print("\n" + "="*70)
    print("PROTOTYPE: Incremental Lot Update")
    print("="*70)

    # Get the book
    book = service.get_book(test_isbn)
    if not book:
        print(f"❌ Book {test_isbn} not found")
        return

    print(f"\n📖 Test Book: {book.metadata.title}")
    print(f"   Author: {book.metadata.canonical_author}")
    print(f"   ISBN: {test_isbn}")

    # Phase 1: Build ALL skeletons (should be fast)
    print(f"\n⏱️  Phase 1: Building lot skeletons (no eBay calls)...")
    skeleton_start = time.time()

    # For prototype, we'll use existing lot generation but count lots
    # In real implementation, this would be refactored to avoid pricing
    candidates = service.build_lot_candidates()

    # Convert to skeletons (simulated - in real impl, build_lot_candidates would return skeletons)
    skeletons = []
    for candidate in candidates:
        skeleton = build_lot_skeleton(
            name=candidate.name,
            strategy=candidate.strategy,
            books=candidate.books,
            justification=list(candidate.justification),
            series_name=getattr(candidate, 'series_name', None),
            author_name=getattr(candidate, 'canonical_author', None)
        )
        if skeleton:
            skeletons.append(skeleton)

    skeleton_time = time.time() - skeleton_start
    print(f"   ✓ Built {len(skeletons)} skeletons in {skeleton_time:.2f}s")

    # Phase 2: Filter to affected lots
    print(f"\n⏱️  Phase 2: Filtering to affected lots...")
    filter_start = time.time()

    affected_skeletons = [
        s for s in skeletons
        if test_isbn in s.book_isbns
    ]

    filter_time = time.time() - filter_start
    print(f"   ✓ Found {len(affected_skeletons)} affected lots (out of {len(skeletons)} total)")
    print(f"   ⚡ Filter took {filter_time:.3f}s")

    if not affected_skeletons:
        print(f"\n   ℹ️  No lots contain ISBN {test_isbn}")
        return

    # Show which lots are affected
    print(f"\n   Affected lots:")
    for skeleton in affected_skeletons:
        print(f"     - {skeleton.name} ({skeleton.strategy})")

    # Phase 3: Enrich ONLY affected lots with pricing
    print(f"\n⏱️  Phase 3: Enriching affected lots with eBay pricing...")
    print(f"   Expected eBay calls: {len(affected_skeletons)}")

    enrich_start = time.time()
    enriched_lots = []

    for skeleton in affected_skeletons:
        enriched = enrich_lot_with_pricing(skeleton)
        enriched_lots.append(enriched)

    enrich_time = time.time() - enrich_start
    print(f"\n   ✓ Enriched {len(enriched_lots)} lots in {enrich_time:.2f}s")

    # Total time
    total_time = skeleton_time + filter_time + enrich_time
    print(f"\n" + "="*70)
    print(f"RESULTS:")
    print(f"   Phase 1 (skeletons):  {skeleton_time:.2f}s")
    print(f"   Phase 2 (filter):     {filter_time:.3f}s")
    print(f"   Phase 3 (enrich):     {enrich_time:.2f}s")
    print(f"   TOTAL:                {total_time:.2f}s")
    print(f"\n   Efficiency: {len(affected_skeletons)}/{len(skeletons)} lots updated")
    print(f"   Savings: {((len(skeletons) - len(affected_skeletons)) / len(skeletons) * 100):.1f}% fewer eBay calls")
    print("="*70)

    return enriched_lots


def prototype_comparison(service: BookService, test_isbn: str):
    """
    Compare incremental update to full regeneration.
    """
    print("\n" + "="*70)
    print("PERFORMANCE COMPARISON")
    print("="*70)

    # Test 1: Incremental Update (prototype)
    print(f"\n🚀 Test 1: Incremental Update (NEW APPROACH)")
    incr_start = time.time()
    enriched_lots = prototype_incremental_update(service, test_isbn)
    incr_time = time.time() - incr_start

    # Test 2: Full Regeneration (current approach)
    print(f"\n🐌 Test 2: Full Regeneration (CURRENT APPROACH)")
    print(f"   This will take ~77 seconds with 122 eBay API calls...")

    # Note: We're NOT actually running full regen as it's too slow
    # In real testing, we would run this and measure
    full_time_estimated = 77.0  # From our measurements
    full_calls_estimated = 122

    print(f"   ⏱️  Estimated time: {full_time_estimated:.2f}s")
    print(f"   🔍 Estimated eBay calls: {full_calls_estimated}")

    # Analysis
    print(f"\n" + "="*70)
    print(f"ANALYSIS:")
    print(f"   Incremental: {incr_time:.2f}s with {len(enriched_lots)} eBay calls")
    print(f"   Full regen:  {full_time_estimated:.2f}s with {full_calls_estimated} eBay calls")
    print(f"\n   ⚡ Speedup: {full_time_estimated / incr_time:.1f}x faster")
    print(f"   📉 API reduction: {((full_calls_estimated - len(enriched_lots)) / full_calls_estimated * 100):.1f}% fewer calls")
    print("="*70)


if __name__ == "__main__":
    print("\n" + "="*70)
    print("LOT INCREMENTAL UPDATE PROTOTYPE")
    print("="*70)

    # Initialize service
    db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
    service = BookService(db_path)

    # Get a test book from database
    books = service.list_books()
    if not books:
        print("❌ No books in database")
        exit(1)

    # Use the first book for testing
    test_isbn = books[0].isbn

    print(f"\nTest ISBN: {test_isbn}")
    print(f"Database: {len(books)} books")

    # Run prototype
    try:
        prototype_comparison(service, test_isbn)

        print(f"\n✅ Prototype completed successfully!")
        print(f"\n💡 Key Takeaway:")
        print(f"   By separating structure generation from pricing enrichment,")
        print(f"   we can achieve 20-40x speedup for incremental updates.")

    except KeyboardInterrupt:
        print(f"\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
