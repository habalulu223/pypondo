#!/usr/bin/env python3
"""
PyPondo client auto-configuration helper.

Scans for the admin app, writes server_host.txt when a reachable server is
found, and optionally launches the desktop client with --launch.
"""

import os
import re
import socket
import subprocess
import sys
from urllib import error as http_error
from urllib import request as http_request


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
            **hidden_subprocess_kwargs(),
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


def get_arp_hosts():
    """Return active IPv4 neighbors from the local ARP cache."""
    if os.name != "nt":
        return []

    try:
        output = subprocess.check_output(
            ["arp", "-a"],
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=4,
            **hidden_subprocess_kwargs(),
        )
    except Exception:
        return []

    hosts = []
    for match in re.finditer(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", output):
        ip = match.group(0)
        if ip.startswith(("127.", "169.254.", "224.", "239.", "255.")):
            continue
        if ip not in hosts:
            hosts.append(ip)
    return hosts


def test_connection(host, port=5000):
    """Test if admin app is running on the given host."""
    for path in ("/api/server-info", "/login", "/api/agent/register-lan"):
        target = f"http://{host}:{port}{path}"
        try:
            with http_request.urlopen(target, timeout=1.2):
                return True
        except http_error.HTTPError as exc:
            if 200 <= exc.code < 500:
                return True
        except Exception:
            continue
    return False


def add_candidate(candidates, host):
    host = str(host or "").strip()
    if host and host not in candidates:
        candidates.append(host)


def build_auto_candidates():
    candidates = []

    for env_name in ("PYPONDO_SERVER_HOST", "PYPONDO_ADMIN_IP", "LAN_SERVER_HOST"):
        add_candidate(candidates, os.getenv(env_name, ""))

    if os.path.exists("server_host.txt"):
        try:
            with open("server_host.txt", "r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if line and not line.startswith("#"):
                        add_candidate(candidates, line)
        except Exception:
            pass

    add_candidate(candidates, "127.0.0.1")
    add_candidate(candidates, "localhost")
    add_candidate(candidates, get_gateway_ip())

    local_ip = get_local_ip()
    add_candidate(candidates, local_ip)
    if local_ip:
        parts = local_ip.split(".")
        if len(parts) == 4:
            prefix = ".".join(parts[:3])
            try:
                local_suffix = int(parts[3])
            except ValueError:
                local_suffix = 0
            suffixes = list(range(max(1, local_suffix - 8), min(254, local_suffix + 8) + 1))
            suffixes.extend([1, 2, 10, 50, 100, 101, 102, 150, 200, 254])
            for suffix in suffixes:
                if suffix != local_suffix:
                    add_candidate(candidates, f"{prefix}.{suffix}")

    for host in get_arp_hosts():
        add_candidate(candidates, host)

    return candidates


def save_server_host(host):
    with open("server_host.txt", "w", encoding="utf-8") as handle:
        handle.write("# Auto-detected admin app location\n")
        handle.write(f"{host}\n")


def main():
    print("\n" + "=" * 60)
    print("PyPondo Auto Configuration Helper")
    print("=" * 60)
    print()

    print("Detected Configuration:")
    print(f"  Your Local IP: {get_local_ip()}")
    print(f"  Network Gateway: {get_gateway_ip()}")
    print()

    print("Scanning for the admin app...")
    for host in build_auto_candidates():
        print(f"  Trying {host}:5000...")
        if test_connection(host, 5000):
            save_server_host(host)
            os.environ["PYPONDO_SERVER_HOST"] = host
            print(f"[OK] Admin app found at {host}:5000")
            print("[OK] server_host.txt updated automatically")
            if "--launch" in sys.argv:
                import desktop_app

                return desktop_app.main()
            return 0

    print("[WARN] No reachable admin app found. The desktop client will keep auto-discovering at startup.")
    if "--launch" in sys.argv:
        import desktop_app

        return desktop_app.main()
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        raise SystemExit(0)
