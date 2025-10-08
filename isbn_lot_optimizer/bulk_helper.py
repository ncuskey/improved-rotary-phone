"""
BulkHelper: Optimize book combinations for multi-vendor buyback.

This module analyzes BookScouter vendor offers across your catalog and suggests
optimal book combinations to maximize profit while meeting vendor minimums.

Two-Phase Optimization Strategy:
---------------------------------
Phase 1 (Greedy Assignment):
  - Sort vendors by average offer price (prioritize high-value vendors)
  - Each vendor greedily selects books by price (highest first)
  - Books can only be assigned to one vendor

Phase 2 (Rescue & Redistribution):
  - Identify bundles below minimum (these have $0 value, not sum of prices!)
  - For each failing bundle:
    * TRY RESCUE: Move books from successful bundles with low opportunity cost
      - Only move if source bundle stays above minimum
      - Opportunity cost = difference between current and new vendor's offer
    * IF RESCUE FAILS: Redistribute failing bundle's books to maximize total profit
      - Assign each book to best alternative vendor that can accept it

Key Principle:
  Bundle value = total_price IF meets_minimum ELSE 0.0

This ensures we maximize actual sellable value, not theoretical totals that
can't be realized due to minimums.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple
from collections import defaultdict


# Vendor minimum buyback requirements (in USD)
# Based on common industry standards - update as needed
VENDOR_MINIMUMS = {
    "6": 10.0,      # eCampus
    "7": 10.0,      # CollegeBooksDirect
    "16": 10.0,     # Valore
    "19": 10.0,     # TextbookRush
    "49": 10.0,     # MyBookCart
    "50": 10.0,     # Bookstores.com
    "67": 10.0,     # TopDollar4Books
    "70": 10.0,     # TextbookAgent
    "73": 10.0,     # RentText
    "77": 10.0,     # TextbookManiac
    "809": 10.0,    # BooksRun
    "824": 5.0,     # Comic Blessing
    "836": 5.0,     # World of Books - Sell Your Books
    "841": 10.0,    # Empire Text
}


@dataclass
class BookOffer:
    """A single book with its offer from a specific vendor."""
    isbn: str
    title: str
    vendor_id: str
    vendor_name: str
    price: float
    condition: str = "Good"
    quantity: int = 1


@dataclass
class VendorBundle:
    """Optimized bundle of books for a single vendor."""
    vendor_id: str
    vendor_name: str
    minimum_required: float
    books: List[BookOffer] = field(default_factory=list)
    total_value: float = 0.0
    meets_minimum: bool = False
    books_count: int = 0

    def add_book(self, book: BookOffer) -> None:
        """Add a book to this bundle."""
        self.books.append(book)
        self.total_value += book.price * book.quantity
        self.books_count += book.quantity
        self.meets_minimum = self.total_value >= self.minimum_required

    def get_remaining_needed(self) -> float:
        """How much more value is needed to meet minimum."""
        return max(0.0, self.minimum_required - self.total_value)


@dataclass
class BulkOptimizationResult:
    """Result of bulk optimization across all vendors."""
    bundles: List[VendorBundle] = field(default_factory=list)
    total_value: float = 0.0
    total_books: int = 0
    vendors_used: int = 0
    unassigned_books: List[BookOffer] = field(default_factory=list)


def extract_offers_from_books(books: Sequence) -> List[BookOffer]:
    """
    Extract all vendor offers from a list of BookEvaluation objects.

    Args:
        books: List of BookEvaluation objects with bookscouter data

    Returns:
        List of BookOffer objects, one per book-vendor combination
    """
    offers: List[BookOffer] = []

    for book in books:
        # Check if book has bookscouter data
        bookscouter = getattr(book, "bookscouter", None)
        if not bookscouter or not bookscouter.offers:
            continue

        # Get book details
        isbn = book.isbn
        title = getattr(book.metadata, "title", "Unknown")
        condition = book.condition
        quantity = getattr(book, "quantity", 1)

        # Create an offer for each vendor
        for vendor_offer in bookscouter.offers:
            if vendor_offer.price <= 0:
                continue

            offers.append(BookOffer(
                isbn=isbn,
                title=title,
                vendor_id=vendor_offer.vendor_id,
                vendor_name=vendor_offer.vendor_name,
                price=vendor_offer.price,
                condition=condition,
                quantity=quantity,
            ))

    return offers


def optimize_vendor_bundles(
    offers: List[BookOffer],
    *,
    vendor_minimums: Optional[Dict[str, float]] = None,
    max_books_per_vendor: int = 100,
) -> BulkOptimizationResult:
    """
    Optimize book assignments to vendors to maximize total profit.

    Two-phase strategy:
    1. Phase 1: Greedy assignment by vendor priority (highest avg price first)
    2. Phase 2: Rescue failing bundles (below minimum = $0 value)
       - Try moving low-opportunity-cost books from successful bundles
       - If rescue fails, redistribute failing bundle books to maximize total profit

    Key principle: Bundles below minimum have ZERO value, not sum of individual prices.

    Args:
        offers: List of all book-vendor offer combinations
        vendor_minimums: Dict of vendor_id -> minimum buyback amount
        max_books_per_vendor: Maximum books to assign to any single vendor

    Returns:
        BulkOptimizationResult with optimized bundles
    """
    if vendor_minimums is None:
        vendor_minimums = VENDOR_MINIMUMS

    # Group offers by ISBN (all vendors for each book)
    offers_by_isbn: Dict[str, List[BookOffer]] = defaultdict(list)
    for offer in offers:
        offers_by_isbn[offer.isbn].append(offer)

    # Group offers by vendor
    vendor_offers: Dict[str, List[BookOffer]] = defaultdict(list)
    for offer in offers:
        vendor_offers[offer.vendor_id].append(offer)

    # === PHASE 1: Initial greedy assignment ===
    assigned_isbns: set[str] = set()
    isbn_to_vendor: Dict[str, str] = {}  # Track which vendor got each ISBN

    all_bundles: Dict[str, VendorBundle] = {}  # vendor_id -> bundle

    # Sort vendors by average offer price (prioritize high-value vendors)
    vendor_avg_prices = []
    for vendor_id, vendor_offer_list in vendor_offers.items():
        if not vendor_offer_list:
            continue
        avg_price = sum(o.price for o in vendor_offer_list) / len(vendor_offer_list)
        vendor_avg_prices.append((vendor_id, avg_price, vendor_offer_list))

    vendor_avg_prices.sort(key=lambda x: x[1], reverse=True)

    # Build initial bundles
    for vendor_id, avg_price, vendor_offer_list in vendor_avg_prices:
        vendor_name = vendor_offer_list[0].vendor_name if vendor_offer_list else f"Vendor {vendor_id}"
        minimum = vendor_minimums.get(vendor_id, 10.0)

        bundle = VendorBundle(
            vendor_id=vendor_id,
            vendor_name=vendor_name,
            minimum_required=minimum,
        )

        # Sort offers by price (highest first)
        sorted_offers = sorted(vendor_offer_list, key=lambda x: x.price, reverse=True)

        for offer in sorted_offers:
            if offer.isbn in assigned_isbns:
                continue
            if len(bundle.books) >= max_books_per_vendor:
                break

            bundle.add_book(offer)
            assigned_isbns.add(offer.isbn)
            isbn_to_vendor[offer.isbn] = vendor_id

            # Stop if we've met minimum and have decent buffer
            if bundle.meets_minimum and bundle.total_value >= minimum * 1.5:
                break

        all_bundles[vendor_id] = bundle

    # === PHASE 2: Rescue failing bundles ===
    failing_bundles = [b for b in all_bundles.values() if not b.meets_minimum]
    successful_bundles = [b for b in all_bundles.values() if b.meets_minimum]

    for failing_bundle in failing_bundles:
        needed = failing_bundle.get_remaining_needed()

        # Try to rescue by pulling books from successful bundles
        rescued = _try_rescue_bundle(
            failing_bundle,
            successful_bundles,
            offers_by_isbn,
            isbn_to_vendor,
            vendor_minimums,
        )

        if not rescued:
            # Can't rescue - redistribute this bundle's books to maximize profit
            _redistribute_bundle(
                failing_bundle,
                successful_bundles,
                offers_by_isbn,
                isbn_to_vendor,
                max_books_per_vendor,
            )

    # Rebuild final bundles list (only successful ones have value)
    final_bundles = [b for b in all_bundles.values() if b.meets_minimum]

    # Calculate totals
    total_value = sum(b.total_value for b in final_bundles)
    total_books = sum(b.books_count for b in final_bundles)
    vendors_used = len(final_bundles)

    # Find unassigned books
    final_assigned_isbns = set()
    for bundle in final_bundles:
        for book in bundle.books:
            final_assigned_isbns.add(book.isbn)

    unassigned_by_isbn: Dict[str, BookOffer] = {}
    for isbn, isbn_offers in offers_by_isbn.items():
        if isbn not in final_assigned_isbns:
            # Keep best offer for this ISBN
            best_offer = max(isbn_offers, key=lambda o: o.price)
            unassigned_by_isbn[isbn] = best_offer

    return BulkOptimizationResult(
        bundles=final_bundles,
        total_value=total_value,
        total_books=total_books,
        vendors_used=vendors_used,
        unassigned_books=list(unassigned_by_isbn.values()),
    )


def _try_rescue_bundle(
    failing_bundle: VendorBundle,
    successful_bundles: List[VendorBundle],
    offers_by_isbn: Dict[str, List[BookOffer]],
    isbn_to_vendor: Dict[str, str],
    vendor_minimums: Dict[str, float],
) -> bool:
    """
    Try to rescue a failing bundle by moving books from successful bundles.

    Strategy: Look for books in successful bundles where:
    1. The book has an offer from the failing vendor
    2. Moving it won't drop the source bundle below minimum
    3. The opportunity cost is low (small difference between offers)

    Returns:
        True if bundle was rescued (now meets minimum), False otherwise
    """
    needed = failing_bundle.get_remaining_needed()
    if needed <= 0:
        return True

    # Find candidate books to steal from successful bundles
    candidates: List[Tuple[float, BookOffer, VendorBundle]] = []  # (opportunity_cost, offer, source_bundle)

    for source_bundle in successful_bundles:
        # How much buffer does this bundle have above minimum?
        buffer = source_bundle.total_value - source_bundle.minimum_required

        for book in source_bundle.books:
            # Does failing bundle have an offer for this book?
            book_offers = offers_by_isbn.get(book.isbn, [])
            failing_vendor_offer = None
            for offer in book_offers:
                if offer.vendor_id == failing_bundle.vendor_id:
                    failing_vendor_offer = offer
                    break

            if not failing_vendor_offer:
                continue

            # Would removing this book drop source below minimum?
            if book.price > buffer:
                continue  # Can't afford to lose this book

            # Calculate opportunity cost (what we lose by moving it)
            opportunity_cost = book.price - failing_vendor_offer.price

            candidates.append((opportunity_cost, failing_vendor_offer, source_bundle))

    if not candidates:
        return False

    # Sort by opportunity cost (lowest first - best moves)
    candidates.sort(key=lambda x: x[0])

    # Try moving books until we meet minimum
    moved_value = 0.0
    for opp_cost, offer, source_bundle in candidates:
        # Remove book from source bundle
        book_to_remove = None
        for book in source_bundle.books:
            if book.isbn == offer.isbn:
                book_to_remove = book
                break

        if not book_to_remove:
            continue

        source_bundle.books.remove(book_to_remove)
        source_bundle.total_value -= book_to_remove.price
        source_bundle.books_count -= book_to_remove.quantity
        source_bundle.meets_minimum = source_bundle.total_value >= source_bundle.minimum_required

        # Add book to failing bundle
        failing_bundle.add_book(offer)
        isbn_to_vendor[offer.isbn] = failing_bundle.vendor_id

        if failing_bundle.meets_minimum:
            return True

    return failing_bundle.meets_minimum


def _redistribute_bundle(
    failing_bundle: VendorBundle,
    successful_bundles: List[VendorBundle],
    offers_by_isbn: Dict[str, List[BookOffer]],
    isbn_to_vendor: Dict[str, str],
    max_books_per_vendor: int,
) -> None:
    """
    Redistribute a failing bundle's books to successful bundles to maximize total profit.

    Since this bundle can't meet minimum (value = $0), we reassign its books to
    vendors who will pay the most and can accept them.
    """
    # Remove all books from failing bundle
    books_to_redistribute = list(failing_bundle.books)
    failing_bundle.books.clear()
    failing_bundle.total_value = 0.0
    failing_bundle.books_count = 0
    failing_bundle.meets_minimum = False

    # For each book, find best alternative vendor from successful bundles
    for book in books_to_redistribute:
        book_offers = offers_by_isbn.get(book.isbn, [])

        # Find best offer from successful bundles
        best_offer = None
        best_bundle = None

        for offer in sorted(book_offers, key=lambda o: o.price, reverse=True):
            # Find the bundle for this vendor
            target_bundle = None
            for bundle in successful_bundles:
                if bundle.vendor_id == offer.vendor_id:
                    target_bundle = bundle
                    break

            if not target_bundle:
                continue

            # Check if bundle can accept more books
            if len(target_bundle.books) >= max_books_per_vendor:
                continue

            best_offer = offer
            best_bundle = target_bundle
            break

        if best_offer and best_bundle:
            # Add to best bundle
            best_bundle.add_book(best_offer)
            isbn_to_vendor[best_offer.isbn] = best_bundle.vendor_id


def suggest_additional_books(
    bundle: VendorBundle,
    available_offers: List[BookOffer],
    assigned_isbns: set[str],
) -> List[BookOffer]:
    """
    Suggest additional books to help a bundle meet its minimum.

    Args:
        bundle: The bundle that needs more books
        available_offers: All available offers for this vendor
        assigned_isbns: ISBNs already assigned to other vendors

    Returns:
        List of suggested book offers, sorted by price (descending)
    """
    remaining_needed = bundle.get_remaining_needed()
    if remaining_needed <= 0:
        return []

    # Filter to unassigned books
    candidates = [
        offer for offer in available_offers
        if offer.isbn not in assigned_isbns
        and offer.vendor_id == bundle.vendor_id
    ]

    # Sort by price
    candidates.sort(key=lambda x: x.price, reverse=True)

    # Return enough to meet minimum
    suggestions = []
    value_so_far = 0.0
    for offer in candidates:
        suggestions.append(offer)
        value_so_far += offer.price
        if value_so_far >= remaining_needed:
            break

    return suggestions


def format_bundle_summary(bundle: VendorBundle) -> str:
    """Format a bundle as a readable summary string."""
    status = "✓ Meets minimum" if bundle.meets_minimum else "✗ Below minimum"
    lines = [
        f"{bundle.vendor_name} (ID: {bundle.vendor_id})",
        f"  Minimum: ${bundle.minimum_required:.2f}",
        f"  Total Value: ${bundle.total_value:.2f}",
        f"  Books: {bundle.books_count}",
        f"  Status: {status}",
    ]
    return "\n".join(lines)
