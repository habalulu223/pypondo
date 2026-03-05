# PyPondo Architecture & Gateway Discovery

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PyPondo System                           │
└─────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Core Components                                              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐   ┌──────────────┐    │
│  │   app.py     │    │ desktop_app  │   │  lan_agent   │    │
│  │              │    │     .py      │   │     .py      │    │
│  │ Admin Server │    │ Client UI    │   │ LAN Agent    │    │
│  │              │    │              │   │              │    │
│  │ • Flask Web  │    │ • Desktop    │   │ • Registers  │    │
│  │ • Database   │    │ • Browser    │   │ • Polls      │    │
│  │ • LAN APIs   │    │ • Auto-disc. │   │ • Auto-disc. │    │
│  │ • Commands   │    │ • Gateway    │   │ • Gateway    │    │
│  │              │    │   discovery  │   │   discovery  │    │
│  └──────────────┘    └──────────────┘   └──────────────┘    │
│       ▲                     ▲                   ▲              │
│       │                     │ Discovers        │ Discovers    │
│       └─────────────────────┼────────────────────┘             │
│                             │ via                              │
│                             └─ Gateway IP                      │
│                                                                │
└──────────────────────────────────────────────────────────────┘
```

## Gateway Discovery Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Client App Startup (desktop_app.py)                         │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────┐
        │ Is Client Mode?                 │
        │ (PYPONDO_APP_MODE=client)       │
        └────────┬────────────────────────┘
                 │
        ┌────────┴─────────┐
        │ NO               │ YES
        ▼                  ▼
   [Start Local]    ┌──────────────────────────────────┐
   Admin Server     │ Try to Discover Remote Server    │
                    └───────────────┬──────────────────┘
                                    │
                                    ▼
                    ┌──────────────────────────────────┐
                    │ build_server_base_url_candidates│
                    └───────────────┬──────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
   ┌──────────────┐     ┌──────────────────┐     ┌────────────────────┐
   │ Explicit     │     │ From File        │     │ Auto Discovery     │
   │ Env Vars     │     │ server_host.txt  │     │ Gateway IPs ← NEW! │
   │              │     │                  │     │                    │
   │ PYPONDO_     │     │ • IP addresses   │     │ ipconfig →         │
   │ SERVER_      │     │ • Hostnames      │     │ Default Gateway    │
   │ HOST         │     │ • Full URLs      │     │ → 192.168.1.1      │
   └──────┬───────┘     └────────┬─────────┘     └──────────┬─────────┘
          │                      │                          │
          └──────────────────────┼──────────────────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────────────┐
                    │ Deduplicate & Order Candidates  │
                    │ (prefer DNS over IP)            │
                    └───────────────┬──────────────────┘
                                    │
                                    ▼
                    ┌──────────────────────────────────┐
                    │ Probe Each Candidate            │
                    │ Test: /login                    │
                    │ Test: /api/agent/register-lan   │
                    └───────────────┬──────────────────┘
                                    │
                    ┌───────────────┴────────────────┐
                    │                                │
                    ▼ SUCCESS                        ▼ NOT FOUND
        ┌──────────────────────┐      ┌──────────────────────────┐
        │ Found Remote Server! │      │ Use Local Fallback       │
        │ Connect to Admin     │      │ Start Local Server       │
        │ Launch UI → Remote   │      │ Launch UI → Localhost    │
        └──────────────────────┘      └──────────────────────────┘
                    │                                │
                    ▼                                ▼
        ┌──────────────────────┐      ┌──────────────────────────┐
        │ Start Client Agent   │      │ Start Client Agent       │
        │ (lan_agent.py)       │      │ (lan_agent.py)           │
        │ Uses Server URL      │      │ Uses Local Server        │
        └──────────────────────┘      └──────────────────────────┘
```

## Gateway Discovery Detailed

```
Step 1: Execute ipconfig
────────────────────────────────────────────────────────────
        │
        ▼
    subprocess.check_output(["ipconfig"])
        │
        ▼
    Windows:
    Ethernet adapter Local Area Connection:
    ...
    IPv4 Address . . . . . . . . . . : 192.168.1.50
    Subnet Mask . . . . . . . . . . : 255.255.255.0
    Default Gateway . . . . . . . . . : 192.168.1.1  ← Extract this!
    ...

Step 2: Parse Output
────────────────────────────────────────────────────────────
        │
        ▼
    Search for lines with "Default Gateway"
        │
        ▼
    Extract text after ":"
    "192.168.1.1"
        │
        ▼
    Validate IPv4 format
    ✓ 4 octets
    ✓ Each 0-255
        │
        ▼
    Store in list: ["192.168.1.1"]

Step 3: Return Gateway List
────────────────────────────────────────────────────────────
        │
        ▼
    return ["192.168.1.1"]
        │
        ▼
    Added to: host_candidates
        │
        ▼
    Used in: probe_server_base_url()
```

