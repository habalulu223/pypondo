import os
import sys
import socket
import threading
import time
import webbrowser
import logging
import re
import subprocess
from urllib import request as http_request
from urllib import error as http_error
from urllib import parse as http_parse


APP_TITLE = "CyberCore"
APP_HOST = os.getenv("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"
APP_PORT = int(os.getenv("APP_PORT", "5000"))
APP_DATA_DIR_NAME = "CyberCore"
APP_MODE = (os.getenv("PYPONDO_APP_MODE", "client").strip().lower() or "client")
SERVER_HOST_FILE = os.getenv("PYPONDO_SERVER_HOST_FILE", "server_host.txt").strip() or "server_host.txt"
STARTUP_VALUE_NAME = os.getenv("PYPONDO_STARTUP_VALUE_NAME", "CyberCoreClient").strip() or "CyberCoreClient"


def hidden_subprocess_kwargs():
    """Return kwargs to hide subprocess windows on Windows."""
    if os.name != "nt":
        return {}

    kwargs = {}
    create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if create_no_window:
        kwargs["creationflags"] = create_no_window

    startupinfo_type = getattr(subprocess, "STARTUPINFO", None)
    startf_use_showwindow = getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
    sw_hide = getattr(subprocess, "SW_HIDE", 0)
    if startupinfo_type and startf_use_showwindow:
        startupinfo = startupinfo_type()
        startupinfo.dwFlags |= startf_use_showwindow
        startupinfo.wShowWindow = sw_hide
        kwargs["startupinfo"] = startupinfo

    return kwargs


def is_verbose_logging_enabled():
    return str(os.getenv("PYPONDO_VERBOSE", "")).strip().lower() in {"1", "true", "yes"}


def env_flag(name, default=False):
    raw = os.getenv(name, "")
    if not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def is_client_mode():
    return APP_MODE in {"client", "kiosk"}


def is_client_app_mode():
    return APP_MODE == "client"


def kiosk_lock_enabled():
    if env_flag("PYPONDO_ALLOW_EXIT", default=False):
        return False
    return env_flag("PYPONDO_KIOSK_MODE", default=is_client_mode())


def get_start_path():
    custom_path = os.getenv("PYPONDO_START_PATH", "").strip()
    if custom_path:
        if not custom_path.startswith("/"):
            custom_path = "/" + custom_path
        return custom_path
    if is_client_mode():
        return "/client"
    return "/"


def split_host_candidates(raw_value):
    values = []
    for part in str(raw_value or "").replace(";", ",").split(","):
        candidate = part.strip()
        if candidate:
            values.append(candidate)
    return values


def get_preferred_server_ports():
    ports = []
    for value in (os.getenv("PYPONDO_SERVER_PORT", "").strip(), os.getenv("APP_PORT", "").strip(), "5000"):
        try:
            parsed_port = int(value)
        except Exception:
            continue
        if parsed_port not in ports:
            ports.append(parsed_port)
    return ports


def looks_like_ip_literal(host_value):
    raw = str(host_value or "").strip()
    if not raw:
        return False
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    raw = raw.split("%", 1)[0]
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            socket.inet_pton(family, raw)
            return True
        except OSError:
            continue
    return False


def read_host_candidates_from_file():
    file_path = os.path.join(get_runtime_base_dir(), SERVER_HOST_FILE)
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


def save_manual_admin_host(host_value):
    host = str(host_value or "").strip()
    if not host:
        return False
    file_path = os.path.join(get_runtime_base_dir(), SERVER_HOST_FILE)
    try:
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write("# Admin server host or IP\n")
            handle.write(host + "\n")
        return True
    except Exception:
        return False


def prompt_manual_admin_host(headless_mode=False):
    preset = os.getenv("PYPONDO_ADMIN_IP", "").strip() or os.getenv("PYPONDO_SERVER_HOST", "").strip()
    if headless_mode:
        if preset:
            return preset
        try:
            value = input("Enter admin server IP/host: ").strip()
            return value or None
        except Exception:
            return None

    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()
        value = simpledialog.askstring(
            "Admin Server",
            "Enter admin server IP or hostname:",
            initialvalue=preset or ""
        )
        root.destroy()
        if value and value.strip():
            return value.strip()
    except Exception:
        pass
    return None


def discover_hosts_from_net_view():
    if os.name != "nt":
        return []
    try:
        output = subprocess.check_output(
            ["net", "view"],
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=4,
            **hidden_subprocess_kwargs()
        )
    except Exception:
        return []

    found = []
    for raw_line in output.splitlines():
        match = re.match(r"^\s*\\\\([^\\\s]+)", raw_line)
        if not match:
            continue
        host_name = match.group(1).strip()
        if host_name:
            found.append(host_name)
    return found


def discover_default_gateway_ips():
    """Extract default gateway IPs from ipconfig output on Windows."""
    if os.name != "nt":
        return []
    
    try:
        output = subprocess.check_output(
            ["ipconfig"],
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=4,
            **hidden_subprocess_kwargs()
        )
    except Exception:
        return []
    
    gateways = []
    for line in output.splitlines():
        if "Default Gateway" not in line:
            continue
        _, _, remainder = line.partition(":")
        for ip_str in remainder.split():
            parts = ip_str.strip().split(".")
            if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                if ip_str not in gateways:
                    gateways.append(ip_str)
    
    return gateways


def discover_local_network_ips():
    """Extract all IPv4 addresses from ipconfig output on Windows."""
    if os.name != "nt":
        return []
    
    try:
        output = subprocess.check_output(
            ["ipconfig"],
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=4,
            **hidden_subprocess_kwargs()
        )
    except Exception:
        return []
    
    local_ips = []
    for line in output.splitlines():
        if "IPv4 Address" not in line or "Gateway" in line:
            continue
        _, _, remainder = line.partition(":")
        ip_str = remainder.strip()
        parts = ip_str.strip().split(".")
        if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
            if ip_str not in local_ips and not ip_str.startswith("127."):
                local_ips.append(ip_str)
    
    return local_ips


def extract_base_url(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    parsed = http_parse.urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def build_base_urls_from_host_value(host_value):
    raw = str(host_value or "").strip()
    if not raw:
        return []

    direct_url = extract_base_url(raw)
    if direct_url:
        parsed = http_parse.urlparse(direct_url)
        if parsed.port:
            return [direct_url]
        # If user enters scheme without port, still probe configured server ports.
        host_name = parsed.hostname or ""
        if not host_name:
            return [direct_url]
        scheme = parsed.scheme or (os.getenv("PYPONDO_SERVER_SCHEME", "http").strip() or "http")
        return [f"{scheme}://{host_name}:{port}" for port in get_preferred_server_ports()]

    scheme = os.getenv("PYPONDO_SERVER_SCHEME", "http").strip() or "http"
    return [f"{scheme}://{raw}:{port}" for port in get_preferred_server_ports()]


def get_manual_host_candidates():
    values = []
    for env_name in ("PYPONDO_ADMIN_IP", "PYPONDO_SERVER_HOST"):
        values.extend(split_host_candidates(os.getenv(env_name, "")))

    file_values = read_host_candidates_from_file()
    if file_values:
        values.extend(file_values)

    seen = set()
    ordered = []
    for value in values:
        key = str(value).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(str(value).strip())
    return ordered


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


def discover_server_ip_from_admin(base_url):
    """Request admin server IP from the admin server's public API."""
    if not base_url:
        return None
    
    try:
        info_url = base_url.rstrip("/") + "/api/server-info"
        with http_request.urlopen(info_url, timeout=2) as response:
            import json as json_module
            data = json_module.loads(response.read().decode("utf-8"))
            if data.get("ok") and data.get("server_ip"):
                return data.get("server_ip")
    except Exception:
        return None
    
    return None


def build_server_base_url_candidates():
    explicit_candidates = []
    for env_name in ("PYPONDO_SERVER_BASE_URL", "LAN_SERVER_BASE_URL"):
        value = os.getenv(env_name, "").strip()
        if not value:
            continue
        normalized = extract_base_url(value)
        if normalized:
            explicit_candidates.append(normalized)

    host_candidates = []
    for env_name in ("PYPONDO_SERVER_HOST", "LAN_SERVER_HOST", "PYPONDO_SERVER_HOSTS", "PYPONDO_SERVER_HOST_CANDIDATES"):
        host_candidates.extend(split_host_candidates(os.getenv(env_name, "")))

    host_candidates.extend(read_host_candidates_from_file())

    app_host = os.getenv("APP_HOST", "").strip()
    if app_host and app_host not in {"127.0.0.1", "0.0.0.0", "localhost"}:
        host_candidates.append(app_host)

    for env_name in ("LAN_SERVER_REGISTER_URL",):
        url_value = os.getenv(env_name, "").strip()
        normalized = extract_base_url(url_value)
        if normalized:
            explicit_candidates.append(normalized)
            parsed = http_parse.urlparse(normalized)
            if parsed.hostname:
                host_candidates.append(parsed.hostname)

    host_candidates.extend(discover_hosts_from_net_view())
    # DISABLED: Skip gateway IP discovery - prevents 192.168.x.x connection attempts
    # host_candidates.extend(discover_default_gateway_ips())
    host_candidates.extend(discover_local_network_ips())

    # ALWAYS prioritize localhost first for same-machine admin
    if "127.0.0.1" not in host_candidates and "localhost" not in host_candidates:
        host_candidates.insert(0, "127.0.0.1")

    seen = set()
    unique_hosts = []
    for host in host_candidates:
        raw_host = str(host).strip()
        if not raw_host:
            continue
        key = raw_host.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_hosts.append(raw_host)

    scheme = os.getenv("PYPONDO_SERVER_SCHEME", "http").strip() or "http"
    port_values = []
    for value in (os.getenv("PYPONDO_SERVER_PORT", "").strip(), os.getenv("APP_PORT", "").strip(), "5000"):
        try:
            parsed_port = int(value)
        except Exception:
            continue
        if parsed_port not in port_values:
            port_values.append(parsed_port)

    discovered_candidates = []
    for host in unique_hosts:
        host_value = host
        if "://" in host_value:
            normalized = extract_base_url(host_value)
            if normalized:
                discovered_candidates.append(normalized)
            continue
        for port in port_values:
            discovered_candidates.append(f"{scheme}://{host_value}:{port}")

    preferred = []
    fallback = []
    for candidate in explicit_candidates + discovered_candidates:
        parsed = http_parse.urlparse(candidate)
        host_name = parsed.hostname or ""
        if looks_like_ip_literal(host_name):
            fallback.append(candidate.rstrip("/"))
        else:
            preferred.append(candidate.rstrip("/"))

    ordered = []
    seen_urls = set()
    for candidate in preferred + fallback:
        key = candidate.lower()
        if key in seen_urls:
            continue
        seen_urls.add(key)
        ordered.append(candidate)
    return ordered


def discover_remote_server_base_url():
    candidates = []

    manual_host = os.getenv("PYPONDO_ADMIN_IP", "").strip()
    if manual_host:
        os.environ["PYPONDO_SERVER_HOST"] = manual_host

    # Always probe manually configured host(s) first so client obeys explicit admin IP.
    manual_candidates = []
    for manual_value in get_manual_host_candidates():
        for candidate in build_base_urls_from_host_value(manual_value):
            if candidate not in manual_candidates:
                manual_candidates.append(candidate)

    for candidate in manual_candidates:
        if probe_server_base_url(candidate):
            return candidate.rstrip("/")

    # When manual host is configured but unreachable, do not auto-switch to random LAN hosts.
    if manual_candidates:
        return None

    for candidate in build_server_base_url_candidates():
        if candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        if probe_server_base_url(candidate):
            return candidate.rstrip("/")

    return None


CLIENT_AGENT_STARTED = False


def start_client_agent_background(server_base_url):
    global CLIENT_AGENT_STARTED
    if CLIENT_AGENT_STARTED:
        return True

    base_url = str(server_base_url or "").rstrip("/")
    if not base_url:
        return False

    os.environ.setdefault("LAN_SERVER_BASE_URL", base_url)
    os.environ.setdefault("LAN_SERVER_REGISTER_URL", base_url + "/api/agent/register-lan")
    os.environ.setdefault("LAN_SERVER_COMMAND_POLL_URL", base_url + "/api/agent/pull-command")
    os.environ.setdefault("LAN_SERVER_COMMAND_ACK_URL", base_url + "/api/agent/ack-command")
    os.environ.setdefault("LAN_PC_NAME", socket.gethostname())
    os.environ.setdefault("LAN_AGENT_HOST", "0.0.0.0")
    os.environ.setdefault("LAN_AGENT_PORT", os.getenv("LAN_AGENT_PORT", "5001"))

    try:
        import lan_agent as client_agent
    except Exception as exc:
        if is_verbose_logging_enabled():
            print(f"Client LAN agent import failed: {exc}")
        return False

    if client_agent.REGISTER_URL and client_agent.AGENT_TOKEN:
        threading.Thread(target=client_agent.registration_loop, daemon=True).start()
    if client_agent.get_poll_url() and client_agent.get_ack_url() and client_agent.AGENT_TOKEN:
        threading.Thread(target=client_agent.command_poll_loop, daemon=True).start()

    if env_flag("PYPONDO_CLIENT_AGENT_ENABLE_HTTP", default=False):
        def run_agent_http():
            logging.getLogger("werkzeug").setLevel(logging.ERROR)
            client_agent.app.run(host=client_agent.HOST, port=client_agent.PORT, debug=False, use_reloader=False, threaded=True)

        threading.Thread(target=run_agent_http, daemon=True).start()

    CLIENT_AGENT_STARTED = True
    return True


def is_frozen_bundle():
    return bool(getattr(sys, "frozen", False))


def get_runtime_base_dir():
    if is_frozen_bundle():
        return os.path.abspath(os.path.dirname(sys.executable))
    return os.path.abspath(os.path.dirname(__file__))


def get_windows_startup_command():
    if is_frozen_bundle():
        return f'"{sys.executable}"'

    pythonw_path = sys.executable
    lower_exec = pythonw_path.lower()
    if lower_exec.endswith("python.exe"):
        pythonw_candidate = pythonw_path[:-10] + "pythonw.exe"
        if os.path.exists(pythonw_candidate):
            pythonw_path = pythonw_candidate

    script_path = os.path.abspath(__file__)
    return f'"{pythonw_path}" "{script_path}"'


def ensure_windows_startup_registration():
    if os.name != "nt" or not is_client_mode():
        return
    if env_flag("PYPONDO_DISABLE_AUTO_STARTUP", default=False):
        return

    try:
        command = get_windows_startup_command()
        reg_query = subprocess.run(
            [
                "reg",
                "query",
                r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
                "/v",
                STARTUP_VALUE_NAME,
            ],
            text=True,
            encoding="utf-8",
            errors="ignore",
            capture_output=True,
            check=False,
            **hidden_subprocess_kwargs(),
        )

        already_set = reg_query.returncode == 0 and command in (reg_query.stdout or "")
        if already_set:
            return

        subprocess.run(
            [
                "reg",
                "add",
                r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
                "/v",
                STARTUP_VALUE_NAME,
                "/t",
                "REG_SZ",
                "/d",
                command,
                "/f",
            ],
            text=True,
            encoding="utf-8",
            errors="ignore",
            capture_output=True,
            check=False,
            **hidden_subprocess_kwargs(),
        )
    except Exception:
        return


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


def configure_runtime_defaults():
    if not os.getenv("PYPONDO_KIOSK_MODE", "").strip():
        os.environ["PYPONDO_KIOSK_MODE"] = "1" if is_client_mode() else "0"


configure_default_data_dir()
configure_runtime_defaults()

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
    try:
        import flask.cli
        flask.cli.show_server_banner = lambda *args, **kwargs: None
    except Exception:
        pass
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    server.app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


def launch_browser_control_window(url):
    import tkinter as tk
    from tkinter import ttk

    def open_in_browser():
        webbrowser.open(url)

    root = tk.Tk()
    root.title(APP_TITLE)

    # Only the standard client app is forced fullscreen and borderless.
    if is_client_app_mode():
        root.overrideredirect(True)
        try:
            root.attributes("-fullscreen", True)
        except Exception:
            screen_w = root.winfo_screenwidth()
            screen_h = root.winfo_screenheight()
            root.geometry(f"{screen_w}x{screen_h}+0+0")
    else:
        root.geometry("520x220")
        root.minsize(460, 200)

    if kiosk_lock_enabled():
        root.protocol("WM_DELETE_WINDOW", lambda: None)
        root.bind("<Alt-F4>", lambda event: "break")
        root.bind("<Control-w>", lambda event: "break")

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)

    title_text = "PyPondo is running."
    if kiosk_lock_enabled():
        title_text = "PyPondo client kiosk is locked."
    ttk.Label(frame, text=title_text, font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 8))
    ttk.Label(
        frame,
        text="Login is required before desktop access is unlocked."
    ).pack(anchor="w", pady=(0, 12))
    ttk.Label(frame, text=url, foreground="#1f5fbf").pack(anchor="w", pady=(0, 16))

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x")
    ttk.Button(button_row, text="Open App", command=open_in_browser).pack(side="left")
    if not kiosk_lock_enabled():
        ttk.Button(button_row, text="Exit", command=root.destroy).pack(side="right")

    open_in_browser()
    root.mainloop()


