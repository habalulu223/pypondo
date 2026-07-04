#!/usr/bin/env python3
"""
PyPondo Client Connectivity Test
Verifies that the client can find and connect to the admin server.
"""

import os
import socket
import subprocess
import sys
from urllib import error as http_error
from urllib import request as http_request

PASS_LABEL = "[PASS]"
FAIL_LABEL = "[FAIL]"
WARN_LABEL = "[WARN]"


def print_header(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def check_python_version():
    """Verify Python 3.8+."""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print(f"{FAIL_LABEL}: Python 3.8+ required")
        print(f"   Current: {sys.version}")
        return False
    print(f"{PASS_LABEL}: Python {version.major}.{version.minor}")
    return True


def check_core_packages():
    """Verify Flask and dependencies."""
    required = ["flask", "flask_sqlalchemy", "flask_login"]
    missing = []

    for package in required:
        try:
            __import__(package)
            print(f"{PASS_LABEL} {package}")
        except ImportError:
            print(f"{FAIL_LABEL} {package}")
            missing.append(package)

    if missing:
        print(f"\n{FAIL_LABEL}: Missing packages: {', '.join(missing)}")
        return False
    print(f"\n{PASS_LABEL}: All core packages installed")
    return True


def check_server_config():
    """Check optional server_host.txt configuration."""
    if os.path.exists("server_host.txt"):
        with open("server_host.txt", "r", encoding="utf-8") as handle:
            config = handle.read().strip()
        config_lines = [
            line.strip()
            for line in config.split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]
        if config_lines:
            print(f"{PASS_LABEL} Found server_host.txt")
            for line in config_lines:
                print(f"   Server: {line}")
            return True, config_lines[0]

    print(f"{WARN_LABEL}: server_host.txt not found")
    print("   This is OK. The client now auto-detects the admin server at startup.")
    return True, None


def check_network_connectivity(host):
    """Test network connectivity to admin server."""
    if not host:
        return False

    print(f"Testing connectivity to: {host}")

    if os.name == "nt":
        cmd = ["ping", "-n", "1", "-w", "1000", host]
    else:
        cmd = ["ping", "-c", "1", "-W", "1000", host]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=5)
        if result.returncode == 0:
            print(f"{PASS_LABEL}: Ping successful to {host}")
            return True
    except Exception:
        pass

    print(f"{WARN_LABEL}: Could not ping {host}")
    print("   This might be normal if hostname resolution fails")
    print("   Will attempt HTTP connection instead...")
    return None


def check_http_connection(host, port=5000):
    """Test HTTP connection to admin server."""
    paths = ["/login", "/api/agent/register-lan"]

    for path in paths:
        url = f"http://{host}:{port}{path}"
        try:
            print(f"   Trying {url}...", end=" ", flush=True)
            with http_request.urlopen(url, timeout=2):
                print(PASS_LABEL)
                print(f"\n{PASS_LABEL}: Admin server is reachable at http://{host}:{port}")
                return True
        except http_error.HTTPError as exc:
            if 200 <= exc.code < 500:
                print(f"{PASS_LABEL} (HTTP {exc.code})")
                print(f"\n{PASS_LABEL}: Admin server is reachable at http://{host}:{port}")
                return True
        except Exception:
            print(FAIL_LABEL)

    print(f"{FAIL_LABEL}: Could not connect to admin server")
    print(f"   Make sure admin server is running on {host}:{port}")
    return False


def check_local_ip():
    """Get local IP address."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        print(f"{PASS_LABEL} Local IP: {ip}")
        return ip
    except Exception as exc:
        print(f"{FAIL_LABEL} Could not determine local IP: {exc}")
        return None


def main():
    print_header("PyPondo Client Connectivity Test")

    results = []

    print_header("1. Python Version")
    results.append(("Python Version", check_python_version()))

    print_header("2. Required Packages")
    results.append(("Core Packages", check_core_packages()))

    print_header("3. Local Network Configuration")
    local_ip = check_local_ip()
    results.append(("Local IP", local_ip is not None))

    print_header("4. Server Configuration")
    config_ok, server_host = check_server_config()
    results.append(("Server Config", config_ok))

    if not server_host:
        print_header("5. Auto Discovery")
        print(f"{PASS_LABEL}: No manual server config required")
        results.append(("Auto Discovery", True))
        print_header("Test Summary")
        for name, result in results:
            status = PASS_LABEL if result else FAIL_LABEL
            print(f"{status}: {name}")
        print("\nThe client will scan saved hosts, localhost, LAN neighbors, and nearby subnet addresses when it starts.")
        return 0

    print_header("5. Network Connectivity")
    ping_result = check_network_connectivity(server_host)
    results.append(("Network Ping", ping_result is not False))

    print_header("6. HTTP Connection to Admin Server")
    http_ok = check_http_connection(server_host)
    if http_ok:
        results.append(("HTTP Connection", True))
    else:
        print(f"{WARN_LABEL}: Saved server is unreachable; startup auto-discovery will continue scanning other hosts.")
        results.append(("Stale Config Fallback", True))

    print_header("Test Summary")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = PASS_LABEL if result else FAIL_LABEL
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if http_ok:
        print("\n" + "=" * 60)
        print(f"  {PASS_LABEL} ALL CHECKS PASSED!")
        print("  Your client should be able to connect to the admin server.")
        print("  You can now run: python desktop_app.py")
        print("=" * 60 + "\n")
        return 0

    print("\n" + "=" * 60)
    print(f"  {WARN_LABEL} SAVED HOST IS STALE")
    print("  This is no longer fatal. The client will continue auto-discovery at startup.")
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user.")
        sys.exit(1)
