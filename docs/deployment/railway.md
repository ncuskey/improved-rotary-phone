# Railway Deployment Guide

Step-by-step guide for deploying to Railway (recommended platform).

---

## Why Railway?

- ⭐ Easiest setup (5 minutes)
- ⭐ Auto-detects configuration
- ⭐ Free PostgreSQL included
- ⭐ 500 hours/month free tier
- ⭐ Auto-deploy on git push

---

## Quick Deploy

### 1. Prepare Repository

```bash
git add .
git commit -m "Ready for Railway deployment"
git push origin main
```

### 2. Create Railway Project

1. Visit https://railway.app
2. Sign in with GitHub
3. Click **"New Project"**
4. Select **"Deploy from GitHub repo"**
5. Choose your repository
6. Railway detects `railway.json` automatically

### 3. Configure Domain

1. In project dashboard, click **"Generate Domain"**
2. Your app will be at: `your-app.railway.app`
3. Or add custom domain in Settings

### 4. Done!

- Build starts automatically
- Deployment completes in 2-3 minutes
- Visit your URL to verify

---

## Configuration

Railway uses `railway.json` in your repo root:

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

**Already configured!** No changes needed.

---

## Add Database (Optional)

### Add PostgreSQL

1. In project dashboard, click **"+ New"**
2. Select **"Database" → "PostgreSQL"**
3. Railway creates database and sets `DATABASE_URL`
4. Restart your service

### Verify Connection

Check Variables tab to see `DATABASE_URL` is set.

---

## Environment Variables

### Add Variables

1. Click **"Variables"** tab
2. Click **"+ New Variable"**
3. Add your API keys:

```
EBAY_APP_ID=your-finding-app-id
EBAY_CLIENT_ID=your-browse-client-id
EBAY_CLIENT_SECRET=your-browse-secret
BOOKSCOUTER_API_KEY=your-key
HARDCOVER_API_TOKEN=Bearer your-token
```

4. Click **"Deploy"** to restart with new variables

### Railway Provides

These are set automatically:
- `PORT` - Port to listen on
- `DATABASE_URL` - If PostgreSQL added
- `RAILWAY_ENVIRONMENT` - deployment/production

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

In Railway dashboard:
1. Click **"Deploy"** button
2. Or select commit from **"Deployments"** tab

### Rollback

1. Go to **"Deployments"** tab
2. Find previous successful deployment
3. Click **"Redeploy"**

---

## Monitoring

### View Logs

1. Click **"Deployments"** tab
2. Select active deployment
3. View real-time logs

### Metrics

Dashboard shows:
- CPU usage
- Memory usage
- Request count
- Response times

---

## Domains & HTTPS

### Free Subdomain

1. Click **"Settings"**
2. Click **"Generate Domain"**
3. Get: `your-app.railway.app`
4. HTTPS automatic

### Custom Domain

1. Go to **"Settings" → "Domains"**
2. Click **"Custom Domain"**
3. Enter your domain
4. Update DNS records as shown:
   - Type: CNAME
   - Name: @
   - Value: your-app.railway.app

5. Wait for DNS propagation (5-30 minutes)
6. HTTPS certificate issued automatically

---

## Pricing

### Free Tier

- **500 hours/month** execution time
- **$5 monthly credit** (one-time, new accounts)
- **100GB outbound bandwidth**
- Ideal for testing and low-traffic apps

### Usage Tips

500 hours = ~20 days of 24/7 uptime
- Good for: Development, testing, personal use
- Consider upgrading for: Production 24/7 apps

### Paid Plans

**Hobby:** $5/month minimum
- Pay for what you use
- No execution time limits
- Priority support

**Pro:** $20/month
- Team collaboration
- Advanced features
- Higher limits

---

## Troubleshooting

### Build Fails

**Check build logs:**
- Deployments tab → Failed build → View logs
- Common issues: Missing dependencies, Python version

**Fix:**
```bash
# Test locally first
pip install -r requirements.txt
python -m isbn_web.main
```

### App Won't Start

**Check start command:**
- Should be: `cd isbn_web && uvicorn main:app --host 0.0.0.0 --port $PORT`
- Verify in railway.json

**Check environment:**
- Variables tab → Ensure `PORT` is set
- Railway sets this automatically

### Database Connection

**Verify DATABASE_URL:**
- Variables tab → Check `DATABASE_URL` exists
- Format: `postgresql://user:pass@host:port/db`

**Fix Heroku-style URLs:**
Railway sometimes uses `postgres://` instead of `postgresql://`. Update code:

```python
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./catalog.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
```

### Slow Response

**Check region:**
- Settings → Change region closer to users
- Options: US West, US East, Europe

**Add database:**
- SQLite not persistent in Railway
- Add PostgreSQL for production

---

## Best Practices

### Version Control

```bash
# Always commit before deploy
git status
git add .
git commit -m "Descriptive message"
git push
```

### Environment Variables

- ✅ Add all secrets in Railway dashboard
- ❌ Never commit `.env` to git
- ✅ Use different values for dev/prod

### Database Backups

```bash
# Export PostgreSQL backup
railway run pg_dump $DATABASE_URL > backup.sql

# Restore
railway run psql $DATABASE_URL < backup.sql
```

### Monitoring

- Check logs daily
- Set up uptime monitoring (UptimeRobot, etc.)
- Monitor usage in dashboard

---

## Advanced

### Multiple Environments

Create separate projects:
- Development
- Staging
- Production

Deploy different branches to each.

### CI/CD Integration

Railway auto-deploys from GitHub. For additional checks:

`.github/workflows/deploy.yml`:
```yaml
name: Deploy to Railway
on:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - run: pip install -r requirements.txt
      - run: pytest
  # Railway deploys automatically after tests pass
```

### Custom Build Command

Edit `railway.json`:
```json
{
  "buildCommand": "pip install -r requirements.txt && python setup.py",
  "startCommand": "cd isbn_web && uvicorn main:app --host 0.0.0.0 --port $PORT"
}
```

---

## Support

- **Docs:** https://docs.railway.app
- **Discord:** https://discord.gg/railway
- **Status:** https://railway.statuspage.io

---

## Summary

**Setup:** 5 minutes
**Cost:** Free (500 hrs/mo)
**Deploy:** Auto on git push
**Database:** PostgreSQL included
**Difficulty:** ⭐⭐⭐⭐⭐ Easiest

**Railway is the recommended platform for quick, hassle-free deployment!**

---

**Next:** [Deployment Overview](overview.md) | [Render Guide](render.md)
