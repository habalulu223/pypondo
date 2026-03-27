# PyPondo Mobile Client

A mobile Android app for the PyPondo PC Cafe management system.

## Features

- Connect to PyPondo server
- User login and authentication
- View account balance
- Mobile-optimized interface for PC Cafe customers

## Building the Android APK

### Prerequisites

1. Ubuntu via WSL on Windows, or a native Linux environment
2. Python 3.8+
3. Java JDK 17+
4. Android SDK/NDK (automatically downloaded by buildozer)

### Build Steps

1. If WSL is not installed yet, install Ubuntu and reboot:
   ```powershell
   wsl --install -d Ubuntu
   ```

2. After reboot, run this inside Ubuntu from your project folder:
   ```bash
   sudo apt update && sudo apt install -y python3 python3-venv python3-pip openjdk-17-jdk git zip unzip
   python3 -m venv .venv-android
   source .venv-android/bin/activate
   pip install --upgrade pip
   pip install buildozer cython
   buildozer android debug
   ```

3. Or, if you are already in Linux/Ubuntu with the dependencies installed:
   ```bash
   buildozer android debug
   ```

4. The APK will be created in `bin/pypondo_mobile-1.0.0-debug.apk`

### Installing on Android

1. Enable "Install unknown apps" in Android settings
2. Transfer the APK to your Android device
3. Open the APK file to install

## Usage

1. Launch the app
2. Enter server IP and port
3. Test connection
4. Login with your credentials
5. Access your account features

## Development

The app is built with Kivy for cross-platform compatibility.

### Running on Desktop

```bash
python main.py
```

### Project Structure

- `main.py` - Main Kivy application
- `buildozer.spec` - Build configuration
- `build_android.bat` - Windows build script
