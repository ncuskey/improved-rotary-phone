from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass
class BookMetadata:
    isbn: str
    title: str = ""
    subtitle: Optional[str] = None
    authors: Tuple[str, ...] = tuple()
    credited_authors: Tuple[str, ...] = tuple()
    canonical_author: Optional[str] = None
    series: Optional[str] = None
    published_year: Optional[int] = None
    published_raw: Optional[str] = None
    page_count: Optional[int] = None
    categories: Tuple[str, ...] = tuple()
    average_rating: Optional[float] = None
    ratings_count: Optional[int] = None
    list_price: Optional[float] = None
    currency: Optional[str] = None
    info_link: Optional[str] = None
    thumbnail: Optional[str] = None
    description: Optional[str] = None
    identifiers: Tuple[str, ...] = tuple()
    # Extended normalized metadata fields (populated from metadata_json when available)
    categories_str: Optional[str] = None
    cover_url: Optional[str] = None
    series_name: Optional[str] = None
    series_index: Optional[int] = None
    series_id: Optional[str] = None
    source: str = "unknown"
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EbayMarketStats:
    isbn: str
    active_count: int
    active_avg_price: Optional[float]
    sold_count: int
    sold_avg_price: Optional[float]
    sell_through_rate: Optional[float]
    currency: Optional[str]
    active_median_price: Optional[float] = None
    sold_median_price: Optional[float] = None
    unsold_count: Optional[int] = None
    raw_active: Optional[Dict[str, Any]] = None
    raw_sold: Optional[Dict[str, Any]] = None


@dataclass
class BooksRunOffer:
    isbn: str
    condition: str
    cash_price: Optional[float] = None
    store_credit: Optional[float] = None
    currency: Optional[str] = None
    url: Optional[str] = None
    updated_at: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BookEvaluation:
    isbn: str
    original_isbn: str
    metadata: BookMetadata
    market: Optional[EbayMarketStats]
    estimated_price: float
    condition: str
    edition: Optional[str]
    rarity: Optional[float]
    probability_score: float
    probability_label: str
    justification: Sequence[str] = field(default_factory=list)
    suppress_single: bool = False
    quantity: int = 1
    booksrun: Optional[BooksRunOffer] = None
    booksrun_value_label: Optional[str] = None
    booksrun_value_ratio: Optional[float] = None


@dataclass
class LotSuggestion:
    name: str
    strategy: str
    book_isbns: Sequence[str]
    estimated_value: float
    probability_score: float
    probability_label: str
    sell_through: Optional[float]
    justification: Sequence[str] = field(default_factory=list)
    display_author_label: Optional[str] = None
    canonical_author: Optional[str] = None
    canonical_series: Optional[str] = None
    series_name: Optional[str] = None
    books: Sequence[BookEvaluation] = field(default_factory=tuple)


@dataclass
class LotCandidate:
    name: str
    strategy: str
    books: List[BookEvaluation]
    book_isbns: Sequence[str]
    author: Optional[str] = None
    series_name: Optional[str] = None
    canonical_author: Optional[str] = None
    canonical_series: Optional[str] = None
    series_have: Optional[int] = None
    series_expected: Optional[int] = None
    is_single_series: bool = False
    estimated_value: float = 0.0
    estimated_price: float = 0.0
    probability_score: float = 0.0
    probability_label: str = "Unknown"
    probability_reasons: str = ""
    sell_through: Optional[float] = None
    justification: Sequence[str] = field(default_factory=list)
    market_json: Optional[str] = None
    ebay_active_count: Optional[int] = None
    ebay_sold_count: Optional[int] = None
    display_author_label: Optional[str] = None
