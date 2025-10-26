# eBay OAuth Authorization Guide

This guide explains how to authorize the app to create eBay listings on your behalf.

## Prerequisites

1. Token broker service running: `cd token-broker && node server.js`
2. eBay App ID and Secret in `.env`

## Authorization Flow

### Step 1: Check OAuth Status

```bash
curl http://localhost:8787/oauth/status
```

**Response if not authorized**:
```json
{
  "authorized": false,
  "message": "No user token found. User needs to authorize.",
  "authorization_url": "http://localhost:8787/oauth/authorize"
}
```

### Step 2: Get Authorization URL

```bash
curl http://localhost:8787/oauth/authorize
```

**Response**:
```json
{
  "authorization_url": "https://auth.ebay.com/oauth2/authorize?client_id=...",
  "state": "abc123...",
  "scopes": [
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
    "https://api.ebay.com/oauth/api_scope/sell.marketing"
  ],
  "instructions": "Redirect user to authorization_url. eBay will redirect back to /oauth/callback with code."
}
```

###Human: Let me know when you need my input