#!/usr/bin/env python3
"""
PyPondo Configuration Helper
Helps set up client app to connect to admin app on another PC
"""

import os
import sys
import subprocess
import socket
from urllib import request as http_request
from urllib import error as http_error

def hidden_subprocess_kwargs():
    """Return kwargs to hide subprocess windows on Windows."""
    if os.name != "nt":
        return {}

    kwargs = {}
    create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if create_no_window:
        kwargs["creationflags"] = create_no_window

    startupinfo_type = getattr(subprocess, "STARTUPINFO", None)
    startf_use_showwindow = getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
    sw_hide = getattr(subprocess, "SW_HIDE", 0)
    if startupinfo_type and startf_use_showwindow:
        startupinfo = startupinfo_type()
        startupinfo.dwFlags |= startf_use_showwindow
        startupinfo.wShowWindow = sw_hide
        kwargs["startupinfo"] = startupinfo

    return kwargs

def get_local_ip():
    """Get this machine's local IP address."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return None

def get_gateway_ip():
    """Get default gateway IP."""
    if os.name != "nt":
        return None
    
    try:
        output = subprocess.check_output(
            ["ipconfig"],
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=4,
            **hidden_subprocess_kwargs()
        )
    except Exception:
        return None
    
    for line in output.splitlines():
        if "Default Gateway" not in line:
            continue
        _, _, remainder = line.partition(":")
        for ip_str in remainder.split():
            parts = ip_str.strip().split(".")
            if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                return ip_str
    return None

def test_connection(host, port=5000):
    """Test if admin app is running on given host."""
    for path in ["/login", "/api/agent/register-lan"]:
        target = f"http://{host}:{port}{path}"
        try:
            with http_request.urlopen(target, timeout=1.5):
                return True
        except http_error.HTTPError as exc:
            if 200 <= exc.code < 500:
                return True
        except Exception:
            continue
    return False

def main():
    """Interactive configuration wizard."""
    print("\n" + "=" * 60)
    print("PyPondo Configuration Helper")
    print("=" * 60)
    print()
    
    # Detect local info
    local_ip = get_local_ip()
    gateway_ip = get_gateway_ip()
    
    print("Detected Configuration:")
    print(f"  Your Local IP: {local_ip}")
    print(f"  Network Gateway: {gateway_ip}")
    print()
    
    # Menu
    print("Configuration Options:")
    print("  1. Specify admin app IP address")
    print("  2. Test admin app connection")
    print("  3. Create server_host.txt")
    print("  4. Run client app with configuration")
    print("  5. Exit")
    print()
    
    choice = input("Select option [1-5]: ").strip()
    
    if choice == "1":
        admin_ip = input("\nEnter admin app IP address: ").strip()
        print(f"Configuring client to use: {admin_ip}")
        os.environ["PYPONDO_SERVER_HOST"] = admin_ip
        print("✓ Configuration saved to environment")
        print("\nRun client with:")
        print(f'  $env:PYPONDO_SERVER_HOST="{admin_ip}"')
        print("  python desktop_app.py")
        
    elif choice == "2":
        admin_ip = input("\nEnter IP to test: ").strip()
        print(f"\nTesting connection to {admin_ip}:5000...")
        if test_connection(admin_ip, 5000):
            print("✓ Admin app found and responding!")
            print(f"\nRun client with:")
            print(f'  $env:PYPONDO_SERVER_HOST="{admin_ip}"')
            print("  python desktop_app.py")
        else:
            print("✗ Admin app not found on that IP")
            print("  Make sure:")
            print("    1. Admin IP is correct")
            print("    2. Admin app is running (python app.py)")
            print("    3. Firewall allows port 5000")
    
    elif choice == "3":
        print("\nCreating server_host.txt...")
        admin_ip = input("Enter admin app IP address: ").strip()
        with open("server_host.txt", "w") as f:
            f.write(f"# Admin app location\n{admin_ip}\n")
        print("✓ server_host.txt created with admin IP")
        print("\nNow run client with:")
        print("  python desktop_app.py")
    
    elif choice == "4":
        admin_ip = input("\nEnter admin app IP address: ").strip()
        if not test_connection(admin_ip, 5000):
            print(f"⚠ Warning: Cannot reach {admin_ip}:5000")
            cont = input("Continue anyway? [y/N]: ").strip().lower()
            if cont != 'y':
                return
        
        print(f"\nStarting client app connecting to {admin_ip}...")
        os.environ["PYPONDO_SERVER_HOST"] = admin_ip
        os.environ["PYPONDO_VERBOSE"] = "1"
        
        try:
            import desktop_app
            sys.exit(desktop_app.main())
        except Exception as e:
            print(f"Error starting client app: {e}")
    
    elif choice == "5":
        print("Goodbye!")
        return
    
    else:
        print("Invalid choice")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        sys.exit(0)