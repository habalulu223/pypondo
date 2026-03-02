import os
import socket
import threading
import time
from urllib import request as http_request


def configure_default_data_dir():
    if os.getenv("PYPONDO_DB_PATH", "").strip() or os.getenv("PYPONDO_DATA_DIR", "").strip():
        return
    base_dir = os.path.abspath(os.path.dirname(__file__))
    legacy_db = os.path.join(base_dir, "pccafe.db")
    if os.path.exists(legacy_db):
        os.environ["PYPONDO_DB_PATH"] = legacy_db
        return
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    os.environ["PYPONDO_DATA_DIR"] = data_dir


configure_default_data_dir()

import app as server  # noqa: E402


APP_TITLE = "PyPondo Desktop"
APP_HOST = os.getenv("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"
APP_PORT = int(os.getenv("APP_PORT", "5000"))


def ensure_seed_data():
    with server.app.app_context():
        server.db.create_all()
        created = False

        if server.PC.query.count() == 0:
            for i in range(1, 6):
                server.db.session.add(server.PC(name=f"PC-{i}"))
            created = True

        if not server.User.query.filter_by(username="admin").first():
            admin = server.User(username="admin", is_admin=True)
            admin.set_password("admin123")
            server.db.session.add(admin)
            created = True

        if created:
            server.db.session.commit()
            print("DB init complete: admin/admin123")


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


def launch_ui(url):
    try:
        import webview

        webview.create_window(APP_TITLE, url=url, width=1280, height=820, min_size=(980, 700))
        webview.start()
        return True
    except Exception as exc:
        print("App mode requires pywebview and a supported GUI backend.")
        print(f"Failed to start desktop window: {exc}")
        print("Install dependency with: pip install pywebview")
        return False


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

    if not launch_ui(base_url):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
