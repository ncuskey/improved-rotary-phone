#!/usr/bin/env python3
"""
eBay User OAuth Token Setup

This script helps you obtain a user OAuth token from eBay to access your sales history.
Run this once to get a refresh token that will be saved to .env

Usage:
    python3 scripts/setup_ebay_user_token.py
"""

import base64
import os
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv, set_key

# Load environment
load_dotenv()

CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")
REDIRECT_URI = "https://localhost/oauth"  # eBay requires HTTPS for prod, but we'll handle the code manually

# Scopes needed for sales history
SCOPES = [
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
]

def get_auth_url():
    """Generate eBay OAuth authorization URL."""
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
    }

    base_url = "https://auth.ebay.com/oauth2/authorize"
    return f"{base_url}?{urlencode(params)}"

def exchange_code_for_token(auth_code: str) -> dict:
    """Exchange authorization code for access and refresh tokens."""

    # Create Basic auth header
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    b64_credentials = base64.b64encode(credentials.encode()).decode()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {b64_credentials}",
    }

    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": REDIRECT_URI,
    }

    response = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers=headers,
        data=data,
    )

    response.raise_for_status()
    return response.json()

def save_tokens(token_data: dict):
    """Save refresh token to .env file."""
    env_file = Path(".env")

    refresh_token = token_data.get("refresh_token")
    if refresh_token:
        set_key(env_file, "EBAY_USER_REFRESH_TOKEN", refresh_token)
        print(f"\n✓ Saved refresh token to {env_file}")

    # Also show access token (expires in ~2 hours)
    access_token = token_data.get("access_token")
    if access_token:
        print(f"\n✓ Access token obtained (valid for {token_data.get('expires_in', 0) // 3600} hours)")

def main():
    print("="*80)
    print("EBAY USER OAUTH TOKEN SETUP")
    print("="*80)
    print()

    if not CLIENT_ID or not CLIENT_SECRET:
        print("✗ Error: EBAY_CLIENT_ID and EBAY_CLIENT_SECRET must be set in .env")
        return 1

    print("Step 1: Opening eBay authorization page in your browser...")
    print()

    auth_url = get_auth_url()
    print(f"Authorization URL:\n{auth_url}\n")

    # Try to open browser
    try:
        webbrowser.open(auth_url)
        print("✓ Browser opened")
    except:
        print("⚠ Could not open browser automatically")
        print(f"Please open this URL manually:\n{auth_url}")

    print()
    print("Step 2: Log in to eBay and authorize the application")
    print()
    print("Step 3: After authorization, eBay will redirect to:")
    print(f"  {REDIRECT_URI}?code=...")
    print()
    print("The page will fail to load (that's expected!).")
    print("Copy the ENTIRE URL from your browser's address bar and paste it below.")
    print()

    redirect_url = input("Paste the redirect URL here: ").strip()

    # Extract authorization code from URL
    if "code=" not in redirect_url:
        print("\n✗ Error: No authorization code found in URL")
        print("Make sure you copied the complete URL including ?code=...")
        return 1

    # Parse code from URL
    auth_code = redirect_url.split("code=")[1].split("&")[0]

    print(f"\n✓ Authorization code extracted: {auth_code[:20]}...")
    print("\nStep 4: Exchanging authorization code for tokens...")

    try:
        token_data = exchange_code_for_token(auth_code)
        save_tokens(token_data)

        print()
        print("="*80)
        print("SETUP COMPLETE!")
        print("="*80)
        print()
        print("You can now run:")
        print("  python3 scripts/collect_my_ebay_sales.py")
        print()
        print("The refresh token will be used to automatically get new access tokens.")

        return 0

    except requests.exceptions.HTTPError as e:
        print(f"\n✗ Error exchanging code for token: {e}")
        print(f"Response: {e.response.text}")
        return 1

if __name__ == "__main__":
    exit(main())
