from __future__ import annotations

import math
import re
import statistics
from typing import Any, Dict, List, Optional, Sequence, Tuple

from shared.models import BookEvaluation, BookMetadata, EbayMarketStats

HIGH_DEMAND_KEYWORDS = (
    "business",
    "finance",
    "medical",
    "nursing",
    "law",
    "science",
    "technology",
    "computer",
    "engineering",
    "mathematics",
    "physics",
    "chemistry",
    "exam",
    "textbook",
)

CONDITION_WEIGHTS = {
    "New": 1.25,
    "Like New": 1.15,
    "Very Good": 1.05,
    "Good": 0.95,
    "Acceptable": 0.8,
    "Poor": 0.6,
}

# Mapping eBay condition IDs/names to our standardized conditions
EBAY_CONDITION_MAP = {
    "1000": "New",  # Brand New
    "1500": "New",  # New other (see details)
    "2000": "New",  # Manufacturer refurbished
    "2500": "Like New",  # Seller refurbished
    "3000": "Like New",  # Used - Like New
    "4000": "Very Good",  # Used - Very Good
    "5000": "Good",  # Used - Good
    "6000": "Acceptable",  # Used - Acceptable
    "7000": "Poor",  # For parts or not working
}


def _normalize_condition(ebay_condition: str) -> Optional[str]:
    """
    Normalize an eBay condition string to our standard conditions.

    Args:
        ebay_condition: eBay condition ID or name

    Returns:
        Standardized condition string or None
    """
    if not ebay_condition:
        return None

    # Check if it's a condition ID
    condition_normalized = EBAY_CONDITION_MAP.get(str(ebay_condition))
    if condition_normalized:
        return condition_normalized

    # Try matching by text
    lower = ebay_condition.lower()
    if "new" in lower and "like" not in lower:
        return "New"
    elif "like new" in lower:
        return "Like New"
    elif "very good" in lower:
        return "Very Good"
    elif "good" in lower:
        return "Good"
    elif "acceptable" in lower:
        return "Acceptable"
    elif "poor" in lower or "parts" in lower:
        return "Poor"

    return None


def _extract_sold_comps_by_condition(
    market: Optional[EbayMarketStats],
    target_condition: str,
    edition: Optional[str] = None,
) -> Tuple[List[float], int]:
    """
    Extract sold comp prices that match the target condition (and optionally edition).

    Args:
        market: eBay market stats containing raw sold data
        target_condition: The condition to filter for (e.g., "Like New")
        edition: Optional edition string to check for (e.g., "First Edition")

    Returns:
        Tuple of (list of matching prices, total comps examined)
    """
    if not market or not market.raw_sold:
        return [], 0

    def _first_or_default(val):
        return val[0] if isinstance(val, list) and val else val

    # Extract items from eBay response
    root_any = market.raw_sold.get("findCompletedItemsResponse")
    if not root_any:
        return [], 0

    root_obj = _first_or_default(root_any)
    if not isinstance(root_obj, dict):
        return [], 0

    search_result_any = root_obj.get("searchResult")
    if not search_result_any:
        return [], 0

    search_obj = _first_or_default(search_result_any)
    if not isinstance(search_obj, dict):
        return [], 0

    items_any = search_obj.get("item") or []
    items = []
    if isinstance(items_any, list):
        items = [i for i in items_any if isinstance(i, dict)]
    elif isinstance(items_any, dict):
        items = [items_any]

    matching_prices = []
    total_examined = 0

    for item in items:
        # Check if it sold
        status = _first_or_default(item.get("sellingStatus")) or {}
        state = _first_or_default(status.get("sellingState"))
        if state != "EndedWithSales":
            continue

        total_examined += 1

        # Extract condition
        condition_info = _first_or_default(item.get("condition"))
        if condition_info and isinstance(condition_info, dict):
            ebay_condition_id = _first_or_default(condition_info.get("conditionId"))
            ebay_condition_name = _first_or_default(condition_info.get("conditionDisplayName"))

            item_condition = _normalize_condition(str(ebay_condition_id) if ebay_condition_id else ebay_condition_name)

            # Check if condition matches
            if item_condition != target_condition:
                continue
        else:
            # No condition info, skip
            continue

        # If edition is specified, check title for edition keywords
        if edition:
            title = _first_or_default(item.get("title")) or ""
            edition_lower = edition.lower()
            title_lower = title.lower()

            # Check for first edition
            if "first" in edition_lower or "1st" in edition_lower:
                if not ("first" in title_lower or "1st" in title_lower):
                    continue

            # Check for signed
            if "signed" in edition_lower:
                if "signed" not in title_lower and "autograph" not in title_lower:
                    continue

        # Extract price
        price_info = _first_or_default(status.get("currentPrice"))
        if not price_info:
            price_info = _first_or_default(status.get("convertedCurrentPrice"))

        if isinstance(price_info, dict):
            value = price_info.get("__value__")
            if value is not None:
                try:
                    price = float(value)
                    matching_prices.append(price)
                except (ValueError, TypeError):
                    pass

    return matching_prices, total_examined


