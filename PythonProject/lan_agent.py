import os
import socket
import subprocess
import threading
import time
import ctypes
import re
from flask import Flask, request, jsonify
from urllib import request as http_request
from urllib import error as http_error
from urllib import parse as http_parse
import json

app = Flask(__name__)

DEFAULT_LAN_AGENT_TOKEN = "pypondo-lan-token-change-me"
AGENT_TOKEN = os.getenv("LAN_AGENT_TOKEN", DEFAULT_LAN_AGENT_TOKEN).strip() or DEFAULT_LAN_AGENT_TOKEN
HOST = os.getenv("LAN_AGENT_HOST", "0.0.0.0")
PORT = int(os.getenv("LAN_AGENT_PORT", "5001"))
PC_NAME = os.getenv("LAN_PC_NAME", "").strip()
REGISTER_URL = os.getenv("LAN_SERVER_REGISTER_URL", "").strip()
REGISTER_INTERVAL_SECONDS = int(os.getenv("LAN_REGISTER_INTERVAL_SECONDS", "60"))
SERVER_BASE_URL = os.getenv("LAN_SERVER_BASE_URL", "").strip()
COMMAND_POLL_URL = os.getenv("LAN_SERVER_COMMAND_POLL_URL", "").strip()
COMMAND_ACK_URL = os.getenv("LAN_SERVER_COMMAND_ACK_URL", "").strip()
SERVER_HOST = os.getenv("LAN_SERVER_HOST", "").strip()
SERVER_SCHEME = os.getenv("LAN_SERVER_SCHEME", "http").strip() or "http"
SERVER_HOST_CANDIDATES = os.getenv("LAN_SERVER_HOST_CANDIDATES", "").strip()
SERVER_HOST_FILE = os.getenv("LAN_SERVER_HOST_FILE", "server_host.txt").strip() or "server_host.txt"
try:
    SERVER_PORT = int(os.getenv("LAN_SERVER_PORT", "5000"))
except Exception:
    SERVER_PORT = 5000
POLL_INTERVAL_SECONDS = int(os.getenv("LAN_POLL_INTERVAL_SECONDS", "3"))
AGENT_IDENTITY = PC_NAME or socket.gethostname()
REQUIRE_USER_APPROVAL = str(os.getenv("LAN_REQUIRE_USER_APPROVAL", "1")).strip().lower() in {"1", "true", "yes"}
APPROVAL_COMMANDS = {"lock", "restart", "shutdown"}
ACTIVE_SERVER_BASE_URL = ""
ACTIVE_REGISTER_URL = ""


def detect_local_lan_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        return ip
    except Exception:
        return None
    finally:
        sock.close()


def split_host_candidates(raw_value):
    values = []
    for part in str(raw_value or "").replace(";", ",").split(","):
        candidate = part.strip()
        if candidate:
            values.append(candidate)
    return values


def read_host_candidates_from_file():
    runtime_dir = os.path.abspath(os.path.dirname(__file__))
    file_path = os.path.join(runtime_dir, SERVER_HOST_FILE)
    if not os.path.exists(file_path):
        return []
    values = []
    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                values.extend(split_host_candidates(line))
    except Exception:
        return []
    return values


def discover_hosts_from_net_view():
    if os.name != "nt":
        return []
    try:
        output = subprocess.check_output(
            ["net", "view"],
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=4
        )
    except Exception:
        return []

    hosts = []
    for raw_line in output.splitlines():
        match = re.match(r"^\s*\\\\([^\\\s]+)", raw_line)
        if not match:
            continue
        value = match.group(1).strip()
        if value:
            hosts.append(value)
    return hosts


