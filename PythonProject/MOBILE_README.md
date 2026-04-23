# PyPondo Mobile Client

A mobile Android app for the PyPondo PC Cafe management system.

> NOTE: The current Android app source is in `PyPondoMobile/pypondo-web/android`.
> The legacy Kivy build kit is still present in the repository, but the installable
> Android APK should be generated from the Capacitor project using a proper
> Android toolchain.

## Features

- Connect to PyPondo server
- User login and authentication
- View account balance
- Mobile-optimized interface for PC Cafe customers

## Building the Android APK

### Prerequisites

1. Node.js and npm/yarn
2. Java JDK 17+ (Android Gradle plugin requires Java 11 or newer)
3. Android SDK / Android Studio toolchain
4. The Android app source is in `PyPondoMobile/pypondo-web/android`
5. Use the helper builder scripts in `PyPondoMobile/pypondo-web`:
   - `build_android.bat`
   - `build_android.ps1`
   - Or from the workspace root: `build_mobile_apk.bat`

### Build Steps

1. If WSL is not installed yet, install Ubuntu and reboot:
   ```powershell
   wsl --install -d Ubuntu
   ```

2. From Windows, the safest option is to run:
   ```bat
   build_android_safe.bat
   ```
   If it says WSL is not ready, open PowerShell as Administrator and run:
   ```powershell
   wsl --install -d Ubuntu
   ```
   Then reboot Windows, open Ubuntu once, finish the Linux first-user setup, and run `build_android_safe.bat` again.

3. Or from Windows PowerShell in the project folder, run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\build_android.ps1
   ```

4. If you are already inside Ubuntu/Linux in the project folder, run:
   ```bash
   chmod +x build_android_wsl.sh
   ./build_android_wsl.sh
   ```

5. Do not run `build_android_wsl.sh` directly from PowerShell. That causes the `/usr/bin/env` error because it is a Linux shell script.

6. The APK will be created in `bin/pypondo_mobile-1.0.0-debug.apk`

### From the Admin Dashboard

If an APK has not been built yet, the admin dashboard download button now gives you a `PyPondo-Android-build-kit.zip` bundle instead of failing.

That bundle includes:

- `main.py`
- `buildozer.spec`
- `buildozer_shim.py`
- `build_android.bat`
- `build_android_safe.bat`
- `build_android.ps1`
- `build_android_wsl.sh`
- this README and the app icon assets

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
