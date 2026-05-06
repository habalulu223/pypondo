# PyPondo Complete Deployment Architecture

## System Overview

Your PyPondo system now has a complete production deployment setup with Netlify (frontend) and Railway (backend).

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Global Users                                 │
└────────────────────────┬────────────────────────────────────────────┘
                         │
         ┌───────────────┴────────────────┐
         │                                 │
    ┌────▼─────────────────────┐  ┌──────▼──────────────────────┐
    │  Netlify CDN              │  │  Mobile/Desktop Apps        │
    │  your-site.netlify.app    │  │  (Auto-discover & connect)  │
    │  - React Frontend         │  │                             │
    │  - 300 free builds/mo     │  └──────┬──────────────────────┘
    │  - Global distribution    │         │
    │  - HTTPS included         │         │
    └────┬──────────────────────┘         │
         │                                 │
         └──────────────┬──────────────────┘
                        │
         ┌──────────────▼──────────────────┐
         │   API Routing (Netlify.toml)    │
         │   /api/* → Railway backend      │
         └──────────────┬──────────────────┘
                        │
         ┌──────────────▼───────────────────────────────┐
         │  Railway.app                                  │
         │  your-app-xxx.railway.app                     │
         │  - Flask Backend                              │
         │  - Auto-scales                                │
         │  - $5/month free tier credit                  │
         └──────────────┬───────────────────────────────┘
                        │
         ┌──────────────▼───────────────────────────────┐
         │  Business Logic & Data                        │
         │  - Authentication                             │
         │  - Booking Management                         │
         │  - Payments Processing                        │
         │  - LAN Agent Commands                         │
         └──────────────┬───────────────────────────────┘
                        │
         ┌──────────────▼───────────────────────────────┐
         │  Database                                     │
         │  ├─ SQLite (development)                      │
         │  └─ PostgreSQL (production via Railway)       │
         └──────────────────────────────────────────────┘
```

## Deployment Files Created

### Frontend (Netlify)
```
pypondo/
├── netlify.toml                  ← Netlify configuration
├── NETLIFY_DEPLOYMENT_GUIDE.md   ← Frontend deployment docs
├── NETLIFY_QUICK_START.md        ← Quick reference
└── PyPondoMobile/pypondo-web/
    ├── .env.example              ← Environment template
    ├── src/api/config.ts         ← API client
    └── vite.config.ts            ← Build config
```

### Backend (Railway)
```
pypondo/
├── railway.json                  ← Root-level Railway config (NEW)
├── Procfile                      ← Startup script (NEW)
├── RAILWAY_DEPLOYMENT_GUIDE.md   ← Backend deployment docs (NEW)
├── RAILWAY_QUICK_START.md        ← Quick reference (NEW)
└── PythonProject/
    ├── railway.toml              ← Project-level config (NEW)
    ├── app.py                    ← Flask app (already 0.0.0.0 ready)
    ├── requirements.txt          ← Dependencies
    └── start_tunneling.ps1       ← ngrok for development
```

### Universal
```
pypondo/
├── GETTING_STARTED_NETLIFY.md    ← Getting started guide
├── setup_netlify.py              ← Setup helper script
└── NETLIFY_DEPLOYMENT_CHECKLIST.md ← Step-by-step checklist
```

## Architecture Components

### 1. Frontend (Netlify)

**Purpose**: Serve React app to users worldwide

**Key Features**:
- Global CDN distribution
- Automatic HTTPS
- SPA routing (refresh works)
- 300 free build minutes/month
- Auto-deploy from GitHub

**Configuration**:
- `netlify.toml` - build settings, redirects, headers
- `.env.example` - environment variables
- `src/api/config.ts` - API client with env-based URLs

**API Routing**:
```toml
[[redirects]]
  from = "/api/*"
  to = "https://your-railway-url/api/:splat"
```

### 2. Backend (Railway)

**Purpose**: Run Flask app with auto-scaling

**Key Features**:
- $5/month free credit
- Auto-scaling infrastructure
- PostgreSQL included
- Automatic deployments from GitHub
- Health checks included

**Configuration**:
- `railway.json` (root) - Main deploy config
- `requirements.txt` (root) - Points Railpack to `PythonProject/requirements.txt`
- `Procfile` (root) - Fallback startup command
- `PythonProject/railway.toml` - Project config

**What It Does**:
1. Clones repository
2. Reads `railway.json`
3. Finds root Python markers (`requirements.txt`, `railway.json`, `Procfile`)
4. Installs dependencies from `PythonProject/requirements.txt`
5. Runs `python app.py`
6. Uses the Railway-provided `PORT`
7. Provides HTTPS URL

### 3. Database

**Development**: SQLite in PythonProject/
```
pccafe.db
```

**Production**: PostgreSQL (Railway provision)
```
DATABASE_URL env var (auto-provided)
```

### 4. Environment Variables

**Frontend** (Netlify UI):
```
VITE_API_URL=https://your-railway-url
VITE_API_TIMEOUT=30000
```

**Backend** (Railway Dashboard):
```
FLASK_HOST=0.0.0.0
ALLOWED_ORIGINS=https://your-site.netlify.app,https://your-railway-url
PYPONDO_DB_PATH=/app/data/pccafe.db
DATABASE_URL=<auto from PostgreSQL>
```

## Deployment Flow

### Initial Setup

```
1. Push to GitHub
   ├─ Includes railway.json (tells Railway about PythonProject/)
   ├─ Includes netlify.toml (tells Netlify how to build)
   └─ Includes Procfile (startup script)

2. Connect Netlify to GitHub
   ├─ Auto-detects netlify.toml
   └─ Builds PyPondoMobile/pypondo-web/

3. Connect Railway to GitHub
   ├─ Auto-detects railway.json
   ├─ Finds PythonProject/ directory
   └─ Builds and runs Flask app

4. Get URLs
   ├─ Netlify: your-site.netlify.app
   └─ Railway: your-app-xxx.railway.app

5. Update Netlify environment variables
   └─ Set VITE_API_URL to Railway URL

6. Configure Backend CORS
   └─ Set ALLOWED_ORIGINS to Netlify URL

7. Live! 🎉
```

### Ongoing Deployments

```
Developer pushes to main
    ↓
GitHub notifies Netlify & Railway
    ↓
Both trigger builds simultaneously
    ↓
Netlify rebuilds frontend
Railway rebuilds backend
    ↓
Both deploy new versions
    ↓
Users get latest version automatically
```

## The Key Fix

The issue was that Railway was scanning the repo root and finding:
- Documentation files
- Helper scripts
- Configuration files

But NOT finding:
- app.py (was in PythonProject/)
- requirements.txt (was in PythonProject/)

**Solution**: make the repo root deployable by adding root Python markers:
```txt
requirements.txt -> -r PythonProject/requirements.txt
railway.json -> startCommand: python app.py
Procfile -> web: python app.py
```

This lets Railpack detect the app even when it scans the repository root.

**Optional dashboard setting**: if you want Railway to build directly from the subdirectory instead,
set the service Root Directory to `PythonProject` in the Railway dashboard. That setting is
dashboard-only and is not applied from `railway.json`.

## Cost Breakdown

| Service | Tier | Cost/Month | Notes |
|---------|------|-----------|-------|
| Netlify | Free | $0 | 300 build min, unlimited bandwidth |
| Railway | Free | $0-5 | $5 monthly credit, auto-scales |
| Domain | Optional | $10-15 | Custom domain (not required) |
| **Total** | **Free** | **$0-5** | Fully hosted in free tier |

## Development vs Production

### Development
```
Local machine:
- Python virtual env
- Flask app on localhost:5000
- ngrok tunnel for testing remote
- SQLite database
- npm dev server on localhost:3000
```

### Production
```
GitHub:
- Single source of truth
- All configuration files committed

Netlify:
- React app served globally
- Auto-deploys on push

Railway:
- Flask backend
- PostgreSQL database
- Auto-scales
- Auto-deploys on push

Users:
- Visit your-site.netlify.app
- API calls routed to Railway
- Fast, secure, reliable
```

## File Dependencies

```
railway.json (root)
    ├─ Points to PythonProject/
    └─ Railway reads this first

Procfile (root)
    ├─ Uses web: python app.py
    └─ Fallback startup path

PythonProject/railway.toml
    ├─ Additional configuration
    └─ Health checks, buildpacks

netlify.toml (root)
    ├─ Build frontend
    ├─ SPA routing
    └─ API redirects to Railway

netlify.toml also specifies:
    └─ VITE_API_URL → Railway URL
```

## Verification Checklist

- [ ] `railway.json` exists at repo root
- [ ] `railway.json` starts with `python app.py`
- [ ] `requirements.txt` exists at repo root
- [ ] `Procfile` exists at repo root
- [ ] `Procfile` has `web: python app.py`
- [ ] `PythonProject/railway.toml` exists
- [ ] `PythonProject/app.py` exists
- [ ] `PythonProject/requirements.txt` exists
- [ ] `app.py` uses `host='0.0.0.0'` (it does by default)
- [ ] All pushed to GitHub main branch
- [ ] Railway project created and linked
- [ ] Netlify project created and linked
- [ ] Both have green build status ✅

## Testing the Connection

### Test Backend URL
```bash
# Replace with your Railway URL
curl https://your-app-xxx.railway.app/api/health
```

### Test Frontend Access
```bash
# Visit in browser
https://your-site.netlify.app
# Check browser console (F12) for errors
```

### Test from Mobile/Desktop
```bash
# Should auto-discover Netlify URL
python desktop_app.py
```

## Troubleshooting Deployment

### Railway Build Fails

**Check these in order**:

1. Does `railway.json` exist at repo root?
   ```bash
   git log --all --full-history -- railway.json
   ```

2. Does it start the app from the package root?
   ```json
   "startCommand": "python app.py"
   ```

3. Are files in PythonProject/?
   ```bash
   ls -la PythonProject/app.py
   ls -la PythonProject/requirements.txt
   ```

4. Is there a root `requirements.txt` that points to the subdirectory?
   ```txt
   -r PythonProject/requirements.txt
   ```

4. Push and check Railway logs:
   ```bash
   git push origin main
   # Go to Railway Dashboard → Logs
   ```

### Netlify Build Fails

**Check**:
1. Are Node.js dependencies correct?
2. Does build command work locally?
   ```bash
   cd PyPondoMobile/pypondo-web
   npm run build
   ```
3. Check Netlify deploy logs

### CORS Errors

**In browser console**: `Access to XMLHttpRequest blocked by CORS policy`

**Fix**:
1. Get your Netlify URL
2. Set in Railway environment:
   ```
   ALLOWED_ORIGINS=https://your-site.netlify.app
   ```
3. Redeploy Railway
4. Test again

## Next Steps

1. **Commit & Push**
   ```bash
   git add railway.json Procfile PythonProject/railway.toml
   git commit -m "Add Railway deployment configuration"
   git push origin main
   ```

2. **Deploy Backend**
   - Go to https://railway.app
   - Create project
   - Connect GitHub
   - Watch build logs
   - Copy Railway URL

3. **Deploy Frontend**
   - Go to https://netlify.com
   - Create project
   - Connect GitHub
   - Update environment variables
   - Watch build logs

4. **Connect Them**
   - Update netlify.toml with Railway URL
   - Set ALLOWED_ORIGINS on Railway
   - Test API from frontend

5. **Go Live** 🚀

## Resources

- [Railway Docs](https://docs.railway.app)
- [Railway Python Guide](https://docs.railway.app/guides/native-python)
- [Netlify Docs](https://docs.netlify.com)
- [Vite Docs](https://vitejs.dev)
- [Flask Docs](https://flask.palletsprojects.com)

---

## Summary

✅ **Frontend**: Netlify - React app served globally  
✅ **Backend**: Railway - Flask app with auto-scaling  
✅ **Database**: SQLite (dev) or PostgreSQL (prod)  
✅ **Configuration**: All files in place  
✅ **Ready**: Just push to GitHub and deploy!

**Status**: Production-ready. Next: Push to GitHub and follow deployment steps above.