def extract_base_url(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    parsed = http_parse.urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def probe_server_base_url(base_url):
    root = str(base_url or "").rstrip("/")
    if not root:
        return False
    for path in ("/login", "/api/agent/register-lan"):
        target = root + path
        try:
            with http_request.urlopen(target, timeout=1.5):
                return True
        except http_error.HTTPError as exc:
            if 200 <= exc.code < 500:
                return True
        except Exception:
            continue
    return False


def build_server_base_candidates():
    explicit = []
    for value in (SERVER_BASE_URL, REGISTER_URL):
        base = extract_base_url(value)
        if base:
            explicit.append(base)

    hosts = []
    hosts.extend(split_host_candidates(SERVER_HOST))
    hosts.extend(split_host_candidates(SERVER_HOST_CANDIDATES))
    hosts.extend(read_host_candidates_from_file())
    hosts.extend(discover_hosts_from_net_view())

    seen = set()
    unique_hosts = []
    for host in hosts:
        value = str(host).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_hosts.append(value)

    candidates = []
    for host in unique_hosts:
        if "://" in host:
            base = extract_base_url(host)
            if base:
                candidates.append(base)
            continue
        candidates.append(f"{SERVER_SCHEME}://{host}:{SERVER_PORT}")

    ordered = []
    seen_urls = set()
    for candidate in explicit + candidates:
        key = candidate.lower()
        if key in seen_urls:
            continue
        seen_urls.add(key)
        ordered.append(candidate.rstrip("/"))
    return ordered


def discover_server_base_url():
    global ACTIVE_SERVER_BASE_URL

    if ACTIVE_SERVER_BASE_URL and probe_server_base_url(ACTIVE_SERVER_BASE_URL):
        return ACTIVE_SERVER_BASE_URL

    for candidate in build_server_base_candidates():
        if probe_server_base_url(candidate):
            ACTIVE_SERVER_BASE_URL = candidate.rstrip("/")
            return ACTIVE_SERVER_BASE_URL
    return ""


def get_register_url_candidates():
    global ACTIVE_REGISTER_URL

    candidates = []
    if ACTIVE_REGISTER_URL:
        candidates.append(ACTIVE_REGISTER_URL)

    discovered_base = discover_server_base_url()
    if discovered_base:
        candidates.append(discovered_base + "/api/agent/register-lan")
    if REGISTER_URL:
        candidates.append(REGISTER_URL)

    seen = set()
    ordered = []
    for value in candidates:
        target = str(value or "").strip()
        if not target:
            continue
        key = target.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(target)
    return ordered


def register_with_server():
    global ACTIVE_REGISTER_URL, ACTIVE_SERVER_BASE_URL

    register_targets = get_register_url_candidates()
    if not register_targets or not AGENT_TOKEN:
        return False, "Registration skipped (missing LAN server host/URL or LAN_AGENT_TOKEN)"

    lan_ip = detect_local_lan_ip()
    body = json.dumps({
        "pc_name": AGENT_IDENTITY,
        "lan_ip": lan_ip,
        "agent_port": PORT
    }).encode("utf-8")
    errors = []

    for register_url in register_targets:
        req = http_request.Request(
            register_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Agent-Token": AGENT_TOKEN
            }
        )

        try:
            with http_request.urlopen(req, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
                if payload.get("ok"):
                    ACTIVE_REGISTER_URL = register_url
                    discovered_base = extract_base_url(register_url)
                    if discovered_base:
                        ACTIVE_SERVER_BASE_URL = discovered_base
                    pending = payload.get("pending_command")
                    if isinstance(pending, dict) and pending.get("command"):
                        command_id = pending.get("command_id")
                        command = str(pending.get("command", "")).strip().lower()
                        server_pc_name = str(pending.get("pc_name", "")).strip() or AGENT_IDENTITY
                        exec_ok, exec_message = execute_allowed_command(command, pending.get("payload", {}))
                        ack_ok, ack_message = ack_command_to_server(command_id, exec_ok, exec_message, pc_identity=server_pc_name)
                        if not ack_ok:
                            return True, f"Registered {payload.get('pc_name')} -> {payload.get('lan_ip')} | executed queued #{command_id} ({'ok' if exec_ok else 'fail'}) but ack failed: {ack_message}"
                        return True, f"Registered {payload.get('pc_name')} -> {payload.get('lan_ip')} | executed queued #{command_id}: {'ok' if exec_ok else 'fail'}"
                    return True, f"Registered {payload.get('pc_name')} -> {payload.get('lan_ip')}"
                errors.append(f"{register_url}: {payload.get('error', 'registration failed')}")
        except http_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            errors.append(f"{register_url}: HTTP {exc.code}: {detail}")
        except Exception as exc:
            errors.append(f"{register_url}: {exc}")

    if errors:
        return False, " | ".join(errors[:3])
    return False, "Registration failed"


def resolve_server_url(path):
    if ACTIVE_SERVER_BASE_URL:
        return ACTIVE_SERVER_BASE_URL.rstrip("/") + path
    if SERVER_BASE_URL:
        return SERVER_BASE_URL.rstrip("/") + path
    if REGISTER_URL and "/api/agent/register-lan" in REGISTER_URL:
        return REGISTER_URL.split("/api/agent/register-lan", 1)[0] + path
    if REGISTER_URL and "/api/" in REGISTER_URL:
        return REGISTER_URL.split("/api/", 1)[0] + path
    discovered = discover_server_base_url()
    if discovered:
        return discovered.rstrip("/") + path
    return ""


def get_poll_url():
    return COMMAND_POLL_URL or resolve_server_url("/api/agent/pull-command")


def get_ack_url():
    return COMMAND_ACK_URL or resolve_server_url("/api/agent/ack-command")


def registration_loop():
    while True:
        ok, message = register_with_server()
        print(f"[LAN_AGENT] register: {'ok' if ok else 'fail'} - {message}")
        if REGISTER_INTERVAL_SECONDS <= 0:
            break
        time.sleep(REGISTER_INTERVAL_SECONDS)


def pull_command_from_server():
    poll_url = get_poll_url()
    if not poll_url or not AGENT_TOKEN:
        return False, "Polling disabled (missing URL/token)", None

    body = json.dumps({
        "pc_name": AGENT_IDENTITY,
        "lan_ip": detect_local_lan_ip()
    }).encode("utf-8")
    req = http_request.Request(
        poll_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Agent-Token": AGENT_TOKEN
        }
    )

    try:
        with http_request.urlopen(req, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
            return True, "ok", payload
    except http_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        return False, f"HTTP {exc.code}: {detail}", None
    except Exception as exc:
        return False, str(exc), None


def ack_command_to_server(command_id, ok, message, pc_identity=None):
    ack_url = get_ack_url()
    if not ack_url or not AGENT_TOKEN:
        return False, "Ack skipped (missing URL/token)"

    identity = (pc_identity or AGENT_IDENTITY).strip() or AGENT_IDENTITY
    body = json.dumps({
        "pc_name": identity,
        "lan_ip": detect_local_lan_ip(),
        "command_id": command_id,
        "ok": bool(ok),
        "message": str(message or "")
    }).encode("utf-8")
    req = http_request.Request(
        ack_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Agent-Token": AGENT_TOKEN
        }
    )

    try:
        with http_request.urlopen(req, timeout=8):
            return True, "ok"
    except http_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        return False, f"HTTP {exc.code}: {detail}"
    except Exception as exc:
        return False, str(exc)


