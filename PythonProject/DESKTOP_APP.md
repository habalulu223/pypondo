# PyPondo Desktop App

## Run desktop app (development)

1. Open terminal in `PythonProject`.
2. Run:

```powershell
python desktop_app.py
```

Or on Windows:

```powershell
.\run_desktop_app.bat
```

Notes:
- If `pywebview` is installed, PyPondo opens in a native app window.
- If `pywebview` is not installed, PyPondo opens in your default browser and keeps a small desktop control window open.
- `run_desktop_app.bat` now auto-installs `pythonnet` (pre-release for Python 3.14) and `pywebview` when possible.
- Desktop data is persisted automatically:
  - Source run: `PythonProject\pccafe.db` (if present) or `PythonProject\data\pccafe.db`
  - Built EXE run: `%LOCALAPPDATA%\PyPondo\pccafe.db`

## Build standalone Windows EXE (no Python required on target PC)

Run:

```powershell
.\build_desktop_exe.bat
```

Output:
- `dist\PyPondo.exe`

You can share/download `PyPondo.exe` directly and run it on another Windows machine without installing Python.

## Download full apps from Admin dashboard

When logged in as admin, dashboard now provides:
- `DOWNLOAD ADMIN APP`: generates `pypondo-admin-standalone.zip` with `PyPondoAdmin.exe`.
- `DOWNLOAD CLIENT APP`: generates one generic `pypondo-client-standalone.zip` with:
  - `PyPondoClient.exe` (opens app window)
  - `PyPondoLanAgent.exe` (started automatically by client app)

Client app auto-starts the LAN agent, auto-detects client hostname, and auto-registers LAN IP to admin.

Optional environment variable:
- `LAN_SERVER_PUBLIC_BASE_URL` (set this if clients should open callback pages using a specific LAN IP/host).
