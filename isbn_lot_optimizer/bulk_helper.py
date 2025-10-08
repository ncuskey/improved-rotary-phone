"""
BulkHelper: Optimize book combinations for multi-vendor buyback.

This module analyzes BookScouter vendor offers across your catalog and suggests
optimal book combinations to maximize profit while meeting vendor minimums.
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

    Strategy:
    1. Group offers by vendor
    2. For each vendor, select books using greedy algorithm (highest price first)
    3. Only include vendors where we can meet their minimum
    4. Each book can only be assigned to one vendor (highest bidder wins)

    Args:
        offers: List of all book-vendor offer combinations
        vendor_minimums: Dict of vendor_id -> minimum buyback amount
        max_books_per_vendor: Maximum books to assign to any single vendor

    Returns:
        BulkOptimizationResult with optimized bundles
    """
    if vendor_minimums is None:
        vendor_minimums = VENDOR_MINIMUMS

    # Group offers by vendor
    vendor_offers: Dict[str, List[BookOffer]] = defaultdict(list)
    for offer in offers:
        vendor_offers[offer.vendor_id].append(offer)

    # Track which books have been assigned
    assigned_isbns: set[str] = set()

    # Create bundles for each vendor
    bundles: List[VendorBundle] = []

    # Sort vendors by average offer price (prioritize high-value vendors)
    vendor_avg_prices = []
    for vendor_id, vendor_offer_list in vendor_offers.items():
        if not vendor_offer_list:
            continue
        avg_price = sum(o.price for o in vendor_offer_list) / len(vendor_offer_list)
        vendor_avg_prices.append((vendor_id, avg_price, vendor_offer_list))

    vendor_avg_prices.sort(key=lambda x: x[1], reverse=True)

    # Process each vendor
    for vendor_id, avg_price, vendor_offer_list in vendor_avg_prices:
        # Get vendor name from first offer
        vendor_name = vendor_offer_list[0].vendor_name if vendor_offer_list else f"Vendor {vendor_id}"
        minimum = vendor_minimums.get(vendor_id, 10.0)

        bundle = VendorBundle(
            vendor_id=vendor_id,
            vendor_name=vendor_name,
            minimum_required=minimum,
        )

        # Sort this vendor's offers by price (highest first)
        sorted_offers = sorted(vendor_offer_list, key=lambda x: x.price, reverse=True)

        # Greedily add books until we meet minimum or run out
        for offer in sorted_offers:
            # Skip if book already assigned to another vendor
            if offer.isbn in assigned_isbns:
                continue

            # Skip if we've hit max books for this vendor
            if len(bundle.books) >= max_books_per_vendor:
                break

            # Add this book
            bundle.add_book(offer)
            assigned_isbns.add(offer.isbn)

            # If we've met the minimum and have a good bundle, we can stop
            # But we might want to keep adding if prices are still high
            if bundle.meets_minimum and bundle.total_value >= minimum * 1.5:
                break

        # Only include bundles that meet the minimum
        if bundle.meets_minimum:
            bundles.append(bundle)

    # Calculate totals
    total_value = sum(b.total_value for b in bundles)
    total_books = sum(b.books_count for b in bundles)
    vendors_used = len(bundles)

    # Find unassigned books with offers
    unassigned = []
    for offer in offers:
        if offer.isbn not in assigned_isbns:
            unassigned.append(offer)

    # Deduplicate unassigned (keep best offer per ISBN)
    unassigned_by_isbn: Dict[str, BookOffer] = {}
    for offer in unassigned:
        if offer.isbn not in unassigned_by_isbn or offer.price > unassigned_by_isbn[offer.isbn].price:
            unassigned_by_isbn[offer.isbn] = offer

    return BulkOptimizationResult(
        bundles=bundles,
        total_value=total_value,
        total_books=total_books,
        vendors_used=vendors_used,
        unassigned_books=list(unassigned_by_isbn.values()),
    )


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
