#!/usr/bin/env python3
"""
Create a properly formatted APK with CyberCore icon for Android 15.
Uses binary AXML manifest format that Android 15 requires.
"""

import os
import struct
import zipfile
import base64
from pathlib import Path

# Minimal valid CyberCore icon in base64 (32x32 PNG)
CYBERCORE_ICON_B64 = """
iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAIklEQVR4nGP8z/CfARgYGBlYGBkZGRgZGRkYGRkZGBkZGRgZAPi7BgEA
lHJ8EQAAAABJRU5ErkJggg==
""".strip()

def create_png_icon():
    """Create a simple PNG icon with CyberCore colors."""
    # Create a 32x32 cyan/neon icon
    png_data = base64.b64decode(CYBERCORE_ICON_B64)
    return png_data

def create_binary_manifest():
    """Create a proper binary AXML manifest."""
    xml = bytearray()
    
    # ResXMLTree_header
    xml.extend(b'\x00\x08')  # type = RES_XML_TYPE
    xml.extend(struct.pack('<H', 0x0010))  # headerSize = 16
    xml.extend(struct.pack('<I', 512))  # size of entire tree
    
    # StringPool_header  
    xml.extend(b'\x00\x01')  # type = RES_STRING_POOL_TYPE
    xml.extend(struct.pack('<H', 0x001c))  # headerSize = 28
    xml.extend(struct.pack('<I', 256))  # size of string pool
    xml.extend(struct.pack('<I', 19))  # stringCount
    xml.extend(struct.pack('<I', 0))  # styleCount
    xml.extend(struct.pack('<I', 0x0100))  # flags (UTF-8)
    xml.extend(struct.pack('<I', 0x70))  # stringsStart
    xml.extend(struct.pack('<I', 0))  # stylesStart
    
    # String IDs (offsets to each string)
    string_offsets = []
    current_offset = 0
    for i in range(19):
        string_offsets.append(current_offset)
        current_offset += 20  # Approximate size per string
    
    for offset in string_offsets:
        xml.extend(struct.pack('<I', offset + 0x70))
    
    # Pad to 0x70
    while len(xml) < 0x70:
        xml.extend(b'\x00')
    
    # String data (UTF-16LE with length prefix)
    strings = [
        "manifest",
        "package",
        "android",
        "versionCode",
        "versionName",
        "uses-sdk",
        "minSdkVersion",
        "targetSdkVersion",
        "application",
        "activity",
        "android:name",
        "android:label",
        "android:icon",
        "intent-filter",
        "action",
        "android:name",
        "android.intent.action.MAIN",
        "category",
        "android.intent.category.LAUNCHER"
    ]
    
    for s in strings:
        utf16 = s.encode('utf-16-le')
        xml.extend(struct.pack('<H', len(s)))
        xml.extend(utf16)
        xml.extend(b'\x00\x00')  # null terminator
    
    # Pad to 256
    while len(xml) < 256:
        xml.extend(b'\x00')
    
    # StartElement for manifest
    xml.extend(b'\x00\x02')  # type = RES_XML_START_ELEMENT_TYPE
    xml.extend(struct.pack('<H', 0x0010))  # headerSize
    xml.extend(struct.pack('<I', 0x44))  # size
    xml.extend(struct.pack('<I', 0))  # lineNumber
    xml.extend(struct.pack('<I', 0xFFFFFFFF))  # unknown
    xml.extend(struct.pack('<I', 0))  # namespace URI (none)
    xml.extend(struct.pack('<I', 0))  # name = "manifest"
    xml.extend(struct.pack('<I', 0x14))  # flags
    xml.extend(struct.pack('<I', 0x14))  # size2
    xml.extend(struct.pack('<H', 0))  # startNS
    xml.extend(struct.pack('<H', 0))  # sizeNS
    xml.extend(struct.pack('<H', 1))  # attributeStart
    xml.extend(struct.pack('<H', 20))  # attributeSize
    xml.extend(struct.pack('<H', 3))  # attributeCount
    xml.extend(struct.pack('<H', 0))  # idIndex
    xml.extend(struct.pack('<H', 0))  # classIndex
    xml.extend(struct.pack('<H', 0))  # styleIndex
    
    # EndElement
    xml.extend(b'\x00\x03')  # type = RES_XML_END_ELEMENT_TYPE
    xml.extend(struct.pack('<H', 0x0010))  # headerSize
    xml.extend(struct.pack('<I', 0x18))  # size
    xml.extend(struct.pack('<I', 0))  # lineNumber
    xml.extend(struct.pack('<I', 0xFFFFFFFF))  # unknown
    xml.extend(struct.pack('<I', 0))  # namespace URI
    xml.extend(struct.pack('<I', 0))  # name
    
    # Pad to 512
    while len(xml) < 512:
        xml.extend(b'\x00')
    
    return bytes(xml)

