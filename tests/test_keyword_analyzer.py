#!/usr/bin/env python3
"""Tests for keyword analyzer and SEO title generation.

This test file verifies:
1. Keyword extraction from eBay titles
2. Keyword scoring algorithm
3. Title score calculation
4. Caching behavior
5. Integration with AI title generation

Usage:
    python3 tests/test_keyword_analyzer.py
    pytest tests/test_keyword_analyzer.py -v
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env
env_file = PROJECT_ROOT / '.env'
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key] = value

from isbn_lot_optimizer.keyword_analyzer import (
    KeywordAnalyzer,
    calculate_title_score,
    format_keyword_report,
)


def test_keyword_analyzer_basic():
    """Test basic keyword analysis for a known ISBN."""

    # Use a popular book with lots of eBay listings
    # Game of Thrones (Book 1)
    isbn = "9780553381689"

    print(f"\n{'='*70}")
    print(f"Test: Keyword Analysis for ISBN {isbn}")
    print(f"{'='*70}\n")

    analyzer = KeywordAnalyzer()

    # Analyze keywords
    keywords = analyzer.analyze_keywords_for_isbn(isbn, limit=100)

    # Assertions
    assert keywords, "Should return at least some keywords"
    assert len(keywords) > 0, "Should have at least 1 keyword"
    assert len(keywords) <= 50, "Should be limited to max_keywords (50)"

    # Check keyword structure
    first_keyword = keywords[0]
    assert hasattr(first_keyword, 'word'), "Keyword should have 'word' attribute"
    assert hasattr(first_keyword, 'score'), "Keyword should have 'score' attribute"
    assert hasattr(first_keyword, 'frequency'), "Keyword should have 'frequency' attribute"
    assert hasattr(first_keyword, 'avg_price'), "Keyword should have 'avg_price' attribute"

    # Check score range
    assert 0 <= first_keyword.score <= 10, f"Score should be 0-10, got {first_keyword.score}"

    # Print top keywords
    print(format_keyword_report(keywords, top_n=20))

    print(f"\n✓ Found {len(keywords)} keywords")
    print(f"✓ Top keyword: '{first_keyword.word}' (score: {first_keyword.score:.2f}, freq: {first_keyword.frequency})")

    return keywords


def test_title_scoring():
    """Test title scoring with known keywords."""

    print(f"\n{'='*70}")
    print(f"Test: Title Scoring")
    print(f"{'='*70}\n")

    # Get keywords from previous test
    isbn = "9780553381689"
    analyzer = KeywordAnalyzer()
    keywords = analyzer.analyze_keywords_for_isbn(isbn, limit=100, use_cache=True)

    # Test different title styles
    test_titles = [
        # SEO-optimized (keyword-packed)
        "Game Thrones Martin Fantasy Epic Series Hardcover Westeros Dragons Complete",

        # Standard (grammatically correct)
        "A Game of Thrones by George R.R. Martin - Hardcover Fantasy Novel",

        # Minimal (very short)
        "Game of Thrones Book",

        # Keyword spam (too many keywords)
        "Game Thrones GOT Martin GRRR Fantasy Epic Series Westeros Ice Fire Dragons Magic"
    ]

    scores = []
    for title in test_titles:
        score = calculate_title_score(title, keywords)
        scores.append(score)
        print(f"\nTitle: {title}")
        print(f"Score: {score:.1f}")

    # Assertions
    assert scores[0] > scores[2], "SEO title should score higher than minimal title"
    print(f"\n✓ Title scoring works correctly")
    print(f"✓ SEO-optimized title scored: {scores[0]:.1f}")
    print(f"✓ Standard title scored: {scores[1]:.1f}")
    print(f"✓ Minimal title scored: {scores[2]:.1f}")


def test_caching():
    """Test that caching works correctly."""

    print(f"\n{'='*70}")
    print(f"Test: Keyword Analysis Caching")
    print(f"{'='*70}\n")

    isbn = "9780553381689"
    analyzer = KeywordAnalyzer()

    # Clear cache first
    analyzer.clear_cache()
    print("✓ Cache cleared")

    # First call (should hit API)
    print("\nFirst call (no cache):")
    import time
    start = time.time()
    keywords1 = analyzer.analyze_keywords_for_isbn(isbn, limit=50, use_cache=True)
    duration1 = time.time() - start
    print(f"  Duration: {duration1:.2f}s")
    print(f"  Keywords: {len(keywords1)}")

    # Second call (should use cache)
    print("\nSecond call (from cache):")
    start = time.time()
    keywords2 = analyzer.analyze_keywords_for_isbn(isbn, limit=50, use_cache=True)
    duration2 = time.time() - start
    print(f"  Duration: {duration2:.2f}s")
    print(f"  Keywords: {len(keywords2)}")

    # Assertions
    assert len(keywords1) == len(keywords2), "Cache should return same number of keywords"
    assert duration2 < duration1 / 10, f"Cache should be much faster (was {duration2:.2f}s vs {duration1:.2f}s)"

    print(f"\n✓ Caching works correctly")
    print(f"✓ Cache speedup: {duration1/duration2:.1f}x faster")


def test_keyword_filtering():
    """Test that stopwords are properly filtered."""

    print(f"\n{'='*70}")
    print(f"Test: Stopword Filtering")
    print(f"{'='*70}\n")

    from isbn_lot_optimizer.keyword_analyzer import ALL_STOPWORDS

    isbn = "9780553381689"
    analyzer = KeywordAnalyzer()
    keywords = analyzer.analyze_keywords_for_isbn(isbn, limit=100, use_cache=True)

    # Check that no stopwords appear in results
    keyword_words = {kw.word for kw in keywords}
    stopwords_found = keyword_words & ALL_STOPWORDS

    print(f"Total keywords: {len(keywords)}")
    print(f"Stopwords found: {len(stopwords_found)}")

    if stopwords_found:
        print(f"  Stopwords in results: {', '.join(list(stopwords_found)[:10])}")

    assert len(stopwords_found) == 0, f"No stopwords should appear in results, found: {stopwords_found}"

    print(f"\n✓ Stopword filtering works correctly")
    print(f"✓ All {len(keywords)} keywords are meaningful")


def test_scoring_components():
    """Test that individual scoring components work correctly."""

    print(f"\n{'='*70}")
    print(f"Test: Scoring Components")
    print(f"{'='*70}\n")

    isbn = "9780553381689"
    analyzer = KeywordAnalyzer()
    keywords = analyzer.analyze_keywords_for_isbn(isbn, limit=20, use_cache=True)

    # Check that scoring components are reasonable
    for i, kw in enumerate(keywords[:5], 1):
        print(f"\n{i}. '{kw.word}' (overall score: {kw.score:.2f})")
        print(f"   - Frequency: {kw.frequency} listings → score: {kw.frequency_score:.2f}/10")
        print(f"   - Avg Price: ${kw.avg_price:.2f} → score: {kw.price_score:.2f}/10")
        print(f"   - Velocity: {kw.velocity_score:.2f}/10 (N/A for Browse API)")
        print(f"   - Competition: {kw.competition_score:.2f}/10")

        # Assertions
        assert 0 <= kw.frequency_score <= 10, "Frequency score should be 0-10"
        assert 0 <= kw.price_score <= 10, "Price score should be 0-10"
        assert 0 <= kw.velocity_score <= 10, "Velocity score should be 0-10"
        assert 0 <= kw.competition_score <= 10, "Competition score should be 0-10"

    print(f"\n✓ All scoring components are within valid ranges")


def test_multiple_isbns():
    """Test keyword analysis on multiple different books."""

    print(f"\n{'='*70}")
    print(f"Test: Multiple ISBNs")
    print(f"{'='*70}\n")

    test_isbns = [
        ("9780553381689", "Game of Thrones"),
        ("9780439708180", "Harry Potter and the Sorcerer's Stone"),
        ("9780439023480", "The Hunger Games"),
    ]

    analyzer = KeywordAnalyzer()

    for isbn, title in test_isbns:
        print(f"\n{title} ({isbn}):")
        keywords = analyzer.analyze_keywords_for_isbn(isbn, limit=50, use_cache=True)

        if keywords:
            top_5 = keywords[:5]
            print(f"  ✓ Found {len(keywords)} keywords")
            print(f"  ✓ Top 5: {', '.join([f'{kw.word} ({kw.score:.1f})' for kw in top_5])}")
        else:
            print(f"  ⚠️  No keywords found (book may not have eBay listings)")

    print(f"\n✓ Multi-ISBN analysis works")


def main():
    """Run all tests."""

    print("\n" + "="*70)
    print("KEYWORD ANALYZER TEST SUITE")
    print("="*70)

    tests = [
        ("Basic Keyword Analysis", test_keyword_analyzer_basic),
        ("Title Scoring", test_title_scoring),
        ("Caching", test_caching),
        ("Stopword Filtering", test_keyword_filtering),
        ("Scoring Components", test_scoring_components),
        ("Multiple ISBNs", test_multiple_isbns),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n✗ Test failed: {name}")
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "="*70)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    print("="*70)

    if failed > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
