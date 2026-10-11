import os
import sys
import socket
import threading
import time
import logging
import re
import subprocess
from urllib import request as http_request
from urllib import error as http_error
from urllib import parse as http_parse

APP_TITLE = "PyPondo"
APP_HOST = os.getenv("APP_HOST", "0.0.0.0").strip() or "0.0.0.0"
APP_PORT = int(os.getenv("APP_PORT", "5000"))
APP_DATA_DIR_NAME = "CyberCore"
APP_MODE = (os.getenv("PYPONDO_APP_MODE", "client").strip().lower() or "client")
if APP_MODE == "kiosk":
    APP_MODE = "client"
SERVER_HOST_FILE = os.getenv("PYPONDO_SERVER_HOST_FILE", "server_host.txt").strip() or "server_host.txt"


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
    return APP_MODE == "client"


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
    values = []
    seen_paths = set()

    for file_path in get_server_host_candidate_paths():
        normalized_path = os.path.normcase(os.path.abspath(file_path))
        if normalized_path in seen_paths or not os.path.exists(file_path):
            continue
        seen_paths.add(normalized_path)

        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    values.extend(split_host_candidates(line))
        except Exception:
            continue

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
    return preset or None


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
    # Prefer the explicit health endpoint so the desktop client can verify
    # that the updated PyPondo server is ready before opening its UI. Keep the
    # legacy routes as fallbacks for older installations.
    for path in ("/api/health", "/login", "/api/agent/register-lan"):
        target = root + path
        try:
            with http_request.urlopen(target, timeout=1.2):
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


def is_private_ipv4(host_value):
    parts = str(host_value or "").strip().split(".")
    if len(parts) != 4:
        return False
    try:
        octets = [int(part) for part in parts]
    except ValueError:
        return False
    if any(octet < 0 or octet > 255 for octet in octets):
        return False
    return (
        octets[0] == 10
        or (octets[0] == 172 and 16 <= octets[1] <= 31)
        or (octets[0] == 192 and octets[1] == 168)
    )


