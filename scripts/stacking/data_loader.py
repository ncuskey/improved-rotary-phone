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
        bookfinder_books = self._load_bookfinder_books()  # NEW: BookFinder vendor pricing

        print(f"\nRaw data loaded:")
        print(f"  Unified Training DB: {len(unified_training_books)} books (in_training=1)")
        print(f"  Catalog:             {len(catalog_books)} books")
        print(f"  Legacy Training:     {len(training_books)} books")
        print(f"  Amazon Pricing:      {len(cache_books)} books")
        print(f"  BookFinder Vendors:  {len(bookfinder_books)} books")

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

        # Process cache books (Amazon and eBay sold_comps)
        for book in cache_books:
            if book.get('metadata') and 'title' in book['metadata']:
                if is_lot(book['metadata']['title']):
                    continue

            if book.get('amazon_target'):
                amazon_data.append((book, book['amazon_target']))

            if book.get('ebay_target'):
                ebay_data.append((book, book['ebay_target']))

        # Process BookFinder vendor books (NEW: AbeBooks, Alibris, Biblio, Zvab)
        for book in bookfinder_books:
            if book.get('metadata') and 'title' in book['metadata']:
                if is_lot(book['metadata']['title']):
                    continue

            if book.get('abebooks_target'):
                abebooks_data.append((book, book['abebooks_target']))

            if book.get('alibris_target'):
                alibris_data.append((book, book['alibris_target']))

            if book.get('biblio_target'):
                biblio_data.append((book, book['biblio_target']))

            if book.get('zvab_target'):
                zvab_data.append((book, book['zvab_target']))

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
        Load books from unified training database (metadata_cache.db with enriched market data).

        This is the NEW primary source for training data, containing books
        enriched with eBay market data:
        - last_enrichment_at IS NOT NULL (has been enriched)
        - sold_comps_count >= 1 (has at least 1 comp)
        - sold_comps_median >= $3 (reasonable minimum price)
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
            sold_comps_count,
            abebooks_enr_count,
            abebooks_enr_min,
            abebooks_enr_median,
            abebooks_enr_avg,
            abebooks_enr_max,
            abebooks_enr_spread,
            abebooks_enr_has_new,
            abebooks_enr_has_used,
            abebooks_enr_hc_premium,
            last_enrichment_at,
            market_fetched_at,
            amazon_fbm_collected_at,
            abebooks_enr_collected_at
        FROM cached_books
        WHERE last_enrichment_at IS NOT NULL
          AND sold_comps_count >= 5
          AND sold_comps_median >= 3
        ORDER BY sold_comps_count DESC, sold_comps_median DESC
        """

        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        books = []
        for row in rows:
            (isbn, title, authors, publisher, pub_year, binding, page_count,
             sold_comps_median, market_json, bookscouter_json,
             cover_type, signed, printing, sold_comps_count,
             abe_enr_count, abe_enr_min, abe_enr_median, abe_enr_avg,
             abe_enr_max, abe_enr_spread, abe_enr_has_new, abe_enr_has_used,
             abe_enr_hc_premium, last_enrichment_at, market_fetched_at,
             amazon_fbm_collected_at, abebooks_enr_collected_at) = row

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

            # Build AbeBooks enriched dict (if data available)
            abebooks_dict = None
            if abe_enr_count and abe_enr_count > 0:
                abebooks_dict = {
                    'abebooks_min_price': abe_enr_min,
                    'abebooks_avg_price': abe_enr_avg,
                    'abebooks_seller_count': abe_enr_count,
                    'abebooks_condition_spread': abe_enr_spread,
                    'abebooks_has_new': abe_enr_has_new,
                    'abebooks_has_used': abe_enr_has_used,
                    'abebooks_hardcover_premium': abe_enr_hc_premium,
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
                'abebooks': abebooks_dict,
                'ebay_target': sold_comps_median,
                'sold_comps_count': sold_comps_count,
                # Timestamps for temporal weighting
                'timestamp': market_fetched_at or last_enrichment_at,  # Prefer market_fetched (most complete)
                'ebay_timestamp': last_enrichment_at,
                'amazon_timestamp': amazon_fbm_collected_at,
                'abebooks_timestamp': abebooks_enr_collected_at,
            }

            # Add AbeBooks target if enriched data available
            if abe_enr_median and abe_enr_median > 0:
                book['abebooks_target'] = abe_enr_median
                book['abebooks_price_type'] = 'listing'  # AbeBooks = asking prices

            # Mark eBay target as SOLD price (ground truth)
            if sold_comps_median:
                book['ebay_price_type'] = 'sold'

            books.append(book)

        return books

    def _load_cache_books(self) -> List[dict]:
        """Load books from metadata_cache.db (Amazon pricing + FBM data + eBay sold comps)."""
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
            p.offer_count,
            c.amazon_fbm_count,
            c.amazon_fbm_min,
            c.amazon_fbm_median,
            c.amazon_fbm_max,
            c.amazon_fbm_avg_rating,
            c.sold_comps_count,
            c.sold_comps_min,
            c.sold_comps_median,
            c.sold_comps_max,
            c.amazon_fbm_collected_at,
            c.last_enrichment_at,
            c.market_fetched_at
        FROM cached_books c
        LEFT JOIN amazon_pricing p ON c.isbn = p.isbn
        WHERE (p.median_used_good IS NOT NULL OR p.median_used_very_good IS NOT NULL)
           OR c.amazon_fbm_median IS NOT NULL
           OR c.sold_comps_median IS NOT NULL
        """

        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        books = []
        for row in rows:
            (isbn, title, authors, publisher, pub_year, binding, page_count,
             price_good, price_vg, offer_count,
             fbm_count, fbm_min, fbm_median, fbm_max, fbm_avg_rating,
             sold_comps_count, sold_comps_min, sold_comps_median, sold_comps_max,
             amazon_fbm_collected_at, last_enrichment_at, market_fetched_at) = row

            # Create minimal metadata
            metadata_dict = {
                'title': title,
                'authors': authors,
                'publisher': publisher,
                'published_year': pub_year,
                'page_count': page_count,
            }

            # Build Amazon FBM dict if data available
            amazon_fbm_dict = None
            if fbm_median or fbm_count:
                amazon_fbm_dict = {
                    'amazon_fbm_count': fbm_count,
                    'amazon_fbm_min': fbm_min,
                    'amazon_fbm_median': fbm_median,
                    'amazon_fbm_max': fbm_max,
                    'amazon_fbm_avg_rating': fbm_avg_rating,
                }

            # Build eBay sold_comps dict if data available
            sold_comps_dict = None
            if sold_comps_median or sold_comps_count:
                sold_comps_dict = {
                    'sold_comps_count': sold_comps_count,
                    'sold_comps_min': sold_comps_min,
                    'sold_comps_median': sold_comps_median,
                    'sold_comps_max': sold_comps_max,
                }

            # Determine targets for each platform
            amazon_target = None
            ebay_target = None

            # Amazon: Use FBM median as primary target, fallback to old pricing
            if fbm_median and fbm_median > 0:
                amazon_target = fbm_median
            elif price_good and price_good > 0:
                amazon_target = price_good
            elif price_vg and price_vg > 0:
                amazon_target = price_vg

            # eBay: Use sold_comps_median as target
            if sold_comps_median and sold_comps_median > 0:
                ebay_target = sold_comps_median

            # Add book if it has at least one valid target
            if amazon_target or ebay_target:
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
                    'amazon_fbm': amazon_fbm_dict,
                    'sold_comps': sold_comps_dict,
                    # Timestamps for temporal weighting
                    'timestamp': market_fetched_at or amazon_fbm_collected_at or last_enrichment_at,
                    'amazon_timestamp': amazon_fbm_collected_at,
                    'ebay_timestamp': last_enrichment_at,
                }

                if amazon_target:
                    book['amazon_target'] = amazon_target
                    book['amazon_price_type'] = 'listing'  # Amazon FBM = listed prices
                if ebay_target:
                    book['ebay_target'] = ebay_target
                    book['ebay_price_type'] = 'sold'  # eBay sold comps = actual sales

                books.append(book)

        return books

    def _load_bookfinder_books(self) -> List[dict]:
        """
        Load books from BookFinder vendor pricing (catalog.db bookfinder_offers).

        Similar to _load_cache_books(), this queries bookfinder_offers for vendor pricing
        and joins with metadata_cache.db for book metadata.
        """
        if not self.catalog_db.exists():
            print(f"Warning: {self.catalog_db} not found")
            return []

        if not self.cache_db.exists():
            print(f"Warning: {self.cache_db} not found")
            return []

        # Connect to catalog.db for BookFinder offers
        catalog_conn = sqlite3.connect(self.catalog_db)

        # Query vendor pricing: MIN(price + shipping) per ISBN per vendor
        catalog_cursor = catalog_conn.cursor()
        catalog_cursor.execute("""
            SELECT
                isbn,
                vendor,
                MIN(price + COALESCE(shipping, 0)) as min_price
            FROM bookfinder_offers
            GROUP BY isbn, vendor
            HAVING min_price > 0
        """)

        # Build dict: isbn -> {vendor: price}
        isbn_vendor_prices = {}
        for row in catalog_cursor.fetchall():
            isbn, vendor, price = row
            if isbn not in isbn_vendor_prices:
                isbn_vendor_prices[isbn] = {}
            isbn_vendor_prices[isbn][vendor] = price

        catalog_conn.close()

        # Now query metadata for these ISBNs from metadata_cache.db
        cache_conn = sqlite3.connect(self.cache_db)
        cache_cursor = cache_conn.cursor()

        # Get metadata for ISBNs that have BookFinder offers
        books = []
        for isbn, vendor_prices in isbn_vendor_prices.items():
            # Query metadata for this ISBN
            cache_cursor.execute("""
                SELECT
                    title,
                    authors,
                    publisher,
                    publication_year,
                    binding,
                    page_count
                FROM cached_books
                WHERE isbn = ?
            """, (isbn,))

            row = cache_cursor.fetchone()
            if not row:
                continue  # Skip ISBNs without metadata

            title, authors, publisher, pub_year, binding, page_count = row

            # Build metadata dict
            metadata_dict = {
                'title': title,
                'authors': authors,
                'publisher': publisher,
                'published_year': pub_year,
                'page_count': page_count,
            }

            # Create book record with vendor-specific targets
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
            }

            # Set vendor-specific targets based on available pricing
            if 'AbeBooks' in vendor_prices and vendor_prices['AbeBooks'] > 0:
                book['abebooks_target'] = vendor_prices['AbeBooks']

            if 'Alibris' in vendor_prices and vendor_prices['Alibris'] > 0:
                book['alibris_target'] = vendor_prices['Alibris']

            if 'Biblio' in vendor_prices and vendor_prices['Biblio'] > 0:
                book['biblio_target'] = vendor_prices['Biblio']

            if 'Zvab' in vendor_prices and vendor_prices['Zvab'] > 0:
                book['zvab_target'] = vendor_prices['Zvab']

            # Only add book if it has at least one vendor target
            if any(k.endswith('_target') for k in book.keys()):
                books.append(book)

        cache_conn.close()
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


