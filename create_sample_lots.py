#!/usr/bin/env python3
"""
Create sample lots manually for testing the Lot Details page.
"""

import sys
from pathlib import Path
import json

# Add the project root to Python path
sys.path.append('.')

from isbn_lot_optimizer.service import BookService
from isbn_lot_optimizer.models import LotSuggestion

def create_sample_lots():
    """Create sample lots manually for testing."""
    
    # Initialize service
    service = BookService(Path('books.db'))
    
    # Get existing books
    books = service.list_books()
    print(f"📚 Found {len(books)} books in database")
    
    if len(books) < 2:
        print("❌ Need at least 2 books to create lots. Run create_sample_data.py first.")
        return
    
    # Create sample lots manually
    sample_lots = [
        {
            "name": "Adventure Books Collection",
            "strategy": "author",
            "book_isbns": [books[0].isbn, books[1].isbn],  # First two books
            "estimated_value": books[0].estimated_price + books[1].estimated_price,
            "probability_score": 0.85,
            "probability_label": "Good",
            "sell_through": 0.75,
            "justification": "Both books are adventure genre\nSimilar target audience\nGood condition books with market demand"
        },
        {
            "name": "Programming & Technology",
            "strategy": "genre", 
            "book_isbns": [books[2].isbn, books[3].isbn],  # Programming books
            "estimated_value": books[2].estimated_price + books[3].estimated_price,
            "probability_score": 0.92,
            "probability_label": "Excellent",
            "sell_through": 0.85,
            "justification": "Technology books have high demand\nProgramming books sell well together\nExcellent condition increases value"
        },
        {
            "name": "Cooking & Lifestyle",
            "strategy": "genre",
            "book_isbns": [books[4].isbn],  # Single cooking book
            "estimated_value": books[4].estimated_price,
            "probability_score": 0.78,
            "probability_label": "Good", 
            "sell_through": 0.70,
            "justification": "Cooking books are popular\nSingle book lot for testing"
        }
    ]
    
    print("\n📦 Creating sample lots...")
    
    # Add lots to database
    service.db.replace_lots(sample_lots)
    
    print("✅ Created sample lots:")
    for i, lot_data in enumerate(sample_lots, 1):
        print(f"   {i}. {lot_data['name']} - ${lot_data['estimated_value']:.2f}")
    
    # Verify lots were created
    lots = service.list_lots()
    print(f"\n🎉 Successfully created {len(lots)} lots in database!")
    
    for lot in lots:
        lot_id = getattr(lot, 'id', 'N/A')
        print(f"   - {lot.name} (ID: {lot_id}) - ${lot.estimated_value:.2f}")
    
    print(f"\n🚀 You can now test the lot details page!")
    print(f"   - Start server: uvicorn isbn_web.main:app --reload")
    print(f"   - Go to: http://localhost:8000")
    print(f"   - Click on a lot to see details")
    print(f"   - Or go directly to: http://localhost:8000/api/lots/1/details")

if __name__ == "__main__":
    create_sample_lots()
