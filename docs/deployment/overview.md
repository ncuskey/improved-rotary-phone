# Deployment Guide

Complete guide to deploying the ISBN Lot Optimizer web interface to cloud platforms.

---

## Overview

This guide covers deploying the **isbn_web** application (web interface only) to various cloud platforms. The desktop GUI and iOS app are not deployed—they remain local applications.

**What gets deployed:**
- FastAPI web interface (`isbn_web/`)
- REST API endpoints
- Web-based scanner interface
- Lot management and visualization

**What stays local:**
- Desktop Tkinter GUI
- iOS scanner app
- CLI tools

---

## Quick Start (Railway - 5 Minutes)

The fastest way to get your web app online:

### 1. Push to GitHub

```bash
git add .
git commit -m "Ready for deployment"
git push origin main
```

### 2. Deploy to Railway

1. Go to https://railway.app
2. Sign in with GitHub
3. Click "New Project" → "Deploy from GitHub repo"
4. Select your repository
5. Railway auto-detects `railway.json` configuration
6. Done! Live in 2-3 minutes

### 3. Get Your URL

- In Railway dashboard, click "Generate Domain"
- Your app: `your-app.railway.app`

**That's it!** 🚀

---

## Platform Comparison

| Feature | Railway | Render | Fly.io |
|---------|---------|--------|--------|
| **Ease of Setup** | ⭐⭐⭐⭐⭐ Easiest | ⭐⭐⭐⭐ Easy | ⭐⭐⭐ Moderate |
| **Free Tier** | 500 hrs/mo + $5 credit | Yes (spins down) | 3GB storage |
| **Auto-Deploy** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Database** | PostgreSQL (free) | PostgreSQL (90 days) | PostgreSQL (addon) |
| **Config File** | `railway.json` | `render.yaml` | `fly.toml` |
| **Global CDN** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Custom Domains** | ✅ Yes | ✅ Yes | ✅ Yes |

**Recommendation:** Railway for quickest setup, Render for generous free tier.

---

## Deployment Configuration Files

Your repository includes pre-configured files:

### Procfile (All Platforms)
```
web: cd isbn_web && uvicorn main:app --host 0.0.0.0 --port $PORT
```

### railway.json (Railway)
```json
{
  "services": {
    "type": "web",
    "name": "isbn-lot-optimizer",
    "env": "python",
    "region": "oregon",
    "buildCommand": "pip install -r requirements.txt",
    "startCommand": "cd isbn_web && uvicorn main:app --host 0.0.0.0 --port $PORT"
  }
}
```

### render.yaml (Render)
```yaml
services:
  - type: web
    name: isbn-lot-optimizer
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: cd isbn_web && uvicorn main:app --host 0.0.0.0 --port $PORT
```

---

## Detailed Platform Guides

### Railway (Recommended)

Railway auto-detects Python apps and handles configuration automatically.

**Prerequisites:**
- GitHub repository
- Python 3.11+

**Steps:**

1. **Sign Up**
   - Visit https://railway.app
   - Sign up with GitHub

2. **Create Project**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository

3. **Configure (Optional)**
   - Add environment variables in Variables tab
   - See [Configuration](../setup/configuration.md) for variables

4. **Generate Domain**
   - Click "Generate Domain" in Settings
   - Or add custom domain

5. **Deploy**
   - Automatic on every git push
   - View logs in dashboard

**Database:**
- Add PostgreSQL service (free)
- Automatically sets `DATABASE_URL`

**Cost:**
- Free: 500 hours/month + $5 credit
- Paid: From $5/month

**See:** [Railway-Specific Guide](railway.md)

---

### Render

Similar to Railway with generous free tier.

**Prerequisites:**
- GitHub repository
- Python 3.11+

**Steps:**

1. **Sign Up**
   - Visit https://render.com
   - Sign up with GitHub

2. **Create Web Service**
   - Click "New +" → "Web Service"
   - Connect GitHub repository

3. **Configure**
   - **Name:** isbn-lot-optimizer
   - **Region:** Choose closest
   - **Branch:** main
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `cd isbn_web && uvicorn main:app --host 0.0.0.0 --port $PORT`

4. **Select Plan**
   - Free tier for testing
   - Paid plans from $7/month

5. **Add Environment Variables** (optional)
   - Click "Environment" tab
   - Add API keys as needed

6. **Deploy**
   - Click "Create Web Service"
   - Auto-deploys on git push

**Database:**
- Free PostgreSQL (90-day limit)
- Paid tiers have persistent database

**Cost:**
- Free: Available (spins down after 15min inactivity)
- Paid: From $7/month

**See:** [Render-Specific Guide](render.md)

---

### Fly.io

Global deployment with edge network.

**Prerequisites:**
- Fly CLI installed
- GitHub repository

**Steps:**

1. **Install CLI**
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Login**
   ```bash
   fly auth login
   ```

3. **Launch App**
   ```bash
   fly launch
   ```
   - Choose app name
   - Choose region
   - Don't deploy yet

4. **Configure fly.toml**
   ```toml
   [build]
   builder = "paketobuildpacks/builder:base"

   [env]
   PORT = "8080"

   [[services]]
   internal_port = 8080
   protocol = "tcp"

   [[services.ports]]
   handlers = ["http"]
   port = 80

   [[services.ports]]
   handlers = ["tls", "http"]
   port = 443
   ```

5. **Deploy**
   ```bash
   fly deploy
   ```

**Database:**
- PostgreSQL addon available
- `fly postgres create`

**Cost:**
- Free: 3GB storage
- Paid: Usage-based

---

## Database Configuration

### Current: SQLite (Development)

