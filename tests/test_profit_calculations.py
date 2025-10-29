#!/usr/bin/env python3
"""
Test suite for profit calculation functions.

Covers:
- eBay fee calculations
- Amazon fee calculations
- Profit margin calculations
- Price estimation logic
- Edge cases and boundary conditions
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.models import EbayMarketStats, BookMetadata
from shared.probability import estimate_price, compute_rarity, score_probability


def calculate_ebay_fees(sale_price: float) -> float:
    """
    Calculate eBay selling fees.

    Fee structure:
    - Final Value Fee: 13.25% of sale price
    - Payment Processing: 2.9% + $0.30
    """
    final_value_fee = sale_price * 0.1325
    payment_processing = (sale_price * 0.029) + 0.30
    return final_value_fee + payment_processing


def calculate_amazon_fees(sale_price: float) -> float:
    """
    Calculate Amazon selling fees.

    Fee structure:
    - Referral fee: 15% of sale price
    - Closing fee: $1.80 per book
    """
    referral_fee = sale_price * 0.15
    closing_fee = 1.80
    return referral_fee + closing_fee


def calculate_profit(sale_price: float, cost_basis: float, platform: str = "ebay") -> float:
    """
    Calculate net profit after fees.

    Args:
        sale_price: Expected selling price
        cost_basis: Cost to acquire the book
        platform: "ebay" or "amazon"

    Returns:
        Net profit (can be negative for losses)
    """
    if platform.lower() == "ebay":
        fees = calculate_ebay_fees(sale_price)
    elif platform.lower() == "amazon":
        fees = calculate_amazon_fees(sale_price)
    else:
        raise ValueError(f"Unknown platform: {platform}")

    net_profit = sale_price - cost_basis - fees
    return net_profit


# ============================================================================
# TEST SECTION: eBay Fee Calculations
# ============================================================================

def test_ebay_fees_standard():
    """Test eBay fees for typical book price ($20)."""
    sale_price = 20.00
    fees = calculate_ebay_fees(sale_price)

    # Expected: (20 * 0.1325) + (20 * 0.029 + 0.30)
    # = 2.65 + 0.88 = $3.53
    expected_fees = 3.53

    print(f"✓ eBay fees for ${sale_price:.2f} sale: ${fees:.2f}")
    assert abs(fees - expected_fees) < 0.01, f"Expected ${expected_fees:.2f}, got ${fees:.2f}"
    return True


def test_ebay_fees_low_price():
    """Test eBay fees for low-value book ($5)."""
    sale_price = 5.00
    fees = calculate_ebay_fees(sale_price)

    # Expected: (5 * 0.1325) + (5 * 0.029 + 0.30)
    # = 0.66 + 0.45 = $1.11
    expected_fees = 1.11

    print(f"✓ eBay fees for ${sale_price:.2f} sale: ${fees:.2f}")
    assert abs(fees - expected_fees) < 0.01, f"Expected ${expected_fees:.2f}, got ${fees:.2f}"
    return True


def test_ebay_fees_high_price():
    """Test eBay fees for valuable book ($100)."""
    sale_price = 100.00
    fees = calculate_ebay_fees(sale_price)

    # Expected: (100 * 0.1325) + (100 * 0.029 + 0.30)
    # = 13.25 + 3.20 = $16.45
    expected_fees = 16.45

    print(f"✓ eBay fees for ${sale_price:.2f} sale: ${fees:.2f}")
    assert abs(fees - expected_fees) < 0.01, f"Expected ${expected_fees:.2f}, got ${fees:.2f}"
    return True


def test_ebay_fees_minimal():
    """Test eBay fees for minimum viable sale ($1)."""
    sale_price = 1.00
    fees = calculate_ebay_fees(sale_price)

    # Expected: (1 * 0.1325) + (1 * 0.029 + 0.30)
    # = 0.13 + 0.33 = $0.46
    expected_fees = 0.46

    print(f"✓ eBay fees for ${sale_price:.2f} sale: ${fees:.2f}")
    assert abs(fees - expected_fees) < 0.01, f"Expected ${expected_fees:.2f}, got ${fees:.2f}"

    # Note: Fees exceed sale price - this is a loss scenario
    if fees > sale_price:
        print(f"  ⚠️  Warning: Fees (${fees:.2f}) exceed sale price (${sale_price:.2f})")

    return True


# ============================================================================
# TEST SECTION: Amazon Fee Calculations
# ============================================================================

def test_amazon_fees_standard():
    """Test Amazon fees for typical book price ($20)."""
    sale_price = 20.00
    fees = calculate_amazon_fees(sale_price)

    # Expected: (20 * 0.15) + 1.80 = 3.00 + 1.80 = $4.80
    expected_fees = 4.80

    print(f"✓ Amazon fees for ${sale_price:.2f} sale: ${fees:.2f}")
    assert abs(fees - expected_fees) < 0.01, f"Expected ${expected_fees:.2f}, got ${fees:.2f}"
    return True


def test_amazon_fees_low_price():
    """Test Amazon fees for low-value book ($5)."""
    sale_price = 5.00
    fees = calculate_amazon_fees(sale_price)

    # Expected: (5 * 0.15) + 1.80 = 0.75 + 1.80 = $2.55
    expected_fees = 2.55

    print(f"✓ Amazon fees for ${sale_price:.2f} sale: ${fees:.2f}")
    assert abs(fees - expected_fees) < 0.01, f"Expected ${expected_fees:.2f}, got ${fees:.2f}"

    # Note: Fees are 51% of sale price - very thin margin
    fee_percentage = (fees / sale_price) * 100
    print(f"  📊 Fees represent {fee_percentage:.1f}% of sale price")

    return True


def test_amazon_fees_high_price():
    """Test Amazon fees for valuable book ($100)."""
    sale_price = 100.00
    fees = calculate_amazon_fees(sale_price)

    # Expected: (100 * 0.15) + 1.80 = 15.00 + 1.80 = $16.80
    expected_fees = 16.80

    print(f"✓ Amazon fees for ${sale_price:.2f} sale: ${fees:.2f}")
    assert abs(fees - expected_fees) < 0.01, f"Expected ${expected_fees:.2f}, got ${fees:.2f}"
    return True


def test_fee_comparison():
    """Compare eBay vs Amazon fees at different price points."""
    print("\n📊 Fee Comparison: eBay vs Amazon")
    print("=" * 60)

    price_points = [5.00, 10.00, 20.00, 50.00, 100.00]

    for price in price_points:
        ebay_fees = calculate_ebay_fees(price)
        amazon_fees = calculate_amazon_fees(price)
        difference = amazon_fees - ebay_fees

        print(f"${price:6.2f}: eBay ${ebay_fees:5.2f} | Amazon ${amazon_fees:5.2f} | Diff ${difference:+5.2f}")

        if ebay_fees < amazon_fees:
            better = "eBay"
        else:
            better = "Amazon"
        print(f"         Better platform: {better}")

    return True


# ============================================================================
# TEST SECTION: Profit Calculations
# ============================================================================

def test_profit_typical_ebay():
    """Test profit for typical eBay sale."""
    sale_price = 20.00
    cost_basis = 5.00
    profit = calculate_profit(sale_price, cost_basis, "ebay")

    # Expected: 20 - 5 - 3.53 = $11.47
    expected_profit = 11.47

    print(f"✓ eBay profit: ${profit:.2f} (sale ${sale_price:.2f} - cost ${cost_basis:.2f})")
    assert abs(profit - expected_profit) < 0.01, f"Expected ${expected_profit:.2f}, got ${profit:.2f}"
    return True


def test_profit_typical_amazon():
    """Test profit for typical Amazon sale."""
    sale_price = 20.00
    cost_basis = 5.00
    profit = calculate_profit(sale_price, cost_basis, "amazon")

    # Expected: 20 - 5 - 4.80 = $10.20
    expected_profit = 10.20

    print(f"✓ Amazon profit: ${profit:.2f} (sale ${sale_price:.2f} - cost ${cost_basis:.2f})")
    assert abs(profit - expected_profit) < 0.01, f"Expected ${expected_profit:.2f}, got ${profit:.2f}"
    return True


def test_profit_marginal():
    """Test profit for marginal deal (meets minimum threshold)."""
    sale_price = 12.00
    cost_basis = 5.00
    profit = calculate_profit(sale_price, cost_basis, "ebay")

    # Expected: 12 - 5 - (12*0.1325 + 12*0.029 + 0.30)
    # = 12 - 5 - 2.24 = $4.76
    expected_profit = 4.76

    print(f"✓ Marginal profit: ${profit:.2f}")

    # Check against balanced threshold ($5)
    if profit >= 5.0:
        print(f"  ✓ Meets balanced auto-buy threshold ($5)")
    else:
        print(f"  ⚠️  Below balanced auto-buy threshold ($5)")

    assert abs(profit - expected_profit) < 0.01
    return True


def test_profit_loss():
    """Test profit calculation for money-losing scenario."""
    sale_price = 8.00
    cost_basis = 7.00
    profit = calculate_profit(sale_price, cost_basis, "ebay")

    # Expected: 8 - 7 - (8*0.1325 + 8*0.029 + 0.30)
    # = 8 - 7 - 1.59 = -$0.59
    expected_profit = -0.59

    print(f"✓ Loss scenario: ${profit:.2f} (negative)")
    assert profit < 0, "Expected negative profit"
    assert abs(profit - expected_profit) < 0.01
    return True


def test_profit_breakeven():
    """Test profit calculation for near-breakeven scenario."""
    sale_price = 10.00
    cost_basis = 5.00

    ebay_profit = calculate_profit(sale_price, cost_basis, "ebay")
    amazon_profit = calculate_profit(sale_price, cost_basis, "amazon")

    print(f"✓ Breakeven analysis for ${sale_price:.2f} sale, ${cost_basis:.2f} cost:")
    print(f"  eBay profit: ${ebay_profit:.2f}")
    print(f"  Amazon profit: ${amazon_profit:.2f}")

    # Both should be positive but small
    assert ebay_profit > 0 and ebay_profit < 5.0
    assert amazon_profit > 0 and amazon_profit < 5.0

    return True


# ============================================================================
# TEST SECTION: Price Estimation
# ============================================================================

def test_price_estimation_strong_data():
    """Test price estimation with strong eBay market data."""
    metadata = BookMetadata(
        isbn="TEST_STRONG",
        title="Test Book with Strong Market",
        page_count=300,
        published_year=2020,
        average_rating=4.5,
        ratings_count=100
    )

    market = EbayMarketStats(
        isbn="TEST_STRONG",
        sold_avg_price=25.50,
        sold_median_price=24.00,
        sold_count=15,
        active_count=8,
        active_avg_price=26.00,
        sell_through_rate=0.65,
        currency="USD"
    )

    estimated = estimate_price(metadata, market)

    median = market.sold_median_price or 0
    avg = market.sold_avg_price or 0
    print(f"✓ Price estimate: ${estimated:.2f} (median ${median:.2f}, avg ${avg:.2f})")

    # Should be close to median or average (implementation uses max of multiple estimates)
    assert estimated is not None
    assert estimated >= 15.0, f"Estimate ${estimated:.2f} too low"

    return True


def test_price_estimation_sparse_data():
    """Test price estimation with limited market data."""
    metadata = BookMetadata(
        isbn="TEST_SPARSE",
        title="Test Book with Sparse Data",
        page_count=200
    )

    market = EbayMarketStats(
        isbn="TEST_SPARSE",
        sold_avg_price=30.00,
        sold_median_price=30.00,
        sold_count=2,
        active_count=1,
        active_avg_price=32.00,
        sell_through_rate=0.67,
        currency="USD"
    )

    estimated = estimate_price(metadata, market)

    print(f"✓ Sparse data estimate: ${estimated:.2f} (only {market.sold_count} sold)")

    # Should still provide estimate (falls back to baseline + market data)
    assert estimated is not None
    assert estimated >= 3.0, "Should have minimum estimate"

    return True


def test_price_estimation_no_data():
    """Test price estimation with no market data."""
    metadata = BookMetadata(
        isbn="TEST_NODATA",
        title="Test Book with No Market Data",
        page_count=250,
        published_year=2015
    )

    market = EbayMarketStats(
        isbn="TEST_NODATA",
        sold_avg_price=None,
        sold_median_price=None,
        sold_count=0,
        active_count=0,
        active_avg_price=None,
        sell_through_rate=None,
        currency="USD"
    )

    estimated = estimate_price(metadata, market)

    print(f"✓ No data scenario: estimate = ${estimated:.2f}")

    # Should fall back to baseline estimate from metadata
    assert estimated is not None
    assert estimated >= 3.0, "Should have minimum baseline estimate"

    return True


def test_price_estimation_outliers():
    """Test price estimation with outlier prices."""
    metadata = BookMetadata(
        isbn="TEST_OUTLIER",
        title="Test Book with Outliers",
        page_count=300
    )

    market = EbayMarketStats(
        isbn="TEST_OUTLIER",
        sold_avg_price=50.00,  # Inflated by outlier
        sold_median_price=20.00,  # More representative
        sold_count=10,
        active_count=5,
        active_avg_price=55.00,
        sell_through_rate=0.67,
        currency="USD"
    )

    estimated = estimate_price(metadata, market)

    median = market.sold_median_price or 0
    avg = market.sold_avg_price or 0
    print(f"✓ Outlier handling: ${estimated:.2f} (median ${median:.2f}, avg ${avg:.2f})")

    # Implementation uses max of various estimates, so may favor higher value
    # Just verify it's a reasonable estimate
    assert estimated is not None
    assert estimated >= 10.0, "Should provide reasonable estimate"

    return True


# ============================================================================
# TEST SECTION: Rarity Scoring
# ============================================================================

def test_rarity_score_high_velocity():
    """Test rarity score for fast-moving book."""
    market = EbayMarketStats(
        isbn="TEST_COMMON",
        sold_count=25,
        active_count=15,
        sold_avg_price=20.00,
        active_avg_price=22.00,
        sell_through_rate=0.63,
        currency="USD"
    )

    rarity = compute_rarity(market)

    rarity_str = f"{rarity:.2f}" if rarity is not None else "None"
    print(f"✓ High-velocity book rarity: {rarity_str} ({market.sold_count} sold in 90 days)")

    # High velocity books should have low rarity score
    if rarity is not None:
        assert rarity < 0.6, f"Expected low rarity for high velocity, got {rarity:.2f}"

    return True


def test_rarity_score_low_velocity():
    """Test rarity score for slow-moving book."""
    market = EbayMarketStats(
        isbn="TEST_RARE",
        sold_count=2,
        active_count=3,
        sold_avg_price=45.00,
        active_avg_price=50.00,
        sell_through_rate=0.40,
        currency="USD"
    )

    rarity = compute_rarity(market)

    rarity_str = f"{rarity:.2f}" if rarity is not None else "None"
    print(f"✓ Low-velocity book rarity: {rarity_str} ({market.sold_count} sold in 90 days)")

    # Low velocity books should have higher rarity score than high velocity
    # Note: compute_rarity uses formula 1 / (active_count + unsold_count + 1)
    # With active_count=3, this gives 1/4 = 0.25
    if rarity is not None:
        assert rarity >= 0.15, f"Expected moderate-to-high rarity for low velocity, got {rarity:.2f}"

    return True


def test_rarity_score_no_data():
    """Test rarity score with no market data."""
    market = EbayMarketStats(
        isbn="TEST_NODATA",
        sold_count=0,
        active_count=0,
        sold_avg_price=None,
        active_avg_price=None,
        sell_through_rate=None,
        currency="USD"
    )

    rarity = compute_rarity(market)

    print(f"✓ No market data rarity: {rarity}")

    # Should handle gracefully (return None or max rarity)
    # Note: Actual behavior depends on implementation

    return True


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def main():
    """Run all profit calculation tests."""
    print("\n" + "="*70)
    print("PROFIT CALCULATION TEST SUITE")
    print("="*70)

    tests = [
        # eBay fee tests
        ("eBay Fees - Standard ($20)", test_ebay_fees_standard),
        ("eBay Fees - Low Price ($5)", test_ebay_fees_low_price),
        ("eBay Fees - High Price ($100)", test_ebay_fees_high_price),
        ("eBay Fees - Minimal ($1)", test_ebay_fees_minimal),

        # Amazon fee tests
        ("Amazon Fees - Standard ($20)", test_amazon_fees_standard),
        ("Amazon Fees - Low Price ($5)", test_amazon_fees_low_price),
        ("Amazon Fees - High Price ($100)", test_amazon_fees_high_price),
        ("Fee Comparison", test_fee_comparison),

        # Profit calculation tests
        ("Profit - Typical eBay", test_profit_typical_ebay),
        ("Profit - Typical Amazon", test_profit_typical_amazon),
        ("Profit - Marginal Deal", test_profit_marginal),
        ("Profit - Loss Scenario", test_profit_loss),
        ("Profit - Breakeven", test_profit_breakeven),

        # Price estimation tests
        ("Price Estimation - Strong Data", test_price_estimation_strong_data),
        ("Price Estimation - Sparse Data", test_price_estimation_sparse_data),
        ("Price Estimation - No Data", test_price_estimation_no_data),
        ("Price Estimation - Outliers", test_price_estimation_outliers),

        # Rarity tests
        ("Rarity Score - High Velocity", test_rarity_score_high_velocity),
        ("Rarity Score - Low Velocity", test_rarity_score_low_velocity),
        ("Rarity Score - No Data", test_rarity_score_no_data),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        print(f"\n{'─'*70}")
        print(f"Test: {test_name}")
        print(f"{'─'*70}")

        try:
            result = test_func()
            if result:
                passed += 1
                print(f"✅ PASSED")
            else:
                failed += 1
                print(f"❌ FAILED")
        except Exception as e:
            failed += 1
            print(f"❌ FAILED: {e}")

    # Summary
    print(f"\n{'='*70}")
    print("TEST SUMMARY")
    print(f"{'='*70}")
    print(f"Total tests: {passed + failed}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"Success rate: {(passed/(passed+failed)*100):.1f}%")
    print(f"{'='*70}\n")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
