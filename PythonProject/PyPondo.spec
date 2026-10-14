# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

project_dir = os.path.abspath(SPECPATH)
online_build = os.getenv('PYPONDO_BUILD_ONLINE', '').strip().lower() in ('1', 'true', 'yes')
entry_script = 'desktop_online_app.py' if online_build else 'desktop_app.py'
executable_name = 'PyPondoOnline' if online_build else 'PyPondo'
datas = [('templates', 'templates'), ('assets', 'assets')]
server_host_file = os.path.join(project_dir, 'server_host.txt')
if os.path.isfile(server_host_file):
    datas.append((server_host_file, '.'))
if not online_build:
    main_database = os.getenv('PYPONDO_MAIN_DB_SEED', '').strip() or os.path.join(project_dir, 'pccafe.db')
    community_database = os.getenv('PYPONDO_COMMUNITY_DB_SEED', '').strip()
    if not community_database:
        community_candidates = (
            os.path.join(project_dir, 'community_equipment.db'),
            os.path.join(project_dir, 'instance', 'community_equipment.db'),
        )
        community_database = next((path for path in community_candidates if os.path.isfile(path)), '')
    if main_database and not os.path.isabs(main_database):
        main_database = os.path.join(project_dir, main_database)
    if community_database and not os.path.isabs(community_database):
        community_database = os.path.join(project_dir, community_database)
    if os.path.isfile(main_database):
        datas.append((main_database, os.path.join('database-seed', 'main')))
    if os.path.isfile(community_database):
        datas.append((community_database, os.path.join('database-seed', 'community')))
binaries = []
# qrcode is imported lazily inside the QR request handlers, and qrcode's own PNG
# image factory imports PIL lazily too. PyInstaller does not follow either hop
# reliably, so collect both packages up front or the packaged exe 500s on the
# equipment/PC label endpoints.
hiddenimports = ['profile_routes', 'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont']
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('qrcode')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PIL')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    [entry_script],
    pathex=[project_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=executable_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/pypondo.ico'],
)
