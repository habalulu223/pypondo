# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Building the Android APK

This project includes helper scripts to build the Android package from the Capacitor app.

Requirements:
- Node.js + npm
- JDK 11 or newer (Java 8 will not work)
- Android SDK (Gradle will download it if needed)

Run one of these from the `PyPondoMobile/pypondo-web` folder:

- `build_android.bat`
- `build_android.ps1`

The scripts will:
- install npm dependencies if needed
- build the React web app
- assemble the Android debug APK with Gradle
- copy the resulting APK into `PythonProject/bin/pypondo_mobile-1.0.0-debug.apk`

You can also run the package script from the same folder:

```powershell
npm run android:build
```

## Installing on Android

1. Enable "Install unknown apps" in Android settings:
   - Go to Settings > Apps > Special app access > Install unknown apps
   - Select your browser or file manager and allow installation

2. Transfer the APK file to your Android device (e.g., via USB, email, or download)

3. Open the APK file on your device and install it

4. Launch the PyPondo app

5. Enter your server URL (e.g., http://192.168.1.100:5000) and tap Connect

The app is configured to connect to local network servers over HTTP for development.

## APK Features

The built APK includes:
- CyberCore-themed icon
- Network security config allowing cleartext traffic on local networks (192.168.x.x, 10.x.x.x, 172.16.x.x)
- INTERNET permission for server communication
- Proper Android manifest for Capacitor web app wrapper

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```
