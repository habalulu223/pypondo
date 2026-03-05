# PyPondo Client - Quick Start (3 Steps)

## Step 1: Build the Client Executable
On your admin PC, open Command Prompt and run:
```batch
build_desktop_exe.bat
```

This creates `dist/PyPondo.exe`

## Step 2: Copy to Client PC
Copy `PyPondo.exe` to a folder on the client PC (e.g., Desktop or Documents)

## Step 3: Configure Server Address
In the same folder as `PyPondo.exe`, create a file named `server_host.txt` with your admin server's address.

**Option A - Use Computer Name (Recommended)**
```
MY-ADMIN-PC
```

**Option B - Use IP Address**
```
192.168.1.100
```

To find your admin server's IP:
- On admin PC, open Command Prompt
- Type: `ipconfig`
- Look for "IPv4 Address" line (e.g., `192.168.x.x`)

## Step 4: Run
Double-click `PyPondo.exe` on client PC. That's it!

---

## Troubleshooting

**Q: App shows "Unable to locate admin app host"**
- Make sure `server_host.txt` exists in the same folder as `PyPondo.exe`
- Check the hostname/IP is correct
- Make sure admin server is running on the other PC
- Try ping: Open Command Prompt and type `ping YOUR-ADMIN-PC`

**Q: Still not working?**
- Run with debug output: `set PYPONDO_VERBOSE=1` then `PyPondo.exe`
- This shows what servers it's trying to connect to

---

## For Developers: Python Script Mode

If you prefer running as Python script instead of EXE:

1. Copy to client PC:
   - `desktop_app.py`
   - `app.py`
   - `lan_agent.py`
   - `templates/` folder

2. Create `server_host.txt` with admin server address

3. Install Python 3.8+ and run:
   ```batch
   python -m pip install flask flask-sqlalchemy flask-login werkzeug
   python desktop_app.py
   ```
