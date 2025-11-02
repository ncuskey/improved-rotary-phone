"""
Test script for Amazon PA-API integration.

Run this to verify your Amazon PA-API credentials are working
before attempting bulk collection.

Usage:
    python3 scripts/test_amazon_paapi.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env
env_file = Path(__file__).parent.parent / '.env'
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key] = value.strip('"').strip("'")

print("=" * 80)
print("AMAZON PA-API TEST")
print("=" * 80)
print()

# Test 1: Check credentials
print("Test 1: Checking credentials...")
access_key = os.getenv("AMAZON_ACCESS_KEY")
secret_key = os.getenv("AMAZON_SECRET_KEY")
associate_tag = os.getenv("AMAZON_ASSOCIATE_TAG")

if not access_key:
    print("  ❌ FAIL: AMAZON_ACCESS_KEY not found in environment")
    print("  → Add to .env file")
    sys.exit(1)
else:
    print(f"  ✓ Access Key: {access_key[:10]}... (hidden)")

if not secret_key:
    print("  ❌ FAIL: AMAZON_SECRET_KEY not found in environment")
    print("  → Add to .env file")
    sys.exit(1)
else:
    print(f"  ✓ Secret Key: {'*' * 20}... (hidden)")

if not associate_tag:
    print("  ❌ FAIL: AMAZON_ASSOCIATE_TAG not found in environment")
    print("  → Add to .env file")
    sys.exit(1)
else:
    print(f"  ✓ Associate Tag: {associate_tag}")

print()

# Test 2: Check package installation
print("Test 2: Checking amazon-paapi package...")
try:
    from amazon.paapi import AmazonAPI
    print("  ✓ Package installed")
except ImportError:
    print("  ❌ FAIL: amazon-paapi package not installed")
    print("  → Run: pip install amazon-paapi")
    sys.exit(1)
print()

# Test 3: Import our module
print("Test 3: Importing amazon_paapi module...")
try:
    from shared.amazon_paapi import fetch_amazon_data, AmazonPAAPIClient
    print("  ✓ Module imported successfully")
except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)
print()

# Test 4: Create client
print("Test 4: Creating PA-API client...")
try:
    client = AmazonPAAPIClient()
    print("  ✓ Client created successfully")
except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)
print()

# Test 5: Lookup a well-known ISBN
print("Test 5: Looking up test ISBN (A Game of Thrones)...")
test_isbn = "9780553381702"
print(f"  ISBN: {test_isbn}")
print()

try:
    data = fetch_amazon_data(test_isbn)

    if "error" in data and not data.get("title"):
        print(f"  ❌ FAIL: {data['error']}")
        print()
        print("  Possible causes:")
        print("    1. Invalid credentials")
        print("    2. Associates account not approved")
        print("    3. PA-API access not enabled")
        print("    4. Rate limit exceeded (unlikely on first request)")
        print("    5. ISBN not in Amazon catalog")
        print()
        print("  Troubleshooting:")
        print("    - Verify credentials at: https://affiliate-program.amazon.com")
        print("    - Check Associates account status")
        print("    - Ensure PA-API is enabled in your Associates account")
        sys.exit(1)
    else:
        print("  ✓ Lookup successful!")
        print()
        print("  Book Details:")
        print(f"    Title: {data.get('title', 'N/A')}")
        print(f"    Authors: {data.get('authors', 'N/A')}")
        print(f"    ASIN: {data.get('asin', 'N/A')}")
        print(f"    Binding: {data.get('binding', 'N/A')}")
        print(f"    Publication: {data.get('publication_date', 'N/A')}")
        print()
        print("  Amazon Data:")
        print(f"    Sales Rank: {data.get('amazon_sales_rank', 'N/A')}")
        print(f"    Price: ${data.get('amazon_lowest_price', 0):.2f}")
        print(f"    Page Count: {data.get('page_count', 'N/A')}")
        print()
        print("  ML Features:")
        ml_features = data.get('ml_features', {})
        for key, value in ml_features.items():
            print(f"    {key}: {value}")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 80)
print("✓ ALL TESTS PASSED!")
print("=" * 80)
print()
print("Your Amazon PA-API integration is working correctly.")
print()
print("Next steps:")
print("  1. Run bulk collection test:")
print("     python3 scripts/collect_amazon_paapi.py --limit 10")
print()
print("  2. Switch production scripts to use PA-API instead of Decodo")
print()
print("  3. Start saving Decodo credits! 🎉")
print()

sys.exit(0)