## Multi-Machine Network Example

```
┌────────────────────────────────────────────────────────────┐
│  Local Area Network (192.168.1.0/24)                       │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌─────────────────────────┐                              │
│  │ Router / Network Device │                              │
│  │ 192.168.1.1 (Gateway)   │                              │
│  │                         │                              │
│  │ NOT running PyPondo     │                              │
│  └──────────┬──────────────┘                              │
│             │                                              │
│  ┌──────────┼──────────────────────────────────────────┐  │
│  │          │                                          │  │
│  │          ▼                                          ▼  │
│  │  ┌──────────────────────┐           ┌─────────────────┐ │
│  │  │ Admin PC             │           │ Client PC #1    │ │
│  │  │ 192.168.1.10         │           │ 192.168.1.50    │ │
│  │  │                      │           │                 │ │
│  │  │ python app.py        │◄──────────│ Discovers via   │ │
│  │  │ Running on :5000     │  Probes   │ gateway IP      │ │
│  │  │                      │  Gateway  │ python desktop_ │ │
│  │  │ - Web Interface      │  (1.1)    │ app.py          │ │
│  │  │ - Database           │  :5000    │                 │ │
│  │  │ - LAN APIs           │           │ - Opens UI on   │ │
│  │  │                      │           │   Admin (1.10)  │ │
│  │  └──────────────────────┘           └─────────────────┘ │
│  │           ▲                                              │
│  │           │                          ┌─────────────────┐ │
│  │           │                          │ Client PC #2    │ │
│  │           │                          │ 192.168.1.51    │ │
│  │           └──────────────────────────│ Discovers via   │ │
│  │                  Probes Gateway      │ gateway IP      │ │
│  │                  :5000               │ python desktop_ │ │
│  │                                      │ app.py          │ │
│  │                                      └─────────────────┘ │
│  │                                                          │
│  └──────────────────────────────────────────────────────────┘
│
│  Discovery Process:
│  ────────────────
│  Client PC #1 & #2:
│    1. Run: ipconfig
│    2. Find: Default Gateway = 192.168.1.1
│    3. Probe: http://192.168.1.1:5000/login
│    4. Fail: No response (gateway is router)
│    5. Try other methods: net view, etc.
│    6. Find: 192.168.1.10 from net view
│    7. Probe: http://192.168.1.10:5000/login
│    8. Success! Connect to Admin
│
└────────────────────────────────────────────────────────────┘
```

## Discovery Priority Chain

```
Candidate Sources (in order of precedence):
────────────────────────────────────────────

1. EXPLICIT ENVIRONMENT VARIABLES
   └─ PYPONDO_SERVER_BASE_URL
   └─ PYPONDO_SERVER_HOST
   └─ LAN_SERVER_BASE_URL

2. CONFIGURATION FILE
   └─ server_host.txt

3. ENVIRONMENT VARIABLES (SECONDARY)
   └─ APP_HOST
   └─ LAN_SERVER_REGISTER_URL

4. AUTOMATIC DISCOVERY
   ├─ net view (Windows network shares)
   ├─ ipconfig (Default Gateway IPs) ← NEW!
   └─ Combination of above

5. LOCAL FALLBACK
   └─ Start local Flask server
```

## Server Probing

```
For each candidate URL:
─────────────────────────────────────────────────────

Candidate: http://192.168.1.1:5000
           │
           ▼
        ┌──────────────────────────────┐
        │ Try /login endpoint          │
        │ (HTTP request, 1.5s timeout) │
        └────┬─────────────────────────┘
             │
        ┌────┴─────────┐
        │              │
     SUCCESS        FAIL/TIMEOUT
        │              │
        ▼              ▼
    Return ✓      Try /api/agent/register-lan
    (Found!)      │
                  ▼
              ┌──────────────────────────────┐
              │ Try API endpoint             │
              │ (HTTP request, 1.5s timeout) │
              └────┬─────────────────────────┘
                   │
              ┌────┴─────────┐
              │              │
           SUCCESS        FAIL/TIMEOUT
              │              │
              ▼              ▼
          Return ✓       Move to next
          (Found!)       candidate
```

