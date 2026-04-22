# PyPondo - Complete Setup Guide

## What Changed?

The client app and LAN agent now **automatically discover the admin app** by searching the network gateway. Previously, users had to manually configure the admin app's IP address.

### Key Improvements

✅ **Automatic Gateway Discovery** - No manual IP configuration needed
✅ **Zero PyCharm Dependency** - Apps run independently from IDE
✅ **Backward Compatible** - Manual configuration still works
✅ **Cross-Platform Ready** - Falls back gracefully on non-Windows

## Quick Reference

| Component | File | Purpose |
|-----------|------|---------|
| Admin Server | `app.py` | Web interface + LAN command server |
| Client Desktop | `desktop_app.py` | Desktop app that finds & connects to admin |
| LAN Agent | `lan_agent.py` | Client-side agent for remote PC commands |
| **NEW** Gateway Discovery | Both apps | Auto-find admin via network gateway |

## Single Machine Setup (Testing)

Perfect for testing both admin and client on the same machine:

```powershell
# Terminal 1: Admin app
cd C:\path\to\pypondo\PythonProject
python app.py
# Listens on http://127.0.0.1:5000

# Terminal 2: Client app (discovers admin automatically)
python desktop_app.py
# Opens client interface connecting to admin
```

Expected behavior:
- Admin starts server
- Client looks for admin on network
- Client doesn't find (same machine)
- Client falls back to local server mode
- Both work together transparently

## Multi-Machine Setup (Real Deployment)

With admin on one PC and clients on other machines:

### Step 1: Admin PC

```powershell
# Admin PC (e.g., 192.168.1.10)
cd C:\path\to\pypondo\PythonProject

# Optional: Configure to accept remote connections
$env:FLASK_HOST="0.0.0.0"
$env:LAN_AGENT_TOKEN="secure-secret-key-here"

python app.py
```

Admin will be accessible at:
- Local: `http://127.0.0.1:5000`
- Network: `http://192.168.1.10:5000`

### Step 2: Client PCs

```powershell
# Client PC (e.g., 192.168.1.50)
cd C:\path\to\pypondo\PythonProject

# Automatic discovery (default)
python desktop_app.py
```

The client app will:
1. Extract gateway IP from `ipconfig` (e.g., 192.168.1.1)
2. Check if admin is running there
3. If not found on gateway, try other discovery methods
4. Connect to admin if found
5. Fall back to local mode if not found

### Step 3: LAN Agents (Optional)

For sending commands to client PCs:

```powershell
# On each client PC
$env:LAN_SERVER_REGISTER_URL="http://192.168.1.10:5000/api/agent/register-lan"
$env:LAN_AGENT_TOKEN="secure-secret-key-here"
$env:LAN_PC_NAME="ClientPC-1"

python lan_agent.py
```

## How Gateway Discovery Works

### The Problem It Solves

```
Before:
User manually enters: PYPONDO_SERVER_HOST=192.168.1.10
         ↓
Client app connects to admin ✓

Now:
Client runs ipconfig and finds gateway automatically
         ↓
Probes gateway for admin app
         ↓
Connects automatically (no manual config!) ✓
```

### Technical Details

1. **Gateway Detection**
   ```powershell
   ipconfig /all
   # Output includes:
   # Default Gateway . . . . . . . . . : 192.168.1.1
   ```

2. **Extraction**
   - Parses `ipconfig` output
   - Finds "Default Gateway" lines
   - Extracts IPv4 addresses
   - Validates format (4 octets, 0-255 range)

3. **Probing**
   - For each gateway IP: probe `http://gateway:5000/login`
   - If responds: gateway is admin app
   - Connect and launch UI

4. **Fallback**
   - Gateway not found → Try other sources
   - Still not found → Run local server mode

## Configuration Methods

### Method 1: Automatic (NEW!) ⭐

```powershell
# Just run it!
python desktop_app.py
# Automatically finds admin on gateway
```

### Method 2: Environment Variables

```powershell
$env:PYPONDO_SERVER_HOST="192.168.1.10"
$env:PYPONDO_SERVER_PORT="5000"
python desktop_app.py
```

### Method 3: Configuration File

Create `server_host.txt`:
```
# Admin app location
192.168.1.10

# Or with hostname
admin-pc.local

# Or multiple options
192.168.1.1
192.168.1.10
admin-server
```

Then run:
```powershell
python desktop_app.py  # Reads server_host.txt automatically
```

### Method 4: Full URL

```powershell
$env:PYPONDO_SERVER_BASE_URL="http://192.168.1.10:5000"
python desktop_app.py
```

## Verification Steps

### Step 1: Test Gateway Discovery

```powershell
python test_independence.py
```

Expected output:
```
Testing Gateway Discovery
✓ Found 1 gateway IP(s):
  - 192.168.1.1

Testing Required Imports
✓ flask
✓ flask_sqlalchemy
✓ flask_login
✓ werkzeug
✓ sqlalchemy

Testing App Independence (No PyCharm Dependencies)
✓ No PyCharm dependencies found
✓ Apps can run independently from PyCharm

Testing Gateway Discovery Code
✓ desktop_app.py: contains discover_default_gateway_ips()
✓ lan_agent.py: contains discover_default_gateway_ips()

Test Summary
Gateway Discovery: ✓ PASS
Required Imports: ✓ PASS
App Independence: ✓ PASS
Gateway Code: ✓ PASS

✓ All tests passed!

You can now run:
  python app.py          # Admin app
  python desktop_app.py  # Client app (auto-discovers admin)
```

