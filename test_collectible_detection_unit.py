#!/usr/bin/env python3
"""
Unit test for collectible detection logic.
Tests the core detection functions with mock metadata.
"""

from shared.models import BookMetadata
from shared.collectible_detection import detect_collectible,CollectibleDetector

def test_signed_famous_person():
    """Test detection of signed books by famous people."""
    print("\n" + "="*70)
    print("TEST 1: Signed book by Frank Herbert")
    print("="*70)

    metadata = BookMetadata(
        isbn="9780385523714",
        title="The White Plague",
        authors=("Frank Herbert",),
        published_year=1982,
        
    )

    result = detect_collectible(
        metadata=metadata,
        signed=True,
        first_edition=True
    )

    print(f"Is Collectible: {result.is_collectible}")
    print(f"Type: {result.collectible_type}")
    print(f"Famous Person: {result.famous_person}")
    print(f"Multiplier: {result.fame_multiplier}x")
    print(f"Notes: {result.notes}")

    assert result.is_collectible,"Should detect as collectible"
    assert result.collectible_type == "signed_famous",f"Wrong type: {result.collectible_type}"
    assert result.fame_multiplier >= 50.0,f"Multiplier too low: {result.fame_multiplier}"
    print("✅ PASS")
    return True


def test_comma_separated_name():
    """Test name parsing for comma-separated names (e.g.,'Scorsese,Martin')."""
    print("\n" + "="*70)
    print("TEST 2: Comma-separated name (Scorsese,Martin)")
    print("="*70)

    # Simulate how metadata might come back with comma-separated author
    metadata = BookMetadata(
        isbn="9780571205455",
        title="Conversations with Scorsese",
        authors=("Scorsese,Martin",),# Comma-separated format
        published_year=2004,
        
    )

    result = detect_collectible(
        metadata=metadata,
        signed=True,
        first_edition=False
    )

    print(f"Is Collectible: {result.is_collectible}")
    print(f"Type: {result.collectible_type}")
    print(f"Famous Person: {result.famous_person}")
    print(f"Multiplier: {result.fame_multiplier}x")

    assert result.is_collectible,"Should detect despite comma-separated name"
    assert result.collectible_type == "signed_famous"
    assert result.fame_multiplier >= 100.0,f"Scorsese multiplier too low: {result.fame_multiplier}"
    print("✅ PASS")
    return True


def test_award_winner_unsigned():
    """Test unsigned first edition by award winner."""
    print("\n" + "="*70)
    print("TEST 3: Unsigned first edition by Pulitzer winner")
    print("="*70)

    metadata = BookMetadata(
        isbn="9780062671110",
        title="The Night Watchman",
        authors=("Louise Erdrich",),
        published_year=2020,
        
    )

    result = detect_collectible(
        metadata=metadata,
        signed=False,
        first_edition=True
    )

    print(f"Is Collectible: {result.is_collectible}")
    print(f"Type: {result.collectible_type}")
    print(f"Multiplier: {result.fame_multiplier}x")
    print(f"Awards: {result.awards}")

    assert result.is_collectible,"Should detect award winner first edition"
    assert result.collectible_type == "award_winner"
    print("✅ PASS")
    return True


def test_bundle_rule_bypass():
    """Test that collectible books bypass the under-$10 bundle rule."""
    print("\n" + "="*70)
    print("TEST 4: Bundle rule bypass for high-fame collectibles")
    print("="*70)

    metadata = BookMetadata(
        isbn="9780385523714",
        title="The White Plague",
        authors=("Frank Herbert",),
        published_year=1982,
        
    )

    collectible_info = detect_collectible(
        metadata=metadata,
        signed=True,
        first_edition=True
    )

    detector = CollectibleDetector()
    should_bypass = detector.should_bypass_bundle_rule(collectible_info,base_price=8.0)

    print(f"Base Price: $8.00 (under $10 threshold)")
    print(f"Fame Multiplier: {collectible_info.fame_multiplier}x")
    print(f"Should Bypass Bundle Rule: {should_bypass}")

    assert should_bypass,"High-fame collectibles should bypass bundle rule"
    print("✅ PASS")
    return True


def test_non_collectible():
    """Test that regular books are not detected as collectible."""
    print("\n" + "="*70)
    print("TEST 5: Regular book (not collectible)")
    print("="*70)

    metadata = BookMetadata(
        isbn="9780123456789",
        title="Some Random Book",
        authors=("Unknown Author",),
        published_year=2020,
        
    )

    result = detect_collectible(
        metadata=metadata,
        signed=False,
        first_edition=False
    )

    print(f"Is Collectible: {result.is_collectible}")
    print(f"Multiplier: {result.fame_multiplier}x")

    assert not result.is_collectible,"Regular book should not be collectible"
    assert result.fame_multiplier == 1.0,"Regular book should have 1.0x multiplier"
    print("✅ PASS")
    return True


def main():
    print("\n" + "="*70)
    print("COLLECTIBLE DETECTION UNIT TESTS")
    print("="*70)

    tests = [
        ("Signed Famous Person",test_signed_famous_person),
        ("Comma-Separated Name",test_comma_separated_name),
        ("Award Winner Unsigned",test_award_winner_unsigned),
        ("Bundle Rule Bypass",test_bundle_rule_bypass),
        ("Non-Collectible",test_non_collectible),
    ]

    passed = 0
    failed = 0

    for name,test_func in tests:
        try:
            if test_func():
                passed += 1
        except AssertionError as e:
            print(f"❌ FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*70}")
    print(f"RESULTS: {passed}/{len(tests)} tests passed")
    if failed > 0:
        print(f"⚠️  {failed} tests failed")
    else:
        print("✅ All tests passed!")
    print(f"{'='*70}\n")

    return failed == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
