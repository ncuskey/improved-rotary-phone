from __future__ import annotations

import math
import re
import statistics
from typing import Any, Dict, List, Optional, Sequence, Tuple

from shared.models import BookEvaluation, BookMetadata, BookScouterResult, EbayMarketStats

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
    bookscouter: Optional[BookScouterResult] = None,
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

    # Use Amazon lowest price as additional market signal (what customers pay on Amazon)
    # This is particularly useful when eBay data is sparse or unavailable
    if bookscouter and bookscouter.amazon_lowest_price:
        # Apply condition modifier to Amazon price since it may be for different condition
        condition_weight = CONDITION_WEIGHTS.get(condition, 0.95) if condition else 0.95
        # Use 70% of Amazon price as conservative eBay sale estimate
        amazon_estimate = bookscouter.amazon_lowest_price * 0.7 * condition_weight
        base = max(base, amazon_estimate)

    base = max(base, 3.0)

    # Apply condition and format multipliers from eBay multipliers file
    # These are market-researched multipliers that apply regardless of sold comps data
    try:
        from pathlib import Path
        import json
        multipliers_path = Path.home() / "ISBN" / "isbn_lot_optimizer" / "models" / "ebay_multipliers.json"
        with open(multipliers_path, 'r') as f:
            mult_data = json.load(f)
            condition_multipliers = mult_data.get('condition_multipliers', {})
            binding_multipliers = mult_data.get('binding_multipliers', {})

        # Apply condition multiplier
        if condition and condition in condition_multipliers:
            base = base * condition_multipliers[condition]

        # Apply format/binding multiplier based on metadata.cover_type
        if metadata.cover_type and metadata.cover_type in binding_multipliers:
            base = base * binding_multipliers[metadata.cover_type]

    except Exception as e:
        # If multipliers file not available, continue without them
        pass

    return round(base, 2)


def compute_rarity(market: Optional[EbayMarketStats]) -> Optional[float]:
    if not market:
        return None
    denominator = max(1, market.active_count + market.unsold_count if market.unsold_count is not None else market.active_count)
    rarity = 1 / (denominator + 1)
    return round(rarity, 3)


def compute_time_to_sell(market: Optional[EbayMarketStats]) -> Optional[int]:
    """
    Calculate expected time to sell based on 90-day sold count.

    Formula: TTS = 90 / max(sold_count, 1)

    This estimates how many days it takes for one unit to sell based on
    historical velocity over the past 90 days. Capped between 7 days
    (very fast-moving) and 365 days (very slow/niche).

    Examples:
        - 30 sold in 90 days → TTS = 3 days (very fast)
        - 9 sold in 90 days → TTS = 10 days (fast)
        - 3 sold in 90 days → TTS = 30 days (moderate)
        - 1 sold in 90 days → TTS = 90 days (slow)
        - 0 sold in 90 days → TTS = 365 days (very slow, capped)

    Args:
        market: eBay market stats with sold_count from last 90 days

    Returns:
        Expected days to sell (7-365) or None if no market data
    """
    if not market or market.sold_count is None or market.sold_count < 0:
        return None

    # Avoid division by zero - if nothing sold, cap at maximum
    if market.sold_count == 0:
        return 365

    # Calculate raw TTS
    raw_tts = 90.0 / market.sold_count

    # Cap between 7 and 365 days
    tts = int(max(7, min(365, raw_tts)))

    return tts


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
    bookscouter: Optional[BookScouterResult] = None,
    collectible_info = None,
) -> Tuple[float, str, List[str], bool]:
    score = 0.0
    reasons: List[str] = []
    suppress_single = False
    has_ebay_data = False

    # BookScouter buyback offers (instant sale option if profitable)
    # Note: Profitability depends on purchase price being less than buyback offer
    if bookscouter and bookscouter.best_price > 0:
        # Only boost score for objectively valuable buyback offers
        # Lower offers are mentioned but don't influence the buy decision
        # since profitability depends entirely on purchase price
        if bookscouter.best_price >= 5.0:
            score += 35
            reasons.append(f"Strong buyback offer: ${bookscouter.best_price:.2f} from {bookscouter.best_vendor or 'vendor'} (profitable if purchased < ${bookscouter.best_price:.2f})")
        elif bookscouter.best_price >= 3.0:
            score += 25
            reasons.append(f"Good buyback offer: ${bookscouter.best_price:.2f} (instant sale if profitable)")
        elif bookscouter.best_price >= 1.0:
            score += 12
            reasons.append(f"Buyback available: ${bookscouter.best_price:.2f} (profit depends on purchase price)")
        else:
            # Small buyback offers: mention but don't boost score
            # These are only profitable if book is free/very cheap
            reasons.append(f"Buyback floor: ${bookscouter.best_price:.2f} from {bookscouter.best_vendor or 'vendor'} (only profitable if free/very cheap)")

        # Multiple vendor competition = higher confidence in market value
        if bookscouter.total_vendors > 1:
            vendor_count = len([o for o in bookscouter.offers if o.price > 0])
            if vendor_count >= 3:
                score += 8
                reasons.append(f"{vendor_count} vendors bidding (competitive demand)")
            elif vendor_count >= 2:
                score += 4
                reasons.append(f"{vendor_count} vendors interested")

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
        # Check if collectible - bypass bundle rule for collectibles
        if collectible_info and collectible_info.is_collectible:
            # Collectible books under $10 base can still be valuable
            from shared.collectible_detection import CollectibleDetector
            detector = CollectibleDetector()
            if detector.should_bypass_bundle_rule(collectible_info, price_baseline):
                score += 5  # Modest boost for collectible
                reasons.append(f"Collectible book ({collectible_info.collectible_type}) - not bundling despite ${price_baseline:.2f} base price")
            else:
                score -= 20
                suppress_single = True
                reasons.append("Single-item resale under $10; recommend bundling")
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


