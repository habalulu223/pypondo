"""Smoke-test the auth database split and login routes against temp DB copies."""
import os
import shutil
import sys
import tempfile

PROJECT = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp(prefix='techpuls_auth_test_')

# Copy the real cafe db so the migration path is exercised on real data.
shutil.copy(os.path.join(PROJECT, 'pccafe.db'), os.path.join(tmp, 'pccafe.db'))
os.environ['PYPONDO_DB_PATH'] = os.path.join(tmp, 'pccafe.db')
os.environ['PYPONDO_COMMUNITY_DB_PATH'] = os.path.join(tmp, 'community_equipment.db')
os.environ['PYPONDO_AUTH_DB_PATH'] = os.path.join(tmp, 'auth.db')
os.environ['PYPONDO_SECRET_KEY'] = 'test-secret-key'

sys.path.insert(0, PROJECT)
import app as app_module  # noqa: E402

failures = []


def check(name, condition, detail=''):
    status = 'PASS' if condition else 'FAIL'
    print(f'[{status}] {name}' + (f' - {detail}' if detail and not condition else ''))
    if not condition:
        failures.append(name)


with app_module.app.app_context():
    app_module.initialize_database()

    # auth.db exists and every user got mirrored
    user_count = app_module.User.query.count()
    auth_count = app_module.AuthUser.query.count()
    auth_db_exists = os.path.exists(os.environ['PYPONDO_AUTH_DB_PATH'])
    check('auth.db created', auth_db_exists)
    check('users mirrored to auth.db', user_count > 0 and auth_count == user_count,
          f'{auth_count} auth rows vs {user_count} users')

    # password login works through auth.db
    user = app_module.authenticate_credentials('admin', 'admin123')
    check('admin password login via auth.db', user is not None)
    check('wrong password rejected', app_module.authenticate_credentials('admin', 'nope') is None)
    check('email/username lookup handles missing', app_module.authenticate_credentials('ghost', 'x') is None)

client = app_module.app.test_client()

# login page renders with the new theme
page = client.get('/login')
check('login page renders', page.status_code == 200)
check('theme include present', b'professional.css' in page.data)
check('Inter font loaded', b'family=Inter' in page.data)
check('old Orbitron font removed', b'Orbitron' not in page.data)
check('Google button hidden when unconfigured', b'Sign in with Google' not in page.data)

# form login against auth db
resp = client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False)
check('form login succeeds', resp.status_code == 302, str(resp.status_code))
page = client.get('/logout')
check('logout works', page.status_code in (301, 302))

# bad credentials flash an error
resp = client.post('/login', data={'username': 'admin', 'password': 'wrong'})
check('bad login shows error', b'Invalid credentials' in resp.data)

# google route not configured -> safe redirect to login
resp = client.get('/auth/google', follow_redirects=True)
check('google start redirects when unconfigured', b'not configured' in resp.data)

# callback without state is rejected
resp = client.get('/auth/google/callback', follow_redirects=True)
check('callback rejects missing state', b'could not be verified' in resp.data)

# registration writes to auth.db too
resp = client.post('/register', data={'username': 'smoketest_user', 'password': 'testpass123'},
                   follow_redirects=True)
with app_module.app.app_context():
    account = app_module.AuthUser.query.filter_by(username='smoketest_user').first()
    check('registration creates auth row', account is not None)
    check('registered user can log in', app_module.authenticate_credentials('smoketest_user', 'testpass123') is not None)

print()
if failures:
    print(f'{len(failures)} FAILURE(S): {failures}')
    sys.exit(1)
print('All smoke tests passed.')
