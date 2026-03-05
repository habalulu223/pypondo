# PyPondo Server IP Discovery Update - March 2026

## What's New

The client app now requests the admin server's IP address directly from the admin server instead of trying to guess it from the gateway.

## How It Works

### Old Behavior (Before)
```
Client → Try gateway IP (192.168.0.181)
      → Try hostname
      → Try local network scan
      → Try environment variables
```

### New Behavior (After)
```
Client → Find admin server via hostname/IP/gateway/scan
      → Request admin server info via /api/server-info
      → Use the admin-provided IP for future connections
      → Register with client agent using admin's actual IP
```

## Benefits

✅ **More Reliable**: Uses the actual IP from the admin server  
✅ **Automatic**: No need to configure gateway IP  
✅ **Handles Network Changes**: Works even if IP changes  
✅ **Public API**: No authentication required for discovery  

## New API Endpoint

### GET /api/server-info
**Purpose**: Public endpoint for clients to discover admin server information  
**Authentication**: None required  
**Response**:
```json
{
  "ok": true,
  "server_ip": "192.168.1.100",
  "server_port": 5000,
  "server_hostname": "ADMIN-PC"
}
```

## Client-Side Changes

### desktop_app.py
- **New function**: `discover_server_ip_from_admin(base_url)`
  - Calls `/api/server-info` endpoint
  - Extracts server IP from response
  - Returns IP address or None on error

- **Enhanced function**: `discover_remote_server_base_url()`
  - Now calls the new function after finding any server
  - Uses the admin-provided IP for the actual connection
  - Falls back gracefully if API call fails

### lan_agent.py
- **Enhanced function**: `discover_server_base_url()`
  - Requests server info from admin
  - Replaces hostname with actual IP in ACTIVE_SERVER_BASE_URL
  - Ensures registration and polling use the correct IP

## Server-Side Changes

### app.py
- **New endpoint**: `/api/server-info` [lines 1205-1222]
  - Public endpoint (no login required)
  - Returns server's local network IP
  - Returns server hostname and port
  - Used by clients for discovery

## Usage Examples

### Python Script Mode
```python
# No changes needed! Client automatically requests IP
python desktop_app.py
```

### With Environment Variable
```batch
set PYPONDO_SERVER_HOST=admin.local
python desktop_app.py
# Client will find admin.local, then request its IP
```

### With Configuration File
```batch
# Create server_host.txt
echo MY-ADMIN-PC > server_host.txt
python desktop_app.py
# Client finds MY-ADMIN-PC via hostname, then requests its actual IP
```

## Debugging

Enable verbose mode to see the discovery process:

```batch
set PYPONDO_VERBOSE=1
python desktop_app.py
```

Output will show:
```
[DEBUG] Searching 10 server candidates...
[DEBUG] Try #1: http://192.168.1.100:5000
[DEBUG] Found server: http://192.168.1.100:5000
[DEBUG] Admin server IP: 192.168.1.100
```

## Fallback Behavior

If the `/api/server-info` API call fails:
1. Client continues with the URL it found (hostname-based)
2. Everything still works normally
3. Log message shows API call failure
4. No disruption to user experience

## Security Notes

- `/api/server-info` is a **public endpoint** (no login required)
- Returns only network information
- No sensitive data exposed
- Same security as the `/login` page

## Compatibility

✅ **Fully backward compatible**
- Old client installations still work
- Existing configurations still work
- Gateway discovery still works as fallback
- No breaking changes

## Technical Details

### Discovery Pipeline (New Order)

1. **Explicit Configuration**
   - Environment variables: `PYPONDO_SERVER_HOST`, `PYPONDO_SERVER_BASE_URL`
   - Configuration file: `server_host.txt`

2. **Network Discovery** (if config not found)
   - Gateway IP detection
   - Network computer scan (`net view`)
   - Local IP addresses

3. **Probe Each Candidate**
   - Try each URL with HTTP request
   - First working URL is selected

4. **Request Admin Info** (NEW)
   - Call `/api/server-info` on found server
   - Get actual IP address
   - Use this IP for future registrations/commands

## Files Changed

```
app.py
  - Added: /api/server-info endpoint [lines 1205-1222]
  
desktop_app.py
  - Added: discover_server_ip_from_admin() function
  - Enhanced: discover_remote_server_base_url() function
  
lan_agent.py
  - Enhanced: discover_server_base_url() function
```

## Testing

### Test 1: Verify Endpoint Works
```batch
# Admin running on http://localhost:5000
curl http://localhost:5000/api/server-info
```

Expected response:
```json
{
  "ok": true,
  "server_ip": "192.168.168.100",
  "server_port": 5000,
  "server_hostname": "MY-ADMIN-PC"
}
```

### Test 2: Client Auto-Discovery
```batch
# On client PC with server_host.txt containing admin hostname
set PYPONDO_VERBOSE=1
python desktop_app.py
```

Should show:
- Server found via hostname
- Server info requested
- Admin IP retrieved
- Connection established

### Test 3: No Configuration
```batch
# On client PC, no server_host.txt
set PYPONDO_VERBOSE=1
python desktop_app.py
```

Should:
- Auto-discover via gateway
- Request admin info
- Connect successfully

## Advantages Over Old System

| Aspect | Old | New |
|--------|-----|-----|
| Gateway dependency | ✓ Hard-coded | ✗ Dynamic from admin |
| IP changes | ✗ Break | ✓ Auto-adjust |
| Network resilience | ✓ Works via hostname | ✓ Works + gets IP |
| Reliability | ✓ Good | ✓ Better |
| Configuration | ✓ Required | ✓ Optional |

## Future Enhancements

Possible future improvements:
- Return multiple IPs (WiFi + Ethernet)
- Return admin version info
- Return supported protocols
- Return available port list

## Migration Guide

### For Existing Installations

No action required! The system is fully backward compatible:

1. If using hostname: Works as before (now gets actual IP too)
2. If using gateway: Works as before
3. If using IP address: Works as before
4. No configuration changes needed

### For New Installations

Recommended approach:
1. Use hostname in `server_host.txt`
2. Client auto-discovers and requests IP
3. System uses actual admin IP for all future connections

## Troubleshooting

### "Cannot get server IP"
- Normal fallback behavior
- Client continues with discovered URL
- No action needed

### "Server info API returned error"
- Check admin server is running
- Verify network connectivity
- Try with `-v` verbose flag

### "IP keeps changing"
- Verify admin PC has static IP
- Or update DHCP lease time
- Client will auto-adjust anyway

## Summary

The client now intelligently requests the admin server's IP address once connected, ensuring it uses the most direct and reliable IP for all future communications. This is automatic, transparent, and fully backward compatible.

---

**Version**: 1.0  
**Date**: March 2026  
**Status**: Ready for Production
