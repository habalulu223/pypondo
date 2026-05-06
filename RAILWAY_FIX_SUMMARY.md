# Railway Configuration - Problem Solved

## The Problem

Railway was scanning the repository root and mostly seeing documentation and helper files. The real Flask backend lived in `PythonProject/`, so Railpack could not identify a Python app from the repo root.

## The Fix

The repo root is now deployable as a Python service, so Railway no longer has to rely on a subdirectory-only root setting.

### Root files now used by Railway

`railway.json`

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "deploy": {
    "startCommand": "python app.py",
    "healthcheckPath": "/api/health",
    "restartPolicyMaxRetries": 5,
    "restartPolicyWindowSeconds": 60
  }
}
```

`Procfile`

```procfile
web: python app.py
```

`requirements.txt`

```txt
-r PythonProject/requirements.txt
```

### App changes

- Root `app.py` was added as a wrapper so `python app.py` works from either the repo root or `PythonProject`.
- `PythonProject/app.py` now exposes `/api/health`.
- `PythonProject/app.py` now respects Railway's `PORT` environment variable.

## What Railway Does Now

1. Clones the repo.
2. Sees root `requirements.txt`.
3. Detects a Python project from the repo root.
4. Installs dependencies from `PythonProject/requirements.txt`.
5. Starts the backend with `python app.py`.
6. Waits for `/api/health` to return `200`.

## Dashboard Note

If you still want Railway to deploy only the `PythonProject` subdirectory, set the service Root Directory to `PythonProject` in the Railway dashboard. This repo no longer depends on that setting, but the dashboard option is still the right place for a true monorepo subdirectory deploy.

## Deploy

```bash
git add railway.json Procfile requirements.txt PythonProject/__init__.py PythonProject/app.py
git commit -m "Fix Railway root build detection"
git push origin main
```

## Verification Checklist

- Root `requirements.txt` exists.
- Root `railway.json` uses `python app.py`.
- Root `Procfile` uses `python app.py`.
- `PythonProject/app.py` reads `PORT`.
- `PythonProject/app.py` exposes `/api/health`.
