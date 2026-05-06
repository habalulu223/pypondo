# PyPondo Netlify Deployment Setup Guide

## Overview

This guide explains how to deploy PyPondo to Netlify with a free, secure tunneling solution. Netlify hosts the React frontend and provides API routing to your backend server.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Netlify CDN                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  PyPondo React Frontend (pypondo-web)           │   │
│  │  - Deployed automatically from GitHub           │   │
│  │  - Globally distributed                         │   │
│  │  - HTTPS/SSL included                           │   │
│  └──────────────────────────────────────────────────┘   │
│                          │                               │
│              Redirects API requests to:                  │
│                          │                               │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────┐
        │   Your Backend (Flask app.py)        │
        │   - Runs on your server/PC           │
        │   - Can use ngrok or exposed URL     │
        │   - Handles all business logic       │
        └──────────────────────────────────────┘
```

## Prerequisites

1. **Netlify Account** (free tier available)
   - Sign up at https://netlify.com

2. **GitHub Account** (recommended for easy deployments)
   - Push your repository to GitHub

3. **Your Backend URL**
   - Backend server exposed (see Backend Tunneling section)
   - IP address or domain name

## Step 1: Prepare Your Backend for Remote Access

### Option A: Using ngrok (Fastest)

```powershell
# Download ngrok from https://ngrok.com/download
# Extract and add to PATH

# Start your Flask app
python app.py

# In another terminal, expose it
ngrok http 5000

# Copy the public URL (e.g., https://abc123.ngrok.io)
```

### Option B: Using Expose (Alternative)

```powershell
# Install expose
pip install expose

# Expose your Flask app
expose http://127.0.0.1:5000
```

### Option C: Using Your Own Server

If you have a dedicated server:
```
https://yourdomain.com
```

## Step 2: Set Up Frontend for Deployment

### Update Environment Variables

The frontend uses environment variables from `netlify.toml`. Update these with your backend URL:

In `netlify.toml`, replace all instances of `https://your-backend.herokuapp.com` with your actual backend URL:

```toml
[context.production.environment]
  VITE_API_URL = "https://your-abc123.ngrok.io"

[[redirects]]
  from = "/api/*"
  to = "https://your-abc123.ngrok.io/api/:splat"
```

### Update Frontend Code (if needed)

In your React components, use the environment variable:

```typescript
// src/api/config.ts
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

export const fetchApi = async (endpoint: string, options?: RequestInit) => {
  const url = `${API_URL}${endpoint}`;
  return fetch(url, options);
};
```

## Step 3: Deploy to Netlify

### Option 1: Using GitHub (Recommended)

1. **Push code to GitHub**
   ```bash
   git add .
   git commit -m "Add Netlify configuration"
   git push origin main
   ```

2. **Connect to Netlify**
   - Go to https://app.netlify.com
   - Click "New site from Git"
   - Choose GitHub and select your repository
   - Netlify automatically detects the build settings from `netlify.toml`
   - Click "Deploy"

3. **Set Environment Variables in Netlify UI**
   - Go to Site Settings → Environment Variables
   - Add `VITE_API_URL` with your backend URL
   - Re-deploy

### Option 2: Using Netlify CLI

```powershell
# Install Netlify CLI
npm install -g netlify-cli

# Login to Netlify
netlify login

# Initialize site
netlify init

# Deploy
netlify deploy

# Deploy to production
netlify deploy --prod
```

### Option 3: Manual Deployment

1. Build the project locally:
   ```bash
   cd PyPondoMobile/pypondo-web
   npm install
   npm run build
   ```

2. Deploy the `dist` folder to Netlify:
   - Drag and drop the `dist` folder on https://app.netlify.com

## Step 4: Configure CORS on Your Backend

Your Flask backend needs to allow requests from Netlify. Update `app.py`:

```python
from flask_cors import CORS

# After creating Flask app
app = Flask(__name__)

# Allow Netlify frontend domain
CORS(app, resources={
    r"/api/*": {
        "origins": [
            "https://your-site.netlify.app",  # Your Netlify URL
            "http://localhost:3000",           # Local development
            "http://127.0.0.1:5000"            # Local fallback
        ],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

db = SQLAlchemy(app)
```

