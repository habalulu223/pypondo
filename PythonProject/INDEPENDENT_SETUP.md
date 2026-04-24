# PyPondo - Independent App Setup & Gateway Discovery

## Quick Start

### Prerequisites
1. Python 3.8+ installed
2. Required packages: `pip install flask flask-sqlalchemy flask-login werkzeug`
3. Windows system (for automatic gateway discovery)

### Running Independently from PyCharm

Both apps are now completely independent and can be run directly from command line or PowerShell.

## 1. Run Admin App

```powershell
# Navigate to project directory
cd C:\path\to\pypondo\PythonProject

# Run admin app (server)
python app.py
```

The admin app will:
- Start Flask server on `http://127.0.0.1:5000`
- Initialize database if needed
- Be ready to accept client connections

### Admin App Environment Variables (Optional)

```powershell
# Set admin to listen on a specific network interface
$env:FLASK_HOST="0.0.0.0"
$env:FLASK_PORT="5000"

# Set LAN agent token for secure communication
$env:LAN_AGENT_TOKEN="your-secret-key"

python app.py
```

### 2.5 Configure Admin Server IP (Independence Mode)

If you want to configure the admin server IP without the server running:

```powershell
# Configure IP in independence mode (server doesn't need to be running)
python desktop_app.py --independence

# Or use the shorter alias
python desktop_app.py --configure-ip
```

This will:
- Prompt you to enter the admin server IP/hostname
- Save it to `server_host.txt` without trying to connect
- Allow you to run the client normally later

### Expected Output

```
PyPondo Independence Mode - Configure Admin Server IP
=======================================================
[OK] Saved admin server IP '192.168.1.100' to server_host.txt
You can now run the client normally to connect to this server.
Run: python desktop_app.py
```

The client app will automatically:
1. **Search for gateway IP** using `ipconfig` command
2. **Probe the gateway** for the admin app on port 5000
3. **Discover and connect** to the admin app if found
4. **Fall back to local mode** if remote admin is not found

### Client App Environment Variables (Optional)

```powershell
# Explicitly set admin app location
$env:PYPONDO_SERVER_HOST="192.168.1.10"
$env:PYPONDO_SERVER_PORT="5000"

# Enable verbose logging to see discovery process
$env:PYPONDO_VERBOSE="1"

python desktop_app.py
```

### Expected Output

When client successfully discovers admin:
```
[CLIENT] Discovering admin app...
[CLIENT] Probing candidate: http://192.168.1.1:5000
[CLIENT] Found admin at: http://192.168.1.10:5000
[CLIENT] Connecting to admin app...
[CLIENT] Opening UI at http://192.168.1.10:5000/client
```

If discovery fails (normal on same machine):
```
[CLIENT] Admin not found on network
[CLIENT] Starting local server mode...
[CLIENT] Server ready at http://127.0.0.1:5000
```

## 3. Run LAN Agent (On Client PC)

For remote PC client to communicate with admin:

```powershell
# On the client PC, set admin location
$env:LAN_SERVER_REGISTER_URL="http://192.168.1.10:5000/api/agent/register-lan"
$env:LAN_AGENT_TOKEN="your-secret-key"
$env:LAN_PC_NAME="ClientPC-1"

# Run agent
python lan_agent.py
```

The LAN agent will:
- Automatically discover the admin app (via gateway)
- Register itself with the admin
- Wait for commands from admin
- Handle lock/restart/shutdown commands

## Gateway Discovery Deep Dive

### How It Works

1. **Automatic Detection (Windows only)**
   ```powershell
   ipconfig | findstr /i "gateway"
   ```
   This extracts your network gateway IP (e.g., `192.168.1.1`)

2. **Probing**
   The app then probes:
   - `http://gateway-ip:5000/login`
   - `http://gateway-ip:5000/api/agent/register-lan`
   
3. **Auto-Connection**
   If gateway responds with a valid admin app, client connects automatically

### Example Network Layout

```
┌─────────────────────────────────────────┐
│  Network: 192.168.1.0/24                │
│  Gateway: 192.168.1.1                   │
│                                         │
│  ┌─────────────────────────┐            │
│  │ Admin PC (Gateway)      │            │
│  │ 192.168.1.1             │            │
│  │ Running: app.py         │            │
│  │ Port: 5000              │            │
│  └─────────────────────────┘            │
│           ↑                              │
│           │ Auto-discovers              │
│           │ via gateway IP              │
│           ↓                              │
│  ┌─────────────────────────┐            │
│  │ Client PC               │            │
│  │ 192.168.1.50            │            │
│  │ Running: desktop_app.py │            │
│  │ Port: 5000 (local)      │            │
│  └─────────────────────────┘            │
│                                         │
└─────────────────────────────────────────┘
```

