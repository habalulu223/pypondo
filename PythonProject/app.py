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
import sys
import tempfile
import shutil
import importlib.util
import hashlib
from decimal import Decimal, InvalidOperation
from urllib import request as http_request
from urllib import error as http_error
from sqlalchemy import text, func
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import io
import zipfile

app = Flask(__name__)

# --- Config ---
basedir = os.path.abspath(os.path.dirname(__file__))
APP_ICON_PATH = os.path.join(basedir, "assets", "pypondo.ico")
db_path = os.getenv("PYPONDO_DB_PATH", "").strip()
if not db_path:
    data_dir = os.getenv("PYPONDO_DATA_DIR", "").strip()
    if data_dir:
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "pccafe.db")
if not db_path:
    db_path = os.path.join(basedir, "pccafe.db")
APP_DB_PATH = db_path

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + APP_DB_PATH
app.config['SECRET_KEY'] = 'super_secret_cyber_key'

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

HOURLY_RATE = 15.0
ALLOWED_LAN_COMMANDS = {"lock", "restart", "shutdown", "wake"}
POWER_COMMAND_CONFIRM_TEXT = os.getenv("LAN_POWER_COMMAND_CONFIRM_TEXT", "CONFIRM").strip() or "CONFIRM"
MAX_TOPUP_AMOUNT = 10000.0
TOPUP_CURRENCY = os.getenv("TOPUP_CURRENCY", "php").strip().lower() or "php"
DEFAULT_LAN_AGENT_TOKEN = "pypondo-lan-token-change-me"
LAN_SCAN_CACHE = {"timestamp": 0, "cidr": None, "result": None, "scan_in_progress": False}
LAN_SCAN_LOCK = threading.Lock()
NETWORK_CMD_CACHE = {}
NETWORK_CMD_CACHE_LOCK = threading.Lock()
HOSTNAME_CACHE = {}
HOSTNAME_CACHE_LOCK = threading.Lock()
LAN_META_CACHE = {
    "local_lan_addresses": {"timestamp": 0, "data": []},
    "primary_network_summary": {"timestamp": 0, "data": None}
}
LAN_META_CACHE_LOCK = threading.Lock()
PACKAGE_BUILD_CACHE = {}
PACKAGE_BUILD_CACHE_LOCK = threading.Lock()
PACKAGE_BUILD_EXECUTION_LOCK = threading.RLock()
PACKAGE_BUILD_PREWARM_LOCK = threading.Lock()
PACKAGE_BUILD_PREWARM_RUNNING = set()


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
    booking_date = db.Column(db.String(10), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d"))
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
        db.session.execute(text("ALTER TABLE booking ADD COLUMN booking_date VARCHAR(10)"))
        db.session.commit()

    today = datetime.now().strftime("%Y-%m-%d")
    db.session.execute(
        text("UPDATE booking SET booking_date = :today WHERE booking_date IS NULL OR TRIM(booking_date) = ''"),
        {"today": today}
    )
    db.session.commit()


def ensure_core_seed_data():
    created = False

    try:
        default_pc_count = int(str(os.getenv("PYPONDO_DEFAULT_PC_COUNT", "5")).strip())
    except Exception:
        default_pc_count = 5
    default_pc_count = max(1, min(default_pc_count, 200))

    if PC.query.count() == 0:
        for i in range(1, default_pc_count + 1):
            db.session.add(PC(name=f"PC-{i}"))
        created = True

    admin_user = User.query.filter_by(is_admin=True).first()
    if not admin_user:
        preferred_username = str(os.getenv("PYPONDO_DEFAULT_ADMIN_USERNAME", "admin")).strip() or "admin"
        preferred_password = str(os.getenv("PYPONDO_DEFAULT_ADMIN_PASSWORD", "admin123")).strip() or "admin123"

        existing = User.query.filter_by(username=preferred_username).first()
        if existing:
            existing.is_admin = True
            if not existing.password_hash:
                existing.set_password(preferred_password)
            created = True
        else:
            admin = User(username=preferred_username, is_admin=True)
            admin.set_password(preferred_password)
            db.session.add(admin)
            created = True

    if created:
        db.session.commit()
    return created


def retire_legacy_connect_request_commands():
    pending = LanCommand.query.filter(
        LanCommand.command == "connect_request",
        LanCommand.status.in_(["queued", "sent"])
    ).all()
    if not pending:
        return 0

    now_dt = datetime.now()
    for cmd in pending:
        cmd.status = "done"
        cmd.completed_at = now_dt
        cmd.result_message = "Legacy connection request flow removed; auto-connect mode enabled."
    db.session.add(AdminLog(
        admin_name="system",
        action=f"Retired {len(pending)} legacy connect_request command(s) after auto-connect migration"
    ))
    db.session.commit()
    return len(pending)


def normalize_agent_port(value):
    try:
        port = int(str(value).strip())
    except Exception:
        return None
    # Reserve low/system ports; LAN agent is expected on an app port (default 5001).
    if port < 1024 or port > 65535:
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


def normalize_agent_pc_name(value):
    raw = str(value or "").strip()
    if not raw:
        raw = socket.gethostname() or f"PC-{uuid.uuid4().hex[:6]}"
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", raw).strip("-_")
    if not cleaned:
        cleaned = f"PC-{uuid.uuid4().hex[:6]}"
    if len(cleaned) <= 20:
        return cleaned
    digest = hashlib.sha1(cleaned.encode("utf-8", errors="ignore")).hexdigest()[:5]
    return f"{cleaned[:14]}-{digest}"


def make_unique_agent_pc_name(preferred_name):
    base_name = normalize_agent_pc_name(preferred_name)
    if not PC.query.filter_by(name=base_name).first():
        return base_name

    for idx in range(2, 1000):
        suffix = f"-{idx}"
        root_len = max(1, 20 - len(suffix))
        candidate = f"{base_name[:root_len]}{suffix}"
        if not PC.query.filter_by(name=candidate).first():
            return candidate

    return f"PC-{uuid.uuid4().hex[:6]}"


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
        output = subprocess.check_output(command_args, text=True, encoding="utf-8", errors="ignore")
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


def build_primary_ipv4_network_summary(force=False):
    ttl = int(os.getenv("LAN_NETWORK_SUMMARY_CACHE_TTL_SECONDS", "20"))
    now = time.time()
    if not force:
        with LAN_META_CACHE_LOCK:
            cached = LAN_META_CACHE.get("primary_network_summary", {})
            cached_data = cached.get("data")
            cached_timestamp = float(cached.get("timestamp", 0))
            if cached_data is not None and (now - cached_timestamp) < ttl:
                return dict(cached_data)

    interfaces = parse_ipv4_interfaces()
    if not interfaces:
        with LAN_META_CACHE_LOCK:
            LAN_META_CACHE["primary_network_summary"] = {"timestamp": now, "data": None}
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
        with LAN_META_CACHE_LOCK:
            LAN_META_CACHE["primary_network_summary"] = {"timestamp": now, "data": None}
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

    summary = {
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
    with LAN_META_CACHE_LOCK:
        LAN_META_CACHE["primary_network_summary"] = {"timestamp": now, "data": dict(summary)}
    return summary


def ping_ipv4_host(ip, timeout_ms=200):
    try:
        return subprocess.run(
            ["ping", "-n", "1", "-w", str(timeout_ms), ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        ).returncode == 0
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
            timeout=timeout_seconds
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
    summary = build_primary_ipv4_network_summary(force=force)
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


def get_local_lan_addresses(force=False):
    ttl = int(os.getenv("LAN_LOCAL_ADDRESSES_CACHE_TTL_SECONDS", "15"))
    now = time.time()
    if not force:
        with LAN_META_CACHE_LOCK:
            cached = LAN_META_CACHE.get("local_lan_addresses", {})
            cached_data = cached.get("data") or []
            cached_timestamp = float(cached.get("timestamp", 0))
            if cached_data and (now - cached_timestamp) < ttl:
                return list(cached_data)

    addresses = []
    for ip in get_local_ipv4_addresses() + get_local_ipv6_addresses():
        if ip not in addresses:
            addresses.append(ip)
    with LAN_META_CACHE_LOCK:
        LAN_META_CACHE["local_lan_addresses"] = {"timestamp": now, "data": list(addresses)}
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
    targets = []

    local_ips = set(get_local_lan_addresses())
    if host in local_ips or host.startswith("127.") or host in {"::1", "localhost"}:
        # Same-machine target: prefer loopback first to avoid local LAN stack issues.
        for port in ports:
            for local_host in ("127.0.0.1", "localhost"):
                url = f"http://{local_host}:{port}"
                if url not in targets:
                    targets.append(url)

    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    for port in ports:
        url = f"http://{host}:{port}"
        if url not in targets:
            targets.append(url)
    return targets


def get_remote_windows_credentials():
    username = os.getenv("LAN_REMOTE_USERNAME", "").strip()
    password = os.getenv("LAN_REMOTE_PASSWORD", "")
    domain = os.getenv("LAN_REMOTE_DOMAIN", "").strip()

    if not username or password == "":
        return None, None

    if domain and ("\\" not in username) and ("@" not in username):
        username = f"{domain}\\{username}"
    return username, password


def run_remote_windows_fallback(command_args, unc_host=None, username=None, password=None):
    connected_with_net_use = False
    try:
        if unc_host and username and password is not None:
            connect = subprocess.run(
                ["net", "use", unc_host, f"/user:{username}", password],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore"
            )
            if connect.returncode != 0:
                output = (connect.stdout or "").strip()
                error = (connect.stderr or "").strip()
                details = " | ".join(part for part in [output, error] if part).strip()
                return False, details or "Could not authenticate remote admin share"
            connected_with_net_use = True

        control = subprocess.run(
            command_args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )
        output = (control.stdout or "").strip()
        error = (control.stderr or "").strip()
        details = " | ".join(part for part in [output, error] if part).strip()
        if control.returncode == 0:
            return True, details or "ok"
        return False, details or f"exit code {control.returncode}"
    except Exception as exc:
        return False, str(exc)
    finally:
        if connected_with_net_use:
            try:
                subprocess.run(
                    ["net", "use", unc_host, "/delete", "/y"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore"
                )
            except Exception:
                pass


def remote_windows_control_fallback(pc_name, command):
    allow_fallback = str(os.getenv("LAN_ALLOW_REMOTE_WINDOWS_FALLBACK", "1")).strip().lower() in {"1", "true", "yes"}
    if not allow_fallback:
        return False, "Remote Windows fallback is disabled by policy"

    if command not in {"restart", "shutdown", "lock"}:
        return False, "No fallback path for this command"

    pc = PC.query.filter_by(name=pc_name).first()
    if not pc or not pc.lan_ip or ":" in pc.lan_ip:
        return False, "Fallback requires PC IPv4 address"

    unc_host = f"\\\\{pc.lan_ip}"
    username, password = get_remote_windows_credentials()
    using_explicit_credentials = bool(username and password is not None)

    if command == "lock":
        lock_cmd = ["wmic", f"/node:{pc.lan_ip}"]
        if using_explicit_credentials:
            lock_cmd.extend([f"/user:{username}", f"/password:{password}"])
        lock_cmd.extend(["process", "call", "create", "rundll32.exe user32.dll,LockWorkStation"])
        ok, details = run_remote_windows_fallback(lock_cmd, unc_host=unc_host, username=username, password=password)
        if ok and "ReturnValue = 0" in details:
            suffix = " using configured remote credentials" if using_explicit_credentials else " using current session credentials"
            return True, f"Fallback lock sent via cmd for {pc.lan_ip}{suffix}"
        guidance = ""
        if not using_explicit_credentials:
            guidance = " Set LAN_REMOTE_USERNAME and LAN_REMOTE_PASSWORD."
        return False, f"Fallback lock failed via cmd for {pc.lan_ip}: {details or 'access denied or RPC unavailable'}{guidance}"

    shutdown_flag = "/r" if command == "restart" else "/s"
    power_cmd = ["shutdown", "/m", unc_host, shutdown_flag, "/t", "0", "/f"]
    ok, details = run_remote_windows_fallback(power_cmd, unc_host=unc_host, username=username, password=password)
    if ok:
        suffix = " using configured remote credentials" if using_explicit_credentials else " using current session credentials"
        return True, f"Fallback {command} sent via cmd for {pc.lan_ip}{suffix}"
    guidance = ""
    if not using_explicit_credentials:
        guidance = " Set LAN_REMOTE_USERNAME and LAN_REMOTE_PASSWORD."
    return False, f"Fallback {command} failed via cmd for {pc.lan_ip}: {details or 'access denied or RPC unavailable'}{guidance}"


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
    payload_data = payload if isinstance(payload, dict) else {}
    skip_approval = str(payload_data.get("skip_user_approval", "")).strip().lower() in {"1", "true", "yes"}
    targets = resolve_pc_targets(pc_name)
    status_note = get_agent_status_note(pc_name)
    requires_user_popup = command in {"lock", "restart", "shutdown"} and not skip_approval
    agent_only_for_popup = str(os.getenv("LAN_REQUIRE_AGENT_POPUP_PATH", "1")).strip().lower() in {"1", "true", "yes"}
    if not targets:
        queued, created = enqueue_lan_command(pc_name, command, payload_data, note="no direct target")
        if created:
            return True, f"No direct LAN target; queued command #{queued.id} for client pull ({status_note})"
        return True, f"Existing pending command #{queued.id} retained ({status_note})"

    shared_token = get_lan_agent_token()

    body = json.dumps({
        "command": command,
        "payload": payload_data
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

    if requires_user_popup and agent_only_for_popup:
        queued, created = enqueue_lan_command(pc_name, command, payload_data, note="agent popup required")
        details = " | ".join(errors[:3]) if errors else "no connection details"
        if created:
            return True, f"Queued command #{queued.id} for client popup approval ({status_note}). Details: {details}"
        return True, f"Command already pending as #{queued.id} ({status_note}). Direct details: {details}"

    fallback_ok, fallback_message = remote_windows_control_fallback(pc_name, command)
    if fallback_ok:
        return True, fallback_message

    queued, created = enqueue_lan_command(pc_name, command, payload_data, note="direct+fallback failed")
    details = " | ".join(errors[:3]) if errors else "no connection details"
    if created:
        return True, f"Queued command #{queued.id} for client pickup (direct path unavailable, {status_note}). Details: {details}. {fallback_message}"
    return True, f"Command already pending as #{queued.id} ({status_note}). Direct details: {details}. {fallback_message}"


def probe_pc_agent(pc_name):
    targets = resolve_pc_targets(pc_name)
    if not targets:
        return False, "No LAN target configured for this PC."

    errors = []
    for target in targets:
        try:
            req = http_request.Request(f"{target}/agent/info", method="GET")
            with http_request.urlopen(req, timeout=6) as response:
                response_text = response.read().decode("utf-8")
                response_data = json.loads(response_text) if response_text else {}
                if bool(response_data.get("ok", True)):
                    return True, f"Connected to {pc_name} agent at {target}"
                errors.append(f"{target}: invalid response")
        except http_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            errors.append(f"{target}: HTTP {exc.code} {detail}")
        except Exception as exc:
            errors.append(f"{target}: {exc}")

    details = " | ".join(errors[:3]) if errors else "no connection details"
    return False, f"Auto-connect probe failed. Details: {details}"


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


def finalize_session(session):
    if not session or session.end_time is not None:
        return 0.0

    pc = db.session.get(PC, session.pc_id)
    user = db.session.get(User, session.user_id)
    session.end_time = datetime.now()
    duration = session.end_time - session.start_time
    hours_played = duration.total_seconds() / 3600
    cost = round(hours_played * HOURLY_RATE, 2)
    session.cost = cost

    if user:
        user.pondo -= cost
    if pc:
        pc.is_occupied = False
    return cost


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


def get_server_public_base_url():
    configured = os.getenv("LAN_SERVER_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    try:
        host_value = (request.host or "").strip()
        host_name = host_value.split(":", 1)[0].strip().lower()
        if host_name in {"127.0.0.1", "localhost", "::1"}:
            local_ipv4s = get_local_ipv4_addresses()
            if local_ipv4s:
                scheme = "https" if request.is_secure else "http"
                port = host_value.split(":", 1)[1].strip() if ":" in host_value else ("443" if request.is_secure else "80")
                if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
                    return f"{scheme}://{local_ipv4s[0]}"
                return f"{scheme}://{local_ipv4s[0]}:{port}"
        return request.host_url.rstrip("/")
    except Exception:
        return ""


def module_available(module_name):
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def get_packaging_python_command():
    if getattr(sys, "frozen", False):
        fallback = shutil.which("python") or shutil.which("py")
        if fallback:
            return fallback
        raise RuntimeError("Standalone package build requires Python installed on the admin PC.")

    if sys.executable and os.path.exists(sys.executable):
        return sys.executable
    fallback = shutil.which("python") or shutil.which("py")
    if fallback:
        return fallback
    raise RuntimeError("Python executable not found for packaging.")


def run_and_check(command, cwd=None, allow_failure=False):
    result = subprocess.run(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore"
    )
    if result.returncode != 0 and not allow_failure:
        tail = (result.stdout or "").strip()[-4000:]
        raise RuntimeError(f"Command failed ({' '.join(command)}):\n{tail}")
    return result


def build_path_signature(paths):
    parts = []
    for path in paths:
        if not path:
            continue
        absolute = os.path.abspath(path)
        if os.path.isdir(absolute):
            child_paths = []
            for root, _, files in os.walk(absolute):
                for name in sorted(files):
                    child_paths.append(os.path.join(root, name))
            for child in sorted(child_paths):
                try:
                    stat = os.stat(child)
                    parts.append(f"{child}:{int(stat.st_mtime)}:{stat.st_size}")
                except Exception:
                    parts.append(f"{child}:missing")
            continue
        try:
            stat = os.stat(absolute)
            parts.append(f"{absolute}:{int(stat.st_mtime)}:{stat.st_size}")
        except Exception:
            parts.append(f"{absolute}:missing")
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def get_package_cache_directory():
    configured = os.getenv("PACKAGE_BUILD_CACHE_DIR", "").strip()
    cache_dir = configured or os.path.join(basedir, "package_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def get_package_cache_file_path(namespace, cache_key):
    safe_namespace = re.sub(r"[^A-Za-z0-9_-]+", "_", str(namespace))
    safe_cache_key = re.sub(r"[^A-Za-z0-9_-]+", "_", str(cache_key))
    return os.path.join(get_package_cache_directory(), f"{safe_namespace}-{safe_cache_key}.zip")


def get_cached_package_bundle(namespace, cache_key, default_download_name):
    try:
        ttl = int(os.getenv("PACKAGE_BUILD_CACHE_TTL_SECONDS", "900"))
    except Exception:
        ttl = 900
    now = time.time()
    storage_key = f"{namespace}:{cache_key}"
    with PACKAGE_BUILD_CACHE_LOCK:
        item = PACKAGE_BUILD_CACHE.get(storage_key)
        if not item:
            item = None
        if item and ttl > 0 and now - float(item.get("timestamp", 0)) > ttl:
            PACKAGE_BUILD_CACHE.pop(storage_key, None)
            item = None
        if item:
            return io.BytesIO(item["data"]), item["download_name"]

    cache_path = get_package_cache_file_path(namespace, cache_key)
    if not os.path.exists(cache_path):
        return None

    try:
        disk_ttl = int(os.getenv("PACKAGE_BUILD_DISK_CACHE_TTL_SECONDS", "259200"))
    except Exception:
        disk_ttl = 259200

    try:
        if disk_ttl > 0 and now - os.path.getmtime(cache_path) > disk_ttl:
            os.remove(cache_path)
            return None

        with open(cache_path, "rb") as f:
            data = f.read()
        with PACKAGE_BUILD_CACHE_LOCK:
            PACKAGE_BUILD_CACHE[storage_key] = {
                "timestamp": time.time(),
                "download_name": default_download_name,
                "data": data
            }
        return io.BytesIO(data), default_download_name
    except Exception:
        return None


def store_cached_package_bundle(namespace, cache_key, memory_bundle, download_name):
    data = memory_bundle.getvalue() if hasattr(memory_bundle, "getvalue") else bytes(memory_bundle)
    storage_key = f"{namespace}:{cache_key}"
    with PACKAGE_BUILD_CACHE_LOCK:
        PACKAGE_BUILD_CACHE[storage_key] = {
            "timestamp": time.time(),
            "download_name": download_name,
            "data": data
        }
    cache_path = get_package_cache_file_path(namespace, cache_key)
    temp_path = f"{cache_path}.tmp-{uuid.uuid4().hex}"
    try:
        with open(temp_path, "wb") as f:
            f.write(data)
        os.replace(temp_path, cache_path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
    return io.BytesIO(data), download_name


def ensure_packaging_tooling():
    if module_available("PyInstaller"):
        return

    auto_install = str(os.getenv("PYPONDO_AUTO_INSTALL_BUILD_DEPS", "1")).strip().lower() in {"1", "true", "yes"}
    if not auto_install:
        raise RuntimeError("PyInstaller is required. Install it once with: python -m pip install pyinstaller")

    python_cmd = get_packaging_python_command()
    run_and_check([python_cmd, "-m", "pip", "install", "pyinstaller"])
    if not module_available("PyInstaller"):
        raise RuntimeError("PyInstaller install failed. Run: python -m pip install pyinstaller")


def build_executable(
    work_dir,
    entry_script,
    exe_name,
    windowed=True,
    add_data_entries=None,
    collect_all_modules=None
):
    python_cmd = get_packaging_python_command()
    command = [
        python_cmd,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--name",
        exe_name
    ]
    if str(os.getenv("PYPONDO_PYINSTALLER_CLEAN", "0")).strip().lower() in {"1", "true", "yes"}:
        command.append("--clean")
    if windowed:
        command.append("--windowed")
    if os.path.exists(APP_ICON_PATH):
        command.extend(["--icon", APP_ICON_PATH])
    for add_data in (add_data_entries or []):
        command.extend(["--add-data", add_data])
    for module_name in (collect_all_modules or []):
        command.extend(["--collect-all", module_name])
    command.append(entry_script)
    run_and_check(command, cwd=work_dir)

    exe_path = os.path.join(work_dir, "dist", f"{exe_name}.exe")
    if not os.path.exists(exe_path):
        raise RuntimeError(f"Build succeeded but output missing: {exe_path}")
    return exe_path


def build_client_agent_source_bundle():
    server_base_url = get_server_public_base_url().rstrip("/")
    register_url = f"{server_base_url}/api/agent/register-lan" if server_base_url else ""
    token = get_lan_agent_token()
    agent_port = normalize_agent_port(os.getenv("LAN_AGENT_DEFAULT_PORT", "5001")) or 5001

    agent_source_path = os.path.join(basedir, "lan_agent.py")
    with open(agent_source_path, "r", encoding="utf-8") as f:
        agent_source = f.read()

    client_app_py = (
        "import os\n"
        "import time\n"
        "import webbrowser\n\n"
        "REMOTE_URL = os.getenv('PYPONDO_REMOTE_URL', '').strip()\n"
        "if not REMOTE_URL:\n"
        "    print('Missing PYPONDO_REMOTE_URL. Set it in run_client_app.bat.')\n"
        "    raise SystemExit(1)\n\n"
        "try:\n"
        "    import webview\n"
        "    HAS_WEBVIEW = True\n"
        "except Exception as exc:\n"
        "    HAS_WEBVIEW = False\n"
        "    print(f'pywebview not available, using browser mode: {exc}')\n\n"
        "if HAS_WEBVIEW:\n"
        "    webview.create_window('PyPondo Client', url=REMOTE_URL, width=1280, height=820, min_size=(980, 700))\n"
        "    webview.start()\n"
        "else:\n"
        "    webbrowser.open(REMOTE_URL)\n"
        "    try:\n"
        "        while True:\n"
        "            time.sleep(1)\n"
        "    except KeyboardInterrupt:\n"
        "        pass\n"
    )

    run_client_bat = (
        "@echo off\r\n"
        "setlocal\r\n"
        "cd /d \"%~dp0\"\r\n"
        "\r\n"
        f"set \"LAN_AGENT_TOKEN={token}\"\r\n"
        "set \"LAN_PC_NAME=%COMPUTERNAME%\"\r\n"
        f"set \"LAN_SERVER_REGISTER_URL={register_url}\"\r\n"
        f"set \"LAN_SERVER_BASE_URL={server_base_url}\"\r\n"
        f"set \"LAN_AGENT_PORT={agent_port}\"\r\n"
        "set \"LAN_REQUIRE_USER_APPROVAL=1\"\r\n"
        f"set \"PYPONDO_REMOTE_URL={server_base_url}\"\r\n"
        "\r\n"
        "if \"%PYPONDO_REMOTE_URL%\"==\"\" (\r\n"
        "  echo Missing server URL. Ask admin to set LAN_SERVER_PUBLIC_BASE_URL.\r\n"
        "  pause\r\n"
        "  exit /b 1\r\n"
        ")\r\n"
        "\r\n"
        "start \"PyPondo-LAN-Agent\" /MIN python lan_agent.py\r\n"
        "python client_app.py\r\n"
        "endlocal\r\n"
    )

    install_bat = (
        "@echo off\r\n"
        "setlocal\r\n"
        "python -m pip install --upgrade flask flask-sqlalchemy flask-login\r\n"
        "python -m pip install --pre pythonnet\r\n"
        "python -m pip install pywebview\r\n"
        "if errorlevel 1 (\r\n"
        "  echo Failed to install dependencies. Install Python first.\r\n"
        "  pause\r\n"
        "  exit /b 1\r\n"
        ")\r\n"
        "echo Dependencies installed.\r\n"
        "pause\r\n"
        "endlocal\r\n"
    )

    readme = (
        "PyPondo Client Package (Source Mode)\r\n"
        "===================================\r\n\r\n"
        "PC Name: auto (uses client machine hostname)\r\n"
        f"Server URL: {server_base_url or '(not set)'}\r\n"
        f"Register URL: {register_url or '(not set)'}\r\n"
        f"Agent Port: {agent_port}\r\n\r\n"
        "Setup:\r\n"
        "1. Install Python 3.10+ on this client PC.\r\n"
        "2. Run install_requirements.bat once.\r\n"
        "3. Run run_client_app.bat to open client app and auto-start LAN agent.\r\n"
        "4. The LAN agent sends this PC's LAN IP to admin automatically.\r\n"
    )

    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("client_app.py", client_app_py)
        zf.writestr("lan_agent.py", agent_source)
        zf.writestr("run_client_app.bat", run_client_bat)
        zf.writestr("install_requirements.bat", install_bat)
        zf.writestr("README_CLIENT.txt", readme)
    memory.seek(0)
    return memory, "pypondo-client-source.zip"


def build_client_agent_standalone_bundle(server_base_url=None):
    ensure_packaging_tooling()

    server_base_url = (server_base_url or get_server_public_base_url()).rstrip("/")
    if not server_base_url:
        raise RuntimeError("Unable to determine LAN server URL. Set LAN_SERVER_PUBLIC_BASE_URL first.")

    register_url = f"{server_base_url}/api/agent/register-lan"
    token = get_lan_agent_token()
    agent_port = normalize_agent_port(os.getenv("LAN_AGENT_DEFAULT_PORT", "5001")) or 5001

    remote_url_literal = json.dumps(server_base_url)
    token_literal = json.dumps(token)
    register_url_literal = json.dumps(register_url)
    agent_port_literal = json.dumps(str(agent_port))

    launcher_source = (
        "import os\n"
        "import sys\n"
        "import time\n"
        "import socket\n"
        "import threading\n"
        "import subprocess\n"
        "import webbrowser\n\n"
        f"REMOTE_URL = {remote_url_literal}\n"
        f"LAN_AGENT_TOKEN = {token_literal}\n"
        "LAN_PC_NAME = os.getenv('COMPUTERNAME', socket.gethostname())\n"
        f"LAN_SERVER_REGISTER_URL = {register_url_literal}\n"
        f"LAN_SERVER_BASE_URL = {remote_url_literal}\n"
        f"LAN_AGENT_PORT = {agent_port_literal}\n"
        "LAN_REQUIRE_USER_APPROVAL = '1'\n"
        "APP_TITLE = 'PyPondo Client'\n\n"
        "def runtime_dir():\n"
        "    if getattr(sys, 'frozen', False):\n"
        "        return os.path.abspath(os.path.dirname(sys.executable))\n"
        "    return os.path.abspath(os.path.dirname(__file__))\n\n"
        "def build_agent_command():\n"
        "    if getattr(sys, 'frozen', False):\n"
        "        return [sys.executable, '--agent']\n"
        "    return [sys.executable, os.path.abspath(__file__), '--agent']\n\n"
        "def is_local_port_open(port):\n"
        "    try:\n"
        "        target_port = int(str(port).strip())\n"
        "    except Exception:\n"
        "        return False\n"
        "    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:\n"
        "        sock.settimeout(0.8)\n"
        "        return sock.connect_ex(('127.0.0.1', target_port)) == 0\n\n"
        "def run_agent_mode():\n"
        "    os.environ.setdefault('LAN_AGENT_TOKEN', LAN_AGENT_TOKEN)\n"
        "    os.environ.setdefault('LAN_PC_NAME', LAN_PC_NAME)\n"
        "    os.environ.setdefault('LAN_SERVER_REGISTER_URL', LAN_SERVER_REGISTER_URL)\n"
        "    os.environ.setdefault('LAN_SERVER_BASE_URL', LAN_SERVER_BASE_URL)\n"
        "    os.environ.setdefault('LAN_AGENT_PORT', str(LAN_AGENT_PORT))\n"
        "    os.environ.setdefault('LAN_REQUIRE_USER_APPROVAL', LAN_REQUIRE_USER_APPROVAL)\n"
        "    try:\n"
        "        import lan_agent\n"
        "    except Exception as exc:\n"
        "        raise SystemExit(f'Failed to load LAN agent: {exc}')\n"
        "    if lan_agent.REGISTER_URL and lan_agent.AGENT_TOKEN:\n"
        "        threading.Thread(target=lan_agent.registration_loop, daemon=True).start()\n"
        "    if lan_agent.get_poll_url() and lan_agent.get_ack_url() and lan_agent.AGENT_TOKEN:\n"
        "        threading.Thread(target=lan_agent.command_poll_loop, daemon=True).start()\n"
        "    lan_agent.app.run(host=lan_agent.HOST, port=lan_agent.PORT, debug=False)\n\n"
        "def start_agent_if_needed():\n"
        "    if is_local_port_open(LAN_AGENT_PORT):\n"
        "        return True, 'already running'\n"
        "    env = os.environ.copy()\n"
        "    env.update({\n"
        "        'LAN_AGENT_TOKEN': LAN_AGENT_TOKEN,\n"
        "        'LAN_PC_NAME': LAN_PC_NAME,\n"
        "        'LAN_SERVER_REGISTER_URL': LAN_SERVER_REGISTER_URL,\n"
        "        'LAN_SERVER_BASE_URL': LAN_SERVER_BASE_URL,\n"
        "        'LAN_AGENT_PORT': str(LAN_AGENT_PORT),\n"
        "        'LAN_REQUIRE_USER_APPROVAL': LAN_REQUIRE_USER_APPROVAL,\n"
        "    })\n"
        "    creationflags = 0x08000000 if os.name == 'nt' else 0\n"
        "    try:\n"
        "        subprocess.Popen(build_agent_command(), cwd=runtime_dir(), env=env, creationflags=creationflags)\n"
        "        for _ in range(8):\n"
        "            time.sleep(0.25)\n"
        "            if is_local_port_open(LAN_AGENT_PORT):\n"
        "                return True, 'started'\n"
        "        return False, 'agent start timed out'\n"
        "    except Exception as exc:\n"
        "        return False, str(exc)\n\n"
        "def launch_browser_control_window(url, note=''):\n"
        "    import tkinter as tk\n"
        "    from tkinter import ttk\n\n"
        "    def open_in_browser():\n"
        "        webbrowser.open(url)\n\n"
        "    root = tk.Tk()\n"
        "    root.title(APP_TITLE)\n"
        "    root.geometry('560x250')\n"
        "    root.minsize(500, 220)\n"
        "    frame = ttk.Frame(root, padding=16)\n"
        "    frame.pack(fill='both', expand=True)\n"
        "    ttk.Label(frame, text='PyPondo Client is running.', font=('Segoe UI', 14, 'bold')).pack(anchor='w', pady=(0, 8))\n"
        "    ttk.Label(frame, text='The app opened in your default browser. Keep this window open.').pack(anchor='w', pady=(0, 8))\n"
        "    if note:\n"
        "        ttk.Label(frame, text=note, foreground='#d64545').pack(anchor='w', pady=(0, 8))\n"
        "    ttk.Label(frame, text=url, foreground='#1f5fbf').pack(anchor='w', pady=(0, 14))\n"
        "    row = ttk.Frame(frame)\n"
        "    row.pack(fill='x')\n"
        "    ttk.Button(row, text='Open App', command=open_in_browser).pack(side='left')\n"
        "    ttk.Button(row, text='Exit', command=root.destroy).pack(side='right')\n"
        "    open_in_browser()\n"
        "    root.mainloop()\n\n"
        "def launch_ui(url, agent_note=''):\n"
        "    try:\n"
        "        import webview\n"
        "        webview.create_window(APP_TITLE, url=url, width=1280, height=820, min_size=(980, 700))\n"
        "        webview.start()\n"
        "        return\n"
        "    except Exception:\n"
        "        pass\n"
        "    try:\n"
        "        launch_browser_control_window(url, note=agent_note)\n"
        "    except Exception:\n"
        "        webbrowser.open(url)\n"
        "        while True:\n"
        "            time.sleep(1)\n\n"
        "def main():\n"
        "    if '--agent' in sys.argv:\n"
        "        run_agent_mode()\n"
        "        return 0\n"
        "    if not REMOTE_URL:\n"
        "        raise SystemExit('Missing REMOTE_URL in generated client launcher.')\n"
        "    ok, detail = start_agent_if_needed()\n"
        "    note = '' if ok else f'LAN agent failed to start: {detail}'\n"
        "    launch_ui(REMOTE_URL, note)\n"
        "    return 0\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )

    with tempfile.TemporaryDirectory(prefix="pypondo-client-build-") as temp_dir:
        launcher_path = os.path.join(temp_dir, "client_launcher.py")
        agent_path = os.path.join(temp_dir, "lan_agent.py")

        with open(launcher_path, "w", encoding="utf-8") as f:
            f.write(launcher_source)
        shutil.copy2(os.path.join(basedir, "lan_agent.py"), agent_path)

        collect_modules = ["webview"] if module_available("webview") else []
        client_exe = build_executable(
            work_dir=temp_dir,
            entry_script=launcher_path,
            exe_name="PyPondoClient",
            windowed=True,
            collect_all_modules=collect_modules
        )

        start_client_bat = (
            "@echo off\r\n"
            "setlocal\r\n"
            "cd /d \"%~dp0\"\r\n"
            "if not exist \"PyPondoClient.exe\" (\r\n"
            "  echo Missing PyPondoClient.exe\r\n"
            "  pause\r\n"
            "  exit /b 1\r\n"
            ")\r\n"
            "start \"\" \"PyPondoClient.exe\"\r\n"
            "endlocal\r\n"
        )

        readme = (
            "PyPondo Client Package (Standalone EXE)\r\n"
            "=======================================\r\n\r\n"
            "PC Name: auto (uses client machine hostname)\r\n"
            f"Server URL: {server_base_url}\r\n"
            f"Register URL: {register_url}\r\n"
            f"Agent Port: {agent_port}\r\n\r\n"
            "How to use:\r\n"
            "1. Extract this ZIP on the client PC.\r\n"
            "2. Run start_client_app.bat (or PyPondoClient.exe).\r\n"
            "3. No Python/compiler is required on the client PC.\r\n"
            "4. PyPondoClient.exe starts LAN agent mode automatically and sends this PC IP to admin.\r\n"
        )

        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w", zipfile.ZIP_STORED) as zf:
            zf.write(client_exe, arcname="PyPondoClient.exe")
            zf.writestr("start_client_app.bat", start_client_bat)
            zf.writestr("README_CLIENT.txt", readme)
            if os.path.exists(APP_ICON_PATH):
                zf.write(APP_ICON_PATH, arcname="pypondo.ico")
        memory.seek(0)
        return memory, "pypondo-client-standalone.zip"


def build_client_agent_bundle(server_base_url=None):
    server_base_url = (server_base_url or get_server_public_base_url()).rstrip("/")
    agent_port = normalize_agent_port(os.getenv("LAN_AGENT_DEFAULT_PORT", "5001")) or 5001
    token = get_lan_agent_token()
    has_webview = "1" if module_available("webview") else "0"
    download_name = "pypondo-client-standalone.zip"
    source_signature = build_path_signature([
        os.path.join(basedir, "app.py"),
        os.path.join(basedir, "lan_agent.py"),
        APP_ICON_PATH
    ])
    cache_material = f"{server_base_url}|{agent_port}|{token}|{has_webview}|{source_signature}"
    cache_key = hashlib.sha1(cache_material.encode("utf-8", errors="ignore")).hexdigest()
    cached = get_cached_package_bundle("client_bundle", cache_key, download_name)
    if cached is not None:
        return cached

    with PACKAGE_BUILD_EXECUTION_LOCK:
        cached = get_cached_package_bundle("client_bundle", cache_key, download_name)
        if cached is not None:
            return cached
        bundle, built_name = build_client_agent_standalone_bundle(server_base_url=server_base_url)
        return store_cached_package_bundle("client_bundle", cache_key, bundle, built_name)


def build_admin_desktop_bundle():
    has_webview = "1" if module_available("webview") else "0"
    download_name = "pypondo-admin-standalone.zip"
    source_signature = build_path_signature([
        os.path.join(basedir, "app.py"),
        os.path.join(basedir, "desktop_app.py"),
        os.path.join(basedir, "templates"),
        APP_ICON_PATH
    ])
    cache_material = f"{has_webview}|{source_signature}"
    cache_key = hashlib.sha1(cache_material.encode("utf-8", errors="ignore")).hexdigest()
    cached = get_cached_package_bundle("admin_bundle", cache_key, download_name)
    if cached is not None:
        return cached

    with PACKAGE_BUILD_EXECUTION_LOCK:
        cached = get_cached_package_bundle("admin_bundle", cache_key, download_name)
        if cached is not None:
            return cached

        ensure_packaging_tooling()

        with tempfile.TemporaryDirectory(prefix="pypondo-admin-build-") as temp_dir:
            add_data_entries = [f"{os.path.join(basedir, 'templates')};templates"]
            collect_modules = ["webview"] if module_available("webview") else []
            admin_exe = build_executable(
                work_dir=temp_dir,
                entry_script=os.path.join(basedir, "desktop_app.py"),
                exe_name="PyPondoAdmin",
                windowed=True,
                add_data_entries=add_data_entries,
                collect_all_modules=collect_modules
            )

            readme = (
                "PyPondo Admin Desktop App (Standalone EXE)\r\n"
                "=========================================\r\n\r\n"
                "How to use:\r\n"
                "1. Extract this ZIP on the admin/server PC.\r\n"
                "2. Run PyPondoAdmin.exe.\r\n"
                "3. No Python/compiler is required on the target PC.\r\n"
                "4. Share the unified package from admin dashboard using DOWNLOAD APP (ADMIN+CLIENT).\r\n"
            )

            memory = io.BytesIO()
            with zipfile.ZipFile(memory, "w", zipfile.ZIP_STORED) as zf:
                zf.write(admin_exe, arcname="PyPondoAdmin.exe")
                zf.writestr("README_ADMIN.txt", readme)
                if os.path.exists(APP_ICON_PATH):
                    zf.write(APP_ICON_PATH, arcname="pypondo.ico")
            memory.seek(0)
            return store_cached_package_bundle("admin_bundle", cache_key, memory, download_name)


def build_all_in_one_bundle(server_base_url=None):
    server_base_url = (server_base_url or get_server_public_base_url()).rstrip("/")
    agent_port = normalize_agent_port(os.getenv("LAN_AGENT_DEFAULT_PORT", "5001")) or 5001
    token = get_lan_agent_token()
    has_webview = "1" if module_available("webview") else "0"
    download_name = "pypondo-all-in-one.zip"
    source_signature = build_path_signature([
        os.path.join(basedir, "app.py"),
        os.path.join(basedir, "lan_agent.py"),
        os.path.join(basedir, "desktop_app.py"),
        os.path.join(basedir, "templates"),
        APP_ICON_PATH
    ])
    cache_material = f"{server_base_url}|{agent_port}|{token}|{has_webview}|{source_signature}"
    cache_key = hashlib.sha1(cache_material.encode("utf-8", errors="ignore")).hexdigest()
    cached = get_cached_package_bundle("all_in_one_bundle", cache_key, download_name)
    if cached is not None:
        return cached

    with PACKAGE_BUILD_EXECUTION_LOCK:
        cached = get_cached_package_bundle("all_in_one_bundle", cache_key, download_name)
        if cached is not None:
            return cached

        admin_bundle, admin_name = build_admin_desktop_bundle()
        client_bundle, client_name = build_client_agent_bundle(server_base_url=server_base_url)
        admin_bytes = admin_bundle.getvalue() if hasattr(admin_bundle, "getvalue") else bytes(admin_bundle)
        client_bytes = client_bundle.getvalue() if hasattr(client_bundle, "getvalue") else bytes(client_bundle)

        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w", zipfile.ZIP_STORED) as zf:
            with zipfile.ZipFile(io.BytesIO(admin_bytes), "r") as admin_zip:
                for entry in admin_zip.infolist():
                    if entry.is_dir():
                        continue
                    zf.writestr(f"Admin/{entry.filename}", admin_zip.read(entry.filename))

            with zipfile.ZipFile(io.BytesIO(client_bytes), "r") as client_zip:
                for entry in client_zip.infolist():
                    if entry.is_dir():
                        continue
                    zf.writestr(f"Client/{entry.filename}", client_zip.read(entry.filename))

            readme = (
                "PyPondo Unified Package (Admin + Client)\r\n"
                "========================================\r\n\r\n"
                f"Server URL (client preset): {server_base_url or '(not set)'}\r\n"
                f"Client Register URL: {(server_base_url + '/api/agent/register-lan') if server_base_url else '(not set)'}\r\n"
                f"Client Agent Port: {agent_port}\r\n\r\n"
                "Package layout:\r\n"
                "- Admin\\PyPondoAdmin.exe\r\n"
                "- Client\\PyPondoClient.exe\r\n\r\n"
                "How to use:\r\n"
                "1. Extract this ZIP.\r\n"
                "2. On admin/server PC: run Admin\\PyPondoAdmin.exe\r\n"
                "3. On each client PC: run Client\\start_client_app.bat (or Client\\PyPondoClient.exe)\r\n"
                "4. No Python/compiler is required on target PCs.\r\n"
            )
            zf.writestr("README_ALL_IN_ONE.txt", readme)
            zf.writestr("bundle-info.txt", f"admin={admin_name}\r\nclient={client_name}\r\n")
            if os.path.exists(APP_ICON_PATH):
                zf.write(APP_ICON_PATH, arcname="pypondo.ico")
        memory.seek(0)
        return store_cached_package_bundle("all_in_one_bundle", cache_key, memory, download_name)


def trigger_all_in_one_bundle_prebuild(server_base_url=None):
    with PACKAGE_BUILD_PREWARM_LOCK:
        if "all_in_one_bundle" in PACKAGE_BUILD_PREWARM_RUNNING:
            return False
        PACKAGE_BUILD_PREWARM_RUNNING.add("all_in_one_bundle")

    resolved_url = (server_base_url or "").strip().rstrip("/")

    def _runner():
        try:
            build_all_in_one_bundle(server_base_url=resolved_url or None)
        except Exception as exc:
            app.logger.warning("All-in-one bundle prebuild failed: %s", exc)
        finally:
            with PACKAGE_BUILD_PREWARM_LOCK:
                PACKAGE_BUILD_PREWARM_RUNNING.discard("all_in_one_bundle")

    threading.Thread(target=_runner, daemon=True, name="pypondo-all-in-one-prebuild").start()
    return True


def trigger_client_bundle_prebuild(server_base_url=None):
    with PACKAGE_BUILD_PREWARM_LOCK:
        if "client_bundle" in PACKAGE_BUILD_PREWARM_RUNNING:
            return False
        PACKAGE_BUILD_PREWARM_RUNNING.add("client_bundle")

    resolved_url = (server_base_url or "").strip().rstrip("/")

    def _runner():
        try:
            build_client_agent_bundle(server_base_url=resolved_url or None)
        except Exception as exc:
            app.logger.warning("Client bundle prebuild failed: %s", exc)
        finally:
            with PACKAGE_BUILD_PREWARM_LOCK:
                PACKAGE_BUILD_PREWARM_RUNNING.discard("client_bundle")

    threading.Thread(target=_runner, daemon=True, name="pypondo-client-prebuild").start()
    return True


def get_user_active_pc():
    if not current_user.is_authenticated:
        return None
    active_session = Session.query.filter_by(user_id=current_user.id, end_time=None).order_by(Session.start_time.desc()).first()
    if not active_session:
        return None
    return db.session.get(PC, active_session.pc_id)


@app.before_request
def bootstrap_schema():
    if not getattr(app, "_schema_ready", False):
        db.create_all()
        ensure_pc_lan_ip_column()
        ensure_booking_date_column()
        ensure_core_seed_data()
        retire_legacy_connect_request_commands()
        app._schema_ready = True
    if not getattr(app, "_download_bundle_prebuild_started", False):
        configured_url = os.getenv("LAN_SERVER_PUBLIC_BASE_URL", "").strip().rstrip("/")
        prebuild_url = configured_url or get_server_public_base_url().rstrip("/")
        if prebuild_url and trigger_all_in_one_bundle_prebuild(prebuild_url):
            app._download_bundle_prebuild_started = True


@app.route('/favicon.ico')
def favicon():
    if os.path.exists(APP_ICON_PATH):
        return send_file(APP_ICON_PATH, mimetype='image/x-icon')
    return '', 404


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


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials', 'error')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))


# --- Main Routes ---

@app.route('/')
@login_required
def index():
    pcs = PC.query.all()
    users = User.query.all() if current_user.is_admin else [current_user]
    active_sessions = Session.query.filter_by(end_time=None).all()
    recent_payments = PaymentTransaction.query.filter_by(user_id=current_user.id).order_by(PaymentTransaction.created_at.desc()).limit(5).all()
    if current_user.is_admin and not getattr(app, "_download_bundle_prebuild_started", False):
        server_url_hint = get_server_public_base_url().rstrip("/")
        if server_url_hint and trigger_all_in_one_bundle_prebuild(server_url_hint):
            app._download_bundle_prebuild_started = True
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
        rows = db.session.query(
            LanCommand.pc_name,
            func.count(LanCommand.id)
        ).filter(
            LanCommand.status.in_(list(pending_statuses))
        ).group_by(
            LanCommand.pc_name
        ).all()
        pending_counts = {pc_name: int(count) for pc_name, count in rows}

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
        power_command_confirm_text=POWER_COMMAND_CONFIRM_TEXT,
        today_date=datetime.now().strftime("%Y-%m-%d")
    )


# --- ADMIN FEATURES ---

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
    bookings = Booking.query.order_by(Booking.booking_date.asc(), Booking.time_slot.asc(), Booking.id.asc()).all()
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


@app.route('/admin/download_app')
@login_required
def download_app():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    try:
        bundle, download_name = build_all_in_one_bundle()
    except Exception as exc:
        flash(f'Failed to build unified app package: {exc}', 'error')
        return redirect(url_for('index'))

    db.session.add(AdminLog(
        admin_name=current_user.username,
        action=f"Downloaded unified app package: {download_name}"
    ))
    db.session.commit()
    return send_file(
        bundle,
        mimetype="application/zip",
        as_attachment=True,
        download_name=download_name
    )


@app.route('/admin/download_client_app')
@login_required
def download_client_app():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    return redirect(url_for('download_app'))


@app.route('/admin/download_client_app/<int:pc_id>')
@login_required
def download_client_app_legacy(pc_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    return redirect(url_for('download_app'))


@app.route('/admin/download_admin_app')
@login_required
def download_admin_app():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    return redirect(url_for('download_app'))


@app.route('/admin/request_connect', methods=['POST'])
@login_required
def admin_request_connect():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    pc_id = request.form.get('pc_id', type=int)
    connect_ip_raw = (request.form.get('connect_ip') or '').strip()
    connect_port_raw = (request.form.get('connect_port') or '').strip()

    pc = db.session.get(PC, pc_id) if pc_id else None
    if not pc:
        flash('Invalid PC selected for auto-connect.', 'error')
        return redirect(url_for('index'))

    connect_ip = normalize_lan_ip(connect_ip_raw)
    if not connect_ip:
        flash('Invalid target IP for auto-connect.', 'error')
        return redirect(url_for('index'))
    if ":" not in connect_ip and connect_ip in get_gateway_ipv4_set():
        flash('Gateway IP cannot be used as a client target.', 'error')
        return redirect(url_for('index'))

    requested_port = normalize_agent_port(connect_port_raw) if connect_port_raw else None
    if connect_port_raw and not requested_port:
        flash('Invalid agent port. Use 1024-65535 (recommended 5001).', 'error')
        return redirect(url_for('index'))

    # Keep the selected target for this PC so next actions use the same endpoint.
    pc.lan_ip = connect_ip
    if requested_port:
        pc.lan_port = requested_port
    else:
        pc.lan_port = normalize_agent_port(os.getenv("LAN_AGENT_DEFAULT_PORT", "5001")) or 5001

    ok, message = probe_pc_agent(pc.name)
    if ok:
        pc.last_agent_seen_at = datetime.now()

    db.session.add(AdminLog(
        admin_name=current_user.username,
        action=f"Admin auto-connect target set for {pc.name} via {connect_ip}:{pc.lan_port or os.getenv('LAN_AGENT_DEFAULT_PORT', '5001')}: {message}"
    ))
    db.session.commit()

    if not ok:
        flash(f'Auto-connect saved for {pc.name}, but client is not reachable yet. {message}', 'info')
    else:
        flash(f'Auto-connect ready for {pc.name} ({connect_ip}). {message}', 'success')
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

    pending = LanCommand.query.filter(
        LanCommand.pc_name == pc.name,
        LanCommand.status.in_(["queued", "sent"])
    ).all()

    if not pending:
        flash(f'No pending commands for {pc.name}.', 'info')
        return redirect(url_for('index'))

    now_dt = datetime.now()
    for cmd in pending:
        cmd.status = "failed"
        cmd.completed_at = now_dt
        cmd.result_message = "Cleared by admin"

    db.session.add(AdminLog(
        admin_name=current_user.username,
        action=f"Cleared {len(pending)} pending LAN command(s) for {pc.name}"
    ))
    db.session.commit()
    flash(f'Cleared {len(pending)} pending command(s) for {pc.name}.', 'success')
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
    pc_id = request.form.get('pc_id', type=int)
    booking_date_raw = (request.form.get('booking_date') or '').strip()
    time_slot_raw = (request.form.get('time_slot') or '').strip()

    if not pc_id:
        flash('Invalid PC selected.', 'error')
        return redirect(url_for('index'))
    if not booking_date_raw:
        flash('Booking date is required.', 'error')
        return redirect(url_for('index'))
    if not time_slot_raw:
        flash('Booking time is required.', 'error')
        return redirect(url_for('index'))

    try:
        booking_date_dt = datetime.strptime(booking_date_raw, "%Y-%m-%d").date()
    except ValueError:
        flash('Invalid booking date format.', 'error')
        return redirect(url_for('index'))
    if booking_date_dt < datetime.now().date():
        flash('Booking date cannot be in the past.', 'error')
        return redirect(url_for('index'))

    try:
        time_slot = datetime.strptime(time_slot_raw, "%H:%M").strftime("%H:%M")
    except ValueError:
        flash('Invalid booking time format. Use HH:MM.', 'error')
        return redirect(url_for('index'))

    booking_date = booking_date_dt.strftime("%Y-%m-%d")
    existing = Booking.query.filter_by(pc_id=pc_id, booking_date=booking_date, time_slot=time_slot).first()
    if existing:
        flash(f'PC is already booked on {booking_date} at {time_slot}.', 'error')
        return redirect(url_for('index'))

    new_booking = Booking(user_id=current_user.id, pc_id=pc_id, booking_date=booking_date, time_slot=time_slot)
    db.session.add(new_booking)
    db.session.commit()
    flash(f'Reservation confirmed for {booking_date} at {time_slot}.', 'success')
    return redirect(url_for('index'))


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

    reason = (request.form.get('reason') or '').strip()
    confirm_text = (request.form.get('confirm_text') or '').strip()
    if command in {"restart", "shutdown"}:
        if len(reason) < 8 or len(reason) > 200:
            flash('Reason is required for restart/shutdown (8-200 characters).', 'error')
            return redirect(url_for('index'))
        if confirm_text != POWER_COMMAND_CONFIRM_TEXT:
            flash(f'Confirmation text must be {POWER_COMMAND_CONFIRM_TEXT}.', 'error')
            return redirect(url_for('index'))

    payload = {"requested_by": current_user.username}
    if reason:
        payload["reason"] = reason

    payload["skip_user_approval"] = "1"
    ok, message = send_lan_command(pc.name, command, payload)
    db.session.add(AdminLog(admin_name=current_user.username, action=f"LAN auto-connect command '{command}' to {pc.name}: {message}"))
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

    payload = dict(payload or {})
    payload.setdefault("requested_by", current_user.username)
    payload.setdefault("skip_user_approval", "1")

    if command in {"restart", "shutdown"}:
        reason = str(payload.get("reason", "")).strip()
        if len(reason) < 8 or len(reason) > 200:
            return jsonify({"ok": False, "error": "reason is required for restart/shutdown (8-200 characters)"}), 400
        confirm_text = str(payload.get("confirm_text", "")).strip()
        if confirm_text != POWER_COMMAND_CONFIRM_TEXT:
            return jsonify({"ok": False, "error": f"confirm_text must be {POWER_COMMAND_CONFIRM_TEXT}"}), 400

    ok, message = send_lan_command(pc_name, command, payload)
    db.session.add(AdminLog(admin_name=current_user.username, action=f"API LAN auto-connect command '{command}' to {pc_name}: {message}"))
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


@app.route('/api/user/pending-connect-request', methods=['GET'])
@login_required
def api_user_pending_connect_request():
    return jsonify({"ok": True, "no_request": True, "disabled": True}), 200


@app.route('/api/user/respond-connect-request', methods=['POST'])
@login_required
def api_user_respond_connect_request():
    return jsonify({"ok": False, "error": "Connection request flow is disabled. Admin now auto-connects to client agent."}), 410


@app.route('/api/connect-request/<int:command_id>', methods=['GET'])
def api_connect_request_page(command_id):
    return "<h3>Connection request flow is disabled. Admin now auto-connects directly.</h3>", 410


@app.route('/api/connect-request/<int:command_id>/respond', methods=['POST'])
def api_connect_request_respond(command_id):
    return "<h3>Connection request flow is disabled. Admin now auto-connects directly.</h3>", 410


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
    pending_rows = db.session.query(
        LanCommand.pc_name,
        func.count(LanCommand.id)
    ).filter(
        LanCommand.status.in_(["queued", "sent"])
    ).group_by(
        LanCommand.pc_name
    ).all()
    pending_counts = {pc_name: int(count) for pc_name, count in pending_rows}
    discovered_all = discover_lan_addresses()
    gateway_ips = get_default_gateway_ips()
    force_scan = str(request.args.get("force_scan", "")).strip().lower() in {"1", "true", "yes"}
    fast_mode = str(request.args.get("fast", "")).strip().lower() in {"1", "true", "yes"}
    return jsonify({
        "ok": True,
        "local_ips": get_local_lan_addresses(force=force_scan),
        "discovered_ips": discovered_all,
        "gateway_ips": gateway_ips,
        "discovered_pc_ips": [ip for ip in discovered_all if ip not in set(gateway_ips)],
        "lan_summary": build_primary_ipv4_network_summary(force=force_scan),
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
    incoming_name = str(data.get("pc_name", "")).strip()
    normalized_name = normalize_agent_pc_name(incoming_name)
    pc = PC.query.filter_by(name=normalized_name).first()
    if not pc:
        auto_name = make_unique_agent_pc_name(normalized_name)
        pc = PC(name=auto_name)
        db.session.add(pc)
        db.session.flush()

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
    db.session.add(AdminLog(admin_name=f"agent:{pc.name}", action=f"Auto-registered LAN target {detected_ip}:{agent_port}"))
    db.session.commit()
    cmd = pick_next_lan_command_for_names([pc.name, normalized_name])
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
        "pc_name": pc.name,
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


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        ensure_pc_lan_ip_column()
        ensure_booking_date_column()
        seeded = ensure_core_seed_data()
        retired = retire_legacy_connect_request_commands()
        if seeded:
            print("DB Init complete: default admin + PCs created.")
        if retired:
            print(f"Retired {retired} legacy connect_request command(s).")
    app_host = os.getenv("APP_HOST", "0.0.0.0").strip() or "0.0.0.0"
    app_port = int(os.getenv("APP_PORT", "5000"))
    app_debug = str(os.getenv("APP_DEBUG", "1")).strip().lower() in {"1", "true", "yes"}
    app.run(host=app_host, port=app_port, debug=app_debug)
