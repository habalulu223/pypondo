# Railway Deployment - Quick Start

## Problem Fixed ✅

Railway can now build from the repo root because the root exposes Python markers and starts the backend with `python app.py`.

## 1-Minute Setup

### Step 1: Push to GitHub
```bash
cd c:\Users\PC\ 12\PycharmProjects\pypondo
git add railway.json Procfile requirements.txt PythonProject/__init__.py PythonProject/app.py
git commit -m "Add Railway configuration"
git push origin main
```

### Step 2: Deploy to Railway
1. Go to https://app.railway.app
2. Create account (free)
3. Click "New Project"
4. Select "Deploy from GitHub"
5. Choose your `pypondo` repository
6. Railway detects the root `requirements.txt` and `railway.json`
7. Watch it build & deploy

### Step 3: Get Your URL
After deployment succeeds:
- Railway Dashboard → Your Project
- Copy the public domain URL
- Format: `https://pypondo-xxx.railway.app`

### Step 4: Connect to Netlify
Update `netlify.toml`:
```toml
[context.production.environment]
  VITE_API_URL = "https://pypondo-xxx.railway.app"

[[redirects]]
  from = "/api/*"
  to = "https://pypondo-xxx.railway.app/api/:splat"
```

## Files Created

| File | Purpose |
|------|---------|
| `railway.json` | Main Railway config |
| `Procfile` | Fallback startup script |
| `requirements.txt` | Root Python dependency marker for Railpack |
| `PythonProject/__init__.py` | Makes module startup work |
| `RAILWAY_DEPLOYMENT_GUIDE.md` | Full documentation |

## Key Configuration

**railway.json** tells Railway:
```json
"startCommand": "python app.py"
```

**Procfile** tells Railway how to start:
```
web: python app.py
```

## What Railway Does Automatically

✅ Detects Python from the repo root  
✅ Installs from root `requirements.txt`  
✅ Runs `python app.py`  
✅ Provides HTTPS URL  
✅ Auto-deploys on GitHub push  
✅ Manages environment variables  

## Set Environment Variables

In Railway Dashboard → Variables:
```
FLASK_HOST=0.0.0.0
ALLOWED_ORIGINS=https://your-site.netlify.app
PYPONDO_DB_PATH=/app/data/pccafe.db
```

## Test It

```bash
# After Railway URL is ready
curl https://your-railway-url/api/health
```

Should return API response (not 404).

## Cost

- Free tier: $5/month credit (usually free)
- Typically costs $0-2/month for PyPondo

## Troubleshooting

**Build fails?**
1. Check Railway logs
2. Verify root `requirements.txt` exists
3. Verify `PythonProject/app.py` exists
4. If you insist on subdirectory deploys, set Railway Root Directory to `PythonProject`

**API returns 404?**
1. Check app is listening on 0.0.0.0
2. Check ALLOWED_ORIGINS includes your domain
3. Check `railway logs` for errors

**Database issues?**
1. Use PostgreSQL instead of SQLite for production
2. Add volume in Railway for data persistence

## Complete Flow

```
Your GitHub repo (with root requirements.txt and railway.json)
        ↓
Railway detects push
        ↓
Railway sees a Python project at the repo root
        ↓
Builds PythonProject/ as root
        ↓
Installs requirements.txt
        ↓
Runs: python app.py
        ↓
HTTPS URL provided
        ↓
Connected to Netlify frontend ✅
```

## Next Steps

1. **Now**: Push config files to GitHub
2. **Go to**: https://app.railway.app
3. **Connect**: GitHub repository
4. **Watch**: Build logs
5. **Copy**: Public URL
6. **Update**: netlify.toml
7. **Deploy**: Netlify frontend

---

**Status**: ✅ Ready - Just push to GitHub and Railway will handle the rest!

See [RAILWAY_DEPLOYMENT_GUIDE.md](RAILWAY_DEPLOYMENT_GUIDE.md) for detailed instructions.
