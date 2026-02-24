import os
import subprocess
from flask import Flask, request, jsonify

app = Flask(__name__)

AGENT_TOKEN = os.getenv("LAN_AGENT_TOKEN", "").strip()
HOST = os.getenv("LAN_AGENT_HOST", "0.0.0.0")
PORT = int(os.getenv("LAN_AGENT_PORT", "5001"))


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


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False)
