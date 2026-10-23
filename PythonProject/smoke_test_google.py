"""Verify Google button + OAuth redirect when GOOGLE_CLIENT_ID/SECRET are set."""
import os
import sys
import tempfile

PROJECT = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp(prefix='techpuls_google_test_')
os.environ['PYPONDO_DB_PATH'] = os.path.join(tmp, 'pccafe.db')
os.environ['PYPONDO_COMMUNITY_DB_PATH'] = os.path.join(tmp, 'community_equipment.db')
os.environ['PYPONDO_AUTH_DB_PATH'] = os.path.join(tmp, 'auth.db')
os.environ['PYPONDO_SECRET_KEY'] = 'test-secret-key'
os.environ['GOOGLE_CLIENT_ID'] = 'test-id.apps.googleusercontent.com'
os.environ['GOOGLE_CLIENT_SECRET'] = 'test-secret'

sys.path.insert(0, PROJECT)
import app as app_module

with app_module.app.app_context():
    app_module.initialize_database()

client = app_module.app.test_client()
page = client.get('/login')
assert b'Sign in with Google' in page.data, 'google button missing'
resp = client.get('/auth/google')
assert resp.status_code == 302, resp.status_code
location = resp.headers['Location']
assert 'accounts.google.com' in location, location
assert 'client_id=test-id' in location, location
assert 'redirect_uri' in location, location
# state cookie issued for CSRF protection
assert 'session=' in resp.headers.get('Set-Cookie', ''), 'state session missing'
print('Google OAuth wiring OK')
