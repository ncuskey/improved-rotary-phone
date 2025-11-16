#!/usr/bin/env python3
"""
Quick test of collectible detection integration.
Tests the books that were problematic in our comparison notes.
"""

from pathlib import Path
from isbn_lot_optimizer.service import BookService

def test_collectible_book(isbn: str, title: str, signed: bool, first_ed: bool, expected_min_price: float):
    """Test a collectible book."""
    print(f"\n{'='*70}")
    print(f"Testing: {title}")
    print(f"ISBN: {isbn}")
    print(f"Signed: {signed}, First Edition: {first_ed}")
    print(f"Expected minimum price: ${expected_min_price:.2f}")
    print(f"{'='*70}")

    db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
    service = BookService(database_path=str(db_path))

    try:
        evaluation = service.evaluate_isbn(
            isbn,
            condition="Good",
            signed=signed,
            first_edition=first_ed,
            include_market=True  # Need market fetch for full metadata
        )

        # Debug: Show metadata
        if evaluation.metadata:
            print(f"\nMetadata Title: {evaluation.metadata.title}")
            if evaluation.metadata.authors:
                print(f"Metadata Authors: {evaluation.metadata.authors}")
            else:
                print(f"⚠️  NO AUTHORS IN METADATA (but metadata object exists)")
        else:
            print(f"\n⚠️  NO METADATA OBJECT AT ALL")

        print(f"\nSystem Prediction: ${evaluation.estimated_price:.2f}")
        print(f"Probability: {evaluation.probability_label} ({evaluation.probability_score:.1f}/100)")

        # Check justification for collectible detection
        print(f"\nJustification:")
        for reason in evaluation.justification[:8]:  # Show first 8 reasons
            print(f"  • {reason}")

        # Validate
        if evaluation.estimated_price >= expected_min_price:
            print(f"\n✅ PASS: ${evaluation.estimated_price:.2f} >= ${expected_min_price:.2f}")
            return True
        else:
            print(f"\n❌ FAIL: ${evaluation.estimated_price:.2f} < ${expected_min_price:.2f}")
            return False

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        service.close()


def main():
    print("\n" + "="*70)
    print("COLLECTIBLE DETECTION FIX VALIDATION")
    print("="*70)
    print("\nTesting books from comparison notes that were undervalued...")

    tests = [
        # Book 2: Frank Herbert signed first edition
        ("0385523718", "The White Plague by Frank Herbert", True, True, 100.0),

        # Book 3: Demi Moore signed memoir
        ("0062963910", "Inside Out by Demi Moore", True, False, 50.0),

        # Book 6: Liz Goldwyn signed
        ("1594862516", "Pretty Things by Liz Goldwyn", True, False, 30.0),

        # Book 7: Martin Scorsese signed
        ("0571205453", "Conversations with Scorsese", True, False, 200.0),

        # Book 9: Buzz Aldrin signed
        ("0061374318", "Magnificent Desolation by Buzz Aldrin", True, False, 80.0),

        # Book 10: Louise Erdrich first edition (award winner)
        ("0062671111", "The Night Watchman by Louise Erdrich", False, True, 15.0),
    ]

    passed = 0
    failed = 0

    for isbn, title, signed, first_ed, min_price in tests:
        if test_collectible_book(isbn, title, signed, first_ed, min_price):
            passed += 1
        else:
            failed += 1

    print(f"\n{'='*70}")
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(f"{'='*70}\n")

    return failed == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
