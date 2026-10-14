"""Regression tests for the PyPondo equipment/PC QR label feature.

Locks in the launch-readiness fixes: label authorization (IDOR), the read-only
GET label route, deactivated-label handling, the unified qr_value format,
locally generated QR images, and the audit/error paths.

Runs against a throwaway data directory, so the developer's pccafe.db and
community_equipment.db are never touched.

Usage:
    pytest test_equipment_qr.py
    python test_equipment_qr.py     # standalone; used by quickstart.bat
"""
import base64
import glob
import io
import os
import subprocess
import sys
import tempfile

# PYPONDO_DATA_DIR and PYPONDO_SECRET_KEY are read at app import time to build
# the database URIs, so they must be set before app.py is imported.
os.environ.setdefault('PYPONDO_DATA_DIR', tempfile.mkdtemp(prefix='pypondo_test_'))
os.environ.setdefault('PYPONDO_SECRET_KEY', 'test-secret-key-not-for-production')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pytest  # noqa: E402
import qrcode  # noqa: E402
from qrcode.constants import ERROR_CORRECT_H  # noqa: E402

import app as app_module  # noqa: E402
from app import (  # noqa: E402
    CommunityEquipment,
    CommunityEquipmentCategory,
    CommunityEquipmentQRCode,
    CommunityLaboratory,
    PC,
    User,
    db,
    equipment_qr_value,
    ensure_community_user,
)

PASSWORD = 'pw12345'
_counter = 0


def _uniq(prefix):
    global _counter
    _counter += 1
    return f'{prefix}-{_counter}'


@pytest.fixture(scope='session')
def app():
    with app_module.app.app_context():
        db.create_all()
    return app_module.app


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username):
    client.get('/logout')
    response = client.post('/login', data={'username': username, 'password': PASSWORD})
    assert response.status_code in (200, 302), f'login failed for {username}'


def make_user(app, role, is_admin=False):
    """Create a user of the given role; returns (username, community_identity_id)."""
    with app.app_context():
        user = User(username=_uniq(role), full_name=f'{role.title()} User', role=role,
                    is_admin=is_admin, is_active_staff=True)
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
        username = user.username
        identity_id = None
        if role == 'instructor':
            identity = ensure_community_user(user)
            db.session.commit()
            identity_id = identity.user_id
        # Detach the token before the session closes so callers can use it later.
        token = app_module.create_mobile_api_token(user) if role != 'student' else None
    return username, identity_id, token


@pytest.fixture
def staff(client, app):
    """An equipment-management staff user, already logged in."""
    username, _, _ = make_user(app, 'laboratory_custodian')
    login(client, username)


@pytest.fixture
def make_equipment(app):
    """Create equipment; returns (equipment_id, equipment_code, qr_value_or_None)."""
    def _make(owner_identity_id=None, with_code=True, is_active=True):
        with app.app_context():
            laboratory = CommunityLaboratory.query.first()
            if laboratory is None:
                laboratory = CommunityLaboratory(laboratory_name='Test Lab')
                db.session.add(laboratory)
            category = CommunityEquipmentCategory.query.first()
            if category is None:
                category = CommunityEquipmentCategory(category_name='Test Category')
                db.session.add(category)
            db.session.flush()
            item = CommunityEquipment(
                laboratory_id=laboratory.laboratory_id, category_id=category.category_id,
                equipment_code=_uniq('EQ'), equipment_name='Test Centrifuge',
                owner_user_id=owner_identity_id)
            db.session.add(item)
            db.session.flush()
            qr = None
            if with_code:
                qr = CommunityEquipmentQRCode(equipment_id=item.equipment_id,
                                              qr_value=equipment_qr_value(item),
                                              is_active=is_active)
                db.session.add(qr)
            db.session.commit()
            return item.equipment_id, item.equipment_code, (qr.qr_value if qr else None)
    return _make


def qr_value_for(equipment_id, app):
    with app.app_context():
        row = CommunityEquipmentQRCode.query.filter_by(equipment_id=equipment_id).first()
        return row.qr_value if row else None


def qr_is_active(equipment_id, app):
    with app.app_context():
        row = CommunityEquipmentQRCode.query.filter_by(equipment_id=equipment_id).first()
        return row.is_active if row else None


# ---------------------------------------------------------------------------
# The label GET route must be read-only
# ---------------------------------------------------------------------------

