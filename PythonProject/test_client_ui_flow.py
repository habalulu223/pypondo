import importlib.util
import os
import tempfile
from pathlib import Path


def load_server_module(temp_db_path):
    os.environ["PYPONDO_DB_PATH"] = temp_db_path
    os.environ["PYPONDO_DISABLE_BILLING"] = "1"

    module_path = Path(__file__).with_name("app.py")
    spec = importlib.util.spec_from_file_location("pypondo_ui_app", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_zero_balance_client_bookings_prompts_for_top_up():
    with tempfile.TemporaryDirectory(prefix="pypondo-ui-") as temp_dir:
        temp_db_path = str(Path(temp_dir) / "ui.db")
        module = load_server_module(temp_db_path)
        app = module.app
        db = module.db
        User = module.User

        try:
            with app.app_context():
                db.create_all()
                module.ensure_pc_lan_ip_column()
                module.ensure_booking_date_column()
                module.ensure_session_last_charged_at_column()
                module.ensure_core_seed_data()

                user = User(username="ui-user", pondo=0.0)
                user.set_password("ui-pass")
                db.session.add(user)
                db.session.commit()

            client = app.test_client()
            login_response = client.post(
                "/login",
                data={"username": "ui-user", "password": "ui-pass"},
                follow_redirects=False,
            )
            assert login_response.status_code in (302, 303)

            bookings_response = client.get("/client/bookings")
            assert bookings_response.status_code == 200

            html = bookings_response.get_data(as_text=True)
            assert "Add balance to unlock desktop access" in html
            assert "Top Up to Unlock Desktop" in html
            assert "insuficient balance please top up" in html
        finally:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()


def test_sub_one_balance_blocks_desktop_access():
    with tempfile.TemporaryDirectory(prefix="pypondo-ui-") as temp_dir:
        temp_db_path = str(Path(temp_dir) / "ui.db")
        module = load_server_module(temp_db_path)
        app = module.app
        db = module.db
        User = module.User

        try:
            with app.app_context():
                db.create_all()
                module.ensure_pc_lan_ip_column()
                module.ensure_booking_date_column()
                module.ensure_session_last_charged_at_column()
                module.ensure_core_seed_data()

                user = User(username="ui-low-balance", pondo=0.5)
                user.set_password("ui-pass")
                db.session.add(user)
                db.session.commit()

            client = app.test_client()
            login_response = client.post(
                "/login",
                data={"username": "ui-low-balance", "password": "ui-pass"},
                follow_redirects=False,
            )
            assert login_response.status_code in (302, 303)

            desktop_response = client.get("/client", follow_redirects=False)
            assert desktop_response.status_code == 302
            assert desktop_response.headers["Location"].endswith("/client/bookings")
        finally:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()


if __name__ == "__main__":
    test_zero_balance_client_bookings_prompts_for_top_up()
    test_sub_one_balance_blocks_desktop_access()
    print("Verified zero and sub-1 balance flows hide desktop access and timer entry.")