# Feature price multipliers (used as fallback when insufficient comp data)
FEATURE_MULTIPLIERS = {
    "Signed": 1.20,  # Signed books command 20% premium
    "First Edition": 1.15,  # First editions are collectible
    "First Printing": 1.10,  # First printings add value
    "Dust Jacket": 1.10,  # For hardcovers with DJ
    "Limited Edition": 1.30,  # Limited editions are rare
    "Illustrated": 1.08,  # Illustrated copies add value
}


def _extract_features_from_title(title: str) -> List[str]:
    """
    Extract special features from an eBay listing title.

    Args:
        title: eBay listing title

    Returns:
        List of detected features (e.g., ["Signed", "First Edition"])
    """
    features = []
    title_lower = title.lower()

    # Check for signed/autographed
    if "signed" in title_lower or "autograph" in title_lower:
        features.append("Signed")

    # Check for first edition
    if "first edition" in title_lower or "1st edition" in title_lower or " 1st " in title_lower:
        features.append("First Edition")

    # Check for first printing
    if "first printing" in title_lower or "1st printing" in title_lower:
        features.append("First Printing")

    # Check for dust jacket
    if "dust jacket" in title_lower or " dj" in title_lower or " d/j" in title_lower or "dustjacket" in title_lower:
        features.append("Dust Jacket")

    # Check for limited edition
    if "limited edition" in title_lower or "ltd edition" in title_lower or "ltd ed" in title_lower:
        features.append("Limited Edition")

    # Check for illustrated
    if "illustrated" in title_lower or "illust" in title_lower:
        features.append("Illustrated")

    return features


def _parse_comps_with_features(market: Optional[EbayMarketStats]) -> List[Dict[str, Any]]:
    """
    Parse eBay sold comps and extract condition, features, and price for each.

    Args:
        market: eBay market stats with raw sold data

    Returns:
        List of comp dicts with structure:
        {
            "condition": str,
            "features": [str],
            "price": float,
            "title": str,
        }
    """
    if not market or not market.raw_sold:
        return []

    def _first_or_default(val):
        return val[0] if isinstance(val, list) and val else val

    # Extract items from eBay response
    root_any = market.raw_sold.get("findCompletedItemsResponse")
    if not root_any:
        return []

    root_obj = _first_or_default(root_any)
    if not isinstance(root_obj, dict):
        return []

    search_result_any = root_obj.get("searchResult")
    if not search_result_any:
        return []

    search_obj = _first_or_default(search_result_any)
    if not isinstance(search_obj, dict):
        return []

    items_any = search_obj.get("item") or []
    items = []
    if isinstance(items_any, list):
        items = [i for i in items_any if isinstance(i, dict)]
    elif isinstance(items_any, dict):
        items = [items_any]

    comps = []

    for item in items:
        # Check if it sold
        status = _first_or_default(item.get("sellingStatus")) or {}
        state = _first_or_default(status.get("sellingState"))
        if state != "EndedWithSales":
            continue

        # Extract price
        price_info = _first_or_default(status.get("currentPrice"))
        if not price_info:
            price_info = _first_or_default(status.get("convertedCurrentPrice"))

        if not isinstance(price_info, dict):
            continue

        value = price_info.get("__value__")
        if value is None:
            continue

        try:
            price = float(value)
        except (ValueError, TypeError):
            continue

        # Extract condition
        condition = None
        condition_info = _first_or_default(item.get("condition"))
        if condition_info and isinstance(condition_info, dict):
            ebay_condition_id = _first_or_default(condition_info.get("conditionId"))
            ebay_condition_name = _first_or_default(condition_info.get("conditionDisplayName"))
            condition = _normalize_condition(
                str(ebay_condition_id) if ebay_condition_id else ebay_condition_name
            )

        if not condition:
            # Skip comps without condition info
            continue

        # Extract title and features
        title = _first_or_default(item.get("title")) or ""
        features = _extract_features_from_title(title)

        comps.append({
            "condition": condition,
            "features": features,
            "price": price,
            "title": title,
        })

    return comps


