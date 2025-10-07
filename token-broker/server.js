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

app.use(["/isbn", "/isbn-web", "/"], router);

app.listen(PORT, () => console.log(`token broker on :${PORT}`));