def command_poll_loop():
    while True:
        ok, message, payload = pull_command_from_server()
        if not ok:
            print(f"[LAN_AGENT] poll: fail - {message}")
            time.sleep(max(1, POLL_INTERVAL_SECONDS))
            continue

        if not isinstance(payload, dict) or payload.get("no_command", False):
            time.sleep(max(1, POLL_INTERVAL_SECONDS))
            continue

        command_id = payload.get("command_id")
        server_pc_name = str(payload.get("pc_name", "")).strip() or AGENT_IDENTITY
        command = str(payload.get("command", "")).strip().lower()
        exec_ok, exec_message = execute_allowed_command(command, payload.get("payload", {}))
        print(f"[LAN_AGENT] polled command #{command_id}: {command} -> {'ok' if exec_ok else 'fail'} ({exec_message})")

        ack_ok, ack_message = ack_command_to_server(command_id, exec_ok, exec_message, pc_identity=server_pc_name)
        if not ack_ok:
            print(f"[LAN_AGENT] ack fail for #{command_id}: {ack_message}")
        time.sleep(0.2)


def run_windows_command(command_args):
    try:
        subprocess.run(command_args, check=True)
        return True, "ok"
    except subprocess.CalledProcessError as exc:
        return False, f"Command failed: {exc}"
    except Exception as exc:
        return False, str(exc)


