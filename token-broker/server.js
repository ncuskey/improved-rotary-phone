import express from "express";
import fetch from "node-fetch";
import crypto from "crypto";

const { EBAY_APP_ID, EBAY_APP_SECRET, PORT = 8787, REDIRECT_URI = "http://localhost:8787/oauth/callback" } = process.env;

// App token cache (for Browse API, etc.)
let appCache = { token: null, expiresAt: 0 };

// User token storage (in-memory for now - move to database for production)
// Key: userId (default "default"), Value: { accessToken, refreshToken, expiresAt, scopes }
let userTokens = new Map();

// OAuth state storage (for CSRF protection)
let pendingStates = new Map(); // state -> { timestamp, scopes }

// ============================================================================
// APP-LEVEL OAUTH (Client Credentials)
// ============================================================================

async function getAppToken() {
  const now = Date.now();
  if (appCache.token && now < appCache.expiresAt - 5 * 60_000) return appCache.token;

  const body = new URLSearchParams({
    grant_type: "client_credentials",
    scope: "https://api.ebay.com/oauth/api_scope",
  }).toString();

  const resp = await fetch("https://api.ebay.com/identity/v1/oauth2/token", {
    method: "POST",
    headers: {
      Authorization:
        "Basic " + Buffer.from(`${EBAY_APP_ID}:${EBAY_APP_SECRET}`).toString("base64"),
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body,
  });

  const json = await resp.json();
  if (!resp.ok) throw new Error(`${resp.status} ${JSON.stringify(json)}`);

  appCache.token = json.access_token;
  appCache.expiresAt = now + (json.expires_in ?? 7200) * 1000;
  return appCache.token;
}

// ============================================================================
// USER-LEVEL OAUTH (Authorization Code Grant)
// ============================================================================

/**
 * Get or refresh a user access token.
 * @param {string} userId - User identifier (default: "default")
 * @param {string[]} requiredScopes - Required OAuth scopes
 * @returns {Promise<string>} Access token
 */
async function getUserToken(userId = "default", requiredScopes = []) {
  const stored = userTokens.get(userId);

  if (!stored) {
    throw new Error(`No user token found for ${userId}. User needs to authorize via /oauth/authorize`);
  }

  // Check if stored scopes match required scopes
  if (requiredScopes.length > 0) {
    const hasAllScopes = requiredScopes.every(scope => stored.scopes.includes(scope));
    if (!hasAllScopes) {
      throw new Error(`User token missing required scopes. Has: ${stored.scopes.join(', ')}, Needs: ${requiredScopes.join(', ')}`);
    }
  }

  // Check if token is still valid (with 5 min buffer)
  const now = Date.now();
  if (stored.accessToken && now < stored.expiresAt - 5 * 60_000) {
    return stored.accessToken;
  }

  // Token expired - refresh it
  console.log(`Refreshing user token for ${userId}...`);
  const refreshed = await refreshUserToken(stored.refreshToken);

  // Update storage
  userTokens.set(userId, {
    accessToken: refreshed.access_token,
    refreshToken: stored.refreshToken, // Keep existing refresh token
    expiresAt: now + (refreshed.expires_in ?? 7200) * 1000,
    scopes: stored.scopes,
  });

  return refreshed.access_token;
}

/**
 * Exchange refresh token for new access token.
 */
async function refreshUserToken(refreshToken) {
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: refreshToken,
  }).toString();

  const resp = await fetch("https://api.ebay.com/identity/v1/oauth2/token", {
    method: "POST",
    headers: {
      Authorization:
        "Basic " + Buffer.from(`${EBAY_APP_ID}:${EBAY_APP_SECRET}`).toString("base64"),
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body,
  });

  const json = await resp.json();
  if (!resp.ok) throw new Error(`Failed to refresh token: ${resp.status} ${JSON.stringify(json)}`);

  return json;
}

/**
 * Exchange authorization code for access/refresh tokens.
 */
async function exchangeCodeForToken(code) {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code: code,
    redirect_uri: REDIRECT_URI,
  }).toString();

  const resp = await fetch("https://api.ebay.com/identity/v1/oauth2/token", {
    method: "POST",
    headers: {
      Authorization:
        "Basic " + Buffer.from(`${EBAY_APP_ID}:${EBAY_APP_SECRET}`).toString("base64"),
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body,
  });

  const json = await resp.json();
  if (!resp.ok) throw new Error(`Failed to exchange code: ${resp.status} ${JSON.stringify(json)}`);

  return json;
}

// ============================================================================
// EXPRESS APP
// ============================================================================

const app = express();
app.use(express.json());

const router = express.Router();

// ----------------------------------------------------------------------------
// App-level token endpoint (existing)
// ----------------------------------------------------------------------------

