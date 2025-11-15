#!/usr/bin/env python3
"""
Collect eBay Sales History

This script retrieves your eBay sales history using the Sell Fulfillment API
and saves them to the catalog.db sold_listings table. Signed books are detected
automatically and flagged for ML training.

Prerequisites:
    1. Token broker must be running at http://localhost:8787
    2. Complete OAuth via: http://localhost:8787/oauth/authorize?scopes=sell.fulfillment,sell.inventory
    3. Or use --use-env-token flag with EBAY_USER_REFRESH_TOKEN in .env

Usage:
    python3 scripts/collect_my_ebay_sales.py [--days 90] [--dry-run]
"""

import argparse
import base64
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.feature_detector import is_signed

# Load environment
load_dotenv()


class TokenBrokerClient:
    """Get eBay user tokens from token broker."""

    def __init__(self, broker_url: str = "http://localhost:8787"):
        self.broker_url = broker_url

    def get_access_token(self) -> str:
        """Get user access token from token broker."""
        response = requests.get(
            f"{self.broker_url}/token/ebay-user",
            params={"scopes": "sell.fulfillment,sell.inventory"}
        )

        if response.status_code == 401:
            error_data = response.json()
            auth_url = error_data.get("authorization_url", f"{self.broker_url}/oauth/authorize")
            raise Exception(
                f"User not authorized. Please visit:\n{auth_url}?scopes=sell.fulfillment,sell.inventory"
            )

        response.raise_for_status()
        token_data = response.json()
        return token_data["access_token"]


class DirectOAuthClient:
    """Handle eBay OAuth token management directly (fallback)."""

    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._access_token = None
        self._token_expires_at = None

    def get_access_token(self) -> str:
        """Get valid access token, refreshing if necessary."""
        if self._access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at:
                return self._access_token

        # Refresh token
        credentials = f"{self.client_id}:{self.client_secret}"
        b64_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {b64_credentials}",
        }

        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "scope": " ".join([
                "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
                "https://api.ebay.com/oauth/api_scope/sell.inventory",
            ])
        }

        response = requests.post(
            "https://api.ebay.com/identity/v1/oauth2/token",
            headers=headers,
            data=data,
        )
        response.raise_for_status()

        token_data = response.json()
        self._access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 7200)  # Default 2 hours
        self._token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)  # 5 min buffer

        return self._access_token


