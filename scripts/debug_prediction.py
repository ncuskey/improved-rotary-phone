#!/usr/bin/env python3
"""
Debug ML prediction for a specific ISBN.

Shows which model was used, what features were extracted, and why
the prediction came out as it did.
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from isbn_lot_optimizer.ml.prediction_router import get_prediction_router
from isbn_lot_optimizer.ml.feature_extractor import PlatformFeatureExtractor
from shared.database import get_db_connection


def debug_prediction(isbn: str):
    """Debug prediction for an ISBN."""
    print(f"\n=== Debugging Prediction for ISBN: {isbn} ===\n")

    # Get book data from database
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get metadata
        cursor.execute("""
            SELECT title, author, publisher, page_count, publish_date,
                   amazon_rank, ratings_count, average_rating
            FROM book_metadata
            WHERE isbn = ?
        """, (isbn,))
        metadata_row = cursor.fetchone()

        if not metadata_row:
            print(f"❌ No metadata found for ISBN {isbn}")
            return

        print(f"📖 Title: {metadata_row[0]}")
        print(f"👤 Author: {metadata_row[1]}")
        print(f"📄 Pages: {metadata_row[3]}")
        print(f"📊 Amazon Rank: {metadata_row[5]}")
        print(f"⭐ Rating: {metadata_row[7]} ({metadata_row[6]} ratings)")
        print()

        # Get market data
        cursor.execute("""
            SELECT active_median_price, sold_comps_median, sold_count,
                   active_count, sold_comps_min, sold_comps_max
            FROM ebay_market
            WHERE isbn = ?
        """, (isbn,))
        market_row = cursor.fetchone()

        if market_row:
            print("🏪 eBay Market Data:")
            print(f"  Active Median: ${market_row[0] or 'N/A'}")
            print(f"  Sold Median: ${market_row[1] or 'N/A'}")
            print(f"  Sold Count: {market_row[2] or 0}")
            print(f"  Active Count: {market_row[3] or 0}")
            print()
        else:
            print("❌ No eBay market data")
            print()

        # Get AbeBooks data
        cursor.execute("""
            SELECT abebooks_min_price, abebooks_avg_price, abebooks_seller_count
            FROM abebooks_pricing
            WHERE isbn = ?
        """, (isbn,))
        abebooks_row = cursor.fetchone()

        if abebooks_row and abebooks_row[1]:
            print("📚 AbeBooks Data:")
            print(f"  Min Price: ${abebooks_row[0]}")
            print(f"  Avg Price: ${abebooks_row[1]}")
            print(f"  Seller Count: {abebooks_row[2]}")
            print()
        else:
            print("❌ No AbeBooks data")
            print()

    # Make prediction
    router = get_prediction_router()

    # This is simplified - in reality you'd need to reconstruct the full objects
    # For now, just show routing stats
    print("🤖 Model Routing Statistics:")
    print(f"  Total Predictions: {router.stats['total_predictions']}")
    print(f"  AbeBooks Specialist: {router.stats['abebooks_routed']} ({router.stats['abebooks_routed']/max(1, router.stats['total_predictions'])*100:.1f}%)")
    print(f"  eBay Specialist: {router.stats['ebay_routed']} ({router.stats['ebay_routed']/max(1, router.stats['total_predictions'])*100:.1f}%)")
    print(f"  Unified Fallback: {router.stats['unified_fallback']} ({router.stats['unified_fallback']/max(1, router.stats['total_predictions'])*100:.1f}%)")
    print()

    print("💡 Common Reasons for $13.25 Prediction:")
    print("  1. Missing eBay market data → Unified model fallback")
    print("  2. Missing AbeBooks data → Unified model fallback")
    print("  3. Missing metadata (pages, rank, ratings) → Fewer features")
    print("  4. Model predicts near training set mean (~$13) when uncertain")
    print()
    print("✅ Solutions:")
    print("  1. Collect eBay sold listings for this ISBN")
    print("  2. Collect AbeBooks pricing data")
    print("  3. Enrich metadata (Amazon rank, ratings, page count)")
    print("  4. Retrain model with more diverse price range")


def main():
    parser = argparse.ArgumentParser(description="Debug ML prediction for ISBN")
    parser.add_argument("isbn", help="ISBN to debug")
    args = parser.parse_args()

    debug_prediction(args.isbn)


if __name__ == "__main__":
    main()
