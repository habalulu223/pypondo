# PyPondo Desktop App

## Run as desktop app (development)

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
- The app runs Flask locally and opens a desktop window via `pywebview` (app mode only).
- No browser fallback is used.
- If `PythonProject\pccafe.db` already exists, desktop mode uses it.
- Otherwise data is stored in `PythonProject\data\pccafe.db`.

## Build Windows EXE

Run:

```powershell
.\build_desktop_exe.bat
```

Output:
- `dist\PyPondo.exe`

Optional environment variable:
- `LAN_SERVER_PUBLIC_BASE_URL` (set this if clients should open callback pages using a specific LAN IP/host).