def launch_ui(url):
    try:
        import webview  # type: ignore

        try:
            window = webview.create_window(
                APP_TITLE,
                url=url,
                width=1280,
                height=820,
                min_size=(980, 700),
                resizable=not is_client_mode(),
                frameless=is_client_app_mode(),
                fullscreen=is_client_app_mode(),
                easy_drag=False
            )
            if kiosk_lock_enabled():
                def prevent_close():
                    return True

                try:
                    window.events.closing += prevent_close
                except Exception:
                    pass
            webview.start()
            return True
        except Exception as exc:
            if is_verbose_logging_enabled():
                print(f"pywebview failed, falling back to browser mode: {exc}")
    except Exception as exc:
        if is_verbose_logging_enabled():
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
    headless_mode = str(os.getenv("PYPONDO_HEADLESS", "")).strip().lower() in {"1", "true", "yes"}

    ensure_windows_startup_registration()

    if is_client_mode() and not env_flag("PYPONDO_FORCE_LOCAL_SERVER", default=False):
        if is_verbose_logging_enabled():
            print("[INFO] Client mode: searching for remote admin server...")
        remote_base_url = discover_remote_server_base_url()
        if not remote_base_url:
            manual_host = prompt_manual_admin_host(headless_mode=headless_mode)
            if manual_host:
                os.environ["PYPONDO_SERVER_HOST"] = manual_host
                os.environ["PYPONDO_ADMIN_IP"] = manual_host
                save_manual_admin_host(manual_host)
                remote_base_url = discover_remote_server_base_url()
        if remote_base_url:
            launch_url = f"{remote_base_url}{get_start_path()}"
            if is_verbose_logging_enabled():
                print(f"[INFO] Connected to admin server: {remote_base_url}")
            start_client_agent_background(remote_base_url)
            if headless_mode:
                print(f"Server ready at {launch_url}")
                return 0

            if kiosk_lock_enabled():
                while True:
                    if not launch_ui(launch_url):
                        return 1
                    time.sleep(0.3)
            else:
                if not launch_ui(launch_url):
                    return 1
            return 0

        # Could not find remote server - ALWAYS allow local fallback for App Independence
        if is_verbose_logging_enabled():
            print("[WARNING] Could not locate admin server, starting local server")
        # Continue to local server mode (below)

    # Local server mode (standalone or fallback)
    ensure_seed_data()
    chosen_port = pick_port(APP_PORT)
    os.environ["APP_HOST"] = APP_HOST
    os.environ["APP_PORT"] = str(chosen_port)

    server_thread = threading.Thread(target=run_flask, args=(APP_HOST, chosen_port), daemon=True)
    server_thread.start()

    base_url = f"http://{APP_HOST}:{chosen_port}"
    launch_url = f"{base_url}{get_start_path()}"
    if not wait_for_server(base_url):
        print(f"Failed to start local server at {base_url}")
        return 1

    if headless_mode:
        print(f"Server ready at {launch_url}")
        return 0

    if kiosk_lock_enabled():
        while True:
            if not launch_ui(launch_url):
                return 1
            time.sleep(0.3)
    else:
        if not launch_ui(launch_url):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())