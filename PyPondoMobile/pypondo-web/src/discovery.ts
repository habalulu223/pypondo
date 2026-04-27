/**
 * Server Discovery Module
 * Implements multiple strategies to find PyPondo servers across different LANs and routers
 */

export type DiscoveredServer = {
  address: string
  hostname: string
  port: number
  ip: string
  source: 'broadcast' | 'gateway' | 'subnet' | 'mdns' | 'manual'
  reachable: boolean
  responseTime: number
}

const DISCOVERY_TIMEOUT_MS = 3000
const DEFAULT_PORT = 5000
const COMMON_PORTS = [5000, 8000, 8080, 3000]

/**
 * Get all possible gateway IPs from the device
 * Uses common gateway addresses as fallbacks
 */
export async function discoverGatewayIps(): Promise<string[]> {
  const gateways: Set<string> = new Set()

  // Common gateway IP ranges
  const commonGateways = [
    '192.168.1.1',
    '192.168.0.1',
    '10.0.0.1',
    '172.16.0.1',
    '192.168.100.1',
    '192.168.2.1',
    '192.168.88.1',
  ]

  commonGateways.forEach((gw) => gateways.add(gw))

  // Try to detect local IP via WebRTC (if available)
  try {
    const localIps = await detectLocalIpsViaWebRTC()
    localIps.forEach((ip) => {
      // Extract gateway from local IP (e.g., 192.168.1.x -> 192.168.1.1)
      const parts = ip.split('.')
      if (parts.length === 4) {
        parts[3] = '1'
        gateways.add(parts.join('.'))
        // Also try .254 and .0 for some networks
        parts[3] = '254'
        gateways.add(parts.join('.'))
      }
    })
  } catch {
    // WebRTC detection not available, continue with common gateways
  }

  return Array.from(gateways)
}

/**
 * Detect local IP addresses using WebRTC
 */
export function detectLocalIpsViaWebRTC(): Promise<string[]> {
  return new Promise((resolve) => {
    const ips: Set<string> = new Set()

    const pc = new RTCPeerConnection({ iceServers: [] })
    setTimeout(() => {
      pc.close()
      resolve(Array.from(ips))
    }, 1000)

    pc.createDataChannel('')

    pc.onicecandidate = (ice) => {
      if (!ice || !ice.candidate) {
        return
      }

      const candidate = ice.candidate.candidate
      const ipMatch = candidate.match(/([0-9]{1,3}(\.[0-9]{1,3}){3})/)
      if (ipMatch) {
        const ip = ipMatch[1]
        // Filter out localhost and link-local addresses
        if (!ip.startsWith('127.') && !ip.startsWith('169.254.')) {
          ips.add(ip)
        }
      }
    }

    pc.createOffer()
      .then((offer) => pc.setLocalDescription(offer))
      .catch(() => {
        // Ignore errors
      })
  })
}

/**
 * Generate possible IPs in a subnet (first 254 addresses)
 */
export function generateSubnetIps(baseIp: string, count: number = 20): string[] {
  const ips: string[] = []
  const parts = baseIp.split('.')

  if (parts.length !== 4) {
    return ips
  }

  const base = [parseInt(parts[0]), parseInt(parts[1]), parseInt(parts[2])]
  const maxHost = parseInt(parts[3])

  // Generate IPs around the detected local IP
  for (let i = Math.max(1, maxHost - count / 2); i <= Math.min(254, maxHost + count / 2); i++) {
    if (i !== maxHost) {
      // Skip the local IP itself
      ips.push(`${base[0]}.${base[1]}.${base[2]}.${i}`)
    }
  }

  return ips
}

/**
 * Test if a server is reachable at the given address
 */
export async function probeServer(
  address: string,
  port: number = DEFAULT_PORT,
  timeoutMs: number = DISCOVERY_TIMEOUT_MS,
): Promise<{ reachable: boolean; responseTime: number }> {
  const startTime = Date.now()
  const url = `http://${address}:${port}/api/server-info`

  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

    const response = await fetch(url, {
      signal: controller.signal,
      method: 'GET',
      mode: 'no-cors',
    })

    clearTimeout(timeoutId)
    const responseTime = Date.now() - startTime

    return {
      reachable: response.ok || response.status === 0, // 0 for CORS mode
      responseTime,
    }
  } catch {
    const responseTime = Date.now() - startTime
    return {
      reachable: false,
      responseTime,
    }
  }
}

/**
 * Get server info from a reachable server
 */
export async function getServerInfo(address: string, port: number = DEFAULT_PORT) {
  const url = `http://${address}:${port}/api/server-info`

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
    })

    if (!response.ok) {
      return null
    }

    const data = (await response.json()) as any
    return {
      hostname: data.server_hostname || address,
      ip: data.server_ip || address,
      port: data.server_port || port,
    }
  } catch {
    return null
  }
}

