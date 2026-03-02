# LAN Command API Setup

This project now includes:
- Server endpoint: `POST /api/pc-command` (admin login required)
- Dashboard action: per-PC LAN command form on the main page
- LAN discovery: `GET /api/admin/lan-discovery` (admin)
- Auto assignment: `POST /api/admin/auto-assign-ips` (admin)
- Client agent: `lan_agent.py` (run this on each target PC)

## 1) Configure the server

Set these environment variables before running `app.py`:

```powershell
$env:LAN_AGENT_TOKEN="replace-with-strong-shared-secret"
$env:LAN_PC_TARGETS='{"PC-1":"192.168.1.101:5001","PC-2":"192.168.1.102:5001"}'
$env:LAN_REMOTE_USERNAME="Administrator"
$env:LAN_REMOTE_PASSWORD="your-remote-admin-password"
# Optional if using domain account:
# $env:LAN_REMOTE_DOMAIN="MYDOMAIN"
python app.py
```

- `LAN_AGENT_TOKEN`: shared secret used by server and all agents.
- `LAN_PC_TARGETS`: JSON mapping from `PC.name` to `host:port` or full URL.
- `LAN_REMOTE_USERNAME` / `LAN_REMOTE_PASSWORD`: optional Windows credentials used by fallback (`shutdown /m` and `wmic`) when the LAN agent is unreachable.
- `LAN_REMOTE_DOMAIN`: optional domain prefix for `LAN_REMOTE_USERNAME` (e.g. `MYDOMAIN\Administrator`).
- Optional `LAN_AGENT_DEFAULT_PORT`: default is `5001` when using DB-assigned PC IPs.
- Optional `LAN_REQUIRE_AGENT_POPUP_PATH`: default `1`. When enabled, `lock/restart/shutdown` are queued for agent popup approval if direct agent delivery fails (Windows fallback is skipped for these commands).
- Optional `LAN_POWER_COMMAND_CONFIRM_TEXT`: default `CONFIRM`. Required in admin form/API for restart/shutdown.

## 2) Run an agent on each client PC

On each Windows client machine:

```powershell
$env:LAN_AGENT_TOKEN="replace-with-strong-shared-secret"
$env:LAN_PC_NAME="PC-1"
$env:LAN_SERVER_REGISTER_URL="http://192.168.1.10:5000/api/agent/register-lan"
$env:LAN_AGENT_PORT="5001"
python lan_agent.py
```

Admin download shortcut:
- In dashboard, each PC card has `Download Client (Join This System)`.
- It downloads a preconfigured ZIP with:
  - `run_client_app.bat` (opens the same admin system URL in app window mode)
  - `run_client_agent.bat` (LAN command agent connector)
  - server URL and PC name already configured

Allow inbound TCP `5001` in Windows Firewall for your LAN.

Optional agent approval prompt (recommended for shared PCs):
- `LAN_REQUIRE_USER_APPROVAL=1` (default) shows a Yes/No popup on the client before `lock`, `restart`, or `shutdown`.
- If the user clicks **No**, the command is rejected and this is reported back to server logs/status.
- Set `LAN_REQUIRE_USER_APPROVAL=0` to execute immediately without popup.

Auto-registration behavior:
- Client detects its own LAN IPv4.
- Client calls `POST /api/agent/register-lan` on server.
- Server updates `PC.lan_ip` for the matching `LAN_PC_NAME`.
- Optional: set `LAN_REGISTER_INTERVAL_SECONDS` (default `60`, set `0` for one-time registration).

## 3) Call the API

Login as admin, then call:

```http
POST /api/pc-command
Content-Type: application/json

{
  "pc_name": "PC-1",
  "command": "lock",
  "payload": {}
}
```

Allowed commands:
- `lock`
- `restart`
- `shutdown`
- `wake`

For `restart` and `shutdown`, include:
- `reason`: 8-200 characters
- `confirm_text`: must match `LAN_POWER_COMMAND_CONFIRM_TEXT` (default: `CONFIRM`)

## Notes

- Endpoint is `admin-only` and restricted to an allowlist (no arbitrary shell commands).
- Every command attempt is saved in `AdminLog`.
- `lock`, `restart`, and `shutdown` are designed for agent-side user approval popup (Yes/No) on the targeted PC.
- Server now sends an agent `connect_request` first. If user approves immediately, command executes right away; otherwise command waits and API returns pending approval.
- Windows fallback is enabled by default. It uses:
  - `shutdown /m` for `restart` and `shutdown`
  - remote WMI process call for `lock`
  - if provided, fallback authenticates using `LAN_REMOTE_USERNAME` / `LAN_REMOTE_PASSWORD` before command execution
  Disable all fallback by setting `LAN_ALLOW_REMOTE_WINDOWS_FALLBACK=0`.
- Admin dashboard now shows local server IPs (`ipconfig`) and discovered LAN devices (`arp -a`), and can auto-assign discovered IPs to PCs.

## Access Denied (5) Troubleshooting

If you still see `Access is denied.(5)`:

1. Confirm the client agent is actually running on the target PC (`python lan_agent.py`), and firewall allows inbound port `5001`.
2. If agent is offline, configure fallback credentials on the server:
   - `LAN_REMOTE_USERNAME`
   - `LAN_REMOTE_PASSWORD`
3. Ensure the remote Windows machine allows remote admin/WMI/shutdown for that account (local admin rights required).
4. Restart `app.py` after setting environment variables so the server picks up the new credentials.

## Online Top-Up (Database Only)

This mode does not call any external payment gateway.

User flow:
- User enters amount and submits online top-up.
- App stores a `PaymentTransaction` row with status `pending`.
- Record is visible in user recent top-ups.

API flow:
- `POST /api/topup` body: `{ "amount": 100 }` -> returns `transaction_id` (saved as pending)
- `POST /api/topup/confirm` body: `{ "transaction_id": "REQ-..." }` -> returns current transaction status
