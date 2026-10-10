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
    main_database = os.path.join(project_dir, 'pccafe.db')
    community_database = r'D:\Users\jush\Downloads\sample.db'
    if os.path.isfile(main_database):
        datas.append((main_database, 'database-seed'))
    if os.path.isfile(community_database):
        datas.append((community_database, 'database-seed'))
binaries = []
hiddenimports = ['profile_routes']
tmp_ret = collect_all('webview')
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