Works for local/testing but has cloud limitations:
- ❌ May not persist between deployments
- ❌ Not suitable for multiple instances
- ❌ Limited to single-node

### Recommended: PostgreSQL (Production)

For cloud deployment, switch to PostgreSQL:

**1. Update requirements.txt:**
```
psycopg2-binary
```

**2. Update database connection:**
```python
import os
from sqlalchemy import create_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///~/.isbn_lot_optimizer/catalog.db"
)

# Fix for Railway/Render Postgres URLs
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
```

**3. Run migrations:**
```bash
# Create tables on first deploy
python -m isbn_lot_optimizer.database
```

**Platform-Specific:**
- **Railway:** Add PostgreSQL service, `DATABASE_URL` set automatically
- **Render:** Add PostgreSQL database, connect in environment
- **Fly.io:** `fly postgres create`, attach to app

---

## Environment Variables

Add to your platform's dashboard:

### Essential (Optional)
```bash
# eBay APIs
EBAY_APP_ID=your-finding-app-id
EBAY_CLIENT_ID=your-browse-client-id
EBAY_CLIENT_SECRET=your-browse-client-secret

# BookScouter
BOOKSCOUTER_API_KEY=your-bookscouter-key

# Hardcover
HARDCOVER_API_TOKEN=Bearer your-hardcover-token
```

See [Configuration Guide](../setup/configuration.md) for complete list.

### Adding Variables

**Railway:**
- Project → Variables tab → Add variable

**Render:**
- Service → Environment tab → Add environment variable

**Fly.io:**
```bash
fly secrets set EBAY_APP_ID=your-key
```

---

## Post-Deployment

### Verify Deployment

1. **Visit your URL**
   ```
   https://your-app.railway.app
   https://your-app.onrender.com
   https://your-app.fly.dev
   ```

2. **Test core features:**
   - Home page loads
   - Can scan/add ISBN
   - Database persists data
   - Lots generate correctly

### Monitor Logs

**Railway:**
- Dashboard → Deployments → View logs

**Render:**
- Service → Logs tab

**Fly.io:**
```bash
fly logs
```

### Update Deployment

**All platforms:**
```bash
git add .
git commit -m "Update app"
git push origin main
# Auto-deploys on push
```

---

## Custom Domains

### Railway
1. Settings → Domains
2. Add custom domain
3. Update DNS records as shown

### Render
1. Settings → Custom Domains
2. Add domain
3. Configure DNS

### Fly.io
```bash
fly certs create yourdomain.com
```

---

## Troubleshooting

### Build Failures

**Check requirements.txt:**
```bash
# Test locally
pip install -r requirements.txt
```

**Check Python version:**
- Ensure 3.11+ specified in config

**Check logs:**
- Platform dashboard shows build errors

### App Won't Start

**Check start command:**
```bash
# Should be:
cd isbn_web && uvicorn main:app --host 0.0.0.0 --port $PORT
```

**Check imports:**
```bash
python -c "import isbn_web; print('OK')"
```

### Database Issues

**PostgreSQL connection:**
- Verify `DATABASE_URL` set
- Check postgres:// vs postgresql://
- Ensure migrations ran

**SQLite persistence:**
- Use volume mounts or switch to PostgreSQL

### Port Issues

**Ensure using $PORT:**
```python
import os
port = int(os.getenv("PORT", 8000))
uvicorn.run(app, host="0.0.0.0", port=port)
```

---

## Cost Optimization

### Free Tier Tips

**Railway:**
- 500 hours/month = ~20 days
- Use for development/testing
- Upgrade for 24/7 uptime

**Render:**
- Spins down after 15min inactivity
- First request wakes up (~30s)
- Good for low-traffic apps

**Fly.io:**
- 3GB storage free
- Pay for usage beyond that
- Good for global distribution

### Reducing Costs

1. **Use free PostgreSQL** (if available)
2. **Optimize Docker images** (if using containers)
3. **Monitor usage** in dashboard
4. **Scale down** when not needed
5. **Use CDN** for static assets

---

## Security

### HTTPS

All platforms provide free HTTPS:
- ✅ Automatic SSL certificates
- ✅ Forced HTTPS redirect
- ✅ Certificate renewal

### Environment Variables

- ✅ Never commit API keys to git
- ✅ Use platform's secrets management
- ✅ Rotate keys periodically

### Database

- ✅ Use connection pooling
- ✅ Encrypt connections (PostgreSQL SSL)
- ✅ Regular backups

---

## Comparison: Cloud vs Local

| Aspect | Cloud Deployment | Local Server |
|--------|-----------------|--------------|
| **Access** | 🌍 Anywhere | 🏠 Local network |
| **Setup** | ☁️ 5 minutes | ⚙️ One-time setup |
| **Cost** | 💰 $0-10/month | 💡 Electricity only |
| **Maintenance** | ✅ Auto-managed | 🔧 You manage |
| **Speed** | 🌐 Internet dependent | ⚡ Very fast |
| **Privacy** | ☁️ Their servers | 🔒 Your hardware |

**Use cloud when:**
- Need remote access
- Sharing with others
- Want zero maintenance

**Use local server when:**
- Home/office use only
- Want full control
- Prefer privacy

---

## Summary

**Quickest:** Railway (5 minutes)
**Best free tier:** Render
**Global distribution:** Fly.io
**Most control:** Local server

**Next steps:**
- [Railway Guide](railway.md) - Detailed Railway instructions
- [Render Guide](render.md) - Detailed Render instructions
- [Configuration](../setup/configuration.md) - Environment variables
- [Local Server](../setup/installation.md) - Self-hosting option