### Configuration Priority

The app checks sources in this order:

1. **Environment Variables** (explicit)
   - `PYPONDO_SERVER_BASE_URL`
   - `PYPONDO_SERVER_HOST`

2. **Configuration File** (`server_host.txt`)
   - Add hosts line by line or comma-separated

3. **Automatic Discovery**
   - `net view` (network browsing)
   - `ipconfig` (gateway IPs) ← **New!**

4. **Local Fallback**
   - Start local server if remote not found

## Testing

### Test Gateway Discovery

```powershell
cd C:\path\to\pypondo\PythonProject
python test_independence.py
```

This will:
- Check if gateway IPs can be detected
- Verify all required Python packages are installed
- Confirm no PyCharm dependencies exist
- Validate gateway discovery code is in place

### Test Manual Connection

```powershell
# From client machine
$env:PYPONDO_VERBOSE="1"
python desktop_app.py
```

Watch the console for discovery attempts and final connection status.

## Troubleshooting

### Problem: Client can't find admin

**Solution 1: Check gateway**
```powershell
ipconfig | findstr /i "gateway"
```

**Solution 2: Verify admin is running**
```powershell
curl http://192.168.1.1:5000/login
```

**Solution 3: Set explicit host**
```powershell
$env:PYPONDO_SERVER_HOST="192.168.1.1"
python desktop_app.py
```

### Problem: "Unable to locate admin app host"

Create `server_host.txt`:
```
192.168.1.1
admin-pc
192.168.1.10
```

Then run client.

### Problem: Firewall blocking connection

Allow port 5000 in Windows Firewall:
```powershell
New-NetFirewallRule -DisplayName "PyPondo Admin" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5000
```

### Problem: Script won't run

Make sure Python is in PATH:
```powershell
python --version
```

If not found, run from Python installation directory or add Python to PATH.

## Running as Batch Files

Create `run_admin.bat`:
```batch
@echo off
cd /d "%~dp0"
python app.py
pause
```

Create `run_client.bat`:
```batch
@echo off
cd /d "%~dp0"
python desktop_app.py
pause
```

Then just double-click the `.bat` files to run.

## Environment Variables Summary

| Variable | Description | Example |
|----------|-----------|---------|
| `PYPONDO_SERVER_HOST` | Admin app hostname/IP | `192.168.1.10` |
| `PYPONDO_SERVER_PORT` | Admin app port | `5000` |
| `PYPONDO_VERBOSE` | Enable debug logging | `1` |
| `PYPONDO_FALLBACK_LOCAL_SERVER` | Allow local mode fallback | `1` |
| `PYPONDO_FORCE_LOCAL_SERVER` | Force local-only mode | `0` |
| `LAN_AGENT_TOKEN` | Shared secret token | `my-secret-key` |
| `LAN_PC_NAME` | PC identifier for agent | `PC-1` |
| `LAN_SERVER_HOST` | Server host (agent) | `192.168.1.10` |
| `APP_HOST` | Local app listen host | `127.0.0.1` |
| `APP_PORT` | Local app listen port | `5000` |

## Architecture Changes

### New Function: `discover_default_gateway_ips()` 

Added to:
- `desktop_app.py` - Enables client to find admin via gateway
- `lan_agent.py` - Enables LAN agent to find admin via gateway

**How it works:**
```python
def discover_default_gateway_ips():
    """Extract default gateway IPs from ipconfig output on Windows."""
    # Runs: ipconfig
    # Searches for: "Default Gateway"
    # Extracts: IPv4 addresses
    # Returns: List of gateway IPs
```

### Modified Function: `build_server_base_url_candidates()`

Now includes:
```python
host_candidates.extend(discover_default_gateway_ips())
```

This integrates gateway discovery into the automatic server discovery pipeline.

## Next Steps

1. **Test gateway discovery**: `python test_independence.py`
2. **Start admin app**: `python app.py`
3. **Start client app**: `python desktop_app.py`
4. **Verify connection**: Check console output for success message

## Support

For issues or questions:
1. Enable verbose logging: `$env:PYPONDO_VERBOSE="1"`
2. Check console output for error messages
3. Review firewall and network settings
4. Create `server_host.txt` with admin IP as fallback
