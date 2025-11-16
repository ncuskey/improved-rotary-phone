#!/usr/bin/env python3
"""Test expanded fame database entries."""

from shared.models import BookMetadata
from shared.collectible_detection import detect_collectible

# Test new additions
tests = [
    ("Kurt Vonnegut", "Slaughterhouse-Five", 95),
    ("Hunter S. Thompson", "Fear and Loathing in Las Vegas", 110),
    ("Tolkien, J.R.R.", "The Lord of the Rings", 500),
    ("Martin, George R.R.", "A Game of Thrones", 30),
    ("Gaiman, Neil", "American Gods", 25),
    ("Agatha Christie", "Murder on the Orient Express", 300),
    ("Chandler, Raymond", "The Big Sleep", 200),
    ("Connelly, Michael", "The Black Echo", 12),
    ("Grafton, Sue", "A is for Alibi", 15),
    ("Bourdain, Anthony", "Kitchen Confidential", 45),
    ("Tarantino, Quentin", "Pulp Fiction screenplay", 50),
    ("Coppola, Francis Ford", "The Godfather screenplay", 70),
]

print("\n" + "="*70)
print("TESTING EXPANDED FAME DATABASE")
print("="*70)

passed = 0
failed = 0

for author_name, title, expected_mult in tests:
    metadata = BookMetadata(
        isbn="9780000000000",
        title=title,
        authors=(author_name,),
        published_year=2000
    )

    result = detect_collectible(
        metadata=metadata,
        signed=True,
        first_edition=False
    )

    if result.is_collectible and result.fame_multiplier == expected_mult:
        print(f"✅ {author_name:30s} {result.fame_multiplier:3.0f}x (expected {expected_mult}x)")
        passed += 1
    else:
        print(f"❌ {author_name:30s} {result.fame_multiplier:3.0f}x (expected {expected_mult}x)")
        if not result.is_collectible:
            print(f"   → NOT DETECTED as collectible")
        failed += 1

print("\n" + "="*70)
print(f"RESULTS: {passed}/{len(tests)} tests passed")
if failed == 0:
    print("✅ All tests passed!")
else:
    print(f"⚠️  {failed} tests failed")
print("="*70 + "\n")
