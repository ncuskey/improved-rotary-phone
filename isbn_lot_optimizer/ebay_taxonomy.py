"""eBay Taxonomy API integration for Item Aspects validation.

This module provides access to eBay's Taxonomy API to discover required and
recommended Item Specifics (aspects) for listing categories. It helps ensure
our listings include all necessary aspects for optimal search visibility.

Key features:
- Fetch required/optional aspects for Books category (377)
- Cache aspect requirements to avoid repeated API calls
- Validate aspect values against eBay's requirements
- Provide aspect metadata (data types, allowed values, cardinality)

Usage:
    from isbn_lot_optimizer.ebay_taxonomy import EbayTaxonomyClient

    client = EbayTaxonomyClient()

    # Get aspect requirements for Books category
    aspects = client.get_category_aspects("377")

    # Check if an aspect is required
    if client.is_aspect_required("377", "Author"):
        print("Author is a required field")

    # Validate aspects before creating listing
    errors = client.validate_aspects("377", {
        "Author": ["Stephen King"],
        "Format": ["Hardcover"],
        "Language": ["English"]
    })
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

import requests

logger = logging.getLogger(__name__)


# Cache for taxonomy data (24-hour TTL)
_taxonomy_cache: Dict[str, tuple[Any, float]] = {}
_TAXONOMY_CACHE_TTL = 86400  # 24 hours


@dataclass
class AspectConstraint:
    """Constraints for an Item Aspect."""
    aspect_required: bool
    aspect_data_type: str  # STRING, NUMBER, DATE, etc.
    aspect_mode: str  # FREE_TEXT or SELECTION_ONLY
    cardinality: str  # SINGLE or MULTI
    aspect_enabled_for_variations: bool


@dataclass
class AspectMetadata:
    """Metadata for an Item Aspect."""
    name: str
    constraint: AspectConstraint
    allowed_values: Optional[List[str]] = None  # For SELECTION_ONLY aspects
    relevance_score: Optional[float] = None


class EbayTaxonomyClient:
    """Client for eBay Taxonomy API to fetch and validate Item Aspects."""

    # eBay Taxonomy API endpoints
    TAXONOMY_API_URL = "https://api.ebay.com/commerce/taxonomy/v1"

    # Books category ID (Fiction & Nonfiction Books under Books category)
    BOOKS_CATEGORY_ID = "377"

    def __init__(
        self,
        token_broker_url: str = "http://localhost:8787",
        marketplace_id: str = "EBAY_US",
    ):
        """
        Initialize the Taxonomy API client.

        Args:
            token_broker_url: URL of OAuth token broker
            marketplace_id: eBay marketplace ID (default: EBAY_US)
        """
        self.token_broker_url = token_broker_url
        self.marketplace_id = marketplace_id

        # Category tree ID for US marketplace
        self.category_tree_id = "0"  # 0 = US, 3 = UK, etc.

    def _get_app_token(self) -> str:
        """Get application OAuth token."""
        from shared.market import get_app_token
        return get_app_token()

    def get_category_aspects(
        self,
        category_id: str = BOOKS_CATEGORY_ID,
        use_cache: bool = True,
    ) -> List[AspectMetadata]:
        """
        Get Item Aspects for a category.

        Args:
            category_id: eBay category ID (default: 377 for Books)
            use_cache: Whether to use cached results

        Returns:
            List of AspectMetadata objects
        """
        # Check cache
        if use_cache:
            cache_key = f"aspects:{category_id}"
            now = time.time()
            if cache_key in _taxonomy_cache:
                cached_result, expires_at = _taxonomy_cache[cache_key]
                if expires_at > now:
                    logger.debug(f"Using cached aspects for category {category_id}")
                    return cached_result

        logger.info(f"Fetching Item Aspects for category {category_id}")

        token = self._get_app_token()
        url = f"{self.TAXONOMY_API_URL}/category_tree/{self.category_tree_id}/get_item_aspects_for_category"

        try:
            response = requests.get(
                url,
                params={"category_id": category_id},
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
                },
                timeout=30,
            )

            if response.status_code != 200:
                logger.error(f"Taxonomy API error: {response.status_code}")
                return []

            data = response.json()
            aspects = self._parse_aspects_response(data)

            # Cache result
            if use_cache:
                cache_key = f"aspects:{category_id}"
                _taxonomy_cache[cache_key] = (aspects, time.time() + _TAXONOMY_CACHE_TTL)

            logger.info(f"Retrieved {len(aspects)} aspects for category {category_id}")
            return aspects

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch aspects: {e}")
            return []

    def _parse_aspects_response(self, data: Dict[str, Any]) -> List[AspectMetadata]:
        """Parse eBay Taxonomy API response into AspectMetadata objects."""
        aspects = []

        for aspect_data in data.get("aspects", []):
            name = aspect_data.get("localizedAspectName", "")
            if not name:
                continue

            constraint_data = aspect_data.get("aspectConstraint", {})

            constraint = AspectConstraint(
                aspect_required=constraint_data.get("aspectRequired", False),
                aspect_data_type=constraint_data.get("aspectDataType", "STRING"),
                aspect_mode=constraint_data.get("aspectMode", "FREE_TEXT"),
                cardinality=constraint_data.get("itemToAspectCardinality", "SINGLE"),
                aspect_enabled_for_variations=constraint_data.get("aspectEnabledForVariations", False),
            )

            # Extract allowed values for SELECTION_ONLY aspects
            allowed_values = None
            if constraint.aspect_mode == "SELECTION_ONLY":
                aspect_values = aspect_data.get("aspectValues", [])
                allowed_values = [
                    val.get("localizedValue")
                    for val in aspect_values
                    if val.get("localizedValue")
                ]

            aspects.append(
                AspectMetadata(
                    name=name,
                    constraint=constraint,
                    allowed_values=allowed_values,
                )
            )

        return aspects

    def is_aspect_required(
        self,
        category_id: str,
        aspect_name: str,
    ) -> bool:
        """
        Check if an aspect is required for a category.

        Args:
            category_id: eBay category ID
            aspect_name: Name of the aspect

        Returns:
            True if required, False otherwise
        """
        aspects = self.get_category_aspects(category_id)

        for aspect in aspects:
            if aspect.name.lower() == aspect_name.lower():
                return aspect.constraint.aspect_required

        return False

    def get_required_aspects(
        self,
        category_id: str = BOOKS_CATEGORY_ID,
    ) -> List[str]:
        """
        Get list of required aspect names for a category.

        Args:
            category_id: eBay category ID (default: 377 for Books)

        Returns:
            List of required aspect names
        """
        aspects = self.get_category_aspects(category_id)
        return [
            aspect.name
            for aspect in aspects
            if aspect.constraint.aspect_required
        ]

    def validate_aspects(
        self,
        category_id: str,
        aspects: Dict[str, List[str]],
    ) -> List[str]:
        """
        Validate aspects against eBay requirements.

        Args:
            category_id: eBay category ID
            aspects: Dict mapping aspect names to values

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Get aspect requirements
        aspect_metadata = self.get_category_aspects(category_id)
        metadata_by_name = {m.name.lower(): m for m in aspect_metadata}

        # Check required aspects
        for metadata in aspect_metadata:
            if metadata.constraint.aspect_required:
                if metadata.name not in aspects or not aspects[metadata.name]:
                    errors.append(f"Required aspect missing: {metadata.name}")

        # Validate provided aspects
        for aspect_name, values in aspects.items():
            metadata = metadata_by_name.get(aspect_name.lower())
            if not metadata:
                # Aspect not recognized (but may still be valid)
                continue

            # Check cardinality
            if metadata.constraint.cardinality == "SINGLE" and len(values) > 1:
                errors.append(f"{aspect_name} accepts only one value")

            # Check selection-only aspects
            if metadata.constraint.aspect_mode == "SELECTION_ONLY":
                if metadata.allowed_values:
                    for value in values:
                        if value not in metadata.allowed_values:
                            errors.append(
                                f"{aspect_name}: '{value}' not in allowed values"
                            )

        return errors

    def clear_cache(self) -> None:
        """Clear the taxonomy cache."""
        _taxonomy_cache.clear()
        logger.info("Taxonomy cache cleared")


# Pre-defined fallback aspects for Books category (if API fails)
# Based on common eBay Books Item Specifics
FALLBACK_BOOK_ASPECTS = {
    "required": [
        "Author",
        "Format",
        "Language",
        "Publication Year",
    ],
    "recommended": [
        "Publisher",
        "Book Title",
        "Number of Pages",
        "Genre",
        "Book Series",
        "Narrative Type",
        "Special Attributes",
        "Features",
        "Intended Audience",
    ],
}
