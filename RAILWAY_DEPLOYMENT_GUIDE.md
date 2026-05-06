# PyPondo Railway Deployment Guide

## Overview

Railway.app can deploy the PyPondo backend directly from the repo root. This guide uses a root-level `requirements.txt` plus a module start command so Railpack recognizes Python without depending on a monorepo root-directory setting.

## Problem Solved

**Previous Issue**: Railway was scanning the repo root and finding mostly documentation, so Railpack could not identify a Python app.

**Solution**: The repo root now exposes Python project markers and starts the backend with `python app.py`. A root wrapper delegates to `PythonProject/app.py`, so the same start command also works if Railway is pointed directly at `PythonProject`.

## Files Added

1. **`railway.json`** (repo root) - Railway deploy configuration
2. **`Procfile`** (repo root) - Fallback start command
3. **`requirements.txt`** (repo root) - Forwards dependency install to `PythonProject/requirements.txt`
4. **`PythonProject/__init__.py`** - Lets Railway start the backend as a package module
5. **`PythonProject/railway.toml`** - Optional project-level config if you use a Railway subdirectory setup

## Quick Deploy (3 Steps)

### Step 1: Create Railway Account
1. Go to https://railway.app
2. Sign up (free tier available)
3. Create new project

### Step 2: Connect GitHub
1. Click "New Project"
2. Select "Deploy from GitHub"
3. Authorize Railway to access your GitHub
4. Select your `pypondo` repository
5. Railway automatically detects the root `requirements.txt` and `railway.json`

### Step 3: Deploy
Railway will automatically:
- ✅ Detect Python from the repo root
- ✅ Install dependencies from `requirements.txt` → `PythonProject/requirements.txt`
- ✅ Run `python app.py`
- ✅ Provide public HTTPS URL

## Configuration Details

### railway.json (Repo Root)

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "deploy": {
    "startCommand": "python app.py",
    "healthcheckPath": "/api/health"
  }
}
```

**Key Settings**:
- `startCommand`: Starts the backend from the repo root
- `healthcheckPath`: Lets Railway wait for a healthy HTTP response
- `$schema`: Enables editor validation for Railway config

### Procfile (Root Directory)

```
web: python app.py
```

**Purpose**: Fallback start command that Railpack recognizes

### PythonProject/railway.toml

This file is optional if you deploy from the repo root. Keep it only if you choose to deploy `PythonProject` as a dedicated Railway root directory from the dashboard.

## Environment Variables

Set in Railway Dashboard → Project Settings → Variables:

```
FLASK_HOST=0.0.0.0
ALLOWED_ORIGINS=https://your-site.netlify.app,https://your-railway-url.railway.app
PYPONDO_DB_PATH=/app/data/pccafe.db
PYPONDO_DISABLE_BILLING=0
```

**Important**: Don't hardcode secrets in config files!

## Setting Up Railway Deployment

### Via Railway CLI

```powershell
# Install Railway CLI
npm install -g railway

# Login
railway login

# Initialize project (from repo root)
railway init

# Deploy
railway up
```

If you prefer deploying only the subdirectory permanently, set the service Root Directory to `PythonProject` in the Railway dashboard.

### Via GitHub Actions (Auto-Deploy)

Railway automatically deploys when you push to main:

```bash
git add .
git commit -m "Add Railway configuration"
git push origin main
```

## Verifying Deployment

### Check Build Logs
1. Go to Railway Dashboard
2. Select your project
3. View build logs for any errors

### Test Endpoint
```bash
# Replace with your Railway URL
curl https://your-railway-url.railway.app/api/health

# Should return: {"status":"ok"} or similar
```

### Monitor Running App
```powershell
railway logs
```

## Database Setup

### Option 1: SQLite (Default)
Database file stored at: `/app/data/pccafe.db`

Create data directory if needed:
```python
# In app.py, add:
import os
os.makedirs('/app/data', exist_ok=True)
```

### Option 2: PostgreSQL
Railway can provision PostgreSQL:

1. Click "Add Service" → "PostgreSQL"
2. Railway creates `DATABASE_URL` automatically
3. Update app.py to use PostgreSQL:

```python
# Instead of:
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///...'

