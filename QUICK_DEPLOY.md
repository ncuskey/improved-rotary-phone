# Quick Deploy Guide - ISBN Lot Optimizer Web App

The fastest way to deploy your web app to the cloud!

## ⚡ Quick Start with Railway (5 minutes)

1. **Push to GitHub**
   ```bash
   git add .
   git commit -m "Ready for deployment"
   git push origin main
   ```

2. **Deploy to Railway**
   - Go to https://railway.app
   - Sign in with GitHub
   - Click "New Project" → "Deploy from GitHub repo"
   - Select your repository
   - Railway will automatically detect the configuration
   - Done! Your app will be live in 2-3 minutes

3. **Get Your URL**
   - In Railway dashboard, click "Generate Domain"
   - Your app will be available at: `your-app.railway.app`

## Files Created for Deployment

- **`Procfile`** - Tells platforms how to start your app
- **`railway.json`** - Railway-specific configuration
- **`render.yaml`** - Render-specific configuration
- **`DEPLOYMENT.md`** - Full deployment guide for all platforms

## What Gets Deployed

Only the **isbn_web** directory (the web interface) gets deployed. The desktop Python app stays local.

## Environment Variables (Optional)

If you need to add API keys or database URLs:
1. Go to your platform's dashboard
2. Find "Variables" or "Environment Variables"
3. Add your keys

## Monitoring Your App

After deployment:
- Check logs in your platform's dashboard
- Visit your deployment URL
- Test by scanning an ISBN

## Need More Help?

See **DEPLOYMENT.md** for detailed guides for Railway, Render, and Fly.io.

---

**That's it!** Your ISBN Lot Optimizer web app should now be live! 🚀
