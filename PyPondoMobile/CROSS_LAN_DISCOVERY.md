# PyPondo Mobile App - Cross-LAN Server Discovery

## Overview

The mobile app now supports automatic discovery of PyPondo servers across different LANs and routers. Users no longer need to manually enter server IP addresses if the server is running on a different subnet or router.

## Features

### Multiple Discovery Methods

The app uses several strategies to find servers:

1. **Gateway IP Discovery**
   - Probes common gateway IPs (192.168.1.1, 192.168.0.1, 10.0.0.1, etc.)
   - Tries ports 5000, 8000, 8080, 3000
   - Works across different network ranges

2. **WebRTC-based Local IP Detection**
   - Detects device's local IP using WebRTC
   - Generates subnet addresses around the device
   - Scans nearby IPs for running servers

3. **Subnet Scanning**
   - Probes up to 30 nearby IP addresses in the device's subnet
   - Uses concurrent requests (10 at a time) for speed
   - Shows scan progress to user

4. **Multiple Port Support**
   - Tests common PyPondo ports: 5000, 8000, 8080, 3000
   - Flexible port configuration ready for future versions

### Smart Server Selection

- **Single server found**: Auto-connects automatically
- **Multiple servers found**: Shows list with:
  - Server hostname
  - IP address and port
  - Discovery source (gateway, subnet scan, etc.)
  - Response time in milliseconds
- **No servers found**: Suggests manual entry

### Server Information

Uses the existing `/api/server-info` endpoint to retrieve:
- Server hostname
- Server IP address
- Server port
- App version

## Usage

### For End Users

1. **Automatic Discovery (Recommended)**
   - Launch the app
   - Click "Discover servers" button in Connection panel
   - Wait for scan to complete (10-30 seconds)
   - Select server from list if multiple found
   - App auto-connects to single server

2. **Manual Entry (Fallback)**
   - Enter server address manually in the form
   - Click "Connect"
   - Works as before

3. **Reset Between Servers**
   - Click "Reset saved data" to clear connection
   - Discover again or enter new address

## Implementation Details

### New Files

- `src/discovery.ts` - Server discovery module with all detection methods

### Modified Files

- `src/App.tsx` - Added discovery state and handlers, UI components
- `src/App.css` - Added styles for discovery UI

### Discovery Algorithm Flow

```
User clicks "Discover servers"
    ↓
Start discovery process
    ├─ Gateway IP Discovery (parallel)
    │  └─ Probe common gateways for PyPondo
    │
    ├─ WebRTC IP Detection (parallel)
    │  ├─ Detect local device IP
    │  └─ Generate subnet IP list
    │
    └─ Subnet Scan (parallel)
       └─ Probe nearby IPs with progress
    ↓
Deduplicate results
    ↓
Sort by response time
    ↓
Display results to user
    ↓
User selects server → Connect
```

### Network Requests

Each discovery uses HTTP GET requests to:
- `http://{ip}:{port}/api/server-info` - Verify server and get info

Timeouts:
- Gateway probe: 2 seconds
- Subnet scan: 1.5 seconds each
- Overall scan limit: 30 seconds

## Cross-LAN/Router Support

### How It Works Across Different Networks

1. **Same Physical Location, Different Router**
   - App on Phone A, Server on PC (connected to different router)
   - Both connected to same WiFi or neighboring WiFi networks
   - Gateway discovery finds server via gateway IP
   - Subnet scanning verifies connectivity

2. **Different Locations, Same Network**
   - Works across subnets and VLANs if accessible
   - Requires servers to be on same logical network or connected gateways

3. **Port Forwarding Setup**
   - Can manually enter IP:port if automatic discovery doesn't work
   - Useful for complex network topologies

### Requirements for Cross-LAN Discovery

- Both device and server must be on networks that can reach each other
- Server must be running on an accessible IP address
- Firewall must allow HTTP traffic on server port
- Server must respond to `/api/server-info` endpoint

## Error Handling

### "No servers found"
- Server might not be running
- Check network connectivity
- Verify server is on the same or accessible networks
- Try manual IP entry

### "Response timeout"
- Network latency too high
- Firewall blocking requests
- Server port not responding
- Try different port or manual entry

### "Connection failed"
- Server found but refused connection
- Verify correct server address
- Check server is running
- Verify username/password

## Performance

- **Discovery Time**: 10-30 seconds depending on network
- **Concurrent Requests**: 10 simultaneous probes
- **Memory Usage**: Minimal, cleared after discovery
- **Battery Impact**: Moderate during scan, minimal after

## Security Considerations

- No authentication required for discovery
- Only probes standard ports for PyPondo
- No sensitive data transmitted during discovery
- Same security as manual entry method
- Uses HTTP (same as existing app)

## Future Enhancements

1. **mDNS/Bonjour Service Discovery**
   - Automatic service announcement
   - Faster discovery on local networks

2. **Broadcast-based Discovery**
   - Direct UDP broadcast to find servers
   - Fastest discovery method

3. **Cloud Registration** (Optional)
   - Fallback discovery via cloud service
   - Find servers outside local network
   - Requires server registration

4. **QR Code Scanning**
   - Scan QR code on server to auto-configure
   - One-tap server setup

## Testing

### Test Scenario 1: Same Network
1. Server and phone on same WiFi
2. Click "Discover servers"
3. Should find server via gateway

### Test Scenario 2: Different Subnets
1. Server on 192.168.1.x, Phone on 192.168.2.x
2. Routers connected (can reach each other)
3. Discovery may find via gateway probe

### Test Scenario 3: Auto-Connect
1. Only one server running
2. Click "Discover servers"
3. Should auto-connect without user interaction

### Test Scenario 4: Multiple Servers
1. Start multiple PyPondo servers on different ports
2. Click "Discover servers"
3. Should list all servers with response times
4. Select one to connect

## Troubleshooting

### Discovery Takes Too Long
- Check network connectivity
- Verify firewall settings
- Try manual entry instead

### Finds Wrong Server
- Multiple PyPondo instances running
- Check server IP displayed matches expected
- Verify response time (first one = fastest)

### Keeps Finding Server Even After Connecting Elsewhere
- Data is cached during session
- Click "Reset saved data" to clear
- App restarts with fresh discovery

## Backend Requirements

The PyPondo server must have the `/api/server-info` endpoint available. This endpoint is automatically provided in the main `app.py`.

### Endpoint Details
```
GET /api/server-info
Content-Type: application/json

Response:
{
  "ok": true,
  "server_ip": "192.168.1.100",
  "server_port": 5000,
  "server_hostname": "OFFICE-PC",
  "app_version": "1.0.0"
}
```

## Configuration

Currently no configuration needed. The app uses sensible defaults:
- Default port: 5000
- Common ports tested: 5000, 8000, 8080, 3000
- Subnet scan count: 30 addresses
- Timeout: 2 seconds per gateway, 1.5 seconds per subnet IP

These can be enhanced in future versions through environment variables or settings.

## Related Files

- `src/discovery.ts` - Server discovery implementation
- `src/App.tsx` - UI integration
- `src/App.css` - Styling
- `PythonProject/app.py` - Backend server info endpoint

## Support

For issues with cross-LAN discovery:
1. Verify both devices have network connectivity
2. Check firewall settings on server
3. Verify server is running on expected port
4. Try manual IP entry as fallback
5. Check server logs for connection attempts

---

**Version**: 1.0.0  
**Date**: April 2026  
**Status**: Production Ready