### Step 2: Test Admin App

```powershell
python app.py

# You should see:
# * Running on http://127.0.0.1:5000
# * Debug mode: off
```

Open browser to `http://127.0.0.1:5000` - should see login page.

### Step 3: Test Client Discovery

```powershell
$env:PYPONDO_VERBOSE="1"
python desktop_app.py

# You should see:
# [DEBUG] Building server candidates...
# [DEBUG] Checking gateway: 192.168.1.1:5000
# [DEBUG] Probing http://192.168.1.1:5000/login
# Connection successful / Connection failed
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│ PyPondo - Independent Modular Architecture              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────┐
│   app.py            │  Admin Server
│   (Flask Backend)   │  - Database (SQLite)
│   - Routes          │  - User Authentication
│   - APIs            │  - LAN Command Server
│   - Web UI Routes   │  - Network Discovery APIs
└──────────┬──────────┘
           │
           │ :5000
           │
           ▼
    ┌──────────────────────────────────────────┐
    │  Network (e.g., 192.168.1.0/24)          │
    │  Gateway: 192.168.1.1 (Admin PC)         │
    │                                           │
    │  ┌──────────────────────┐                │
    │  │ desktop_app.py       │ Client Desktop │
    │  │ - Auto-discovers via │                │
    │  │   gateway IP lookup  │                │
    │  │ - Connects to admin  │                │
    │  │ - Shows UI           │                │
    │  └──────────────────────┘                │
    │                                           │
    │  ┌──────────────────────┐                │
    │  │ lan_agent.py         │ LAN Agent      │
    │  │ - Also auto-discovers│                │
    │  │   admin via gateway  │                │
    │  │ - Registers with     │                │
    │  │   admin for commands │                │
    │  └──────────────────────┘                │
    └──────────────────────────────────────────┘

Discovery Chain:
1. Explicit env vars (PYPONDO_SERVER_HOST)
2. Config file (server_host.txt)
3. Network sources:
   a. net view (Windows network sharing)
   b. ipconfig (gateway IPs) ← NEW!
4. Local fallback server
```

## Files Modified

### desktop_app.py
- **Added**: `discover_default_gateway_ips()` function
- **Modified**: `build_server_base_url_candidates()` to include gateway IPs
- **Behavior**: Client now searches gateway before starting local server

### lan_agent.py
- **Added**: `discover_default_gateway_ips()` function  
- **Modified**: `build_server_base_candidates()` to include gateway IPs
- **Behavior**: LAN agent now searches gateway for admin registration

### No Changes Required
- `app.py` - Admin server code unchanged
- `run_desktop_app.bat` - Still works as-is
- `build_desktop_exe.bat` - Still builds standalone EXE

## New Files Added

- `INDEPENDENT_SETUP.md` - Detailed standalone setup guide
- `GATEWAY_DISCOVERY.md` - Technical gateway discovery documentation
- `test_independence.py` - Automated verification script

## Troubleshooting

### "Unable to locate admin app host"

**Cause**: Client can't find admin on gateway

**Solutions**:
1. Create `server_host.txt` with admin IP:
   ```
   192.168.1.10
   ```

2. Set explicit host:
   ```powershell
   $env:PYPONDO_SERVER_HOST="192.168.1.10"
   python desktop_app.py
   ```

3. Check admin is running on gateway:
   ```powershell
   curl http://192.168.1.1:5000/login
   ```

### Client connects but then disconnects

**Cause**: Authentication issue or app crash

**Solutions**:
1. Check credentials in login screen
2. Check browser console for errors
3. Run admin with logging:
   ```powershell
   python app.py 2>&1 | Tee-Object -FilePath log.txt
   ```

### Gateway discovery finds wrong IP

**Cause**: Multiple gateways or IPv6 confusion

**Solutions**:
1. Check current gateway:
   ```powershell
   ipconfig | findstr /i "gateway"
   ```

2. Explicitly set correct host:
   ```powershell
   $env:PYPONDO_SERVER_HOST="correct.ip.here"
   ```

### Apps won't start

**Cause**: Missing dependencies

**Solution**:
```powershell
pip install flask flask-sqlalchemy flask-login werkzeug
python test_independence.py
```

## Performance & Security

### Performance
- Gateway discovery: < 1 second (subprocess)
- Server probing: < 2 seconds (3 probes × timeout)
- **Total**: < 3 seconds from app start to connection

### Security
- Gateway discovery uses no external network requests
- No data sent outside LAN
- Optional: `LAN_AGENT_TOKEN` for authenticated registration
- Still requires admin login for UI

## Next Steps

1. ✅ **Test**: `python test_independence.py`
2. ✅ **Run Admin**: `python app.py`
3. ✅ **Run Client**: `python desktop_app.py`
4. ✅ **Configure** (optional): Create `server_host.txt` or env vars
5. ✅ **Deploy**: Use as standalone or built EXE

## Support & Help

See detailed guides:
- `INDEPENDENT_SETUP.md` - Step-by-step setup
- `GATEWAY_DISCOVERY.md` - Technical deep-dive
- `LAN_API_SETUP.md` - LAN agent configuration
- `DESKTOP_APP.md` - Desktop-specific features

Run with verbose logging for debugging:
```powershell
$env:PYPONDO_VERBOSE="1"
python desktop_app.py
```
