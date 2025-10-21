# Render Deployment Guide

Step-by-step guide for deploying to Render.

---

## Why Render?

- ⭐ Generous free tier
- ⭐ Simple setup
- ⭐ Auto-deploy from GitHub
- ⭐ Free PostgreSQL (90 days)
- ⭐ No credit card required for free tier

---

## Quick Deploy

### 1. Prepare Repository

```bash
git add .
git commit -m "Ready for Render deployment"
git push origin main
```

### 2. Create Web Service

1. Visit https://render.com
2. Sign in with GitHub
3. Click **"New +"** → **"Web Service"**
4. Connect your GitHub repository
5. Select the repository

### 3. Configure Service

Fill in the form:

- **Name:** `isbn-lot-optimizer`
- **Region:** Choose closest to you
- **Branch:** `main`
- **Root Directory:** (leave blank)
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `cd isbn_web && uvicorn main:app --host 0.0.0.0 --port $PORT`

### 4. Select Plan

Choose **Free** tier:
- ✅ Automatic sleep after 15min inactivity
- ✅ Wakes on first request (~30s)
- ✅ Perfect for testing/low-traffic

### 5. Create Service

Click **"Create Web Service"**
- Build starts automatically
- First deploy takes 3-5 minutes
- Visit your URL when ready

---

## Configuration

Render uses `render.yaml` in your repo root:

```yaml
services:
  - type: web
    name: isbn-lot-optimizer
    env: python
    region: oregon
    buildCommand: pip install -r requirements.txt
    startCommand: cd isbn_web && uvicorn main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.0
```

**Already configured!** Render detects this automatically.

---

## Add Database (Optional)

### Add PostgreSQL

1. Click **"New +"** → **"PostgreSQL"**
2. Name your database
3. Select region (same as web service)
4. Choose **Free** tier
5. Click **"Create Database"**

### Connect to Web Service

1. Go to your web service settings
2. Click **"Environment"** tab
3. Add variable:
   - **Key:** `DATABASE_URL`
   - **Value:** (copy from PostgreSQL dashboard → "Internal Database URL")

4. Save and redeploy

**Note:** Free PostgreSQL expires after 90 days. Upgrade to paid for persistence.

---

## Environment Variables

### Add Variables

1. Go to web service dashboard
2. Click **"Environment"** tab
3. Click **"Add Environment Variable"**
4. Add your API keys:

```
EBAY_APP_ID = your-finding-app-id
EBAY_CLIENT_ID = your-browse-client-id
EBAY_CLIENT_SECRET = your-browse-secret
BOOKSCOUTER_API_KEY = your-key
HARDCOVER_API_TOKEN = Bearer your-token
```

5. Click **"Save Changes"**
6. Service redeploys automatically

### Render Provides

These are set automatically:
- `PORT` - Port to listen on (10000)
- `RENDER` - true (indicates Render environment)
- `IS_PULL_REQUEST` - true/false

---

## Deployment

### Auto-Deploy

Every `git push` triggers deployment:

```bash
git add .
git commit -m "Update feature"
git push origin main
# Deploys automatically
```

### Manual Deploy

In Render dashboard:
1. Click **"Manual Deploy"** button
2. Select branch
3. Click **"Deploy"**

### Disable Auto-Deploy

1. Settings tab
2. Uncheck **"Auto-Deploy"**
3. Use manual deploy instead

---

## Monitoring

### View Logs

1. Click **"Logs"** tab
2. View real-time logs
3. Filter by log level

### Metrics

Dashboard shows:
- Memory usage
- CPU usage
- Bandwidth
- Request count

### Alerts

Set up email alerts:
1. Settings → **"Notifications"**
2. Add email address
3. Select events (deploy fail, service down, etc.)

---

## Domains & HTTPS

### Free Subdomain

Automatically provided:
- Format: `your-app.onrender.com`
- HTTPS enabled by default

### Custom Domain

1. Go to **"Settings"** tab
2. Scroll to **"Custom Domains"**
3. Click **"Add Custom Domain"**
4. Enter your domain: `yourdomain.com`
5. Update DNS records:
   - **Type:** CNAME
   - **Name:** `@` or `www`
   - **Value:** `your-app.onrender.com`

6. Wait for DNS propagation (5-60 minutes)
7. SSL certificate issued automatically