def calculate_price_variants(
    metadata: BookMetadata,
    market: Optional[EbayMarketStats],
    current_condition: str,
    current_price: float,
    bookscouter: Optional[BookScouterResult] = None,
) -> Dict[str, Any]:
    """
    Calculate price variants for different conditions and special features by analyzing
    actual sold comps.

    This shows users how their book's price would change with different conditions
    or special features (signed, first edition, etc.), based on real market data when
    available, falling back to estimated multipliers when data is sparse.

    Args:
        metadata: Book metadata
        market: eBay market stats with raw sold comps
        current_condition: The book's current condition
        current_price: Current estimated price
        bookscouter: BookScouter data for additional market signals

    Returns:
        Dict with structure:
        {
            "base_price": float,  # Normalized base price
            "current_condition": str,
            "current_price": float,
            "condition_variants": [
                {
                    "condition": str,
                    "price": float,
                    "price_difference": float,  # vs current
                    "percentage_change": float,  # vs current
                    "sample_size": int,  # Number of comps found
                    "data_source": "comps" | "estimated"
                },
                ...
            ],
            "feature_variants": [
                {
                    "features": [str],  # e.g., ["Signed", "First Edition"]
                    "description": str,  # Human-readable
                    "price": float,
                    "price_difference": float,  # vs current
                    "percentage_change": float,  # vs current
                    "sample_size": int,  # Number of comps found
                    "data_source": "comps" | "estimated"
                },
                ...
            ]
        }
    """
    # Parse all comps with their features and conditions
    comps = _parse_comps_with_features(market)

    # Group comps by condition
    condition_groups: Dict[str, List[float]] = {}
    for comp in comps:
        # Only include comps without special features for condition baseline
        if len(comp["features"]) == 0:
            condition = comp["condition"]
            if condition not in condition_groups:
                condition_groups[condition] = []
            condition_groups[condition].append(comp["price"])

    # Group comps by feature combinations (for current condition only)
    feature_groups: Dict[str, List[float]] = {}
    for comp in comps:
        if comp["condition"] == current_condition and len(comp["features"]) > 0:
            # Sort features for consistent keys
            feature_key = ", ".join(sorted(comp["features"]))
            if feature_key not in feature_groups:
                feature_groups[feature_key] = []
            feature_groups[feature_key].append(comp["price"])

    # Calculate base price from current condition
    current_weight = CONDITION_WEIGHTS.get(current_condition, 0.95)
    base_price = current_price / current_weight

    # Generate condition variants
    condition_variants = []
    for condition, weight in CONDITION_WEIGHTS.items():
        if condition in condition_groups and len(condition_groups[condition]) >= 2:
            # Use real market data
            prices = condition_groups[condition]
            variant_price = round(statistics.median(prices), 2)
            data_source = "comps"
            sample_size = len(prices)
        else:
            # Fall back to estimated price
            variant_price = round(base_price * weight, 2)
            data_source = "estimated"
            sample_size = len(condition_groups.get(condition, []))

        price_diff = round(variant_price - current_price, 2)
        pct_change = round(((variant_price / current_price) - 1) * 100, 1) if current_price > 0 else 0.0

        condition_variants.append({
            "condition": condition,
            "price": variant_price,
            "price_difference": price_diff,
            "percentage_change": pct_change,
            "sample_size": sample_size,
            "data_source": data_source,
        })

    # Sort by price descending
    condition_variants.sort(key=lambda x: x["price"], reverse=True)

    # Generate feature variants
    feature_variants = []

    # Analyze each individual feature
    for feature in ["Signed", "First Edition", "First Printing", "Dust Jacket", "Limited Edition", "Illustrated"]:
        # Find comps with this feature (and possibly others)
        matching_prices = [
            comp["price"]
            for comp in comps
            if comp["condition"] == current_condition and feature in comp["features"]
        ]

        if len(matching_prices) >= 2:
            # Use real market data
            variant_price = round(statistics.median(matching_prices), 2)
            data_source = "comps"
            sample_size = len(matching_prices)
        else:
            # Fall back to multiplier-based estimate
            multiplier = FEATURE_MULTIPLIERS.get(feature, 1.0)
            variant_price = round(current_price * multiplier, 2)
            data_source = "estimated"
            sample_size = len(matching_prices)

        price_diff = round(variant_price - current_price, 2)
        pct_change = round(((variant_price / current_price) - 1) * 100, 1) if current_price > 0 else 0.0

        # Only include if it adds value (positive price difference)
        if price_diff > 0 or sample_size > 0:
            feature_variants.append({
                "features": [feature],
                "description": feature,
                "price": variant_price,
                "price_difference": price_diff,
                "percentage_change": pct_change,
                "sample_size": sample_size,
                "data_source": data_source,
            })

    # Analyze common feature combinations found in comps
    for feature_key, prices in feature_groups.items():
        if len(prices) >= 2:
            features = feature_key.split(", ")
            variant_price = round(statistics.median(prices), 2)
            price_diff = round(variant_price - current_price, 2)
            pct_change = round(((variant_price / current_price) - 1) * 100, 1) if current_price > 0 else 0.0

            # Only include valuable combinations not already covered by single features
            if len(features) >= 2 and price_diff > 0:
                feature_variants.append({
                    "features": features,
                    "description": feature_key,
                    "price": variant_price,
                    "price_difference": price_diff,
                    "percentage_change": pct_change,
                    "sample_size": len(prices),
                    "data_source": "comps",
                })

    # Add estimated combinations for valuable pairings if not found in comps
    estimated_combos = [
        (["Signed", "First Edition"], "Signed First Edition"),
        (["Signed", "Limited Edition"], "Signed Limited Edition"),
        (["First Edition", "Dust Jacket"], "First Edition with Dust Jacket"),
    ]

    for features, description in estimated_combos:
        # Check if we already have this combo from real comps
        if any(set(v["features"]) == set(features) for v in feature_variants):
            continue

        # Calculate estimated price using multipliers
        combined_multiplier = 1.0
        for feature in features:
            combined_multiplier *= FEATURE_MULTIPLIERS.get(feature, 1.0)

        variant_price = round(current_price * combined_multiplier, 2)
        price_diff = round(variant_price - current_price, 2)
        pct_change = round(((combined_multiplier - 1) * 100), 1)

        if price_diff > 0:
            feature_variants.append({
                "features": features,
                "description": description,
                "price": variant_price,
                "price_difference": price_diff,
                "percentage_change": pct_change,
                "sample_size": 0,
                "data_source": "estimated",
            })

    # Sort by price difference descending (most valuable first)
    feature_variants.sort(key=lambda x: x["price_difference"], reverse=True)

    return {
        "base_price": round(base_price, 2),
        "current_condition": current_condition,
        "current_price": current_price,
        "condition_variants": condition_variants,
        "feature_variants": feature_variants,
    }


