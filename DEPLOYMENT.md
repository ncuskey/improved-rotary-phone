# ISBN Lot Optimizer - Web App Deployment Guide

This guide explains how to deploy the **isbn_web** application (web interface only) to various cloud platforms.

## Prerequisites

- Your code pushed to a Git repository (GitHub, GitLab, etc.)
- The web app is located in the `isbn_web/` directory
- Python 3.11+ required

## Deployment Options

### Option 1: Railway (Recommended - Easiest)

Railway auto-detects Python apps and handles most configuration automatically.

**Steps:**

1. **Sign up for Railway**
   - Go to https://railway.app
   - Sign up with GitHub

2. **Create New Project**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository

3. **Configure Environment Variables** (if needed)
   - In Railway dashboard, go to Variables
   - Add any required environment variables

4. **Deploy**
   - Railway will automatically detect the `railway.json` config
   - Build and deployment happen automatically
   - Your app will be available at a Railway-provided URL

**Database Note:** Railway provides free PostgreSQL. To use it:
- Add PostgreSQL service in Railway dashboard
- Update your app to use the `DATABASE_URL` environment variable

**Cost:** Free tier includes 500 hours/month and $5 credit

---

### Option 2: Render

Render is similar to Railway with a generous free tier.

**Steps:**

1. **Sign up for Render**
   - Go to https://render.com
   - Sign up with GitHub

2. **Create New Web Service**
   - Click "New +" → "Web Service"
   - Connect your GitHub repository

3. **Configure Service**
   - **Name:** isbn-lot-optimizer
   - **Region:** Choose closest to you
   - **Branch:** main (or your default branch)
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `cd isbn_web && uvicorn main:app --host 0.0.0.0 --port $PORT`

4. **Select Plan**
   - Choose "Free" tier for testing

5. **Deploy**
   - Click "Create Web Service"
   - Render will build and deploy automatically

**Database Note:** Render offers free PostgreSQL (expires after 90 days)

**Cost:** Free tier available (spins down after inactivity)

---

### Option 3: Fly.io

Fly.io offers global deployment with a free tier.

**Steps:**

1. **Install Fly CLI**
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Login to Fly**
   ```bash
   fly auth login
   ```

3. **Create fly.toml** (if not exists)
   ```bash
   fly launch
   ```
   - Choose a name for your app
   - Choose a region
   - Don't deploy yet - we need to configure

4. **Configure fly.toml**
   Edit the generated `fly.toml` to ensure it has:
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

**Database Note:** Fly.io has PostgreSQL add-on available

**Cost:** Free tier includes 3GB storage

---

## Database Considerations

### Current Setup (SQLite)
The app currently uses SQLite, which works fine for development but has limitations in cloud environments:
- May not persist between deployments
- Not suitable for multiple instances
- Limited to single-node deployments

### Recommended: PostgreSQL
For production, switch to PostgreSQL:

1. **Update requirements.txt:**
   ```
   psycopg2-binary
   ```

2. **Update database configuration** in `isbn_web/config.py`:
   - Use `DATABASE_URL` environment variable
   - Format: `postgresql://user:password@host:port/database`

3. **All platforms offer PostgreSQL:**
   - Railway: Built-in PostgreSQL service
   - Render: Free PostgreSQL (with limits)
   - Fly.io: Fly Postgres

---

## Environment Variables

Set these environment variables in your deployment platform:

- `PORT` - Automatically provided by most platforms
- `DATABASE_URL` - If using PostgreSQL (optional for SQLite)
- Any API keys your app uses (eBay, etc.)

---

## Post-Deployment

After deployment:

1. **Check logs** to ensure app started correctly
2. **Test the web interface** by visiting your deployment URL
3. **Scan an ISBN** to verify functionality
4. **Monitor performance** and adjust resources as needed

---

## Troubleshooting

### App won't start
- Check logs for Python errors
- Verify all dependencies are in `requirements.txt`
- Ensure Python version is 3.11+

### Database errors
- Verify `DATABASE_URL` is set correctly
- Check database migrations ran
- Ensure database is accessible from your app

### Static files not loading
- Verify static file paths in templates
- Check web server configuration
- Ensure static directory is included in deployment

---

## Local Testing Before Deployment

Always test locally before deploying:

```bash
cd isbn_web
uvicorn main:app --host 0.0.0.0 --port 8000
```

Visit http://localhost:8000 to verify everything works.

---

## Need Help?

- Railway: https://docs.railway.app
- Render: https://render.com/docs
- Fly.io: https://fly.io/docs

## Summary

**Easiest:** Railway (auto-detects everything)
**Most Features:** Render (good free tier, easy to use)
**Global:** Fly.io (best for worldwide users)

All three options will work well for the ISBN Lot Optimizer web app!
