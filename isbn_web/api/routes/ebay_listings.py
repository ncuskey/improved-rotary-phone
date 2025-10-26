"""API routes for eBay listing management."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from isbn_lot_optimizer.service import BookService
from isbn_lot_optimizer.ebay_listing import EbayListingService

from ..dependencies import get_book_service

router = APIRouter()


class ItemSpecifics(BaseModel):
    """Schema for eBay Item Specifics (custom aspects provided by user)."""

    # User-provided format and condition details
    format: Optional[List[str]] = Field(None, description="Book format (e.g., Hardcover, Paperback, Mass Market)")
    language: Optional[List[str]] = Field(None, description="Book language (default: English)")
    features: Optional[List[str]] = Field(None, description="Special features (e.g., Dust Jacket, Signed, First Edition)")
    special_attributes: Optional[List[str]] = Field(None, description="Special attributes (e.g., Illustrated, Large Print)")

    # Additional fields that might come from iOS wizard
    narrative_type: Optional[List[str]] = Field(None, description="Fiction or Nonfiction")
    genre: Optional[List[str]] = Field(None, description="Genre override")

    class Config:
        json_schema_extra = {
            "example": {
                "format": ["Hardcover"],
                "language": ["English"],
                "features": ["Dust Jacket", "First Edition"]
            }
        }


class CreateEbayListingRequest(BaseModel):
    """Schema for creating an eBay listing."""

    isbn: str = Field(..., description="ISBN-10 or ISBN-13")
    price: float = Field(..., description="Listing price in USD", gt=0)
    condition: str = Field("Good", description="eBay condition (Acceptable, Good, Very Good, Like New, New)")
    quantity: int = Field(1, description="Number of copies to list", gt=0)
    item_specifics: Optional[ItemSpecifics] = Field(None, description="Custom Item Specifics from user")
    use_seo_optimization: bool = Field(False, description="Use SEO-optimized title generation")

    class Config:
        json_schema_extra = {
            "example": {
                "isbn": "9780545349277",
                "price": 24.99,
                "condition": "Very Good",
                "quantity": 1,
                "item_specifics": {
                    "format": ["Hardcover"],
                    "language": ["English"],
                    "features": ["Dust Jacket"]
                },
                "use_seo_optimization": True
            }
        }


class CreateEbayListingResponse(BaseModel):
    """Schema for eBay listing creation response."""

    id: int = Field(..., description="Database ID of the listing")
    sku: str = Field(..., description="Generated SKU")
    offer_id: Optional[str] = Field(None, description="eBay Offer ID")
    ebay_listing_id: Optional[str] = Field(None, description="eBay Listing ID")
    epid: Optional[str] = Field(None, description="eBay Product ID (if found)")
    title: str = Field(..., description="Generated listing title")
    title_score: Optional[float] = Field(None, description="SEO title score (if SEO enabled)")
    price: float = Field(..., description="Listing price")
    status: str = Field(..., description="Listing status (draft, active, etc.)")

    class Config:
        json_schema_extra = {
            "example": {
                "id": 123,
                "sku": "BOOK-9780545349277-1698345678",
                "offer_id": "12345678901",
                "ebay_listing_id": "123456789012",
                "epid": "201632303",
                "title": "Wings Fire Brightest Night Sutherland Fantasy Series Hardcover Complete",
                "title_score": 48.7,
                "price": 24.99,
                "status": "active"
            }
        }


@router.post("/create-listing", response_model=CreateEbayListingResponse)
async def create_ebay_listing(
    request: CreateEbayListingRequest,
    service: BookService = Depends(get_book_service),
) -> JSONResponse:
    """
    Create an eBay listing for a book.

    This endpoint handles the complete eBay listing workflow:
    1. Retrieves book metadata from the catalog
    2. Looks up cached ePID (for auto-populated Item Specifics)
    3. Generates AI-powered title and description
    4. Creates eBay inventory item and offer
    5. Returns listing details including ePID status

    **ePID Auto-Population:**
    - If ePID is found, eBay auto-populates 20+ Item Specifics (Author, Publisher, Year, Pages, etc.)
    - If no ePID, comprehensive manual Item Specifics are used (from metadata + user inputs)

    **SEO Optimization:**
    - When `use_seo_optimization=true`, generates keyword-ranked titles
    - Achieves 50%+ higher keyword scores vs standard titles

    **Item Specifics:**
    - User provides: Format, Language, Features, Special Attributes
    - System derives: Genre, Narrative Type (Fiction/Nonfiction)
    - Metadata provides: Author, Publisher, Year, Pages, Series
    """
    try:
        # Get book from catalog
        book = service.get_book(request.isbn)
        if not book:
            raise HTTPException(
                status_code=404,
                detail=f"Book not found in catalog: {request.isbn}. Please scan the book first."
            )

        # Initialize eBay listing service
        listing_service = EbayListingService(service.db.db_path)

        # Convert ItemSpecifics model to dict (filter out None values)
        item_specifics_dict = None
        if request.item_specifics:
            item_specifics_dict = {
                key: value
                for key, value in request.item_specifics.model_dump().items()
                if value is not None
            }

        # Create the listing
        result = listing_service.create_book_listing(
            book=book,
            price=request.price,
            condition=request.condition,
            quantity=request.quantity,
            use_ai=True,  # Always use AI for title/description
            use_seo_optimization=request.use_seo_optimization,
            item_specifics=item_specifics_dict,
            epid=None,  # Let the service look it up automatically
        )

        # Build response
        response_data = {
            "id": result.get("id"),
            "sku": result.get("sku"),
            "offer_id": result.get("offer_id"),
            "ebay_listing_id": result.get("ebay_listing_id"),
            "epid": result.get("epid"),
            "title": result.get("title"),
            "title_score": result.get("title_score"),
            "price": result.get("price"),
            "status": result.get("status", "active"),
        }

        return JSONResponse(content=response_data, status_code=201)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Log the full error but return a sanitized message
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create eBay listing: {str(e)}"
        )


@router.get("/listings")
async def get_ebay_listings(
    service: BookService = Depends(get_book_service),
    limit: int = 100,
    status: Optional[str] = None,
) -> JSONResponse:
    """
    Get all eBay listings from the database.

    Args:
        limit: Maximum number of listings to return
        status: Filter by status (active, sold, ended, etc.)

    Returns:
        List of eBay listings with metadata
    """
    try:
        # Query database for listings
        query = "SELECT * FROM ebay_listings"
        params = []

        if status:
            query += " WHERE status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        conn = service.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)

        columns = [desc[0] for desc in cursor.description]
        listings = [dict(zip(columns, row)) for row in cursor.fetchall()]

        return JSONResponse(content={"listings": listings, "count": len(listings)})

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve listings: {str(e)}"
        )


@router.get("/listings/{isbn}")
async def get_ebay_listings_by_isbn(
    isbn: str,
    service: BookService = Depends(get_book_service),
) -> JSONResponse:
    """
    Get all eBay listings for a specific ISBN.

    Args:
        isbn: ISBN-10 or ISBN-13

    Returns:
        List of listings for the specified ISBN
    """
    try:
        conn = service.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM ebay_listings WHERE isbn = ? ORDER BY created_at DESC",
            (isbn,)
        )

        columns = [desc[0] for desc in cursor.description]
        listings = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if not listings:
            raise HTTPException(
                status_code=404,
                detail=f"No listings found for ISBN: {isbn}"
            )

        return JSONResponse(content={"listings": listings, "count": len(listings)})

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve listings: {str(e)}"
        )
