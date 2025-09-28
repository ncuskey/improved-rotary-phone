from __future__ import annotations

from typing import Dict, List, Optional


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def rel_spread(vals: List[float]) -> float:
    xs = [v for v in vals if isinstance(v, (int, float)) and v > 0]
    if len(xs) < 2:
        return 0.0
    lo, hi = min(xs), max(xs)
    midpoint = (hi + lo) / 2.0 if (hi + lo) else 1.0
    if midpoint == 0:
        return 0.0
    return (hi - lo) / midpoint


def estimate_shipping_lbs(books: List[Dict]) -> float:
    weight = 0.0
    for book in books:
        pages = book.get("page_count") or 250
        fmt = (book.get("format") or "pb").lower()
        if "hard" in fmt:
            weight += 1.0
        elif pages >= 350:
            weight += 0.5
        else:
            weight += 0.35
    return weight


def score_lot(
    snapshot: Dict,
    books: List[Dict],
    is_single_series: bool,
    series_have: Optional[int],
    series_expected: Optional[int],
) -> Dict:
    active_price = snapshot.get("active_median")
    sold_price = snapshot.get("sold_median")
    price_baseline = next((p for p in (sold_price, active_price) if p), None)
    active_count = snapshot.get("active_count", 0) or 0
    sold_count = snapshot.get("sold_count", 0) or 0
    total_books = len(books)

    sell_through = sold_count / max(1, sold_count + active_count)
    cohesion = 1.0 if is_single_series else 0.7
    completeness = 0.0
    if series_expected:
        completeness = (series_have or 0) / max(1, series_expected)
    size_bonus = 1.0 if 3 <= total_books <= 8 else 0.8 if total_books in (2, 9, 10, 11, 12) else 0.6 if total_books > 12 else 0.5
    shipping_penalty = clamp((estimate_shipping_lbs(books) * 0.75) / max(10.0, price_baseline or 10.0), 0.0, 0.5)
    consistency = 1 - rel_spread([v for v in (active_price, sold_price) if v])

    score = (
        0.35 * sell_through
        + 0.25 * cohesion
        + 0.15 * completeness
        + 0.10 * size_bonus
        + 0.10 * consistency
        - 0.20 * shipping_penalty
    )

    label = "High" if score >= 0.70 else "Medium" if score >= 0.45 else "Low"

    reasons = [
        f"Sell-through proxy {round(sell_through * 100)}% ({sold_count} sold vs {active_count} active)",
        ("Series lot" if is_single_series else "Author lot") + f", completeness {int(completeness * 100)}%",
        f"Size {total_books} (bonus {size_bonus})",
        f"Price consistency {round(consistency, 2)}; shipping penalty {round(shipping_penalty, 2)}",
        f"Price baseline ${price_baseline:.2f}" if price_baseline else "No price baseline",
    ]

    return {
        "score": round(score, 2),
        "label": label,
        "reasons": reasons,
        "price_baseline": price_baseline,
        "active_median": active_price,
        "sold_median": sold_price,
        "sell_through": round(sell_through, 3),
    }
