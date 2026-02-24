from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
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

app = Flask(__name__)

# --- Config ---
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'pccafe.db')
app.config['SECRET_KEY'] = 'super_secret_cyber_key'

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

HOURLY_RATE = 20.0
ALLOWED_LAN_COMMANDS = {"lock", "restart", "shutdown", "wake"}
MAX_TOPUP_AMOUNT = 10000.0
TOPUP_CURRENCY = os.getenv("TOPUP_CURRENCY", "php").strip().lower() or "php"


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


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    pc_id = db.Column(db.Integer, db.ForeignKey('pc.id'), nullable=False)
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


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def ensure_pc_lan_ip_column():
    try:
        cols = [row[1] for row in db.session.execute(text("PRAGMA table_info(pc)")).fetchall()]
    except Exception:
        db.create_all()
        cols = [row[1] for row in db.session.execute(text("PRAGMA table_info(pc)")).fetchall()]
    if "lan_ip" not in cols:
        db.session.execute(text("ALTER TABLE pc ADD COLUMN lan_ip VARCHAR(64)"))
        db.session.commit()


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


def get_local_ipv4_addresses():
    try:
        output = subprocess.check_output(["ipconfig"], text=True, encoding="utf-8", errors="ignore")
    except Exception:
        return []

    matches = re.findall(r"(\d+\.\d+\.\d+\.\d+)", output)
    ips = []
    for value in matches:
        ip = normalize_ipv4(value)
        if not ip:
            continue
        if ip.startswith("169.254.") or ip not in ips:
            if not ip.startswith("169.254."):
                ips.append(ip)
    return ips


def discover_lan_ips():
    try:
        output = subprocess.check_output(["arp", "-a"], text=True, encoding="utf-8", errors="ignore")
    except Exception:
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


def resolve_pc_target(pc_name):
    targets = load_lan_targets()
    target = targets.get(pc_name)
    if target:
        return target

    pc = PC.query.filter_by(name=pc_name).first()
    if not pc or not pc.lan_ip:
        return None

    default_port = os.getenv("LAN_AGENT_DEFAULT_PORT", "5001").strip() or "5001"
    return f"http://{pc.lan_ip}:{default_port}"


def send_lan_command(pc_name, command, payload=None):
    target = resolve_pc_target(pc_name)
    if not target:
        return False, f"No LAN agent configured for {pc_name}"

    shared_token = os.getenv("LAN_AGENT_TOKEN", "").strip()
    if not shared_token:
        return False, "LAN_AGENT_TOKEN is missing on server"

    body = json.dumps({
        "command": command,
        "payload": payload if isinstance(payload, dict) else {}
    }).encode("utf-8")

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
            return ok, message
    except http_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        return False, f"Agent rejected command ({exc.code}): {detail}"
    except Exception as exc:
        return False, f"Failed to reach LAN agent: {exc}"


def finalize_session(session):
    if not session or session.end_time is not None:
        return 0.0

    pc = PC.query.get(session.pc_id)
    user = User.query.get(session.user_id)
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


@app.before_request
def bootstrap_schema():
    if not getattr(app, "_schema_ready", False):
        db.create_all()
        ensure_pc_lan_ip_column()
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
    local_ips = get_local_ipv4_addresses() if current_user.is_admin else []
    discovered_ips = discover_lan_ips() if current_user.is_admin else []
    assigned_ips = {pc.lan_ip for pc in pcs if pc.lan_ip}
    return render_template(
        'index.html',
        pcs=pcs,
        users=users,
        sessions=active_sessions,
        recent_payments=recent_payments,
        local_ips=local_ips,
        discovered_ips=discovered_ips,
        assigned_ips=assigned_ips
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
    bookings = Booking.query.all()
    return render_template('bookings.html', bookings=bookings)


@app.route('/delete_booking/<int:id>')
@login_required
def delete_booking(id):
    if not current_user.is_admin: return redirect(url_for('index'))
    booking = Booking.query.get(id)
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

    discovered = discover_lan_ips()
    if not discovered:
        flash('No LAN IPs discovered. Ensure clients are online and visible in ARP table.', 'error')
        return redirect(url_for('index'))

    pcs = PC.query.order_by(PC.id.asc()).all()
    already_used = {pc.lan_ip for pc in pcs if pc.lan_ip}
    available = [ip for ip in discovered if ip not in already_used]

    assigned_count = 0
    for pc in pcs:
        if pc.lan_ip:
            continue
        if not available:
            break
        pc.lan_ip = available.pop(0)
        assigned_count += 1

    db.session.add(AdminLog(admin_name=current_user.username, action=f"Auto-assigned LAN IPs to {assigned_count} PC(s)"))
    db.session.commit()
    flash(f'Auto-assigned LAN IP to {assigned_count} PC(s).', 'success')
    return redirect(url_for('index'))


@app.route('/admin/set_pc_ip/<int:pc_id>', methods=['POST'])
@login_required
def set_pc_ip(pc_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))

    pc = PC.query.get(pc_id)
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

    ip = normalize_ipv4(raw_ip)
    if not ip:
        flash('Invalid IPv4 address.', 'error')
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
    time_slot = request.form['time_slot']

    # Check if already booked for that slot (Optional logic improvement)
    # existing = Booking.query.filter_by(pc_id=pc_id, time_slot=time_slot).first()
    # if existing: flash('Slot taken', 'error'); return ...

    new_booking = Booking(user_id=current_user.id, pc_id=pc_id, time_slot=time_slot)
    db.session.add(new_booking)
    db.session.commit()
    flash('Reservation confirmed!', 'success')
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
    pc = PC.query.get(pc_id) if pc_id else None

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
    user = User.query.get(user_id)
    pc = PC.query.get(pc_id)
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
    session = Session.query.get(session_id)
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

    user = User.query.get(user_id)
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
            user = User.query.get(int(user_id))
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
    return jsonify({
        "ok": True,
        "local_ips": get_local_ipv4_addresses(),
        "discovered_ips": discover_lan_ips(),
        "pc_assignments": [{"pc_id": pc.id, "pc_name": pc.name, "lan_ip": pc.lan_ip} for pc in pcs]
    }), 200


@app.route('/api/admin/auto-assign-ips', methods=['POST'])
@login_required
def api_admin_auto_assign_ips():
    if not current_user.is_admin:
        return jsonify({"ok": False, "error": "admin-only endpoint"}), 403

    discovered = discover_lan_ips()
    pcs = PC.query.order_by(PC.id.asc()).all()
    already_used = {pc.lan_ip for pc in pcs if pc.lan_ip}
    available = [ip for ip in discovered if ip not in already_used]

    assigned = []
    for pc in pcs:
        if pc.lan_ip or not available:
            continue
        ip = available.pop(0)
        pc.lan_ip = ip
        assigned.append({"pc_id": pc.id, "pc_name": pc.name, "lan_ip": ip})

    db.session.add(AdminLog(admin_name=current_user.username, action=f"API auto-assigned LAN IPs to {len(assigned)} PC(s)"))
    db.session.commit()
    return jsonify({"ok": True, "assigned_count": len(assigned), "assigned": assigned}), 200


if __name__ == '__main__':
    if not os.path.exists(os.path.join(basedir, 'pccafe.db')):
        with app.app_context():
            db.create_all()
            # Default PCs
            for i in range(1, 6):
                db.session.add(PC(name=f'PC-{i}'))
            # Admin
            admin = User(username='admin', is_admin=True)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("DB Init: admin/admin123")
    app.run(debug=True)
