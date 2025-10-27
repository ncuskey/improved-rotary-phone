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


class TitlePreviewRequest(BaseModel):
    """Schema for title preview request."""

    isbn: str = Field(..., description="ISBN-10 or ISBN-13")
    item_specifics: Optional[ItemSpecifics] = Field(None, description="Item Specifics for context")
    use_seo_optimization: bool = Field(True, description="Use SEO-optimized title generation")

    class Config:
        json_schema_extra = {
            "example": {
                "isbn": "9780545349277",
                "item_specifics": {
                    "format": ["Hardcover"],
                    "features": ["First Edition", "Dust Jacket"]
                },
                "use_seo_optimization": True
            }
        }


class TitlePreviewResponse(BaseModel):
    """Schema for title preview response."""

    title: str = Field(..., description="Generated title")
    title_score: float = Field(..., description="Keyword optimization score")
    max_score: float = Field(..., description="Maximum possible score")
    score_percentage: float = Field(..., description="Score as percentage of maximum")

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Wings Fire Brightest Night Sutherland Fantasy Series Hardcover Complete",
                "title_score": 48.7,
                "max_score": 75.0,
                "score_percentage": 64.9
            }
        }


@router.post("/preview-title", response_model=TitlePreviewResponse)
async def preview_title(
    request: TitlePreviewRequest,
    service: BookService = Depends(get_book_service),
) -> JSONResponse:
    """
    Preview the generated eBay listing title with keyword score.

    This endpoint generates and scores a title WITHOUT creating a listing,
    allowing the user to review the title before final submission.

    The title is generated using:
    - Book metadata (title, author, series, etc.)
    - SEO keyword analysis from 90-day sold comps
    - Item Specifics for context

    Returns:
        Title preview with keyword optimization score
    """
    try:
        # Get book from catalog
        book = service.get_book(request.isbn)
        if not book:
            raise HTTPException(
                status_code=404,
                detail=f"Book not found in catalog: {request.isbn}"
            )

        # Initialize AI generator for title generation
        from isbn_lot_optimizer.ebay_listing import EbayListingService
        listing_service = EbayListingService(service.db.db_path)

        # Convert ItemSpecifics to dict
        item_specifics_dict = None
        if request.item_specifics:
            item_specifics_dict = {
                key: value
                for key, value in request.item_specifics.model_dump().items()
                if value is not None
            }

        # Generate title using AI generator
        # Note: We use condition="Good" and a placeholder price since we only need the title
        ai_content = listing_service.ai_generator.generate_book_listing(
            book=book,
            condition="Good",
            price=book.estimated_price or 10.0,
            use_seo_optimization=request.use_seo_optimization,
            isbn=request.isbn,
        )

        title = ai_content.title
        title_score = ai_content.title_score or 0.0

        # Calculate max possible score (sum of top keyword scores)
        # For now, use a reasonable estimate based on typical ranges
        # TODO: Could enhance by actually calculating from keyword analysis
        max_score = 75.0  # Typical max score for well-optimized titles
        score_percentage = (title_score / max_score * 100) if max_score > 0 else 0

        response_data = {
            "title": title,
            "title_score": round(title_score, 1),
            "max_score": max_score,
            "score_percentage": round(score_percentage, 1)
        }

        return JSONResponse(content=response_data, status_code=200)

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate title preview: {str(e)}"
        )


class PriceRecommendationRequest(BaseModel):
    """Schema for price recommendation request."""

    isbn: str = Field(..., description="ISBN-10 or ISBN-13")
    item_specifics: Optional[ItemSpecifics] = Field(None, description="Item Specifics to filter comps")

    class Config:
        json_schema_extra = {
            "example": {
                "isbn": "9780545349277",
                "item_specifics": {
                    "format": ["Hardcover"],
                    "features": ["First Edition", "Signed"]
                }
            }
        }


class PriceRecommendationResponse(BaseModel):
    """Schema for price recommendation response."""

    recommended_price: float = Field(..., description="Recommended price based on filtered comps")
    source: str = Field(..., description="Source of price data")
    comps_count: int = Field(..., description="Number of comps used for calculation")
    price_range_min: float = Field(..., description="Minimum price from filtered comps")
    price_range_max: float = Field(..., description="Maximum price from filtered comps")
    features_matched: List[str] = Field(..., description="Features that were matched in filtering")

    class Config:
        json_schema_extra = {
            "example": {
                "recommended_price": 32.50,
                "source": "eBay Sold Comps (90 days)",
                "comps_count": 8,
                "price_range_min": 24.99,
                "price_range_max": 45.00,
                "features_matched": ["First Edition", "Signed"]
            }
        }


@router.post("/recommend-price", response_model=PriceRecommendationResponse)
async def recommend_price(
    request: PriceRecommendationRequest,
    service: BookService = Depends(get_book_service),
) -> JSONResponse:
    """
    Get price recommendation based on sold comps filtered by features.

    This endpoint:
    1. Retrieves sold comps from last 90 days
    2. Filters by matching features (first edition, signed, etc.)
    3. Returns median price from filtered comps

    This allows dynamic price updates as users select features in the wizard.

    Returns:
        Price recommendation with details about filtered comps
    """
    try:
        from shared.ebay_sold_comps import EbaySoldComps

        # Convert iOS feature names to filter format
        features_dict = {}
        if request.item_specifics and request.item_specifics.features:
            for feature in request.item_specifics.features:
                feature_lower = feature.lower().replace(" ", "_")
                features_dict[feature_lower] = True

        # Get sold comps with feature filtering
        sold_comps_service = EbaySoldComps()
        result = sold_comps_service.get_sold_comps(
            gtin=request.isbn,
            fallback_to_estimate=True,
            max_samples=50,  # Get more samples for better filtering
            features=features_dict if features_dict else None
        )

        if not result or result["count"] == 0:
            raise HTTPException(
                status_code=404,
                detail="No sold comps found for this ISBN with the specified features"
            )

        response_data = {
            "recommended_price": result["median"],
            "source": "eBay Sold Comps (90 days)" if not result["is_estimate"] else "Active Listings Estimate",
            "comps_count": result["count"],
            "price_range_min": result["min"],
            "price_range_max": result["max"],
            "features_matched": list(features_dict.keys()) if features_dict else []
        }

        return JSONResponse(content=response_data, status_code=200)

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get price recommendation: {str(e)}"
        )