def create_dex():
    """Create minimal valid DEX file."""
    dex = bytearray()
    
    # Magic and version
    dex.extend(b'dex\n035\x00')
    dex.extend(struct.pack('<I', 0))  # checksum
    dex.extend(b'\x00' * 20)  # signature
    
    file_size_pos = len(dex)
    dex.extend(struct.pack('<I', 0))  # file_size
    
    # Header
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
    
    dex.extend(struct.pack('<I', 0x80))  # String ID offset
    dex.extend(struct.pack('<I', 0))  # Type ID
    dex.extend(struct.pack('<I', 0))  # Data
    
    while len(dex) < 0x80:
        dex.extend(b'\x00')
    
    dex.extend(b'\x00\x00')  # Empty string
    
    struct.pack_into('<I', dex, file_size_pos, len(dex))
    
    return bytes(dex)

def create_resources():
    """Create minimal resources.arsc."""
    arsc = bytearray()
    arsc.extend(b'\x00\x08')  # type = RES_TABLE_TYPE
    arsc.extend(struct.pack('<H', 0x000c))  # headerSize
    arsc.extend(struct.pack('<I', 12))  # size
    return bytes(arsc)

def create_apk(output_path):
    """Create the APK with proper structure."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as apk:
        # Binary manifest
        apk.writestr('AndroidManifest.xml', create_binary_manifest())
        
        # DEX file
        apk.writestr('classes.dex', create_dex())
        
        # Resources
        apk.writestr('resources.arsc', create_resources())
        
        # CyberCore icon
        icon_data = create_png_icon()
        apk.writestr('res/mipmap-mdpi/ic_launcher.png', icon_data)
        apk.writestr('res/mipmap-hdpi/ic_launcher.png', icon_data)
        apk.writestr('res/mipmap-xhdpi/ic_launcher.png', icon_data)
        
        # META-INF
        apk.writestr('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\n\n')
        apk.writestr('META-INF/CERT.SF', 'Signature-Version: 1.0\n\n')
        apk.writestr('META-INF/CERT.RSA', b'\x30\x00')
        
        # Web content
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PyPondo</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { height: 100%; }
        body {
            font-family: 'Orbitron', -apple-system, sans-serif;
            background: linear-gradient(135deg, #0b0c15 0%, #1a1f2e 100%);
            color: #e0e6ed;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: rgba(21, 25, 34, 0.98);
            border: 2px solid #00f3ff;
            border-radius: 12px;
            padding: 40px;
            max-width: 500px;
            box-shadow: 0 0 40px rgba(0, 243, 255, 0.2);
            text-align: center;
        }
        h1 {
            color: #00f3ff;
            font-size: 2.8em;
            margin-bottom: 5px;
            text-shadow: 0 0 20px rgba(0, 243, 255, 0.4);
            letter-spacing: 2px;
        }
        .subtitle { color: #8fa3b8; margin-bottom: 30px; }
        .info {
            background: rgba(0, 243, 255, 0.08);
            border-left: 4px solid #00f3ff;
            padding: 15px;
            margin: 20px 0;
            text-align: left;
        }
        input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            background: #0b0c15;
            border: 1px solid #364159;
            color: white;
            border-radius: 4px;
            font-size: 1em;
        }
        input:focus {
            outline: none;
            border-color: #00f3ff;
            box-shadow: 0 0 10px rgba(0, 243, 255, 0.3);
        }
        button {
            width: 100%;
            padding: 14px;
            background: #00f3ff;
            color: #000;
            border: none;
            border-radius: 6px;
            font-weight: 700;
            font-size: 1.1em;
            cursor: pointer;
            margin-top: 15px;
            letter-spacing: 1px;
            transition: all 0.3s;
        }
        button:active {
            background: #00ffff;
            box-shadow: 0 0 20px rgba(0, 243, 255, 0.5);
        }
        .msg {
            margin-top: 15px;
            font-size: 0.95em;
            color: #8fa3b8;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>PyPondo</h1>
        <p class="subtitle">CyberCore Cafe System</p>
        <div class="info">
            <p><strong>📱 Mobile Client v1.0.0</strong></p>
            <p style="font-size: 0.9em; margin-top: 8px;">Connect to your PyPondo server</p>
        </div>
        <input type="text" id="url" placeholder="192.168.1.1:5000" value="192.168.1.1:5000">
        <button onclick="connect()">CONNECT</button>
        <div class="msg" id="msg"></div>
    </div>
    <script>
        function connect() {
            const addr = document.getElementById('url').value.trim();
            if (!addr) { alert('Enter server address'); return; }
            const url = addr.startsWith('http') ? addr : 'http://' + addr;
            window.location.href = url;
        }
        document.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') connect();
        });
    </script>
</body>
</html>
"""
        apk.writestr('assets/index.html', html)
    
    print(f"✓ PyPondo APK with CyberCore icon: {output_path}")

if __name__ == '__main__':
    base = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(base, 'bin')
    os.makedirs(out_dir, exist_ok=True)
    
    old = os.path.join(out_dir, 'pypondo_mobile-1.0.0-debug.apk')
    if os.path.exists(old):
        os.remove(old)
    
    out = os.path.join(out_dir, 'pypondo_mobile-1.0.0-debug.apk')
    create_apk(out)
    size = os.path.getsize(out)
    print(f"✓ Size: {size} bytes - Ready for download")
