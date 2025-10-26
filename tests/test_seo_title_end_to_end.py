#!/usr/bin/env python3
"""End-to-end test for SEO-optimized title generation.

This script demonstrates the complete SEO title workflow:
1. Load a book from the database
2. Analyze keywords from eBay marketplace
3. Generate standard AI title
4. Generate SEO-optimized AI title with keyword ranking
5. Compare scores and show results

Usage:
    python3 tests/test_seo_title_end_to_end.py [isbn]
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables
env_file = PROJECT_ROOT / '.env'
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key] = value

from isbn_lot_optimizer.service import BookService
from isbn_lot_optimizer.ai import EbayListingGenerator
from isbn_lot_optimizer.keyword_analyzer import KeywordAnalyzer, calculate_title_score


def test_seo_title_generation(isbn: str):
    """Test end-to-end SEO title generation for a book."""

    print("\n" + "="*70)
    print("SEO TITLE GENERATION - END-TO-END TEST")
    print("="*70)

    # Initialize services
    db_path = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
    book_service = BookService(db_path)
    generator = EbayListingGenerator()
    analyzer = KeywordAnalyzer()

    # Step 1: Load book
    print(f"\n[1/5] Loading book: {isbn}")
    book = book_service.get_book(isbn)
    if not book:
        print(f"✗ Book not found in database: {isbn}")
        sys.exit(1)

    print(f"  ✓ {book.metadata.title}")
    if book.metadata.authors:
        print(f"    by {', '.join(book.metadata.authors)}")

    # Step 2: Analyze keywords
    print(f"\n[2/5] Analyzing keywords from eBay marketplace...")
    keywords = analyzer.analyze_keywords_for_isbn(isbn, limit=100)

    if not keywords:
        print(f"  ✗ No keywords found (book may not have eBay listings)")
        sys.exit(1)

    print(f"  ✓ Found {len(keywords)} keywords")
    print(f"  ✓ Top 5 keywords:")
    for i, kw in enumerate(keywords[:5], 1):
        print(f"    {i}. '{kw.word}' (score: {kw.score:.2f}, appears {kw.frequency}x, avg price: ${kw.avg_price:.2f})")

    # Step 3: Generate standard title
    print(f"\n[3/5] Generating standard AI title...")
    try:
        standard_content = generator.generate_book_listing(
            book=book,
            condition="Good",
            price=book.estimated_price,
            use_seo_optimization=False,
        )
        standard_title = standard_content.title
        standard_score = calculate_title_score(standard_title, keywords)

        print(f"  ✓ Standard title:")
        print(f"    \"{standard_title}\"")
        print(f"    Score: {standard_score:.1f}")
    except Exception as e:
        print(f"  ✗ Standard title generation failed: {e}")
        print(f"    (This is expected if Ollama is not running)")
        standard_title = None
        standard_score = 0

    # Step 4: Generate SEO-optimized title
    print(f"\n[4/5] Generating SEO-optimized title with keyword ranking...")
    try:
        seo_content = generator.generate_book_listing(
            book=book,
            condition="Good",
            price=book.estimated_price,
            use_seo_optimization=True,
            isbn=isbn,
        )
        seo_title = seo_content.title
        seo_score = seo_content.title_score

        print(f"  ✓ SEO-optimized title:")
        print(f"    \"{seo_title}\"")
        print(f"    Score: {seo_score:.1f}")

        # Show title variations that were considered
        if hasattr(seo_content, 'keyword_scores') and seo_content.keyword_scores:
            print(f"  ✓ Used top {len(seo_content.keyword_scores)} keywords for optimization")

    except Exception as e:
        print(f"  ✗ SEO title generation failed: {e}")
        print(f"    (This is expected if Ollama is not running)")
        seo_title = None
        seo_score = 0

    # Step 5: Compare results
    print(f"\n[5/5] Comparison:")
    print(f"  {'='*68}")

    if standard_title:
        print(f"  Standard Title:")
        print(f"    \"{standard_title}\"")
        print(f"    Length: {len(standard_title)} chars")
        print(f"    Score: {standard_score:.1f}")
        print()

    if seo_title:
        print(f"  SEO-Optimized Title:")
        print(f"    \"{seo_title}\"")
        print(f"    Length: {len(seo_title)} chars")
        print(f"    Score: {seo_score:.1f}")
        print()

    if standard_score and seo_score:
        improvement = ((seo_score - standard_score) / standard_score) * 100
        print(f"  Score Improvement: {improvement:+.1f}%")
        print(f"  {'='*68}")

        if seo_score > standard_score:
            print(f"\n  ✓ SEO optimization produced a higher-scoring title!")
        else:
            print(f"\n  ⚠️  Standard title scored higher (may need tuning)")

    print("\n" + "="*70)
    print("END-TO-END TEST COMPLETE")
    print("="*70)

    # Return data for programmatic use
    return {
        'isbn': isbn,
        'book_title': book.metadata.title,
        'keywords_found': len(keywords),
        'standard_title': standard_title,
        'standard_score': standard_score,
        'seo_title': seo_title,
        'seo_score': seo_score,
    }


def main():
    """Run the end-to-end test."""

    # Default ISBN (Game of Thrones)
    default_isbn = "9780553381689"

    if len(sys.argv) > 1:
        isbn = sys.argv[1]
    else:
        isbn = default_isbn
        print(f"Using default ISBN: {isbn}")
        print(f"(Specify a different ISBN: python3 tests/test_seo_title_end_to_end.py <isbn>)")

    try:
        result = test_seo_title_generation(isbn)

        # Exit with success if we got results
        if result['seo_title']:
            sys.exit(0)
        else:
            print("\n⚠️  SEO title generation requires Ollama to be running:")
            print("    ollama serve")
            print("    ollama pull llama3.1:8b")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
