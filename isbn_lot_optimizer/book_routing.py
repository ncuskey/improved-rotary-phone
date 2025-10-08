"""
Book Routing Strategy: Intelligent routing of books to optimal sales channels.

This module implements a multi-factor decision engine to determine whether a book
should be:
1. Listed individually on eBay
2. Included in a multi-book lot
3. Sold to a bulk buyback vendor

The routing logic balances profitability, resale confidence, time investment,
and strategic lot-building opportunities.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from .models import BookEvaluation


class SalesChannel(Enum):
    """Possible sales channels for a book."""
    EBAY_INDIVIDUAL = "ebay_individual"  # List as single item on eBay
    EBAY_LOT = "ebay_lot"  # Include in multi-book eBay lot
    BULK_VENDOR = "bulk_vendor"  # Sell to BookScouter vendor
    HOLD = "hold"  # Hold for strategic lot building


@dataclass
class RoutingDecision:
    """Result of routing algorithm for a single book."""
    channel: SalesChannel
    confidence: float  # 0.0-1.0, how confident we are in this decision
    reasoning: list[str]  # Human-readable justification
    expected_profit: float  # Expected profit in USD
    expected_days_to_sale: Optional[int]  # Estimated time to sell


# ============================================================================
# ROUTING THRESHOLDS & PARAMETERS
# ============================================================================

# Minimum eBay value to justify listing time and fees
MIN_EBAY_INDIVIDUAL_VALUE = 10.0

# If eBay value is below this, strongly prefer bulk vendor
STRONG_BULK_PREFERENCE_THRESHOLD = 7.0

# Probability score thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.7
MEDIUM_CONFIDENCE_THRESHOLD = 0.4
LOW_CONFIDENCE_THRESHOLD = 0.2

# Amazon Sales Rank thresholds (Books category)
# Lower rank = higher popularity/velocity
AMAZON_HIGH_VELOCITY_RANK = 100_000  # Top 100k = fast mover
AMAZON_MEDIUM_VELOCITY_RANK = 500_000  # 100k-500k = moderate
AMAZON_LOW_VELOCITY_RANK = 1_000_000  # 500k-1M = slow
# > 1M = very slow/niche

# Last sold recency thresholds (for eBay sold comps)
RECENT_SALE_DAYS = 30
MODERATE_SALE_DAYS = 90
STALE_SALE_DAYS = 180

# Bulk vendor value ratio threshold
# If bulk offer is > 70% of eBay value, consider bulk route
BULK_VALUE_RATIO_THRESHOLD = 0.7


# ============================================================================
# ROUTING ALGORITHM
# ============================================================================

def route_book(book: BookEvaluation) -> RoutingDecision:
    """
    Determine optimal sales channel for a book.

    Decision Logic Flow:

    1. **Low Value Check**: If eBay value < $10, route to bulk vendor
       - Listing fees + time investment not worth it for low-value items

    2. **High Value + High Confidence**: Route to eBay individual
       - eBay value >= $10
       - High probability score (>0.7) OR high Amazon velocity (<100k rank)
       - Recent sold comps (<30 days)

    3. **High Value + Low Confidence**: Consider bulk vendor
       - eBay value >= $10 but <$15
       - Low probability score (<0.4) AND (low Amazon rank OR stale sold comps)
       - Bulk offer is competitive (>70% of eBay value)
       - Risk mitigation: take guaranteed bulk money over uncertain eBay sale

    4. **Lot Building Opportunity**: Route to lot
       - Book fits into a valuable series/author/theme lot
       - Book has more value as part of lot than individually
       - Evaluated separately by lot optimization engine

    5. **Default to eBay Individual**: If no other criteria met
       - Medium value + medium confidence
       - Worth the risk of listing

    Args:
        book: BookEvaluation with all market data

    Returns:
        RoutingDecision with channel, confidence, and reasoning
    """
    reasoning: list[str] = []

    # Extract key metrics
    ebay_value = book.estimated_price or 0.0
    probability = book.probability_score or 0.0
    bulk_price = book.bookscouter.best_price if book.bookscouter else 0.0
    amazon_rank = book.bookscouter.amazon_sales_rank if book.bookscouter else None

    # Parse last sold date from market data
    last_sold_days = _parse_last_sold_days(book)

    # Calculate bulk value ratio
    bulk_ratio = bulk_price / ebay_value if ebay_value > 0 else 0.0

    # ========================================================================
    # RULE 1: Low Value → Bulk Vendor
    # ========================================================================
    if ebay_value < MIN_EBAY_INDIVIDUAL_VALUE:
        reasoning.append(
            f"eBay value ${ebay_value:.2f} below ${MIN_EBAY_INDIVIDUAL_VALUE} threshold"
        )

        if bulk_price > 0:
            reasoning.append(
                f"Bulk vendor offers ${bulk_price:.2f} - immediate sale, no fees"
            )
            return RoutingDecision(
                channel=SalesChannel.BULK_VENDOR,
                confidence=0.9,
                reasoning=reasoning,
                expected_profit=bulk_price,
                expected_days_to_sale=7  # Typical bulk vendor processing time
            )
        else:
            reasoning.append("No bulk offers available, but still not worth eBay listing")
            return RoutingDecision(
                channel=SalesChannel.HOLD,
                confidence=0.6,
                reasoning=reasoning,
                expected_profit=0.0,
                expected_days_to_sale=None
            )

    # ========================================================================
    # RULE 2: High Value + High Confidence → eBay Individual
    # ========================================================================
    high_confidence = probability >= HIGH_CONFIDENCE_THRESHOLD
    high_velocity = amazon_rank and amazon_rank < AMAZON_HIGH_VELOCITY_RANK
    recent_sales = last_sold_days and last_sold_days < RECENT_SALE_DAYS

    if high_confidence or high_velocity or recent_sales:
        if high_confidence:
            reasoning.append(
                f"High resale confidence ({probability:.0%}) - strong eBay market"
            )
        if high_velocity:
            reasoning.append(
                f"Amazon rank {amazon_rank:,} indicates high demand/velocity"
            )
        if recent_sales:
            reasoning.append(
                f"Recent eBay sale within {last_sold_days} days - active market"
            )

        reasoning.append(
            f"eBay value ${ebay_value:.2f} justifies individual listing"
        )

        # Estimate days to sale based on velocity indicators
        if high_velocity or recent_sales:
            days_to_sale = 14  # Fast mover
        elif high_confidence:
            days_to_sale = 30  # Moderate
        else:
            days_to_sale = 45  # Slower

        # Calculate expected profit (eBay value minus ~15% fees)
        expected_profit = ebay_value * 0.85

        return RoutingDecision(
            channel=SalesChannel.EBAY_INDIVIDUAL,
            confidence=0.85 if (high_confidence and high_velocity) else 0.75,
            reasoning=reasoning,
            expected_profit=expected_profit,
            expected_days_to_sale=days_to_sale
        )

    # ========================================================================
    # RULE 3: High Value + Low Confidence → Bulk Vendor (if competitive)
    # ========================================================================
    low_confidence = probability < LOW_CONFIDENCE_THRESHOLD
    low_velocity = amazon_rank and amazon_rank > AMAZON_LOW_VELOCITY_RANK
    stale_sales = last_sold_days and last_sold_days > STALE_SALE_DAYS
    competitive_bulk = bulk_ratio >= BULK_VALUE_RATIO_THRESHOLD

    if (low_confidence or low_velocity or stale_sales) and competitive_bulk:
        reasoning.append(
            f"Low confidence in eBay sale: prob={probability:.0%}"
        )

        if low_velocity:
            reasoning.append(
                f"Low Amazon velocity (rank {amazon_rank:,}) - slow market"
            )
        if stale_sales:
            reasoning.append(
                f"Last eBay sale was {last_sold_days} days ago - stale market"
            )

        reasoning.append(
            f"Bulk vendor offers ${bulk_price:.2f} ({bulk_ratio:.0%} of eBay value) - "
            f"guaranteed sale vs. risky eBay listing"
        )

        return RoutingDecision(
            channel=SalesChannel.BULK_VENDOR,
            confidence=0.8,
            reasoning=reasoning,
            expected_profit=bulk_price,
            expected_days_to_sale=7
        )

    # ========================================================================
    # RULE 4: Lot Building (placeholder - implemented by lot optimizer)
    # ========================================================================
    # NOTE: This is determined by the lot optimization engine, which evaluates
    # whether books have more value as part of a series/author/theme lot.
    # The lot optimizer will override individual routing decisions when appropriate.

    # ========================================================================
    # RULE 5: Default → eBay Individual (medium confidence scenario)
    # ========================================================================
    reasoning.append(
        f"Medium value (${ebay_value:.2f}) with moderate confidence ({probability:.0%})"
    )
    reasoning.append("Worth listing on eBay - no strong indicators against it")

    if bulk_price > 0:
        reasoning.append(
            f"Bulk vendor offers ${bulk_price:.2f} but eBay has higher potential"
        )

    expected_profit = ebay_value * 0.85  # After eBay fees

    return RoutingDecision(
        channel=SalesChannel.EBAY_INDIVIDUAL,
        confidence=0.6,
        reasoning=reasoning,
        expected_profit=expected_profit,
        expected_days_to_sale=45
    )


def _parse_last_sold_days(book: BookEvaluation) -> Optional[int]:
    """
    Calculate days since last eBay sale from market data.

    Returns:
        Number of days since last sale, or None if no sold data available
    """
    if not book.market or not book.market.sold_comps_last_sold_date:
        return None

    try:
        # Parse ISO 8601 date string (e.g., "2024-01-15")
        last_sold_date = datetime.fromisoformat(
            book.market.sold_comps_last_sold_date.split("T")[0]
        )
        days_ago = (datetime.now() - last_sold_date).days
        return days_ago
    except (ValueError, AttributeError):
        return None


# ============================================================================
# BATCH ROUTING UTILITIES
# ============================================================================

def route_books(books: list[BookEvaluation]) -> dict[str, RoutingDecision]:
    """
    Route multiple books and return a mapping of ISBN -> RoutingDecision.

    This can be extended to consider cross-book optimization opportunities
    (e.g., identifying lot building candidates).

    Args:
        books: List of BookEvaluation objects

    Returns:
        Dict mapping ISBN to RoutingDecision
    """
    return {book.isbn: route_book(book) for book in books}


def summarize_routing_decisions(
    decisions: dict[str, RoutingDecision]
) -> dict[str, int]:
    """
    Summarize routing decisions by channel.

    Returns:
        Dict with channel counts, e.g., {"ebay_individual": 10, "bulk_vendor": 5}
    """
    summary = {}
    for decision in decisions.values():
        channel_name = decision.channel.value
        summary[channel_name] = summary.get(channel_name, 0) + 1
    return summary
