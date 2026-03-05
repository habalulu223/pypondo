# PyPondo Quick Reference Card

## 🎯 What Was Fixed

### Problem 1: CMD Windows Spam ✅
- **Before**: CMD windows pop up repeatedly when running commands
- **After**: Commands execute silently, no visible windows
- **How**: Added `hidden_subprocess_kwargs()` to hide Windows

### Problem 2: Client on Another PC ✅  
- **Before**: Client can't find admin server on different PC
- **After**: Client auto-discovers or uses configuration file
- **How**: Created `server_host.txt` configuration system

---

## 🚀 5-Minute Setup for Client on Another PC

### Step 1: Build Client EXE (on admin PC)
```batch
build_desktop_exe.bat
```
→ Creates `dist/PyPondo.exe`

### Step 2: Copy EXE (to client PC)
Copy `PyPondo.exe` to client PC (Desktop, Documents, etc.)

### Step 3: Create Configuration (on client PC)
Create file `server_host.txt` in same folder as `PyPondo.exe`:
```
MY-ADMIN-PC
```
OR use IP address:
```
192.168.1.100
```

### Step 4: Run (on client PC)
Double-click `PyPondo.exe`

### Step 5: Verify (optional)
```batch
python test_client.py
```

---

## 🔍 Finding Admin Server IP

On admin PC, open Command Prompt and type:
```batch
ipconfig
```

Look for line like:
```
IPv4 Address . . . . . . . . . . . : 192.168.1.100
```

Use that IP in client's `server_host.txt`

---

## 🆘 Troubleshooting

| Problem | Solution |
|---------|----------|
| Client can't find server | Create `server_host.txt` with admin PC name/IP |
| Hostname doesn't work | Try IP address instead |
| Still not working | Run `python test_client.py` to diagnose |
| Want to see what's happening | `set PYPONDO_VERBOSE=1` before running |
| CMD windows still appear | You may have old version, re-copy the EXE |

---

## 📁 Key Files

### To Build Client
- `build_desktop_exe.bat` - Creates standalone EXE

### On Client PC
- `PyPondo.exe` - The client application
- `server_host.txt` - Your configuration file (create this!)

### For Setup/Testing  
- `setup_client.bat` - Automated setup wizard
- `test_client.py` - Test connectivity

### Documentation
- `QUICK_START_CLIENT.md` - Start here!
- `CLIENT_SETUP.md` - Detailed guide
- `FINAL_SUMMARY.txt` - Complete summary

---

## 💻 Commands Cheat Sheet

```batch
# Build client EXE
build_desktop_exe.bat

# Run with server config
set PYPONDO_SERVER_HOST=MY-ADMIN-PC
python desktop_app.py

# Test connectivity
python test_client.py

# Enable debug logging
set PYPONDO_VERBOSE=1

# Run setup wizard
setup_client.bat

# Run with PowerShell
.\setup_client.ps1
```

---

## 📋 server_host.txt Examples

### Example 1: Using Hostname (Recommended)
```
# Configuration file for PyPondo client
# Put your admin PC hostname below

OFFICE-PC
```

### Example 2: Using IP Address
```
# Configuration file for PyPondo client
# Put your admin PC IP address below

192.168.1.100
```

### Example 3: Multiple Servers (Try in order)
```
# Primary server
MAIN-ADMIN-PC

# Backup server
BACKUP-ADMIN-PC
```

---

## ✅ Checklist

- [ ] Admin server works (can login at http://localhost:5000)
- [ ] Ran `build_desktop_exe.bat` to create PyPondo.exe
- [ ] Copied PyPondo.exe to client PC
- [ ] Created server_host.txt on client PC with admin server name/IP
- [ ] Can double-click PyPondo.exe and see it connect
- [ ] Can login with same credentials as admin server
- [ ] No CMD windows appear
- [ ] Run `python test_client.py` successfully

---

## 🎓 Advanced

### Use Environment Variable Instead of File
```batch
set PYPONDO_SERVER_HOST=192.168.1.100
python desktop_app.py
```

### Use Different Port
```batch
set PYPONDO_SERVER_PORT=8000
python desktop_app.py
```

### Run in Headless Mode (no UI)
```batch
set PYPONDO_HEADLESS=1
python desktop_app.py
```

### Enable Verbose Debug Output
```batch
set PYPONDO_VERBOSE=1
python desktop_app.py
```

---

## 🔐 Security Notes

- Change default `LAN_AGENT_TOKEN` in `lan_agent.py` for production
- Use HTTPS for internet-exposed servers (not default)
- Default login: admin/admin (change this!)
- Firewall should allow port 5000 only for trusted networks

---

## 📞 Need Help?

| Question | Answer |
|----------|--------|
| Client won't start | Create `server_host.txt` with admin PC name/IP |
| Can't find server | Check admin PC is running, server name/IP is correct |
| Slow to start | First run installs dependencies, subsequent runs are faster |
| Port already in use | Change `APP_PORT` environment variable |
| Want to see logs | Run with `PYPONDO_VERBOSE=1` |

---

## 🎯 Most Common Issues & Fixes

### Issue: "Unable to locate admin app host"
**Fix**: 
1. Create file `server_host.txt`
2. Write your admin PC's hostname or IP in it
3. Run app again

### Issue: Client won't connect to server
**Fix**:
1. Check admin server is running
2. Check server_host.txt has correct hostname/IP  
3. Run: `python test_client.py` to diagnose
4. If using hostname, try IP address instead

### Issue: "Port 5000 already in use"
**Fix**:
```batch
set APP_PORT=5001
python desktop_app.py
```

### Issue: Seeing debug info but still not connecting
**Check**:
1. Are both PCs on same network?
2. Is firewall blocking port 5000?
3. Is admin PC actually running?

---

## 🚀 Next Steps

1. Read: `QUICK_START_CLIENT.md` (3-step guide)
2. Build: `build_desktop_exe.bat`
3. Deploy: Copy `PyPondo.exe` to client PC
4. Configure: Create `server_host.txt` on client
5. Test: Run `python test_client.py` 
6. Done! ✅

---

**Quick Reference Version 1.0 - March 2026**