def load_unified_cross_platform_data() -> Tuple[List[dict], List[float]]:
    """
    Load unified training dataset with eBay sold prices as targets,
    and all platform listing prices as features.

    This approach:
    - Uses real eBay sold prices as ground truth (no synthetic targets)
    - Treats Amazon, AbeBooks, Alibris, etc. listings as FEATURES
    - Allows model to learn cross-platform relationships from data
    - Validates against real sold prices (statistically sound)

    Returns:
        Tuple of (records, targets) where:
        - records: List of book dicts with multi-platform features
        - targets: eBay sold prices (ground truth)

    Example record structure:
        {
            'isbn': '9780143039983',
            'target': 8.62,  # eBay sold price (ground truth)
            'target_type': 'sold',
            'timestamp': '2025-01-15T10:30:00Z',

            # eBay features
            'ebay_listing_median': 12.86,
            'ebay_listing_count': 15,
            'ebay_active_vs_sold_ratio': 1.49,

            # Amazon features (signals)
            'amazon_fbm_median': 40.11,
            'amazon_fbm_count': 8,

            # AbeBooks features (signals)
            'abebooks_median': 6.75,
            'abebooks_count': 12,

            # Cross-platform ratios (learned features)
            'amazon_to_ebay_ratio': 3.12,
            'abebooks_to_ebay_ratio': 0.52,

            # Other metadata, market stats, etc.
            'metadata': {...},
            'market': {...},
            'bookscouter': {...},
        }
    """
    print("=" * 80)
    print("LOADING UNIFIED CROSS-PLATFORM TRAINING DATA")
    print("=" * 80)

    cache_db = Path.home() / '.isbn_lot_optimizer' / 'metadata_cache.db'
    catalog_db = Path.home() / '.isbn_lot_optimizer' / 'catalog.db'

    if not cache_db.exists():
        print(f"Error: {cache_db} not found")
        return [], []

    conn = sqlite3.connect(cache_db)
    cursor = conn.cursor()

    # Query all books with eBay sold prices (ground truth requirement)
    # Also fetch Amazon, AbeBooks, and other platform listings as features
    query = """
    SELECT
        c.isbn,
        c.title,
        c.authors,
        c.publisher,
        c.publication_year,
        c.binding,
        c.page_count,
        c.sold_comps_median,
        c.sold_comps_count,
        c.sold_comps_min,
        c.sold_comps_max,
        c.amazon_fbm_median,
        c.amazon_fbm_count,
        c.amazon_fbm_min,
        c.amazon_fbm_max,
        c.amazon_fbm_avg_rating,
        c.abebooks_enr_median,
        c.abebooks_enr_count,
        c.abebooks_enr_min,
        c.abebooks_enr_max,
        c.abebooks_enr_spread,
        c.abebooks_enr_has_new,
        c.abebooks_enr_has_used,
        c.abebooks_enr_hc_premium,
        c.last_enrichment_at,
        c.market_fetched_at,
        c.amazon_fbm_collected_at,
        c.abebooks_enr_collected_at,
        c.market_json,
        c.bookscouter_json,
        c.cover_type,
        c.signed,
        c.printing
    FROM cached_books c
    WHERE c.sold_comps_median IS NOT NULL
      AND c.sold_comps_median >= 3.0
      AND c.sold_comps_count >= 5
    ORDER BY c.sold_comps_count DESC, c.sold_comps_median DESC
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    # Also query eBay active listings from ebay_active_listings table (aggregate by ISBN)
    cursor_ebay = conn.cursor()
    cursor_ebay.execute("""
        SELECT
            isbn,
            COUNT(*) as listing_count,
            MIN(price) as listing_min,
            MAX(price) as listing_max,
            AVG(price) as listing_avg,
            CAST(AVG(price) AS REAL) as listing_median
        FROM ebay_active_listings
        WHERE price IS NOT NULL AND price > 0
        GROUP BY isbn
    """)
    ebay_active_dict = {row[0]: {
        'listing_count': row[1],
        'listing_min': row[2],
        'listing_max': row[3],
        'listing_avg': row[4],
        'listing_median': row[5]  # Using avg as proxy for median (SQLite doesn't have median)
    } for row in cursor_ebay.fetchall()}

    conn.close()

    print(f"\nLoaded {len(rows)} books with eBay sold prices (ground truth)")
    print(f"Loaded {len(ebay_active_dict)} books with eBay active listings")

    records = []
    targets = []

    for row in rows:
        (isbn, title, authors, publisher, pub_year, binding, page_count,
         sold_comps_median, sold_comps_count, sold_comps_min, sold_comps_max,
         amazon_fbm_median, amazon_fbm_count, amazon_fbm_min, amazon_fbm_max, amazon_fbm_avg_rating,
         abe_enr_median, abe_enr_count, abe_enr_min, abe_enr_max, abe_enr_spread,
         abe_enr_has_new, abe_enr_has_used, abe_enr_hc_premium,
         last_enrichment_at, market_fetched_at, amazon_fbm_collected_at, abebooks_enr_collected_at,
         market_json, bookscouter_json, cover_type, signed, printing) = row

        # Skip lots
        if title and is_lot(title):
            continue

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

        # Get eBay active listings if available
        ebay_active = ebay_active_dict.get(isbn, {})

        # Build unified record
        record = {
            'isbn': isbn,
            'metadata': metadata_dict,
            'market': market_dict,
            'bookscouter': bookscouter_dict,
            'condition': 'Good',  # Default condition
            'cover_type': cover_type,
            'signed': signed,
            'printing': printing,

            # eBay sold (ground truth target)
            'ebay_sold_median': sold_comps_median,
            'ebay_sold_count': sold_comps_count,
            'ebay_sold_min': sold_comps_min,
            'ebay_sold_max': sold_comps_max,

            # eBay listings (feature)
            'ebay_listing_median': ebay_active.get('listing_median'),
            'ebay_listing_count': ebay_active.get('listing_count'),
            'ebay_listing_min': ebay_active.get('listing_min'),
            'ebay_listing_max': ebay_active.get('listing_max'),

            # Amazon FBM (feature)
            'amazon_fbm_median': amazon_fbm_median,
            'amazon_fbm_count': amazon_fbm_count,
            'amazon_fbm_min': amazon_fbm_min,
            'amazon_fbm_max': amazon_fbm_max,
            'amazon_fbm_avg_rating': amazon_fbm_avg_rating,

            # AbeBooks (feature)
            'abebooks_median': abe_enr_median,
            'abebooks_count': abe_enr_count,
            'abebooks_min': abe_enr_min,
            'abebooks_max': abe_enr_max,
            'abebooks_spread': abe_enr_spread,
            'abebooks_has_new': abe_enr_has_new,
            'abebooks_has_used': abe_enr_has_used,
            'abebooks_hc_premium': abe_enr_hc_premium,

            # Cross-platform ratios (let model learn these)
            'amazon_to_ebay_ratio': None,
            'abebooks_to_ebay_ratio': None,
            'amazon_to_abebooks_ratio': None,

            # Timestamps for temporal weighting
            'timestamp': market_fetched_at or last_enrichment_at,
            'ebay_timestamp': last_enrichment_at,
            'amazon_timestamp': amazon_fbm_collected_at,
            'abebooks_timestamp': abebooks_enr_collected_at,

            # Price type classification (for quick wins weighting)
            'target_type': 'sold',  # eBay sold price = ground truth
            'ebay_price_type': 'sold',
            'amazon_price_type': 'listing' if amazon_fbm_median else None,
            'abebooks_price_type': 'listing' if abe_enr_median else None,
        }

        # Calculate cross-platform ratios
        ebay_listing = ebay_active.get('listing_median')
        if ebay_listing and ebay_listing > 0:
            if amazon_fbm_median:
                record['amazon_to_ebay_ratio'] = amazon_fbm_median / ebay_listing
            if abe_enr_median:
                record['abebooks_to_ebay_ratio'] = abe_enr_median / ebay_listing

        if amazon_fbm_median and abe_enr_median and abe_enr_median > 0:
            record['amazon_to_abebooks_ratio'] = amazon_fbm_median / abe_enr_median

        # Calculate eBay listing/sold ratio (seller optimism metric)
        if ebay_listing and sold_comps_median > 0:
            record['ebay_listing_to_sold_ratio'] = ebay_listing / sold_comps_median

        records.append(record)
        targets.append(sold_comps_median)

    print(f"\nUnified dataset created:")
    print(f"  Total records: {len(records)}")
    print(f"  Target (eBay sold) range: ${min(targets):.2f} - ${max(targets):.2f}")
    print(f"  Target mean: ${sum(targets) / len(targets):.2f}")

    # Feature coverage stats
    amazon_count = sum(1 for r in records if r['amazon_fbm_median'])
    abebooks_count = sum(1 for r in records if r['abebooks_median'])
    ebay_listing_count = sum(1 for r in records if r['ebay_listing_median'])
    amazon_ratio_count = sum(1 for r in records if r['amazon_to_ebay_ratio'])
    abebooks_ratio_count = sum(1 for r in records if r['abebooks_to_ebay_ratio'])

    print(f"\nFeature coverage:")
    print(f"  Amazon FBM:           {amazon_count} ({amazon_count/len(records)*100:.1f}%)")
    print(f"  AbeBooks:             {abebooks_count} ({abebooks_count/len(records)*100:.1f}%)")
    print(f"  eBay listings:        {ebay_listing_count} ({ebay_listing_count/len(records)*100:.1f}%)")
    print(f"  Amazon/eBay ratios:   {amazon_ratio_count} ({amazon_ratio_count/len(records)*100:.1f}%)")
    print(f"  AbeBooks/eBay ratios: {abebooks_ratio_count} ({abebooks_ratio_count/len(records)*100:.1f}%)")

    print("\n" + "=" * 80)

    return records, targets


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
