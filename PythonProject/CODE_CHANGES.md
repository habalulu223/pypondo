# Code Changes - Admin IP Discovery Feature

## File 1: app.py

### Change: Added new public API endpoint

**Location**: Before the `/login` route (around line 1205)

**Code Added**:
```python
@app.route('/api/server-info')
def api_server_info():
    """Public API endpoint for clients to discover admin server information."""
    try:
        # Get local network IP
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            server_ip = sock.getsockname()[0]
        except Exception:
            server_ip = "127.0.0.1"
        finally:
            sock.close()
    except Exception:
        server_ip = "127.0.0.1"
    
    return jsonify({
        "ok": True,
        "server_ip": server_ip,
        "server_port": 5000,
        "server_hostname": socket.gethostname()
    }), 200
```

**Lines**: 18 lines added
**Type**: New public endpoint
**Auth**: None (public)

---

## File 2: desktop_app.py

### Change 1: New function to request admin IP

**Location**: Before `build_server_base_url_candidates()` (around line 239)

**Code Added**:
```python
def discover_server_ip_from_admin(base_url):
    """Request admin server IP from the admin server's public API."""
    if not base_url:
        return None
    
    try:
        info_url = base_url.rstrip("/") + "/api/server-info"
        with http_request.urlopen(info_url, timeout=2) as response:
            import json as json_module
            data = json_module.loads(response.read().decode("utf-8"))
            if data.get("ok") and data.get("server_ip"):
                return data.get("server_ip")
    except Exception as e:
        if is_verbose_logging_enabled():
            print(f"[DEBUG] Failed to get server IP from admin: {e}")
    
    return None
```

**Lines**: 15 lines added
**Purpose**: Call /api/server-info and extract admin's IP

### Change 2: Enhanced discovery function

**Location**: `discover_remote_server_base_url()` (around line 345)

**Code Changed From**:
```python
def discover_remote_server_base_url():
    candidates = build_server_base_url_candidates()
    if is_verbose_logging_enabled():
        print(f"[DEBUG] Searching {len(candidates)} server candidates...")
    for idx, candidate in enumerate(candidates, 1):
        if is_verbose_logging_enabled():
            print(f"[DEBUG] Try #{idx}: {candidate}")
        if probe_server_base_url(candidate):
            if is_verbose_logging_enabled():
                print(f"[DEBUG] Found server: {candidate}")
            return candidate.rstrip("/")
    return None
```

**Code Changed To**:
```python
def discover_remote_server_base_url():
    candidates = build_server_base_url_candidates()
    if is_verbose_logging_enabled():
        print(f"[DEBUG] Searching {len(candidates)} server candidates...")
    
    admin_server_url = None
    admin_server_ip = None
    
    # First pass: find any working server (could be via hostname or indirect route)
    for idx, candidate in enumerate(candidates, 1):
        if is_verbose_logging_enabled():
            print(f"[DEBUG] Try #{idx}: {candidate}")
        if probe_server_base_url(candidate):
            if is_verbose_logging_enabled():
                print(f"[DEBUG] Found server: {candidate}")
            admin_server_url = candidate.rstrip("/")
            # Now request the actual admin IP from the server
            admin_server_ip = discover_server_ip_from_admin(admin_server_url)
            if admin_server_ip and is_verbose_logging_enabled():
                print(f"[DEBUG] Admin server IP: {admin_server_ip}")
            return admin_server_url
    
    return None
```

**Lines**: ~20 lines modified
**Changes**: 
- Added call to `discover_server_ip_from_admin()`
- Added logging for retrieved IP
- Now requests IP once server is found

---

## File 3: lan_agent.py

### Change: Enhanced server discovery function

**Location**: `discover_server_base_url()` (around line 248)

**Code Changed From**:
```python
def discover_server_base_url():
    global ACTIVE_SERVER_BASE_URL

    if ACTIVE_SERVER_BASE_URL and probe_server_base_url(ACTIVE_SERVER_BASE_URL):
        return ACTIVE_SERVER_BASE_URL

    for candidate in build_server_base_candidates():
        if probe_server_base_url(candidate):
            ACTIVE_SERVER_BASE_URL = candidate.rstrip("/")
            return ACTIVE_SERVER_BASE_URL
    return ""
```

**Code Changed To**:
```python
def discover_server_base_url():
    global ACTIVE_SERVER_BASE_URL

    if ACTIVE_SERVER_BASE_URL and probe_server_base_url(ACTIVE_SERVER_BASE_URL):
        return ACTIVE_SERVER_BASE_URL

    # Try all candidates to find server
    for candidate in build_server_base_candidates():
        if probe_server_base_url(candidate):
            ACTIVE_SERVER_BASE_URL = candidate.rstrip("/")
            
            # Now request the actual admin IP from the server
            try:
                info_url = candidate.rstrip("/") + "/api/server-info"
                with http_request.urlopen(info_url, timeout=2) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    if data.get("ok") and data.get("server_ip"):
                        server_ip = data.get("server_ip")
                        # Replace hostname with actual IP in the active URL
                        ACTIVE_SERVER_BASE_URL = f"http://{server_ip}:{SERVER_PORT}"
            except Exception:
                pass
            
            return ACTIVE_SERVER_BASE_URL

    return ""
```

**Lines**: ~15 lines added/modified
**Changes**:
- Added API call to get admin IP
- Replaces hostname with actual IP
- Falls back gracefully if API fails

---

## Summary of Changes

```
app.py
  ✅ Added: /api/server-info endpoint
  📊 Lines: +18
  
desktop_app.py
  ✅ Added: discover_server_ip_from_admin() function
  ✅ Enhanced: discover_remote_server_base_url() function
  📊 Lines: +35
  
lan_agent.py
  ✅ Enhanced: discover_server_base_url() function
  📊 Lines: +15
  
Total: ~70 lines of code added/modified
```

---

## How to Verify Changes

### Verify app.py
```bash
# Check endpoint exists
grep -n "api_server_info" app.py
# Should show: 1206:def api_server_info():

# Test endpoint
curl http://localhost:5000/api/server-info
# Should return JSON with ok: true
```

### Verify desktop_app.py
```bash
# Check new function
grep -n "discover_server_ip_from_admin" desktop_app.py
# Should show: 239:def discover_server_ip_from_admin

# Check it's called
grep -n "discover_server_ip_from_admin" desktop_app.py
# Should show two occurrences (definition + usage)
```

### Verify lan_agent.py
```bash
# Check enhancement
grep -n "server_ip = data.get" lan_agent.py
# Should show: 264:server_ip = data.get("server_ip")
```

---

## Testing the Changes

### Test 1: API Endpoint
```bash
python app.py
curl http://localhost:5000/api/server-info
# Response should be JSON with server_ip
```

### Test 2: Client Discovery
```bash
echo MY-ADMIN-PC > server_host.txt
set PYPONDO_VERBOSE=1
python desktop_app.py
# Look for: [DEBUG] Admin server IP: ...
```

### Test 3: LAN Agent
```bash
# Agent will use admin's actual IP for registration
# Check logs show IP being used correctly
```

---

## Backward Compatibility Check

✅ All changes are additive
✅ No existing functions removed
✅ No breaking changes to APIs
✅ Falls back gracefully if new API fails
✅ Existing configurations still work
✅ Zero impact if new endpoint not called

---

**All code changes are minimal, focused, and fully backward compatible!**