class EBaySalesCollector:
    """Collect eBay sales history via Sell Fulfillment API."""

    def __init__(self, oauth_client):
        self.oauth = oauth_client
        self.base_url = "https://api.ebay.com/sell/fulfillment/v1"

    def get_orders(self, days_back: int = 90) -> List[Dict]:
        """
        Retrieve orders from the past N days.

        Args:
            days_back: Number of days to look back

        Returns:
            List of order dictionaries
        """
        # Calculate date filter
        since_date = datetime.now() - timedelta(days=days_back)
        filter_date = since_date.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        orders = []
        offset = 0
        limit = 50  # eBay max per page

        print(f"Fetching orders from the past {days_back} days...")
        print(f"Filter date: {filter_date}")
        print()

        while True:
            access_token = self.oauth.get_access_token()

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            params = {
                "filter": f"lastmodifieddate:[{filter_date}..]",
                "limit": limit,
                "offset": offset,
            }

            response = requests.get(
                f"{self.base_url}/order",
                headers=headers,
                params=params,
            )

            if response.status_code != 200:
                print(f"✗ API error: {response.status_code}")
                print(response.text)
                break

            data = response.json()
            batch_orders = data.get("orders", [])

            if not batch_orders:
                break

            orders.extend(batch_orders)
            print(f"  Fetched {len(batch_orders)} orders (total: {len(orders)})")

            # Check if there are more results
            total = data.get("total", 0)
            if offset + limit >= total:
                break

            offset += limit

        print(f"\n✓ Retrieved {len(orders)} total orders")
        return orders

    def extract_isbn_from_text(self, text: str) -> Optional[str]:
        """
        Extract ISBN from title or product identifiers.

        Looks for ISBN-10 or ISBN-13 patterns.
        """
        if not text:
            return None

        # ISBN-13 pattern (13 digits, possibly with hyphens)
        isbn13_match = re.search(r'(?:ISBN[-: ]?)?(\d{13})', text)
        if isbn13_match:
            return isbn13_match.group(1)

        # ISBN-10 pattern (10 characters including possible X)
        isbn10_match = re.search(r'(?:ISBN[-: ]?)?(\d{9}[\dXx])', text)
        if isbn10_match:
            return isbn10_match.group(1)

        return None

    def parse_orders_to_sales(self, orders: List[Dict]) -> List[Dict]:
        """
        Parse eBay orders into sales records for database.

        Returns:
            List of sale dictionaries with fields:
                - isbn
                - title
                - sold_price
                - sold_date
                - vendor (always "ebay")
                - signed (1 if detected, 0 otherwise)
                - source ("user_sales")
        """
        sales = []

        for order in orders:
            order_id = order.get("orderId", "")
            order_date = order.get("creationDate", "")

            # Process each line item
            line_items = order.get("lineItems", [])
            for item in line_items:
                title = item.get("title", "")

                # Extract ISBN from title or product identifiers
                isbn = None

                # Try product identifiers first
                sku = item.get("sku", "")
                isbn = self.extract_isbn_from_text(sku)

                # Fall back to parsing title
                if not isbn:
                    isbn = self.extract_isbn_from_text(title)

                # Skip if no ISBN found
                if not isbn:
                    continue

                # Get sale price
                total = item.get("total", {})
                price_str = total.get("value", "0")
                try:
                    sold_price = float(price_str)
                except ValueError:
                    sold_price = 0.0

                # Detect if signed
                signed = 1 if is_signed(title) else 0

                sales.append({
                    "isbn": isbn,
                    "title": title,
                    "sold_price": sold_price,
                    "sold_date": order_date,
                    "vendor": "ebay",
                    "signed": signed,
                    "source": "user_sales",
                    "order_id": order_id,
                })

        return sales

    def save_sales_to_db(self, sales: List[Dict], catalog_db: str, dry_run: bool = False) -> None:
        """
        Save sales to catalog.db sold_listings table.

        Args:
            sales: List of sale dictionaries
            catalog_db: Path to catalog.db
            dry_run: If True, don't actually insert
        """
        if not sales:
            print("No sales to save")
            return

        print()
        print("="*80)
        print("SAVING SALES TO DATABASE")
        print("="*80)
        print()

        conn = sqlite3.connect(catalog_db)
        cursor = conn.cursor()

        # Check if sold_listings table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='sold_listings'
        """)

        if not cursor.fetchone():
            print("✗ sold_listings table not found in catalog.db")
            print("  Creating table...")

            cursor.execute("""
                CREATE TABLE sold_listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    isbn TEXT NOT NULL,
                    title TEXT,
                    sold_price REAL,
                    sold_date TEXT,
                    vendor TEXT,
                    signed INTEGER DEFAULT 0,
                    source TEXT,
                    order_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sold_listings_isbn
                ON sold_listings(isbn)
            """)

            print("✓ Table created")

        # Count sales by signed status
        signed_sales = [s for s in sales if s["signed"] == 1]
        unsigned_sales = [s for s in sales if s["signed"] == 0]

        print(f"Sales to save:")
        print(f"  Total:    {len(sales)}")
        print(f"  Signed:   {len(signed_sales)} ({len(signed_sales)/len(sales)*100:.1f}%)")
        print(f"  Unsigned: {len(unsigned_sales)}")
        print()

        if dry_run:
            print("DRY RUN: Would save the following sales:")
            print()

            if signed_sales:
                print("Sample signed sales:")
                for sale in signed_sales[:5]:
                    print(f"  - {sale['isbn']}: {sale['title'][:60]} → ${sale['sold_price']:.2f}")
                if len(signed_sales) > 5:
                    print(f"  ... and {len(signed_sales) - 5} more signed sales")

            print()
            return

        # Insert sales
        inserted = 0
        skipped = 0

        for sale in sales:
            # Check if this order_id + isbn combo already exists
            cursor.execute("""
                SELECT id FROM sold_listings
                WHERE order_id = ? AND isbn = ?
            """, (sale["order_id"], sale["isbn"]))

            if cursor.fetchone():
                skipped += 1
                continue

            cursor.execute("""
                INSERT INTO sold_listings (
                    isbn, title, sold_price, sold_date, vendor,
                    signed, source, order_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sale["isbn"],
                sale["title"],
                sale["sold_price"],
                sale["sold_date"],
                sale["vendor"],
                sale["signed"],
                sale["source"],
                sale["order_id"],
            ))

            inserted += 1

        conn.commit()
        conn.close()

        print(f"✓ Inserted {inserted} new sales")
        if skipped > 0:
            print(f"  Skipped {skipped} duplicates")

        print()
        print("="*80)
        print("SALES SAVED")
        print("="*80)
        print()
        print("Next steps:")
        print("  1. Run: python3 scripts/sync_signed_status_to_training.py")
        print("  2. Retrain: python3 scripts/stacking/train_ebay_model.py")