def build_book_evaluation(
    isbn: str,
    original_isbn: str,
    metadata: BookMetadata,
    market: Optional[EbayMarketStats],
    condition: str,
    edition: Optional[str],
    amazon_rank: Optional[int] = None,
    bookscouter: Optional[BookScouterResult] = None,
    signed: bool = False,
    first_edition: bool = False,
    abebooks_data = None,
) -> BookEvaluation:
    # Detect if book is collectible
    from shared.collectible_detection import detect_collectible
    collectible_info = detect_collectible(
        metadata=metadata,
        signed=signed,
        first_edition=first_edition,
        abebooks_data=abebooks_data
    )

    # Pass condition, edition, and bookscouter to get attribute-specific price estimate
    estimated_price = estimate_price(metadata, market, condition, edition, bookscouter)

    # Apply collectible multiplier if detected
    if collectible_info.is_collectible:
        estimated_price = estimated_price * collectible_info.fame_multiplier

    rarity = compute_rarity(market)
    tts = compute_time_to_sell(market)

    score, label, reasons, suppress_single = score_probability(
        metadata=metadata,
        market=market,
        estimated_price=estimated_price,
        condition=condition,
        edition=edition,
        amazon_rank=amazon_rank,
        bookscouter=bookscouter,
        collectible_info=collectible_info,
    )

    # Add collectible info to reasons if detected
    if collectible_info.is_collectible:
        collectible_reason = f"COLLECTIBLE: {collectible_info.collectible_type}"
        if collectible_info.famous_person:
            collectible_reason += f" by {collectible_info.famous_person}"
        collectible_reason += f" (${collectible_info.fame_multiplier:.1f}x multiplier)"
        if collectible_info.notes:
            collectible_reason += f" - {collectible_info.notes}"
        reasons.insert(0, collectible_reason)  # Put at top of reasons

    # Add TTS to justification reasons with velocity context
    if tts is not None:
        if tts <= 14:
            reasons.append(f"Very fast-moving: Expected to sell in ~{tts} days")
        elif tts <= 45:
            reasons.append(f"Fast-moving: Expected to sell in ~{tts} days")
        elif tts <= 90:
            reasons.append(f"Moderate velocity: Expected to sell in ~{tts} days")
        elif tts <= 180:
            reasons.append(f"Slow-moving: May take ~{tts} days to sell")
        else:
            reasons.append(f"Very slow: May take {tts}+ days to sell (niche market)")

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
        time_to_sell_days=tts,
    )
