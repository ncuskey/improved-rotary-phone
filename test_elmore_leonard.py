#!/usr/bin/env python3
"""Quick test of Elmore Leonard detection."""

from shared.models import BookMetadata
from shared.collectible_detection import detect_collectible

# Test with comma-separated name as it appears in metadata
metadata = BookMetadata(
    isbn="9780385308465",
    title="Pronto",
    authors=("Elmore, Leonard",),
    published_year=1993
)

result = detect_collectible(
    metadata=metadata,
    signed=True,
    first_edition=True
)

print(f"ISBN: {metadata.isbn}")
print(f"Title: {metadata.title}")
print(f"Author: {metadata.authors[0]}")
print(f"\nIs Collectible: {result.is_collectible}")
print(f"Type: {result.collectible_type}")
print(f"Famous Person: {result.famous_person}")
print(f"Multiplier: {result.fame_multiplier}x")
print(f"Notes: {result.notes}")

if result.is_collectible:
    base_price = 9.30
    collectible_price = base_price * result.fame_multiplier
    print(f"\nBase ML Price: ${base_price:.2f}")
    print(f"With Collectible Multiplier: ${collectible_price:.2f}")
    print(f"\n✅ SUCCESS: Elmore Leonard detected as collectible!")
else:
    print(f"\n❌ FAILED: Elmore Leonard not detected")