def request_user_approval(command, payload=None):
    payload_data = payload if isinstance(payload, dict) else {}
    reason = str(payload_data.get("reason", "")).strip()
    requested_by = str(payload_data.get("requested_by", "admin")).strip() or "admin"

    lines = [
        "Remote command request received.",
        f"Command: {command.upper()}",
        f"Requested by: {requested_by}"
    ]
    if reason:
        lines.append(f"Reason: {reason}")
    lines.append("")
    lines.append("Allow this action?")
    message = "\n".join(lines)

    # YESNO + ICONQUESTION + SYSTEMMODAL + TOPMOST
    flags = 0x00000004 | 0x00000020 | 0x00001000 | 0x00040000
    try:
        response = ctypes.windll.user32.MessageBoxW(0, message, "PyPondo Command Approval", flags)
    except Exception as exc:
        return False, f"Approval prompt failed: {exc}"

    if response == 6:
        return True, "User approved command"
    return False, "User rejected command"


def execute_allowed_command(command, payload=None):
    payload_data = payload if isinstance(payload, dict) else {}
    skip_approval = str(payload_data.get("skip_user_approval", "")).strip().lower() in {"1", "true", "yes"}

    if command == "connect_request":
        return True, "Auto-connect active"

    if REQUIRE_USER_APPROVAL and not skip_approval and command in APPROVAL_COMMANDS:
        approved, approval_message = request_user_approval(command, payload_data)
        if not approved:
            return False, approval_message
    if command == "lock":
        return run_windows_command(["rundll32.exe", "user32.dll,LockWorkStation"])
    if command == "restart":
        return run_windows_command(["shutdown", "/r", "/t", "0"])
    if command == "shutdown":
        return run_windows_command(["shutdown", "/s", "/t", "0"])
    if command == "wake":
        return True, "Wake acknowledged"
    return False, "Unsupported command"


@app.post("/agent/command")
def agent_command():
    if not AGENT_TOKEN:
        return jsonify({"ok": False, "message": "LAN_AGENT_TOKEN is not configured on agent"}), 500

    received_token = request.headers.get("X-Agent-Token", "")
    if received_token != AGENT_TOKEN:
        return jsonify({"ok": False, "message": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    command = str(data.get("command", "")).strip().lower()
    if command not in {"lock", "restart", "shutdown", "wake", "connect_request"}:
        return jsonify({"ok": False, "message": "Invalid command"}), 400

    ok, message = execute_allowed_command(command, data.get("payload", {}))
    return jsonify({"ok": ok, "message": message}), (200 if ok else 500)


@app.post("/agent/connect-web-request")
def agent_connect_web_request():
    return jsonify({"ok": False, "message": "Connection request flow disabled. Admin now auto-connects directly."}), 410


@app.get("/agent/connect-web-request/<int:command_id>")
def agent_connect_web_request_page(command_id):
    return "<h3>Connection request flow disabled. Admin now auto-connects directly.</h3>", 410


@app.post("/agent/connect-web-request/<int:command_id>/respond")
def agent_connect_web_request_respond(command_id):
    return "<h3>Connection request flow disabled. Admin now auto-connects directly.</h3>", 410


@app.get("/agent/info")
def agent_info():
    return jsonify({
        "ok": True,
        "pc_name": PC_NAME or socket.gethostname(),
        "lan_ip": detect_local_lan_ip(),
        "port": PORT
    }), 200


if __name__ == "__main__":
    if AGENT_TOKEN and get_register_url_candidates():
        threading.Thread(target=registration_loop, daemon=True).start()
    else:
        print("[LAN_AGENT] Auto-registration disabled. Set LAN_SERVER_REGISTER_URL or LAN_SERVER_HOST plus LAN_AGENT_TOKEN.")
    if get_poll_url() and get_ack_url() and AGENT_TOKEN:
        threading.Thread(target=command_poll_loop, daemon=True).start()
        print(f"[LAN_AGENT] Command polling enabled for {AGENT_IDENTITY} every {max(1, POLL_INTERVAL_SECONDS)}s")
    else:
        print("[LAN_AGENT] Command polling disabled. Set LAN_SERVER_BASE_URL or LAN_SERVER_COMMAND_POLL_URL/LAN_SERVER_COMMAND_ACK_URL with LAN_AGENT_TOKEN.")
    app.run(host=HOST, port=PORT, debug=False)