Or use environment-based CORS:

```python
import os

ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000').split(',')

CORS(app, resources={
    r"/api/*": {
        "origins": ALLOWED_ORIGINS,
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})
```

Then set the environment variable when running:
```powershell
$env:ALLOWED_ORIGINS = "https://your-site.netlify.app,https://abc123.ngrok.io"
python app.py
```

## Step 5: Configure Mobile & Desktop Apps

Update your mobile and desktop apps to use the Netlify URL:

### In `desktop_app.py`:

```python
# Add to server discovery candidates
def build_server_base_url_candidates():
    candidates = [
        "https://your-site.netlify.app",  # Netlify production
        "http://localhost:5000",           # Local fallback
    ]
    # ... rest of function
```

### In Mobile App (React):

Create an `.env` file:
```
VITE_API_URL=https://your-site.netlify.app
```

## Step 6: Deploy Backend Persistently

For production, you'll want your backend running 24/7:

### Option 1: Heroku (Recommended, has free tier alternatives)

```powershell
# Install Heroku CLI
# Create new app
heroku create your-app-name

# Set environment variables
heroku config:set PYPONDO_DB_PATH=/app/data/pccafe.db

# Deploy
git push heroku main
```

### Option 2: Railway.app (Alternative)

1. Create account at https://railway.app
2. Connect GitHub repository
3. Set environment variables in UI
4. Deploy

### Option 3: PythonAnywhere

1. Sign up at https://pythonanywhere.com
2. Upload your code
3. Configure web app
4. Set custom domain

## Step 7: Testing

### Test Frontend
```bash
# Local development
npm run dev

# Production build
npm run build
npm run preview
```

### Test API Connectivity
```powershell
# Test if API is reachable
Invoke-WebRequest -Uri "https://your-backend-url/api/health" -Method GET

# Test from browser
# https://your-site.netlify.app/api/health
```

### Test from Mobile/Desktop
```powershell
python desktop_app.py
# Should now connect through Netlify to backend
```

## Troubleshooting

### CORS Errors

**Problem**: `Access to XMLHttpRequest blocked by CORS`

**Solution**:
1. Check backend has CORS enabled
2. Verify origin in CORS whitelist
3. Check request headers are allowed

### 404 Errors on SPA Routes

**Problem**: Refreshing page returns 404

**Solution**: Already configured in `netlify.toml` - SPA routing redirects to `index.html`

### API Requests Failing

**Problem**: API calls return 500 or timeout

**Solution**:
1. Verify backend is running and accessible
2. Check API URL in environment variable
3. Check firewall/network settings

### ngrok URL Keeps Changing

**Problem**: ngrok URL changes after restart

**Solution**: Use ngrok Pro account for permanent URL, or use alternative like Expose or Cloudflare Tunnel

## Updating Your Site

Once deployed, updates are automatic:

```bash
# Make changes locally
git add .
git commit -m "Update feature"
git push origin main

# Netlify automatically deploys from GitHub
# Check status at https://app.netlify.com
```

## Environment Variables Cheatsheet

| Variable | Where | Purpose |
|----------|-------|---------|
| `VITE_API_URL` | netlify.toml | Frontend API endpoint |
| `ALLOWED_ORIGINS` | Backend (app.py) | CORS whitelist |
| `FLASK_HOST` | app.py | Backend host (use 0.0.0.0 for remote) |
| `PYPONDO_DB_PATH` | app.py | Database file location |

## Free Tier Limits

- **Netlify**: 300 build minutes/month, unlimited sites and bandwidth
- **ngrok**: 1 URL, 20 connections/minute (free tier)
- **Heroku**: Sleeping dynos (upgrade needed for 24/7)

## Next Steps

1. Choose your backend hosting solution
2. Update `netlify.toml` with backend URL
3. Deploy to Netlify
4. Test all functionality
5. Monitor performance

For questions or issues, refer to:
- [Netlify Docs](https://docs.netlify.com)
- [ngrok Docs](https://ngrok.com/docs)
- [Flask CORS](https://flask-cors.readthedocs.io)
