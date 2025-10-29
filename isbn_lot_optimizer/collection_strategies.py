"""
Collection strategies for strategic ML training data gathering.

Defines target book categories, search strategies, and filtering logic
for finding high-quality training examples on eBay.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class CollectionTarget:
    """
    Definition of a collection target category.

    Attributes:
        category: Unique identifier (e.g., 'signed_hardcover')
        description: Human-readable description
        target_count: How many books to collect in this category
        min_comps: Minimum eBay sold listings required
        priority: Collection priority (1=highest, 4=lowest)
        search_keywords: eBay search keywords
        price_min: Minimum price filter (USD)
        price_max: Maximum price filter (USD)
        additional_filters: Extra eBay Browse API filters
    """
    category: str
    description: str
    target_count: int
    min_comps: int
    priority: int
    search_keywords: List[str]
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    additional_filters: Optional[Dict] = None


# Collection target definitions
# Total: 2000+ books targeting critical gaps and high-quality examples
COLLECTION_TARGETS = [
    # ===================================================================
    # PRIORITY 1: Critical Feature Gaps (850 books)
    # ===================================================================

    CollectionTarget(
        category='signed_hardcover',
        description='Signed/autographed hardcover books',
        target_count=200,
        min_comps=10,
        priority=1,
        search_keywords=[
            'signed first edition hardcover',
            'autographed book hardcover',
            'signed by author hardcover',
            'inscribed first edition'
        ],
        price_min=15.0,
        price_max=200.0,
        additional_filters={'itemFilter': [{'name': 'Condition', 'value': ['New', 'Like New', 'Very Good']}]}
    ),

    CollectionTarget(
        category='first_edition_hardcover',
        description='First edition hardcover books (non-signed)',
        target_count=400,
        min_comps=10,
        priority=1,
        search_keywords=[
            'first edition hardcover',
            '1st edition hardcover',
            'first printing hardcover',
            'first edition stated hardcover'
        ],
        price_min=10.0,
        price_max=150.0,
        additional_filters={}
    ),

    CollectionTarget(
        category='mass_market_paperback',
        description='Mass market paperback editions',
        target_count=150,
        min_comps=10,
        priority=1,
        search_keywords=[
            'mass market paperback',
            'pocket book paperback',
            'mass market edition',
            'paperback vintage mass market'
        ],
        price_min=3.0,
        price_max=20.0,
        additional_filters={}
    ),

    CollectionTarget(
        category='trade_paperback',
        description='Trade paperback (standard paperback format)',
        target_count=100,
        min_comps=15,
        priority=1,
        search_keywords=[
            'trade paperback',
            'paperback fiction',
            'paperback nonfiction',
            'softcover book'
        ],
        price_min=5.0,
        price_max=30.0,
        additional_filters={}
    ),

    # ===================================================================
    # PRIORITY 2: Quality & Diversity (650 books)
    # ===================================================================

    CollectionTarget(
        category='premium_collectible',
        description='High-value collectible books ($30-100)',
        target_count=150,
        min_comps=10,
        priority=2,
        search_keywords=[
            'collectible book',
            'rare book',
            'limited edition book',
            'collector edition hardcover'
        ],
        price_min=30.0,
        price_max=100.0,
        additional_filters={'itemFilter': [{'name': 'Condition', 'value': ['New', 'Like New', 'Very Good']}]}
    ),

    CollectionTarget(
        category='fiction_hardcover',
        description='Popular fiction hardcovers (bestsellers)',
        target_count=300,
        min_comps=15,
        priority=2,
        search_keywords=[
            'hardcover fiction bestseller',
            'novel hardcover',
            'thriller hardcover',
            'mystery hardcover'
        ],
        price_min=8.0,
        price_max=40.0,
        additional_filters={'categoryId': '377'}  # Fiction category
    ),

    CollectionTarget(
        category='textbook_various',
        description='Textbooks (various subjects and conditions)',
        target_count=200,
        min_comps=10,
        priority=2,
        search_keywords=[
            'college textbook',
            'university textbook',
            'science textbook',
            'computer science textbook'
        ],
        price_min=10.0,
        price_max=80.0,
        additional_filters={'categoryId': '2228'}  # Textbooks category
    ),

    # ===================================================================
    # PRIORITY 3: Breadth & Coverage (500 books)
    # ===================================================================

    CollectionTarget(
        category='vintage_classics',
        description='Vintage and classic literature',
        target_count=150,
        min_comps=8,
        priority=3,
        search_keywords=[
            'vintage book',
            'classic literature',
            'vintage hardcover',
            'antique book'
        ],
        price_min=8.0,
        price_max=60.0,
        additional_filters={}
    ),

    CollectionTarget(
        category='nonfiction_hardcover',
        description='Nonfiction hardcovers (history, biography, science)',
        target_count=200,
        min_comps=12,
        priority=3,
        search_keywords=[
            'hardcover nonfiction',
            'biography hardcover',
            'history book hardcover',
            'science book hardcover'
        ],
        price_min=8.0,
        price_max=50.0,
        additional_filters={'categoryId': '378'}  # Nonfiction category
    ),

    CollectionTarget(
        category='children_illustrated',
        description='Children\'s books and illustrated editions',
        target_count=100,
        min_comps=10,
        priority=3,
        search_keywords=[
            'children book hardcover',
            'illustrated children book',
            'picture book hardcover',
            'kids book hardcover'
        ],
        price_min=5.0,
        price_max=35.0,
        additional_filters={'categoryId': '279'}  # Children's Books category
    ),

    CollectionTarget(
        category='graphic_novels',
        description='Graphic novels and comic compilations',
        target_count=50,
        min_comps=10,
        priority=3,
        search_keywords=[
            'graphic novel hardcover',
            'comic book collection',
            'manga graphic novel',
            'graphic novel paperback'
        ],
        price_min=8.0,
        price_max=40.0,
        additional_filters={}
    ),
]


class CollectionStrategyManager:
    """
    Manage collection strategies and target tracking.

    Provides methods to select targets, generate search queries,
    and track collection progress.
    """

    def __init__(self):
        """Initialize collection strategy manager."""
        self.targets = {t.category: t for t in COLLECTION_TARGETS}

    def get_target(self, category: str) -> Optional[CollectionTarget]:
        """Get target definition by category."""
        return self.targets.get(category)

    def get_all_targets(self) -> List[CollectionTarget]:
        """Get all collection targets."""
        return list(self.targets.values())

    def get_targets_by_priority(self, priority: int) -> List[CollectionTarget]:
        """Get all targets with given priority."""
        return [t for t in COLLECTION_TARGETS if t.priority == priority]

    def get_active_targets(self, completed_categories: set) -> List[CollectionTarget]:
        """
        Get targets that still need collection.

        Args:
            completed_categories: Set of category names already completed

        Returns:
            List of targets not yet completed, sorted by priority
        """
        active = [t for t in COLLECTION_TARGETS if t.category not in completed_categories]
        return sorted(active, key=lambda t: (t.priority, t.category))

    def build_ebay_search_query(self, target: CollectionTarget) -> Dict:
        """
        Build eBay Browse API search query for a target.

        Args:
            target: CollectionTarget to build query for

        Returns:
            Dict containing search parameters for eBay Browse API
        """
        query_parts = []

        # Use first keyword as primary query
        if target.search_keywords:
            query_parts.append(target.search_keywords[0])

        # Build filter string for eBay Browse API
        filters = []

        # Price filter
        if target.price_min is not None and target.price_max is not None:
            filters.append(f'price:[{target.price_min}..{target.price_max}]')
        elif target.price_min is not None:
            filters.append(f'price:[{target.price_min}..]')
        elif target.price_max is not None:
            filters.append(f'price:[..{target.price_max}]')

        # Condition filter (only new, like new, very good, good - avoid poor/acceptable)
        filters.append('conditionIds:{1000|1500|2000|3000}')  # New, Like New, Very Good, Good

        # Category filter
        category_id = None
        if target.additional_filters and 'categoryId' in target.additional_filters:
            category_id = target.additional_filters['categoryId']

        # Buy It Now only (skip auctions)
        filters.append('buyingOptions:{FIXED_PRICE}')

        # Only items with sold listings
        filters.append('deliveryCountry:US')

        return {
            'q': ' '.join(query_parts),
            'filter': ','.join(filters) if filters else None,
            'category_ids': category_id,
            'limit': 50,  # Max results per request
            'sort': 'price',  # Sort by price to get variety
        }

    def get_alternate_keywords(self, target: CollectionTarget, used_keywords: set) -> Optional[str]:
        """
        Get alternate search keyword for target.

        Args:
            target: CollectionTarget
            used_keywords: Set of keywords already used

        Returns:
            Next unused keyword, or None if all exhausted
        """
        for keyword in target.search_keywords:
            if keyword not in used_keywords:
                return keyword
        return None

    def estimate_api_calls(self, target: CollectionTarget) -> int:
        """
        Estimate eBay API calls needed for target.

        Args:
            target: CollectionTarget

        Returns:
            Estimated number of eBay Browse API calls
        """
        # Each keyword search = 1 call
        # Fetching item details = 1 call per item
        # Fetching sold history (via Finding API) = 1 call per item
        # Assume we need to examine 2-3x target_count to find enough with min_comps
        items_to_examine = target.target_count * 2.5

        api_calls = (
            len(target.search_keywords) +  # Search calls
            items_to_examine * 2  # Details + sold history per item
        )

        return int(api_calls)

    def get_total_target_count(self) -> int:
        """Get total number of books targeted across all categories."""
        return sum(t.target_count for t in COLLECTION_TARGETS)

    def get_category_stats(self) -> Dict:
        """Get statistics about collection targets."""
        return {
            'total_categories': len(COLLECTION_TARGETS),
            'total_target_count': self.get_total_target_count(),
            'by_priority': {
                priority: sum(t.target_count for t in COLLECTION_TARGETS if t.priority == priority)
                for priority in {1, 2, 3, 4}
            },
            'estimated_api_calls': sum(self.estimate_api_calls(t) for t in COLLECTION_TARGETS)
        }
