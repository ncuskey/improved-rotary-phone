"""eBay listing content generator using Ollama LLM.

This module provides AI-powered generation of eBay listing titles and descriptions
for books and lots. It uses local Llama 3.1 8B model via Ollama for fast, private
content generation.

Example usage:
    from isbn_lot_optimizer.ai import EbayListingGenerator
    from isbn_lot_optimizer.service import BookService

    service = BookService(db_path)
    book = service.get_book("9780553381702")

    generator = EbayListingGenerator()
    listing = generator.generate_book_listing(
        book=book,
        condition="Good",
        price=15.99
    )

    print(listing.title)
    print(listing.description)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import requests

from shared.models import BookEvaluation, BookMetadata, LotSuggestion

logger = logging.getLogger(__name__)


class GenerationError(Exception):
    """Raised when AI generation fails."""
    pass


@dataclass
class ListingContent:
    """Generated eBay listing content."""

    title: str
    description: str
    highlights: List[str]
    shipping_notes: Optional[str] = None
    condition_notes: Optional[str] = None
    model_used: str = "llama3.1:8b"
    generation_time_ms: Optional[int] = None
    title_score: Optional[float] = None  # SEO score if using keyword optimization
    keyword_scores: Optional[List[Dict[str, Any]]] = None  # Keyword rankings if using SEO


class EbayListingGenerator:
    """Generate eBay listing content using Ollama LLM."""

    def __init__(
        self,
        model: str = "llama3.1:8b",
        ollama_url: str = "http://localhost:11434",
        timeout: int = 30,
    ):
        """
        Initialize the listing generator.

        Args:
            model: Ollama model name (default: llama3.1:8b)
            ollama_url: Ollama API base URL
            timeout: Request timeout in seconds
        """
        self.model = model
        self.ollama_url = ollama_url
        self.timeout = timeout

    def _call_ollama(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Call Ollama API to generate text.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt for instruction tuning

        Returns:
            Generated text

        Raises:
            GenerationError: If the API call fails
        """
        url = f"{self.ollama_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "top_k": 40,
            },
        }

        if system_prompt:
            payload["system"] = system_prompt

        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama API call failed: {e}")
            raise GenerationError(f"Failed to generate content: {e}") from e

    def generate_book_listing(
        self,
        book: BookEvaluation,
        condition: str = "Good",
        price: Optional[float] = None,
        custom_notes: Optional[str] = None,
        use_seo_optimization: bool = False,
        isbn: Optional[str] = None,
    ) -> ListingContent:
        """
        Generate eBay listing content for a single book.

        Args:
            book: Book evaluation with metadata and market data
            condition: Book condition (Good, Very Good, Like New, etc.)
            price: Listing price (if None, uses estimated_price)
            custom_notes: Additional notes to include in description
            use_seo_optimization: If True, use keyword-ranked SEO title generation
            isbn: ISBN for keyword analysis (if use_seo_optimization=True)

        Returns:
            ListingContent with title, description, and highlights

        Raises:
            GenerationError: If generation fails
        """
        metadata = book.metadata
        market = book.market
        listing_price = price or book.estimated_price

        # Build context about the book
        book_info = {
            "title": metadata.title,
            "subtitle": metadata.subtitle,
            "authors": list(metadata.authors) if metadata.authors else [],
            "isbn": metadata.isbn,
            "published_year": metadata.published_year,
            "page_count": metadata.page_count,
            "description": metadata.description,
            "categories": list(metadata.categories) if metadata.categories else [],
            "condition": condition,
            "price": listing_price,
            "series": metadata.series_name,
            "series_index": metadata.series_index,
        }

        # Add market context if available
        if market:
            book_info["market_data"] = {
                "active_listings": market.active_count,
                "sold_count": market.sold_count,
                "median_price": market.sold_comps_median or market.sold_median_price,
            }

        # Generate title (use SEO optimization if requested)
        if use_seo_optimization:
            title_isbn = isbn or metadata.isbn
            if title_isbn:
                title, title_score, keyword_scores = self.generate_seo_title(
                    book_info, title_isbn
                )
                # Store keyword scores for later use
                book_info["keyword_scores"] = keyword_scores
                book_info["title_score"] = title_score
            else:
                logger.warning("SEO optimization requested but no ISBN provided, using standard title")
                title = self._generate_title(book_info)
        else:
            title = self._generate_title(book_info)

        # Generate description
        description = self._generate_description(book_info, custom_notes)

        # Extract highlights
        highlights = self._extract_highlights(book_info)

        return ListingContent(
            title=title,
            description=description,
            highlights=highlights,
            model_used=self.model,
            title_score=book_info.get("title_score"),
            keyword_scores=book_info.get("keyword_scores"),
        )

    def generate_lot_listing(
        self,
        lot: LotSuggestion,
        books: Sequence[BookEvaluation],
        condition: str = "Good",
        price: Optional[float] = None,
        custom_notes: Optional[str] = None,
    ) -> ListingContent:
        """
        Generate eBay listing content for a book lot.

        Args:
            lot: Lot suggestion with strategy and metadata
            books: Books in the lot
            condition: Average condition of books
            price: Listing price (if None, uses estimated_value)
            custom_notes: Additional notes to include in description

        Returns:
            ListingContent with title, description, and highlights

        Raises:
            GenerationError: If generation fails
        """
        listing_price = price or lot.estimated_value

        # Build context about the lot
        lot_info = {
            "name": lot.name,
            "strategy": lot.strategy,
            "num_books": len(books),
            "condition": condition,
            "price": listing_price,
            "author": lot.canonical_author,
            "series": lot.canonical_series or lot.series_name,
            "books": [],
        }

        # Add individual book details
        for book in books:
            lot_info["books"].append({
                "title": book.metadata.title,
                "authors": list(book.metadata.authors) if book.metadata.authors else [],
                "isbn": book.metadata.isbn,
                "published_year": book.metadata.published_year,
                "series_index": book.metadata.series_index,
            })

        # Generate title
        title = self._generate_lot_title(lot_info)

        # Generate description
        description = self._generate_lot_description(lot_info, custom_notes)

        # Extract highlights
        highlights = self._extract_lot_highlights(lot_info)

        return ListingContent(
            title=title,
            description=description,
            highlights=highlights,
            model_used=self.model,
        )

    def generate_seo_title(
        self,
        book_info: Dict[str, Any],
        isbn: str,
        num_variations: int = 5,
    ) -> tuple[str, float, List[Dict[str, Any]]]:
        """
        Generate SEO-optimized title using keyword ranking analysis.

        This method generates multiple title variations and selects the one with
        the highest combined keyword score while maintaining readability.

        Args:
            book_info: Book information dict
            isbn: ISBN for keyword analysis
            num_variations: Number of title variations to generate (default: 5)

        Returns:
            Tuple of (best_title, title_score, keyword_scores)

        Raises:
            GenerationError: If generation fails
        """
        from isbn_lot_optimizer.keyword_analyzer import KeywordAnalyzer, calculate_title_score

        # Step 1: Analyze keywords for this ISBN
        logger.info(f"Analyzing keywords for ISBN {isbn}")
        analyzer = KeywordAnalyzer()
        keyword_scores = analyzer.analyze_keywords_for_isbn(isbn)

        if not keyword_scores:
            logger.warning(f"No keywords found for ISBN {isbn}, falling back to standard title")
            return self._generate_title(book_info), 0.0, []

        # Get top 30 keywords for prompt
        top_keywords = keyword_scores[:30]
        keywords_str = ", ".join([f"{kw.word} ({kw.score:.1f})" for kw in top_keywords[:15]])

        logger.info(f"Top keywords: {keywords_str}")

        # Step 2: Generate multiple title variations
        system_prompt = """You are an expert eBay SEO specialist creating keyword-optimized titles.

Your goal is to create titles that pack in high-scoring keywords while remaining readable.
These are SEO-style titles similar to what power sellers use on eBay.

Guidelines:
- Maximum 80 characters (strict eBay limit)
- Pack in as many high-scoring keywords as possible
- Keywords with higher scores are more valuable
- Maintain basic readability (can sacrifice perfect grammar)
- Front-load most important keywords
- Use title case for proper nouns
- No stop words (a, the, an) unless needed for clarity
- No punctuation except hyphens and pipes (|)
- Focus on search terms buyers actually use

Examples of good SEO titles:
- "Harry Potter Complete Set Hardcover Books Collection Fantasy Magic Series JK Rowling"
- "Game Thrones GRRM Martin Fantasy Epic Series Hardcover Books Collection Complete Set"
- "Storm Swords Martin Song Ice Fire Fantasy Epic Series Book Hardcover"""

        authors_str = ", ".join(book_info["authors"][:2])
        title = book_info["title"]
        series = book_info.get("series")
        series_index = book_info.get("series_index")

        prompt = f"""Generate {num_variations} different SEO-optimized eBay titles for this book.

Book Information:
- Title: {title}
- Authors: {authors_str}
{f"- Series: {series} #{series_index}" if series else ""}
- ISBN: {isbn}

Top Keywords (ranked by search value 1-10):
{keywords_str}

Instructions:
1. Create {num_variations} variations that use different combinations of keywords
2. Prioritize HIGH-SCORING keywords (scores above 7.0)
3. Each title must be under 80 characters
4. Make them readable but keyword-dense (SEO style)
5. Use different approaches (some with series focus, some with genre focus, etc.)

Return ONLY the {num_variations} titles, one per line, no numbering or quotes."""

        response = self._call_ollama(prompt, system_prompt)

        # Parse variations
        variations = [line.strip().strip('"').strip("'") for line in response.split("\n") if line.strip()]
        variations = [v for v in variations if len(v) <= 80 and len(v) > 10]

        if not variations:
            logger.warning("No valid title variations generated, falling back to standard title")
            return self._generate_title(book_info), 0.0, []

        logger.info(f"Generated {len(variations)} title variations")

        # Step 3: Score each variation
        scored_variations = []
        for variation in variations:
            score = calculate_title_score(variation, keyword_scores)
            scored_variations.append((variation, score))
            logger.debug(f"  {variation} -> Score: {score:.1f}")

        # Step 4: Select best title
        scored_variations.sort(key=lambda x: x[1], reverse=True)
        best_title, best_score = scored_variations[0]

        logger.info(f"Selected best title (score: {best_score:.1f}): {best_title}")

        # Convert keyword scores to serializable format
        keyword_data = [
            {
                "word": kw.word,
                "score": round(kw.score, 2),
                "frequency": kw.frequency,
                "avg_price": round(kw.avg_price, 2),
            }
            for kw in keyword_scores[:50]  # Store top 50
        ]

        return best_title, best_score, keyword_data

    def _generate_title(self, book_info: Dict[str, Any]) -> str:
        """Generate an SEO-friendly eBay listing title (max 80 characters)."""

        system_prompt = """You are an expert eBay listing optimizer specializing in books.
Your task is to create compelling, SEO-optimized titles that maximize visibility and click-through rates.

Guidelines:
- Maximum 80 characters (eBay limit)
- Include: Author, Title, and most important keywords
- Use abbreviations to save space (HC for Hardcover, PB for Paperback, 1st Ed for First Edition)
- Front-load most important keywords (author, title)
- Include series name and number if applicable
- Avoid stop words (the, a, an) when space is tight
- Use pipe separators (|) for clarity
- DO NOT include condition (shown separately on eBay)
- DO NOT include price
- Focus on searchability and professionalism"""

        # Build prompt with book details
        authors_str = ", ".join(book_info["authors"][:2])  # Max 2 authors for space
        title = book_info["title"]
        subtitle = book_info.get("subtitle")
        series = book_info.get("series")
        series_index = book_info.get("series_index")

        prompt = f"""Generate an eBay listing title for this book:

Title: {title}
{f"Subtitle: {subtitle}" if subtitle else ""}
Authors: {authors_str}
{f"Series: {series} #{series_index}" if series and series_index else ""}
ISBN: {book_info["isbn"]}
Published: {book_info.get("published_year", "Unknown")}

Return ONLY the title, no explanation or quotes."""

        title_text = self._call_ollama(prompt, system_prompt)

        # Clean and truncate to 80 chars
        title_text = title_text.strip().strip('"').strip("'")
        if len(title_text) > 80:
            title_text = title_text[:77] + "..."

        return title_text

    def _generate_description(
        self,
        book_info: Dict[str, Any],
        custom_notes: Optional[str] = None,
    ) -> str:
        """Generate an engaging eBay listing description."""

        system_prompt = """You are an expert eBay book seller creating compelling product descriptions.
Your descriptions should be professional, detailed, and buyer-focused.

Guidelines:
- Start with an attention-grabbing opening that highlights the book's appeal
- Include key details: author background, publication info, notable features
- Describe the book's content and themes (without spoilers)
- Mention any special features (series info, awards, popularity)
- Use bullet points for key facts
- Write in active voice, present tense
- Be honest about condition
- End with a call-to-action
- Keep it scannable and easy to read
- Aim for 200-400 words"""

        authors_str = ", ".join(book_info["authors"])
        title = book_info["title"]
        subtitle = book_info.get("subtitle")
        description = book_info.get("description", "")
        categories = ", ".join(book_info.get("categories", []))
        series = book_info.get("series")
        series_index = book_info.get("series_index")

        prompt = f"""Create an eBay listing description for this book:

Title: {title}
{f"Subtitle: {subtitle}" if subtitle else ""}
Authors: {authors_str}
{f"Series: {series} #{series_index}" if series and series_index else ""}
Published: {book_info.get("published_year", "Unknown")}
Pages: {book_info.get("page_count", "Unknown")}
Categories: {categories if categories else "Fiction"}
ISBN: {book_info["isbn"]}
Condition: {book_info["condition"]}

{f"Book Description: {description[:500]}" if description else ""}

{f"Special Notes: {custom_notes}" if custom_notes else ""}

Create a compelling listing description that will help sell this book.
Return ONLY the description, formatted with line breaks for readability."""

        description_text = self._call_ollama(prompt, system_prompt)

        return description_text.strip()

    def _generate_lot_title(self, lot_info: Dict[str, Any]) -> str:
        """Generate an SEO-friendly title for a book lot (max 80 characters)."""

        system_prompt = """You are an expert eBay listing optimizer for book lots.
Your task is to create compelling titles that highlight the lot's value proposition.

Guidelines:
- Maximum 80 characters
- Include: Number of books, author/series name, key theme
- Emphasize value ("Set of 5", "Complete Series", "Lot Bundle")
- Use abbreviations (HC, PB, Bks, Vol, Ser)
- Front-load most important info
- Use pipe separators for clarity
- Focus on searchability"""

        author = lot_info.get("author", "")
        series = lot_info.get("series", "")
        num_books = lot_info["num_books"]
        strategy = lot_info["strategy"]

        prompt = f"""Generate an eBay listing title for this book lot:

Number of Books: {num_books}
{f"Author: {author}" if author else ""}
{f"Series: {series}" if series else ""}
Strategy: {strategy}

Book Titles:
"""

        # Add first few book titles
        for i, book in enumerate(lot_info["books"][:5], 1):
            prompt += f"{i}. {book['title']}\n"

        if len(lot_info["books"]) > 5:
            prompt += f"... and {len(lot_info['books']) - 5} more\n"

        prompt += "\nReturn ONLY the title, no explanation or quotes."

        title_text = self._call_ollama(prompt, system_prompt)

        # Clean and truncate
        title_text = title_text.strip().strip('"').strip("'")
        if len(title_text) > 80:
            title_text = title_text[:77] + "..."

        return title_text

    def _generate_lot_description(
        self,
        lot_info: Dict[str, Any],
        custom_notes: Optional[str] = None,
    ) -> str:
        """Generate description for a book lot."""

        system_prompt = """You are an expert eBay book lot seller.
Create compelling descriptions that highlight the value of buying multiple books together.

Guidelines:
- Emphasize the lot's value proposition (save money, complete collection, etc.)
- List all books clearly with title and author
- Mention any series order or reading sequence
- Describe average condition
- Highlight any standout titles
- Use bullet points for the book list
- Be honest and detailed
- End with shipping and payment info
- Aim for 250-500 words"""

        author = lot_info.get("author", "")
        series = lot_info.get("series", "")
        num_books = lot_info["num_books"]

        prompt = f"""Create an eBay listing description for this book lot:

Number of Books: {num_books}
{f"Author: {author}" if author else ""}
{f"Series: {series}" if series else ""}
Condition: {lot_info["condition"]}
Price: ${lot_info["price"]:.2f} for the entire lot

Books included:
"""

        for i, book in enumerate(lot_info["books"], 1):
            authors_str = ", ".join(book["authors"])
            prompt += f"{i}. {book['title']} by {authors_str}"
            if book.get("series_index"):
                prompt += f" (Book {book['series_index']})"
            prompt += f" - ISBN: {book['isbn']}\n"

        if custom_notes:
            prompt += f"\nSpecial Notes: {custom_notes}\n"

        prompt += "\nCreate a compelling lot description. Return ONLY the description."

        description_text = self._call_ollama(prompt, system_prompt)

        return description_text.strip()

    def _extract_highlights(self, book_info: Dict[str, Any]) -> List[str]:
        """Extract key bullet points for item specifics."""

        highlights = []

        # Author
        if book_info["authors"]:
            authors_str = ", ".join(book_info["authors"][:2])
            highlights.append(f"Author: {authors_str}")

        # ISBN
        highlights.append(f"ISBN: {book_info['isbn']}")

        # Publication year
        if book_info.get("published_year"):
            highlights.append(f"Published: {book_info['published_year']}")

        # Pages
        if book_info.get("page_count"):
            highlights.append(f"Pages: {book_info['page_count']}")

        # Series
        if book_info.get("series") and book_info.get("series_index"):
            highlights.append(f"Series: {book_info['series']} #{book_info['series_index']}")

        # Condition
        highlights.append(f"Condition: {book_info['condition']}")

        return highlights

    def _extract_lot_highlights(self, lot_info: Dict[str, Any]) -> List[str]:
        """Extract key bullet points for lot specifics."""

        highlights = []

        # Number of books
        highlights.append(f"Number of Books: {lot_info['num_books']}")

        # Author/Series
        if lot_info.get("author"):
            highlights.append(f"Author: {lot_info['author']}")
        if lot_info.get("series"):
            highlights.append(f"Series: {lot_info['series']}")

        # Condition
        highlights.append(f"Condition: {lot_info['condition']}")

        # Value
        if lot_info.get("price"):
            per_book = lot_info["price"] / lot_info["num_books"]
            highlights.append(f"Price per book: ${per_book:.2f}")

        return highlights
