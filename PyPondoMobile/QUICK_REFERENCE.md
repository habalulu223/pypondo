# Cross-LAN Discovery - Quick Reference Guide

## 🎯 Quick Start (2 Minutes)

### For End Users
```
1. Open PyPondo Mobile APK
2. Click "Discover servers" button in Connection panel
3. Wait 10-30 seconds for scan
4. Click server from list (or auto-connects if only one)
5. Done! Ready to log in
```

### For Testing
```bash
# Make sure server is running
cd PythonProject
python app.py

# In different network/device
# Open APK → "Discover servers" → Select server
```

---

## 🧪 Testing Scenarios

### Test 1: Same WiFi Network (Fastest)
**Setup**: Server and phone on same WiFi  
**Expected**: Server found in 2-5 seconds  
**Action**:
1. Start server: `python app.py`
2. Open app, click "Discover servers"
3. Should find server via gateway
4. Response time ~50-100ms

### Test 2: Different Router (Adjacent Subnet)
**Setup**: Server on different WiFi, but routers connected  
**Expected**: Server found in 5-10 seconds  
**Action**:
1. Server on 192.168.1.x network
2. Phone on 192.168.2.x network (if networks are bridged)
3. Click "Discover servers"
4. May find via gateway probe
5. Response time 100-300ms

### Test 3: Single Server Auto-Connect
**Setup**: Only one server running  
**Expected**: Auto-connects without user selection  
**Action**:
1. Only one PyPondo instance: `python app.py`
2. Click "Discover servers"
3. Status shows "Found 1 server! Attempting..."
4. Auto-connects without list
5. Server info displays

### Test 4: Multiple Servers
**Setup**: Multiple servers on different ports  
**Expected**: Shows list, allows selection  
**Action**:
1. Start server 1: `PYPONDO_SERVER_PORT=5000 python app.py`
2. Start server 2: `PYPONDO_SERVER_PORT=5001 python app.py`
3. Click "Discover servers"
4. Shows list with both servers
5. Can select either one
6. Connects to selected

### Test 5: No Servers
**Setup**: No servers running  
**Expected**: Shows helpful message  
**Action**:
1. Kill all servers
2. Click "Discover servers"
3. After 30 seconds shows: "No PyPondo servers found..."
4. Can enter address manually
5. Manual entry works

### Test 6: Firewall Blocked
**Setup**: Server running but firewall blocks port  
**Expected**: Not found, manual entry works  
**Action**:
1. Server running but port blocked
2. Click "Discover servers"
3. Nothing found (times out)
4. Enter IP manually: works anyway if firewall allows specific access

---

## 📊 Expected Results

### Discovery Time vs Network Type
| Scenario | Time | Confidence |
|----------|------|-----------|
| Same WiFi (gateway) | 2-5s | Very High |
| Adjacent subnet | 5-10s | High |
| Subnet scan only | 15-30s | Medium |
| No server | 30s + timeout | N/A |

### Response Times
| Network | Typical |
|---------|---------|
| Same WiFi | 50-100ms |
| Local network | 100-200ms |
| Adjacent subnet | 200-500ms |
| Distant subnet | 500-1000ms |

### Success Rates
- **Same network**: 95%+ (via gateway)
- **Adjacent networks**: 80%+ (if accessible)
- **Blocked networks**: 0% (use manual entry)

---

## 🔧 Troubleshooting

### "Scanning..." button stuck
**Fix**:
- Wait full 30 seconds
- If still stuck, refresh browser
- Check network connectivity
- Try "Reset saved data"

### Found server but can't connect
**Fix**:
- Verify server IP shown is correct
- Check server is actually running
- Check firewall allows connection
- Try manual entry with explicit IP

### Discovery very slow (>30 seconds)
**Fix**:
- Normal for remote networks
- Check WiFi signal strength
- Move closer to router
- Try wired connection if possible

### WebRTC blocked error
**Fix**:
- Some corporate networks block WebRTC
- Try manual entry with known IP
- Contact network administrator
- May need VPN

---

## 🚀 Performance Tips

### Speed Up Discovery
1. **Bring phone closer to router** - Faster WiFi = faster scan
2. **Use 5GHz WiFi** - Faster than 2.4GHz if available
3. **Wired connection on server** - More stable, often faster
4. **Fewer devices** - Less network congestion

### Reduce Network Load
- Discovery uses ~120 concurrent probes
- Spread over 10-30 seconds
- Minimal data transfer
- Safe for metered connections

---

## ✅ Verification Checklist

### Server Side
- [ ] `/api/server-info` endpoint returns data
  ```bash
  curl http://localhost:5000/api/server-info
  ```
- [ ] Server has fixed or stable IP
- [ ] Firewall allows port 5000 (or custom port)
- [ ] Server process is running