def estimate_price(
    metadata: BookMetadata,
    market: Optional[EbayMarketStats],
    condition: Optional[str] = None,
    edition: Optional[str] = None,
) -> float:
    base = 4.0
    if metadata.page_count:
        base += min(metadata.page_count * 0.02, 6.0)
    if metadata.published_year:
        if metadata.published_year >= 2019:
            base += 3.0
        elif metadata.published_year >= 2010:
            base += 1.75
        elif metadata.published_year <= 1985:
            base += 1.2
    if metadata.average_rating:
        base += metadata.average_rating * 0.6
    if metadata.ratings_count and metadata.ratings_count > 50:
        base += min(math.log(metadata.ratings_count, 5), 2.0)

    categories_lower = [cat.lower() for cat in metadata.categories]
    if categories_lower:
        if any(any(keyword in cat for keyword in HIGH_DEMAND_KEYWORDS) for cat in categories_lower):
            base += 3.0
        base += min(len(categories_lower) * 0.25, 2.0)

    if metadata.list_price:
        multiplier = 0.5 if metadata.currency == "USD" or metadata.currency is None else 0.4
        base = max(base, metadata.list_price * multiplier)

    # If condition is provided, try to get condition-specific comps
    if market and condition:
        matching_prices, total_examined = _extract_sold_comps_by_condition(market, condition, edition)

        if matching_prices:
            # Use condition-specific comps for price estimate
            condition_median = statistics.median(matching_prices)
            condition_avg = statistics.mean(matching_prices)

            # Apply condition weight to the baseline
            weight = CONDITION_WEIGHTS.get(condition, 0.95)

            # Use weighted average of median and mean, adjusted by condition
            condition_estimate = (condition_median * 0.6 + condition_avg * 0.4) * weight

            # Prioritize condition-specific estimate
            base = max(base, condition_estimate)
        elif total_examined > 0:
            # We found comps but none matched - apply condition weight to general average
            if market.sold_avg_price:
                weight = CONDITION_WEIGHTS.get(condition, 0.95)
                base = max(base, market.sold_avg_price * weight)

    # Fall back to general market data if no condition specified
    if market and not condition:
        if market.sold_avg_price:
            base = max(base, market.sold_avg_price * 0.9)
        elif market.active_avg_price:
            base = max(base, market.active_avg_price * 0.8)

    base = max(base, 3.0)
    return round(base, 2)


def compute_rarity(market: Optional[EbayMarketStats]) -> Optional[float]:
    if not market:
        return None
    denominator = max(1, market.active_count + market.unsold_count if market.unsold_count is not None else market.active_count)
    rarity = 1 / (denominator + 1)
    return round(rarity, 3)


