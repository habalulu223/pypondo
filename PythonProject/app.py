from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
import os
import re
import ipaddress
import subprocess
import uuid
from decimal import Decimal, InvalidOperation
from urllib import request as http_request
from urllib import error as http_error
from sqlalchemy import text
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import atexit

app = Flask(__name__)

# --- Config ---
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'pccafe.db')
app.config['SECRET_KEY'] = 'super_secret_cyber_key'

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

HOURLY_RATE = 15.0
ALLOWED_LAN_COMMANDS = {"lock", "restart", "shutdown", "wake"}
MAX_TOPUP_AMOUNT = 10000.0
TOPUP_CURRENCY = os.getenv("TOPUP_CURRENCY", "php").strip().lower() or "php"
DEFAULT_LAN_AGENT_TOKEN = "pypondo-lan-token-change-me"
LAN_SCAN_CACHE = {"timestamp": 0, "cidr": None, "result": None, "scan_in_progress": False}
LAN_SCAN_LOCK = threading.Lock()
NETWORK_CMD_CACHE = {}
NETWORK_CMD_CACHE_LOCK = threading.Lock()
HOSTNAME_CACHE = {}
HOSTNAME_CACHE_LOCK = threading.Lock()

# Global tracking for ping processes to prevent orphaned pings on exit
ACTIVE_PING_PROCESSES = set()
PING_LOCK = threading.Lock()

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
    if elapsed_seconds < 60:  # minimum 1 minute to avoid tiny charges
        return 0.0

    hours_played = elapsed_seconds / 3600.0
    charge = round(hours_played * HOURLY_RATE, 2)
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


def parse_topup_amount(raw):
    try:
        amount = Decimal(str(raw))
    except (InvalidOperation, TypeError):
        return None
    if amount <= 0 or amount > Decimal(str(MAX_TOPUP_AMOUNT)):
        return None
    return float(amount.quantize(Decimal("0.01")))


def create_online_payment_request(user, amount, source="web"):
    external_id = f"REQ-{uuid.uuid4().hex[:16].upper()}"
    tx = PaymentTransaction(
        user_id=user.id,
        provider="online_request",
        external_id=external_id,
        amount=amount,
        currency=TOPUP_CURRENCY,
        status="pending"
    )
    db.session.add(tx)
    db.session.add(AdminLog(
        admin_name=user.username,
        action=f"Online payment request ({source}) created: {external_id}, amount={amount:.2f} {TOPUP_CURRENCY}"
    ))
    db.session.commit()
    return tx


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


@app.before_request
def bootstrap_schema():
    if not getattr(app, "_schema_ready", False):
        db.create_all()
        ensure_pc_lan_ip_column()
        ensure_booking_date_column()
        ensure_session_last_charged_at_column()
        app._schema_ready = True


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
    try:
        # Get local network IP
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            server_ip = sock.getsockname()[0]
        except Exception:
            server_ip = "127.0.0.1"
        finally:
            sock.close()
    except Exception:
        server_ip = "127.0.0.1"
    
    return jsonify({
        "ok": True,
        "server_ip": server_ip,
        "server_port": 5000,
        "server_hostname": socket.gethostname()
    }), 200


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
    return render_template(
        'client_desktop.html',
        active_session=active_session,
        kiosk_mode=is_kiosk_mode_enabled()
    )


@app.route('/client/bookings')
@login_required
def client_bookings():
    if current_user.is_admin:
        return redirect(url_for('view_bookings'))

    pcs = PC.query.order_by(PC.id.asc()).all()
    my_bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.id.desc()).all()
    return render_template(
        'client_bookings.html',
        pcs=pcs,
        bookings=my_bookings,
        today_date=datetime.now().strftime("%Y-%m-%d"),
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
    users = User.query.all() if current_user.is_admin else [current_user]
    active_sessions = Session.query.filter_by(end_time=None).all()
    recent_payments = PaymentTransaction.query.filter_by(user_id=current_user.id).order_by(PaymentTransaction.created_at.desc()).limit(5).all()
    local_ips = get_local_lan_addresses() if current_user.is_admin else []
    lan_summary = build_primary_ipv4_network_summary() if current_user.is_admin else None
    gateway_scan = get_gateway_client_scan(non_blocking=True) if current_user.is_admin else None
    discovered_ips = [row.get("ip") for row in (gateway_scan.get("clients", []) if isinstance(gateway_scan, dict) else [])] if current_user.is_admin else []
    assigned_ips = {pc.lan_ip for pc in pcs if pc.lan_ip}
    online_window_seconds = int(os.getenv("LAN_AGENT_ONLINE_WINDOW_SECONDS", "90"))
    now_dt = datetime.now()
    pending_statuses = {"queued", "sent"}
    pending_counts = {}
    if current_user.is_admin:
        for cmd in LanCommand.query.filter(LanCommand.status.in_(list(pending_statuses))).all():
            pending_counts[cmd.pc_name] = pending_counts.get(cmd.pc_name, 0) + 1

    agent_status = []
    if current_user.is_admin:
        mapped_ips = set()
        for pc in pcs:
            last_seen = pc.last_agent_seen_at
            is_online = bool(last_seen and (now_dt - last_seen).total_seconds() <= online_window_seconds)
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
        discovered_ips=discovered_ips,
        lan_summary=lan_summary,
        gateway_scan=gateway_scan,
        assigned_ips=assigned_ips,
        agent_status=agent_status,
        today_date=datetime.now().strftime("%Y-%m-%d")
    )