/**
 * Discover servers by probing gateway IPs
 */
export async function discoverViaGateway(): Promise<DiscoveredServer[]> {
  const servers: DiscoveredServer[] = []
  const gateways = await discoverGatewayIps()

  const probes = gateways.map(async (gateway) => {
    for (const port of COMMON_PORTS) {
      const probe = await probeServer(gateway, port, 2000)

      if (probe.reachable) {
        const serverInfo = await getServerInfo(gateway, port)
        servers.push({
          address: gateway,
          hostname: serverInfo?.hostname || gateway,
          port,
          ip: serverInfo?.ip || gateway,
          source: 'gateway',
          reachable: true,
          responseTime: probe.responseTime,
        })
        break // Found on this gateway, move to next
      }
    }
  })

  await Promise.all(probes)
  return servers
}

/**
 * Discover servers by scanning local subnet
 */
export async function discoverViaSubnetScan(
  scanCount: number = 30,
  onProgress?: (found: number, tested: number) => void,
): Promise<DiscoveredServer[]> {
  const servers: DiscoveredServer[] = []
  const localIps = await detectLocalIpsViaWebRTC()

  if (localIps.length === 0) {
    return servers
  }

  const baseIp = localIps[0]
  const subnetIps = generateSubnetIps(baseIp, scanCount)

  let tested = 0

  // Probe multiple IPs in parallel with concurrency limit
  const concurrency = 10
  for (let i = 0; i < subnetIps.length; i += concurrency) {
    const batch = subnetIps.slice(i, i + concurrency)

    const batchProbes = batch.map(async (ip) => {
      const port = DEFAULT_PORT

      const probe = await probeServer(ip, port, 1500)
      tested++

      if (onProgress) {
        onProgress(servers.length, tested)
      }

      if (probe.reachable) {
        const serverInfo = await getServerInfo(ip, port)
        servers.push({
          address: ip,
          hostname: serverInfo?.hostname || ip,
          port,
          ip: serverInfo?.ip || ip,
          source: 'subnet',
          reachable: true,
          responseTime: probe.responseTime,
        })
      }
    })

    await Promise.all(batchProbes)
  }

  return servers
}

/**
 * Discover servers via mDNS/Bonjour if available
 */
export async function discoverViaMdns(): Promise<DiscoveredServer[]> {
  // This would require a native plugin or mDNS.js library
  // For now, return empty - can be enhanced later
  return []
}

/**
 * Discover servers using broadcast
 */
export async function discoverViaBroadcast(): Promise<DiscoveredServer[]> {
  // This would require WebSockets or similar for UDP broadcast
  // For now, return empty - backend would need to support this
  return []
}

/**
 * Main discovery function - tries all methods
 */
export async function discoverServers(
  options: {
    includeGateway?: boolean
    includeSubnet?: boolean
    includeMdns?: boolean
    includeBroadcast?: boolean
    subnetScanCount?: number
    onProgress?: (found: number, tested: number) => void
  } = {},
): Promise<DiscoveredServer[]> {
  const {
    includeGateway = true,
    includeSubnet = true,
    includeMdns = false,
    includeBroadcast = false,
    subnetScanCount = 30,
    onProgress,
  } = options

  const allServers: Map<string, DiscoveredServer> = new Map()

  // Run discovery methods in parallel
  const discoveries: Promise<DiscoveredServer[]>[] = []

  if (includeGateway) {
    discoveries.push(discoverViaGateway())
  }

  if (includeSubnet) {
    discoveries.push(discoverViaSubnetScan(subnetScanCount, onProgress))
  }

  if (includeMdns) {
    discoveries.push(discoverViaMdns())
  }

  if (includeBroadcast) {
    discoveries.push(discoverViaBroadcast())
  }

  const results = await Promise.all(discoveries)

  // Deduplicate by address:port combination
  results.forEach((serverList) => {
    serverList.forEach((server) => {
      const key = `${server.ip}:${server.port}`
      if (!allServers.has(key)) {
        allServers.set(key, server)
      }
    })
  })

  return Array.from(allServers.values()).sort((a, b) => a.responseTime - b.responseTime)
}

/**
 * Format server address for display
 */
export function formatServerAddress(server: DiscoveredServer): string {
  return `${server.hostname || server.address}:${server.port}`
}

/**
 * Get user-friendly source description
 */
export function getSourceDescription(source: DiscoveredServer['source']): string {
  const descriptions: Record<DiscoveredServer['source'], string> = {
    broadcast: 'Found via broadcast',
    gateway: 'Found via gateway',
    subnet: 'Found via subnet scan',
    mdns: 'Found via mDNS',
    manual: 'Manually entered',
  }
  return descriptions[source] || 'Found'
}
