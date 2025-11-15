#!/usr/bin/env python3
"""Bulk Biblio data collection using Decodo Core plan."""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

env_file = Path(__file__).parent.parent / '.env'
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key] = value.strip('"').strip("'")

from shared.biblio_scraper import fetch_biblio_data
from shared.decodo import DecodoClient

def load_isbns(file_path):
    """Load ISBNs from text file."""
    isbns = []
    with open(file_path) as f:
        for line in f:
            isbn = line.strip().replace("-", "")
            if isbn and isbn.isdigit() and len(isbn) in (10, 13):
                isbns.append(isbn)
    return isbns

def main():
    parser = argparse.ArgumentParser(description="Bulk Biblio collection")
    parser.add_argument("--isbn-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    # Load ISBNs
    isbns = load_isbns(args.isbn_file)
    print(f"Loaded {len(isbns)} ISBNs")

    # Load existing if resume
    results = {}
    if args.resume and args.output.exists():
        with open(args.output) as f:
            results = json.load(f)
        print(f"Resuming: {len(results)} already collected")

    isbns_to_collect = [isbn for isbn in isbns if isbn not in results]
    print(f"Collecting {len(isbns_to_collect)} ISBNs")

    # Create client
    username = os.getenv("DECODO_AUTHENTICATION")
    password = os.getenv("DECODO_PASSWORD")
    client = DecodoClient(username=username, password=password, plan="core")

    try:
        for i, isbn in enumerate(isbns_to_collect, 1):
            print(f"[{i}/{len(isbns_to_collect)}] {isbn}...", end=" ", flush=True)
            
            try:
                data = fetch_biblio_data(isbn, client)
                
                if data["stats"]["count"] > 0:
                    print(f"✓ {data['stats']['count']} offers")
                else:
                    print("⚠️  No results")
                
                results[isbn] = data
                
                # Save every 50
                if i % 50 == 0:
                    with open(args.output, 'w') as f:
                        json.dump(results, f, indent=2)
                    print(f"   💾 Checkpoint ({i}/{len(isbns_to_collect)})")
                
                time.sleep(2.5)  # Rate limit
                
            except Exception as e:
                print(f"❌ {e}")
                results[isbn] = {"error": str(e), "stats": {"count": 0}}
    
    finally:
        client.close()
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.output}")

if __name__ == "__main__":
    main()
