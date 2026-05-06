# PyPondo Online Deployment - Getting Started

Welcome! Your PyPondo system is now configured for online hosting via **Netlify** with tunneling support. This document explains what's been set up and how to get started.

## What's New

Your PyPondo project now has complete Netlify deployment support:

✅ **Frontend** hosted globally on Netlify CDN  
✅ **Backend** tunneled securely to your local server or cloud hosting  
✅ **Mobile & Desktop** apps configured for remote URLs  
✅ **CORS** security configured for cross-origin requests  
✅ **Documentation** and scripts for easy deployment  

## Files Added

### Configuration Files
- `netlify.toml` - Netlify build and deployment settings
- `PyPondoMobile/pypondo-web/.env.example` - Environment template
- `PyPondoMobile/pypondo-web/src/api/config.ts` - API client config
- `PythonProject/requirements.txt` - Python dependencies with flask-cors

### Documentation
- `NETLIFY_DEPLOYMENT_GUIDE.md` - **Complete reference** (read this first!)
- `NETLIFY_QUICK_START.md` - **5-minute quick start**
- `NETLIFY_DEPLOYMENT_CHECKLIST.md` - Step-by-step checklist

### Helper Scripts
- `setup_netlify.py` - Automated setup helper
- `PythonProject/start_tunneling.ps1` - Start ngrok (PowerShell)
- `PythonProject/start_tunneling.bat` - Start ngrok (batch)

### Backend Updates
- `PythonProject/app.py` - Now includes Flask-CORS support

## Quick Start (5 Minutes)

### 1. Install ngrok for Backend Tunneling
```powershell
# Download from: https://ngrok.com/download
# Or install via Chocolatey:
choco install ngrok
```

### 2. Start Your Backend
```powershell
cd PythonProject
python app.py
```

### 3. Tunnel It to Internet
```powershell
# In another terminal
python start_tunneling.ps1

# Or manually:
ngrok http 5000
```

You'll see:
```
Forwarding    https://abc123def45.ngrok.io -> http://localhost:5000
```

Copy that URL (e.g., `https://abc123def45.ngrok.io`)

### 4. Update Configuration
Edit `netlify.toml` and replace:
```
https://your-backend.herokuapp.com
```

With your ngrok URL:
```
https://abc123def45.ngrok.io
```

### 5. Deploy to Netlify
```bash
cd PyPondoMobile/pypondo-web

# Build
npm install
npm run build

# Deploy (choose one)
# Option A: Using Netlify CLI
netlify deploy --prod

# Option B: Using GitHub (recommended)
git add .
git commit -m "Setup Netlify deployment"
git push origin main
# Then go to app.netlify.com and connect your repo
```

## Architecture

```
Internet Users
    ↓
Netlify CDN (your-site.netlify.app)
    ↓
Frontend (React/Vite)
    ↓ API calls
Backend Tunnel (ngrok or Railway)
    ↓
Your Flask Server (app.py)
    ↓
Database (SQLite)
```

## For Production

For production use, we recommend:

1. **Backend Hosting**: Railway.app or Heroku
   - More stable than ngrok
   - URLs don't change on restart
   - Automatic deployments from GitHub

2. **Frontend**: Netlify
   - CDN distribution
   - Automatic HTTPS
   - 300 free build minutes/month

3. **Database**: Cloud-hosted
   - PostgreSQL on Railway
   - MongoDB Atlas
   - Firebase

## Common Tasks

### Update Backend URL
```toml
# netlify.toml
[[redirects]]
  from = "/api/*"
  to = "https://your-new-url/api/:splat"
```

### View Deployment Status
```bash
cd PyPondoMobile/pypondo-web
netlify status
netlify logs
```

### Test API Connection
```bash
# From command line
curl https://your-site.netlify.app/api/health

# Or from browser
# https://your-site.netlify.app/api/health
```

### Update Mobile/Desktop Apps
They automatically discover and connect to the Netlify URL. No changes needed!

## Troubleshooting

### CORS Errors
**Error**: `Access to XMLHttpRequest blocked by CORS policy`

**Fix**: 
1. Verify ALLOWED_ORIGINS in app.py includes your Netlify domain
2. Restart backend with correct ALLOWED_ORIGINS:
   ```powershell
   $env:ALLOWED_ORIGINS = "https://your-site.netlify.app"
   python app.py
   ```

### API Timeout
**Error**: `Failed to fetch - timeout or network error`

**Fix**:
1. Verify backend is running and accessible
2. Check ngrok/tunnel is still active
3. Verify backend URL in netlify.toml is correct

### 404 on Page Refresh
This is already fixed! SPA routing configured in netlify.toml

### Build Fails on Netlify
1. Check Node.js version
2. Try: `npm ci` instead of `npm install`
3. Clear cache: Site Settings → Clear cache and redeploy

## Next Steps

1. **Read** [NETLIFY_DEPLOYMENT_GUIDE.md](NETLIFY_DEPLOYMENT_GUIDE.md) for complete details
2. **Follow** [NETLIFY_DEPLOYMENT_CHECKLIST.md](NETLIFY_DEPLOYMENT_CHECKLIST.md) for step-by-step deployment
3. **Run** `python setup_netlify.py` for automated setup
4. **Test** your deployment before going live

## Support Resources

- [Netlify Docs](https://docs.netlify.com)
- [ngrok Docs](https://ngrok.com/docs)
- [Flask CORS](https://flask-cors.readthedocs.io)
- [Vite Docs](https://vitejs.dev)

## Key Features Enabled

✅ **HTTPS/SSL** - Automatic via Netlify  
✅ **Global CDN** - Fast content delivery worldwide  
✅ **API Routing** - Transparent backend connectivity  
✅ **SPA Support** - React routing works on refresh  
✅ **CORS Security** - Properly configured cross-origin access  
✅ **Environment Variables** - Easy configuration per environment  
✅ **Auto-deploy** - Push to GitHub → automatic Netlify deployment  
✅ **Mobile & Desktop** - All clients work with remote URLs  

## Status

🎉 **Your system is ready for online deployment!**

Next: Follow the Quick Start guide above or read NETLIFY_DEPLOYMENT_GUIDE.md for more details.

---

**Questions?** Check the documentation files or run `python setup_netlify.py --help`
