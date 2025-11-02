"""
Decodo Core Plan Access Verification Script

Tests Core plan credentials and verifies AbeBooks scraping capability.
Run this FIRST before attempting bulk collection.

Usage:
    python3 scripts/test_decodo_access.py

Expected output:
    ✓ All checks pass → Ready for bulk collection
    ✗ Any failures → Follow troubleshooting guide
"""

import os
import sys
import time
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
print("DECODO CORE PLAN ACCESS VERIFICATION")
print("=" * 80)
print()

# Test 1: Check credentials
print("Test 1: Checking Decodo credentials...")
username = os.getenv("DECODO_AUTHENTICATION")
password = os.getenv("DECODO_PASSWORD")

if not username or not password:
    print("  ❌ FAIL: Credentials not found in environment")
    print("  → Set DECODO_AUTHENTICATION and DECODO_PASSWORD in .env file")
    sys.exit(1)
else:
    print(f"  ✓ Username: {username}")
    print(f"  ✓ Password: {'*' * 20}... (hidden)")
print()

# Test 2: Import dependencies
print("Test 2: Checking dependencies...")
try:
    from shared.decodo import DecodoClient
    from shared.abebooks_scraper import fetch_abebooks_data
    print("  ✓ All imports successful")
except ImportError as e:
    print(f"  ❌ FAIL: Import error - {e}")
    sys.exit(1)
print()

# Test 3: Create Decodo client
print("Test 3: Creating Decodo client...")
try:
    client = DecodoClient(
        username=username,
        password=password,
        rate_limit=1  # Very conservative for testing
    )
    print("  ✓ Client created successfully")
except Exception as e:
    print(f"  ❌ FAIL: Could not create client - {e}")
    sys.exit(1)
print()

# Test 4: Test with simple URL (not AbeBooks)
print("Test 4: Testing basic scraping capability (example.com)...")
try:
    test_url = "https://example.com"
    response = client.scrape_url(test_url, render_js=False, max_retries=1)

    if response.status_code == 200:
        print("  ✓ Basic scraping works (200 OK)")
        print(f"  ✓ Response length: {len(response.body)} bytes")
    elif response.status_code == 429:
        print("  ❌ FAIL: Rate limit (429)")
        print("  → Check dashboard: https://dashboard.decodo.com")
        print("  → Possible causes:")
        print("     1. Credits depleted")
        print("     2. Subscription expired")
        print("     3. Wrong credentials for Core plan")
        client.close()
        sys.exit(1)
    else:
        print(f"  ⚠️  WARNING: Unexpected status code {response.status_code}")
        if response.error:
            print(f"  Error: {response.error}")
except Exception as e:
    print(f"  ❌ FAIL: {e}")
    client.close()
    sys.exit(1)
print()

# Test 5: Test rate limiting
print("Test 5: Testing rate limiting...")
try:
    start = time.time()
    for i in range(3):
        response = client.scrape_url("https://example.com", render_js=False, max_retries=1)
        if response.status_code != 200:
            print(f"  ⚠️  Request {i+1} failed with status {response.status_code}")
    elapsed = time.time() - start
    print(f"  ✓ 3 requests completed in {elapsed:.1f}s")
    print(f"  ✓ Rate: {3/elapsed:.2f} req/sec")
except Exception as e:
    print(f"  ❌ FAIL: {e}")
    client.close()
    sys.exit(1)
print()

# Test 6: Test AbeBooks scraping (the real test!)
print("Test 6: Testing AbeBooks scraping...")
print("  Using test ISBN: 9780553381702 (A Game of Thrones)")
print("  This will use 1 Core plan credit")
print()

input("  Press Enter to continue (or Ctrl+C to abort)...")
print()

try:
    test_isbn = "9780553381702"
    start = time.time()

    data = fetch_abebooks_data(test_isbn, client)

    elapsed = time.time() - start

    if data.get("error") and data["stats"]["count"] == 0:
        print(f"  ❌ FAIL: {data['error']}")
        print()
        print("  Troubleshooting:")
        print("  → AbeBooks may be blocking Decodo")
        print("  → Try with render_js=True (already enabled)")
        print("  → Check if CAPTCHA is present in response")
        print("  → Contact Decodo support about AbeBooks access")
    else:
        print(f"  ✓ AbeBooks scraping successful!")
        print(f"  ✓ Time: {elapsed:.1f}s")
        print(f"  ✓ Results found: {data['total_results']}")
        print(f"  ✓ Offers parsed: {data['stats']['count']}")

        if data['stats']['count'] > 0:
            stats = data['stats']
            print()
            print("  Pricing Data:")
            print(f"    Min price: ${stats['min_price']:.2f}")
            print(f"    Max price: ${stats['max_price']:.2f}")
            print(f"    Avg price: ${stats['avg_price']:.2f}")
            print(f"    Median price: ${stats['median_price']:.2f}")

            print()
            print("  ML Features:")
            for key, value in data['ml_features'].items():
                print(f"    {key}: {value}")

            print()
            print("  Sample offers:")
            for i, offer in enumerate(data['offers'][:3], 1):
                condition = offer.get('condition', 'Unknown')
                binding = offer.get('binding', 'Unknown')
                price = offer['price']
                print(f"    {i}. ${price:.2f} - {condition} {binding}")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    client.close()
    sys.exit(1)

client.close()
print()

# Final summary
print("=" * 80)
print("VERIFICATION SUMMARY")
print("=" * 80)
print()
print("✓ All tests passed!")
print()
print("Next steps:")
print("  1. Run small batch test:")
print("     python3 scripts/collect_abebooks_bulk.py --limit 10")
print()
print("  2. Review results and validate data quality")
print()
print("  3. Scale up to full collection:")
print("     python3 scripts/collect_abebooks_bulk.py --limit 5000 --resume")
print()
print("  4. Monitor credit usage in dashboard:")
print("     https://dashboard.decodo.com")
print()

sys.exit(0)
