import os
import socket
import subprocess
import threading
import time
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
                return True, f"Registered {payload.get('pc_name')} -> {payload.get('lan_ip')}"
            return False, payload.get("error", "Registration failed")
    except http_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        return False, f"HTTP {exc.code}: {detail}"
    except Exception as exc:
        return False, str(exc)


def registration_loop():
    while True:
        ok, message = register_with_server()
        print(f"[LAN_AGENT] register: {'ok' if ok else 'fail'} - {message}")
        if REGISTER_INTERVAL_SECONDS <= 0:
            break
        time.sleep(REGISTER_INTERVAL_SECONDS)


def run_windows_command(command_args):
    try:
        subprocess.run(command_args, check=True)
        return True, "ok"
    except subprocess.CalledProcessError as exc:
        return False, f"Command failed: {exc}"
    except Exception as exc:
        return False, str(exc)


def execute_allowed_command(command):
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

    ok, message = execute_allowed_command(command)
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
    app.run(host=HOST, port=PORT, debug=False)
