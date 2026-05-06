# PyPondo Netlify Deployment - Quick Reference

## 5-Minute Setup

### Step 1: Install ngrok (for backend tunneling)
```powershell
# Download from https://ngrok.com/download
# Or install via Chocolatey (if available)
choco install ngrok

# Verify installation
ngrok --version
```

### Step 2: Start Backend with Tunneling
```powershell
# Terminal 1: Start Flask backend
cd PythonProject
python app.py

# Terminal 2: Start ngrok tunnel
python start_tunneling.ps1
# Or: ngrok http 5000

# Copy the URL shown (e.g., https://abc123.ngrok.io)
```

### Step 3: Update Frontend Configuration
Edit `netlify.toml`:
```toml
[context.production.environment]
  VITE_API_URL = "https://abc123.ngrok.io"

[[redirects]]
  from = "/api/*"
  to = "https://abc123.ngrok.io/api/:splat"
```

### Step 4: Deploy to Netlify
```bash
# Option A: Using CLI
cd PyPondoMobile/pypondo-web
npm install -g netlify-cli
netlify deploy --prod

# Option B: Using GitHub (recommended)
git add .
git commit -m "Add Netlify configuration"
git push origin main
# Then go to app.netlify.com and connect your repo
```

### Step 5: Configure Backend CORS
```powershell
# When starting Flask, set allowed origins
$env:ALLOWED_ORIGINS = "https://your-site.netlify.app,https://abc123.ngrok.io"
python app.py
```

## Environment Variables

### Frontend (.env.local)
```
VITE_API_URL=https://abc123.ngrok.io
VITE_API_TIMEOUT=30000
```

### Backend (when starting)
```powershell
$env:ALLOWED_ORIGINS = "https://your-site.netlify.app,http://localhost:3000"
python app.py
```

## File Structure

```
pypondo/
├── netlify.toml                 ← Netlify configuration
├── NETLIFY_DEPLOYMENT_GUIDE.md  ← Full documentation
├── setup_netlify.py             ← Setup helper script
├── PythonProject/
│   ├── app.py                   ← Backend with CORS
│   ├── requirements.txt          ← Python dependencies
│   ├── start_tunneling.ps1      ← ngrok startup script
│   └── start_tunneling.bat      ← Windows batch version
└── PyPondoMobile/
    └── pypondo-web/
        ├── netlify.toml         ← (redundant, can be moved here)
        ├── .env.example         ← Environment template
        ├── vite.config.ts       ← Vite configuration
        └── src/
            └── api/
                └── config.ts    ← API client configuration
```

## Useful Commands

```powershell
# Start Flask backend
python PythonProject/app.py

# Start ngrok tunnel
ngrok http 5000

# Build frontend
cd PyPondoMobile/pypondo-web
npm run build

# Preview production build
npm run preview

# Deploy with Netlify CLI
netlify deploy --prod

# Check Netlify site status
netlify status

# View Netlify logs
netlify logs
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| CORS errors | Check ALLOWED_ORIGINS env var includes your domain |
| 404 on page refresh | Already configured in netlify.toml (SPA routing) |
| API timeouts | Check backend is running and accessible from ngrok URL |
| ngrok URL changes | Use ngrok Pro for permanent URL or Railway/Heroku for stable backend |
| Build fails on Netlify | Check node_modules doesn't have stale dependencies |

## Free Hosting Alternatives

| Service | Tier | Notes |
|---------|------|-------|
| **Netlify** | Free | 300 build min/mo, unlimited bandwidth |
| **ngrok** | Free | 1 tunnel, 20 conn/min |
| **Railway.app** | Free | Deploy backend, $5/mo credit |
| **Vercel** | Free | Alternative to Netlify |
| **Heroku** | Paid | Was free, now $7/mo minimum |

## Monitoring

After deployment, monitor:
- Browser console for errors (F12)
- Netlify build logs
- Backend logs for API errors
- Network tab for failed requests

For detailed documentation, see: [NETLIFY_DEPLOYMENT_GUIDE.md](NETLIFY_DEPLOYMENT_GUIDE.md)
