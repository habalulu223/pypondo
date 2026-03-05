#!/usr/bin/env python3
"""
Test script to verify gateway discovery and app independence.
Run this to test if client app can detect admin app.
"""

import os
import sys
import subprocess

def test_gateway_discovery():
    """Test that gateway discovery works."""
    print("=" * 60)
    print("Testing Gateway Discovery")
    print("=" * 60)
    
    if os.name != "nt":
        print("WARNING: Gateway discovery only works on Windows")
        return False
    
    try:
        # Run ipconfig to get gateway info
        output = subprocess.check_output(
            ["ipconfig"],
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=4
        )
        
        gateways = []
        for line in output.splitlines():
            if "Default Gateway" not in line:
                continue
            _, _, remainder = line.partition(":")
            for ip_str in remainder.split():
                parts = ip_str.strip().split(".")
                if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                    if ip_str not in gateways:
                        gateways.append(ip_str)
        
        if gateways:
            print(f"✓ Found {len(gateways)} gateway IP(s):")
            for gw in gateways:
                print(f"  - {gw}")
            return True
        else:
            print("✗ No gateway IPs found in ipconfig output")
            return False
            
    except Exception as e:
        print(f"✗ Error running ipconfig: {e}")
        return False


def test_imports():
    """Test that all required imports are available."""
    print("\n" + "=" * 60)
    print("Testing Required Imports")
    print("=" * 60)
    
    modules = [
        "flask",
        "flask_sqlalchemy",
        "flask_login",
        "werkzeug",
        "sqlalchemy",
    ]
    
    missing = []
    for module in modules:
        try:
            __import__(module)
            print(f"✓ {module}")
        except ImportError as e:
            print(f"✗ {module}: {e}")
            missing.append(module)
    
    if missing:
        print(f"\nMissing modules: {', '.join(missing)}")
        print("Install with: pip install flask flask-sqlalchemy flask-login werkzeug")
        return False
    
    return True


def test_app_independence():
    """Test that apps don't depend on PyCharm."""
    print("\n" + "=" * 60)
    print("Testing App Independence (No PyCharm Dependencies)")
    print("=" * 60)
    
    files_to_check = [
        "app.py",
        "desktop_app.py", 
        "lan_agent.py"
    ]
    
    pycharm_keywords = ["pycharm", "ide", "jetbrains", "intellij"]
    issues = []
    
    for filename in files_to_check:
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read().lower()
                for keyword in pycharm_keywords:
                    if keyword in content:
                        issues.append(f"{filename}: contains '{keyword}'")
        except FileNotFoundError:
            print(f"⚠ {filename} not found")
    
    if issues:
        print("✗ Found PyCharm dependencies:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print("✓ No PyCharm dependencies found")
        print("✓ Apps can run independently from PyCharm")
        return True


def test_gateway_discovery_code():
    """Test that gateway discovery functions exist in code."""
    print("\n" + "=" * 60)
    print("Testing Gateway Discovery Code")
    print("=" * 60)
    
    files_to_check = {
        "desktop_app.py": "discover_default_gateway_ips",
        "lan_agent.py": "discover_default_gateway_ips",
    }
    
    all_ok = True
    for filename, function_name in files_to_check.items():
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
                if function_name in content:
                    print(f"✓ {filename}: contains {function_name}()")
                else:
                    print(f"✗ {filename}: missing {function_name}()")
                    all_ok = False
        except FileNotFoundError:
            print(f"✗ {filename} not found")
            all_ok = False
    
    return all_ok


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("PyPondo App Independence & Gateway Discovery Tests")
    print("=" * 60)
    
    results = {
        "Gateway Discovery": test_gateway_discovery(),
        "Required Imports": test_imports(),
        "App Independence": test_app_independence(),
        "Gateway Code": test_gateway_discovery_code(),
    }
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name}: {status}")
    
    all_passed = all(results.values())
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ All tests passed!")
        print("\nYou can now run:")
        print("  python app.py          # Admin app")
        print("  python desktop_app.py  # Client app (auto-discovers admin)")
        return 0
    else:
        print("✗ Some tests failed. See above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