### Client Side
- [ ] WiFi connected
- [ ] App has network permissions
- [ ] WebRTC not blocked (or manual entry fallback)
- [ ] Phone can ping server (optional test)

### Discovery Test
- [ ] Button responds to clicks
- [ ] Shows progress counter
- [ ] Finds at least one server
- [ ] Server info displays correctly
- [ ] Can connect after selection

---

## 📝 Common Commands

### Start Server
```bash
cd PythonProject
python app.py
# Server running on http://localhost:5000
```

### Start Multiple Servers (Testing)
```bash
# Terminal 1
python app.py  # Port 5000

# Terminal 2
PYPONDO_SERVER_PORT=5001 python app.py  # Port 5001

# Terminal 3
PYPONDO_SERVER_PORT=5002 python app.py  # Port 5002
```

### Test Server Info Endpoint
```bash
# Linux/Mac
curl http://localhost:5000/api/server-info | jq

# Windows PowerShell
Invoke-WebRequest http://localhost:5000/api/server-info
```

### Check Network Connectivity
```bash
# Ping server
ping 192.168.1.100

# Test specific port
telnet 192.168.1.100 5000

# Quick server check
curl http://192.168.1.100:5000/api/server-info
```

---

## 🐛 Debug Mode

### Enable Verbose Logging (if implemented)
```javascript
// In browser console (F12)
localStorage.setItem('pypondo.debug', '1')
// Reload app
// Check console for detailed discovery logs
```

### Check Browser Console
1. Open app in browser or mobile dev tools
2. Press F12 (or right-click → Inspect)
3. Go to Console tab
4. Look for discovery logs
5. Check for errors or timeouts

### Network Traffic Analysis
1. Open Dev Tools → Network tab
2. Click "Discover servers"
3. Watch HTTP requests
4. See response times
5. Check for failed requests

---

## 🎓 Understanding the Results

### Discovery Source Meanings
- **gateway** - Found via gateway IP probe (most reliable)
- **subnet** - Found via subnet IP scanning
- **mdns** - Found via mDNS/Bonjour (future feature)
- **broadcast** - Found via broadcast discovery (future feature)

### Response Time Interpretation
- **<100ms** - Same local network
- **100-300ms** - Adjacent network or slower WiFi
- **300-1000ms** - Distant network or high latency
- **>1000ms** - Very slow or poor connection

### Best Server Choice
- **Fastest response** - Usually most reliable
- **Gateway source** - Usually more stable
- **Lowest latency** - Best for real-time operations

---

## 🔒 Security Notes

### Discovery Doesn't Expose
- ✅ No passwords
- ✅ No user data
- ✅ No sensitive config
- ✅ Only server metadata

### Discovery Does Expose
- Server IP address (already known if finding it)
- Server hostname (non-sensitive)
- Server port (already open)
- App version (public info)

### Safe for Use
- Discovery endpoint is public (no auth required)
- Same security as /login page
- No additional vulnerabilities
- Can be disabled with firewall if needed

---

## 📚 Related Docs

- `CROSS_LAN_DISCOVERY.md` - Full technical documentation
- `IMPLEMENTATION_SUMMARY.md` - Implementation overview
- `src/discovery.ts` - Source code with comments
- `src/App.tsx` - UI integration code

---

## 💡 Tips & Tricks

### Manual Entry Still Works
```
If discovery fails:
1. Get server IP manually
2. Type into "Server address" field
3. Click "Connect"
4. Works exactly as before
```

### Resetting Everything
```
If app behaves oddly:
1. Click "Reset saved data"
2. Clears all saved config and session
3. Fresh start for discovery
4. Can discover again
```

### Finding Your Server's IP
```bash
# On server machine
# Windows
ipconfig

# Mac/Linux
ifconfig

# Look for IPv4 address like: 192.168.1.100
```

### Testing Without WiFi
```
If testing locally on same machine:
- Enter: localhost:5000
- Or: 127.0.0.1:5000
- Manual entry always works
```

---

## ⏱️ Typical Session Timeline

```
00:00 - User clicks "Discover servers"
00:02 - Gateway discovery finds 1st server
00:05 - WebRTC detects local IP
00:08 - Subnet scan starts
00:25 - Last subnet IP probed
00:28 - Results deduplicated
00:30 - UI shows 3 servers found
00:31 - User selects one
00:32 - Server info displayed
00:33 - User clicks on server
00:34 - Connected to server
00:35 - Server info shows on dashboard
```

---

## 🎯 Next Steps

After successful discovery:
1. App shows server info on dashboard
2. Sign in with your credentials
3. App loads bookings and PC list
4. Ready to use all features!

---

**Happy discovering! 🚀**
