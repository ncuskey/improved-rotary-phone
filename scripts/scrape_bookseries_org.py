#!/usr/bin/env python3
"""
Scraper for bookseries.org - extracts authors and their book series information.
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import sys
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urljoin


class BookSeriesScraper:
    """Scraper for bookseries.org website."""

    BASE_URL = "https://www.bookseries.org"
    AUTHORS_LIST_URL = f"{BASE_URL}/list-of-authors/"

    def __init__(self, delay: float = 1.0):
        """
        Initialize scraper.

        Args:
            delay: Delay in seconds between requests (be respectful to the server)
        """
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

    def get_all_authors(self) -> List[Dict[str, str]]:
        """
        Scrape the list of all authors from the main authors page.

        Returns:
            List of dictionaries containing author name and URL
        """
        print(f"Fetching authors list from {self.AUTHORS_LIST_URL}...")

        try:
            response = self.session.get(self.AUTHORS_LIST_URL)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Error fetching authors list: {e}")
            return []

        soup = BeautifulSoup(response.content, 'html.parser')
        authors = []

        # Find all author links - they typically appear in a list or content area
        # The links follow pattern: /authors/[author-name]/
        author_links = soup.find_all('a', href=lambda href: href and '/authors/' in href)

        seen_urls = set()
        for link in author_links:
            author_url = urljoin(self.BASE_URL, link['href'])

            # Skip duplicates
            if author_url in seen_urls:
                continue

            seen_urls.add(author_url)
            author_name = link.get_text(strip=True)

            if author_name:  # Only add if name is not empty
                authors.append({
                    'name': author_name,
                    'url': author_url
                })

        print(f"Found {len(authors)} authors")
        return authors

    def get_author_series(self, author_url: str, author_name: str) -> Optional[Dict]:
        """
        Scrape book series information for a specific author.

        Args:
            author_url: URL to the author's page
            author_name: Name of the author

        Returns:
            Dictionary containing author info and their series/books
        """
        print(f"Fetching series for {author_name}...")

        time.sleep(self.delay)  # Be respectful to the server

        try:
            response = self.session.get(author_url)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Error fetching {author_name}: {e}")
            return None

        soup = BeautifulSoup(response.content, 'html.parser')

        author_data = {
            'name': author_name,
            'url': author_url,
            'bio': '',
            'series': []
        }

        # Extract author bio if available
        # Usually in a paragraph near the top or in a specific div
        content_area = soup.find('div', class_='entry-content') or soup.find('article')
        if content_area:
            # Try to find the first few paragraphs as bio
            paragraphs = content_area.find_all('p', limit=3)
            bio_parts = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                # Stop if we hit a heading or series marker
                if text and not text.startswith('Order of') and not text.startswith('When Does'):
                    bio_parts.append(text)
            author_data['bio'] = ' '.join(bio_parts)

        # Find all h2 headings that contain series information
        # These typically start with "Order of" or contain "Series"
        headings = soup.find_all(['h2', 'h3'])

        for heading in headings:
            series_title = heading.get_text(strip=True)

            # Skip non-series headings
            skip_phrases = [
                'recent authors', 'recent author interviews', 'biography',
                'about', 'when does the next', 'thoughts on', 'leave a reply',
                'navigation', 'search', 'categories', 'archives'
            ]

            if any(phrase in series_title.lower() for phrase in skip_phrases):
                continue

            # Look for a table following this heading
            table = heading.find_next('table')

            if not table:
                continue

            # Parse the table to extract books
            books = []
            rows = table.find_all('tr')

            for row in rows[1:]:  # Skip header row
                cells = row.find_all(['td', 'th'])

                if len(cells) < 2:
                    continue

                # Extract book information from table cells
                # Typically: #, Read checkbox, Title, Published date, Details/Buy links
                book_info = {}

                # Try to find the title cell (usually has a link or is the longest text)
                for cell in cells:
                    text = cell.get_text(strip=True)

                    # Skip cells with just numbers, checkboxes, or short text
                    if not text or text.isdigit() or len(text) < 3:
                        continue

                    # Skip cells with just "Description / Buy" type text
                    if 'description' in text.lower() or text.lower() == 'buy':
                        continue

                    # Look for the title (usually a link or longest substantial text)
                    link = cell.find('a')
                    if link and len(link.get_text(strip=True)) > 5:
                        book_info['title'] = link.get_text(strip=True)
                        book_info['link'] = urljoin(self.BASE_URL, link.get('href', ''))
                        break
                    elif not book_info.get('title') and len(text) > 5:
                        book_info['title'] = text

                if book_info.get('title'):
                    books.append(book_info)

            if books:
                # Clean up series title (remove "Order of " prefix if present)
                clean_title = series_title
                if clean_title.lower().startswith('order of '):
                    clean_title = clean_title[9:]

                author_data['series'].append({
                    'title': clean_title,
                    'book_count': len(books),
                    'books': books
                })

        return author_data

    def scrape_all(self, limit: Optional[int] = None, output_file: str = 'bookseries_data.json') -> Dict:
        """
        Scrape all authors and their series information.

        Args:
            limit: Optional limit on number of authors to scrape (for testing)
            output_file: Path to save the JSON output

        Returns:
            Dictionary containing all scraped data
        """
        authors = self.get_all_authors()

        if not authors:
            print("No authors found!")
            return {'authors': []}

        if limit:
            authors = authors[:limit]
            print(f"Limiting to first {limit} authors for testing")

        data = {
            'source': self.BASE_URL,
            'total_authors': len(authors),
            'authors': []
        }

        for i, author in enumerate(authors, 1):
            print(f"[{i}/{len(authors)}] Processing {author['name']}...")

            author_data = self.get_author_series(author['url'], author['name'])
            if author_data:
                data['authors'].append(author_data)

            # Save progress periodically
            if i % 50 == 0:
                self._save_data(data, output_file)
                print(f"Progress saved to {output_file}")

        # Final save
        self._save_data(data, output_file)
        print(f"\nScraping complete! Data saved to {output_file}")
        print(f"Total authors scraped: {len(data['authors'])}")

        return data

    def _save_data(self, data: Dict, output_file: str):
        """Save data to JSON file."""
        output_path = Path(output_file)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Scrape authors and book series from bookseries.org'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of authors to scrape (for testing)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=1.0,
        help='Delay between requests in seconds (default: 1.0)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='bookseries_data.json',
        help='Output JSON file (default: bookseries_data.json)'
    )
    parser.add_argument(
        '--authors-only',
        action='store_true',
        help='Only scrape the authors list, not individual series'
    )

    args = parser.parse_args()

    scraper = BookSeriesScraper(delay=args.delay)

    if args.authors_only:
        # Just get the authors list
        authors = scraper.get_all_authors()
        data = {
            'source': scraper.BASE_URL,
            'total_authors': len(authors),
            'authors': authors
        }
        scraper._save_data(data, args.output)
        print(f"Authors list saved to {args.output}")
    else:
        # Full scrape
        scraper.scrape_all(limit=args.limit, output_file=args.output)


if __name__ == '__main__':
    main()
