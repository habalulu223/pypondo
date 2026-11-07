"""Smoke-test that every themed page renders with the calm Techpuls UI assets."""
import os
import shutil
import sys
import tempfile

PROJECT = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp(prefix='techpuls_ui_test_')

shutil.copy(os.path.join(PROJECT, 'pccafe.db'), os.path.join(tmp, 'pccafe.db'))
os.environ['PYPONDO_DB_PATH'] = os.path.join(tmp, 'pccafe.db')
os.environ['PYPONDO_COMMUNITY_DB_PATH'] = os.path.join(tmp, 'community_equipment.db')
os.environ['PYPONDO_AUTH_DB_PATH'] = os.path.join(tmp, 'auth.db')
os.environ['PYPONDO_SECRET_KEY'] = 'test-secret-key'

sys.path.insert(0, PROJECT)
import app as app_module  # noqa: E402

with app_module.app.app_context():
    app_module.initialize_database()

failures = []


def check(name, condition, detail=''):
    status = 'PASS' if condition else 'FAIL'
    print(f'[{status}] {name}' + (f' - {detail}' if detail and not condition else ''))
    if not condition:
        failures.append(name)


client = app_module.app.test_client()

# Public pages
page = client.get('/login')
check('login renders', page.status_code == 200)
check('login uses theme + Inter', b'professional.css' in page.data and b'family=Inter' in page.data)
page = client.get('/register')
check('register renders', page.status_code == 200)
check('register uses theme + Inter', b'professional.css' in page.data and b'family=Inter' in page.data)

page = client.get('/definitely-not-a-page')
check('error page renders themed', page.status_code == 404 and b'css/error.css' in page.data and b'#16090d' not in page.data)

# Authenticated pages (admin seed account)
client.post('/login', data={'username': 'admin', 'password': 'admin123'})

THEMED_PAGES = {
    '/profile': 'profile',
    '/dean/pcs': 'dean',
    '/mobile/pairing': 'mobile pairing',
    '/dashboard': 'role dashboard',
    '/equipment': 'equipment',
    '/bookings': 'bookings',
    '/logs': 'logs',
    '/admin/payments': 'payments',
    '/pondo': 'pondo',
}
for path, label in THEMED_PAGES.items():
    page = client.get(path)
    ok_status = page.status_code == 200
    check(f'{label} renders ({path})', ok_status, f'status {page.status_code}')
    if ok_status:
        check(f'{label} loads theme', b'professional.css' in page.data)
        check(f'{label} loads Inter', b'family=Inter' in page.data)

# /dashboard is role-gated; an account without a staff or borrowing role is redirected.
page = client.get('/dashboard')
check('role dashboard responds', page.status_code in (200, 302), f'status {page.status_code}')
if page.status_code == 200:
    check('role dashboard loads theme', b'professional.css' in page.data)

print()
if failures:
    print(f'{len(failures)} FAILURE(S): {failures}')
    sys.exit(1)
print('All UI smoke tests passed.')
