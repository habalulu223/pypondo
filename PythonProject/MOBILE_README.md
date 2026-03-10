# PyPondo Mobile Client

A mobile Android app for the PyPondo PC Cafe management system.

## Features

- Connect to PyPondo server
- User login and authentication
- View account balance
- Mobile-optimized interface for PC Cafe customers

## Building the Android APK

### Prerequisites

1. Python 3.8+
2. Java JDK 8+
3. Android SDK/NDK (automatically downloaded by buildozer)
4. Buildozer: `pip install buildozer`

### Build Steps

1. Install dependencies:
   ```bash
   pip install kivy buildozer
   ```

2. Run the build script:
   ```bash
   build_android.bat  # Windows
   # or
   buildozer android debug  # Manual
   ```

3. The APK will be created in `bin/pypondo_mobile-1.0.0-debug.apk`

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