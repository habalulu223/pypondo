#!/usr/bin/env python3
"""
PyPondo Netlify Deployment Helper Script

This script helps with setting up and testing Netlify deployment for PyPondo.
"""

import os
import sys
import subprocess
import webbrowser
from pathlib import Path

def print_header(title: str):
    """Print a formatted header."""
    print("\n" + "=" * 50)
    print(f"  {title}")
    print("=" * 50 + "\n")

def find_npm() -> bool:
    """Try to find npm in common locations."""
    import glob
    
    # Common npm paths on Windows
    common_paths = [
        r"C:\Program Files\nodejs\npm",
        r"C:\Program Files (x86)\nodejs\npm",
        r"C:\Users\{}\AppData\Roaming\npm".format(os.getenv('USERNAME', '')),
    ]
    
    # Try PATH first
    try:
        result = subprocess.run("npm --version", shell=True, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return True
    except:
        pass
    
    # Try common installation paths
    for path in common_paths:
        npm_exe = path if path.endswith('.exe') else path + '.cmd'
        if Path(npm_exe).exists():
            return True
    
    # Try finding nodejs directory
    try:
        result = subprocess.run("where node", shell=True, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return True
    except:
        pass
    
    return False

def check_dependencies() -> bool:
    """Check if required tools are installed."""
    print_header("Checking Dependencies")
    
    deps = {
        "Git": ("git --version", "https://git-scm.com/download/win"),
        "Python": ("python --version", "https://python.org/downloads"),
    }
    
    all_ok = True
    
    # Check Node.js/npm separately with better error handling
    npm_ok = find_npm()
    if npm_ok:
        try:
            result = subprocess.run("npm --version", shell=True, capture_output=True, text=True, timeout=5)
            version = result.stdout.strip().split('\n')[0]
            print(f"✓ Node.js & npm: npm {version}")
        except:
            print(f"✗ Node.js & npm: Found but error checking version")
            all_ok = False
    else:
        print(f"✗ Node.js & npm: Not found")
        print(f"   Install from: https://nodejs.org/")
        print(f"   Or try: choco install nodejs")
        all_ok = False
    
    # Check other dependencies
    for name, (cmd, install_url) in deps.items():
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                version = result.stdout.strip().split('\n')[0]
                print(f"✓ {name}: {version}")
            else:
                print(f"✗ {name}: Not found - {install_url}")
                all_ok = False
        except Exception as e:
            print(f"✗ {name}: Error checking - Install from {install_url}")
            all_ok = False
    
    return all_ok

def setup_frontend() -> bool:
    """Set up the frontend for Netlify deployment."""
    print_header("Setting Up Frontend")
    
    frontend_path = Path("PyPondoMobile/pypondo-web")
    
    if not frontend_path.exists():
        print(f"✗ Frontend path not found: {frontend_path}")
        return False
    
    os.chdir(frontend_path)
    
    # Check if node_modules exists
    if not Path("node_modules").exists():
        print("Installing npm dependencies...")
        result = subprocess.run("npm install", shell=True)
        if result.returncode != 0:
            print("✗ Failed to install dependencies")
            return False
        print("✓ Dependencies installed")
    else:
        print("✓ Dependencies already installed")
    
    # Create .env.local if it doesn't exist
    env_local = Path(".env.local")
    if not env_local.exists():
        print("Creating .env.local...")
        env_local.write_text("VITE_API_URL=http://localhost:5000\nVITE_API_TIMEOUT=30000\n")
        print("✓ Created .env.local")
    
    # Build the project
    print("Building frontend...")
    result = subprocess.run("npm run build", shell=True)
    if result.returncode != 0:
        print("✗ Build failed")
        return False
    
    print("✓ Frontend built successfully")
    return True

def setup_backend() -> bool:
    """Set up the backend for remote access."""
    print_header("Setting Up Backend")
    
    backend_path = Path("PythonProject")
    
    if not backend_path.exists():
        print(f"✗ Backend path not found: {backend_path}")
        return False
    
    # Check if requirements.txt exists
    req_file = backend_path / "requirements.txt"
    if not req_file.exists():
        print("✗ requirements.txt not found")
        return False
    
    print("Installing Python dependencies...")
    result = subprocess.run(
        f"pip install -r {req_file}",
        shell=True
    )
    
    if result.returncode != 0:
        print("⚠ Some dependencies may have failed to install (non-critical)")
    else:
        print("✓ Python dependencies installed")
    
    return True

def test_api() -> bool:
    """Test if the backend API is accessible."""
    print_header("Testing Backend API")
    
    import socket
    from urllib.request import urlopen
    from urllib.error import URLError
    
    # Check if port 5000 is in use
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', 5000))
    
    if result != 0:
        print("⚠ Backend not running on localhost:5000")
        print("  Start it with: python app.py")
        return False
    
    # Try to access the API
    try:
        response = urlopen('http://localhost:5000/api/health', timeout=5)
        print(f"✓ API is accessible: HTTP {response.status}")
        return True
    except URLError as e:
        print(f"✗ Could not reach API: {e}")
        return False

def show_deployment_steps():
    """Show the deployment steps."""
    print_header("Next Steps for Netlify Deployment")
    
    print("""
1. SET UP BACKEND TUNNELING
   Option A: Using ngrok (fastest)
   - Download from https://ngrok.com/download
   - Run: ngrok http 5000
   - Copy the public URL
   
   Option B: Using Railway.app (free hosting)
   - Sign up at https://railway.app
   - Connect your GitHub repo
   - Deploy

2. UPDATE CONFIGURATION
   - Edit netlify.toml
   - Replace 'https://your-backend.herokuapp.com' with your URL
   - Example: https://abc123.ngrok.io

3. DEPLOY TO NETLIFY
   Option A: Using Netlify CLI
   - Run: netlify deploy --prod
   
   Option B: Using GitHub (recommended)
   - Push to GitHub: git push origin main
   - Go to https://app.netlify.com
   - Select "New site from Git"
   - Choose your repository
   - Netlify auto-detects build settings

4. CONFIGURE ENVIRONMENT VARIABLES
   - In Netlify UI: Site Settings → Environment Variables
   - Add: VITE_API_URL = your-backend-url
   - Re-deploy

5. UPDATE ALLOWED ORIGINS
   - In app.py, set ALLOWED_ORIGINS environment variable
   - Include your Netlify domain
   - Example: https://my-site.netlify.app,https://abc123.ngrok.io

6. TEST
   - Visit your Netlify domain
   - Check browser console for errors
   - Test API calls
    """)

def main():
    """Main entry point."""
    print("\n" + "=" * 50)
    print("  PyPondo Netlify Deployment Helper")
    print("=" * 50)
    
    args = sys.argv[1:] if len(sys.argv) > 1 else []
    
    if "--help" in args or "-h" in args:
        print("""
Usage: python setup_netlify.py [options]

Options:
  --check           Check dependencies only
  --setup-frontend  Set up frontend only
  --setup-backend   Set up backend only
  --test-api        Test API connectivity
  --all             Run all setup steps (default)
  --help            Show this help message
        """)
        return
    
    # Check dependencies first
    if not check_dependencies():
        print("\n✗ Please install missing dependencies and try again.")
        return
    
    if "--check" in args:
        return
    
    # Run setup steps
    if "--setup-frontend" in args or "--all" in args or not args:
        if not setup_frontend():
            print("\n✗ Frontend setup failed")
            return
    
    if "--setup-backend" in args or "--all" in args:
        if not setup_backend():
            print("\n⚠ Backend setup had issues (may still work)")
    
    if "--test-api" in args or "--all" in args:
        test_api()
    
    # Show next steps
    if "--all" in args or not args:
        show_deployment_steps()
    
    print("\n✓ Setup complete!")

if __name__ == "__main__":
    main()