def main():
    parser = argparse.ArgumentParser(
        description="Collect eBay sales history for ML training"
    )
    parser.add_argument(
        '--days',
        type=int,
        default=90,
        help='Number of days to look back (default: 90)'
    )
    parser.add_argument(
        '--catalog-db',
        default=str(Path.home() / '.isbn_lot_optimizer' / 'catalog.db'),
        help='Path to catalog.db (default: ~/.isbn_lot_optimizer/catalog.db)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be saved without actually saving'
    )
    parser.add_argument(
        '--use-env-token',
        action='store_true',
        help='Use EBAY_USER_REFRESH_TOKEN from .env instead of token broker'
    )
    parser.add_argument(
        '--broker-url',
        default='http://localhost:8787',
        help='Token broker URL (default: http://localhost:8787)'
    )

    args = parser.parse_args()

    print("="*80)
    print("EBAY SALES COLLECTION")
    print("="*80)
    print()

    # Check catalog.db exists
    catalog_path = Path(args.catalog_db)
    if not catalog_path.parent.exists():
        print(f"✗ Error: Directory not found: {catalog_path.parent}")
        return 1

    # Initialize OAuth client
    try:
        if args.use_env_token:
            # Use direct OAuth with refresh token from .env
            CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
            CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")
            USER_REFRESH_TOKEN = os.getenv("EBAY_USER_REFRESH_TOKEN")

            if not CLIENT_ID or not CLIENT_SECRET:
                print("✗ Error: EBAY_CLIENT_ID and EBAY_CLIENT_SECRET must be set in .env")
                return 1

            if not USER_REFRESH_TOKEN:
                print("✗ Error: EBAY_USER_REFRESH_TOKEN not found in .env")
                print()
                print("Run this first to obtain a refresh token:")
                print("  python3 scripts/setup_ebay_user_token.py")
                return 1

            print("Using direct OAuth with refresh token from .env")
            oauth = DirectOAuthClient(CLIENT_ID, CLIENT_SECRET, USER_REFRESH_TOKEN)
        else:
            # Use token broker (default)
            print(f"Using token broker at {args.broker_url}")
            oauth = TokenBrokerClient(args.broker_url)

        collector = EBaySalesCollector(oauth)
    except Exception as e:
        print(f"✗ Error initializing eBay client: {e}")
        return 1

    # Fetch orders
    try:
        orders = collector.get_orders(days_back=args.days)
    except requests.exceptions.HTTPError as e:
        print(f"✗ Error fetching orders: {e}")
        if e.response:
            print(f"Response: {e.response.text}")
        return 1

    if not orders:
        print()
        print("No orders found in the specified time period")
        return 0

    # Parse orders into sales
    print()
    print("Parsing orders into sales records...")
    sales = collector.parse_orders_to_sales(orders)

    if not sales:
        print()
        print("⚠ No sales with ISBNs found")
        print("  Sales may not have ISBN information in titles or SKUs")
        return 0

    print(f"✓ Parsed {len(sales)} sales with ISBNs")

    # Count signed books
    signed_count = sum(1 for s in sales if s["signed"] == 1)
    if signed_count > 0:
        print(f"✓ Found {signed_count} signed book sales ({signed_count/len(sales)*100:.1f}%)")

    # Save to database
    collector.save_sales_to_db(sales, args.catalog_db, dry_run=args.dry_run)

    return 0


if __name__ == '__main__':
    sys.exit(main())
