"""eBay listing service - combines AI generation, eBay APIs, and database tracking.

This is the high-level service that orchestrates the complete listing creation workflow:
1. Generate AI-powered listing content
2. Create inventory and offer on eBay
3. Track listing in database
4. Update status when sold

Example usage:
    from isbn_lot_optimizer.ebay_listing import EbayListingService
    from isbn_lot_optimizer.service import BookService

    # Initialize
    listing_service = EbayListingService(db_path)
    book_service = BookService(db_path)

    # Get a book
    book = book_service.get_book("9780553381702")

    # Create and publish listing
    listing = listing_service.create_book_listing(
        book=book,
        price=15.99,
        condition="Good",
        use_ai=True,
    )

    print(f"✓ Listed on eBay: {listing['ebay_listing_id']}")
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from isbn_lot_optimizer.ai import EbayListingGenerator, GenerationError
from isbn_lot_optimizer.ebay_sell import EbaySellClient, EbaySellError
from shared.models import BookEvaluation, LotSuggestion

logger = logging.getLogger(__name__)


@dataclass
class EbayListingRecord:
    """Listing record for database tracking."""
    id: Optional[int]
    isbn: Optional[str]
    lot_id: Optional[int]
    ebay_listing_id: Optional[str]
    ebay_offer_id: Optional[str]
    sku: str
    title: str
    description: str
    photos: List[str]
    listing_price: float
    estimated_price: float
    cost_basis: Optional[float]
    quantity: int
    condition: str
    format: Optional[str]
    status: str
    listed_at: Optional[str]
    sold_at: Optional[str]
    final_sale_price: Optional[float]
    actual_tts_days: Optional[int]
    ai_generated: bool
    ai_model: Optional[str]
    user_edited: bool
    created_at: str
    updated_at: str


class EbayListingService:
    """High-level service for creating and managing eBay listings."""

    def __init__(
        self,
        db_path: Path,
        token_broker_url: str = "http://localhost:8787",
        ai_model: str = "llama3.1:8b",
    ):
        """
        Initialize the listing service.

        Args:
            db_path: Path to catalog database
            token_broker_url: Token broker URL
            ai_model: Ollama model for AI generation
        """
        self.db_path = Path(db_path)
        self.ebay_client = EbaySellClient(token_broker_url=token_broker_url)
        self.ai_generator = EbayListingGenerator(model=ai_model)

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_book_listing(
        self,
        book: BookEvaluation,
        price: Optional[float] = None,
        condition: str = "Good",
        quantity: int = 1,
        use_ai: bool = True,
        custom_title: Optional[str] = None,
        custom_description: Optional[str] = None,
        photos: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create and publish an eBay listing for a book.

        Args:
            book: Book evaluation
            price: Listing price (uses estimated_price if None)
            condition: Book condition
            quantity: Available quantity
            use_ai: Whether to use AI for title/description generation
            custom_title: Custom title (overrides AI)
            custom_description: Custom description (overrides AI)
            photos: Photo URLs/paths

        Returns:
            Dict with listing details

        Raises:
            EbaySellError: If eBay API call fails
            GenerationError: If AI generation fails
        """
        listing_price = price or book.estimated_price

        # Generate listing content
        if use_ai and not (custom_title and custom_description):
            logger.info(f"Generating AI listing content for {book.metadata.title}")
            try:
                ai_content = self.ai_generator.generate_book_listing(
                    book=book,
                    condition=condition,
                    price=listing_price,
                )
                title = custom_title or ai_content.title
                description = custom_description or ai_content.description
                ai_generated = True
                ai_model = ai_content.model_used
                user_edited = bool(custom_title or custom_description)
            except GenerationError as e:
                logger.warning(f"AI generation failed, using fallback: {e}")
                title = custom_title or book.metadata.title
                description = custom_description or (book.metadata.description or book.metadata.title)
                ai_generated = False
                ai_model = None
                user_edited = False
        else:
            title = custom_title or book.metadata.title
            description = custom_description or (book.metadata.description or book.metadata.title)
            ai_generated = False
            ai_model = None
            user_edited = False

        # Prepare photos
        photo_urls = photos or ([book.metadata.thumbnail] if book.metadata.thumbnail else [])

        # Create listing on eBay
        logger.info(f"Creating eBay listing for {book.metadata.isbn}")
        try:
            ebay_result = self.ebay_client.create_and_publish_book_listing(
                book=book,
                price=listing_price,
                condition=condition,
                quantity=quantity,
                listing_description=description,
            )

            sku = ebay_result["sku"]
            offer_id = ebay_result["offer_id"]
            listing_id = ebay_result.get("listing_id")

            logger.info(f"✓ Created eBay listing: SKU={sku}, Offer={offer_id}")

        except EbaySellError as e:
            logger.error(f"Failed to create eBay listing: {e}")
            # Save as draft in database
            draft_id = self._save_listing_draft(
                isbn=book.metadata.isbn,
                title=title,
                description=description,
                photos=photo_urls,
                price=listing_price,
                condition=condition,
                quantity=quantity,
                estimated_price=book.estimated_price,
                ai_generated=ai_generated,
                ai_model=ai_model,
                user_edited=user_edited,
                error_message=str(e),
            )
            raise EbaySellError(f"Failed to create listing (saved as draft {draft_id}): {e}") from e

        # Save to database
        listing_id_db = self._save_listing(
            isbn=book.metadata.isbn,
            sku=sku,
            ebay_offer_id=offer_id,
            ebay_listing_id=listing_id,
            title=title,
            description=description,
            photos=photo_urls,
            listing_price=listing_price,
            estimated_price=book.estimated_price,
            condition=condition,
            quantity=quantity,
            ai_generated=ai_generated,
            ai_model=ai_model,
            user_edited=user_edited,
        )

        logger.info(f"✓ Listing saved to database: ID={listing_id_db}")

        return {
            "id": listing_id_db,
            "sku": sku,
            "offer_id": offer_id,
            "ebay_listing_id": listing_id,
            "title": title,
            "description": description,
            "price": listing_price,
            "status": "active",
        }

    def _save_listing(
        self,
        isbn: str,
        sku: str,
        ebay_offer_id: str,
        ebay_listing_id: Optional[str],
        title: str,
        description: str,
        photos: List[str],
        listing_price: float,
        estimated_price: float,
        condition: str,
        quantity: int,
        ai_generated: bool,
        ai_model: Optional[str],
        user_edited: bool,
    ) -> int:
        """Save listing to database."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ebay_listings (
                    isbn, sku, ebay_offer_id, ebay_listing_id,
                    title, description, photos,
                    listing_price, estimated_price, condition, quantity,
                    status, listed_at,
                    ai_generated, ai_model, user_edited
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    isbn, sku, ebay_offer_id, ebay_listing_id,
                    title, description, json.dumps(photos),
                    listing_price, estimated_price, condition, quantity,
                    "active", datetime.now().isoformat(),
                    1 if ai_generated else 0, ai_model, 1 if user_edited else 0,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def _save_listing_draft(
        self,
        isbn: str,
        title: str,
        description: str,
        photos: List[str],
        price: float,
        condition: str,
        quantity: int,
        estimated_price: float,
        ai_generated: bool,
        ai_model: Optional[str],
        user_edited: bool,
        error_message: str,
    ) -> int:
        """Save failed listing as draft."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ebay_listings (
                    isbn, sku, title, description, photos,
                    listing_price, estimated_price, condition, quantity,
                    status, error_message,
                    ai_generated, ai_model, user_edited
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    isbn, f"DRAFT-{int(datetime.now().timestamp())}",
                    title, description, json.dumps(photos),
                    price, estimated_price, condition, quantity,
                    "error", error_message,
                    1 if ai_generated else 0, ai_model, 1 if user_edited else 0,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_listing(self, listing_id: int) -> Optional[EbayListingRecord]:
        """Get a listing by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM ebay_listings WHERE id = ?",
                (listing_id,)
            )
            row = cursor.fetchone()

        if not row:
            return None

        return EbayListingRecord(
            id=row["id"],
            isbn=row["isbn"],
            lot_id=row["lot_id"],
            ebay_listing_id=row["ebay_listing_id"],
            ebay_offer_id=row["ebay_offer_id"],
            sku=row["sku"],
            title=row["title"],
            description=row["description"],
            photos=json.loads(row["photos"] or "[]"),
            listing_price=row["listing_price"],
            estimated_price=row["estimated_price"],
            cost_basis=row["cost_basis"],
            quantity=row["quantity"],
            condition=row["condition"],
            format=row["format"],
            status=row["status"],
            listed_at=row["listed_at"],
            sold_at=row["sold_at"],
            final_sale_price=row["final_sale_price"],
            actual_tts_days=row["actual_tts_days"],
            ai_generated=bool(row["ai_generated"]),
            ai_model=row["ai_model"],
            user_edited=bool(row["user_edited"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_active_listings(self) -> List[EbayListingRecord]:
        """Get all active listings."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM ebay_listings WHERE status = 'active' ORDER BY listed_at DESC"
            )
            rows = cursor.fetchall()

        return [
            EbayListingRecord(
                id=row["id"],
                isbn=row["isbn"],
                lot_id=row["lot_id"],
                ebay_listing_id=row["ebay_listing_id"],
                ebay_offer_id=row["ebay_offer_id"],
                sku=row["sku"],
                title=row["title"],
                description=row["description"],
                photos=json.loads(row["photos"] or "[]"),
                listing_price=row["listing_price"],
                estimated_price=row["estimated_price"],
                cost_basis=row["cost_basis"],
                quantity=row["quantity"],
                condition=row["condition"],
                format=row["format"],
                status=row["status"],
                listed_at=row["listed_at"],
                sold_at=row["sold_at"],
                final_sale_price=row["final_sale_price"],
                actual_tts_days=row["actual_tts_days"],
                ai_generated=bool(row["ai_generated"]),
                ai_model=row["ai_model"],
                user_edited=bool(row["user_edited"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def mark_listing_sold(
        self,
        listing_id: int,
        final_sale_price: float,
        sold_at: Optional[str] = None,
    ) -> None:
        """
        Mark a listing as sold and calculate metrics.

        Args:
            listing_id: Listing ID
            final_sale_price: Actual sale price
            sold_at: Sale timestamp (uses now if None)
        """
        listing = self.get_listing(listing_id)
        if not listing:
            raise ValueError(f"Listing {listing_id} not found")

        sold_timestamp = sold_at or datetime.now().isoformat()

        # Calculate actual TTS
        if listing.listed_at:
            listed_dt = datetime.fromisoformat(listing.listed_at)
            sold_dt = datetime.fromisoformat(sold_timestamp)
            actual_tts_days = (sold_dt - listed_dt).days
        else:
            actual_tts_days = None

        # Calculate accuracy metrics
        price_accuracy = final_sale_price / listing.estimated_price if listing.estimated_price else None

        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE ebay_listings
                SET status = 'sold',
                    sold_at = ?,
                    final_sale_price = ?,
                    actual_tts_days = ?,
                    price_accuracy = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (sold_timestamp, final_sale_price, actual_tts_days, price_accuracy, listing_id),
            )
            conn.commit()

        logger.info(
            f"✓ Listing {listing_id} marked as sold: "
            f"${final_sale_price:.2f} (estimated ${listing.estimated_price:.2f}), "
            f"TTS={actual_tts_days} days"
        )