def test_get_label_does_not_write_to_database(client, staff, make_equipment, app):
    equipment_id, _, _ = make_equipment(with_code=False)
    with app.app_context():
        before = CommunityEquipmentQRCode.query.count()

    assert client.get(f'/community/qr/{equipment_id}').status_code == 200

    with app.app_context():
        assert CommunityEquipmentQRCode.query.count() == before, 'GET must not mint a QR code'


def test_label_page_offers_generate_when_no_code_exists(client, staff, make_equipment):
    equipment_id, _, _ = make_equipment(with_code=False)
    body = client.get(f'/community/qr/{equipment_id}').data
    assert b'Not generated' in body
    assert b'Generate QR code' in body


def test_image_endpoint_404s_when_no_code_exists(client, staff, make_equipment):
    equipment_id, _, _ = make_equipment(with_code=False)
    assert client.get(f'/community/qr/{equipment_id}/image').status_code == 404


def test_staff_can_view_label_and_svg_image(client, staff, make_equipment):
    equipment_id, code, qr_value = make_equipment()

    page = client.get(f'/community/qr/{equipment_id}')
    assert page.status_code == 200
    assert qr_value.encode() in page.data
    assert b'status active' in page.data

    image = client.get(f'/community/qr/{equipment_id}/image')
    assert image.status_code == 200
    assert image.mimetype == 'image/svg+xml'
    assert b'<svg' in image.data[:400]
    assert code in image.headers.get('Content-Disposition', ''), \
        'download filename must use the equipment code, matching the template'


# ---------------------------------------------------------------------------
# Authorization: before the fix, any logged-in user could read any label
# ---------------------------------------------------------------------------

def test_anonymous_visit_is_redirected_not_served(client, make_equipment):
    equipment_id, _, _ = make_equipment()
    assert client.get(f'/community/qr/{equipment_id}').status_code == 302


def test_student_cannot_read_a_label_they_do_not_own(client, staff, make_equipment, app):
    equipment_id, _, _ = make_equipment()
    student_username, _, _ = make_user(app, 'student')
    login(client, student_username)

    assert client.get(f'/community/qr/{equipment_id}').status_code == 404
    assert client.get(f'/community/qr/{equipment_id}/image').status_code == 404


def test_instructor_can_read_own_label_but_not_others(client, make_equipment, app):
    instructor_username, instructor_identity, _ = make_user(app, 'instructor')
    owned_id, _, _ = make_equipment(owner_identity_id=instructor_identity)
    other_id, _, _ = make_equipment(owner_identity_id=None)

    login(client, instructor_username)
    assert client.get(f'/community/qr/{owned_id}').status_code == 200
    assert client.get(f'/community/qr/{other_id}').status_code == 404, \
        'instructor must not read labels for items they do not own'
    assert client.get(f'/community/qr/{other_id}/image').status_code == 404


# ---------------------------------------------------------------------------
# Deactivated and unknown labels must not dead-end
# ---------------------------------------------------------------------------

def test_deactivated_label_renders_instead_of_dead_404(client, staff, make_equipment):
    equipment_id, _, _ = make_equipment()
    client.post(f'/community/qr/{equipment_id}', data={'action': 'deactivate'})

    page = client.get(f'/community/qr/{equipment_id}')
    assert page.status_code == 200, 'a deactivated code must still show its label'
    assert b'status inactive' in page.data
    assert b'Reactivate' in page.data
    # The physical sticker is still on the machine, so the image must resolve.
    assert client.get(f'/community/qr/{equipment_id}/image').status_code == 200


def test_unknown_equipment_id_returns_styled_404(client, staff):
    response = client.get('/community/qr/999999')
    assert response.status_code == 404
    assert b'error-card' in response.data, 'must use the styled error page, not the raw Flask page'


def test_api_requests_receive_json_errors(client):
    response = client.get('/api/not-a-real-endpoint')
    assert response.status_code == 404
    assert response.is_json


# ---------------------------------------------------------------------------
# POST lifecycle and audit trail
# ---------------------------------------------------------------------------

