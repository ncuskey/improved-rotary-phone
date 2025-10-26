#!/usr/bin/env python3
"""Test script for eBay listing API endpoint.

Tests the POST /api/ebay/create-listing endpoint with real data.

Usage:
    python3 tests/test_ebay_listing_api.py [isbn]
"""

import json
import sys
from pathlib import Path

import requests

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_create_listing_api(isbn: str, base_url: str = "http://localhost:8000"):
    """Test the eBay listing creation API endpoint."""

    print("=" * 80)
    print(f"TESTING eBay LISTING API ENDPOINT")
    print("=" * 80)
    print(f"\nISBN: {isbn}")
    print(f"API URL: {base_url}/api/ebay/create-listing")

    # Test payload
    payload = {
        "isbn": isbn,
        "price": 24.99,
        "condition": "Very Good",
        "quantity": 1,
        "item_specifics": {
            "format": ["Hardcover"],
            "language": ["English"],
            "features": ["Dust Jacket"]
        },
        "use_seo_optimization": True
    }

    print("\n" + "-" * 80)
    print("[1/3] Sending request to API...")
    print("-" * 80)
    print(f"\nPayload:")
    print(json.dumps(payload, indent=2))

    try:
        response = requests.post(
            f"{base_url}/api/ebay/create-listing",
            json=payload,
            timeout=60
        )

        print(f"\n✓ Response Status: {response.status_code}")

    except requests.exceptions.RequestException as e:
        print(f"\n✗ Request failed: {e}")
        return False

    # Check response
    print("\n" + "-" * 80)
    print("[2/3] Analyzing response...")
    print("-" * 80)

    if response.status_code == 201:
        print("✓ Status: 201 Created (Success)")

        data = response.json()
        print(f"\nResponse data:")
        print(json.dumps(data, indent=2))

        # Validate response structure
        print("\n" + "-" * 80)
        print("[3/3] Validating response structure...")
        print("-" * 80)

        required_fields = ["id", "sku", "title", "price", "status"]
        missing_fields = [f for f in required_fields if f not in data]

        if missing_fields:
            print(f"✗ Missing required fields: {missing_fields}")
            return False

        print(f"✓ All required fields present")

        # Show key details
        print(f"\n📋 Listing Details:")
        print(f"  ID: {data.get('id')}")
        print(f"  SKU: {data.get('sku')}")
        print(f"  Title: {data.get('title')}")
        print(f"  Price: ${data.get('price')}")
        print(f"  Status: {data.get('status')}")

        if data.get('epid'):
            print(f"\n  🎉 ePID Found: {data['epid']}")
            print(f"     eBay will auto-populate 20+ Item Specifics!")
        else:
            print(f"\n  ⚠️  No ePID (using comprehensive manual Item Specifics)")

        if data.get('title_score'):
            print(f"\n  📊 SEO Title Score: {data['title_score']}")

        if data.get('offer_id'):
            print(f"\n  ✓ eBay Offer ID: {data['offer_id']}")
        if data.get('ebay_listing_id'):
            print(f"  ✓ eBay Listing ID: {data['ebay_listing_id']}")

        print("\n" + "=" * 80)
        print("✓ API ENDPOINT TEST PASSED")
        print("=" * 80)

        return True

    elif response.status_code == 404:
        print(f"✗ Status: 404 Not Found")
        print(f"\nError: {response.json().get('detail')}")
        print(f"\nThe book needs to be scanned first before creating a listing.")
        return False

    elif response.status_code == 400:
        print(f"✗ Status: 400 Bad Request")
        print(f"\nError: {response.json().get('detail')}")
        return False

    elif response.status_code == 500:
        print(f"✗ Status: 500 Internal Server Error")
        print(f"\nError: {response.json().get('detail')}")
        print(f"\nFull response:")
        print(json.dumps(response.json(), indent=2))
        return False

    else:
        print(f"✗ Unexpected status code: {response.status_code}")
        print(f"\nResponse:")
        try:
            print(json.dumps(response.json(), indent=2))
        except:
            print(response.text)
        return False


def main():
    """Run the API test."""

    # Default to Wings of Fire (we know it has an ePID)
    default_isbn = "9780545349277"

    if len(sys.argv) > 1:
        isbn = sys.argv[1]
    else:
        isbn = default_isbn
        print(f"Using default ISBN: {isbn}")
        print(f"(Specify a different ISBN: python3 tests/test_ebay_listing_api.py <isbn>)")

    # Check if server is running
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code != 200:
            print("✗ API server not responding correctly")
            print("  Make sure the server is running: uvicorn isbn_web.main:app --reload")
            sys.exit(1)
    except requests.exceptions.RequestException:
        print("✗ Cannot connect to API server at http://localhost:8000")
        print("  Make sure the server is running: uvicorn isbn_web.main:app --reload")
        sys.exit(1)

    # Run the test
    try:
        success = test_create_listing_api(isbn)
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
