"""
Data loader for platform-specific stacking models.

Loads training data split by platform availability:
- eBay: Books with sold_comps_median target
- AbeBooks: Books with abebooks_avg_price target
- Amazon: Books with amazon_lowest_price target
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.lot_detector import is_lot


class PlatformDataLoader:
    """Load and organize training data by platform."""

    def __init__(self):
        self.catalog_db = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'
        self.training_db = Path.home() / '.isbn_lot_optimizer' / 'training_data.db'  # Legacy, deprecated
        self.cache_db = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'  # NEW: Unified training DB

    def load_all_data(self) -> Dict[str, Tuple[List[dict], List[float]]]:
        """
        Load all platform-specific training data.

        Data sources (in priority order):
        1. Unified Training DB (metadata_cache.db with in_training=1)
        2. Catalog (catalog.db - recent scans)
        3. Legacy Training DB (training_data.db - deprecated)
        4. Amazon Pricing (metadata_cache.db amazon_pricing table)

        Returns:
            Dict mapping platform name to (book_records, targets) tuple:
            - 'ebay': Books with eBay sold comps
            - 'abebooks': Books with AbeBooks pricing
            - 'amazon': Books with Amazon pricing
        """
        print("=" * 80)
        print("LOADING PLATFORM-SPECIFIC TRAINING DATA")
        print("=" * 80)

        # Load raw data from all sources
        unified_training_books = self._load_unified_training_books()  # NEW: Primary source
        catalog_books = self._load_catalog_books()
        training_books = self._load_training_books()  # Legacy
        cache_books = self._load_cache_books()  # Amazon pricing

        print(f"\nRaw data loaded:")
        print(f"  Unified Training DB: {len(unified_training_books)} books (in_training=1)")
        print(f"  Catalog:             {len(catalog_books)} books")
        print(f"  Legacy Training:     {len(training_books)} books")
        print(f"  Amazon Pricing:      {len(cache_books)} books")

        # Organize by platform
        ebay_data = []
        abebooks_data = []
        amazon_data = []
        biblio_data = []
        alibris_data = []
        zvab_data = []

        # Process unified training books (NEW: Primary source)
        for book in unified_training_books:
            # Apply lot detection
            if book.get('metadata') and 'title' in book['metadata']:
                if is_lot(book['metadata']['title']):
                    continue

            # Categorize by available target
            if book.get('ebay_target'):
                ebay_data.append((book, book['ebay_target']))

            if book.get('abebooks_target'):
                abebooks_data.append((book, book['abebooks_target']))

            if book.get('amazon_target'):
                amazon_data.append((book, book['amazon_target']))

            if book.get('biblio_target'):
                biblio_data.append((book, book['biblio_target']))

            if book.get('alibris_target'):
                alibris_data.append((book, book['alibris_target']))

            if book.get('zvab_target'):
                zvab_data.append((book, book['zvab_target']))

        # Process catalog books
        for book in catalog_books:
            # Apply lot detection
            if book.get('metadata') and 'title' in book['metadata']:
                if is_lot(book['metadata']['title']):
                    continue

            # Categorize by available target
            if book.get('ebay_target'):
                ebay_data.append((book, book['ebay_target']))

            if book.get('abebooks_target'):
                abebooks_data.append((book, book['abebooks_target']))

            if book.get('amazon_target'):
                amazon_data.append((book, book['amazon_target']))

            # NEW: BookFinder vendor targets
            if book.get('biblio_target'):
                biblio_data.append((book, book['biblio_target']))

            if book.get('alibris_target'):
                alibris_data.append((book, book['alibris_target']))

            if book.get('zvab_target'):
                zvab_data.append((book, book['zvab_target']))

        # Process training books (eBay only)
        for book in training_books:
            if book.get('metadata') and 'title' in book['metadata']:
                if is_lot(book['metadata']['title']):
                    continue

            if book.get('ebay_target'):
                ebay_data.append((book, book['ebay_target']))

        # Process cache books (Amazon only)
        for book in cache_books:
            if book.get('metadata') and 'title' in book['metadata']:
                if is_lot(book['metadata']['title']):
                    continue

            if book.get('amazon_target'):
                amazon_data.append((book, book['amazon_target']))

        print(f"\nPlatform-specific data after lot filtering:")
        print(f"  eBay:     {len(ebay_data)} books")
        print(f"  AbeBooks: {len(abebooks_data)} books")
        print(f"  Amazon:   {len(amazon_data)} books")
        print(f"  Biblio:   {len(biblio_data)} books")
        print(f"  Alibris:  {len(alibris_data)} books")
        print(f"  Zvab:     {len(zvab_data)} books")

        # Split into records and targets
        ebay_records = [record for record, _ in ebay_data]
        ebay_targets = [target for _, target in ebay_data]

        abebooks_records = [record for record, _ in abebooks_data]
        abebooks_targets = [target for _, target in abebooks_data]

        amazon_records = [record for record, _ in amazon_data]
        amazon_targets = [target for _, target in amazon_data]

        biblio_records = [record for record, _ in biblio_data]
        biblio_targets = [target for _, target in biblio_data]

        alibris_records = [record for record, _ in alibris_data]
        alibris_targets = [target for _, target in alibris_data]

        zvab_records = [record for record, _ in zvab_data]
        zvab_targets = [target for _, target in zvab_data]

        return {
            'ebay': (ebay_records, ebay_targets),
            'abebooks': (abebooks_records, abebooks_targets),
            'amazon': (amazon_records, amazon_targets),
            'biblio': (biblio_records, biblio_targets),
            'alibris': (alibris_records, alibris_targets),
            'zvab': (zvab_records, zvab_targets),
        }

    def _load_catalog_books(self) -> List[dict]:
        """Load books from catalog.db."""
        if not self.catalog_db.exists():
            print(f"Warning: {self.catalog_db} not found")
            return []

        conn = sqlite3.connect(self.catalog_db)
        cursor = conn.cursor()

        query = """
        SELECT
            isbn,
            metadata_json,
            market_json,
            bookscouter_json,
            condition,
            sold_comps_median,
            json_extract(bookscouter_json, '$.amazon_lowest_price') as amazon_price,
            cover_type,
            signed,
            printing,
            abebooks_min_price,
            abebooks_avg_price,
            abebooks_seller_count,
            abebooks_condition_spread,
            abebooks_has_new,
            abebooks_has_used,
            abebooks_hardcover_premium
        FROM books
        WHERE bookscouter_json IS NOT NULL
        ORDER BY updated_at DESC
        """

        cursor.execute(query)
        rows = cursor.fetchall()
        # Don't close conn yet - need it for BookFinder queries below

        books = []
        for row in rows:
            (isbn, metadata_json, market_json, bookscouter_json, condition,
             sold_comps_median, amazon_price, cover_type, signed, printing,
             abebooks_min, abebooks_avg, abebooks_count, abebooks_spread,
             abebooks_has_new, abebooks_has_used, abebooks_hc_premium) = row

            # Parse JSONs
            metadata_dict = json.loads(metadata_json) if metadata_json else {}
            market_dict = json.loads(market_json) if market_json else {}
            bookscouter_dict = json.loads(bookscouter_json) if bookscouter_json else {}

            # Build AbeBooks dict
            abebooks_dict = None
            if abebooks_min or abebooks_avg or abebooks_count:
                abebooks_dict = {
                    'abebooks_min_price': abebooks_min,
                    'abebooks_avg_price': abebooks_avg,
                    'abebooks_seller_count': abebooks_count,
                    'abebooks_condition_spread': abebooks_spread,
                    'abebooks_has_new': abebooks_has_new,
                    'abebooks_has_used': abebooks_has_used,
                    'abebooks_hardcover_premium': abebooks_hc_premium,
                }

            # Determine targets for each platform
            book = {
                'isbn': isbn,
                'metadata': metadata_dict,
                'market': market_dict,
                'bookscouter': bookscouter_dict,
                'condition': condition or 'Good',
                'cover_type': cover_type,
                'signed': signed,
                'printing': printing,
                'abebooks': abebooks_dict,
            }

            # eBay target: sold_comps_median
            if sold_comps_median and sold_comps_median > 0:
                book['ebay_target'] = sold_comps_median

            # AbeBooks target: abebooks_avg_price
            if abebooks_avg and abebooks_avg > 0:
                book['abebooks_target'] = abebooks_avg

            # Amazon target: amazon_lowest_price
            if amazon_price and float(amazon_price) > 0:
                book['amazon_target'] = float(amazon_price)

            books.append(book)

        # NOW: Query BookFinder vendor prices and augment book records
        print("\n  Querying BookFinder vendor prices...")
        for book in books:
            isbn = book['isbn']

            # Query minimum prices for each vendor from BookFinder
            cursor = conn.cursor()
            cursor.execute("""
                SELECT vendor, MIN(price + COALESCE(shipping, 0)) as min_price
                FROM bookfinder_offers
                WHERE isbn = ?
                GROUP BY vendor
            """, (isbn,))

            vendor_prices = {row[0]: row[1] for row in cursor.fetchall()}

            # Add BookFinder vendor targets (augments existing models + creates new ones)
            if 'eBay' in vendor_prices and vendor_prices['eBay'] > 0:
                # Augment existing eBay model with BookFinder eBay data
                if 'ebay_target' not in book or not book['ebay_target']:
                    book['ebay_target'] = vendor_prices['eBay']

            if 'AbeBooks' in vendor_prices and vendor_prices['AbeBooks'] > 0:
                # Augment existing AbeBooks model
                if 'abebooks_target' not in book or not book['abebooks_target']:
                    book['abebooks_target'] = vendor_prices['AbeBooks']

            if 'Amazon_Usa' in vendor_prices and vendor_prices['Amazon_Usa'] > 0:
                # Augment existing Amazon model
                if 'amazon_target' not in book or not book['amazon_target']:
                    book['amazon_target'] = vendor_prices['Amazon_Usa']

            # NEW: Add targets for new vendor models
            if 'Biblio' in vendor_prices and vendor_prices['Biblio'] > 0:
                book['biblio_target'] = vendor_prices['Biblio']

            if 'Alibris' in vendor_prices and vendor_prices['Alibris'] > 0:
                book['alibris_target'] = vendor_prices['Alibris']

            if 'Zvab' in vendor_prices and vendor_prices['Zvab'] > 0:
                book['zvab_target'] = vendor_prices['Zvab']

        conn.close()
        return books

    def _load_training_books(self) -> List[dict]:
        """Load books from training_data.db (eBay sold comps)."""
        if not self.training_db.exists():
            print(f"Warning: {self.training_db} not found")
            return []

        conn = sqlite3.connect(self.training_db)
        cursor = conn.cursor()

        query = """
        SELECT
            isbn,
            metadata_json,
            market_json,
            bookscouter_json,
            sold_avg_price,
            sold_median_price,
            sold_count,
            cover_type,
            signed,
            printing
        FROM training_books
        WHERE sold_avg_price IS NOT NULL
          AND sold_count >= 5
        """

        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        books = []
        for row in rows:
            (isbn, metadata_json, market_json, bookscouter_json,
             sold_avg, sold_median, sold_count,
             cover_type, signed, printing) = row

            # Parse JSONs
            metadata_dict = json.loads(metadata_json) if metadata_json else {}
            market_dict = json.loads(market_json) if market_json else {}
            bookscouter_dict = json.loads(bookscouter_json) if bookscouter_json else {}

            book = {
                'isbn': isbn,
                'metadata': metadata_dict,
                'market': market_dict,
                'bookscouter': bookscouter_dict,
                'condition': 'Good',
                'cover_type': cover_type,
                'signed': signed,
                'printing': printing,
                'abebooks': None,
                'ebay_target': sold_median if sold_median else sold_avg,
            }

            books.append(book)

        return books

    def _load_unified_training_books(self) -> List[dict]:
        """
        Load books from unified training database (metadata_cache.db with in_training=1).

        This is the NEW primary source for training data, containing high-quality
        books that meet quality gates:
        - in_training = 1
        - sold_comps_count >= 8
        - sold_comps_median >= $5
        - training_quality_score >= 0.6
        """
        if not self.cache_db.exists():
            print(f"Warning: {self.cache_db} not found")
            return []

        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()

        query = """
        SELECT
            isbn,
            title,
            authors,
            publisher,
            publication_year,
            binding,
            page_count,
            sold_comps_median,
            market_json,
            bookscouter_json,
            cover_type,
            signed,
            printing,
            training_quality_score
        FROM cached_books
        WHERE in_training = 1
          AND sold_comps_count >= 8
          AND sold_comps_median >= 5
        ORDER BY training_quality_score DESC
        """

        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        books = []
        for row in rows:
            (isbn, title, authors, publisher, pub_year, binding, page_count,
             sold_comps_median, market_json, bookscouter_json,
             cover_type, signed, printing, training_quality_score) = row

            # Parse JSONs
            market_dict = json.loads(market_json) if market_json else {}
            bookscouter_dict = json.loads(bookscouter_json) if bookscouter_json else {}

            # Build metadata dict
            metadata_dict = {
                'title': title,
                'authors': authors,
                'publisher': publisher,
                'published_year': pub_year,
                'page_count': page_count,
                'binding': binding,
            }

            book = {
                'isbn': isbn,
                'metadata': metadata_dict,
                'market': market_dict,
                'bookscouter': bookscouter_dict,
                'condition': 'Good',
                'cover_type': cover_type,
                'signed': signed,
                'printing': printing,
                'abebooks': None,
                'ebay_target': sold_comps_median,
                'training_quality_score': training_quality_score,
            }

            books.append(book)

        return books

    def _load_cache_books(self) -> List[dict]:
        """Load books from metadata_cache.db (Amazon pricing)."""
        if not self.cache_db.exists():
            print(f"Warning: {self.cache_db} not found")
            return []

        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()

        query = """
        SELECT
            c.isbn,
            c.title,
            c.authors,
            c.publisher,
            c.publication_year,
            c.binding,
            c.page_count,
            p.median_used_good,
            p.median_used_very_good,
            p.offer_count
        FROM cached_books c
        JOIN amazon_pricing p ON c.isbn = p.isbn
        WHERE p.median_used_good IS NOT NULL
           OR p.median_used_very_good IS NOT NULL
        """

        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        books = []
        for row in rows:
            (isbn, title, authors, publisher, pub_year, binding, page_count,
             price_good, price_vg, offer_count) = row

            # Create minimal metadata
            metadata_dict = {
                'title': title,
                'authors': authors,
                'publisher': publisher,
                'published_year': pub_year,
                'page_count': page_count,
            }

            # Use Good condition price, fallback to Very Good
            target_price = price_good if price_good and price_good > 0 else price_vg

            if target_price and target_price > 0:
                book = {
                    'isbn': isbn,
                    'metadata': metadata_dict,
                    'market': {},
                    'bookscouter': {},
                    'condition': 'Good',
                    'cover_type': binding,
                    'signed': False,
                    'printing': None,
                    'abebooks': None,
                    'amazon_target': target_price,
                }
                books.append(book)

        return books


def load_platform_training_data() -> Dict[str, Tuple[List[dict], List[float]]]:
    """
    Convenience function to load all platform-specific training data.

    Returns:
        Dict mapping platform name to (book_records, targets):
        - 'ebay': Books with eBay sold comps (target: sold_comps_median)
        - 'abebooks': Books with AbeBooks pricing (target: abebooks_avg_price)
        - 'amazon': Books with Amazon pricing (target: amazon_lowest_price)
    """
    loader = PlatformDataLoader()
    return loader.load_all_data()


if __name__ == "__main__":
    # Test the data loader
    print("\n" + "=" * 80)
    print("TESTING PLATFORM DATA LOADER")
    print("=" * 80)

    data = load_platform_training_data()

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for platform, (records, targets) in data.items():
        print(f"\n{platform.upper()}:")
        print(f"  Records: {len(records)}")
        print(f"  Targets: {len(targets)}")
        if targets:
            print(f"  Target range: ${min(targets):.2f} - ${max(targets):.2f}")
            print(f"  Target mean: ${sum(targets) / len(targets):.2f}")

    print("\n" + "=" * 80)