def _calculate_fallback_score(
    amazon_rank: int,
    metadata: BookMetadata,
    reasons: List[str],
) -> float:
    """
    Fallback probability calculation when eBay sell-through data is unavailable.

    Relies more heavily on Amazon Sales Rank as demand indicator, combined with
    book metadata signals (ratings, recency, categories).

    Args:
        amazon_rank: Amazon Sales Rank (lower = more popular)
        metadata: Book metadata
        reasons: List to append reasoning strings to

    Returns:
        Fallback probability score (0-100 scale)
    """
    score = 0.0

    # Amazon rank as primary signal (boosted weights vs. normal scoring)
    if amazon_rank < 50_000:
        score += 50  # Bestseller - very high confidence
        reasons.append("Bestseller status provides high confidence even without eBay data")
    elif amazon_rank < 100_000:
        score += 40  # High demand
        reasons.append("Strong Amazon demand compensates for missing eBay data")
    elif amazon_rank < 300_000:
        score += 28  # Solid demand
        reasons.append("Solid Amazon sales indicate good market")
    elif amazon_rank < 500_000:
        score += 16  # Moderate
        reasons.append("Moderate Amazon velocity suggests fair demand")
    elif amazon_rank < 1_000_000:
        score += 8  # Average
    elif amazon_rank < 2_000_000:
        score -= 5  # Slow
        reasons.append("Slow Amazon velocity suggests limited demand")
    else:
        score -= 15  # Very niche
        reasons.append("Very slow Amazon rank indicates niche market")

    # Book recency boost (recent books with Amazon rank = likely still in demand)
    if metadata.published_year:
        if metadata.published_year >= 2022:
            score += 10
            reasons.append("Recent publication year strengthens confidence")
        elif metadata.published_year >= 2018:
            score += 5
        elif metadata.published_year <= 1990:
            score -= 3
            reasons.append("Older title may have limited demand")

    # Reader engagement as demand proxy
    if metadata.ratings_count:
        if metadata.ratings_count >= 5000:
            score += 8
            reasons.append(f"High reader engagement ({metadata.ratings_count:,} ratings)")
        elif metadata.ratings_count >= 1000:
            score += 5
        elif metadata.ratings_count >= 100:
            score += 2

    # Quality signal
    if metadata.average_rating:
        if metadata.average_rating >= 4.5:
            score += 5
            reasons.append("Excellent reader ratings suggest quality")
        elif metadata.average_rating >= 4.0:
            score += 3
        elif metadata.average_rating < 3.0:
            score -= 5

    # High-demand categories
    categories_lower = [cat.lower() for cat in metadata.categories]
    if any(any(keyword in cat for keyword in HIGH_DEMAND_KEYWORDS) for cat in categories_lower):
        score += 8
        reasons.append("High-demand category (textbook/professional)")

    return score


