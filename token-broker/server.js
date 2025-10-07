import express from "express";
import fetch from "node-fetch";

const { EBAY_APP_ID, EBAY_APP_SECRET, PORT = 8787 } = process.env;

let cache = { token: null, expiresAt: 0 }; // epoch ms

async function getAppToken() {
  const now = Date.now();
  if (cache.token && now < cache.expiresAt - 5 * 60_000) return cache.token; // reuse until 5 min left

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

  cache.token = json.access_token;
  cache.expiresAt = now + (json.expires_in ?? 7200) * 1000;
  return cache.token;
}

const app = express();
const router = express.Router();

router.get("/token/ebay-browse", async (_req, res) => {
  try {
    const token = await getAppToken();
    res.json({ access_token: token, token_type: "Application Access Token", expires_in: 7200 });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

// Track A: Marketplace Insights (sold comps) - requires eBay approval
router.get("/sold/ebay", async (req, res) => {
  try {
    const { gtin, q, dateFrom, dateTo, marketplace = 'EBAY_US' } = req.query;

    // For now, return 501 Not Implemented until MI access is granted
    // TODO: Once eBay approves MI access:
    // 1. Implement getUserAccessTokenWithRefresh() for User token with MI scope
    // 2. Store refresh token securely
    // 3. Enable the code below

    res.status(501).json({
      error: 'eBay Marketplace Insights not enabled on this app. Apply for access at https://developer.ebay.com/my/keys'
    });

    /* UNCOMMENT WHEN MI ACCESS IS GRANTED:

    const term = gtin ?? q;
    if (!term) return res.status(400).json({ error: 'Missing gtin or q parameter' });

    // Get/refresh a USER access token with Marketplace Insights scope
    const userAccessToken = await getUserAccessTokenWithRefresh();

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

app.use(["/isbn", "/isbn-web", "/"], router);

app.listen(PORT, () => console.log(`token broker on :${PORT}`));