# --- ADMIN FEATURES ---

@app.route('/admin/download_app')
@login_required
def admin_download_app():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    candidates = []
    all_in_one_zip = get_latest_bundle_path("all_in_one_bundle-")
    if all_in_one_zip:
        candidates.append((all_in_one_zip, "pypondo-app-bundle.zip"))

    dist_zip = os.path.join(basedir, "dist", "PyPondo-windows.zip")
    if os.path.exists(dist_zip):
        candidates.append((dist_zip, "PyPondo-windows.zip"))

    dist_exe = os.path.join(basedir, "dist", "PyPondo.exe")
    if os.path.exists(dist_exe):
        candidates.append((dist_exe, "PyPondo.exe"))

    if candidates:
        latest_path, latest_name = max(candidates, key=lambda row: os.path.getmtime(row[0]))
        return send_file(
            latest_path,
            as_attachment=True,
            download_name=latest_name
        )

    flash("No app bundle found. Build first using build_desktop_exe.bat.", "error")
    return redirect(url_for('index'))


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


# --- SYSTEM FEATURES ---

@app.route('/pondo', methods=['GET', 'POST'])
@login_required
def manage_pondo():
    if not current_user.is_admin: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        try:
            amount = float(request.form['amount'])
        except:
            return redirect(url_for('manage_pondo'))

        user = User.query.filter_by(username=username).first()
        if user:
            user.pondo += amount
            log = AdminLog(admin_name=current_user.username, action=f"Added ₱{amount} to '{username}'")
            db.session.add(log)
            db.session.commit()
            flash(f'Credits added to {username}!', 'success')
        else:
            flash('User not found.', 'error')
        return redirect(url_for('index'))
    return render_template('pondo.html')


@app.route('/book', methods=['POST'])
@login_required
def book_pc():
    pc_id = request.form['pc_id']
    booking_date = (request.form.get('booking_date') or '').strip()
    if not booking_date:
        booking_date = datetime.now().strftime("%Y-%m-%d")
    else:
        try:
            booking_date = datetime.strptime(booking_date, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            flash('Invalid booking date.', 'error')
            if current_user.is_admin:
                return redirect(url_for('index'))
            return redirect(url_for('client_bookings'))
    time_slot = request.form['time_slot']

    # Check if already booked for that slot (Optional logic improvement)
    # existing = Booking.query.filter_by(pc_id=pc_id, time_slot=time_slot).first()
    # if existing: flash('Slot taken', 'error'); return ...

    new_booking = Booking(
        user_id=current_user.id,
        pc_id=pc_id,
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
        return redirect(url_for('index'))

    tx = create_online_payment_request(current_user, amount, source="web")
    flash(f'Payment request saved: {tx.external_id}. Waiting for confirmation.', 'success')
    return redirect(url_for('index'))


@app.route('/topup/online', methods=['POST'])
@login_required
def topup_online():
    amount = parse_topup_amount(request.form.get('amount', '').strip())
    if amount is None:
        flash('Invalid top-up amount.', 'error')
        return redirect(url_for('index'))

    tx = create_online_payment_request(current_user, amount, source="web_online")
    flash(f'Payment request saved: {tx.external_id}. Waiting for confirmation.', 'success')
    return redirect(url_for('index'))


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


@app.route('/pc_command', methods=['POST'])
@login_required
def pc_command():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    pc_id = request.form.get('pc_id', type=int)
    command = (request.form.get('command') or '').strip().lower()
    pc = db.session.get(PC, pc_id) if pc_id else None

    if not pc:
        flash('Invalid PC selected.', 'error')
        return redirect(url_for('index'))

    if command not in ALLOWED_LAN_COMMANDS:
        flash('Invalid command.', 'error')
        return redirect(url_for('index'))

    ok, message = send_lan_command(pc.name, command, {})
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

    ok, message = send_lan_command(pc_name, command, payload)
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
        return jsonify({"ok": False, "error": "pc not found"}), 404

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
    pc.last_agent_seen_at = datetime.now()
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
        touched_pc.last_agent_seen_at = datetime.now()
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
        touched_pc.last_agent_seen_at = datetime.now()

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
    if _billing_thread_started:
        return
    _billing_thread_started = True

    def billing_loop():
        with app.app_context():
            while True:
                time.sleep(600)  # 10 minutes
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

@app.before_first_request
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
