from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

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


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


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
    return render_template('index.html', pcs=pcs, users=users, sessions=active_sessions)


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


@app.route('/start_session/<int:pc_id>/<int:user_id>')
@login_required
def start_session(pc_id, user_id):
    if not current_user.is_admin: return redirect(url_for('index'))
    user = User.query.get(user_id)
    pc = PC.query.get(pc_id)
    if user.pondo <= 0:
        flash('Insufficient Pondo!', 'error')
        return redirect(url_for('index'))
    new_session = Session(user_id=user.id, pc_id=pc.id)
    pc.is_occupied = True
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/end_session/<int:session_id>')
@login_required
def end_session(session_id):
    if not current_user.is_admin: return redirect(url_for('index'))
    session = Session.query.get(session_id)
    if not session: return redirect(url_for('index'))
    pc = PC.query.get(session.pc_id)
    user = User.query.get(session.user_id)
    session.end_time = datetime.now()
    duration = session.end_time - session.start_time
    hours_played = duration.total_seconds() / 3600
    cost = round(hours_played * HOURLY_RATE, 2)
    session.cost = cost
    user.pondo -= cost
    pc.is_occupied = False
    db.session.commit()
    flash(f'Session Ended. Cost: ₱{cost}.', 'info')
    return redirect(url_for('index'))


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