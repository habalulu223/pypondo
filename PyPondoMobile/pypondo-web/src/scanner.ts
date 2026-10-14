import { Capacitor } from '@capacitor/core'
import {
  CapacitorBarcodeScanner,
  CapacitorBarcodeScannerCameraDirection,
  CapacitorBarcodeScannerTypeHint,
} from '@capacitor/barcode-scanner'

/**
 * QR capture for the pairing flow and the equipment lookup.
 *
 * The Android WebView has no `BarcodeDetector`, so on a device the scan is delegated to
 * the native Capacitor plugin, which opens its own camera screen and returns the decoded
 * text. The browser keeps the in-app video scanner.
 */
export function isNativeScannerAvailable(): boolean {
  return Capacitor.isNativePlatform()
}

/** Resolves with the decoded text, or an empty string when the user backed out. */
export async function scanQr(instructions?: string): Promise<string> {
  try {
    const result = await CapacitorBarcodeScanner.scanBarcode({
      hint: CapacitorBarcodeScannerTypeHint.QR_CODE,
      cameraDirection: CapacitorBarcodeScannerCameraDirection.BACK,
      scanInstructions: instructions,
    })
    return (result?.ScanResult || '').trim()
  } catch (error) {
    // Cancelling the camera is a normal outcome, not a failure worth surfacing.
    if (isUserCancelled(error)) {
      return ''
    }
    throw error
  }
}

function isUserCancelled(error: unknown): boolean {
  const details = (error || {}) as { code?: string; message?: string }
  const code = (details.code || '').toUpperCase()
  if (code.includes('CANCEL')) {
    return true
  }
  const message = (details.message || '').toLowerCase()
  return message.includes('cancel') || message === 'no scan'
}