def discover_arp_neighbor_ips():
    if os.name != "nt":
        return []

    try:
        output = subprocess.check_output(
            ["arp", "-a"],
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=4,
            **hidden_subprocess_kwargs()
        )
    except Exception:
        return []

    found = []
    for match in re.finditer(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", output):
        ip_value = match.group(0)
        if ip_value.startswith(("127.", "169.254.", "224.", "239.", "255.")):
            continue
        if is_private_ipv4(ip_value) and ip_value not in found:
            found.append(ip_value)
    return found


def build_nearby_subnet_hosts(local_ips):
    hosts = []
    common_suffixes = (1, 2, 10, 20, 50, 100, 101, 102, 103, 104, 105, 110, 150, 200, 254)

    for local_ip in local_ips:
        parts = str(local_ip or "").strip().split(".")
        if len(parts) != 4:
            continue
        try:
            host_octet = int(parts[3])
        except ValueError:
            continue

        prefix = ".".join(parts[:3])
        nearby_suffixes = range(max(1, host_octet - 8), min(254, host_octet + 8) + 1)
        for suffix in list(nearby_suffixes) + list(common_suffixes):
            if suffix == host_octet:
                continue
            candidate = f"{prefix}.{suffix}"
            if candidate not in hosts:
                hosts.append(candidate)

    return hosts


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
    local_network_ips = discover_local_network_ips()
    host_candidates.extend(local_network_ips)
    host_candidates.extend(discover_arp_neighbor_ips())
    host_candidates.extend(build_nearby_subnet_hosts(local_network_ips))

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


def get_runtime_resource_dir():
    if is_frozen_bundle() and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.abspath(os.path.dirname(__file__))


def get_server_host_candidate_paths():
    primary_path = os.path.join(get_runtime_base_dir(), SERVER_HOST_FILE)
    resource_path = os.path.join(get_runtime_resource_dir(), SERVER_HOST_FILE)

    paths = [primary_path]
    if os.path.normcase(os.path.abspath(resource_path)) != os.path.normcase(os.path.abspath(primary_path)):
        paths.append(resource_path)
    return paths


def get_default_data_dir():
    if is_frozen_bundle():
        local_app_data = os.getenv("LOCALAPPDATA", "").strip() or os.getenv("APPDATA", "").strip()
        if local_app_data:
            return os.path.join(local_app_data, APP_DATA_DIR_NAME)
    return os.path.join(get_runtime_base_dir(), "data")


def configure_default_data_dir():
    if not is_frozen_bundle():
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
        return

    runtime_dir = get_runtime_base_dir()
    data_dir = get_default_data_dir()
    os.makedirs(data_dir, exist_ok=True)
    source_project_dir = os.path.dirname(runtime_dir)
    running_from_project_dist = os.path.isfile(os.path.join(source_project_dir, "desktop_app.py"))

    if not os.getenv("PYPONDO_DB_PATH", "").strip():
        explicit_data_dir = os.getenv("PYPONDO_DATA_DIR", "").strip()
        database_candidates = [
            os.path.join(runtime_dir, "pccafe.db"),
            os.path.join(os.path.dirname(runtime_dir), "pccafe.db"),
        ]
        if running_from_project_dist:
            database_candidates.insert(0, os.path.join(source_project_dir, "pccafe.db"))
        if explicit_data_dir:
            database_candidates.insert(0, os.path.join(os.path.abspath(explicit_data_dir), "pccafe.db"))

        existing_database = next((path for path in database_candidates if os.path.isfile(path)), None)
        os.environ["PYPONDO_DB_PATH"] = existing_database or os.path.join(
            os.path.abspath(explicit_data_dir) if explicit_data_dir else data_dir, "pccafe.db"
        )

    if not os.getenv("PYPONDO_COMMUNITY_DB_PATH", "").strip():
        community_candidates = [
            os.path.join(runtime_dir, "community_equipment.db"),
            os.path.join(os.path.dirname(runtime_dir), "community_equipment.db"),
        ]
        if running_from_project_dist:
            community_candidates.insert(0, os.path.join(source_project_dir, "community_equipment.db"))
        existing_community_db = next((path for path in community_candidates if os.path.isfile(path)), None)
        os.environ["PYPONDO_COMMUNITY_DB_PATH"] = existing_community_db or os.path.join(
            os.path.abspath(os.getenv("PYPONDO_DATA_DIR", "").strip()) or data_dir,
            "community_equipment.db",
        )

    seed_dir = os.path.join(get_runtime_resource_dir(), "database-seed")
    seed_targets = (
        ("main", os.getenv("PYPONDO_DB_PATH", "").strip(), ("pccafe.db",)),
        ("community", os.getenv("PYPONDO_COMMUNITY_DB_PATH", "").strip(),
         ("community_equipment.db", "sample.db")),
    )
    for seed_name, target_path, legacy_names in seed_targets:
        source_dir = os.path.join(seed_dir, seed_name)
        source_candidates = [
            os.path.join(source_dir, name)
            for name in sorted(os.listdir(source_dir))
            if name.lower().endswith(".db") and os.path.isfile(os.path.join(source_dir, name))
        ] if os.path.isdir(source_dir) else []
        source_candidates.extend(os.path.join(seed_dir, name) for name in legacy_names)
        source_path = next((path for path in source_candidates if os.path.isfile(path)), "")
        if target_path and not os.path.exists(target_path) and os.path.isfile(source_path):
            os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
            shutil.copy2(source_path, target_path)


def configure_runtime_defaults():
    os.environ["PYPONDO_KIOSK_MODE"] = "0"


configure_default_data_dir()
configure_runtime_defaults()

import app as server  # noqa: E402


def ensure_seed_data():
    with server.app.app_context():
        server.initialize_database()


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


def normalize_timer_started_at(raw_value):
    default_value = int(time.time() * 1000)
    try:
        return max(int(float(str(raw_value).strip())), 0)
    except Exception:
        return default_value


def get_timer_launch_command(started_at_ms):
    started_at_ms = str(normalize_timer_started_at(started_at_ms))
    if is_frozen_bundle():
        return [sys.executable, "--timer-window", started_at_ms]

    pythonw_path = sys.executable
    lower_exec = pythonw_path.lower()
    if lower_exec.endswith("python.exe"):
        pythonw_candidate = pythonw_path[:-10] + "pythonw.exe"
        if os.path.exists(pythonw_candidate):
            pythonw_path = pythonw_candidate

    return [pythonw_path, os.path.abspath(__file__), "--timer-window", started_at_ms]


def run_timer_window(started_at_ms=None):
    import tkinter as tk

    started_at_ms = normalize_timer_started_at(started_at_ms)
    timer_rate = float(getattr(server, "HOURLY_RATE", 15.0))

    timer_window = tk.Tk()
    timer_window.title("PyPondo Timer")
    timer_window.geometry("320x160")
    timer_window.resizable(False, False)
    timer_window.configure(bg="black")
    timer_window.overrideredirect(True)
    timer_window.protocol("WM_DELETE_WINDOW", lambda: None)

    try:
        timer_window.attributes("-topmost", True)
    except Exception:
        pass

    def set_alpha(alpha_value):
        try:
            timer_window.attributes("-alpha", alpha_value)
        except Exception:
            pass

    time_label = tk.Label(
        timer_window,
        text="00:00:00",
        font=("Arial", 18, "bold"),
        fg="cyan",
        bg="black"
    )
    time_label.pack(pady=(16, 8))

    cost_label = tk.Label(
        timer_window,
        text="Cost: PHP 0.00",
        font=("Arial", 11),
        fg="yellow",
        bg="black"
    )
    cost_label.pack(pady=4)

    status_label = tk.Label(
        timer_window,
        text="Drag to move. Click to close the timer.",
        font=("Arial", 8),
        fg="white",
        bg="black"
    )
    status_label.pack(pady=(6, 10))

    drag_state = {"offset_x": 0, "offset_y": 0, "moved": False}

    def update_timer():
        elapsed_seconds = max((time.time() * 1000 - started_at_ms) / 1000.0, 0.0)
        hours = int(elapsed_seconds // 3600)
        minutes = int((elapsed_seconds % 3600) // 60)
        seconds = int(elapsed_seconds % 60)
        time_label.config(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        cost_label.config(text=f"Cost: PHP {(elapsed_seconds / 3600.0) * timer_rate:.2f}")
        timer_window.after(1000, update_timer)

    def start_drag(event):
        set_alpha(1.0)
        drag_state["offset_x"] = event.x_root - timer_window.winfo_x()
        drag_state["offset_y"] = event.y_root - timer_window.winfo_y()
        drag_state["moved"] = False

    def do_drag(event):
        next_x = event.x_root - drag_state["offset_x"]
        next_y = event.y_root - drag_state["offset_y"]
        if abs(next_x - timer_window.winfo_x()) > 2 or abs(next_y - timer_window.winfo_y()) > 2:
            drag_state["moved"] = True
        timer_window.geometry(f"+{next_x}+{next_y}")

    def stop_drag(_event):
        if not drag_state["moved"]:
            timer_window.destroy()
            return
        drag_state["moved"] = False

    def on_enter(_event):
        set_alpha(1.0)

    def on_leave(_event):
        set_alpha(0.4)

    for widget in (timer_window, time_label, cost_label, status_label):
        widget.bind("<Button-1>", start_drag)
        widget.bind("<B1-Motion>", do_drag)
        widget.bind("<ButtonRelease-1>", stop_drag)
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    timer_window.update_idletasks()
    screen_width = timer_window.winfo_screenwidth()
    screen_height = timer_window.winfo_screenheight()
    window_width = timer_window.winfo_width() or 320
    window_height = timer_window.winfo_height() or 160
    timer_window.geometry(f"+{screen_width - window_width - 20}+{screen_height - window_height - 50}")
    set_alpha(1.0)
    update_timer()
    timer_window.mainloop()


def launch_ui(url):
    ui_error = "pywebview is not installed."
    try:
        import webview  # type: ignore

        timer_process = None
        timer_process_lock = threading.Lock()
        window_obj = None

        def start_timer_window(started_at=None):
            nonlocal timer_process

            with timer_process_lock:
                if timer_process is not None and timer_process.poll() is None:
                    return True
                try:
                    timer_process = subprocess.Popen(
                        get_timer_launch_command(started_at),
                        cwd=get_runtime_base_dir()
                    )
                    return True
                except Exception as exc:
                    if is_verbose_logging_enabled():
                        print(f"Failed to start timer: {exc}")
                    timer_process = None
                    return False

        def stop_timer_window():
            nonlocal timer_process

            with timer_process_lock:
                if timer_process is None:
                    return True
                try:
                    if timer_process.poll() is None:
                        timer_process.terminate()
                        try:
                            timer_process.wait(timeout=2)
                        except Exception:
                            timer_process.kill()
                except Exception:
                    pass
                timer_process = None
                return True

        try:
            class Api:
                def minimize(self):
                    try:
                        if window_obj is not None:
                            window_obj.minimize()
                        elif webview.windows:
                            webview.windows[0].minimize()
                        return True
                    except Exception:
                        return False
                    
                def start_timer(self, started_at=None):
                    try:
                        return start_timer_window(started_at)
                    except Exception:
                        return False

                def stop_timer(self):
                    return stop_timer_window()
                
                def terminate(self, secret_key):
                    # Secret key to terminate the client app
                    if secret_key == "PYPONDO_TERMINATE_2026":
                        try:
                            stop_timer_window()
                        except Exception:
                            pass
                        try:
                            webview.windows[0].destroy()
                            return True
                        except Exception:
                            pass
                    return False

            window = webview.create_window(
                APP_TITLE,
                url=url,
                width=1280,
                height=820,
                min_size=(800, 600),
                resizable=True,
                frameless=False,
                fullscreen=False,
                easy_drag=False,
                js_api=Api()
            )
            window_obj = window
            webview.start()
            stop_timer_window()
            return True
        except Exception as exc:
            ui_error = str(exc)
            if is_verbose_logging_enabled():
                print(f"pywebview window failed: {exc}")
    except Exception as exc:
        ui_error = str(exc)
        if is_verbose_logging_enabled():
            print(f"pywebview is not available: {exc}")

    message = (
        "PyPondo could not open its built-in desktop window. "
        "Install the WebView2 Runtime and rebuild/reinstall the desktop app.\n\n"
        f"Details: {ui_error}"
    )
    if is_verbose_logging_enabled():
        print(message)
    try:
        import tkinter as tk
        from tkinter import messagebox

        dialog = tk.Tk()
        dialog.withdraw()
        messagebox.showerror("PyPondo desktop window unavailable", message, parent=dialog)
        dialog.destroy()
    except Exception:
        pass
    return False


def show_remote_server_required_message(headless=False):
    message = (
        "The PyPondo server is not running or cannot be reached. "
        "Start the server on the same network, then open PyPondo Online again."
    )
    print(message)
    if headless:
        return
    try:
        import tkinter as tk
        from tkinter import messagebox

        dialog = tk.Tk()
        dialog.withdraw()
        messagebox.showwarning("PyPondo server required", message, parent=dialog)
        dialog.destroy()
    except Exception:
        pass


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--timer-window":
        run_timer_window(argv[1] if len(argv) > 1 else None)
        return 0

    # Check for independence mode (configure IP without server validation)
    if argv and argv[0] in ("--independence", "--configure-ip", "--setup"):
        print("PyPondo Auto Setup - Detect Admin Server")
        print("=" * 55)
        detected_base_url = discover_remote_server_base_url()
        detected_host = None
        if detected_base_url:
            parsed_detected_url = http_parse.urlparse(detected_base_url)
            detected_host = parsed_detected_url.hostname or detected_base_url
        else:
            detected_host = prompt_manual_admin_host(headless_mode=True)

        if detected_host:
            if save_manual_admin_host(detected_host):
                print(f"[OK] Saved admin server '{detected_host}' to server_host.txt")
                print("You can now run the client normally to connect to this server.")
                print(f"Run: python desktop_app.py")
                return 0
            else:
                print("[ERROR] Failed to save server_host.txt")
                return 1
        else:
            print("[WARN] No admin server detected. Run the admin app, then start the client again.")
            return 1

    headless_mode = str(os.getenv("PYPONDO_HEADLESS", "")).strip().lower() in {"1", "true", "yes"}
    remote_only_mode = env_flag("PYPONDO_REMOTE_ONLY", default=False)

    if is_client_mode() and (remote_only_mode or not env_flag("PYPONDO_FORCE_LOCAL_SERVER", default=False)):
        if is_verbose_logging_enabled():
            print("[INFO] Client mode: searching for remote admin server...")
        manual_candidates = get_manual_host_candidates()
        if remote_only_mode:
            # The online build must search broadly because it has no local
            # server fallback.
            remote_base_url = discover_remote_server_base_url()
        else:
            # The standalone build should open quickly. Only check explicitly
            # configured server addresses; broad LAN discovery can involve
            # hundreds of sequential timeouts before the local server starts.
            remote_base_url = None
            for manual_host in manual_candidates:
                for candidate in build_base_urls_from_host_value(manual_host):
                    if probe_server_base_url(candidate):
                        remote_base_url = candidate.rstrip("/")
                        break
                if remote_base_url:
                    break
        
        if remote_base_url:
            launch_url = f"{remote_base_url}{get_start_path()}"
            if is_verbose_logging_enabled():
                print(f"[INFO] Connected to admin server: {remote_base_url}")
            start_client_agent_background(remote_base_url)
            if headless_mode:
                print(f"Server ready at {launch_url}")
                return 0

            if not launch_ui(launch_url):
                return 1
            return 0

        if remote_only_mode:
            show_remote_server_required_message(headless=headless_mode)
            return 1

        # If manual server is configured in server_host.txt but not currently reachable,
        # fall back to local mode instead of prompting user
        if manual_candidates:
            if is_verbose_logging_enabled():
                print("[WARNING] Configured server unavailable, starting local server as fallback")
            # Continue to local server mode (below)
        else:
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

    launch_host = "127.0.0.1" if APP_HOST in {"0.0.0.0", "::"} else APP_HOST
    base_url = f"http://{launch_host}:{chosen_port}"
    launch_url = f"{base_url}{get_start_path()}"
    if not wait_for_server(base_url):
        print(f"Failed to start local server at {base_url}")
        return 1

    if headless_mode:
        print(f"Server ready at {launch_url}")
        return 0

    if not launch_ui(launch_url):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
