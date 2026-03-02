import os
import sys
import socket
import threading
import time
import webbrowser
from urllib import request as http_request


APP_TITLE = "CyberCore"
APP_HOST = os.getenv("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"
APP_PORT = int(os.getenv("APP_PORT", "5000"))
APP_DATA_DIR_NAME = "CyberCore"


def is_frozen_bundle():
    return bool(getattr(sys, "frozen", False))


def get_runtime_base_dir():
    if is_frozen_bundle():
        return os.path.abspath(os.path.dirname(sys.executable))
    return os.path.abspath(os.path.dirname(__file__))


def get_default_data_dir():
    if is_frozen_bundle():
        local_app_data = os.getenv("LOCALAPPDATA", "").strip() or os.getenv("APPDATA", "").strip()
        if local_app_data:
            return os.path.join(local_app_data, APP_DATA_DIR_NAME)
    return os.path.join(get_runtime_base_dir(), "data")


def configure_default_data_dir():
    if os.getenv("PYPONDO_DB_PATH", "").strip() or os.getenv("PYPONDO_DATA_DIR", "").strip():
        return

    runtime_dir = get_runtime_base_dir()
    legacy_db = os.path.join(runtime_dir, "pccafe.db")
    if os.path.exists(legacy_db):
        os.environ["PYPONDO_DB_PATH"] = legacy_db
        return

    data_dir = get_default_data_dir()
    os.makedirs(data_dir, exist_ok=True)
    os.environ["PYPONDO_DATA_DIR"] = data_dir


configure_default_data_dir()

import app as server  # noqa: E402


def ensure_seed_data():
    with server.app.app_context():
        server.db.create_all()
        server.ensure_pc_lan_ip_column()
        server.ensure_booking_date_column()
        seeded = server.ensure_core_seed_data()
        if seeded:
            print("DB init complete: default admin + PCs created.")


def is_port_available(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def pick_port(preferred_port):
    if is_port_available(APP_HOST, preferred_port):
        return preferred_port
    for port in range(preferred_port + 1, preferred_port + 40):
        if is_port_available(APP_HOST, port):
            return port
    raise RuntimeError("No available local port for desktop app")


def wait_for_server(url, timeout_seconds=20):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with http_request.urlopen(url, timeout=1.5):
                return True
        except Exception:
            time.sleep(0.25)
    return False


def run_flask(host, port):
    server.app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


def launch_browser_control_window(url):
    import tkinter as tk
    from tkinter import ttk

    def open_in_browser():
        webbrowser.open(url)

    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("520x220")
    root.minsize(460, 200)

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="PyPondo is running.", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 8))
    ttk.Label(
        frame,
        text="The app opened in your default web browser. Keep this window open while using PyPondo."
    ).pack(anchor="w", pady=(0, 12))
    ttk.Label(frame, text=url, foreground="#1f5fbf").pack(anchor="w", pady=(0, 16))

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x")
    ttk.Button(button_row, text="Open App", command=open_in_browser).pack(side="left")
    ttk.Button(button_row, text="Exit", command=root.destroy).pack(side="right")

    open_in_browser()
    root.mainloop()


def launch_ui(url):
    try:
        import webview

        webview.create_window(APP_TITLE, url=url, width=1280, height=820, min_size=(980, 700))
        webview.start()
        return True
    except Exception as exc:
        print(f"pywebview not available, using browser mode instead: {exc}")

    try:
        launch_browser_control_window(url)
        return True
    except Exception as exc:
        print(f"Fallback UI failed: {exc}")
        print("Trying direct browser launch.")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return True


def main():
    ensure_seed_data()
    chosen_port = pick_port(APP_PORT)
    os.environ["APP_HOST"] = APP_HOST
    os.environ["APP_PORT"] = str(chosen_port)

    server_thread = threading.Thread(target=run_flask, args=(APP_HOST, chosen_port), daemon=True)
    server_thread.start()

    base_url = f"http://{APP_HOST}:{chosen_port}"
    if not wait_for_server(base_url):
        print(f"Failed to start local server at {base_url}")
        return 1

    headless_mode = str(os.getenv("PYPONDO_HEADLESS", "")).strip().lower() in {"1", "true", "yes"}
    if headless_mode:
        print(f"Server ready at {base_url}")
        return 0

    if not launch_ui(base_url):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
