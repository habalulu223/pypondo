# PyPondo Client Setup Guide

This guide explains how to set up and run the PyPondo client app on another PC to connect to your admin server.

## Prerequisites

- **Admin Server Running**: You must have the PyPondo admin server running on one PC
- **Network Connection**: Client PC must be on the same network as the admin server
- **Python 3.8+** (for script mode) OR **Pre-built executable** (standalone)

## Option 1: Using Pre-built Executable (Easiest)

### Step 1: Get the Executable
Build the executable on your admin PC:
```batch
build_desktop_exe.bat
```

This creates `dist/PyPondo.exe` - a standalone app that doesn't require Python.

### Step 2: Copy to Client PC
Copy the entire `PyPondo.exe` file to the client PC.

### Step 3: Create Server Configuration
On the client PC, create a `server_host.txt` file in the same folder as `PyPondo.exe` with:

**Option A: Use Computer Name** (Recommended)
```
ADMIN-PC-NAME
```

**Option B: Use IP Address**
```
192.168.1.100
```

**Option C: Use Fully Qualified Domain Name**
```
admin.local
admin.example.com
```

### Step 4: Run the Client
Double-click `PyPondo.exe` on the client PC. It will automatically:
1. Search for the admin server using the name/IP from server_host.txt
2. Try to discover the gateway IP (network router)
3. Connect to the admin server
4. Open the login screen

## Option 2: Using Python Script Mode

### Step 1: Install Python
Install Python 3.8+ on the client PC if not already installed.

### Step 2: Copy Client Files
Copy these files to the client PC in a folder:
- `desktop_app.py`
- `app.py`
- `lan_agent.py`
- `templates/` (folder)

### Step 3: Create Server Configuration
Create `server_host.txt` in the same folder with the admin server's hostname or IP.

### Step 4: Install Dependencies
On the client PC, open Command Prompt in the folder and run:
```batch
pip install flask flask-sqlalchemy flask-login werkzeug
```

Optionally install UI dependencies:
```batch
pip install pywebview
```

### Step 5: Run the Client
```batch
python desktop_app.py
```

## Troubleshooting

### Client Can't Find Server
**Problem**: "Unable to locate admin app host"

**Solutions**:
1. Check the admin server is running: `http://ADMIN-IP:5000/login`
2. Verify server_host.txt has correct hostname/IP
3. Try IP address instead of computer name
4. Check network connectivity: Ping the admin PC from client PC
5. Check firewall: Port 5000 must be open on admin PC

### Server Name Not Resolving
**Problem**: Client finds gateway but not the actual server

**Solution**: Use IP address instead of hostname in server_host.txt

### Still Not Working?
1. Get the admin server's IP address:
   - On admin PC, run `ipconfig` in Command Prompt
   - Look for "IPv4 Address" (e.g., `192.168.1.100`)

2. On client PC, create `server_host.txt`:
   ```
   192.168.1.100
   ```

3. Ensure both PCs are on the same network

## Auto-Discovery Features

The client automatically searches for the admin server in this order:
1. Explicit configuration (server_host.txt or environment variable)
2. Network gateway IP (auto-detected from router)
3. Local network scan (attempts to find other PCs)
4. All IPv4 addresses on the local machine

## Environment Variables (Advanced)

You can set these variables instead of using server_host.txt:

```batch
set PYPONDO_SERVER_HOST=admin-pc-name
set PYPONDO_SERVER_PORT=5000
```

Then run:
```batch
python desktop_app.py
```

## Notes

- The client app is completely independent - no PyCharm or IDE required
- All communication happens over HTTP on port 5000 (by default)
- The database and configs are stored separately on client and server
- First time login requires admin credentials set up on the server