## Configuration Methods Diagram

```
                 ┌──────────────┐
                 │ Run App      │
                 └──────┬───────┘
                        │
         ┌──────────────┼──────────────┐
         │              │              │
         ▼              ▼              ▼
    ┌─────────┐   ┌──────────┐   ┌─────────────┐
    │ Method 1│   │ Method 2 │   │  Method 3   │
    │ Env Var │   │  Config  │   │   Explicit  │
    │         │   │   File   │   │    URL      │
    └────┬────┘   └────┬─────┘   └──────┬──────┘
         │             │                │
         │ Set env:    │ Create file:   │ Full URL:
         │             │                │
         │$env:        │server_host.txt │$env:PYPONDO
         │PYPONDO_    │                │_SERVER_
         │SERVER_HOST │192.168.1.10    │BASE_URL
         │ =           │admin-pc        │="http://..."
         │"192.168.1"  │                │
         │             │                │
         └─────┬───────┴────────────────┘
               │
               ▼ (if no manual config)
         ┌──────────────────┐
         │ Auto-Discovery   │
         │ (Gateway IPs)    │
         │ ipconfig         │
         └──────────────────┘
               │
               ▼
         ┌──────────────────┐
         │ Server Found?    │
         └────┬─────────────┘
              │
         ┌────┴─────────┐
         │              │
        YES             NO
         │              │
         ▼              ▼
    ┌─────────┐   ┌──────────┐
    │ Connect │   │ Fallback │
    │ to      │   │ to Local │
    │ Remote  │   │ Server   │
    └─────────┘   └──────────┘
```

## Component Dependencies

```
                    PyPondo System
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
      app.py        desktop_app.py   lan_agent.py
         │               │               │
         ├─ Flask        ├─ Flask        ├─ Flask
         ├─ SQLAlchemy   ├─ stdlib       ├─ stdlib
         ├─ SQLite       │               │
         └─ stdlib       └─ None!        └─ None!
                                (except Flask)
                                
    None of these require:
    ├─ PyCharm
    ├─ IntelliJ
    ├─ IDE plugins
    ├─ Jython
    └─ Any special setup

    Can run with:
    ├─ Command Prompt
    ├─ PowerShell
    ├─ Batch files
    ├─ Task Scheduler
    ├─ Standalone EXE
    └─ Docker
```

## Startup Sequence

```
User runs: python desktop_app.py
│
▼
┌──────────────────────────────────────┐
│ Check APP_MODE                       │
│ (client mode by default)             │
└────────┬─────────────────────────────┘
         │
         ▼
    ┌──────────────────────────────────────┐
    │ Try Remote Discovery                 │
    │ build_server_base_url_candidates()   │
    │   │                                  │
    │   ├─ Check env vars                  │
    │   ├─ Read server_host.txt            │
    │   ├─ Run net view                    │
    │   ├─ Run ipconfig ← NEW!             │
    │   └─ Get gateway IPs                 │
    │                                      │
    │ Probe each candidate                 │
    └────────┬─────────────────────────────┘
             │
        ┌────┴──────┐
        │           │
       YES          NO
        │           │
        ▼           ▼
    ┌─────────┐  ┌──────────────────────┐
    │ Found!  │  │ Fallback to Local    │
    │ Connect │  │ ensure_seed_data()   │
    │ to      │  │ pick_port()          │
    │ Remote  │  │ run_flask()          │
    │ Server  │  │ wait_for_server()    │
    └─────────┘  └──────────────────────┘
        │                │
        ├────────┬───────┘
                 │
                 ▼
    ┌──────────────────────────────┐
    │ start_client_agent_background│
    │ (lan_agent.py)               │
    │ Registers with admin         │
    └──────────────────────────────┘
        │
        ▼
    ┌──────────────────────────────┐
    │ launch_ui(url)               │
    │ Opens UI in:                 │
    │ • pywebview (preferred)      │
    │ • System browser (fallback)  │
    └──────────────────────────────┘
```

---

This architecture ensures:
✅ Automatic discovery via gateway
✅ Zero manual configuration (optional only)
✅ Complete app independence
✅ Graceful fallback mechanisms
✅ Production-ready deployment