def score_probability(
    metadata: BookMetadata,
    market: Optional[EbayMarketStats],
    estimated_price: float,
    condition: str,
    edition: Optional[str],
    amazon_rank: Optional[int] = None,
) -> Tuple[float, str, List[str], bool]:
    score = 0.0
    reasons: List[str] = []
    suppress_single = False
    has_ebay_data = False

    # Check if we have eBay sell-through data
    sell_through = market.sell_through_rate if market else None
    if sell_through is not None:
        has_ebay_data = True
        if sell_through >= 0.65:
            score += 40
            reasons.append(f"Strong sell-through rate at {sell_through:.0%} on eBay")
        elif sell_through >= 0.45:
            score += 28
            reasons.append(f"Moderate sell-through rate at {sell_through:.0%}")
        elif sell_through >= 0.25:
            score += 12
            reasons.append(f"Some market activity ({sell_through:.0%} sell-through)")
        else:
            score -= 8
            reasons.append(f"Weak historical sell-through ({sell_through:.0%})")

    # Amazon Sales Rank scoring (velocity/demand indicator)
    if amazon_rank is not None:
        if amazon_rank < 50_000:
            score += 15
            reasons.append(f"Amazon bestseller territory (rank {amazon_rank:,})")
        elif amazon_rank < 100_000:
            score += 10
            reasons.append(f"High Amazon demand (rank {amazon_rank:,})")
        elif amazon_rank < 300_000:
            score += 5
            reasons.append(f"Solid Amazon demand (rank {amazon_rank:,})")
        elif amazon_rank < 500_000:
            score += 2
            reasons.append(f"Moderate Amazon demand (rank {amazon_rank:,})")
        elif amazon_rank < 1_000_000:
            # Neutral - no points added or subtracted
            reasons.append(f"Average Amazon velocity (rank {amazon_rank:,})")
        elif amazon_rank < 2_000_000:
            score -= 5
            reasons.append(f"Slow Amazon velocity (rank {amazon_rank:,})")
        else:
            score -= 10
            reasons.append(f"Very niche/stale on Amazon (rank {amazon_rank:,})")

    # If no eBay data, use fallback scoring with heavier Amazon weight
    if not has_ebay_data:
        if amazon_rank is not None:
            # Use Amazon rank as primary signal with boosted weight
            reasons.append("Using Amazon-based confidence (no eBay sell-through data)")
            score = _calculate_fallback_score(amazon_rank, metadata, reasons)
        else:
            # No market data at all - very conservative
            score -= 5
            reasons.append("No completed sales found; limited market data")

    price_anchor = market.sold_avg_price or market.sold_median_price if market else None
    price_baseline = price_anchor or estimated_price
    if price_baseline >= 30:
        score += 24
        reasons.append(f"Average sale price around ${price_baseline:.2f}")
    elif price_baseline >= 20:
        score += 16
        reasons.append(f"Sale price trending near ${price_baseline:.2f}")
    elif price_baseline >= 10:
        score += 8
        reasons.append(f"Sale price above minimum threshold (${price_baseline:.2f})")
    else:
        score -= 20
        suppress_single = True
        reasons.append("Single-item resale under $10; recommend bundling")

    condition = condition or "Good"
    weight = CONDITION_WEIGHTS.get(condition, 0.9)
    condition_modifier = (weight - 1) * 20
    score += condition_modifier
    reasons.append(f"Condition set to {condition} (modifier {condition_modifier:+.1f})")

    if edition:
        edition_lower = edition.lower()
        if "first" in edition_lower or "1st" in edition_lower:
            score += 6
            reasons.append("First edition noted")
        elif "signed" in edition_lower or "limited" in edition_lower:
            score += 10
            reasons.append("Signed/limited edition boosts demand")

    if market and market.active_count is not None:
        if market.active_count <= 3:
            score += 8
            reasons.append("Few active listings; inventory looks tight")
        elif market.active_count >= 20:
            score -= 6
            reasons.append("Many active listings; competition is high")

    categories_lower = [cat.lower() for cat in metadata.categories]
    if categories_lower and any("set" in cat or "series" in cat for cat in categories_lower):
        score += 5
        reasons.append("Series-related title; grouping may improve appeal")

    if metadata.authors:
        reasons.append(f"Author focus: {', '.join(metadata.authors[:2])}")

    if metadata.average_rating and metadata.ratings_count:
        reasons.append(f"Reader rating {metadata.average_rating:.1f} ({metadata.ratings_count} reviews)")
        # Demand signal: strong reader ratings boost
        try:
            if float(metadata.average_rating) >= 4.2 and int(metadata.ratings_count) >= 1000:
                score += 4  # small positive bump
                reasons.append("High reader rating")
        except Exception:
            pass

    # Cap score at 100 to prevent exceeding 100% confidence
    score = min(score, 100.0)
    probability_label = classify_probability(score)
    return score, probability_label, reasons, suppress_single


def classify_probability(score: float) -> str:
    if score >= 70:
        return "High"
    if score >= 45:
        return "Medium"
    return "Low"


def build_book_evaluation(
    isbn: str,
    original_isbn: str,
    metadata: BookMetadata,
    market: Optional[EbayMarketStats],
    condition: str,
    edition: Optional[str],
    amazon_rank: Optional[int] = None,
) -> BookEvaluation:
    # Pass condition and edition to get attribute-specific price estimate
    estimated_price = estimate_price(metadata, market, condition, edition)
    rarity = compute_rarity(market)
    score, label, reasons, suppress_single = score_probability(
        metadata=metadata,
        market=market,
        estimated_price=estimated_price,
        condition=condition,
        edition=edition,
        amazon_rank=amazon_rank,
    )
    return BookEvaluation(
        isbn=isbn,
        original_isbn=original_isbn,
        metadata=metadata,
        market=market,
        estimated_price=estimated_price,
        condition=condition,
        edition=edition,
        rarity=rarity,
        probability_score=round(score, 1),
        probability_label=label,
        justification=reasons,
        suppress_single=suppress_single,
    )