def test_create_deactivate_regenerate_lifecycle(client, staff, make_equipment, app):
    equipment_id, code, _ = make_equipment(with_code=False)

    client.post(f'/community/qr/{equipment_id}', data={'action': 'create'}, follow_redirects=True)
    value = qr_value_for(equipment_id, app)
    assert value is not None
    parts = value.split(':')
    assert parts[:2] == ['PYPONDO-EQUIPMENT', code], f'unexpected format: {value}'
    assert len(parts[2]) == 12, f'missing random suffix: {value}'

    client.post(f'/community/qr/{equipment_id}', data={'action': 'deactivate'})
    assert qr_is_active(equipment_id, app) is False

    client.post(f'/community/qr/{equipment_id}', data={'action': 'regenerate'},
                follow_redirects=True)
    rotated = qr_value_for(equipment_id, app)
    assert rotated != value, 'regenerate must rotate the value'
    assert qr_is_active(equipment_id, app) is True


def test_qr_lifecycle_actions_are_audited(client, staff, make_equipment, app):
    equipment_id, _, _ = make_equipment(with_code=False)
    for action in ('create', 'deactivate', 'regenerate'):
        client.post(f'/community/qr/{equipment_id}', data={'action': action})

    with app.app_context():
        actions = ' '.join(row.action for row in app_module.CommunityAuditLog.query.filter_by(
            table_name='equipment_qr_codes').all())
    for expected in ('Created', 'Deactivate', 'Regenerate'):
        assert expected in actions, f'{expected} is not audited: {actions}'


def test_flash_message_renders_on_label_page(client, staff, make_equipment):
    equipment_id, _, _ = make_equipment()
    response = client.post(f'/community/qr/{equipment_id}', data={'action': 'deactivate'},
                           follow_redirects=True)
    assert b'class="flash success"' in response.data
    assert b'Equipment QR code deactivate.' in response.data


# ---------------------------------------------------------------------------
# Scanner compatibility: the format unification must not break scanning
# ---------------------------------------------------------------------------

def test_scan_api_accepts_active_and_rejects_deactivated(client, staff, make_equipment, app):
    _, _, token = make_user(app, 'laboratory_custodian')
    equipment_id, _, qr_value = make_equipment()
    headers = {'Authorization': f'Bearer {token}'}

    ok = client.get('/api/mobile/equipment/scan', query_string={'qr': qr_value}, headers=headers)
    assert ok.status_code == 200 and ok.get_json()['ok'] is True

    client.post(f'/community/qr/{equipment_id}', data={'action': 'deactivate'})
    dead = client.get('/api/mobile/equipment/scan', query_string={'qr': qr_value}, headers=headers)
    assert dead.status_code == 404, 'a deactivated code must be rejected by the scanner'


# ---------------------------------------------------------------------------
# Label durability, and no third-party QR services
# ---------------------------------------------------------------------------

class _FakeItem:
    def __init__(self, code):
        self.equipment_code = code


def test_label_images_can_use_error_correction_h():
    """Physical lab labels get scuffed and solvent-wiped; level M is not enough."""
    qr = qrcode.QRCode(box_size=10, border=4, error_correction=ERROR_CORRECT_H)
    qr.add_data(equipment_qr_value(_FakeItem('EQ-1')))
    qr.make(fit=True)
    buffer = io.BytesIO()
    qr.make_image(fill_color='black', back_color='white').save(buffer, format='PNG')
    assert buffer.getvalue()[:4] == b'\x89PNG'


def test_no_qr_payload_is_sent_to_an_external_service():
    """Pairing QR payloads embed the server's LAN host, port, and tunnel address.

    Handing those to a third-party image API leaks internal network topology and
    breaks on an offline LAN, which is the primary deployment.
    """
    sources = [os.path.join(HERE, 'app.py')]
    template_dir = os.path.join(HERE, 'templates')
    if os.path.isdir(template_dir):
        sources += sorted(glob.glob(os.path.join(template_dir, '*.html')))

    offenders = []
    for path in sources:
        with open(path, encoding='utf-8', errors='replace') as handle:
            text = handle.read()
        for marker in ('api.qrserver.com', 'quickchart.io', 'chart.googleapis.com'):
            if marker in text:
                offenders.append((os.path.basename(path), marker))
    assert not offenders, f'external QR service referenced: {offenders}'


def test_local_qr_data_url_is_self_contained():
    url = app_module.local_qr_data_url('http://192.168.1.50:5000/api/mobile/pairing')
    assert url.startswith('data:image/png;base64,')
    assert 'qrserver' not in url
    assert base64.b64decode(url.split(',', 1)[1])[:4] == b'\x89PNG'


