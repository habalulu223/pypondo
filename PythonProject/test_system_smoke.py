#!/usr/bin/env python3
"""
Focused smoke test for the PyPondo server and mobile API flows.
Runs against a temporary SQLite database so the real cafe data is untouched.
"""

import importlib.util
import io
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

PASS_LABEL = "[PASS]"
FAIL_LABEL = "[FAIL]"


def load_server_module(temp_db_path):
    os.environ["PYPONDO_DB_PATH"] = temp_db_path
    os.environ["PYPONDO_DISABLE_BILLING"] = "1"

    module_path = Path(__file__).with_name("app.py")
    spec = importlib.util.spec_from_file_location("pypondo_smoke_app", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(condition, description):
    if not condition:
        raise AssertionError(description)
    print(f"{PASS_LABEL} {description}")


def main():
    with tempfile.TemporaryDirectory(prefix="pypondo-smoke-") as temp_dir:
        temp_db_path = str(Path(temp_dir) / "smoke.db")
        module = load_server_module(temp_db_path)

        app = module.app
        db = module.db
        User = module.User
        PC = module.PC
        Session = module.Session
        LanCommand = module.LanCommand

        with app.app_context():
            db.create_all()
            module.ensure_pc_lan_ip_column()
            module.ensure_booking_date_column()
            module.ensure_session_last_charged_at_column()
            module.ensure_core_seed_data()

            user = User(username="smoke-user", pondo=0.0)
            user.set_password("smoke-pass")
            db.session.add(user)
            db.session.commit()
            user_id = user.id

            active_pc = PC.query.order_by(PC.id.asc()).first()
            active_pc_id = active_pc.id
            active_start = datetime.now() - timedelta(minutes=25)
            active_session = Session(
                user_id=user_id,
                pc_id=active_pc_id,
                start_time=active_start,
                last_charged_at=active_start,
                cost=0.0,
            )
            active_pc.is_occupied = True
            db.session.add(active_session)
            db.session.commit()

        client = app.test_client()
        try:
            server_info = client.get("/api/server-info")
            check(server_info.status_code == 200, "server info endpoint responds")
            server_payload = server_info.get_json()
            check(server_payload.get("ok") is True, "server info payload is marked ok")
            check(bool(server_payload.get("app_version")), "server info includes app version")
            check(bool(server_payload.get("server_address")), "server info exposes a preferred server address")

            pairing_response = client.get("/api/mobile/pairing")
            check(pairing_response.status_code == 200, "mobile pairing endpoint responds")
            pairing_payload = pairing_response.get_json()
            check(pairing_payload.get("pairing_mode") == "lan_qr", "mobile pairing endpoint marks the LAN QR mode")
            check(bool(pairing_payload.get("pairing_url")), "mobile pairing endpoint exposes a QR pairing URL")

            login_response = client.post(
                "/api/mobile/login",
                data={"username": "smoke-user", "password": "smoke-pass"},
            )
            check(login_response.status_code == 200, "mobile login succeeds")
            login_payload = login_response.get_json()
            check(login_payload.get("user_id") == user_id, "mobile login returns the correct user id")

            pcs_response = client.get("/api/mobile/pcs")
            check(pcs_response.status_code == 200, "mobile PC list responds")
            pcs_payload = pcs_response.get_json()
            check(len(pcs_payload.get("pcs", [])) >= 5, "mobile PC list exposes seeded PCs")
            first_pc = pcs_payload["pcs"][0]

            booking_dt = datetime.now() + timedelta(days=1)
            booking_response = client.post(
                "/api/mobile/book",
                data={
                    "user_id": user_id,
                    "pc_id": first_pc["id"],
                    "date": booking_dt.strftime("%Y-%m-%d"),
                    "time": booking_dt.strftime("%H:%M"),
                },
            )
            check(booking_response.status_code == 201, "mobile booking creation succeeds")
            booking_payload = booking_response.get_json()
            check(booking_payload.get("ok") is True, "mobile booking payload is marked ok")

            bookings_response = client.get(f"/api/mobile/bookings?user_id={user_id}")
            check(bookings_response.status_code == 200, "mobile bookings list responds")
            bookings_payload = bookings_response.get_json()
            check(len(bookings_payload.get("bookings", [])) == 1, "mobile bookings list returns the new booking")

            topup_response = client.post(
                "/api/mobile/topup",
                json={"user_id": user_id, "amount": 150},
            )
            check(topup_response.status_code == 201, "mobile top-up request succeeds")
            topup_payload = topup_response.get_json()
            check(bool(topup_payload.get("external_id")), "mobile top-up returns a payment reference")

            updates_response = client.get("/api/mobile/updates")
            check(updates_response.status_code == 200, "mobile updates feed responds")
            updates_payload = updates_response.get_json()
            check(len(updates_payload.get("updates", [])) >= 1, "mobile updates feed returns items")

            chat_response = client.post(
                "/api/mobile/ai-chat",
                data={"user_id": user_id, "message": "What is my balance?"},
            )
            check(chat_response.status_code == 200, "mobile assistant endpoint responds")
            chat_payload = chat_response.get_json()
            check("balance" in chat_payload.get("response", "").lower(), "mobile assistant returns a balance-aware reply")

            admin_login = client.post(
                "/login",
                data={"username": "admin", "password": "admin123"},
                follow_redirects=False,
            )
            check(admin_login.status_code in (302, 303), "admin web login succeeds")

            module.send_lan_command = lambda pc_name, command, payload=None: (
                True,
                f"stubbed {command} for {pc_name}",
            )

            admin_index = client.get("/")
            admin_html = admin_index.get_data(as_text=True)
            check(admin_index.status_code == 200, "admin dashboard responds")
            check("Logged In:" in admin_html, "admin dashboard shows the active session user label")
            check("Current Charge:" in admin_html, "admin dashboard shows the live session charge label")
            check("smoke-user" in admin_html, "admin dashboard includes the session username")
            check("Mobile LAN Pairing" in admin_html, "admin dashboard shows the mobile LAN pairing section")

            connect_response = client.post(
                "/admin/request_connect",
                data={
                    "pc_id": active_pc_id,
                    "connect_ip": "192.168.18.123",
                    "connect_port": "5001",
                },
                follow_redirects=False,
            )
            check(connect_response.status_code in (302, 303), "admin request-connect action succeeds")
            with app.app_context():
                refreshed_pc = db.session.get(PC, active_pc_id)
                check(refreshed_pc.lan_ip == "192.168.18.123", "admin request-connect saves the PC LAN IP")
                check(refreshed_pc.lan_port == 5001, "admin request-connect saves the PC LAN port")

                pending_cmd = LanCommand(
                    pc_name=refreshed_pc.name,
                    command="lock",
                    payload_json="{}",
                    status="queued",
                )
                db.session.add(pending_cmd)
                db.session.commit()
                pending_cmd_id = pending_cmd.id

            clear_response = client.post(
                f"/admin/clear_pc_commands/{active_pc_id}",
                follow_redirects=False,
            )
            check(clear_response.status_code in (302, 303), "admin clear-pending-commands action succeeds")
            with app.app_context():
                cancelled_cmd = db.session.get(LanCommand, pending_cmd_id)
                check(cancelled_cmd.status == "cancelled", "admin clear-pending-commands cancels queued LAN commands")

            android_download = client.get("/admin/download_android_app")
            check(android_download.status_code == 200, "admin Android download endpoint responds")
            check(
                "PyPondo-Android-build-kit.zip" in android_download.headers.get("Content-Disposition", ""),
                "admin Android download falls back to the build kit when no APK exists",
            )
            check(android_download.data[:2] == b"PK", "admin Android build kit download is a zip file")
            with zipfile.ZipFile(io.BytesIO(android_download.data), "r") as archive:
                archive_names = set(archive.namelist())
            check(
                "PyPondo-Android-build-kit/build_android.ps1" in archive_names,
                "admin Android build kit includes the PowerShell launcher",
            )
        finally:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()

    print(f"\n{PASS_LABEL} Smoke test completed successfully.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"\n{FAIL_LABEL} Smoke test failed: {exc}")
        sys.exit(1)
