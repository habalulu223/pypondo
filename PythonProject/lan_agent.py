import os
import socket
import subprocess
import threading
import time
import ctypes
from flask import Flask, request, jsonify
from urllib import request as http_request
from urllib import error as http_error
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
POLL_INTERVAL_SECONDS = int(os.getenv("LAN_POLL_INTERVAL_SECONDS", "3"))
AGENT_IDENTITY = PC_NAME or socket.gethostname()
REQUIRE_USER_APPROVAL = str(os.getenv("LAN_REQUIRE_USER_APPROVAL", "1")).strip().lower() in {"1", "true", "yes"}
APPROVAL_COMMANDS = {"lock", "restart", "shutdown"}


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


def register_with_server():
    if not REGISTER_URL or not PC_NAME or not AGENT_TOKEN:
        return False, "Registration skipped (missing LAN_SERVER_REGISTER_URL, LAN_PC_NAME, or LAN_AGENT_TOKEN)"

    lan_ip = detect_local_lan_ip()
    body = json.dumps({
        "pc_name": PC_NAME,
        "lan_ip": lan_ip,
        "agent_port": PORT
    }).encode("utf-8")

    req = http_request.Request(
        REGISTER_URL,
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
            return False, payload.get("error", "Registration failed")
    except http_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        return False, f"HTTP {exc.code}: {detail}"
    except Exception as exc:
        return False, str(exc)


def resolve_server_url(path):
    if SERVER_BASE_URL:
        return SERVER_BASE_URL.rstrip("/") + path
    if REGISTER_URL and "/api/agent/register-lan" in REGISTER_URL:
        return REGISTER_URL.split("/api/agent/register-lan", 1)[0] + path
    if REGISTER_URL and "/api/" in REGISTER_URL:
        return REGISTER_URL.split("/api/", 1)[0] + path
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
    if REQUIRE_USER_APPROVAL and command in APPROVAL_COMMANDS:
        approved, approval_message = request_user_approval(command, payload)
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
    if command not in {"lock", "restart", "shutdown", "wake"}:
        return jsonify({"ok": False, "message": "Invalid command"}), 400

    ok, message = execute_allowed_command(command, data.get("payload", {}))
    return jsonify({"ok": ok, "message": message}), (200 if ok else 500)


@app.get("/agent/info")
def agent_info():
    return jsonify({
        "ok": True,
        "pc_name": PC_NAME or socket.gethostname(),
        "lan_ip": detect_local_lan_ip(),
        "port": PORT
    }), 200


if __name__ == "__main__":
    if REGISTER_URL and PC_NAME and AGENT_TOKEN:
        threading.Thread(target=registration_loop, daemon=True).start()
    else:
        print("[LAN_AGENT] Auto-registration disabled. Set LAN_SERVER_REGISTER_URL, LAN_PC_NAME, and LAN_AGENT_TOKEN.")
    if get_poll_url() and get_ack_url() and AGENT_TOKEN:
        threading.Thread(target=command_poll_loop, daemon=True).start()
        print(f"[LAN_AGENT] Command polling enabled for {AGENT_IDENTITY} every {max(1, POLL_INTERVAL_SECONDS)}s")
    else:
        print("[LAN_AGENT] Command polling disabled. Set LAN_SERVER_BASE_URL or LAN_SERVER_COMMAND_POLL_URL/LAN_SERVER_COMMAND_ACK_URL with LAN_AGENT_TOKEN.")
    app.run(host=HOST, port=PORT, debug=False)