# Use:
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
```

## Troubleshooting

### Build Fails: "No project files found"

**Problem**: Railway still scans root directory

**Solution**:
1. Verify the repo root has `requirements.txt`
2. Verify `Procfile` exists at root with: `python app.py`
3. Delete Railway cache:
   - Go to Settings → Variables
   - Clear all
   - Re-deploy

### App Starts but API Returns 404

**Problem**: App runs but endpoints not working

**Check**:
1. Is Flask listening on 0.0.0.0?
   ```python
   if __name__ == '__main__':
       app.run(host='0.0.0.0', port=5000)
   ```

2. Is database initialized?
   ```bash
   railway logs
   ```

3. Check ALLOWED_ORIGINS includes your domain

### Database File Not Persisting

**Problem**: Data lost after redeploy

**Solution**: Use PostgreSQL or create proper data volume:
1. Go to Project Settings → Volumes
2. Add volume pointing to `/app/data`

## Getting Your Railway URL

After deployment succeeds:
1. Go to Railway Dashboard
2. Select project
3. Click on the service
4. Copy URL from "Public Domain"

**Format**: `https://your-project-xxx.railway.app`

## Connecting to Netlify

Update your `netlify.toml`:

```toml
[context.production.environment]
  VITE_API_URL = "https://your-project-xxx.railway.app"

[[redirects]]
  from = "/api/*"
  to = "https://your-project-xxx.railway.app/api/:splat"
```

Then set environment variable in Netlify Dashboard:
- `VITE_API_URL = https://your-project-xxx.railway.app`

## Update Backend CORS

Set in Railway variables:
```
ALLOWED_ORIGINS=https://your-site.netlify.app,https://your-project-xxx.railway.app,http://localhost:3000
```

## Cost & Limits

| Item | Free Tier |
|------|-----------|
| Usage Credit | $5/month |
| Deployments | Unlimited |
| Databases | 1 PostgreSQL |
| Regions | Multiple |
| HTTPS | ✅ Included |

Typical PyPondo setup costs $0-5/month on free tier.

## Advanced: Custom Domain

1. Go to Project Settings → Custom Domains
2. Add your domain
3. Follow DNS setup instructions
4. Wait for DNS propagation (up to 24 hours)

## Monitoring & Logs

```bash
# View real-time logs
railway logs --follow

# View specific service logs
railway logs -s pypondo-backend

# View environment variables
railway variables list
```

## Auto-Scaling

Railway automatically scales based on traffic. For production:
1. Go to Service Settings
2. Adjust Memory/CPU as needed
3. Set restart policy

## Deployment Checklist

- [ ] `railway.json` exists in repo root
- [ ] `Procfile` exists in repo root
- [ ] `PythonProject/railway.toml` exists
- [ ] `PythonProject/requirements.txt` includes all dependencies
- [ ] `PythonProject/app.py` runs `app.run(host='0.0.0.0')`
- [ ] GitHub account connected to Railway
- [ ] Repository pushed to GitHub
- [ ] Railway project created and linked to GitHub
- [ ] Environment variables set in Railway Dashboard
- [ ] Build succeeds (check logs)
- [ ] App starts (check logs)
- [ ] API endpoint responds (curl test)
- [ ] Netlify frontend can reach API
- [ ] Mobile/desktop apps configured with Railway URL

## Next Steps

1. Push changes to GitHub
   ```bash
   git add railway.json Procfile PythonProject/railway.toml
   git commit -m "Add Railway configuration for PythonProject"
   git push origin main
   ```

2. Go to https://railway.app
3. Create new project and connect GitHub
4. Watch deployment logs
5. Get public URL
6. Update Netlify configuration

## Support

- [Railway Docs](https://docs.railway.app)
- [Railway Discord](https://discord.gg/railway)
- [Python on Railway](https://docs.railway.app/guides/native-python)

---

**Status**: ✅ Ready to deploy to Railway

Your PyPondo backend is now configured for Railway deployment!
