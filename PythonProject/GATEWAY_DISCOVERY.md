# Gateway Discovery Feature

## Overview

The client app and LAN agent now automatically discover the admin app by searching for it on the default network gateway. This enables automatic detection without requiring manual IP configuration.

## How It Works

### Client App (desktop_app.py)

The client app uses the following discovery strategy in order:

1. **Explicit Environment Variables**: `PYPONDO_SERVER_BASE_URL`, `LAN_SERVER_BASE_URL`
2. **Configuration File**: `server_host.txt` (host candidates)
3. **Environment Host Candidates**: `PYPONDO_SERVER_HOST`, `LAN_SERVER_HOST`, etc.
4. **Network Discovery**:
   - `net view` command (Windows network browsing)
   - **Gateway IP Discovery** (NEW) - Extracts default gateway IPs from `ipconfig`
5. **Local Address Probing**: Tests known local addresses
6. **API Endpoints Tested**: `/login`, `/api/agent/register-lan`

### LAN Agent (lan_agent.py)

The LAN agent uses identical discovery logic:

1. Explicit configuration from environment variables
2. File-based host candidates
3. Network discovery including **gateway IPs**
4. Probes for server availability

### Gateway Discovery Process

1. Runs `ipconfig` command on Windows
2. Searches for lines containing "Default Gateway"
3. Extracts IPv4 addresses from the gateway lines
4. Validates IPv4 format (4 octets, 0-255 each)
5. Adds discovered gateways to the candidate list
6. Probes each gateway candidate on default ports (5000, 5001)

## Usage

### Automatic Discovery (No Configuration)

```powershell
# Admin app
python app.py

# Client app - automatically finds admin
python desktop_app.py
```

The client will search the network gateway automatically.

### Explicit Configuration (Optional)

```powershell
# Set admin app location explicitly
$env:PYPONDO_SERVER_HOST="192.168.1.1"
$env:PYPONDO_SERVER_PORT="5000"
python desktop_app.py
```

### Via Configuration File

Create `server_host.txt`:
```
192.168.1.1
admin.local
gateway-pc
```

Then run client:
```powershell
python desktop_app.py
```

## Gateway IP Detection Examples

### Windows ipconfig output:
```
Ethernet adapter Local Area Connection:
   Default Gateway . . . . . . . . . : 192.168.1.1
                                        fe80::1%5
```

Extracted: `192.168.1.1`

### Multiple gateway scenario:
```
Default Gateway . . . . . . . . . : 192.168.1.1 192.168.100.1
```

Extracted: `192.168.1.1`, `192.168.100.1`

## Environment Variables

### Gateway Discovery Settings

Gateway discovery is automatic on Windows. To disable or configure:

```powershell
# Disable gateway discovery (use explicit config only)
$env:PYPONDO_SERVER_HOST="192.168.1.10"

# Specify multiple host candidates
$env:PYPONDO_SERVER_HOST_CANDIDATES="192.168.1.1,192.168.1.10,admin-pc"

# Custom port
$env:PYPONDO_SERVER_PORT="8080"
```

## Troubleshooting

### Client can't find admin app

1. **Check gateway detection**:
   ```powershell
   ipconfig | findstr /i "gateway"
   ```

2. **Check admin app is accessible**:
   ```powershell
   curl http://192.168.1.1:5000/login
   ```

3. **Check firewall** - Ensure port 5000 (admin) is accessible from client

4. **Set explicit host** - Use `server_host.txt` or `PYPONDO_SERVER_HOST` env var:
   ```powershell
   $env:PYPONDO_SERVER_HOST="192.168.1.1"
   python desktop_app.py
   ```

### Gateway IP not detected

- Only works on Windows (ipconfig command)
- Check admin app is actually running on the gateway PC
- Check network connectivity to gateway

## Testing Gateway Discovery

Run with verbose logging:

```powershell
$env:PYPONDO_VERBOSE="1"
python desktop_app.py
```

This will show:
- Discovered candidate URLs
- Probing results
- Selected server URL

## Files Modified

- `desktop_app.py` - Added `discover_default_gateway_ips()` function
- `lan_agent.py` - Added `discover_default_gateway_ips()` function
- Both functions are now called in `build_server_base_url_candidates()` / `build_server_base_candidates()`
