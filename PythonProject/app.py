from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import io
import json
import os
import re
import ipaddress
import shutil
import subprocess
import uuid
import zipfile
from decimal import Decimal, InvalidOperation
from urllib import request as http_request
from urllib import error as http_error
from urllib import parse as http_parse
from sqlalchemy import text
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import atexit
from functools import wraps

app = Flask(__name__)

# --- Config ---
basedir = os.path.abspath(os.path.dirname(__file__))
assets_dir = os.path.join(basedir, 'assets')
default_db_path = os.path.join(basedir, 'pccafe.db')
database_path = os.path.abspath(os.getenv("PYPONDO_DB_PATH", default_db_path))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + database_path
app.config['SECRET_KEY'] = 'super_secret_cyber_key'

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- Execution Time Tracking ---
def track_execution_time(f):
    """Decorator to track and record function execution time in response headers."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        start_time = time.time()
        result = f(*args, **kwargs)
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        # Add timing header to response
        try:
            if hasattr(result, 'headers'):
                result.headers['X-Response-Time'] = str(elapsed_ms)
            elif isinstance(result, tuple) and len(result) >= 2:
                headers = result[1] if isinstance(result[1], dict) else {}
                headers['X-Response-Time'] = str(elapsed_ms)
                result = (result[0], headers) + result[2:] if len(result) > 2 else (result[0], headers)
        except Exception:
            pass
        
        return result
    return decorated_function

HOURLY_RATE = 15.0
BOOKING_LEAD_MINUTES = 30
ALLOWED_LAN_COMMANDS = {"lock", "restart", "shutdown", "wake"}
MAX_TOPUP_AMOUNT = 10000.0
APP_VERSION = os.getenv("PYPONDO_APP_VERSION", "1.0.0").strip() or "1.0.0"
TOPUP_CURRENCY = os.getenv("TOPUP_CURRENCY", "php").strip().lower() or "php"
PAYMONGO_PUBLIC_KEY = os.getenv("PAYMONGO_PUBLIC_KEY", "pk_test_hRN7jf1RAviu9fXsis5mLU8y").strip()
ALLOWED_TOPUP_METHODS = {
    "gcash": "GCash",
    "card": "Card",
    "cash": "Cash"
}
DEFAULT_LAN_AGENT_TOKEN = "pypondo-lan-token-change-me"
BILLING_DISABLED = str(os.getenv("PYPONDO_DISABLE_BILLING", "0")).strip().lower() in {"1", "true", "yes"}
LAN_SCAN_CACHE = {"timestamp": 0, "cidr": None, "result": None, "scan_in_progress": False}
LAN_SCAN_LOCK = threading.Lock()
NETWORK_CMD_CACHE = {}
NETWORK_CMD_CACHE_LOCK = threading.Lock()
HOSTNAME_CACHE = {}
HOSTNAME_CACHE_LOCK = threading.Lock()
PUBLIC_TUNNEL_LOCK = threading.Lock()
PUBLIC_TUNNEL_URL_PATTERN = re.compile(r"https://[-a-zA-Z0-9.]+trycloudflare\.com(?:/[^\s]*)?", re.IGNORECASE)
PUBLIC_TUNNEL_STATE = {
    "process": None,
    "status": "idle",
    "url": "",
    "error": "",
    "binary_path": "",
    "local_url": "",
    "last_output": "",
}

# Global tracking for ping processes to prevent orphaned pings on exit
ACTIVE_PING_PROCESSES = set()
PING_LOCK = threading.Lock()

# Auto-charge settings
AUTO_CHARGE_ENABLED = True  # Default to enabled for backward compatibility

def terminate_all_ping_processes():
    """Kill all active ping processes on exit to prevent spam."""
    with PING_LOCK:
        for proc in list(ACTIVE_PING_PROCESSES):
            try:
                proc.terminate()
            except Exception:
                pass
        ACTIVE_PING_PROCESSES.clear()

atexit.register(terminate_all_ping_processes)


def terminate_public_tunnel():
    with PUBLIC_TUNNEL_LOCK:
        proc = PUBLIC_TUNNEL_STATE.get("process")
        PUBLIC_TUNNEL_STATE["process"] = None
        PUBLIC_TUNNEL_STATE["status"] = "idle"
        PUBLIC_TUNNEL_STATE["url"] = ""
        PUBLIC_TUNNEL_STATE["error"] = ""
        os.environ.pop("PYPONDO_PUBLIC_BASE_URL", None)

    if not proc:
        return

    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


atexit.register(terminate_public_tunnel)


def hidden_subprocess_kwargs():
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


def get_cloudflared_binary_candidates():
    configured = str(os.getenv("PYPONDO_CLOUDFLARED_PATH", "")).strip()
    candidates = []
    if configured:
        candidates.append(configured)

    candidates.extend([
        shutil.which("cloudflared"),
        os.path.join(basedir, "bin", "cloudflared.exe"),
        os.path.join(basedir, "tools", "cloudflared.exe"),
        os.path.join(basedir, "cloudflared.exe"),
    ])
    return [path for path in candidates if path]


def resolve_cloudflared_binary():
    for candidate in get_cloudflared_binary_candidates():
        if candidate and os.path.exists(candidate):
            return os.path.abspath(candidate)
    return ""


def get_default_cloudflared_download_url():
    if os.name == "nt":
        return "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    return "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"


def ensure_cloudflared_binary():
    resolved = resolve_cloudflared_binary()
    if resolved:
        return resolved

    download_url = str(os.getenv("PYPONDO_CLOUDFLARED_DOWNLOAD_URL", "")).strip() or get_default_cloudflared_download_url()
    target_dir = os.path.join(basedir, "bin")
    os.makedirs(target_dir, exist_ok=True)
    target_name = "cloudflared.exe" if os.name == "nt" else "cloudflared"
    target_path = os.path.join(target_dir, target_name)

    temp_path = target_path + ".download"
    http_request.urlretrieve(download_url, temp_path)
    os.replace(temp_path, target_path)
    if os.name != "nt":
        os.chmod(target_path, 0o755)
    return os.path.abspath(target_path)


def update_public_tunnel_state(**changes):
    with PUBLIC_TUNNEL_LOCK:
        PUBLIC_TUNNEL_STATE.update(changes)


def get_public_tunnel_snapshot():
    with PUBLIC_TUNNEL_LOCK:
        proc = PUBLIC_TUNNEL_STATE.get("process")
        alive = bool(proc and proc.poll() is None)
        return {
            "status": PUBLIC_TUNNEL_STATE.get("status", "idle"),
            "url": PUBLIC_TUNNEL_STATE.get("url", ""),
            "error": PUBLIC_TUNNEL_STATE.get("error", ""),
            "binary_path": PUBLIC_TUNNEL_STATE.get("binary_path", ""),
            "local_url": PUBLIC_TUNNEL_STATE.get("local_url", ""),
            "last_output": PUBLIC_TUNNEL_STATE.get("last_output", ""),
            "running": alive,
        }


def _public_tunnel_reader(proc):
    try:
        stream = proc.stdout
        if stream is None:
            return
        for raw_line in stream:
            line = str(raw_line or "").strip()
            if not line:
                continue
            update_public_tunnel_state(last_output=line)
            match = PUBLIC_TUNNEL_URL_PATTERN.search(line)
            if match:
                public_url = match.group(0).rstrip("/")
                os.environ["PYPONDO_PUBLIC_BASE_URL"] = public_url
                update_public_tunnel_state(status="ready", url=public_url, error="")
    finally:
        os.environ.pop("PYPONDO_PUBLIC_BASE_URL", None)
        update_public_tunnel_state(process=None, status="stopped", url="")


def start_public_tunnel(local_port):
    snapshot = get_public_tunnel_snapshot()
    if snapshot["running"] and snapshot["url"]:
        return True, snapshot

    try:
        binary_path = ensure_cloudflared_binary()
    except Exception as exc:
        update_public_tunnel_state(status="error", error=f"cloudflared download failed: {exc}")
        return False, get_public_tunnel_snapshot()

    local_url = f"http://127.0.0.1:{int(local_port)}"
    command = [binary_path, "tunnel", "--url", local_url, "--no-autoupdate"]

    try:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            **hidden_subprocess_kwargs(),
        )
    except Exception as exc:
        update_public_tunnel_state(
            status="error",
            error=f"cloudflared start failed: {exc}",
            binary_path=binary_path,
            local_url=local_url,
        )
        return False, get_public_tunnel_snapshot()

    update_public_tunnel_state(
        process=proc,
        status="starting",
        url="",
        error="",
        binary_path=binary_path,
        local_url=local_url,
        last_output="Launching cloudflared quick tunnel...",
    )

    threading.Thread(target=_public_tunnel_reader, args=(proc,), daemon=True).start()

    deadline = time.time() + 30
    while time.time() < deadline:
        snapshot = get_public_tunnel_snapshot()
        if snapshot["url"]:
            return True, snapshot
        if not snapshot["running"] and snapshot["status"] in {"error", "stopped"}:
            break
        time.sleep(0.25)

    terminate_public_tunnel()
    update_public_tunnel_state(status="error", error="Timed out while waiting for a public route from cloudflared.")
    return False, get_public_tunnel_snapshot()


# --- Database Models ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    pondo = db.Column(db.Float, default=0.0)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class PC(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)
    is_occupied = db.Column(db.Boolean, default=False)
    lan_ip = db.Column(db.String(64), nullable=True)
    lan_port = db.Column(db.Integer, nullable=True)
    last_agent_seen_at = db.Column(db.DateTime, nullable=True)
    online_since_at = db.Column(db.DateTime, nullable=True)


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    pc_id = db.Column(db.Integer, db.ForeignKey('pc.id'), nullable=False)
    booking_date = db.Column(db.String(20), nullable=True)
    time_slot = db.Column(db.String(20), nullable=False)
    # Relationships for easy access in templates
    user = db.relationship('User', backref='bookings')
    pc = db.relationship('PC', backref='bookings')


class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    pc_id = db.Column(db.Integer, db.ForeignKey('pc.id'))
    start_time = db.Column(db.DateTime, default=datetime.now)
    end_time = db.Column(db.DateTime, nullable=True)
    cost = db.Column(db.Float, default=0.0)
    last_charged_at = db.Column(db.DateTime, nullable=True)


class AdminLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_name = db.Column(db.String(80))
    action = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.now)


class PaymentTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    provider = db.Column(db.String(32), nullable=False, default="online_request")
    external_id = db.Column(db.String(128), unique=True, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(8), nullable=False, default="php")
    status = db.Column(db.String(32), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, default=datetime.now)
    credited_at = db.Column(db.DateTime, nullable=True)


class LanCommand(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pc_name = db.Column(db.String(64), nullable=False, index=True)
    command = db.Column(db.String(32), nullable=False)
    payload_json = db.Column(db.Text, nullable=False, default="{}")
    status = db.Column(db.String(16), nullable=False, default="queued", index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    result_message = db.Column(db.String(512), nullable=True)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def ensure_pc_lan_ip_column():
    try:
        cols = [row[1] for row in db.session.execute(text("PRAGMA table_info(pc)")).fetchall()]
    except Exception:
        db.create_all()
        cols = [row[1] for row in db.session.execute(text("PRAGMA table_info(pc)")).fetchall()]
    if "lan_ip" not in cols:
        db.session.execute(text("ALTER TABLE pc ADD COLUMN lan_ip VARCHAR(64)"))
        db.session.commit()
    if "lan_port" not in cols:
        db.session.execute(text("ALTER TABLE pc ADD COLUMN lan_port INTEGER"))
        db.session.commit()
    if "last_agent_seen_at" not in cols:
        db.session.execute(text("ALTER TABLE pc ADD COLUMN last_agent_seen_at DATETIME"))
        db.session.commit()
    if "online_since_at" not in cols:
        db.session.execute(text("ALTER TABLE pc ADD COLUMN online_since_at DATETIME"))
        db.session.commit()


def ensure_booking_date_column():
    try:
        cols = [row[1] for row in db.session.execute(text("PRAGMA table_info(booking)")).fetchall()]
    except Exception:
        db.create_all()
        cols = [row[1] for row in db.session.execute(text("PRAGMA table_info(booking)")).fetchall()]
    if "booking_date" not in cols:
        db.session.execute(text("ALTER TABLE booking ADD COLUMN booking_date VARCHAR(20)"))
        db.session.commit()


def ensure_session_last_charged_at_column():
    try:
        cols = [row[1] for row in db.session.execute(text("PRAGMA table_info(session)")).fetchall()]
    except Exception:
        db.create_all()
        cols = [row[1] for row in db.session.execute(text("PRAGMA table_info(session)")).fetchall()]
    if "last_charged_at" not in cols:
        db.session.execute(text("ALTER TABLE session ADD COLUMN last_charged_at DATETIME"))
        db.session.commit()


def ensure_core_seed_data():
    seeded = False

    if not PC.query.first():
        for i in range(1, 6):
            db.session.add(PC(name=f"PC-{i}"))
        seeded = True

    if not User.query.filter_by(username="admin").first():
        admin = User(username="admin", is_admin=True)
        admin.set_password("admin123")
        db.session.add(admin)
        seeded = True

    if seeded:
        db.session.commit()
    return seeded


def normalize_agent_port(value):
    try:
        port = int(str(value).strip())
    except Exception:
        return None
    if port < 1 or port > 65535:
        return None
    return port


def normalize_ipv4(value):
    try:
        ip = ipaddress.ip_address(value.strip())
    except Exception:
        return None
    if ip.version != 4:
        return None
    if ip.is_loopback or ip.is_multicast or ip.is_unspecified:
        return None
    return str(ip)


def normalize_ipv6(value):
    raw = value.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    raw = raw.split("%", 1)[0]
    try:
        ip = ipaddress.ip_address(raw)
    except Exception:
        return None
    if ip.version != 6:
        return None
    if ip.is_loopback or ip.is_multicast or ip.is_unspecified:
        return None
    return str(ip)


def build_unique_agent_pc_name(raw_name):
    base = re.sub(r"[^A-Za-z0-9_-]", "", str(raw_name or "").strip()) or "PC-AUTO"
    base = base[:20] or "PC-AUTO"

    if not PC.query.filter_by(name=base).first():
        return base

    # Reserve room for a short numeric suffix within the 20-char name limit.
    stem = base[:16] or "PC-AUTO"
    for idx in range(1, 1000):
        candidate = f"{stem}-{idx}"
        if not PC.query.filter_by(name=candidate).first():
            return candidate

    return f"PC-{uuid.uuid4().hex[:8]}"[:20]


def normalize_lan_ip(value):
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    return normalize_ipv4(text_value) or normalize_ipv6(text_value)


def extract_ips_from_text(text):
    found = []
    for token in re.split(r"[\s,]+", text):
        candidate = token.strip("[](){}<>;")
        if not candidate:
            continue
        ip = normalize_lan_ip(candidate)
        if ip and ip not in found:
            found.append(ip)
    return found


def run_cached_network_command(cache_key, command_args, ttl_seconds):
    now = time.time()
    with NETWORK_CMD_CACHE_LOCK:
        cached = NETWORK_CMD_CACHE.get(cache_key)
        if cached and (now - cached["timestamp"] < ttl_seconds):
            return cached["output"]

    try:
        output = subprocess.check_output(
            command_args,
            text=True,
            encoding="utf-8",
            errors="ignore",
            **hidden_subprocess_kwargs()
        )
    except Exception:
        output = ""

    with NETWORK_CMD_CACHE_LOCK:
        NETWORK_CMD_CACHE[cache_key] = {"timestamp": now, "output": output}
    return output


def get_local_ipv4_addresses():
    output = run_cached_network_command("ipconfig", ["ipconfig"], ttl_seconds=8)
    if not output:
        return []

    ips = []
    for value in re.findall(r"(?im)^\s*[^:\r\n]*IPv4[^:\r\n]*:\s*([0-9.]+)\s*$", output):
        ip = normalize_ipv4(value)
        if not ip:
            continue
        if ip.startswith("169.254."):
            continue
        if ip not in ips:
            ips.append(ip)
    return ips


def get_local_ipv6_addresses():
    output = run_cached_network_command("ipconfig", ["ipconfig"], ttl_seconds=8)
    if not output:
        return []

    ips = []
    for value in re.findall(r"(?im)^\s*[^:\r\n]*IPv6[^:\r\n]*:\s*([0-9a-fA-F:%]+)\s*$", output):
        ip = normalize_ipv6(value)
        if not ip:
            continue
        if ip not in ips:
            ips.append(ip)
    return ips


def get_default_gateway_ips():
    output = run_cached_network_command("ipconfig", ["ipconfig"], ttl_seconds=8)
    if not output:
        return []

    lines = output.splitlines()
    gateways = []

    for i, line in enumerate(lines):
        if "Default Gateway" not in line:
            continue

        _, _, remainder = line.partition(":")
        for ip in extract_ips_from_text(remainder):
            if ip not in gateways:
                gateways.append(ip)

        if remainder.strip():
            continue

        j = i + 1
        while j < len(lines):
            next_line = lines[j]
            if not next_line.strip():
                break
            if ":" in next_line and "Default Gateway" not in next_line:
                break
            for ip in extract_ips_from_text(next_line):
                if ip not in gateways:
                    gateways.append(ip)
            j += 1

    return gateways


def parse_ipv4_interfaces():
    output = run_cached_network_command("ipconfig", ["ipconfig"], ttl_seconds=8)
    if not output:
        return []

    interfaces = []
    current = {}

    def flush_current():
        if current.get("ipv4") and current.get("subnet_mask"):
            interfaces.append({
                "name": current.get("name", "Unknown"),
                "ipv4": current["ipv4"],
                "subnet_mask": current["subnet_mask"],
                "default_gateway": current.get("default_gateway")
            })

    for raw_line in output.splitlines():
        line = raw_line.rstrip()

        if line and not raw_line.startswith(" "):
            flush_current()
            current = {"name": line.strip().rstrip(":")}
            continue

        if "IPv4 Address" in line:
            _, _, value = line.partition(":")
            ip = normalize_ipv4(value.strip())
            if ip:
                current["ipv4"] = ip
            continue

        if "Subnet Mask" in line:
            _, _, value = line.partition(":")
            mask = normalize_ipv4(value.strip())
            if mask:
                current["subnet_mask"] = mask
            continue

        if "Default Gateway" in line:
            _, _, value = line.partition(":")
            gateway = None
            for ip in extract_ips_from_text(value):
                if ":" in ip:
                    continue
                gateway = ip
                break
            if gateway:
                current["default_gateway"] = gateway
            continue

    flush_current()
    return interfaces


def build_primary_ipv4_network_summary():
    interfaces = parse_ipv4_interfaces()
    if not interfaces:
        return None

    primary = None
    for iface in interfaces:
        if iface.get("default_gateway"):
            primary = iface
            break
    if primary is None:
        primary = interfaces[0]

    try:
        network = ipaddress.IPv4Network(f"{primary['ipv4']}/{primary['subnet_mask']}", strict=False)
    except Exception:
        return None

    total_addresses = int(network.num_addresses)
    if network.prefixlen >= 31:
        total_usable = total_addresses
    else:
        total_usable = max(total_addresses - 2, 0)

    used = set()
    local_ip = normalize_ipv4(primary.get("ipv4", ""))
    gateway_ip = normalize_ipv4(primary.get("default_gateway", "") or "")

    if local_ip and ipaddress.IPv4Address(local_ip) in network:
        used.add(local_ip)
    if gateway_ip and ipaddress.IPv4Address(gateway_ip) in network:
        used.add(gateway_ip)

    for ip in discover_lan_ipv4_neighbors():
        try:
            if ipaddress.IPv4Address(ip) in network:
                used.add(ip)
        except Exception:
            continue

    used_count = len(used)
    available_count = max(total_usable - used_count, 0)

    return {
        "interface": primary.get("name"),
        "local_ipv4": local_ip,
        "subnet_mask": primary.get("subnet_mask"),
        "gateway_ipv4": gateway_ip,
        "network": str(network.network_address),
        "broadcast": str(network.broadcast_address),
        "cidr": str(network),
        "prefixlen": int(network.prefixlen),
        "total_usable_hosts": total_usable,
        "used_ipv4_count": used_count,
        "available_ipv4_count": available_count,
        "used_ipv4": sorted(used, key=lambda value: tuple(int(part) for part in value.split(".")))
    }


def ping_ipv4_host(ip, timeout_ms=200):
    try:
        # Use Popen to track the process for cleanup on exit
        proc = subprocess.Popen(
            ["ping", "-n", "1", "-w", str(timeout_ms), ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **hidden_subprocess_kwargs()
        )
        with PING_LOCK:
            ACTIVE_PING_PROCESSES.add(proc)
        try:
            return proc.wait() == 0
        finally:
            with PING_LOCK:
                ACTIVE_PING_PROCESSES.discard(proc)
    except Exception:
        return False


def reverse_dns_name(ip):
    ttl = int(os.getenv("LAN_DNS_CACHE_TTL_SECONDS", "300"))
    now = time.time()
    with HOSTNAME_CACHE_LOCK:
        cached = HOSTNAME_CACHE.get(ip)
        if cached and (now - cached["timestamp"] < ttl):
            return cached["hostname"]

    try:
        host, _, _ = socket.gethostbyaddr(ip)
        value = host
    except Exception:
        value = None

    with HOSTNAME_CACHE_LOCK:
        HOSTNAME_CACHE[ip] = {"timestamp": now, "hostname": value}
    return value


def netbios_name(ip, timeout_seconds=0.5):
    try:
        result = subprocess.run(
            ["nbtstat", "-A", ip],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout_seconds,
            **hidden_subprocess_kwargs()
        )
    except Exception:
        return None

    if result.returncode != 0:
        return None

    match = re.search(r"(?im)^\s*([^\s<]+)\s+<00>\s+UNIQUE\s*$", result.stdout)
    if match:
        return match.group(1).strip()
    return None


def short_host_name(value):
    if not value:
        return None
    return str(value).split(".", 1)[0].strip() or None


def _quick_gateway_scan_result(summary):
    gateway_ip = summary.get("gateway_ipv4")
    local_ip = summary.get("local_ipv4")

    clients = []
    for ip in discover_lan_ipv4_neighbors():
        if ip in {gateway_ip, local_ip}:
            continue
        clients.append({
            "ip": ip,
            "hostname": "unknown",
            "source_pc_name": "unknown"
        })

    clients = sorted(clients, key=lambda row: tuple(int(part) for part in row["ip"].split(".")))
    return {
        "ok": True,
        "network": summary["cidr"],
        "gateway_ipv4": gateway_ip,
        "local_ipv4": local_ip,
        "client_count": len(clients),
        "clients": clients,
        "stale": True,
        "mode": "quick"
    }


def _full_gateway_scan(summary):
    network = ipaddress.IPv4Network(summary["cidr"], strict=False)
    max_hosts = int(os.getenv("LAN_SCAN_MAX_HOSTS", "254"))
    workers = int(os.getenv("LAN_SCAN_WORKERS", "48"))
    timeout_ms = int(os.getenv("LAN_SCAN_PING_TIMEOUT_MS", "150"))
    dns_workers = int(os.getenv("LAN_SCAN_DNS_WORKERS", "24"))
    enable_netbios = str(os.getenv("LAN_SCAN_ENABLE_NETBIOS", "0")).strip().lower() in {"1", "true", "yes"}
    nbt_timeout = float(os.getenv("LAN_SCAN_NBTSTAT_TIMEOUT_SECONDS", "0.5"))
    gateway_ip = summary.get("gateway_ipv4")
    local_ip = summary.get("local_ipv4")

    host_pool = [str(ip) for ip in network.hosts()]
    if local_ip in host_pool:
        host_pool.remove(local_ip)
    if gateway_ip in host_pool:
        host_pool.remove(gateway_ip)

    if len(host_pool) > max_hosts:
        result = {
            "ok": False,
            "error": f"network too large to scan safely ({len(host_pool)} hosts, max {max_hosts})",
            "network": summary["cidr"],
            "gateway_ipv4": gateway_ip,
            "clients": [],
            "stale": False,
            "mode": "full"
        }
        return result

    active_ips = set(discover_lan_ipv4_neighbors())
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(ping_ipv4_host, ip, timeout_ms): ip for ip in host_pool}
        for future in as_completed(futures):
            ip = futures[future]
            try:
                if future.result():
                    active_ips.add(ip)
            except Exception:
                continue

    active_ips.discard(local_ip)
    active_ips.discard(gateway_ip)

    mapped_pc_by_ip = {pc.lan_ip: pc.name for pc in PC.query.filter(PC.lan_ip.isnot(None)).all()}
    ordered_ips = sorted(active_ips, key=lambda value: tuple(int(part) for part in value.split(".")))
    resolved = {}

    def resolve_one(ip):
        dns_name = reverse_dns_name(ip)
        nb_name = None
        if enable_netbios:
            try:
                nb_name = netbios_name(ip, timeout_seconds=nbt_timeout)
            except Exception:
                nb_name = None
        return ip, dns_name, nb_name

    with ThreadPoolExecutor(max_workers=max(1, dns_workers)) as executor:
        futures = {executor.submit(resolve_one, ip): ip for ip in ordered_ips}
        for future in as_completed(futures):
            ip = futures[future]
            try:
                resolved_ip, dns_name, nb_name = future.result()
                resolved[resolved_ip] = (dns_name, nb_name)
            except Exception:
                resolved[ip] = (None, None)

    clients = []
    for ip in ordered_ips:
        dns_name, nb_name = resolved.get(ip, (None, None))
        source_pc_name = nb_name or short_host_name(dns_name) or "unknown"
        clients.append({
            "ip": ip,
            "hostname": dns_name or "unknown",
            "source_pc_name": source_pc_name,
            "device_name": source_pc_name,
            "mapped_pc_name": mapped_pc_by_ip.get(ip)
        })

    return {
        "ok": True,
        "network": summary["cidr"],
        "gateway_ipv4": gateway_ip,
        "local_ipv4": local_ip,
        "client_count": len(clients),
        "clients": clients,
        "stale": False,
        "mode": "full"
    }


def _store_gateway_scan_cache(cidr, result):
    with LAN_SCAN_LOCK:
        LAN_SCAN_CACHE["timestamp"] = time.time()
        LAN_SCAN_CACHE["cidr"] = cidr
        LAN_SCAN_CACHE["result"] = result
        LAN_SCAN_CACHE["scan_in_progress"] = False


def _run_gateway_scan_background():
    summary = build_primary_ipv4_network_summary()
    if not summary:
        with LAN_SCAN_LOCK:
            LAN_SCAN_CACHE["scan_in_progress"] = False
        return
    try:
        result = _full_gateway_scan(summary)
        _store_gateway_scan_cache(summary["cidr"], result)
    except Exception:
        with LAN_SCAN_LOCK:
            LAN_SCAN_CACHE["scan_in_progress"] = False


def _trigger_gateway_scan_background():
    with LAN_SCAN_LOCK:
        if LAN_SCAN_CACHE.get("scan_in_progress"):
            return
        LAN_SCAN_CACHE["scan_in_progress"] = True
    threading.Thread(target=_run_gateway_scan_background, daemon=True).start()


def get_gateway_client_scan(force=False, non_blocking=False):
    summary = build_primary_ipv4_network_summary()
    if not summary:
        return {"ok": False, "error": "no active IPv4 router network detected", "clients": []}

    ttl = int(os.getenv("LAN_SCAN_TTL_SECONDS", "45"))
    now = time.time()
    with LAN_SCAN_LOCK:
        cached = LAN_SCAN_CACHE.get("result")
        cached_cidr = LAN_SCAN_CACHE.get("cidr")
        cached_age = now - float(LAN_SCAN_CACHE.get("timestamp", 0))

    if not force and cached is not None and cached_cidr == summary["cidr"] and cached_age < ttl:
        return cached

    if non_blocking:
        _trigger_gateway_scan_background()
        if cached is not None and cached_cidr == summary["cidr"]:
            if isinstance(cached, dict):
                stale_cached = dict(cached)
                stale_cached["stale"] = True
                stale_cached["mode"] = stale_cached.get("mode", "cache")
                return stale_cached
            return cached
        return _quick_gateway_scan_result(summary)

    result = _full_gateway_scan(summary)
    _store_gateway_scan_cache(summary["cidr"], result)
    return result


def get_local_lan_addresses():
    addresses = []
    for ip in get_local_ipv4_addresses() + get_local_ipv6_addresses():
        if ip not in addresses:
            addresses.append(ip)
    return addresses


def discover_lan_ipv4_neighbors():
    output = run_cached_network_command("arp_a", ["arp", "-a"], ttl_seconds=5)
    if not output:
        return []

    local_ips = set(get_local_ipv4_addresses())
    found = []
    for match in re.findall(r"(\d+\.\d+\.\d+\.\d+)", output):
        ip = normalize_ipv4(match)
        if not ip:
            continue
        if ip in local_ips or ip.endswith(".0") or ip.endswith(".255") or ip.startswith("169.254."):
            continue
        if ip not in found:
            found.append(ip)
    return found


def discover_lan_ipv6_neighbors():
    output = run_cached_network_command(
        "netsh_ipv6_neighbors",
        ["netsh", "interface", "ipv6", "show", "neighbors"],
        ttl_seconds=10
    )
    if not output:
        return []

    local_ips = set(get_local_ipv6_addresses())
    found = []
    for token in re.split(r"\s+", output):
        ip = normalize_ipv6(token)
        if not ip or ip in local_ips:
            continue
        if ip not in found:
            found.append(ip)
    return found


def discover_lan_addresses():
    local_ips = set(get_local_lan_addresses())
    found = []

    for ip in get_default_gateway_ips():
        if ip in local_ips:
            continue
        if ip not in found:
            found.append(ip)

    for ip in discover_lan_ipv4_neighbors() + discover_lan_ipv6_neighbors():
        if ip in local_ips:
            continue
        if ip not in found:
            found.append(ip)

    return found


def discover_lan_ips():
    return [ip for ip in discover_lan_addresses() if ":" not in ip]


def get_gateway_ipv4_set():
    gateways = set()
    for ip in get_default_gateway_ips():
        if ":" in ip:
            continue
        normalized = normalize_ipv4(ip)
        if normalized:
            gateways.add(normalized)
    return gateways


def get_assignable_pc_ipv4_addresses(online_only=False):
    local_ipv4 = set(get_local_ipv4_addresses())
    gateway_ipv4 = get_gateway_ipv4_set()
    assignable = []
    dns_only = str(os.getenv("LAN_ASSIGN_DNS_ONLY", "0")).strip().lower() in {"1", "true", "yes"}

    if online_only:
        scan = get_gateway_client_scan(force=True, non_blocking=False)
    else:
        scan = get_gateway_client_scan(non_blocking=True)

    candidate_ips = []
    if isinstance(scan, dict) and scan.get("ok"):
        for row in scan.get("clients", []):
            ip = row.get("ip")
            if not ip:
                continue
            if dns_only:
                name = str(row.get("source_pc_name", "")).strip().lower()
                if not name or name == "unknown":
                    continue
            if ip not in candidate_ips:
                candidate_ips.append(ip)

    if not online_only:
        for ip in discover_lan_ipv4_neighbors():
            if ip not in candidate_ips:
                candidate_ips.append(ip)

    for ip in candidate_ips:
        if not ip:
            continue
        if ip in local_ipv4:
            continue
        if ip in gateway_ipv4:
            continue
        if ip not in assignable:
            assignable.append(ip)

    return assignable


def clear_undetected_pc_ips(detected_ips):
    detected_set = set(detected_ips or [])
    gateway_ipv4 = get_gateway_ipv4_set()
    cleared = []
    pcs = PC.query.order_by(PC.id.asc()).all()

    for pc in pcs:
        if not pc.lan_ip:
            continue
        if pc.lan_ip in gateway_ipv4:
            cleared.append({"pc_id": pc.id, "pc_name": pc.name, "old_ip": pc.lan_ip, "reason": "gateway_ip"})
            pc.lan_ip = None
            continue
        if pc.lan_ip in detected_set:
            continue
        cleared.append({"pc_id": pc.id, "pc_name": pc.name, "old_ip": pc.lan_ip, "reason": "not_detected"})
        pc.lan_ip = None

    return cleared


def load_lan_targets():
    raw_targets = os.getenv("LAN_PC_TARGETS", "").strip()
    if not raw_targets:
        return {}

    try:
        parsed = json.loads(raw_targets)
    except json.JSONDecodeError:
        return {}

    if not isinstance(parsed, dict):
        return {}

    normalized = {}
    for pc_name, target in parsed.items():
        if not isinstance(pc_name, str) or not isinstance(target, str):
            continue
        value = target.strip()
        if not value:
            continue
        if not value.startswith("http://") and not value.startswith("https://"):
            value = f"http://{value}"
        normalized[pc_name] = value.rstrip("/")
    return normalized


def get_lan_agent_token():
    return os.getenv("LAN_AGENT_TOKEN", DEFAULT_LAN_AGENT_TOKEN).strip() or DEFAULT_LAN_AGENT_TOKEN


def resolve_pc_targets(pc_name):
    targets = load_lan_targets()
    target = targets.get(pc_name)
    if target:
        return [target]

    pc = PC.query.filter_by(name=pc_name).first()
    if not pc or not pc.lan_ip:
        return []

    ports = []
    if pc.lan_port:
        ports.append(pc.lan_port)

    default_port = normalize_agent_port(os.getenv("LAN_AGENT_DEFAULT_PORT", "5001"))
    if default_port:
        ports.append(default_port)

    for fallback in (5001, 5000):
        if fallback not in ports:
            ports.append(fallback)

    host = pc.lan_ip
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return [f"http://{host}:{port}" for port in ports]


def remote_windows_control_fallback(pc_name, command):
    if command not in {"restart", "shutdown", "lock"}:
        return False, "No fallback path for this command"

    pc = PC.query.filter_by(name=pc_name).first()
    if not pc or not pc.lan_ip or ":" in pc.lan_ip:
        return False, "Fallback requires PC IPv4 address"

    unc_host = f"\\\\{pc.lan_ip}"
    if command == "lock":
        cmd_line = "wmic /node:" + pc.lan_ip + " process call create \"rundll32.exe user32.dll,LockWorkStation\""
    else:
        shutdown_flag = "/r" if command == "restart" else "/s"
        cmd_line = f"shutdown /m {unc_host} {shutdown_flag} /t 0 /f"

    try:
        control = subprocess.run(
            ["cmd", "/c", cmd_line],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            **hidden_subprocess_kwargs()
        )
    except Exception as exc:
        return False, f"Fallback failed: {exc}"

    output = (control.stdout or "").strip()
    error = (control.stderr or "").strip()
    details = " | ".join(part for part in [output, error] if part).strip()

    if command == "lock":
        if control.returncode == 0 and "ReturnValue = 0" in (output + "\n" + error):
            return True, f"Fallback lock sent via cmd using {pc.lan_ip}"
        return False, f"Fallback lock failed via cmd for {pc.lan_ip}: {details or 'access denied or RPC unavailable'}"

    if control.returncode == 0:
        return True, f"Fallback {command} sent via cmd using {pc.lan_ip}"
    return False, f"Fallback {command} failed via cmd for {pc.lan_ip}: {details or 'access denied or RPC unavailable'}"


def get_agent_status_note(pc_name):
    pc = PC.query.filter_by(name=pc_name).first()
    if not pc:
        return "agent status: unknown PC"
    if not pc.last_agent_seen_at:
        return "agent status: never seen"
    age_seconds = int(max((datetime.now() - pc.last_agent_seen_at).total_seconds(), 0))
    if age_seconds < 60:
        return f"agent status: last seen {age_seconds}s ago"
    return f"agent status: last seen {age_seconds // 60}m ago"


def get_agent_online_window_seconds():
    try:
        return max(int(os.getenv("LAN_AGENT_ONLINE_WINDOW_SECONDS", "90")), 1)
    except Exception:
        return 90


def is_pc_online(pc, now_dt=None, online_window_seconds=None):
    if not pc or not pc.last_agent_seen_at:
        return False
    if now_dt is None:
        now_dt = datetime.now()
    if online_window_seconds is None:
        online_window_seconds = get_agent_online_window_seconds()
    return (now_dt - pc.last_agent_seen_at).total_seconds() <= online_window_seconds


def mark_pc_agent_seen(pc, seen_at=None):
    if not pc:
        return
    if seen_at is None:
        seen_at = datetime.now()

    last_seen = pc.last_agent_seen_at
    online_window_seconds = get_agent_online_window_seconds()
    within_same_online_window = bool(
        last_seen and (seen_at - last_seen).total_seconds() <= online_window_seconds
    )
    if not pc.online_since_at:
        pc.online_since_at = last_seen if within_same_online_window else seen_at
    elif not within_same_online_window:
        pc.online_since_at = seen_at

    pc.last_agent_seen_at = seen_at


def format_duration_compact(total_seconds):
    total_seconds = int(max(total_seconds or 0, 0))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def normalize_booking_date_value(raw_value):
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return datetime.now().strftime("%Y-%m-%d")
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def normalize_time_slot_value(raw_value):
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return None
    for time_format in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(raw_value, time_format).strftime("%H:%M")
        except ValueError:
            continue
    return None


def parse_booking_datetime(booking_date, time_slot):
    try:
        return datetime.strptime(f"{booking_date} {time_slot}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def find_conflicting_booking(pc_id, booking_date, time_slot):
    same_day_bookings = Booking.query.filter_by(pc_id=pc_id, booking_date=booking_date).all()
    for booking in same_day_bookings:
        if normalize_time_slot_value(booking.time_slot) == time_slot:
            return booking
    return None


def get_pc_booking_usage_state(pc, now_dt=None, online_window_seconds=None):
    if now_dt is None:
        now_dt = datetime.now()
    if online_window_seconds is None:
        online_window_seconds = get_agent_online_window_seconds()

    active_session = Session.query.filter_by(pc_id=pc.id, end_time=None).order_by(Session.start_time.desc()).first()
    online_now = is_pc_online(pc, now_dt, online_window_seconds)
    return {
        "active_session": active_session,
        "online_now": online_now,
        "in_use": bool(pc.is_occupied or active_session or online_now)
    }


def annotate_booking_usage_for_pcs(pcs, now_dt=None):
    if not pcs:
        return pcs

    if now_dt is None:
        now_dt = datetime.now()

    online_window_seconds = get_agent_online_window_seconds()
    active_sessions = Session.query.filter_by(end_time=None).order_by(Session.start_time.desc()).all()
    active_session_by_pc = {}
    for session in active_sessions:
        active_session_by_pc.setdefault(session.pc_id, session)

    for pc in pcs:
        active_session = active_session_by_pc.get(pc.id)
        online_now = is_pc_online(pc, now_dt, online_window_seconds)
        pc.booking_in_use_now = bool(pc.is_occupied or active_session or online_now)

    return pcs


def enqueue_lan_command(pc_name, command, payload=None, note=None):
    payload_data = payload if isinstance(payload, dict) else {}
    existing = LanCommand.query.filter(
        LanCommand.pc_name == pc_name,
        LanCommand.command == command,
        LanCommand.status.in_(["queued", "sent"])
    ).order_by(LanCommand.created_at.asc()).first()
    if existing is not None:
        return existing, False

    queued = LanCommand(
        pc_name=pc_name,
        command=command,
        payload_json=json.dumps(payload_data),
        status="queued"
    )
    db.session.add(queued)
    db.session.flush()
    db.session.add(AdminLog(
        admin_name="system",
        action=f"Queued LAN command #{queued.id} for {pc_name}: {command}" + (f" ({note})" if note else "")
    ))
    db.session.commit()
    return queued, True


def pick_next_lan_command_for_names(candidate_names):
    if not candidate_names:
        return None

    now = datetime.now()
    retry_after_seconds = int(os.getenv("LAN_COMMAND_RETRY_AFTER_SECONDS", "20"))

    cmd = LanCommand.query.filter(
        LanCommand.pc_name.in_(candidate_names),
        LanCommand.status == "queued"
    ).order_by(LanCommand.created_at.asc()).first()

    if cmd is None:
        sent_cmd = LanCommand.query.filter(
            LanCommand.pc_name.in_(candidate_names),
            LanCommand.status == "sent"
        ).order_by(LanCommand.sent_at.asc()).first()
        if sent_cmd and sent_cmd.sent_at:
            if (now - sent_cmd.sent_at).total_seconds() >= retry_after_seconds:
                cmd = sent_cmd

    if cmd is None:
        return None

    cmd.status = "sent"
    cmd.sent_at = now
    cmd.attempts = int(cmd.attempts or 0) + 1
    db.session.commit()
    return cmd


def send_lan_command(pc_name, command, payload=None):
    targets = resolve_pc_targets(pc_name)
    status_note = get_agent_status_note(pc_name)
    if not targets:
        queued, created = enqueue_lan_command(pc_name, command, payload, note="no direct target")
        if created:
            return True, f"No direct LAN target; queued command #{queued.id} for client pull ({status_note})"
        return True, f"Existing pending command #{queued.id} retained ({status_note})"

    shared_token = get_lan_agent_token()

    body = json.dumps({
        "command": command,
        "payload": payload if isinstance(payload, dict) else {}
    }).encode("utf-8")

    errors = []
    for target in targets:
        req = http_request.Request(
            f"{target}/agent/command",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Agent-Token": shared_token
            }
        )

        try:
            with http_request.urlopen(req, timeout=6) as response:
                response_text = response.read().decode("utf-8")
                response_data = json.loads(response_text) if response_text else {}
                ok = bool(response_data.get("ok", True))
                message = response_data.get("message", "Command sent")
                if ok:
                    return True, message
                errors.append(f"{target}: {message}")
        except http_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            errors.append(f"{target}: HTTP {exc.code} {detail}")
        except Exception as exc:
            errors.append(f"{target}: {exc}")

    fallback_ok, fallback_message = remote_windows_control_fallback(pc_name, command)
    if fallback_ok:
        return True, fallback_message

    queued, created = enqueue_lan_command(pc_name, command, payload, note="direct+fallback failed")
    details = " | ".join(errors[:3]) if errors else "no connection details"
    if created:
        return True, f"Queued command #{queued.id} for client pickup (direct path unavailable, {status_note}). Details: {details}. {fallback_message}"
    return True, f"Command already pending as #{queued.id} ({status_note}). Direct details: {details}. {fallback_message}"


def get_client_ip_from_request():
    forwarded_for = request.headers.get("X-Forwarded-For", "").strip()
    if forwarded_for:
        first_ip = forwarded_for.split(",")[0].strip()
        ip = normalize_lan_ip(first_ip)
        if ip:
            return ip

    real_ip = request.headers.get("X-Real-IP", "").strip()
    if real_ip:
        ip = normalize_lan_ip(real_ip)
        if ip:
            return ip

    remote_addr = (request.remote_addr or "").strip()
    return normalize_lan_ip(remote_addr)


def get_request_server_port(default_port=5000):
    host = (request.host or "").strip()
    if host:
        if host.startswith("[") and "]:" in host:
            _, _, port_text = host.rpartition("]:")
            try:
                return int(port_text)
            except Exception:
                pass
        elif host.count(":") == 1:
            _, _, port_text = host.rpartition(":")
            try:
                return int(port_text)
            except Exception:
                pass

    try:
        return int(os.getenv("APP_PORT", str(default_port)))
    except Exception:
        return default_port


def split_host_and_port(value):
    host_value = str(value or "").strip()
    if not host_value:
        return "", None

    if host_value.startswith("["):
        end_idx = host_value.find("]")
        if end_idx != -1:
            host = host_value[1:end_idx].strip()
            remainder = host_value[end_idx + 1:]
            if remainder.startswith(":"):
                try:
                    return host, int(remainder[1:])
                except Exception:
                    return host, None
            return host, None

    if host_value.count(":") == 1:
        host, _, port_text = host_value.rpartition(":")
        if host and port_text.isdigit():
            try:
                return host.strip(), int(port_text)
            except Exception:
                return host.strip(), None

    return host_value, None


def format_host_for_url(host):
    value = str(host or "").strip()
    if ":" in value and not value.startswith("["):
        return f"[{value}]"
    return value


def get_primary_local_ipv4():
    interfaces = parse_ipv4_interfaces()
    for interface in interfaces:
        ip = normalize_ipv4(interface.get("ipv4", ""))
        if ip and interface.get("default_gateway"):
            return ip

    local_ipv4 = get_local_ipv4_addresses()
    return local_ipv4[0] if local_ipv4 else None


def build_target_descriptor(base_url, *, host=None, port=None, display_address=None):
    normalized_base_url = str(base_url or "").strip().rstrip("/")
    if not normalized_base_url:
        return None

    try:
        parsed = http_parse.urlsplit(normalized_base_url)
    except Exception:
        return None

    normalized_host = str(host or parsed.hostname or "").strip()
    if not normalized_host:
        return None

    pairing_url = f"{normalized_base_url}/api/mobile/pairing"
    visible_address = str(display_address or "").strip()
    if not visible_address:
        if parsed.port:
            visible_address = f"{format_host_for_url(normalized_host)}:{parsed.port}"
        else:
            visible_address = normalized_base_url

    return {
        "ip": normalized_host,
        "address": visible_address,
        "base_url": normalized_base_url,
        "pairing_url": pairing_url,
        "qr_image_url": (
            "https://api.qrserver.com/v1/create-qr-code/"
            f"?size=240x240&margin=8&data={http_parse.quote(pairing_url, safe='')}"
        ),
    }


def get_public_server_targets(port=None):
    if port is None:
        port = get_request_server_port()

    targets = []
    seen = set()

    def add_target(host_value, override_port=None):
        normalized_host = str(host_value or "").strip()
        if not normalized_host:
            return
        target_port = int(override_port or port)
        key = (normalized_host.lower(), target_port)
        if key in seen:
            return
        formatted_host = format_host_for_url(normalized_host)
        base_url = f"http://{formatted_host}:{target_port}"
        target = build_target_descriptor(
            base_url,
            host=normalized_host,
            port=target_port,
            display_address=f"{formatted_host}:{target_port}",
        )
        if target:
            targets.append(target)
            seen.add(key)

    configured_base_url = str(os.getenv("PYPONDO_PUBLIC_BASE_URL", "")).strip()
    if configured_base_url:
        try:
            parsed = http_parse.urlsplit(configured_base_url)
            configured_host = (parsed.hostname or "").strip()
            configured_port = parsed.port
            key = (configured_host.lower(), int(configured_port or 0))
            if configured_host and key not in seen:
                target = build_target_descriptor(
                    configured_base_url,
                    host=configured_host,
                    port=configured_port,
                    display_address=configured_base_url.rstrip("/"),
                )
                if target:
                    targets.append(target)
                    seen.add(key)
        except Exception:
            pass

    forwarded_host = request.headers.get("X-Forwarded-Host", "").strip()
    if forwarded_host:
        first_host = forwarded_host.split(",")[0].strip()
        host_only, forwarded_port = split_host_and_port(first_host)
        add_target(host_only, forwarded_port or port)

    request_host = (request.host or "").strip()
    if request_host:
        host_only, request_port = split_host_and_port(request_host)
        add_target(host_only, request_port or port)

    return targets


def get_mobile_pairing_targets(port=None):
    if port is None:
        port = get_request_server_port()

    targets = []
    seen = set()

    def add_target(host_value, override_port=None):
        normalized_host = str(host_value or "").strip()
        if not normalized_host:
            return
        target_port = int(override_port or port)
        key = (normalized_host.lower(), target_port)
        if key in seen:
            return
        formatted_host = format_host_for_url(normalized_host)
        base_url = f"http://{formatted_host}:{target_port}"
        target = build_target_descriptor(
            base_url,
            host=normalized_host,
            port=target_port,
            display_address=f"{formatted_host}:{target_port}",
        )
        if target:
            targets.append(target)
            seen.add(key)

    for target in get_public_server_targets(port):
        target_port = 0
        try:
            parsed = http_parse.urlsplit(target.get("base_url", ""))
            target_port = int(parsed.port or 0)
        except Exception:
            target_port = 0
        key = (str(target.get("ip", "")).strip().lower(), target_port)
        if key not in seen:
            targets.append(target)
            seen.add(key)

    ordered_ips = []
    primary_ipv4 = get_primary_local_ipv4()
    if primary_ipv4:
        ordered_ips.append(primary_ipv4)

    for ip in get_local_lan_addresses():
        normalized = normalize_lan_ip(ip)
        if normalized and normalized not in ordered_ips:
            ordered_ips.append(normalized)

    fallback_ip = get_client_ip_from_request()
    if fallback_ip and fallback_ip not in ordered_ips:
        ordered_ips.append(fallback_ip)

    for ip in ordered_ips:
        add_target(ip, port)

    return targets


def build_public_server_payload():
    server_port = get_request_server_port()
    pairing_targets = get_mobile_pairing_targets(server_port)
    primary_target = pairing_targets[0] if pairing_targets else None

    if primary_target is None:
        fallback_ip = get_client_ip_from_request() or "127.0.0.1"
        fallback_host = format_host_for_url(fallback_ip)
        fallback_base_url = f"http://{fallback_host}:{server_port}"
        primary_target = {
            "ip": fallback_ip,
            "address": f"{fallback_host}:{server_port}",
            "base_url": fallback_base_url,
            "pairing_url": f"{fallback_base_url}/api/mobile/pairing",
        }
        pairing_targets = [primary_target]

    return {
        "ok": True,
        "app_version": APP_VERSION,
        "server_hostname": socket.gethostname(),
        "server_ip": primary_target["ip"],
        "server_port": server_port,
        "server_address": primary_target["address"],
        "server_base_url": primary_target["base_url"],
        "server_ips": [target["ip"] for target in pairing_targets],
        "server_addresses": [target["address"] for target in pairing_targets],
        "server_urls": [target["base_url"] for target in pairing_targets],
        "pairing_url": primary_target["pairing_url"],
    }


def charge_elapsed_for_session(session, now=None):
    """Charge for elapsed time since last_charged_at (or start_time). Returns the charge amount."""
    if now is None:
        now = datetime.now()
    if session.end_time is not None:
        return 0.0
    user = db.session.get(User, session.user_id)
    if not user:
        return 0.0

    last_charged = session.last_charged_at or session.start_time
    elapsed_seconds = (now - last_charged).total_seconds()
    if elapsed_seconds < 1:  # minimum 1 second for live charging every 3 seconds
        return 0.0

    hours_played = elapsed_seconds / 3600.0
    charge = round(hours_played * HOURLY_RATE, 2)
    if charge > user.pondo:
        charge = round(user.pondo, 2)
    user.pondo -= charge
    session.cost = (session.cost or 0.0) + charge
    session.last_charged_at = now
    return charge

def finalize_session(session):
    if not session or session.end_time is not None:
        return 0.0
    now = datetime.now()
    charge = charge_elapsed_for_session(session, now)
    session.end_time = now
    pc = db.session.get(PC, session.pc_id)
    if pc:
        pc.is_occupied = False
    return charge


def get_session_current_cost(session, now=None):
    if not session:
        return 0.0
    if now is None:
        now = datetime.now()

    current_cost = float(session.cost or 0.0)
    if session.end_time is not None:
        return round(current_cost, 2)

    last_charged = session.last_charged_at or session.start_time
    if not last_charged:
        return round(current_cost, 2)

    elapsed_seconds = max((now - last_charged).total_seconds(), 0.0)
    current_cost += (elapsed_seconds / 3600.0) * HOURLY_RATE
    return round(current_cost, 2)


def parse_topup_amount(raw):
    try:
        amount = Decimal(str(raw))
    except (InvalidOperation, TypeError):
        return None
    if amount <= 0 or amount > Decimal(str(MAX_TOPUP_AMOUNT)):
        return None
    return float(amount.quantize(Decimal("0.01")))


def create_payment_request(user, amount, source="web", provider="online_request", status="pending", external_id=None):
    external_id = (external_id or "").strip() or f"REQ-{uuid.uuid4().hex[:16].upper()}"
    tx = PaymentTransaction(
        user_id=user.id,
        provider=provider,
        external_id=external_id,
        amount=amount,
        currency=TOPUP_CURRENCY,
        status=status
    )
    db.session.add(tx)
    db.session.add(AdminLog(
        admin_name=user.username,
        action=(
            f"Payment request ({source}) created: {external_id}, provider={provider}, "
            f"status={status}, amount={amount:.2f} {TOPUP_CURRENCY}"
        )
    ))
    db.session.commit()
    return tx


def create_online_payment_request(user, amount, source="web"):
    return create_payment_request(user, amount, source=source)


def get_recent_payment_requests(user_id, limit=5):
    try:
        max_rows = max(1, int(limit))
    except Exception:
        max_rows = 5
    return PaymentTransaction.query.filter_by(user_id=user_id).order_by(PaymentTransaction.created_at.desc()).limit(max_rows).all()


def get_all_payment_requests(limit=200):
    try:
        max_rows = max(1, int(limit))
    except Exception:
        max_rows = 200
    return PaymentTransaction.query.order_by(PaymentTransaction.created_at.desc()).limit(max_rows).all()


def confirm_payment_transaction(tx, admin_user):
    if not tx:
        return False, "Payment transaction not found."
    if tx.status == "paid":
        return False, "Payment is already confirmed."
    if tx.status == "cancelled":
        return False, "Payment is cancelled and cannot be confirmed."

    user = db.session.get(User, tx.user_id)
    if not user:
        return False, "User for this payment was not found."

    user.pondo += float(tx.amount or 0.0)
    tx.status = "paid"
    tx.credited_at = datetime.now()
    db.session.add(AdminLog(
        admin_name=admin_user.username,
        action=(
            f"Confirmed payment {tx.external_id} for {user.username}, "
            f"provider={tx.provider}, amount={tx.amount:.2f} {tx.currency}"
        )
    ))
    db.session.commit()
    return True, f"Confirmed payment {tx.external_id} for {user.username}."


def redirect_for_current_user_page():
    referrer = (request.referrer or "").strip().lower()

    if current_user.is_admin:
        return redirect(url_for('index'))

    if "/client/bookings" in referrer:
        return redirect(url_for('client_bookings'))
    if "/client/desktop" in referrer:
        return redirect(url_for('client_desktop'))

    if user_has_positive_balance(current_user):
        return redirect(url_for('client_desktop'))
    return redirect(url_for('client_bookings'))


def resolve_safe_return_to(raw_value):
    target = str(raw_value or "").strip()
    if target.startswith("/") and not target.startswith("//"):
        return target
    return None


def get_latest_bundle_path(prefix):
    cache_dir = os.path.join(basedir, "package_cache")
    if not os.path.isdir(cache_dir):
        return None

    candidates = []
    for file_name in os.listdir(cache_dir):
        if not file_name.startswith(prefix) or not file_name.endswith(".zip"):
            continue
        full_path = os.path.join(cache_dir, file_name)
        try:
            mtime = os.path.getmtime(full_path)
        except OSError:
            continue
        candidates.append((mtime, full_path))

    if not candidates:
        return None
    return max(candidates, key=lambda row: row[0])[1]


def get_desktop_download_artifact():
    dist_exe = os.path.join(basedir, "dist", "PyPondo.exe")
    if os.path.exists(dist_exe):
        return dist_exe, "PyPondo.exe"

    dist_zip = os.path.join(basedir, "dist", "PyPondo-windows.zip")
    if os.path.exists(dist_zip):
        return dist_zip, "PyPondo-windows.zip"

    all_in_one_zip = get_latest_bundle_path("all_in_one_bundle-")
    if all_in_one_zip:
        return all_in_one_zip, "pypondo-app-bundle.zip"

    return None


def get_android_build_kit_files():
    files = []
    candidates = [
        ("main.py", "main.py"),
        ("buildozer.spec", "buildozer.spec"),
        ("buildozer_shim.py", "buildozer_shim.py"),
        ("build_android.bat", "build_android.bat"),
        ("build_android_safe.bat", "build_android_safe.bat"),
        ("build_android.ps1", "build_android.ps1"),
        ("build_android_wsl.sh", "build_android_wsl.sh"),
        ("MOBILE_README.md", "MOBILE_README.md"),
        (os.path.join("assets", "pypondo-icon-256.png"), os.path.join("assets", "pypondo-icon-256.png")),
        (os.path.join("assets", "pypondo.ico"), os.path.join("assets", "pypondo.ico")),
    ]

    for relative_path, archive_name in candidates:
        full_path = os.path.join(basedir, relative_path)
        if os.path.exists(full_path):
            files.append((full_path, archive_name.replace("\\", "/")))
    return files


def build_android_build_kit_notes():
    return "\n".join([
        "PyPondo Android Build Kit",
        "=========================",
        "",
        "This bundle contains the mobile Kivy app source and Android build scripts.",
        "",
        "Quick build path from Windows PowerShell:",
        "1. Install WSL Ubuntu and reboot if needed: wsl --install -d Ubuntu",
        "2. From Windows in this folder, run: build_android_safe.bat",
        "3. Or run: powershell -ExecutionPolicy Bypass -File .\\build_android.ps1",
        "4. Do not run build_android_wsl.sh directly from PowerShell.",
        "",
        "Quick build path from Linux/WSL shell:",
        "1. Open Ubuntu or another Linux shell in this folder.",
        "2. Run: chmod +x build_android_wsl.sh && ./build_android_wsl.sh",
        "",
        "The generated APK will be placed in bin/ and can then be copied back",
        "into the main PyPondo project under PythonProject/bin/ so the admin",
        "dashboard can serve it directly as DOWNLOAD APK.",
        "",
        f"Expected APK filename pattern: pypondo_mobile-{APP_VERSION}-debug.apk",
    ])


def add_android_build_kit_to_archive(archive, root_prefix="PyPondo-Android-build-kit"):
    normalized_root = str(root_prefix or "").strip("/\\")
    for full_path, archive_name in get_android_build_kit_files():
        target_name = archive_name if not normalized_root else f"{normalized_root}/{archive_name}"
        archive.write(full_path, arcname=target_name)

    notes_name = "README_FIRST.txt" if not normalized_root else f"{normalized_root}/README_FIRST.txt"
    archive.writestr(notes_name, build_android_build_kit_notes())


def build_android_build_kit_bundle():
    bundle_stream = io.BytesIO()
    with zipfile.ZipFile(bundle_stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        add_android_build_kit_to_archive(archive)
    bundle_stream.seek(0)
    return bundle_stream


def build_combined_download_bundle(desktop_artifact, apk_path=None):
    desktop_path, desktop_name = desktop_artifact
    bundle_stream = io.BytesIO()

    with zipfile.ZipFile(bundle_stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(desktop_path, arcname=desktop_name)
        if apk_path:
            archive.write(apk_path, arcname="PyPondo-Android.apk")
        else:
            add_android_build_kit_to_archive(archive)

    bundle_stream.seek(0)
    return bundle_stream


def apk_path_is_valid(apk_path):
    if not os.path.isfile(apk_path):
        return False
    if os.path.getsize(apk_path) < 512 * 1024:
        return False

    try:
        with zipfile.ZipFile(apk_path, 'r') as apk:
            names = apk.namelist()
            if 'AndroidManifest.xml' not in names or 'classes.dex' not in names:
                return False
            with apk.open('AndroidManifest.xml') as manifest_file:
                header = manifest_file.read(16)
                if header.startswith(b'<?xml') or b'<manifest' in header:
                    return False
    except (zipfile.BadZipFile, OSError):
        return False

    return True


def get_latest_apk_path():
    candidates = []

    for folder in (os.path.join(basedir, "bin"), os.path.join(basedir, "package_cache")):
        if not os.path.isdir(folder):
            continue
        for file_name in os.listdir(folder):
            if not file_name.lower().endswith(".apk"):
                continue
            full_path = os.path.join(folder, file_name)
            if not apk_path_is_valid(full_path):
                continue
            try:
                mtime = os.path.getmtime(full_path)
            except OSError:
                continue
            candidates.append((mtime, full_path))

    if not candidates:
        return None
    return max(candidates, key=lambda row: row[0])[1]


def is_android_apk_ready():
    return bool(get_latest_apk_path())


def is_kiosk_mode_enabled():
    return str(os.getenv("PYPONDO_KIOSK_MODE", "0")).strip().lower() in {"1", "true", "yes"}


def user_has_positive_balance(user):
    try:
        return float(getattr(user, "pondo", 0.0)) > 0.0
    except Exception:
        return False


def post_login_endpoint_for_user(user):
    if getattr(user, "is_admin", False):
        return "index"
    if user_has_positive_balance(user):
        return "client_desktop"
    return "client_bookings"


def resolve_safe_next_url():
    next_url = (request.args.get("next") or "").strip()
    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return None


def get_request_data():
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return data
    if request.form:
        return request.form
    if request.args:
        return request.args
    return {}


def get_request_value(name, default=None):
    payload = get_request_data()
    if hasattr(payload, "get"):
        return payload.get(name, default)
    return default


def get_mobile_user_from_request():
    raw_user_id = get_request_value("user_id")
    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        return None, (jsonify({"ok": False, "error": "user_id is required"}), 400)

    user = db.session.get(User, user_id)
    if not user:
        return None, (jsonify({"ok": False, "error": "User not found"}), 404)
    if user.is_admin:
        return None, (jsonify({"ok": False, "error": "Admin accounts are not supported by the mobile client"}), 403)
    return user, None


def serialize_mobile_booking(booking, now_dt=None):
    if now_dt is None:
        now_dt = datetime.now()

    booking_dt = parse_booking_datetime(
        normalize_booking_date_value(booking.booking_date),
        normalize_time_slot_value(booking.time_slot)
    )
    status = "confirmed"
    if booking_dt and booking_dt < now_dt:
        status = "expired"

    return {
        "id": booking.id,
        "pc_id": booking.pc_id,
        "pc_name": booking.pc.name if booking.pc else f"PC-{booking.pc_id}",
        "date": booking.booking_date or now_dt.strftime("%Y-%m-%d"),
        "time": normalize_time_slot_value(booking.time_slot) or booking.time_slot,
        "status": status
    }


def get_mobile_updates_feed():
    newest_timestamp = None
    for relative_path in ("app.py", "desktop_app.py", "main.py"):
        target = os.path.join(basedir, relative_path)
        if not os.path.exists(target):
            continue
        try:
            candidate = datetime.fromtimestamp(os.path.getmtime(target)).isoformat()
        except OSError:
            continue
        if newest_timestamp is None or candidate > newest_timestamp:
            newest_timestamp = candidate

    timestamp = newest_timestamp or datetime.now().isoformat()
    return [
        {
            "version": APP_VERSION,
            "update_type": "major",
            "title": "PyPondo core system ready",
            "description": "Admin, desktop, and mobile booking flows are available from the same server.",
            "timestamp": timestamp
        },
        {
            "version": APP_VERSION,
            "update_type": "feature",
            "title": "Mobile API enabled",
            "description": "The server now exposes mobile login, bookings, PC availability, top-up, and assistant endpoints.",
            "timestamp": timestamp
        },
        {
            "version": APP_VERSION,
            "update_type": "minor",
            "title": "LAN monitoring active",
            "description": "Client discovery, PC mapping, and live session monitoring remain available in the admin dashboard.",
            "timestamp": timestamp
        }
    ]


def build_mobile_assistant_response(user, message):
    text_value = str(message or "").strip()
    lowered = text_value.lower()

    bookings = Booking.query.filter_by(user_id=user.id).order_by(Booking.booking_date.asc(), Booking.time_slot.asc()).all()
    upcoming_booking = None
    now_dt = datetime.now()
    for booking in bookings:
        booking_dt = parse_booking_datetime(
            normalize_booking_date_value(booking.booking_date),
            normalize_time_slot_value(booking.time_slot)
        )
        if booking_dt and booking_dt >= now_dt:
            upcoming_booking = booking
            break

    if any(term in lowered for term in ("balance", "pondo", "credit", "credits")):
        return f"Your current balance is PHP {float(user.pondo or 0.0):.2f}."

    if any(term in lowered for term in ("booking", "reservation", "book")):
        if upcoming_booking:
            return (
                f"Your next booking is for {upcoming_booking.pc.name} on "
                f"{upcoming_booking.booking_date} at {normalize_time_slot_value(upcoming_booking.time_slot) or upcoming_booking.time_slot}."
            )
        if bookings:
            return f"You have {len(bookings)} booking record(s), but none are upcoming right now."
        return "You do not have any bookings yet. Open the Bookings tab to reserve a PC."

    if any(term in lowered for term in ("pc", "pcs", "available", "computer")):
        pcs = PC.query.order_by(PC.id.asc()).all()
        available_count = sum(1 for pc in pcs if not get_pc_booking_usage_state(pc, now_dt=now_dt)["in_use"])
        return f"There are {available_count} available PC(s) right now."

    if any(term in lowered for term in ("top up", "topup", "payment", "gcash", "card", "cash")):
        return "Use the Top Up tab to submit a request. Cash, GCash, and card requests are saved for admin confirmation."

    active_session = Session.query.filter_by(user_id=user.id, end_time=None).order_by(Session.start_time.desc()).first()
    if any(term in lowered for term in ("session", "playing", "time")):
        if active_session and active_session.start_time:
            elapsed = max((now_dt - active_session.start_time).total_seconds(), 0)
            return (
                f"Your session has been running for {format_duration_compact(elapsed)} "
                f"and has cost PHP {float(active_session.cost or 0.0):.2f} so far."
            )
        return "You do not have an active session right now."

    return (
        "I can help with your balance, bookings, available PCs, top-up requests, and session status. "
        "Try asking about any of those."
    )


@app.before_request
def bootstrap_schema():
    if not getattr(app, "_schema_ready", False):
        db.create_all()
        ensure_pc_lan_ip_column()
        ensure_booking_date_column()
        ensure_session_last_charged_at_column()
        ensure_core_seed_data()
        app._schema_ready = True


@app.before_request
def allow_mobile_api_preflight():
    normalized_path = (request.path or "").rstrip("/")
    if request.method != "OPTIONS":
        return None
    if normalized_path == "/api/server-info" or normalized_path == "/api/mobile/pairing" or normalized_path.startswith("/api/mobile/"):
        response = jsonify({"ok": True})
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Accept, X-Requested-With"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response
    return None


@app.after_request
def add_mobile_api_cors_headers(response):
    normalized_path = (request.path or "").rstrip("/")
    if normalized_path == "/api/server-info" or normalized_path == "/api/mobile/pairing" or normalized_path.startswith("/api/mobile/"):
        response.headers.setdefault("Access-Control-Allow-Origin", "*")
        response.headers.setdefault("Access-Control-Allow-Headers", "Content-Type, Accept, X-Requested-With")
        response.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    return response


# --- Auth Routes ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username taken.', 'error')
            return redirect(url_for('register'))
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Account created!', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/api/server-info')
def api_server_info():
    """Public API endpoint for clients to discover admin server information."""
    return jsonify(build_public_server_payload()), 200


@app.route('/api/mobile/pairing')
def api_mobile_pairing():
    payload = build_public_server_payload()
    payload["pairing_mode"] = "lan_qr"
    return jsonify(payload), 200


@app.route('/api/mobile/login', methods=['POST'])
def api_mobile_login():
    username = str(get_request_value("username", "")).strip()
    password = str(get_request_value("password", "")).strip()
    if not username or not password:
        return jsonify({"ok": False, "error": "Username and password are required"}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"ok": False, "error": "Invalid credentials"}), 401
    if user.is_admin:
        return jsonify({"ok": False, "error": "Admin accounts are not supported by the mobile client"}), 403

    return jsonify({
        "ok": True,
        "user_id": user.id,
        "username": user.username,
        "balance": round(float(user.pondo or 0.0), 2),
        "app_version": APP_VERSION
    }), 200


@app.route('/api/mobile/bookings', methods=['GET'])
def api_mobile_bookings():
    user, error = get_mobile_user_from_request()
    if error:
        return error

    now_dt = datetime.now()
    bookings = Booking.query.filter_by(user_id=user.id).order_by(Booking.booking_date.asc(), Booking.time_slot.asc()).all()
    return jsonify({
        "ok": True,
        "bookings": [serialize_mobile_booking(booking, now_dt=now_dt) for booking in bookings]
    }), 200


@app.route('/api/mobile/pcs', methods=['GET'])
def api_mobile_pcs():
    now_dt = datetime.now()
    pcs = PC.query.order_by(PC.id.asc()).all()
    payload = []
    for pc in pcs:
        usage_state = get_pc_booking_usage_state(pc, now_dt=now_dt)
        payload.append({
            "id": pc.id,
            "name": pc.name,
            "is_occupied": usage_state["in_use"],
            "lan_ip": pc.lan_ip,
            "online": usage_state["online_now"]
        })
    return jsonify({"ok": True, "pcs": payload}), 200


@app.route('/api/mobile/updates', methods=['GET'])
def api_mobile_updates():
    return jsonify({"ok": True, "updates": get_mobile_updates_feed()}), 200


@app.route('/api/mobile/book', methods=['POST'])
def api_mobile_book():
    user, error = get_mobile_user_from_request()
    if error:
        return error

    try:
        pc_id = int(get_request_value("pc_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "pc_id is required"}), 400

    pc = db.session.get(PC, pc_id)
    if not pc:
        return jsonify({"ok": False, "error": "Selected PC was not found"}), 404

    booking_date = normalize_booking_date_value(get_request_value("date") or get_request_value("booking_date"))
    if not booking_date:
        return jsonify({"ok": False, "error": "Invalid booking date"}), 400

    time_slot = normalize_time_slot_value(get_request_value("time") or get_request_value("time_slot"))
    if not time_slot:
        return jsonify({"ok": False, "error": "Invalid booking time"}), 400

    booking_dt = parse_booking_datetime(booking_date, time_slot)
    if not booking_dt:
        return jsonify({"ok": False, "error": "Invalid booking schedule"}), 400

    now_dt = datetime.now()
    lead_cutoff = now_dt + timedelta(minutes=BOOKING_LEAD_MINUTES)
    usage_state = get_pc_booking_usage_state(pc, now_dt=now_dt)
    if booking_dt < lead_cutoff:
        if usage_state["in_use"]:
            return jsonify({
                "ok": False,
                "error": f"{pc.name} is currently in use. Choose a time at least {BOOKING_LEAD_MINUTES} minutes from now."
            }), 400
        return jsonify({
            "ok": False,
            "error": f"Bookings must be scheduled at least {BOOKING_LEAD_MINUTES} minutes ahead."
        }), 400

    conflicting_booking = find_conflicting_booking(pc.id, booking_date, time_slot)
    if conflicting_booking:
        if conflicting_booking.user_id == user.id:
            error_message = f"You already have a booking for {pc.name} on {booking_date} at {time_slot}."
        else:
            error_message = f"Another user already booked {pc.name} on {booking_date} at {time_slot}."
        return jsonify({"ok": False, "error": error_message}), 409

    new_booking = Booking(user_id=user.id, pc_id=pc.id, booking_date=booking_date, time_slot=time_slot)
    db.session.add(new_booking)
    db.session.commit()
    return jsonify({
        "ok": True,
        "message": "Booking successful",
        "booking": serialize_mobile_booking(new_booking, now_dt=now_dt)
    }), 201


@app.route('/api/mobile/topup', methods=['POST'])
def api_mobile_topup():
    user, error = get_mobile_user_from_request()
    if error:
        return error

    amount = parse_topup_amount(get_request_value("amount"))
    if amount is None:
        return jsonify({"ok": False, "error": "Invalid top-up amount"}), 400

    tx = create_online_payment_request(user, amount, source="mobile")
    return jsonify({
        "ok": True,
        "message": f"Top-up request saved: {tx.external_id}. Waiting for admin confirmation.",
        "payment_id": tx.id,
        "external_id": tx.external_id,
        "amount": round(float(tx.amount or 0.0), 2),
        "balance": round(float(user.pondo or 0.0), 2)
    }), 201


@app.route('/api/mobile/ai-chat', methods=['POST'])
def api_mobile_ai_chat():
    user, error = get_mobile_user_from_request()
    if error:
        return error

    message = str(get_request_value("message", "")).strip()
    if not message:
        return jsonify({"ok": False, "error": "message is required"}), 400

    return jsonify({
        "ok": True,
        "response": build_mobile_assistant_response(user, message)
    }), 200


@app.route('/api/charge-balance', methods=['POST'])
@login_required
def api_charge_balance():
    if current_user.is_admin:
        return jsonify(ok=False, message='Admins are not charged.'), 403
    if not user_has_positive_balance(current_user):
        return jsonify(ok=False, message='Insufficient balance.'), 402

    active_session = Session.query.filter_by(user_id=current_user.id, end_time=None).order_by(Session.start_time.desc()).first()
    if not active_session:
        active_session = Session(user_id=current_user.id, last_charged_at=datetime.now())
        db.session.add(active_session)
        db.session.commit()
        return jsonify(ok=True, charge=0.0, balance=current_user.pondo, message='Session started.')

    charge = charge_elapsed_for_session(active_session, datetime.now())
    db.session.commit()
    return jsonify(ok=True, charge=charge, balance=current_user.pondo)


@app.route('/api/session-status', methods=['GET'])
@login_required
def api_session_status():
    if current_user.is_admin:
        return jsonify(ok=False, message='Admins do not have sessions.'), 403

    active_session = Session.query.filter_by(user_id=current_user.id, end_time=None).order_by(Session.start_time.desc()).first()

    if not active_session:
        return jsonify(ok=True, has_session=False, balance=current_user.pondo, cost=0.0, start_time=None)

    # Calculate current cost
    now = datetime.now()
    if active_session.last_charged_at:
        elapsed_seconds = (now - active_session.last_charged_at).total_seconds()
        additional_cost = (elapsed_seconds / 3600.0) * HOURLY_RATE
        current_cost = (active_session.cost or 0.0) + additional_cost
    else:
        current_cost = active_session.cost or 0.0

    return jsonify(
        ok=True,
        has_session=True,
        balance=current_user.pondo,
        cost=round(current_cost, 2),
        start_time=active_session.start_time.isoformat() if active_session.start_time else None,
        last_charged_at=active_session.last_charged_at.isoformat() if active_session.last_charged_at else None
    )


@app.route('/favicon.ico')
def favicon():
    favicon_path = os.path.join(assets_dir, 'pypondo.ico')
    if os.path.exists(favicon_path):
        return send_file(favicon_path, mimetype='image/x-icon', max_age=86400)
    return '', 404


@app.route('/app-icon.png')
def app_icon():
    icon_path = os.path.join(assets_dir, 'pypondo-icon-256.png')
    if os.path.exists(icon_path):
        return send_file(icon_path, mimetype='image/png', max_age=86400)
    return '', 404


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(post_login_endpoint_for_user(current_user)))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            if not user.is_admin:
                active_session = Session.query.filter_by(user_id=user.id, end_time=None).order_by(Session.start_time.desc()).first()
                if active_session:
                    cost = finalize_session(active_session)
                    db.session.commit()
                    flash(f'Previous session ended. Cost: ₱{cost:.2f}.', 'info')
                if user_has_positive_balance(user):
                    new_session = Session(user_id=user.id, last_charged_at=datetime.now())
                    db.session.add(new_session)
                    db.session.commit()
            safe_next = resolve_safe_next_url()
            if safe_next:
                return redirect(safe_next)
            return redirect(url_for(post_login_endpoint_for_user(user)))
        else:
            flash('Invalid credentials', 'error')
    return render_template('login.html', kiosk_mode=is_kiosk_mode_enabled())


@app.route('/logout')
@login_required
def logout():
    active_session = Session.query.filter_by(user_id=current_user.id, end_time=None).order_by(Session.start_time.desc()).first()
    if active_session:
        cost = finalize_session(active_session)
        db.session.commit()
        flash(f'Session ended. Cost: ₱{cost:.2f}.', 'info')
    logout_user()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))


# --- Main Routes ---

@app.route('/client')
@login_required
def client_entry():
    if current_user.is_admin:
        return redirect(url_for('index'))
    if user_has_positive_balance(current_user):
        return redirect(url_for('client_desktop'))
    return redirect(url_for('client_bookings'))


@app.route('/client/desktop')
@login_required
def client_desktop():
    if current_user.is_admin:
        return redirect(url_for('index'))
    if not user_has_positive_balance(current_user):
        flash('Insufficient balance. Please reserve first or top up.', 'error')
        return redirect(url_for('client_bookings'))

    active_session = Session.query.filter_by(user_id=current_user.id, end_time=None).order_by(Session.start_time.desc()).first()
    recent_payments = get_recent_payment_requests(current_user.id)
    return render_template(
        'client_desktop.html',
        active_session=active_session,
        recent_payments=recent_payments,
        kiosk_mode=is_kiosk_mode_enabled(),
        hourly_rate=HOURLY_RATE
    )


@app.route('/client/bookings')
@login_required
def client_bookings():
    if current_user.is_admin:
        return redirect(url_for('view_bookings'))

    now_dt = datetime.now()
    pcs = PC.query.order_by(PC.id.asc()).all()
    annotate_booking_usage_for_pcs(pcs, now_dt=now_dt)
    my_bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.id.desc()).all()
    recent_payments = get_recent_payment_requests(current_user.id)
    return render_template(
        'client_bookings.html',
        pcs=pcs,
        bookings=my_bookings,
        recent_payments=recent_payments,
        today_date=now_dt.strftime("%Y-%m-%d"),
        booking_lead_minutes=BOOKING_LEAD_MINUTES,
        hourly_rate=HOURLY_RATE,
        kiosk_mode=is_kiosk_mode_enabled()
    )


@app.route('/client/bookings/delete/<int:id>')
@login_required
def client_delete_booking(id):
    if current_user.is_admin:
        return redirect(url_for('view_bookings'))

    booking = Booking.query.filter_by(id=id, user_id=current_user.id).first()
    if booking:
        db.session.delete(booking)
        db.session.commit()
        flash('Booking removed.', 'info')
    return redirect(url_for('client_bookings'))


@app.route('/')
@login_required
def index():
    if not current_user.is_admin:
        if user_has_positive_balance(current_user):
            return redirect(url_for('client_desktop'))
        return redirect(url_for('client_bookings'))

    pcs = PC.query.all()
    android_apk_ready = is_android_apk_ready() if current_user.is_admin else False
    users = User.query.all() if current_user.is_admin else [current_user]
    active_sessions = Session.query.filter_by(end_time=None).order_by(Session.start_time.asc()).all()
    recent_payments = get_recent_payment_requests(current_user.id)
    local_ips = get_local_lan_addresses() if current_user.is_admin else []
    mobile_pairing_targets = get_mobile_pairing_targets() if current_user.is_admin else []
    mobile_pairing_primary = mobile_pairing_targets[0] if mobile_pairing_targets else None
    public_tunnel = get_public_tunnel_snapshot() if current_user.is_admin else None
    lan_summary = build_primary_ipv4_network_summary() if current_user.is_admin else None
    gateway_scan = get_gateway_client_scan(non_blocking=True) if current_user.is_admin else None
    discovered_ips = [row.get("ip") for row in (gateway_scan.get("clients", []) if isinstance(gateway_scan, dict) else [])] if current_user.is_admin else []
    assigned_ips = {pc.lan_ip for pc in pcs if pc.lan_ip}
    online_window_seconds = get_agent_online_window_seconds()
    now_dt = datetime.now()
    pending_statuses = {"queued", "sent"}
    pending_counts = {}
    active_session_by_pc = {}
    active_session_user_by_id = {}
    for session in active_sessions:
        active_session_by_pc.setdefault(session.pc_id, session)
    if active_sessions:
        session_user_ids = sorted({session.user_id for session in active_sessions if session.user_id})
        for user in User.query.filter(User.id.in_(session_user_ids)).all():
            active_session_user_by_id[user.id] = user

    for pc in pcs:
        active_session = active_session_by_pc.get(pc.id)
        online_now = is_pc_online(pc, now_dt, online_window_seconds)
        effective_in_use = bool(pc.is_occupied or active_session or online_now)
        usage_started_at = None
        usage_source = None
        if active_session:
            usage_started_at = active_session.start_time
            usage_source = "session"
        elif online_now:
            usage_started_at = pc.online_since_at or pc.last_agent_seen_at
            usage_source = "online"
        elif pc.is_occupied:
            usage_source = "occupied"

        pc.dashboard_session = active_session
        pc.dashboard_session_user = active_session_user_by_id.get(active_session.user_id) if active_session else None
        pc.dashboard_session_username = (
            active_session_user_by_id.get(active_session.user_id).username
            if active_session and active_session_user_by_id.get(active_session.user_id) else None
        )
        pc.dashboard_session_current_cost = get_session_current_cost(active_session, now_dt) if active_session else None
        pc.dashboard_online = online_now
        pc.dashboard_in_use = effective_in_use
        pc.dashboard_usage_source = usage_source
        pc.dashboard_usage_started_text = usage_started_at.strftime('%Y-%m-%d %H:%M:%S') if usage_started_at else None
        pc.dashboard_usage_duration_text = (
            format_duration_compact((now_dt - usage_started_at).total_seconds())
            if usage_started_at else None
        )

    if current_user.is_admin:
        for cmd in LanCommand.query.filter(LanCommand.status.in_(list(pending_statuses))).all():
            pending_counts[cmd.pc_name] = pending_counts.get(cmd.pc_name, 0) + 1

    agent_status = []
    if current_user.is_admin:
        mapped_ips = set()
        for pc in pcs:
            last_seen = pc.last_agent_seen_at
            is_online = is_pc_online(pc, now_dt, online_window_seconds)
            if last_seen:
                age_seconds = int(max((now_dt - last_seen).total_seconds(), 0))
                if age_seconds < 60:
                    seen_text = f"{age_seconds}s ago"
                else:
                    seen_text = f"{age_seconds // 60}m ago"
            else:
                seen_text = "never"
            agent_status.append({
                "pc_name": pc.name,
                "lan_ip": pc.lan_ip,
                "online": is_online,
                "seen_text": seen_text,
                "online_since_at": pc.online_since_at.isoformat() if pc.online_since_at else None,
                "queue_count": pending_counts.get(pc.name, 0)
            })
            if pc.lan_ip:
                mapped_ips.add(pc.lan_ip)

        for ip in discovered_ips:
            if ip in mapped_ips:
                continue
            agent_status.append({
                "pc_name": f"Unmapped-{ip}",
                "lan_ip": ip,
                "online": False,
                "seen_text": "never",
                "queue_count": 0
            })

    return render_template(
        'index.html',
        pcs=pcs,
        users=users,
        sessions=active_sessions,
        recent_payments=recent_payments,
        local_ips=local_ips,
        mobile_pairing_targets=mobile_pairing_targets,
        mobile_pairing_primary=mobile_pairing_primary,
        public_tunnel=public_tunnel,
        discovered_ips=discovered_ips,
        lan_summary=lan_summary,
        gateway_scan=gateway_scan,
        assigned_ips=assigned_ips,
        agent_status=agent_status,
        android_apk_ready=android_apk_ready,
        android_download_label="DOWNLOAD APK" if android_apk_ready else "DOWNLOAD BUILD KIT",
        android_download_note=(
            "Android APK is ready for direct download."
            if android_apk_ready else
            "APK is not built yet. This downloads the Android build kit with WSL/Linux build scripts."
        ),
        combined_download_label="DOWNLOAD DESKTOP + PHONE" if android_apk_ready else "DOWNLOAD DESKTOP + ANDROID KIT",
        today_date=datetime.now().strftime("%Y-%m-%d"),
        booking_lead_minutes=BOOKING_LEAD_MINUTES,
        hourly_rate=HOURLY_RATE,
        auto_charge_enabled=AUTO_CHARGE_ENABLED
    )


@app.route('/admin/public_route/start', methods=['POST'])
@login_required
def admin_start_public_route():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    local_port = int(os.getenv("APP_PORT", "5000"))
    ok, snapshot = start_public_tunnel(local_port)
    if ok and snapshot.get("url"):
        flash(f"Public mobile route ready: {snapshot['url']}", "success")
    else:
        flash(snapshot.get("error") or "Unable to create a public mobile route.", "error")
    return redirect(url_for('index'))


@app.route('/admin/public_route/stop', methods=['POST'])
@login_required
def admin_stop_public_route():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    terminate_public_tunnel()
    flash("Public mobile route stopped.", "info")
    return redirect(url_for('index'))


# --- ADMIN FEATURES ---

@app.route('/admin/download_app')
@login_required
def admin_download_app():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    desktop_artifact = get_desktop_download_artifact()
    if desktop_artifact:
        apk_path = get_latest_apk_path()
        bundle_name = "PyPondo-desktop-and-phone.zip" if apk_path else "PyPondo-desktop-and-android-build-kit.zip"
        return send_file(
            build_combined_download_bundle(desktop_artifact, apk_path),
            as_attachment=True,
            download_name=bundle_name,
            mimetype="application/zip"
        )

    flash("No app bundle found. Build first using build_desktop_exe.bat.", "error")
    return redirect(url_for('index'))


@app.route('/admin/download_android_app')
@login_required
def admin_download_android_app():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    apk_path = get_latest_apk_path()
    if apk_path:
        return send_file(
            apk_path,
            as_attachment=True,
            download_name="PyPondo-Android.apk"
        )

    return send_file(
        build_android_build_kit_bundle(),
        as_attachment=True,
        download_name="PyPondo-Android-build-kit.zip",
        mimetype="application/zip"
    )


@app.route('/download/apk')
def download_apk():
    apk_path = get_latest_apk_path()
    if apk_path:
        return send_file(
            apk_path,
            as_attachment=True,
            download_name="PyPondo.apk"
        )

    return (
        "APK not available yet or the current package is not installable. "
        "Build the Android APK using the Capacitor project in PyPondoMobile/pypondo-web/android "
        "with JDK 11+ and place the resulting APK into bin/ or package_cache/."
    ), 404


@app.route('/add_pc')
@login_required
def add_pc():
    if not current_user.is_admin: return redirect(url_for('index'))

    # Auto-generate name based on count
    count = PC.query.count()
    new_name = f"PC-{count + 1}"

    new_pc = PC(name=new_name)
    db.session.add(new_pc)

    # Log it
    log = AdminLog(admin_name=current_user.username, action=f"Added new unit: {new_name}")
    db.session.add(log)

    db.session.commit()
    flash(f'Added {new_name} to the station list.', 'success')
    return redirect(url_for('index'))


@app.route('/bookings')
@login_required
def view_bookings():
    if not current_user.is_admin: return redirect(url_for('index'))
    bookings = Booking.query.all()
    return render_template('bookings.html', bookings=bookings)


@app.route('/delete_booking/<int:id>')
@login_required
def delete_booking(id):
    if not current_user.is_admin: return redirect(url_for('index'))
    booking = db.session.get(Booking, id)
    if booking:
        db.session.delete(booking)
        db.session.commit()
        flash('Booking cancelled/removed.', 'info')
    return redirect(url_for('view_bookings'))


@app.route('/logs')
@login_required
def view_logs():
    if not current_user.is_admin: return redirect(url_for('index'))
    logs = AdminLog.query.order_by(AdminLog.timestamp.desc()).all()
    return render_template('logs.html', logs=logs)


@app.route('/admin/payments')
@login_required
def admin_payments():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    payments = get_all_payment_requests()
    user_map = {
        user.id: user.username
        for user in User.query.filter(User.id.in_([tx.user_id for tx in payments])).all()
    } if payments else {}

    for tx in payments:
        tx.display_username = user_map.get(tx.user_id, f"User #{tx.user_id}")

    return render_template('payments.html', payments=payments)


@app.route('/admin/payments/confirm', methods=['POST'])
@login_required
def admin_confirm_payment():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    tx_id = request.form.get('payment_id', type=int)
    if not tx_id:
        flash('Select a payment first.', 'error')
        return redirect(url_for('admin_payments'))

    tx = db.session.get(PaymentTransaction, tx_id)
    ok, message = confirm_payment_transaction(tx, current_user)
    flash(message, 'success' if ok else 'error')
    return redirect(url_for('admin_payments'))


@app.route('/admin/terminate-system', methods=['POST'])
@login_required
def terminate_system():
    if not current_user.is_admin:
        return {'ok': False, 'error': 'Unauthorized'}, 403
    
    try:
        log = AdminLog(admin_name=current_user.username, action="Terminated client app")
        db.session.add(log)
        db.session.commit()
        return {'ok': True, 'message': 'Client app will terminate'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}, 500


@app.route('/admin/auto_assign_ips')
@login_required
def auto_assign_ips():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    discovered_ipv4 = get_assignable_pc_ipv4_addresses(online_only=True)
    detected_for_sync = set(discovered_ipv4)
    cleared = clear_undetected_pc_ips(detected_for_sync)

    if not discovered_ipv4 and not cleared:
        flash('No online LAN PCs detected from scan. Ensure client PCs are powered on and connected.', 'error')
        return redirect(url_for('index'))

    pcs = PC.query.order_by(PC.id.asc()).all()
    already_used = {pc.lan_ip for pc in pcs if pc.lan_ip}
    available = [ip for ip in discovered_ipv4 if ip not in already_used]

    assigned_count = 0
    for pc in pcs:
        if pc.lan_ip:
            continue
        if not available:
            break
        pc.lan_ip = available.pop(0)
        assigned_count += 1

    db.session.add(AdminLog(
        admin_name=current_user.username,
        action=f"Auto-assign LAN online sync: cleared {len(cleared)} offline/stale IP(s), assigned {assigned_count} online IP(s)"
    ))
    db.session.commit()
    flash(f'LAN online sync complete. Cleared {len(cleared)} offline/stale IP(s), assigned {assigned_count} online IP(s).', 'success')
    return redirect(url_for('index'))


@app.route('/admin/refresh_ips')
@login_required
def refresh_ips():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    discovered_ipv4 = get_assignable_pc_ipv4_addresses(online_only=True)
    detected_for_sync = set(discovered_ipv4)
    cleared = clear_undetected_pc_ips(detected_for_sync)

    db.session.add(AdminLog(
        admin_name=current_user.username,
        action=f"IP refresh scan: cleared {len(cleared)} offline/stale IP(s), found {len(discovered_ipv4)} online IP(s)"
    ))
    db.session.commit()

    flash(f'IP refresh complete. Cleared {len(cleared)} offline/stale IP(s). Found {len(discovered_ipv4)} online IP(s) available for assignment.', 'info')
    return redirect(url_for('index'))


@app.route('/admin/auto_charge/enable')
@login_required
def enable_auto_charge():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    global AUTO_CHARGE_ENABLED
    AUTO_CHARGE_ENABLED = True

    db.session.add(AdminLog(
        admin_name=current_user.username,
        action="Enabled automatic charging for active sessions"
    ))
    db.session.commit()

    flash('Automatic charging enabled. Users will now be charged automatically for active sessions.', 'success')
    return redirect(url_for('index'))


@app.route('/admin/auto_charge/disable')
@login_required
def disable_auto_charge():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    global AUTO_CHARGE_ENABLED
    AUTO_CHARGE_ENABLED = False

    db.session.add(AdminLog(
        admin_name=current_user.username,
        action="Disabled automatic charging for active sessions"
    ))
    db.session.commit()

    flash('Automatic charging disabled. Users will not be charged automatically.', 'warning')
    return redirect(url_for('index'))


@app.route('/admin/set_pc_ip/<int:pc_id>', methods=['POST'])
@login_required
def set_pc_ip(pc_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))

    pc = db.session.get(PC, pc_id)
    if not pc:
        flash('PC not found.', 'error')
        return redirect(url_for('index'))

    raw_ip = (request.form.get('lan_ip') or '').strip()
    if not raw_ip:
        pc.lan_ip = None
        db.session.add(AdminLog(admin_name=current_user.username, action=f"Cleared LAN IP for {pc.name}"))
        db.session.commit()
        flash(f'Cleared LAN IP for {pc.name}.', 'info')
        return redirect(url_for('index'))

    ip = normalize_lan_ip(raw_ip)
    if not ip:
        flash('Invalid IP address.', 'error')
        return redirect(url_for('index'))
    if ":" not in ip and ip in get_gateway_ipv4_set():
        flash('Gateway IP cannot be assigned to a PC.', 'error')
        return redirect(url_for('index'))

    in_use = PC.query.filter(PC.id != pc.id, PC.lan_ip == ip).first()
    if in_use:
        flash(f'IP already assigned to {in_use.name}.', 'error')
        return redirect(url_for('index'))

    pc.lan_ip = ip
    db.session.add(AdminLog(admin_name=current_user.username, action=f"Set LAN IP for {pc.name} to {ip}"))
    db.session.commit()
    flash(f'{pc.name} mapped to {ip}.', 'success')
    return redirect(url_for('index'))


@app.route('/admin/request_connect', methods=['POST'])
@login_required
def admin_request_connect():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    pc_id = request.form.get('pc_id', type=int)
    pc = db.session.get(PC, pc_id) if pc_id else None
    if not pc:
        flash('Invalid PC selected.', 'error')
        return redirect(url_for('index'))

    raw_ip = (request.form.get('connect_ip') or '').strip()
    connect_ip = normalize_lan_ip(raw_ip)
    if not connect_ip:
        flash('Invalid target LAN IP.', 'error')
        return redirect(url_for('index'))
    if ":" not in connect_ip and connect_ip in get_gateway_ipv4_set():
        flash('Gateway IP cannot be assigned to a PC target.', 'error')
        return redirect(url_for('index'))

    raw_port = (request.form.get('connect_port') or '').strip()
    connect_port = normalize_agent_port(raw_port) if raw_port else None
    if raw_port and connect_port is None:
        flash('Invalid agent port.', 'error')
        return redirect(url_for('index'))

    pc.lan_ip = connect_ip
    if connect_port is not None:
        pc.lan_port = connect_port

    db.session.add(AdminLog(
        admin_name=current_user.username,
        action=(
            f"Saved/connect target for {pc.name}: "
            f"{connect_ip}" + (f":{connect_port}" if connect_port else "")
        )
    ))
    db.session.commit()

    payload = {
        "requested_by": current_user.username,
        "target_ip": connect_ip,
        "target_port": connect_port or pc.lan_port or normalize_agent_port(os.getenv("LAN_AGENT_DEFAULT_PORT", "5001")) or 5001,
        "skip_user_approval": True,
    }
    ok, message = send_lan_command(pc.name, "connect_request", payload)

    db.session.add(AdminLog(
        admin_name=current_user.username,
        action=f"Connect request for {pc.name}: {message}"
    ))
    db.session.commit()

    flash(
        f"{pc.name} target saved to {connect_ip}" + (f":{connect_port}" if connect_port else "") + f". {message}",
        'success' if ok else 'error'
    )
    return redirect(url_for('index'))


@app.route('/admin/clear_pc_commands/<int:pc_id>', methods=['POST'])
@login_required
def admin_clear_pc_commands(pc_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))

    pc = db.session.get(PC, pc_id)
    if not pc:
        flash('PC not found.', 'error')
        return redirect(url_for('index'))

    pending_commands = LanCommand.query.filter(
        LanCommand.pc_name == pc.name,
        LanCommand.status.in_(["queued", "sent"])
    ).all()

    if not pending_commands:
        flash(f'No pending commands for {pc.name}.', 'info')
        return redirect(url_for('index'))

    now_dt = datetime.now()
    cleared_count = 0
    for cmd in pending_commands:
        cmd.status = "cancelled"
        cmd.completed_at = now_dt
        cmd.result_message = "Cancelled by admin"
        cleared_count += 1

    db.session.add(AdminLog(
        admin_name=current_user.username,
        action=f"Cleared {cleared_count} pending LAN command(s) for {pc.name}"
    ))
    db.session.commit()

    flash(f'Cleared {cleared_count} pending command(s) for {pc.name}.', 'success')
    return redirect(url_for('index'))


# --- SYSTEM FEATURES ---

@app.route('/pondo', methods=['GET', 'POST'])
@login_required
def manage_pondo():
    # allow admins to credit any account, regular users only their own
    if request.method == 'POST':
        if current_user.is_admin:
            username = request.form.get('username', '').strip()
            user = User.query.filter_by(username=username).first()
            if not user:
                flash('User not found.', 'error')
                return redirect(url_for('manage_pondo'))
        else:
            user = current_user

        try:
            amount = float(request.form['amount'])
        except Exception:
            flash('Invalid amount.', 'error')
            return redirect(url_for('manage_pondo'))

        user.pondo += amount
        if current_user.is_admin:
            log = AdminLog(admin_name=current_user.username, action=f"Added ₱{amount} to '{user.username}'")
            flash(f'Credits added to {user.username}!', 'success')
        else:
            log = AdminLog(admin_name=current_user.username, action=f"User {user.username} topped up ₱{amount}")
            flash('Your balance has been updated.', 'success')

        db.session.add(log)
        db.session.commit()
        return redirect(url_for('index'))

    return render_template('pondo.html')


@app.route('/book', methods=['POST'])
@login_required
def book_pc():
    pc_id = request.form.get('pc_id', type=int)
    if not pc_id:
        flash('Select a PC first.', 'error')
        return redirect_for_current_user_page()

    pc = db.session.get(PC, pc_id)
    if not pc:
        flash('Selected PC was not found.', 'error')
        return redirect_for_current_user_page()

    booking_date = normalize_booking_date_value(request.form.get('booking_date'))
    if not booking_date:
        flash('Invalid booking date.', 'error')
        return redirect_for_current_user_page()

    time_slot = normalize_time_slot_value(request.form.get('time_slot'))
    if not time_slot:
        flash('Invalid booking time.', 'error')
        return redirect_for_current_user_page()

    booking_dt = parse_booking_datetime(booking_date, time_slot)
    if not booking_dt:
        flash('Invalid booking schedule.', 'error')
        return redirect_for_current_user_page()

    now_dt = datetime.now()
    lead_cutoff = now_dt + timedelta(minutes=BOOKING_LEAD_MINUTES)
    usage_state = get_pc_booking_usage_state(pc, now_dt=now_dt)

    if booking_dt < lead_cutoff:
        if usage_state["in_use"]:
            flash(
                f'{pc.name} is currently in use. Choose a booking time at least {BOOKING_LEAD_MINUTES} minutes from now.',
                'error'
            )
        else:
            flash(f'Bookings must be scheduled at least {BOOKING_LEAD_MINUTES} minutes ahead.', 'error')
        return redirect_for_current_user_page()

    conflicting_booking = find_conflicting_booking(pc.id, booking_date, time_slot)
    if conflicting_booking:
        conflict_owner = "You already have" if conflicting_booking.user_id == current_user.id else "Another user already has"
        flash(
            f'{conflict_owner} a booking for {pc.name} on {booking_date} at {time_slot}.',
            'error'
        )
        return redirect_for_current_user_page()

    new_booking = Booking(
        user_id=current_user.id,
        pc_id=pc.id,
        booking_date=booking_date,
        time_slot=time_slot
    )
    db.session.add(new_booking)
    db.session.commit()
    flash('Reservation confirmed!', 'success')
    if current_user.is_admin:
        return redirect(url_for('index'))
    if user_has_positive_balance(current_user):
        return redirect(url_for('client_desktop'))
    return redirect(url_for('client_bookings'))


@app.route('/topup', methods=['POST'])
@login_required
def topup():
    amount_raw = request.form.get('amount', '').strip()
    amount = parse_topup_amount(amount_raw)
    if amount is None:
        flash('Invalid amount.', 'error')
        return redirect_for_current_user_page()

    tx = create_online_payment_request(current_user, amount, source="web")
    flash(f'Payment request saved: {tx.external_id}. Waiting for confirmation.', 'success')
    return redirect_for_current_user_page()


@app.route('/topup/online', methods=['POST'])
@login_required
def topup_online():
    amount = parse_topup_amount(request.form.get('amount', '').strip())
    if amount is None:
        flash('Invalid top-up amount.', 'error')
        return redirect_for_current_user_page()

    return_to = resolve_safe_return_to(request.form.get('return_to')) or resolve_safe_return_to(request.referrer)
    return render_template(
        'payment.html',
        amount=amount,
        return_to=return_to,
        paymongo_public_key=PAYMONGO_PUBLIC_KEY,
        paymongo_ready=bool(PAYMONGO_PUBLIC_KEY),
        topup_currency=TOPUP_CURRENCY.upper(),
        payment_methods=ALLOWED_TOPUP_METHODS
    )


@app.route('/topup/complete', methods=['POST'])
@login_required
def topup_complete():
    amount = parse_topup_amount(request.form.get('amount', '').strip())
    if amount is None:
        flash('Invalid top-up amount.', 'error')
        return redirect_for_current_user_page()

    method = str(request.form.get('method', '')).strip().lower()
    if method not in ALLOWED_TOPUP_METHODS:
        flash('Invalid payment method.', 'error')
        return redirect_for_current_user_page()

    return_to = resolve_safe_return_to(request.form.get('return_to'))
    payment_method_id = str(request.form.get('payment_method_id', '')).strip()
    payment_reference = str(request.form.get('payment_reference', '')).strip()

    if method == "cash":
        tx = create_payment_request(
            current_user,
            amount,
            source="cash_checkout",
            provider="cash",
            status="awaiting_cash",
            external_id=f"CASH-{uuid.uuid4().hex[:16].upper()}"
        )
        flash(f'Cash top-up request saved: {tx.external_id}. Please pay at the counter.', 'success')
    else:
        external_id = payment_method_id or payment_reference or f"{method.upper()}-{uuid.uuid4().hex[:16].upper()}"
        tx = create_payment_request(
            current_user,
            amount,
            source=f"paymongo_{method}",
            provider=f"paymongo_{method}",
            status="pending_confirmation",
            external_id=external_id
        )
        flash(
            f'{ALLOWED_TOPUP_METHODS[method]} top-up request saved: {tx.external_id}. '
            f'Payment is waiting for confirmation.',
            'success'
        )

    if return_to:
        return redirect(return_to)
    return redirect_for_current_user_page()


@app.route('/payment/success')
@login_required
def payment_success():
    flash('Online payment request is recorded directly in database.', 'info')
    return redirect(url_for('index'))


@app.route('/payment/cancel')
@login_required
def payment_cancel():
    flash('Payment cancelled.', 'info')
    return redirect(url_for('index'))


@app.route('/client/payments/cancel/<int:payment_id>', methods=['POST'])
@login_required
def client_cancel_payment(payment_id):
    tx = PaymentTransaction.query.filter_by(id=payment_id, user_id=current_user.id).first()
    if not tx:
        flash('Payment request not found.', 'error')
        return redirect_for_current_user_page()

    if tx.status == 'paid':
        flash('Confirmed payments cannot be cancelled.', 'error')
        return redirect_for_current_user_page()

    if tx.status == 'cancelled':
        flash('Payment request is already cancelled.', 'info')
        return redirect_for_current_user_page()

    tx.status = 'cancelled'
    db.session.add(AdminLog(
        admin_name=current_user.username,
        action=(
            f"Cancelled own payment request {tx.external_id}, "
            f"provider={tx.provider}, amount={tx.amount:.2f} {tx.currency}"
        )
    ))
    db.session.commit()
    flash(f'Payment request {tx.external_id} cancelled.', 'success')
    return redirect_for_current_user_page()


@app.route('/pc_command', methods=['POST'])
@login_required
def pc_command():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    pc_id = request.form.get('pc_id', type=int)
    command = (request.form.get('command') or '').strip().lower()
    reason = (request.form.get('reason') or '').strip()
    pc = db.session.get(PC, pc_id) if pc_id else None

    if not pc:
        flash('Invalid PC selected.', 'error')
        return redirect(url_for('index'))

    if command not in ALLOWED_LAN_COMMANDS:
        flash('Invalid command.', 'error')
        return redirect(url_for('index'))

    payload = {
        "requested_by": current_user.username,
        "skip_user_approval": command in {"lock", "restart", "shutdown"}
    }
    if reason:
        payload["reason"] = reason

    ok, message = send_lan_command(pc.name, command, payload)
    db.session.add(AdminLog(admin_name=current_user.username, action=f"LAN command '{command}' to {pc.name}: {message}"))
    db.session.commit()

    flash(message if ok else f'Command failed: {message}', 'success' if ok else 'error')
    return redirect(url_for('index'))


@app.route('/api/pc-command', methods=['POST'])
@login_required
def api_pc_command():
    if not current_user.is_admin:
        return jsonify({"ok": False, "error": "admin-only endpoint"}), 403

    data = request.get_json(silent=True) or {}
    pc_name = str(data.get("pc_name", "")).strip()
    command = str(data.get("command", "")).strip().lower()
    payload = data.get("payload", {})

    if not pc_name:
        return jsonify({"ok": False, "error": "pc_name is required"}), 400
    if command not in ALLOWED_LAN_COMMANDS:
        return jsonify({
            "ok": False,
            "error": "Invalid command",
            "allowed_commands": sorted(ALLOWED_LAN_COMMANDS)
        }), 400
    if payload is not None and not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "payload must be an object"}), 400

    payload_data = dict(payload or {})
    payload_data.setdefault("requested_by", current_user.username)
    if command in {"lock", "restart", "shutdown"}:
        payload_data["skip_user_approval"] = True

    ok, message = send_lan_command(pc_name, command, payload_data)
    db.session.add(AdminLog(admin_name=current_user.username, action=f"API LAN command '{command}' to {pc_name}: {message}"))
    db.session.commit()

    if not ok:
        return jsonify({"ok": False, "error": message}), 502
    return jsonify({"ok": True, "message": message, "pc_name": pc_name, "command": command}), 200


@app.route('/api/topup', methods=['POST'])
@login_required
def api_topup():
    data = request.get_json(silent=True) or {}
    amount = parse_topup_amount(data.get('amount', 0))
    if amount is None:
        return jsonify({"ok": False, "error": "invalid amount"}), 400

    tx = create_online_payment_request(current_user, amount, source="api")

    return jsonify({
        "ok": True,
        "message": "Payment request saved",
        "amount": amount,
        "transaction_id": tx.external_id,
        "status": tx.status,
        "username": current_user.username
    }), 200


@app.route('/api/topup/confirm', methods=['POST'])
@login_required
def api_topup_confirm():
    data = request.get_json(silent=True) or {}
    transaction_id = str(data.get("transaction_id", "")).strip()
    if not transaction_id:
        return jsonify({"ok": False, "error": "transaction_id is required"}), 400

    tx = PaymentTransaction.query.filter_by(external_id=transaction_id, user_id=current_user.id).first()
    if not tx:
        return jsonify({"ok": False, "error": "transaction not found"}), 404

    return jsonify({
        "ok": True,
        "message": "Transaction status loaded",
        "transaction_id": tx.external_id,
        "status": tx.status,
        "amount": tx.amount,
        "currency": tx.currency
    }), 200


@app.route('/start_session/<int:pc_id>/<int:user_id>')
@login_required
def start_session(pc_id, user_id):
    if not current_user.is_admin: return redirect(url_for('index'))
    user = db.session.get(User, user_id)
    pc = db.session.get(PC, pc_id)
    if not user or not pc:
        flash('Invalid user or PC.', 'error')
        return redirect(url_for('index'))
    if user.pondo <= 0:
        flash('Insufficient Pondo!', 'error')
        return redirect(url_for('index'))
    existing_active = Session.query.filter_by(user_id=user.id, end_time=None).first()
    if existing_active:
        flash('User already has an active session.', 'error')
        return redirect(url_for('index'))
    if pc.is_occupied:
        flash('PC is already occupied.', 'error')
        return redirect(url_for('index'))
    new_session = Session(user_id=user.id, pc_id=pc.id)
    new_session.last_charged_at = datetime.now()
    db.session.add(new_session)
    pc.is_occupied = True
    db.session.add(AdminLog(admin_name=current_user.username, action=f"Started session for {user.username} on {pc.name}"))
    db.session.commit()
    flash(f'Session started for {user.username} on {pc.name}.', 'success')
    return redirect(url_for('index'))


@app.route('/end_session/<int:session_id>')
@login_required
def end_session(session_id):
    if not current_user.is_admin: return redirect(url_for('index'))
    session = db.session.get(Session, session_id)
    if not session: return redirect(url_for('index'))
    cost = finalize_session(session)
    db.session.add(AdminLog(admin_name=current_user.username, action=f"Ended session #{session.id}. Cost: {cost:.2f}"))
    db.session.commit()
    flash(f'Session Ended. Cost: ₱{cost}.', 'info')
    return redirect(url_for('index'))


@app.route('/force_stop_user/<int:user_id>')
@login_required
def force_stop_user(user_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))

    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('index'))

    active_sessions = Session.query.filter_by(user_id=user_id, end_time=None).all()
    if not active_sessions:
        flash(f'No active session for {user.username}.', 'info')
        return redirect(url_for('index'))

    total_cost = 0.0
    for session in active_sessions:
        total_cost += finalize_session(session)

    db.session.add(AdminLog(
        admin_name=current_user.username,
        action=f"Force-stopped {len(active_sessions)} active session(s) for {user.username}. Total cost: {total_cost:.2f}"
    ))
    db.session.commit()
    flash(f'Force-stopped {user.username}. Total cost: {total_cost:.2f}', 'success')
    return redirect(url_for('index'))


@app.route('/api/admin/force-stop-user', methods=['POST'])
@login_required
def api_force_stop_user():
    if not current_user.is_admin:
        return jsonify({"ok": False, "error": "admin-only endpoint"}), 403

    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    username = str(data.get("username", "")).strip()

    user = None
    if user_id is not None:
        try:
            user = db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "user_id must be an integer"}), 400
    elif username:
        user = User.query.filter_by(username=username).first()
    else:
        return jsonify({"ok": False, "error": "provide user_id or username"}), 400

    if not user:
        return jsonify({"ok": False, "error": "user not found"}), 404

    active_sessions = Session.query.filter_by(user_id=user.id, end_time=None).all()
    if not active_sessions:
        return jsonify({"ok": True, "message": "No active sessions", "stopped_sessions": 0, "username": user.username}), 200

    total_cost = 0.0
    for session in active_sessions:
        total_cost += finalize_session(session)

    db.session.add(AdminLog(
        admin_name=current_user.username,
        action=f"API force-stopped {len(active_sessions)} active session(s) for {user.username}. Total cost: {total_cost:.2f}"
    ))
    db.session.commit()

    return jsonify({
        "ok": True,
        "message": "User force-stopped",
        "username": user.username,
        "stopped_sessions": len(active_sessions),
        "total_cost": round(total_cost, 2),
        "new_balance": round(user.pondo, 2)
    }), 200


@app.route('/api/admin/pondo', methods=['POST'])
@login_required
def api_admin_pondo():
    if not current_user.is_admin:
        return jsonify({"ok": False, "error": "admin-only endpoint"}), 403

    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    try:
        amount = float(data.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "amount must be a number"}), 400

    if not username:
        return jsonify({"ok": False, "error": "username is required"}), 400
    if amount <= 0:
        return jsonify({"ok": False, "error": "amount must be greater than 0"}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"ok": False, "error": "user not found"}), 404

    user.pondo += amount
    db.session.add(AdminLog(admin_name=current_user.username, action=f"API added {amount:.2f} credits to {username}"))
    db.session.commit()
    return jsonify({"ok": True, "username": username, "amount": amount, "new_balance": round(user.pondo, 2)}), 200


@app.route('/api/admin/lan-discovery', methods=['GET'])
@login_required
def api_admin_lan_discovery():
    if not current_user.is_admin:
        return jsonify({"ok": False, "error": "admin-only endpoint"}), 403

    pcs = PC.query.order_by(PC.id.asc()).all()
    now_dt = datetime.now()
    online_window_seconds = get_agent_online_window_seconds()
    pending_counts = {}
    for cmd in LanCommand.query.filter(LanCommand.status.in_(["queued", "sent"])).all():
        pending_counts[cmd.pc_name] = pending_counts.get(cmd.pc_name, 0) + 1
    discovered_all = discover_lan_addresses()
    gateway_ips = get_default_gateway_ips()
    force_scan = str(request.args.get("force_scan", "")).strip().lower() in {"1", "true", "yes"}
    fast_mode = str(request.args.get("fast", "")).strip().lower() in {"1", "true", "yes"}
    return jsonify({
        "ok": True,
        "local_ips": get_local_lan_addresses(),
        "discovered_ips": discovered_all,
        "gateway_ips": gateway_ips,
        "discovered_pc_ips": [ip for ip in discovered_all if ip not in set(gateway_ips)],
        "lan_summary": build_primary_ipv4_network_summary(),
        "gateway_scan": get_gateway_client_scan(force=force_scan, non_blocking=(not force_scan and fast_mode)),
        "pc_assignments": [{
            "pc_id": pc.id,
            "pc_name": pc.name,
            "lan_ip": pc.lan_ip,
            "lan_port": pc.lan_port,
            "last_agent_seen_at": pc.last_agent_seen_at.isoformat() if pc.last_agent_seen_at else None,
            "online_since_at": pc.online_since_at.isoformat() if pc.online_since_at else None,
            "online": is_pc_online(pc, now_dt, online_window_seconds),
            "queued_count": pending_counts.get(pc.name, 0)
        } for pc in pcs]
    }), 200


@app.route('/api/admin/auto-assign-ips', methods=['POST'])
@login_required
def api_admin_auto_assign_ips():
    if not current_user.is_admin:
        return jsonify({"ok": False, "error": "admin-only endpoint"}), 403

    discovered_ipv4 = get_assignable_pc_ipv4_addresses(online_only=True)
    detected_for_sync = set(discovered_ipv4)
    cleared = clear_undetected_pc_ips(detected_for_sync)

    if not discovered_ipv4 and not cleared:
        return jsonify({"ok": False, "error": "no online LAN IPv4 PCs detected"}), 404

    pcs = PC.query.order_by(PC.id.asc()).all()
    already_used = {pc.lan_ip for pc in pcs if pc.lan_ip}
    available = [ip for ip in discovered_ipv4 if ip not in already_used]

    assigned = []
    for pc in pcs:
        if pc.lan_ip or not available:
            continue
        ip = available.pop(0)
        pc.lan_ip = ip
        assigned.append({"pc_id": pc.id, "pc_name": pc.name, "lan_ip": ip})

    db.session.add(AdminLog(
        admin_name=current_user.username,
        action=f"API auto-assign LAN online sync: cleared {len(cleared)} offline/stale IP(s), assigned {len(assigned)} online IP(s)"
    ))
    db.session.commit()
    return jsonify({
        "ok": True,
        "cleared_count": len(cleared),
        "cleared": cleared,
        "assigned_count": len(assigned),
        "assigned": assigned
    }), 200


@app.route('/api/agent/register-lan', methods=['POST'])
def api_agent_register_lan():
    shared_token = get_lan_agent_token()

    provided_token = request.headers.get("X-Agent-Token", "").strip()
    if provided_token != shared_token:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    pc_name = str(data.get("pc_name", "")).strip()
    if not pc_name:
        return jsonify({"ok": False, "error": "pc_name is required"}), 400

    pc = PC.query.filter_by(name=pc_name).first()
    if not pc:
        # Auto-create an unmapped PC record for first-time client hostnames.
        created_name = build_unique_agent_pc_name(pc_name)
        pc = PC(name=created_name)
        db.session.add(pc)
        db.session.flush()
        db.session.add(AdminLog(
            admin_name=f"agent:{pc_name}",
            action=f"Auto-created PC record '{created_name}' from agent identity '{pc_name}'"
        ))

    body_ip = normalize_lan_ip(str(data.get("lan_ip", "")).strip()) if data.get("lan_ip") else None
    detected_ip = body_ip or get_client_ip_from_request()
    if not detected_ip:
        return jsonify({"ok": False, "error": "unable to determine LAN IP"}), 400
    if ":" not in detected_ip and detected_ip in get_gateway_ipv4_set():
        return jsonify({"ok": False, "error": "gateway IP cannot be assigned to a PC"}), 400
    agent_port = normalize_agent_port(data.get("agent_port", os.getenv("LAN_AGENT_DEFAULT_PORT", "5001")))
    if not agent_port:
        return jsonify({"ok": False, "error": "invalid agent_port"}), 400

    in_use = PC.query.filter(PC.id != pc.id, PC.lan_ip == detected_ip).first()
    if in_use:
        return jsonify({
            "ok": False,
            "error": f"IP already assigned to {in_use.name}",
            "lan_ip": detected_ip
        }), 409

    pc.lan_ip = detected_ip
    pc.lan_port = agent_port
    mark_pc_agent_seen(pc)
    db.session.add(AdminLog(admin_name=f"agent:{pc_name}", action=f"Auto-registered LAN target {detected_ip}:{agent_port}"))
    db.session.commit()
    cmd = pick_next_lan_command_for_names([pc.name, pc_name])
    pending_command = None
    if cmd is not None:
        try:
            payload = json.loads(cmd.payload_json or "{}")
        except Exception:
            payload = {}
        pending_command = {
            "command_id": cmd.id,
            "pc_name": cmd.pc_name,
            "command": cmd.command,
            "payload": payload
        }

    return jsonify({
        "ok": True,
        "pc_name": pc_name,
        "lan_ip": detected_ip,
        "lan_port": agent_port,
        "pending_command": pending_command
    }), 200


@app.route('/api/agent/pull-command', methods=['POST'])
def api_agent_pull_command():
    shared_token = get_lan_agent_token()
    provided_token = request.headers.get("X-Agent-Token", "").strip()
    if provided_token != shared_token:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    pc_name = str(data.get("pc_name", "")).strip()
    body_ip = normalize_lan_ip(str(data.get("lan_ip", "")).strip()) if data.get("lan_ip") else None
    caller_ip = body_ip or get_client_ip_from_request()
    matched_pc = PC.query.filter_by(lan_ip=caller_ip).first() if caller_ip and ":" not in caller_ip else None
    candidate_names = []
    if pc_name:
        candidate_names.append(pc_name)
    if matched_pc and matched_pc.name not in candidate_names:
        candidate_names.append(matched_pc.name)
    if not candidate_names:
        return jsonify({"ok": False, "error": "pc_name or recognized lan_ip is required"}), 400

    touched_pc = matched_pc or PC.query.filter(PC.name.in_(candidate_names)).first()
    if touched_pc:
        mark_pc_agent_seen(touched_pc)
        db.session.commit()

    cmd = pick_next_lan_command_for_names(candidate_names)
    if cmd is None:
        return jsonify({"ok": True, "no_command": True}), 200

    try:
        payload = json.loads(cmd.payload_json or "{}")
    except Exception:
        payload = {}

    return jsonify({
        "ok": True,
        "no_command": False,
        "command_id": cmd.id,
        "pc_name": cmd.pc_name,
        "command": cmd.command,
        "payload": payload
    }), 200


@app.route('/api/agent/ack-command', methods=['POST'])
def api_agent_ack_command():
    shared_token = get_lan_agent_token()
    provided_token = request.headers.get("X-Agent-Token", "").strip()
    if provided_token != shared_token:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    pc_name = str(data.get("pc_name", "")).strip()
    body_ip = normalize_lan_ip(str(data.get("lan_ip", "")).strip()) if data.get("lan_ip") else None
    caller_ip = body_ip or get_client_ip_from_request()
    command_id = data.get("command_id")
    ok_flag = bool(data.get("ok", False))
    message = str(data.get("message", "")).strip()[:500]

    try:
        command_id = int(command_id)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "command_id must be an integer"}), 400

    cmd = db.session.get(LanCommand, command_id)
    if not cmd:
        return jsonify({"ok": False, "error": "command not found"}), 404

    allowed = False
    if pc_name and cmd.pc_name == pc_name:
        allowed = True
    if not allowed and caller_ip and ":" not in caller_ip:
        mapped_pc = PC.query.filter_by(lan_ip=caller_ip).first()
        if mapped_pc and mapped_pc.name == cmd.pc_name:
            allowed = True
    if not allowed:
        return jsonify({"ok": False, "error": "pc identity mismatch"}), 403

    touched_pc = PC.query.filter_by(name=cmd.pc_name).first()
    if touched_pc:
        mark_pc_agent_seen(touched_pc)

    cmd.status = "done" if ok_flag else "failed"
    cmd.completed_at = datetime.now()
    cmd.result_message = message or ("ok" if ok_flag else "failed")
    db.session.add(AdminLog(
        admin_name=f"agent:{pc_name}",
        action=f"Ack LAN command #{cmd.id} ({cmd.command}) -> {cmd.status}: {cmd.result_message}"
    ))
    db.session.commit()
    return jsonify({"ok": True, "command_id": cmd.id, "status": cmd.status}), 200


# --- Periodic Billing ---
_billing_thread_started = False

def start_periodic_billing():
    global _billing_thread_started
    if _billing_thread_started or BILLING_DISABLED:
        return
    _billing_thread_started = True

    def billing_loop():
        with app.app_context():
            while True:
                time.sleep(3)  # Live charging every 3 seconds
                if not AUTO_CHARGE_ENABLED:
                    continue
                try:
                    now = datetime.now()
                    active_sessions = Session.query.filter_by(end_time=None).all()
                    for sess in active_sessions:
                        try:
                            charge = charge_elapsed_for_session(sess, now)
                            if charge > 0:
                                db.session.commit()
                            else:
                                db.session.rollback()
                        except Exception:
                            db.session.rollback()
                except Exception as e:
                    print(f"Billing task error: {e}")

    t = threading.Thread(target=billing_loop, daemon=True)
    t.start()

@app.before_request
def ensure_billing_started():
    start_periodic_billing()


if __name__ == '__main__':
    # Suppress Flask verbose logging
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    with app.app_context():
        db.create_all()
        ensure_pc_lan_ip_column()
        ensure_booking_date_column()
        seeded = ensure_core_seed_data()
        if seeded:
            print("DB Init: admin/admin123")
    
    app_host = os.getenv("APP_HOST", "0.0.0.0").strip() or "0.0.0.0"
    app_port = int(os.getenv("APP_PORT", "5000"))
    app_debug = str(os.getenv("APP_DEBUG", "0")).strip().lower() in {"1", "true", "yes"}
    
    # Suppress banner and use_reloader to reduce console spam
    app.run(host=app_host, port=app_port, debug=app_debug, use_reloader=False)
