import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.pypondo.mobile',
  appName: 'PyPondo',
  webDir: 'dist',
  android: {
    // The server is reached over plain http on the LAN, the WebView origin may not be.
    allowMixedContent: true,
  },
};

export default config;
