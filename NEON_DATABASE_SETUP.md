# Using Neon Database with Your Web App

Neon is an excellent serverless PostgreSQL database that works perfectly with Railway, Render, or Fly.io.

## Why Use Neon?

- ✅ Serverless PostgreSQL (auto-scales)
- ✅ Generous free tier
- ✅ Automatic backups
- ✅ Branch databases for testing
- ✅ Works with Railway, Render, Fly.io

## Setup Guide

### Step 1: Create Neon Database

1. **Sign up for Neon**
   - Go to https://neon.tech
   - Sign up with GitHub

2. **Create a Project**
   - Click "Create Project"
   - Choose a name (e.g., "isbn-lot-optimizer")
   - Select region closest to your deployment

3. **Get Connection String**
   - After creation, copy the connection string
   - Format: `postgresql://user:password@host/database?sslmode=require`
   - Keep this safe - you'll need it for deployment

### Step 2: Update Your App for PostgreSQL

1. **Add PostgreSQL driver to requirements.txt:**
   ```
   psycopg2-binary
   sqlalchemy
   ```

2. **Update isbn_web/config.py** to use DATABASE_URL:
   ```python
   import os
   from pathlib import Path
   
   # Use DATABASE_URL from environment or fallback to SQLite for local dev
   DATABASE_URL = os.getenv(
       "DATABASE_URL",
       f"sqlite:///{Path(__file__).parent / 'isbn_optimizer.db'}"
   )
   ```

3. **Update database connection** in your service/model files:
   - Replace SQLite connection with DATABASE_URL
   - Ensure SQLAlchemy uses the connection string

### Step 3: Deploy to Railway with Neon

1. **Deploy to Railway** (follow QUICK_DEPLOY.md)

2. **Add DATABASE_URL to Railway:**
   - In Railway dashboard, go to your project
   - Click "Variables"
   - Add new variable:
     - Name: `DATABASE_URL`
     - Value: Your Neon connection string

3. **Redeploy:**
   - Railway will automatically redeploy with the new variable
   - Your app now uses Neon database!

### Step 4: Run Migrations (if needed)

If you have database migrations:
```bash
# In Railway, add a migration command
railway run python -m isbn_web.migrations
```

Or set up in your app's startup to auto-migrate.

## Configuration for Each Platform

### Railway + Neon
```
Environment Variable:
DATABASE_URL = postgresql://user:pass@host/db?sslmode=require
```

### Render + Neon
Same as Railway - add DATABASE_URL in environment variables.

### Fly.io + Neon
Add to your secrets:
```bash
fly secrets set DATABASE_URL="postgresql://user:pass@host/db?sslmode=require"
```

## Local Development

Keep using SQLite locally:
- Local dev: SQLite (automatic, no setup)
- Production: Neon PostgreSQL (set DATABASE_URL)

Your code checks for DATABASE_URL and falls back to SQLite if not found.

## Benefits of This Setup

| Feature | SQLite (Local) | Neon (Production) |
|---------|---------------|-------------------|
| Setup | Zero config | One-time setup |
| Performance | Fast | Very fast |
| Scalability | Single user | Thousands of users |
| Backups | Manual | Automatic |
| Cost | Free | Free tier available |

## Testing with Neon

Neon's cool feature: **Branch databases**

1. Create a branch database for testing
2. Test your changes
3. If good, merge to main database
4. If bad, delete the branch

## Connection Pooling

For production, consider connection pooling:

```python
# In your database setup
from sqlalchemy.pool import NullPool

engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,  # Good for serverless
)
```

## Monitoring

Neon dashboard shows:
- Active connections
- Query performance
- Database size
- CPU usage

## Cost

Neon free tier includes:
- 512 MB storage
- 1 project
- Automatic backups (7 days)
- Branch databases

Perfect for your ISBN app!

## Summary

1. **Neon = Database only** (can't run your FastAPI server)
2. **Railway/Render = Runs your FastAPI server**
3. **Together = Perfect deployment stack**

**Deployment Stack:**
- Code: GitHub
- Server: Railway or Render
- Database: Neon PostgreSQL
- Result: Fast, scalable, free tier ✅

## Why Not Just Use Railway's Built-in Database?

You can! Railway includes PostgreSQL. But Neon offers:
- ✅ Better free tier
- ✅ Database branching
- ✅ Database persists if you change platforms
- ✅ Separate database management

Your choice - both work great!

---

**Next Steps:**
1. Deploy to Railway (QUICK_DEPLOY.md)
2. Set up Neon database (this guide)
3. Add DATABASE_URL to Railway
4. Done! 🚀
