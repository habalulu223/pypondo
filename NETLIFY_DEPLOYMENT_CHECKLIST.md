# PyPondo Netlify Deployment Checklist

## Pre-Deployment Setup

### Backend Configuration
- [ ] Add `flask-cors` to requirements.txt ✓
- [ ] Update `app.py` with CORS configuration ✓
- [ ] Create `requirements.txt` with all dependencies ✓
- [ ] Test backend runs locally: `python app.py`
- [ ] Verify no database errors on startup

### Frontend Configuration  
- [ ] Create `netlify.toml` in web project ✓
- [ ] Create `src/api/config.ts` for API client ✓
- [ ] Create `.env.example` with environment template ✓
- [ ] Update Vite config if needed (already done)

### Backend Tunneling
- [ ] Install ngrok from https://ngrok.com/download
- [ ] Create `start_tunneling.ps1` script ✓
- [ ] Test ngrok tunnel: `ngrok http 5000`
- [ ] Copy public URL from ngrok output

### Documentation
- [ ] Create `NETLIFY_DEPLOYMENT_GUIDE.md` ✓
- [ ] Create `NETLIFY_QUICK_START.md` ✓
- [ ] Create `setup_netlify.py` helper script ✓

## Deployment Steps

### Backend (Persistent Hosting)

Choose ONE option:

#### Option A: ngrok (Temporary/Development)
- [ ] Install and setup ngrok
- [ ] Run `python PythonProject/app.py`
- [ ] Run `start_tunneling.ps1` (keeps URL during session)
- [ ] Copy ngrok URL: `https://abc123.ngrok.io`
- [ ] ⚠️ Note: URL changes after restart (upgrade to Pro to keep same)

#### Option B: Railway.app (Recommended - Free)
- [ ] Create account at https://railway.app
- [ ] Connect GitHub repository
- [ ] Deploy app.py as Python service
- [ ] Get persistent URL: `https://your-app.railway.app`
- [ ] Set DATABASE_URL and ALLOWED_ORIGINS in Railway

#### Option C: Heroku (Alternative)
- [ ] Create account at https://www.heroku.com
- [ ] Install Heroku CLI
- [ ] Run: `heroku create your-app-name`
- [ ] Run: `git push heroku main`
- [ ] Get persistent URL: `https://your-app.herokuapp.com`

### Frontend (Netlify Deployment)

#### Step 1: Prepare Repository
- [ ] Ensure code is in Git repository
- [ ] Push to GitHub/GitLab (recommended)
- [ ] Verify netlify.toml exists in repo root
- [ ] Update netlify.toml with backend URL (from above)

#### Step 2: Update Configuration
- [ ] Update `netlify.toml` redirects with backend URL
- [ ] Example:
  ```toml
  [[redirects]]
    from = "/api/*"
    to = "https://your-backend-url/api/:splat"
  ```

#### Step 3: Deploy to Netlify
Choose ONE method:

**Method A: GitHub (Recommended - Auto-deploy)**
- [ ] Go to https://app.netlify.com
- [ ] Click "New site from Git"
- [ ] Select GitHub and authorize
- [ ] Choose your repository
- [ ] Netlify auto-detects settings from netlify.toml
- [ ] Click "Deploy site"
- [ ] Get your Netlify URL: `https://your-site.netlify.app`

**Method B: Netlify CLI**
- [ ] Install: `npm install -g netlify-cli`
- [ ] Login: `netlify login`
- [ ] Deploy: `netlify deploy --prod`
- [ ] Get your Netlify URL from output

**Method C: Drag & Drop**
- [ ] Build locally: `npm run build`
- [ ] Go to https://app.netlify.com
- [ ] Drag `dist` folder to deploy
- [ ] Get your Netlify URL

### Configuration

#### Update Netlify Environment Variables
- [ ] In Netlify UI: Go to Site Settings → Environment Variables
- [ ] Add: `VITE_API_URL = https://your-backend-url`
- [ ] Add: `VITE_API_TIMEOUT = 30000`
- [ ] Trigger re-deploy

#### Update Backend CORS
- [ ] Update ALLOWED_ORIGINS in app.py or environment
- [ ] Include:
  - [ ] Your Netlify domain: `https://your-site.netlify.app`
  - [ ] Your backend URL: `https://your-backend-url`
  - [ ] Local development: `http://localhost:3000`
- [ ] Example:
  ```
  ALLOWED_ORIGINS = "https://your-site.netlify.app,https://your-backend-url,http://localhost:3000"
  ```

## Testing & Validation

### Backend Testing
- [ ] Backend running and accessible at your URL
- [ ] Health check returns 200: `curl https://your-backend-url/api/health`
- [ ] Database accessible and migrations done
- [ ] CORS headers present in response:
  - [ ] `Access-Control-Allow-Origin` header visible
  - [ ] `Access-Control-Allow-Methods` includes needed methods

### Frontend Testing
- [ ] Build completes without errors: `npm run build`
- [ ] Frontend accessible at Netlify URL
- [ ] Page refresh works (SPA routing configured)
- [ ] No console errors (F12 → Console tab)

### Integration Testing
- [ ] API calls succeed from Netlify frontend
- [ ] Login/authentication works
- [ ] Can create bookings
- [ ] Can view payments
- [ ] File uploads work (if applicable)
- [ ] Mobile view is responsive

### Network Testing
- [ ] Browser Network tab shows successful API calls
- [ ] CORS errors are gone
- [ ] API response times are acceptable
- [ ] Large file uploads complete

## Production Deployment

### Final Checks
- [ ] All tests pass
- [ ] No console errors
- [ ] Performance is acceptable
- [ ] Mobile works on test devices
- [ ] API rate limiting configured (if needed)

### Monitoring Setup
- [ ] Set up Netlify error tracking
- [ ] Monitor build logs for failures
- [ ] Set up backend log monitoring
- [ ] Create uptime monitoring (e.g., UptimeRobot)

### Backups & Security
- [ ] Database backups configured
- [ ] API keys rotated
- [ ] HTTPS/SSL enforced
- [ ] Rate limiting enabled

## Ongoing Maintenance

- [ ] Monitor build logs weekly
- [ ] Check error rates monthly
- [ ] Update dependencies quarterly
- [ ] Backup database regularly
- [ ] Review API usage patterns

## Useful Links

- [Netlify Documentation](https://docs.netlify.com)
- [ngrok Documentation](https://ngrok.com/docs)
- [Railway.app Documentation](https://docs.railway.app)
- [Flask CORS](https://flask-cors.readthedocs.io)
- [Vite Guide](https://vitejs.dev/guide/)

## Success Criteria

✅ All items checked = Production Ready!

**Key Indicators:**
- [ ] Frontend accessible and loads quickly
- [ ] API calls work from any client
- [ ] Database operations work
- [ ] No CORS errors
- [ ] Mobile app connects successfully
- [ ] Performance is acceptable
- [ ] Error rates are low

---

**Last Updated:** 2025-05-06
**Deployment Date:** _____
**Backend URL:** _____
**Frontend URL:** _____
**Deployed By:** _____
