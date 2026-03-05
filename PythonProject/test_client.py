#!/usr/bin/env python3
"""
PyPondo Client Connectivity Test
Verifies that the client can find and connect to the admin server
"""

import os
import sys
import socket
import subprocess
import time
from urllib import request as http_request
from urllib import error as http_error


def print_header(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def check_python_version():
    """Verify Python 3.8+"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ FAIL: Python 3.8+ required")
        print(f"   Current: {sys.version}")
        return False
    print(f"✅ PASS: Python {version.major}.{version.minor}")
    return True


def check_core_packages():
    """Verify Flask and dependencies"""
    required = ["flask", "flask_sqlalchemy", "flask_login"]
    missing = []
    
    for package in required:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package}")
            missing.append(package)
    
    if missing:
        print(f"\n❌ FAIL: Missing packages: {', '.join(missing)}")
        return False
    print("\n✅ PASS: All core packages installed")
    return True


def check_server_config():
    """Check server_host.txt configuration"""
    if os.path.exists("server_host.txt"):
        with open("server_host.txt", "r") as f:
            config = f.read().strip()
            config_lines = [line.strip() for line in config.split('\n') 
                           if line.strip() and not line.strip().startswith('#')]
            if config_lines:
                print(f"✅ Found server_host.txt")
                for line in config_lines:
                    print(f"   Server: {line}")
                return True, config_lines[0]
    
    print("❌ FAIL: server_host.txt not found")
    print("   Create server_host.txt with admin server hostname/IP")
    return False, None


def check_network_connectivity(host):
    """Test network connectivity to admin server"""
    if not host:
        return False
    
    print(f"Testing connectivity to: {host}")
    
    # Try direct connection
    if not os.name == "nt":
        cmd = ["ping", "-c", "1", "-W", "1000", host]
    else:
        cmd = ["ping", "-n", "1", "-w", "1000", host]
    
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=5)
        if result.returncode == 0:
            print(f"✅ PASS: Ping successful to {host}")
            return True
    except Exception as e:
        pass
    
    print(f"❌ WARNING: Could not ping {host}")
    print("   This might be normal if hostname resolution fails")
    print("   Will attempt HTTP connection instead...")
    return None


def check_http_connection(host, port=5000):
    """Test HTTP connection to admin server"""
    paths = ["/login", "/api/agent/register-lan"]
    
    for path in paths:
        url = f"http://{host}:{port}{path}"
        try:
            print(f"   Trying {url}...", end=" ", flush=True)
            with http_request.urlopen(url, timeout=2):
                print("✅")
                print(f"\n✅ PASS: Admin server is reachable at http://{host}:{port}")
                return True
        except http_error.HTTPError as e:
            if 200 <= e.code < 500:
                print(f"✅ (HTTP {e.code})")
                print(f"\n✅ PASS: Admin server is reachable at http://{host}:{port}")
                return True
        except Exception as e:
            print(f"❌")
    
    print(f"❌ FAIL: Could not connect to admin server")
    print(f"   Make sure admin server is running on {host}:5000")
    return False


def check_local_ip():
    """Get local IP address"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        print(f"✅ Local IP: {ip}")
        return ip
    except Exception as e:
        print(f"❌ Could not determine local IP: {e}")
        return None


def main():
    print_header("PyPondo Client Connectivity Test")
    
    results = []
    
    # Check Python version
    print_header("1. Python Version")
    results.append(("Python Version", check_python_version()))
    
    # Check packages
    print_header("2. Required Packages")
    results.append(("Core Packages", check_core_packages()))
    
    # Check local network
    print_header("3. Local Network Configuration")
    local_ip = check_local_ip()
    results.append(("Local IP", local_ip is not None))
    
    # Check server configuration
    print_header("4. Server Configuration")
    config_ok, server_host = check_server_config()
    results.append(("Server Config", config_ok))
    
    if not config_ok:
        print_header("Configuration Required")
        print("To connect to admin server, create server_host.txt with:")
        print("\nOption A (Hostname):")
        print("  MY-ADMIN-PC\n")
        print("Option B (IP Address):")
        print("  192.168.1.100\n")
        print("Then run this test again.")
        return 1
    
    # Check network connectivity
    print_header("5. Network Connectivity")
    ping_result = check_network_connectivity(server_host)
    results.append(("Network Ping", ping_result is not False))
    
    # Check HTTP connection
    print_header("6. HTTP Connection to Admin Server")
    http_ok = check_http_connection(server_host)
    results.append(("HTTP Connection", http_ok))
    
    # Summary
    print_header("Test Summary")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if http_ok:
        print("\n" + "=" * 60)
        print("  ✅ ALL CHECKS PASSED!")
        print("  Your client should be able to connect to the admin server.")
        print("  You can now run: python desktop_app.py")
        print("=" * 60 + "\n")
        return 0
    else:
        print("\n" + "=" * 60)
        print("  ❌ CONNECTIVITY TEST FAILED")
        print("  Please check the server_host.txt configuration.")
        print("=" * 60 + "\n")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user.")
        sys.exit(1)
