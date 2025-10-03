#!/usr/bin/env python3
"""
Create sample data for testing the Lot Details page.
"""

import sys
from pathlib import Path

# Add the project root to Python path
sys.path.append('.')

from isbn_lot_optimizer.service import BookService
from isbn_lot_optimizer.models import BookEvaluation, BookMetadata, EbayMarketStats
from isbn_lot_optimizer.probability import build_book_evaluation
import json

def create_sample_data():
    """Create sample books and lots for testing."""
    
    # Initialize service
    service = BookService(Path('books.db'))
    
    # Create sample books
    sample_books = [
        {
            "isbn": "9780123456789",
            "title": "The Great Adventure",
            "authors": ("John Smith",),
            "condition": "Very Good",
            "estimated_price": 15.99,
            "published_year": 2020,
        },
        {
            "isbn": "9780123456790",
            "title": "Mystery of the Lost City",
            "authors": ("Jane Doe",),
            "condition": "Good",
            "estimated_price": 12.50,
            "published_year": 2019,
        },
        {
            "isbn": "9780123456791",
            "title": "Space Odyssey",
            "authors": ("Robert Johnson",),
            "condition": "Like New",
            "estimated_price": 18.75,
            "published_year": 2021,
        },
        {
            "isbn": "9780123456792",
            "title": "The Art of Programming",
            "authors": ("Alice Wilson",),
            "condition": "Excellent",
            "estimated_price": 25.00,
            "published_year": 2022,
        },
        {
            "isbn": "9780123456793",
            "title": "Cooking Masterclass",
            "authors": ("Chef Marco",),
            "condition": "Good",
            "estimated_price": 14.99,
            "published_year": 2020,
        },
    ]
    
    print("📚 Creating sample books...")
    
    for book_data in sample_books:
        # Create book metadata
        metadata = BookMetadata(
            isbn=book_data["isbn"],
            title=book_data["title"],
            authors=book_data["authors"],
            published_year=book_data["published_year"],
            source="sample"
        )
        
        # Create market stats
        market_stats = EbayMarketStats(
            isbn=book_data["isbn"],
            active_count=10,
            active_avg_price=book_data["estimated_price"],
            sold_count=5,
            sold_avg_price=book_data["estimated_price"] * 0.9,
            sell_through_rate=0.8,
            currency="USD",
            active_median_price=book_data["estimated_price"],
            sold_median_price=book_data["estimated_price"] * 0.9
        )
        
        # Create book evaluation using the proper builder function
        book = build_book_evaluation(
            isbn=book_data["isbn"],
            original_isbn=book_data["isbn"],
            metadata=metadata,
            market=market_stats,
            condition=book_data["condition"],
            edition=None
        )
        
        # Add to database using the internal persist method
        service._persist_book(book)
        print(f"   ✓ Added: {book_data['title']} by {book_data['authors'][0]}")
    
    print(f"\n📦 Generating lots from {len(sample_books)} books...")
    
    # Generate lots
    lots = service.recompute_lots()
    
    print(f"✅ Created {len(lots)} lots:")
    for i, lot in enumerate(lots, 1):
        print(f"   {i}. {lot.name} (ID: {getattr(lot, 'id', 'N/A')}) - ${lot.estimated_value:.2f}")
    
    print(f"\n🎉 Sample data created successfully!")
    print(f"   - {len(sample_books)} books")
    print(f"   - {len(lots)} lots")
    print(f"\n🚀 You can now test the lot details page!")
    print(f"   - Start server: uvicorn isbn_web.main:app --reload")
    print(f"   - Go to: http://localhost:8000")
    print(f"   - Click on a lot to see details")

if __name__ == "__main__":
    create_sample_data()
