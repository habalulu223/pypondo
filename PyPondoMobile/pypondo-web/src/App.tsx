import { startTransition, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'
import { discoverServers, formatServerAddress, getSourceDescription, type DiscoveredServer } from './discovery'

type ServerInfo = {
  ok: boolean
  app_version: string
  server_hostname: string
  server_ip: string
  server_port: number
}

type LoginPayload = {
  ok: boolean
  user_id: number
  username: string
  balance: number
  app_version: string
  error?: string
}

type MobileBooking = {
  id?: number
  pc_name: string
  date: string
  time: string
  status: string
}

type BookingPayload = {
  ok: boolean
  bookings: MobileBooking[]
}

type MobilePc = {
  id: number
  name: string
  is_occupied: boolean
  lan_ip?: string | null
  online?: boolean
}

type PcsPayload = {
  ok: boolean
  pcs: MobilePc[]
}

type MobileUpdate = {
  title: string
  description: string
  version: string
  update_type: string
  timestamp?: string
}

type UpdatesPayload = {
  ok: boolean
  updates: MobileUpdate[]
}

type TopupPayload = {
  ok: boolean
  message: string
  external_id: string
  amount: number
  balance: number
}

type AssistantPayload = {
  ok: boolean
  response: string
}

type ConnectionStatus = 'idle' | 'testing' | 'connected' | 'error'
type TabKey = 'overview' | 'bookings' | 'pcs' | 'topup' | 'assistant' | 'updates'

type StoredConfig = {
  serverAddress: string
}

type StoredSession = {
  balance: number
  userId: number
  username: string
}

type ChatMessage = {
  id: number
  role: 'assistant' | 'system' | 'user'
  text: string
}

const CONFIG_STORAGE_KEY = 'pypondo.mobile.config.v2'
const SESSION_STORAGE_KEY = 'pypondo.mobile.session.v2'
const DEFAULT_SERVER_ADDRESS = '192.168.1.100:5000'
const QUICK_TOPUP_AMOUNTS = [100, 200, 500, 1000]

const currencyFormatter = new Intl.NumberFormat('en-PH', {
  currency: 'PHP',
  style: 'currency',
})

function buildBaseUrl(serverAddress: string) {
  const trimmed = serverAddress.trim()
  if (!trimmed) {
    throw new Error('Enter the PyPondo server address first.')
  }

  const withScheme = /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`
  const url = new URL(withScheme)
  url.pathname = ''
  url.search = ''
  url.hash = ''
  return url.toString().replace(/\/$/, '')
}

async function readJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  const raw = await response.text()
  const data = raw ? JSON.parse(raw) : {}

  if (!response.ok) {
    const message =
      typeof data?.error === 'string'
        ? data.error
        : typeof data?.message === 'string'
          ? data.message
          : `Request failed with status ${response.status}.`
    throw new Error(message)
  }

  return data as T
}

function createFormBody(values: Record<string, string | number>) {
  const body = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => {
    body.set(key, String(value))
  })
  return body.toString()
}

function formatCurrency(amount: number) {
  return currencyFormatter.format(Number.isFinite(amount) ? amount : 0)
}

function formatTimestamp(value?: string) {
  if (!value) {
    return 'Just now'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat('en-PH', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function readStoredConfig(): StoredConfig | null {
  try {
    const raw = window.localStorage.getItem(CONFIG_STORAGE_KEY)
    if (!raw) {
      return null
    }
    return JSON.parse(raw) as StoredConfig
  } catch {
    return null
  }
}

function writeStoredConfig(serverAddress: string) {
  window.localStorage.setItem(
    CONFIG_STORAGE_KEY,
    JSON.stringify({
      serverAddress,
    } satisfies StoredConfig),
  )
}

function readStoredSession(): StoredSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_STORAGE_KEY)
    if (!raw) {
      return null
    }
    return JSON.parse(raw) as StoredSession
  } catch {
    return null
  }
}

function writeStoredSession(session: StoredSession | null) {
  if (!session) {
    window.localStorage.removeItem(SESSION_STORAGE_KEY)
    return
  }

  window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session))
}

function App() {
  const [serverAddress, setServerAddress] = useState(DEFAULT_SERVER_ADDRESS)
  const [baseUrl, setBaseUrl] = useState('')
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('idle')
  const [connectionMessage, setConnectionMessage] = useState(
    'The APK already contains the app UI. Enter the PyPondo server address to link it to your system.',
  )
  const [serverInfo, setServerInfo] = useState<ServerInfo | null>(null)

  // Discovery state
  const [discoveredServers, setDiscoveredServers] = useState<DiscoveredServer[]>([])
  const [discoveringServers, setDiscoveringServers] = useState(false)
  const [discoveryProgress, setDiscoveryProgress] = useState({ found: 0, tested: 0 })
  const [showDiscoveryList, setShowDiscoveryList] = useState(false)

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loginBusy, setLoginBusy] = useState(false)
  const [session, setSession] = useState<StoredSession | null>(null)

  const [activeTab, setActiveTab] = useState<TabKey>('overview')
  const [refreshBusy, setRefreshBusy] = useState(false)
  const [lastSync, setLastSync] = useState('')
  const [bookings, setBookings] = useState<MobileBooking[]>([])
  const [pcs, setPcs] = useState<MobilePc[]>([])
  const [updates, setUpdates] = useState<MobileUpdate[]>([])
  const [assistantMessages, setAssistantMessages] = useState<ChatMessage[]>([
    {
      id: 1,
      role: 'system',
      text: 'Connected apps use the existing PyPondo mobile API. No localhost dev server is required inside the APK.',
    },
  ])

  const [selectedPcId, setSelectedPcId] = useState('')
  const [bookingDate, setBookingDate] = useState('')
  const [bookingTime, setBookingTime] = useState('')
  const [bookingBusy, setBookingBusy] = useState(false)

  const [topupAmount, setTopupAmount] = useState('200')
  const [topupBusy, setTopupBusy] = useState(false)

  const [assistantInput, setAssistantInput] = useState('')
  const [assistantBusy, setAssistantBusy] = useState(false)

  useEffect(() => {
    const storedConfig = readStoredConfig()
    const storedSession = readStoredSession()

    if (storedConfig?.serverAddress) {
      setServerAddress(storedConfig.serverAddress)
      void connectToServer(storedConfig.serverAddress, true)
    }

    if (storedSession) {
      setSession(storedSession)
    }
  }, [])

  useEffect(() => {
    if (!baseUrl) {
      return
    }

    void refreshData()
  }, [baseUrl, session?.userId])

  const availablePcs = pcs.filter((pc) => !pc.is_occupied)
  const connectionLabel =
    connectionStatus === 'connected'
      ? 'Connected'
      : connectionStatus === 'testing'
        ? 'Checking'
        : connectionStatus === 'error'
          ? 'Offline'
          : 'Ready'

  async function connectToServer(addressOverride?: string, silent = false) {
    const candidateAddress = (addressOverride ?? serverAddress).trim()

    try {
      const nextBaseUrl = buildBaseUrl(candidateAddress)
      setConnectionStatus('testing')
      if (!silent) {
        setConnectionMessage('Checking the PyPondo server...')
      }

      const info = await readJson<ServerInfo>(`${nextBaseUrl}/api/server-info`)
      setBaseUrl(nextBaseUrl)
      setServerInfo(info)
      setConnectionStatus('connected')
      setConnectionMessage(
        `Connected to ${info.server_hostname} at ${info.server_ip}:${info.server_port}.`,
      )
      writeStoredConfig(candidateAddress)
      setServerAddress(candidateAddress)
    } catch (error) {
      setBaseUrl('')
      setServerInfo(null)
      setConnectionStatus('error')
      setConnectionMessage(
        error instanceof Error
          ? error.message
          : 'Could not reach the PyPondo server from this device.',
      )
    }
  }

  async function startServerDiscovery() {
    setDiscoveringServers(true)
    setDiscoveryProgress({ found: 0, tested: 0 })
    setConnectionMessage('Searching for PyPondo servers across your network...')

    try {
      const servers = await discoverServers({
        includeGateway: true,
        includeSubnet: true,
        subnetScanCount: 30,
        onProgress: (found, tested) => {
          setDiscoveryProgress({ found, tested })
        },
      })

      setDiscoveredServers(servers)

      if (servers.length === 0) {
        setConnectionMessage(
          'No PyPondo servers found. Try entering the address manually or check your network connection.',
        )
        setShowDiscoveryList(false)
      } else if (servers.length === 1) {
        // Auto-connect if only one server found
        setConnectionMessage(
          `Found ${servers.length} server! Attempting to connect automatically...`,
        )
        await connectToServer(formatServerAddress(servers[0]), false)
      } else {
        setConnectionMessage(`Found ${servers.length} PyPondo servers! Choose one to connect.`)
        setShowDiscoveryList(true)
      }
    } catch (error) {
      setConnectionMessage(
        error instanceof Error ? error.message : 'Server discovery failed. Check your network.',
      )
    } finally {
      setDiscoveringServers(false)
    }
  }

  async function selectDiscoveredServer(server: DiscoveredServer) {
    setShowDiscoveryList(false)
    await connectToServer(formatServerAddress(server), false)
  }

  async function refreshData() {
    if (!baseUrl) {
      return
    }

    setRefreshBusy(true)

    try {
      const [pcsPayload, updatesPayload, bookingsPayload] = await Promise.all([
        readJson<PcsPayload>(`${baseUrl}/api/mobile/pcs`),
        readJson<UpdatesPayload>(`${baseUrl}/api/mobile/updates`),
        session
          ? readJson<BookingPayload>(
              `${baseUrl}/api/mobile/bookings?user_id=${encodeURIComponent(String(session.userId))}`,
            )
          : Promise.resolve<BookingPayload>({ ok: true, bookings: [] }),
      ])

      startTransition(() => {
        setPcs(pcsPayload.pcs ?? [])
        setUpdates(updatesPayload.updates ?? [])
        setBookings(bookingsPayload.bookings ?? [])
      })

      if (!selectedPcId && pcsPayload.pcs.length > 0) {
        const firstAvailable = pcsPayload.pcs.find((pc) => !pc.is_occupied)
        if (firstAvailable) {
          setSelectedPcId(String(firstAvailable.id))
        }
      }

      setLastSync(new Date().toISOString())
    } catch (error) {
      setConnectionMessage(
        error instanceof Error ? error.message : 'Could not refresh mobile data.',
      )
    } finally {
      setRefreshBusy(false)
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!baseUrl) {
      await connectToServer()
    }

    const candidateBaseUrl = baseUrl || buildBaseUrl(serverAddress)
    if (!username.trim() || !password.trim()) {
      setConnectionMessage('Enter both username and password.')
      return
    }

    setLoginBusy(true)

    try {
      const payload = await readJson<LoginPayload>(`${candidateBaseUrl}/api/mobile/login`, {
        body: createFormBody({
          password,
          username,
        }),
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        method: 'POST',
      })

      const nextSession: StoredSession = {
        balance: payload.balance,
        userId: payload.user_id,
        username: payload.username,
      }

      setSession(nextSession)
      writeStoredSession(nextSession)
      setPassword('')
      setConnectionMessage(`Signed in as ${payload.username}.`)
      setActiveTab('overview')
    } catch (error) {
      setConnectionMessage(error instanceof Error ? error.message : 'Login failed.')
    } finally {
      setLoginBusy(false)
    }
  }

  function handleLogout() {
    setSession(null)
    writeStoredSession(null)
    setBookings([])
    setConnectionMessage('Signed out on this device.')
  }

  async function submitBooking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!session) {
      setConnectionMessage('Sign in before creating a booking.')
      return
    }

    if (!selectedPcId || !bookingDate || !bookingTime) {
      setConnectionMessage('Choose a PC, booking date, and booking time.')
      return
    }

    setBookingBusy(true)

    try {
      await readJson(`${baseUrl}/api/mobile/book`, {
        body: createFormBody({
          date: bookingDate,
          pc_id: selectedPcId,
          time: bookingTime,
          user_id: session.userId,
        }),
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        method: 'POST',
      })

      setConnectionMessage('Booking saved successfully.')
      await refreshData()
    } catch (error) {
      setConnectionMessage(error instanceof Error ? error.message : 'Booking failed.')
    } finally {
      setBookingBusy(false)
    }
  }

  async function submitTopup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!session) {
      setConnectionMessage('Sign in before creating a top-up request.')
      return
    }

    const parsedAmount = Number(topupAmount)
    if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      setConnectionMessage('Enter a valid top-up amount.')
      return
    }

    setTopupBusy(true)

    try {
      const payload = await readJson<TopupPayload>(`${baseUrl}/api/mobile/topup`, {
        body: createFormBody({
          amount: parsedAmount,
          user_id: session.userId,
        }),
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        method: 'POST',
      })

      const nextSession = {
        ...session,
        balance: payload.balance,
      }
      setSession(nextSession)
      writeStoredSession(nextSession)
      setConnectionMessage(payload.message)
      setActiveTab('overview')
    } catch (error) {
      setConnectionMessage(error instanceof Error ? error.message : 'Top-up failed.')
    } finally {
      setTopupBusy(false)
    }
  }

  async function submitAssistantMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!session) {
      setConnectionMessage('Sign in before chatting with the assistant.')
      return
    }

    const message = assistantInput.trim()
    if (!message) {
      return
    }

    const userMessage: ChatMessage = {
      id: Date.now(),
      role: 'user',
      text: message,
    }

    startTransition(() => {
      setAssistantMessages((current) => [...current, userMessage])
    })
    setAssistantInput('')
    setAssistantBusy(true)

    try {
      const payload = await readJson<AssistantPayload>(`${baseUrl}/api/mobile/ai-chat`, {
        body: createFormBody({
          message,
          user_id: session.userId,
        }),
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        method: 'POST',
      })

      startTransition(() => {
        setAssistantMessages((current) => [
          ...current,
          {
            id: Date.now() + 1,
            role: 'assistant',
            text: payload.response,
          },
        ])
      })
    } catch (error) {
      startTransition(() => {
        setAssistantMessages((current) => [
          ...current,
          {
            id: Date.now() + 1,
            role: 'system',
            text: error instanceof Error ? error.message : 'Assistant request failed.',
          },
        ])
      })
    } finally {
      setAssistantBusy(false)
    }
  }

  return (
    <main className="app-shell">
      <section className="hero-card">
        <div className="hero-copy">
          <p className="eyebrow">PyPondo Mobile</p>
          <h1>Standalone APK, linked to your PyPondo system.</h1>
          <p className="hero-text">
            The phone app now ships its own interface inside the APK. It no longer
            depends on a PyCharm session or a web dev localhost server.
          </p>
        </div>

        <div className="hero-metrics">
          <div className={`status-badge status-${connectionStatus}`}>{connectionLabel}</div>
          <div className="metric-card">
            <span className="metric-label">Server</span>
            <strong>{serverInfo?.server_hostname || 'Not connected'}</strong>
            <span>{serverInfo ? `${serverInfo.server_ip}:${serverInfo.server_port}` : 'Waiting for address'}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Balance</span>
            <strong>{session ? formatCurrency(session.balance) : 'Sign in required'}</strong>
            <span>{session ? session.username : 'Customer account'}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Last sync</span>
            <strong>{lastSync ? formatTimestamp(lastSync) : 'Not synced yet'}</strong>
            <span>{refreshBusy ? 'Refreshing mobile data' : 'Local UI is bundled in the APK'}</span>
          </div>
        </div>
      </section>

      <section className="panel-grid">
        <article className="panel-card">
          <div className="panel-head">
            <div>
              <p className="section-label">Connection</p>
              <h2>Link this phone to the live PyPondo server</h2>
            </div>
            <button
              className="ghost-button"
              onClick={() => void refreshData()}
              disabled={!baseUrl || refreshBusy}
              type="button"
            >
              {refreshBusy ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>

          <label className="field-label" htmlFor="serverAddress">
            Server address
          </label>
          <input
            id="serverAddress"
            className="text-field"
            onChange={(event) => setServerAddress(event.target.value)}
            placeholder="192.168.1.10:5000"
            type="text"
            value={serverAddress}
          />

          <div className="button-row">
            <button
              className="primary-button"
              disabled={connectionStatus === 'testing'}
              onClick={() => void connectToServer()}
              type="button"
            >
              {connectionStatus === 'testing' ? 'Checking...' : 'Connect'}
            </button>
            <button
              className="secondary-button"
              disabled={discoveringServers}
              onClick={() => void startServerDiscovery()}
              type="button"
            >
              {discoveringServers ? `Scanning... (${discoveryProgress.tested})` : 'Discover servers'}
            </button>
            <button
              className="ghost-button"
              onClick={() => {
                setSession(null)
                writeStoredSession(null)
                window.localStorage.removeItem(CONFIG_STORAGE_KEY)
                setBaseUrl('')
                setServerInfo(null)
                setConnectionStatus('idle')
                setConnectionMessage('Saved device data cleared.')
              }}
              type="button"
            >
              Reset saved data
            </button>
          </div>

          <p className="status-line">{connectionMessage}</p>

          {showDiscoveryList && discoveredServers.length > 0 && (
            <div className="discovered-servers-panel">
              <p className="section-label">Available servers</p>
              <div className="server-list">
                {discoveredServers.map((server, idx) => (
                  <button
                    key={idx}
                    className="server-item"
                    onClick={() => void selectDiscoveredServer(server)}
                    type="button"
                  >
                    <div className="server-info">
                      <strong>{server.hostname}</strong>
                      <span className="server-address">
                        {server.ip}:{server.port}
                      </span>
                      <span className="server-source">{getSourceDescription(server.source)}</span>
                    </div>
                    <div className="server-meta">
                      <span className="response-time">{server.responseTime}ms</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="connection-meta">
            <div className="mini-card">
              <span>App version</span>
              <strong>{serverInfo?.app_version || 'Unknown'}</strong>
            </div>
            <div className="mini-card">
              <span>Available PCs</span>
              <strong>{availablePcs.length}</strong>
            </div>
            <div className="mini-card">
              <span>Updates</span>
              <strong>{updates.length}</strong>
            </div>
          </div>
        </article>

        <article className="panel-card">
          <div className="panel-head">
            <div>
              <p className="section-label">Account</p>
              <h2>{session ? `Signed in as ${session.username}` : 'Customer login'}</h2>
            </div>
            {session ? (
              <button className="ghost-button" onClick={handleLogout} type="button">
                Logout
              </button>
            ) : null}
          </div>

          {session ? (
            <div className="overview-stack">
              <div className="summary-grid">
                <div className="summary-card">
                  <span>Open bookings</span>
                  <strong>{bookings.length}</strong>
                </div>
                <div className="summary-card">
                  <span>Online PCs</span>
                  <strong>{pcs.filter((pc) => pc.online).length}</strong>
                </div>
                <div className="summary-card">
                  <span>Current balance</span>
                  <strong>{formatCurrency(session.balance)}</strong>
                </div>
              </div>

              <div className="tab-row" role="tablist" aria-label="Mobile app sections">
                {(['overview', 'bookings', 'pcs', 'topup', 'assistant', 'updates'] as TabKey[]).map(
                  (tab) => (
                    <button
                      key={tab}
                      className={tab === activeTab ? 'tab-button active' : 'tab-button'}
                      onClick={() => setActiveTab(tab)}
                      type="button"
                    >
                      {tab}
                    </button>
                  ),
                )}
              </div>

              {activeTab === 'overview' ? (
                <section className="content-stack">
                  <div className="info-banner">
                    This APK hosts the customer UI locally. Only the PyPondo server needs
                    to be reachable on the network.
                  </div>

                  <div className="two-column-grid">
                    <div className="content-card">
                      <h3>Upcoming bookings</h3>
                      {bookings.length > 0 ? (
                        bookings.slice(0, 3).map((booking, index) => (
                          <div className="list-item" key={`${booking.pc_name}-${booking.date}-${index}`}>
                            <strong>{booking.pc_name}</strong>
                            <span>
                              {booking.date} at {booking.time}
                            </span>
                            <span className="pill">{booking.status}</span>
                          </div>
                        ))
                      ) : (
                        <p className="empty-copy">No bookings yet.</p>
                      )}
                    </div>

                    <div className="content-card">
                      <h3>Latest updates</h3>
                      {updates.length > 0 ? (
                        updates.slice(0, 2).map((update) => (
                          <div className="list-item" key={`${update.version}-${update.title}`}>
                            <strong>{update.title}</strong>
                            <span>{update.description}</span>
                            <span className="pill accent">
                              v{update.version} {update.update_type}
                            </span>
                          </div>
                        ))
                      ) : (
                        <p className="empty-copy">No updates published yet.</p>
                      )}
                    </div>
                  </div>
                </section>
              ) : null}

              {activeTab === 'bookings' ? (
                <section className="content-stack">
                  <form className="content-card" onSubmit={submitBooking}>
                    <h3>Create booking</h3>
                    <label className="field-label" htmlFor="pcSelect">
                      PC
                    </label>
                    <select
                      id="pcSelect"
                      className="text-field"
                      onChange={(event) => setSelectedPcId(event.target.value)}
                      value={selectedPcId}
                    >
                      <option value="">Select a free PC</option>
                      {availablePcs.map((pc) => (
                        <option key={pc.id} value={pc.id}>
                          {pc.name}
                        </option>
                      ))}
                    </select>

                    <div className="two-column-grid compact">
                      <div>
                        <label className="field-label" htmlFor="bookingDate">
                          Date
                        </label>
                        <input
                          id="bookingDate"
                          className="text-field"
                          onChange={(event) => setBookingDate(event.target.value)}
                          type="date"
                          value={bookingDate}
                        />
                      </div>
                      <div>
                        <label className="field-label" htmlFor="bookingTime">
                          Time
                        </label>
                        <input
                          id="bookingTime"
                          className="text-field"
                          onChange={(event) => setBookingTime(event.target.value)}
                          type="time"
                          value={bookingTime}
                        />
                      </div>
                    </div>

                    <button className="primary-button" disabled={bookingBusy} type="submit">
                      {bookingBusy ? 'Saving booking...' : 'Book now'}
                    </button>
                  </form>

                  <div className="content-card">
                    <h3>Existing bookings</h3>
                    {bookings.length > 0 ? (
                      bookings.map((booking, index) => (
                        <div className="list-item" key={`${booking.pc_name}-${booking.date}-${index}`}>
                          <strong>{booking.pc_name}</strong>
                          <span>
                            {booking.date} at {booking.time}
                          </span>
                          <span className="pill">{booking.status}</span>
                        </div>
                      ))
                    ) : (
                      <p className="empty-copy">No bookings found for this account.</p>
                    )}
                  </div>
                </section>
              ) : null}

              {activeTab === 'pcs' ? (
                <section className="content-card">
                  <h3>PC availability</h3>
                  {pcs.length > 0 ? (
                    pcs.map((pc) => (
                      <div className="list-item" key={pc.id}>
                        <strong>{pc.name}</strong>
                        <span>{pc.lan_ip || 'No LAN IP registered yet'}</span>
                        <span className={pc.online ? 'pill success' : pc.is_occupied ? 'pill warn' : 'pill'}>
                          {pc.online ? 'online' : pc.is_occupied ? 'busy' : 'free'}
                        </span>
                      </div>
                    ))
                  ) : (
                    <p className="empty-copy">No PCs are exposed by the mobile API yet.</p>
                  )}
                </section>
              ) : null}

              {activeTab === 'topup' ? (
                <form className="content-card" onSubmit={submitTopup}>
                  <h3>Create top-up request</h3>
                  <label className="field-label" htmlFor="topupAmount">
                    Amount
                  </label>
                  <input
                    id="topupAmount"
                    className="text-field"
                    inputMode="decimal"
                    onChange={(event) => setTopupAmount(event.target.value)}
                    type="number"
                    value={topupAmount}
                  />

                  <div className="quick-grid">
                    {QUICK_TOPUP_AMOUNTS.map((amount) => (
                      <button
                        key={amount}
                        className="ghost-button"
                        onClick={() => setTopupAmount(String(amount))}
                        type="button"
                      >
                        {formatCurrency(amount)}
                      </button>
                    ))}
                  </div>

                  <button className="primary-button" disabled={topupBusy} type="submit">
                    {topupBusy ? 'Submitting...' : 'Submit request'}
                  </button>
                </form>
              ) : null}

              {activeTab === 'assistant' ? (
                <section className="content-stack">
                  <div className="content-card chat-log">
                    <h3>Assistant</h3>
                    {assistantMessages.map((message) => (
                      <div className={`chat-bubble ${message.role}`} key={message.id}>
                        <span>{message.role}</span>
                        <p>{message.text}</p>
                      </div>
                    ))}
                  </div>

                  <form className="content-card" onSubmit={submitAssistantMessage}>
                    <label className="field-label" htmlFor="assistantInput">
                      Ask about bookings, balance, or cafe updates
                    </label>
                    <textarea
                      id="assistantInput"
                      className="text-area"
                      onChange={(event) => setAssistantInput(event.target.value)}
                      rows={4}
                      value={assistantInput}
                    />
                    <button className="primary-button" disabled={assistantBusy} type="submit">
                      {assistantBusy ? 'Sending...' : 'Send message'}
                    </button>
                  </form>
                </section>
              ) : null}

              {activeTab === 'updates' ? (
                <section className="content-card">
                  <h3>Release feed</h3>
                  {updates.length > 0 ? (
                    updates.map((update) => (
                      <div className="list-item" key={`${update.version}-${update.title}`}>
                        <strong>{update.title}</strong>
                        <span>{update.description}</span>
                        <span className="pill accent">
                          v{update.version} · {update.update_type} · {formatTimestamp(update.timestamp)}
                        </span>
                      </div>
                    ))
                  ) : (
                    <p className="empty-copy">No update feed items are available.</p>
                  )}
                </section>
              ) : null}
            </div>
          ) : (
            <form className="login-form" onSubmit={handleLogin}>
              <p className="login-copy">
                Use a customer account from the existing PyPondo server. The phone app
                connects over LAN and keeps the UI local inside the APK.
              </p>

              <label className="field-label" htmlFor="username">
                Username
              </label>
              <input
                id="username"
                className="text-field"
                onChange={(event) => setUsername(event.target.value)}
                type="text"
                value={username}
              />

              <label className="field-label" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                className="text-field"
                onChange={(event) => setPassword(event.target.value)}
                type="password"
                value={password}
              />

              <button
                className="primary-button"
                disabled={loginBusy || connectionStatus === 'testing'}
                type="submit"
              >
                {loginBusy ? 'Signing in...' : 'Login to mobile app'}
              </button>
            </form>
          )}
        </article>
      </section>
    </main>
  )
}

export default App
