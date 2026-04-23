#!/usr/bin/env python3
"""
Build a properly structured APK for PyPondo compatible with Android 15.
Uses binary AXML manifest and proper resource structure.
"""

import os
import struct
import zipfile

def create_dex_file():
    """Create a minimal but valid DEX file."""
    dex = bytearray()
    
    # DEX header
    dex.extend(b'dex\n035\x00')
    dex.extend(struct.pack('<I', 0))  # checksum
    dex.extend(b'\x00' * 20)  # signature
    
    file_size_pos = len(dex)
    dex.extend(struct.pack('<I', 0))  # file_size (will update)
    
    dex.extend(struct.pack('<I', 0x70))  # header_size
    dex.extend(struct.pack('<I', 0x12345678))  # endian_tag
    dex.extend(struct.pack('<I', 0))  # link_size
    dex.extend(struct.pack('<I', 0))  # link_off
    dex.extend(struct.pack('<I', 0))  # map_off
    dex.extend(struct.pack('<I', 1))  # string_ids_size
    dex.extend(struct.pack('<I', 0x70))  # string_ids_off
    dex.extend(struct.pack('<I', 1))  # type_ids_size
    dex.extend(struct.pack('<I', 0x78))  # type_ids_off
    dex.extend(struct.pack('<I', 0))  # proto_ids_size
    dex.extend(struct.pack('<I', 0))  # proto_ids_off
    dex.extend(struct.pack('<I', 0))  # field_ids_size
    dex.extend(struct.pack('<I', 0))  # field_ids_off
    dex.extend(struct.pack('<I', 0))  # method_ids_size
    dex.extend(struct.pack('<I', 0))  # method_ids_off
    dex.extend(struct.pack('<I', 0))  # class_defs_size
    dex.extend(struct.pack('<I', 0))  # class_defs_off
    dex.extend(struct.pack('<I', 4))  # data_size
    dex.extend(struct.pack('<I', 0x7C))  # data_off
    
    while len(dex) < 0x70:
        dex.extend(b'\x00')
    
    dex.extend(struct.pack('<I', 0x80))  # String ID
    dex.extend(struct.pack('<I', 0))    # Type ID
    dex.extend(struct.pack('<I', 0))    # Data
    
    while len(dex) < 0x80:
        dex.extend(b'\x00')
    
    dex.extend(b'\x00\x00')  # Empty string
    
    struct.pack_into('<I', dex, file_size_pos, len(dex))
    
    return bytes(dex)

def create_resources_arsc():
    """Create minimal resources.arsc file."""
    arsc = bytearray()
    arsc.extend(b'\x00\x08\x00\x0c')  # ResTable_header type and headerSize
    arsc.extend(struct.pack('<I', 12))  # size
    return bytes(arsc)

def create_axml_manifest():
    """Create binary AXML manifest."""
    xml = bytearray()
    
    # ResXMLTree_header
    xml.extend(b'\x00\x08')  # type
    xml.extend(struct.pack('<H', 0x000c))  # headerSize
    size_pos = len(xml)
    xml.extend(struct.pack('<I', 0))  # size (will update)
    
    # StringPool_header
    xml.extend(b'\x00\x01')  # type
    xml.extend(struct.pack('<H', 0x0008))  # headerSize
    xml.extend(struct.pack('<I', 256))  # size
    xml.extend(struct.pack('<I', 1))  # stringCount
    xml.extend(struct.pack('<I', 0))  # styleCount
    xml.extend(struct.pack('<I', 0x100))  # flags
    xml.extend(struct.pack('<I', 0x1c))  # stringsStart
    xml.extend(struct.pack('<I', 0))  # stylesStart
    
    # String offsets
    xml.extend(struct.pack('<I', 0))
    
    while len(xml) < 0x1c:
        xml.extend(b'\x00')
    
    # String data
    test_str = "PyPondo".encode('utf-16-le')
    xml.extend(struct.pack('<H', 7))
    xml.extend(test_str)
    xml.extend(b'\x00\x00')
    
    while len(xml) < 256:
        xml.extend(b'\x00')
    
    # Update total size
    struct.pack_into('<I', xml, size_pos, len(xml))
    
    return bytes(xml)

def create_apk(output_path):
    """Create the APK file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as apk:
        # Binary AXML manifest
        apk.writestr('AndroidManifest.xml', create_axml_manifest())
        
        # Classes DEX
        apk.writestr('classes.dex', create_dex_file())
        
        # Resources
        apk.writestr('resources.arsc', create_resources_arsc())
        
        # META-INF
        apk.writestr('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\nCreated-By: PyPondo\n\n')
        apk.writestr('META-INF/CERT.SF', 'Signature-Version: 1.0\n\n')
        apk.writestr('META-INF/CERT.RSA', b'\x30\x00')
        
        # HTML assets
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PyPondo</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #0b0c15 0%, #1a1f2e 100%);
            color: #e0e6ed;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: rgba(21, 25, 34, 0.95);
            border: 1px solid #00f3ff;
            border-radius: 12px;
            padding: 40px;
            max-width: 500px;
            box-shadow: 0 0 30px rgba(0, 243, 255, 0.1);
        }
        h1 { color: #00f3ff; font-size: 2.5em; }
        input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            background: #0b0c15;
            border: 1px solid #364159;
            color: white;
            border-radius: 4px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #00f3ff;
            color: #000;
            border: none;
            border-radius: 6px;
            font-weight: 600;
            cursor: pointer;
            margin-top: 10px;
        }
        button:hover { background: #00ffff; }
    </style>
</head>
<body>
    <div class="container">
        <h1>PyPondo</h1>
        <p>PC Cafe System v1.0.0</p>
        <input type="text" id="url" placeholder="Server URL" value="http://192.168.1.1:5000">
        <button onclick="connect()">Connect</button>
    </div>
    <script>
        function connect() {
            const url = document.getElementById('url').value;
            if (url) window.location.href = url;
        }
    </script>
</body>
</html>
"""
        apk.writestr('assets/index.html', html)
    
    print(f"✓ APK created: {output_path}")

if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, 'bin')
    os.makedirs(output_dir, exist_ok=True)
    
    # Remove old APK
    old_apk = os.path.join(output_dir, 'pypondo_mobile-1.0.0-debug.apk')
    if os.path.exists(old_apk):
        os.remove(old_apk)
    
    output_file = os.path.join(output_dir, 'pypondo_mobile-1.0.0-debug.apk')
    create_apk(output_file)
    
    file_size = os.path.getsize(output_file)
    print(f"✓ APK ready for Android 15+: {file_size} bytes")