def test_pc_qr_png_endpoint_serves_png(client, app):
    """Regression: qrcode's PNG factory imports PIL lazily, so a missing Pillow
    used to raise at request time and return 500 instead of a label."""
    with app.app_context():
        admin = User(username=_uniq('pcadmin'), full_name='PC Admin', role='administrator',
                     is_admin=True, is_active_staff=True)
        admin.set_password(PASSWORD)
        db.session.add(admin)
        db.session.commit()
        pc = PC(name='Lab PC 1', room='R1')
        db.session.add(pc)
        db.session.commit()
        pc_id, username = pc.id, admin.username

    login(client, username)
    response = client.get(f'/admin/pc/{pc_id}/qr.png')
    assert response.status_code == 200, response.data[:200]
    assert response.mimetype == 'image/png'
    assert response.data[:4] == b'\x89PNG'


# ---------------------------------------------------------------------------
# Template guards
# ---------------------------------------------------------------------------

def test_print_stylesheet_suppresses_animated_background():
    """The background partial sets an !important body colour and fixed-position
    artwork, which otherwise print a grey wash plus neon graphics over the QR."""
    with open(os.path.join(HERE, 'templates', '_animated_background.html'),
              encoding='utf-8') as handle:
        css = handle.read()
    assert '@media print' in css
    assert 'display: none !important' in css
    assert 'background-color: #fff !important' in css


def test_background_partial_resolves_icon_via_url_for():
    with open(os.path.join(HERE, 'templates', '_animated_background.html'),
              encoding='utf-8') as handle:
        markup = handle.read()
    assert "url_for('app_icon')" in markup
    assert '"/app-icon.png"' not in markup, 'hardcoded root path breaks below a sub-path mount'


def test_label_template_accesses_relationships_null_safely():
    with open(os.path.join(HERE, 'templates', 'equipment_qr.html'), encoding='utf-8') as handle:
        markup = handle.read()
    assert 'item.category.category_name if item.category' in markup
    assert 'item.laboratory.laboratory_name if item.laboratory' in markup


def test_label_template_back_link_is_role_aware():
    """A hardcoded equipment_dashboard link bounces instructors to index, since
    that route opens with current_staff_or_redirect()."""
    with open(os.path.join(HERE, 'templates', 'equipment_qr.html'), encoding='utf-8') as handle:
        markup = handle.read()
    assert "'borrower_dashboard'" in markup


def test_all_templates_compile(app):
    for path in sorted(glob.glob(os.path.join(HERE, 'templates', '*.html'))):
        app.jinja_env.get_template(os.path.basename(path))


# ---------------------------------------------------------------------------
# First-launch / migration path, in a subprocess so this session's app
# instance and its already-open database are untouched.
# ---------------------------------------------------------------------------

_FRESH_INSTALL_SNIPPET = r"""
import os, tempfile
os.environ['PYPONDO_DATA_DIR'] = tempfile.mkdtemp(prefix='pypondo_fresh_')
os.environ['PYPONDO_SECRET_KEY'] = 'x'
import app as m
from app import db, CommunityEquipment, CommunityEquipmentQRCode, Equipment
with m.app.app_context():
    db.create_all()
    db.session.add(Equipment(asset_tag='LEGACY-77', name='Old Microscope', status='available'))
    db.session.commit()
    m.app._schema_ready = False
    m.initialize_database()
    first_eq, first_qr = CommunityEquipment.query.count(), CommunityEquipmentQRCode.query.count()
    m.app._schema_ready = False
    m.initialize_database()
    second_eq, second_qr = CommunityEquipment.query.count(), CommunityEquipmentQRCode.query.count()
    print('RESULT', first_eq, first_qr, second_eq, second_qr,
          CommunityEquipmentQRCode.query.first().qr_value)
"""


def test_migration_mints_unified_codes_and_is_idempotent():
    """Re-running the legacy import used to hit the unique equipment_id
    constraint and abort the whole migration."""
    result = subprocess.run([sys.executable, '-c', _FRESH_INSTALL_SNIPPET], cwd=HERE,
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, f'fresh install failed: {result.stderr[-1500:]}'
    line = next(l for l in result.stdout.splitlines() if l.startswith('RESULT'))
    _, first_eq, first_qr, second_eq, second_qr, value = line.split()
    assert first_eq == second_eq, 'second run must not duplicate equipment'
    assert first_qr == second_qr, 'second run must not duplicate QR codes'
    parts = value.split(':')
    assert len(parts) == 3 and len(parts[2]) == 12, f'imported code is not unified: {value}'


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q', '--no-header']))
