"""eBay Sell API client for creating and managing listings.

This module provides a Python client for the eBay Sell APIs (Inventory and Offer).
It integrates with the token broker for OAuth authentication and provides methods
for creating inventory items, publishing offers, and tracking listings.

Example usage:
    from isbn_lot_optimizer.ebay_sell import EbaySellClient
    from isbn_lot_optimizer.service import BookService

    # Initialize
    client = EbaySellClient()
    service = BookService(db_path)

    # Get a book
    book = service.get_book("9780553381702")

    # Create inventory and offer
    sku = client.create_book_inventory(book, condition="GOOD")
    offer_id = client.publish_offer(sku, price=15.99, quantity=1)

    print(f"✓ Listed on eBay: SKU={sku}, Offer ID={offer_id}")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from shared.models import BookEvaluation, LotSuggestion

logger = logging.getLogger(__name__)


class EbaySellError(Exception):
    """Raised when eBay Sell API returns an error."""
    pass


@dataclass
class InventoryItem:
    """eBay inventory item."""
    sku: str
    product_title: str
    product_description: str
    condition: str
    availability: Dict[str, Any]
    product_identifiers: Optional[List[Dict[str, str]]] = None


@dataclass
class Offer:
    """eBay offer (published listing)."""
    offer_id: str
    sku: str
    marketplace_id: str
    format: str
    listing_description: str
    listing_policies: Dict[str, str]
    price: Dict[str, str]
    quantity_limit_per_buyer: int
    available_quantity: int
    category_id: str
    merchant_location_key: str


class EbaySellClient:
    """Client for eBay Sell APIs (Inventory and Offer)."""

    def __init__(
        self,
        token_broker_url: str = "http://localhost:8787",
        marketplace_id: str = "EBAY_US",
        merchant_location_key: str = "default_location",
        timeout: int = 30,
    ):
        """
        Initialize the eBay Sell API client.

        Args:
            token_broker_url: URL of the token broker service
            marketplace_id: eBay marketplace (default: EBAY_US)
            merchant_location_key: Merchant location key for inventory
            timeout: Request timeout in seconds
        """
        self.token_broker_url = token_broker_url
        self.marketplace_id = marketplace_id
        self.merchant_location_key = merchant_location_key
        self.timeout = timeout

        # eBay Sell API base URLs
        self.inventory_api_url = "https://api.ebay.com/sell/inventory/v1"
        self.offer_api_url = "https://api.ebay.com/sell/inventory/v1"

    def _get_user_token(self) -> str:
        """Get user OAuth token from token broker."""
        url = f"{self.token_broker_url}/token/ebay-user"
        params = {"scopes": "sell.inventory,sell.fulfillment,sell.marketing"}

        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data["access_token"]
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get user token: {e}")
            raise EbaySellError(f"Failed to get OAuth token: {e}") from e

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Make an authenticated request to eBay Sell API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., "/inventory_item/SKU123")
            data: Request body (for POST/PUT)
            params: Query parameters

        Returns:
            API response as dict

        Raises:
            EbaySellError: If the request fails
        """
        token = self._get_user_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        url = f"{self.inventory_api_url}{endpoint}"

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params,
                timeout=self.timeout,
            )

            # Log rate limiting info
            if "X-RateLimit-Remaining" in response.headers:
                remaining = response.headers["X-RateLimit-Remaining"]
                logger.debug(f"eBay rate limit remaining: {remaining}")

            # Handle success
            if response.status_code in (200, 201, 204):
                if response.content:
                    return response.json()
                return {}

            # Handle errors
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("errors", [{}])[0].get("message", "Unknown error")

            raise EbaySellError(
                f"eBay API error {response.status_code}: {error_msg}\n"
                f"Details: {error_data}"
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise EbaySellError(f"Request failed: {e}") from e

    # ========================================================================
    # Inventory API Methods
    # ========================================================================

    def create_inventory_item(
        self,
        sku: str,
        product: Dict[str, Any],
        condition: str,
        availability: Dict[str, Any],
    ) -> None:
        """
        Create or update an inventory item on eBay.

        Args:
            sku: Stock keeping unit (unique identifier)
            product: Product details (title, description, identifiers)
            condition: Item condition (e.g., "NEW", "LIKE_NEW", "VERY_GOOD", "GOOD")
            availability: Availability details (ship-to-location-availability)

        Raises:
            EbaySellError: If creation fails
        """
        endpoint = f"/inventory_item/{sku}"

        payload = {
            "product": product,
            "condition": condition,
            "availability": availability,
        }

        logger.info(f"Creating inventory item: {sku}")
        self._make_request("PUT", endpoint, data=payload)
        logger.info(f"✓ Created inventory item: {sku}")

    def create_book_inventory(
        self,
        book: BookEvaluation,
        condition: str = "GOOD",
        quantity: int = 1,
    ) -> str:
        """
        Create an inventory item for a book.

        Args:
            book: Book evaluation with metadata
            condition: Book condition
            quantity: Available quantity

        Returns:
            SKU of the created inventory item

        Raises:
            EbaySellError: If creation fails
        """
        # Generate SKU (use ISBN as basis)
        sku = f"BOOK-{book.metadata.isbn}-{int(time.time())}"

        # Build product payload
        product = {
            "title": book.metadata.title,
            "description": book.metadata.description or "Book in good condition",
            "aspects": {
                "Author": [", ".join(book.metadata.authors)] if book.metadata.authors else ["Unknown"],
                "Format": ["Paperback"],  # TODO: Get from metadata
                "Language": ["English"],
                "Publication Year": [str(book.metadata.published_year)] if book.metadata.published_year else [],
            },
            "imageUrls": [book.metadata.thumbnail] if book.metadata.thumbnail else [],
        }

        # Add ISBN if available
        if book.metadata.isbn:
            product["isbn"] = [book.metadata.isbn]

        # Availability
        availability = {
            "shipToLocationAvailability": {
                "quantity": quantity,
            }
        }

        # Map condition
        condition_map = {
            "New": "NEW",
            "Like New": "LIKE_NEW",
            "Very Good": "VERY_GOOD",
            "Good": "GOOD",
            "Acceptable": "ACCEPTABLE",
        }
        ebay_condition = condition_map.get(condition, "GOOD")

        self.create_inventory_item(sku, product, ebay_condition, availability)

        return sku

    def get_inventory_item(self, sku: str) -> Dict[str, Any]:
        """
        Get an inventory item by SKU.

        Args:
            sku: Stock keeping unit

        Returns:
            Inventory item details

        Raises:
            EbaySellError: If retrieval fails
        """
        endpoint = f"/inventory_item/{sku}"
        return self._make_request("GET", endpoint)

    def delete_inventory_item(self, sku: str) -> None:
        """
        Delete an inventory item.

        Args:
            sku: Stock keeping unit

        Raises:
            EbaySellError: If deletion fails
        """
        endpoint = f"/inventory_item/{sku}"
        self._make_request("DELETE", endpoint)
        logger.info(f"✓ Deleted inventory item: {sku}")

    # ========================================================================
    # Offer API Methods
    # ========================================================================

    def create_offer(
        self,
        sku: str,
        marketplace_id: str,
        format: str,
        price: float,
        quantity: int,
        category_id: str,
        listing_description: str,
        listing_policies: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Create an offer for an inventory item.

        Args:
            sku: Stock keeping unit
            marketplace_id: eBay marketplace (e.g., "EBAY_US")
            format: Listing format ("FIXED_PRICE" or "AUCTION")
            price: Listing price
            quantity: Available quantity
            category_id: eBay category ID
            listing_description: Listing description
            listing_policies: Policy IDs (fulfillment, payment, return)

        Returns:
            Offer ID

        Raises:
            EbaySellError: If creation fails
        """
        endpoint = "/offer"

        payload = {
            "sku": sku,
            "marketplaceId": marketplace_id,
            "format": format,
            "availableQuantity": quantity,
            "categoryId": category_id,
            "listingDescription": listing_description,
            "listingPolicies": listing_policies or {},
            "pricingSummary": {
                "price": {
                    "value": str(price),
                    "currency": "USD",
                },
            },
            "quantityLimitPerBuyer": 1,
            "merchantLocationKey": self.merchant_location_key,
        }

        logger.info(f"Creating offer for SKU: {sku}")
        response = self._make_request("POST", endpoint, data=payload)
        offer_id = response.get("offerId")

        if not offer_id:
            raise EbaySellError(f"No offer ID returned: {response}")

        logger.info(f"✓ Created offer: {offer_id}")
        return offer_id

    def publish_offer(self, offer_id: str) -> None:
        """
        Publish an offer (make it live on eBay).

        Args:
            offer_id: Offer ID

        Raises:
            EbaySellError: If publishing fails
        """
        endpoint = f"/offer/{offer_id}/publish"

        logger.info(f"Publishing offer: {offer_id}")
        response = self._make_request("POST", endpoint)

        listing_id = response.get("listingId")
        if listing_id:
            logger.info(f"✓ Published offer: {offer_id}, Listing ID: {listing_id}")
        else:
            logger.warning(f"Offer published but no listing ID returned: {response}")

    def get_offer(self, offer_id: str) -> Dict[str, Any]:
        """
        Get an offer by ID.

        Args:
            offer_id: Offer ID

        Returns:
            Offer details

        Raises:
            EbaySellError: If retrieval fails
        """
        endpoint = f"/offer/{offer_id}"
        return self._make_request("GET", endpoint)

    def delete_offer(self, offer_id: str) -> None:
        """
        Delete an offer.

        Args:
            offer_id: Offer ID

        Raises:
            EbaySellError: If deletion fails
        """
        endpoint = f"/offer/{offer_id}"
        self._make_request("DELETE", endpoint)
        logger.info(f"✓ Deleted offer: {offer_id}")

    # ========================================================================
    # High-Level Methods
    # ========================================================================

    def create_and_publish_book_listing(
        self,
        book: BookEvaluation,
        price: float,
        condition: str = "GOOD",
        quantity: int = 1,
        category_id: str = "377",  # Books category
        listing_description: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Create inventory, create offer, and publish listing in one call.

        Args:
            book: Book evaluation
            price: Listing price
            condition: Book condition
            quantity: Available quantity
            category_id: eBay category ID (default: 377 for Books)
            listing_description: Optional custom description

        Returns:
            Dict with sku, offer_id, and listing_id

        Raises:
            EbaySellError: If any step fails
        """
        # Step 1: Create inventory
        sku = self.create_book_inventory(book, condition, quantity)

        # Step 2: Create offer
        description = listing_description or book.metadata.description or book.metadata.title

        offer_id = self.create_offer(
            sku=sku,
            marketplace_id=self.marketplace_id,
            format="FIXED_PRICE",
            price=price,
            quantity=quantity,
            category_id=category_id,
            listing_description=description,
        )

        # Step 3: Publish offer
        self.publish_offer(offer_id)

        return {
            "sku": sku,
            "offer_id": offer_id,
            "listing_id": None,  # Would need to retrieve from publish response
        }