---

## Pricing

### Free Tier

- ✅ **Automatic sleep** after 15min inactivity
- ✅ **750 hours/month** execution time
- ✅ **100GB bandwidth/month**
- ✅ **No credit card** required

**Sleep behavior:**
- Service sleeps after 15min with no requests
- First request wakes it up (~30 seconds)
- Subsequent requests are fast

### Paid Plans

**Starter:** $7/month per service
- No sleep
- 24/7 uptime
- 512MB RAM
- Persistent disk

**Standard:** $25/month per service
- 2GB RAM
- Priority support
- Higher limits

**Advanced:** Custom pricing
- Dedicated resources
- SLA
- Custom regions

---

## Troubleshooting

### Build Fails

**Check build logs:**
- Dashboard → Logs tab → Filter: Build
- Common issues: Missing dependencies, wrong Python version

**Fix:**
```bash
# Test locally
pip install -r requirements.txt
python -m py_compile isbn_web/*.py
```

### Service Won't Start

**Check start command:**
```bash
# Should be:
cd isbn_web && uvicorn main:app --host 0.0.0.0 --port $PORT
```

**Verify in:** Settings → Build & Deploy

**Check logs:**
- Logs tab → Filter: Deploy
- Look for import errors or port issues

### Slow Wake-Up (Free Tier)

**Expected behavior:**
- Service sleeps after 15min inactivity
- First request takes ~30 seconds to wake
- This is normal for free tier

**Solutions:**
1. **Upgrade to Starter** ($7/mo) - No sleep
2. **Use cron job** to ping every 14 minutes (keeps awake)
3. **Accept wake time** for low-traffic apps

**Ping script:**
```bash
# Add to crontab or use service like UptimeRobot
*/14 * * * * curl https://your-app.onrender.com > /dev/null 2>&1
```

### Database Connection

**Verify DATABASE_URL:**
- Environment tab → Check `DATABASE_URL` exists
- Use "Internal Database URL" not "External"

**Fix Heroku-style URLs:**
```python
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
```

### Free Database Expiration

**90-day limit:**
- Free PostgreSQL expires after 90 days
- You'll receive email warnings
- Upgrade to paid ($7/mo) or migrate data

**Backup before expiration:**
```bash
# Export data
pg_dump DATABASE_URL > backup.sql

# After creating paid database
psql NEW_DATABASE_URL < backup.sql
```

---

## Best Practices

### Health Checks

Render automatically pings `/` for health checks.

Add a health endpoint:
```python
@app.get("/health")
async def health():
    return {"status": "healthy"}
```

Then in Render Settings:
- **Health Check Path:** `/health`

### Environment Separation

Create separate services:
- **Development:** Deploy from `dev` branch
- **Production:** Deploy from `main` branch

### Scheduled Tasks

Use **Cron Jobs** (paid feature):
1. New + → Cron Job
2. Set schedule: `0 0 * * *` (daily at midnight)
3. Command: `python scripts/daily_task.py`

### Persistent Storage

Free tier has **no persistent disk**. For file uploads:
1. Use PostgreSQL for data
2. Use S3/Cloudinary for images
3. Or upgrade to paid tier with disk

---

## Advanced

### Blue-Green Deployments

1. Create second service (staging)
2. Test on staging URL
3. Swap custom domain to staging
4. Zero-downtime deployment

### Docker Support

Use custom Dockerfile:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY isbn_web ./isbn_web
CMD ["uvicorn", "isbn_web.main:app", "--host", "0.0.0.0", "--port", "10000"]
```

Render auto-detects and builds.

### Private Services

**Internal services** (not exposed to internet):
- Use for background workers
- Only accessible by other Render services
- No external URL

---

## Support

- **Docs:** https://render.com/docs
- **Community:** https://community.render.com
- **Status:** https://status.render.com
- **Support:** support@render.com (paid plans)

---

## Summary

**Setup:** 10 minutes
**Cost:** Free (with sleep)
**Deploy:** Auto on git push
**Database:** PostgreSQL (90 days free)
**Difficulty:** ⭐⭐⭐⭐ Easy

**Best for:** Low-traffic apps, testing, generous free tier

---

**Next:** [Deployment Overview](overview.md) | [Railway Guide](railway.md)