router.get("/token/ebay-browse", async (_req, res) => {
  try {
    const token = await getAppToken();
    res.json({ access_token: token, token_type: "Application Access Token", expires_in: 7200 });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

// ----------------------------------------------------------------------------
// User OAuth endpoints (NEW)
// ----------------------------------------------------------------------------

/**
 * Step 1: Generate OAuth authorization URL
 * GET /oauth/authorize?scopes=sell.inventory,sell.fulfillment,sell.marketing
 */
router.get("/oauth/authorize", (req, res) => {
  try {
    // Parse requested scopes
    const scopesParam = req.query.scopes || "sell.inventory,sell.fulfillment,sell.marketing";
    const requestedScopes = scopesParam.split(",").map(s => s.trim());

    // Map shorthand to full eBay scope URLs
    const scopeMap = {
      "sell.inventory": "https://api.ebay.com/oauth/api_scope/sell.inventory",
      "sell.fulfillment": "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
      "sell.marketing": "https://api.ebay.com/oauth/api_scope/sell.marketing",
      "sell.account": "https://api.ebay.com/oauth/api_scope/sell.account",
      "commerce.identity.readonly": "https://api.ebay.com/oauth/api_scope/commerce.identity.readonly",
    };

    const fullScopes = requestedScopes.map(s => scopeMap[s] || s);

    // Generate CSRF state token
    const state = crypto.randomBytes(16).toString("hex");
    pendingStates.set(state, {
      timestamp: Date.now(),
      scopes: fullScopes,
    });

    // Clean up old states (older than 10 minutes)
    const tenMinutesAgo = Date.now() - 10 * 60_000;
    for (const [key, value] of pendingStates.entries()) {
      if (value.timestamp < tenMinutesAgo) {
        pendingStates.delete(key);
      }
    }

    // Build authorization URL
    const authUrl = new URL("https://auth.ebay.com/oauth2/authorize");
    authUrl.searchParams.set("client_id", EBAY_APP_ID);
    authUrl.searchParams.set("response_type", "code");
    authUrl.searchParams.set("redirect_uri", REDIRECT_URI);
    authUrl.searchParams.set("scope", fullScopes.join(" "));
    authUrl.searchParams.set("state", state);

    res.json({
      authorization_url: authUrl.toString(),
      state: state,
      scopes: fullScopes,
      instructions: "Redirect user to authorization_url. eBay will redirect back to /oauth/callback with code.",
    });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

/**
 * Step 2: OAuth callback handler
 * GET /oauth/callback?code=...&state=...
 */
router.get("/oauth/callback", async (req, res) => {
  try {
    const { code, state, error } = req.query;

    // Handle eBay error response
    if (error) {
      return res.status(400).send(`
        <html><body>
          <h1>OAuth Error</h1>
          <p>eBay returned an error: <strong>${error}</strong></p>
          <p>Description: ${req.query.error_description || "Unknown"}</p>
          <a href="/oauth/authorize">Try again</a>
        </body></html>
      `);
    }

    // Validate state (CSRF protection)
    if (!state || !pendingStates.has(state)) {
      return res.status(400).send(`
        <html><body>
          <h1>Invalid OAuth State</h1>
          <p>The OAuth state parameter is invalid or expired. This could be a CSRF attack.</p>
          <a href="/oauth/authorize">Start over</a>
        </body></html>
      `);
    }

    const { scopes } = pendingStates.get(state);
    pendingStates.delete(state);

    // Exchange authorization code for tokens
    const tokenData = await exchangeCodeForToken(code);

    // Store tokens (using "default" user for now)
    const userId = "default";
    const now = Date.now();
    userTokens.set(userId, {
      accessToken: tokenData.access_token,
      refreshToken: tokenData.refresh_token,
      expiresAt: now + (tokenData.expires_in ?? 7200) * 1000,
      scopes: scopes,
    });

    console.log(`✓ User OAuth successful for ${userId}. Scopes: ${scopes.join(", ")}`);

    res.send(`
      <html><body>
        <h1>✓ Authorization Successful!</h1>
        <p>Your eBay account has been connected.</p>
        <p><strong>Granted Scopes:</strong></p>
        <ul>
          ${scopes.map(s => `<li>${s}</li>`).join("")}
        </ul>
        <p>You can now create eBay listings via the API.</p>
        <p><a href="javascript:window.close()">Close this window</a></p>
      </body></html>
    `);
  } catch (e) {
    res.status(500).send(`
      <html><body>
        <h1>OAuth Error</h1>
        <p>${String(e)}</p>
        <a href="/oauth/authorize">Try again</a>
      </body></html>
    `);
  }
});

/**
 * Get user token (for API calls)
 * GET /token/ebay-user?scopes=sell.inventory,sell.fulfillment
 */
router.get("/token/ebay-user", async (req, res) => {
  try {
    const scopesParam = req.query.scopes || "sell.inventory,sell.fulfillment,sell.marketing";
    const requestedScopes = scopesParam.split(",").map(s => {
      const scopeMap = {
        "sell.inventory": "https://api.ebay.com/oauth/api_scope/sell.inventory",
        "sell.fulfillment": "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
        "sell.marketing": "https://api.ebay.com/oauth/api_scope/sell.marketing",
        "sell.account": "https://api.ebay.com/oauth/api_scope/sell.account",
      };
      return scopeMap[s.trim()] || s.trim();
    });

    const userId = req.query.userId || "default";
    const token = await getUserToken(userId, requestedScopes);

    res.json({
      access_token: token,
      token_type: "User Access Token",
      expires_in: 7200,
    });
  } catch (e) {
    const errorMsg = String(e);
    if (errorMsg.includes("No user token found")) {
      res.status(401).json({
        error: errorMsg,
        authorization_url: `${req.protocol}://${req.get("host")}/oauth/authorize`,
      });
    } else {
      res.status(500).json({ error: errorMsg });
    }
  }
});

/**
 * Check OAuth status
 * GET /oauth/status
 */
router.get("/oauth/status", (req, res) => {
  const userId = req.query.userId || "default";
  const stored = userTokens.get(userId);

  if (!stored) {
    return res.json({
      authorized: false,
      message: "No user token found. User needs to authorize.",
      authorization_url: `${req.protocol}://${req.get("host")}/oauth/authorize`,
    });
  }

  const now = Date.now();
  const isValid = stored.accessToken && now < stored.expiresAt;

  res.json({
    authorized: true,
    token_valid: isValid,
    scopes: stored.scopes,
    expires_in: Math.max(0, Math.floor((stored.expiresAt - now) / 1000)),
  });
});

// ----------------------------------------------------------------------------
// Track A: Marketplace Insights (sold comps) - requires eBay approval
// ----------------------------------------------------------------------------

router.get("/sold/ebay", async (req, res) => {
  try {
    const { gtin, q, dateFrom, dateTo, marketplace = 'EBAY_US' } = req.query;

    // For now, return 501 Not Implemented until MI access is granted
    res.status(501).json({
      error: 'eBay Marketplace Insights not enabled on this app. Apply for access at https://developer.ebay.com/my/keys'
    });

    /* UNCOMMENT WHEN MI ACCESS IS GRANTED:

    const term = gtin ?? q;
    if (!term) return res.status(400).json({ error: 'Missing gtin or q parameter' });

    // Get/refresh a USER access token with Marketplace Insights scope
    const userAccessToken = await getUserToken("default", ["https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"]);

    // Build time filter (last 30 days by default)
    const from = dateFrom ?? new Date(Date.now() - 30 * 864e5).toISOString();
    const to = dateTo ?? new Date().toISOString();

    const params = new URLSearchParams({
      q: term,
      filter: `lastSoldDate:[${from}..${to}]`,
      limit: '100'
    });

    const r = await fetch(
      `https://api.ebay.com/buy/marketplace_insights/v1_beta/item_sales/search?${params}`,
      {
        headers: {
          Authorization: `Bearer ${userAccessToken}`,
          'X-EBAY-C-MARKETPLACE-ID': marketplace
        }
      }
    );

    const json = await r.json();
    if (r.status === 403) {
      return res.status(501).json({
        error: 'Not entitled for Marketplace Insights. Request access via Application Growth Check.'
      });
    }
    if (!r.ok) return res.status(r.status).json({ error: json });

    // Normalize to compact summary
    const rows = (json.itemSales || []).map(it => ({
      title: it.title,
      price: Number(it.price?.value ?? 0),
      currency: it.price?.currency ?? 'USD',
      quantitySold: it.quantitySold ?? 1,
      lastSoldDate: it.lastSoldDate
    }));

    const prices = rows.map(r => r.price).sort((a, b) => a - b);
    const med = prices.length ? prices[(prices.length - 1) >> 1] : 0;

    res.json({
      count: rows.length,
      min: prices[0] ?? 0,
      median: med,
      max: prices[prices.length - 1] ?? 0,
      samples: rows.slice(0, 3) // 3 cheapest
    });
    */
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

// ============================================================================
// SERVER
// ============================================================================

app.use(["/isbn", "/isbn-web", "/"], router);

app.listen(PORT, () => {
  console.log(`\n========================================`);
  console.log(`Token Broker running on :${PORT}`);
  console.log(`========================================`);
  console.log(`\nApp OAuth (Browse API):`);
  console.log(`  GET http://localhost:${PORT}/token/ebay-browse`);
  console.log(`\nUser OAuth (Sell APIs):`);
  console.log(`  1. GET http://localhost:${PORT}/oauth/authorize`);
  console.log(`  2. Follow authorization_url to grant access`);
  console.log(`  3. GET http://localhost:${PORT}/token/ebay-user`);
  console.log(`\nCheck OAuth status:`);
  console.log(`  GET http://localhost:${PORT}/oauth/status`);
  console.log(`========================================\n`);
});
