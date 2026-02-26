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
python app.py
```

- `LAN_AGENT_TOKEN`: shared secret used by server and all agents.
- `LAN_PC_TARGETS`: JSON mapping from `PC.name` to `host:port` or full URL.
- Optional `LAN_AGENT_DEFAULT_PORT`: default is `5001` when using DB-assigned PC IPs.

## 2) Run an agent on each client PC

On each Windows client machine:

```powershell
$env:LAN_AGENT_TOKEN="replace-with-strong-shared-secret"
$env:LAN_PC_NAME="PC-1"
$env:LAN_SERVER_REGISTER_URL="http://192.168.1.10:5000/api/agent/register-lan"
$env:LAN_AGENT_PORT="5001"
python lan_agent.py
```

Allow inbound TCP `5001` in Windows Firewall for your LAN.

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

## Notes

- Endpoint is `admin-only` and restricted to an allowlist (no arbitrary shell commands).
- Every command attempt is saved in `AdminLog`.
- Admin dashboard now shows local server IPs (`ipconfig`) and discovered LAN devices (`arp -a`), and can auto-assign discovered IPs to PCs.

## Online Top-Up (Database Only)

This mode does not call any external payment gateway.

User flow:
- User enters amount and submits online top-up.
- App stores a `PaymentTransaction` row with status `pending`.
- Record is visible in user recent top-ups.

API flow:
- `POST /api/topup` body: `{ "amount": 100 }` -> returns `transaction_id` (saved as pending)
- `POST /api/topup/confirm` body: `{ "transaction_id": "REQ-..." }` -> returns current transaction status
