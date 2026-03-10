#!/usr/bin/env python3
"""
PyPondo Mobile Client - Android App
A mobile client for the PyPondo PC Cafe management system.
"""

import os
import sys
import json
import threading
import time
from urllib import request as http_request
from urllib import error as http_error
from urllib import parse as http_parse

# Kivy imports for Android app
try:
    import kivy
    kivy.require('2.0.0')

    from kivy.app import App
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.label import Label
    from kivy.uix.button import Button
    from kivy.uix.textinput import TextInput
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.popup import Popup
    from kivy.uix.screenmanager import ScreenManager, Screen
    from kivy.core.window import Window
    from kivy.clock import Clock
    from kivy.properties import StringProperty, NumericProperty
    from kivy.metrics import dp

    KIVY_AVAILABLE = True
except ImportError:
    KIVY_AVAILABLE = False
    print("Kivy not available. This is a desktop-only version.")

# Constants
DEFAULT_SERVER_HOST = "192.168.1.100"
DEFAULT_SERVER_PORT = 5000
APP_TITLE = "PyPondo Mobile"

class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(10))

        self.layout.add_widget(Label(text='PyPondo Mobile Client', font_size=dp(24), size_hint_y=None, height=dp(50)))

        # Server connection
        server_layout = GridLayout(cols=2, size_hint_y=None, height=dp(60), spacing=dp(10))
        server_layout.add_widget(Label(text='Server IP:'))
        self.server_input = TextInput(text=DEFAULT_SERVER_HOST, multiline=False)
        server_layout.add_widget(self.server_input)
        server_layout.add_widget(Label(text='Port:'))
        self.port_input = TextInput(text=str(DEFAULT_SERVER_PORT), multiline=False)
        server_layout.add_widget(self.port_input)
        self.layout.add_widget(server_layout)

        # Login credentials
        login_layout = GridLayout(cols=2, size_hint_y=None, height=dp(60), spacing=dp(10))
        login_layout.add_widget(Label(text='Username:'))
        self.username_input = TextInput(multiline=False)
        login_layout.add_widget(self.username_input)
        login_layout.add_widget(Label(text='Password:'))
        self.password_input = TextInput(password=True, multiline=False)
        login_layout.add_widget(self.password_input)
        self.layout.add_widget(login_layout)

        # Buttons
        button_layout = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        self.login_button = Button(text='Login', on_press=self.do_login)
        button_layout.add_widget(self.login_button)
        self.connect_button = Button(text='Test Connection', on_press=self.test_connection)
        button_layout.add_widget(self.connect_button)
        self.layout.add_widget(button_layout)

        self.status_label = Label(text='', size_hint_y=None, height=dp(30), color=(1, 0, 0, 1))
        self.layout.add_widget(self.status_label)

        self.add_widget(self.layout)

    def test_connection(self, instance):
        server = self.server_input.text.strip()
        port = self.port_input.text.strip()
        try:
            port_int = int(port)
            base_url = f"http://{server}:{port_int}"
            response = http_request.urlopen(f"{base_url}/api/server-info", timeout=5)
            if response.status == 200:
                self.status_label.text = "Connection successful!"
                self.status_label.color = (0, 1, 0, 1)
            else:
                self.status_label.text = f"Server responded with status {response.status}"
                self.status_label.color = (1, 0.5, 0, 1)
        except Exception as e:
            self.status_label.text = f"Connection failed: {str(e)}"
            self.status_label.color = (1, 0, 0, 1)

    def do_login(self, instance):
        username = self.username_input.text.strip()
        password = self.password_input.text.strip()
        server = self.server_input.text.strip()
        port = self.port_input.text.strip()

        if not username or not password:
            self.status_label.text = "Please enter username and password"
            self.status_label.color = (1, 0, 0, 1)
            return

        try:
            port_int = int(port)
        except:
            self.status_label.text = "Invalid port number"
            self.status_label.color = (1, 0, 0, 1)
            return

        self.login_button.disabled = True
        self.status_label.text = "Logging in..."
        self.status_label.color = (0, 0, 1, 1)

        # Perform login in background thread
        threading.Thread(target=self._perform_login, args=(username, password, server, port_int), daemon=True).start()

    def _perform_login(self, username, password, server, port):
        try:
            base_url = f"http://{server}:{port}"
            login_data = {"username": username, "password": password}
            data = http_parse.urlencode(login_data).encode('utf-8')

            req = http_request.Request(f"{base_url}/api/mobile/login", data=data, method='POST')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')

            with http_request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                
                if result.get("ok"):
                    Clock.schedule_once(lambda dt: self._login_success(
                        server, port, result["username"], result["user_id"], result["balance"]
                    ), 0)
                else:
                    Clock.schedule_once(lambda dt: self._login_failed(result.get("error", "Login failed")), 0)

        except Exception as e:
            Clock.schedule_once(lambda dt: self._login_failed(f"Login failed: {str(e)}"), 0)

    def _login_success(self, server, port, username, user_id, balance):
        self.status_label.text = "Login successful!"
        self.status_label.color = (0, 1, 0, 1)
        self.login_button.disabled = False

        # Switch to main screen
        app = App.get_running_app()
        app.server_host = server
        app.server_port = port
        app.username = username
        app.user_id = user_id
        app.balance = balance
        app.root.current = 'main'

    def _login_failed(self, message):
        self.status_label.text = message
        self.status_label.color = (1, 0, 0, 1)
        self.login_button.disabled = False


class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical')

        # Header
        self.header = Label(text='PyPondo Mobile - Welcome!', size_hint_y=None, height=dp(50), font_size=dp(18))
        self.layout.add_widget(self.header)

        # Balance display
        self.balance_label = Label(text='Balance: Loading...', size_hint_y=None, height=dp(40))
        self.layout.add_widget(self.balance_label)

        # Menu buttons
        button_layout = GridLayout(cols=2, spacing=dp(10), padding=dp(10))

        self.bookings_button = Button(text='My Bookings', on_press=self.show_bookings)
        button_layout.add_widget(self.bookings_button)

        self.topup_button = Button(text='Top Up Balance', on_press=self.show_topup)
        button_layout.add_widget(self.topup_button)

        self.logout_button = Button(text='Logout', on_press=self.do_logout)
        button_layout.add_widget(self.logout_button)

        self.refresh_button = Button(text='Refresh', on_press=self.refresh_data)
        button_layout.add_widget(self.refresh_button)

        self.layout.add_widget(button_layout)

        # Status
        self.status_label = Label(text='', size_hint_y=None, height=dp(30))
        self.layout.add_widget(self.status_label)

        self.add_widget(self.layout)

        # Start data refresh
        Clock.schedule_once(lambda dt: self.refresh_data(None), 1)

    def refresh_data(self, instance):
        app = App.get_running_app()
        if hasattr(app, 'username') and app.username:
            self.header.text = f'PyPondo Mobile - {app.username}'
            threading.Thread(target=self._fetch_balance, daemon=True).start()

    def _fetch_balance(self):
        app = App.get_running_app()
        try:
            # Use balance from login for now (in real app, fetch updated balance)
            balance = getattr(app, 'balance', 0.0)
            Clock.schedule_once(lambda dt: self._update_balance(f"Balance: PHP {balance:.2f}"), 0)
        except Exception as e:
            Clock.schedule_once(lambda dt: self._update_balance(f"Error loading balance: {str(e)}"), 0)

    def _update_balance(self, text):
        self.balance_label.text = text

    def show_bookings(self, instance):
        # Switch to bookings screen
        app = App.get_running_app()
        if not hasattr(app, 'bookings_screen'):
            app.bookings_screen = BookingsScreen(name='bookings')
            app.root.add_widget(app.bookings_screen)
        app.root.current = 'bookings'
        app.bookings_screen.refresh_bookings()

    def show_topup(self, instance):
        # TODO: Implement topup view
        self.status_label.text = "Top-up feature coming soon!"

    def do_logout(self, instance):
        app = App.get_running_app()
        app.root.current = 'login'
        self.status_label.text = ""


class BookingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical')

        # Header
        header_layout = BoxLayout(size_hint_y=None, height=dp(50))
        back_button = Button(text='← Back', size_hint_x=None, width=dp(80), on_press=self.go_back)
        self.header = Label(text='My Bookings', font_size=dp(18))
        header_layout.add_widget(back_button)
        header_layout.add_widget(self.header)
        self.layout.add_widget(header_layout)

        # Bookings list
        self.scroll_view = ScrollView()
        self.bookings_layout = BoxLayout(orientation='vertical', size_hint_y=None)
        self.bookings_layout.bind(minimum_height=self.bookings_layout.setter('height'))
        self.scroll_view.add_widget(self.bookings_layout)
        self.layout.add_widget(self.scroll_view)

        # New booking section
        new_booking_layout = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(200), padding=dp(10))
        new_booking_layout.add_widget(Label(text='Make New Booking', font_size=dp(16), size_hint_y=None, height=dp(30)))

        # PC selection
        pc_layout = BoxLayout(size_hint_y=None, height=dp(40))
        pc_layout.add_widget(Label(text='PC:', size_hint_x=None, width=dp(50)))
        self.pc_spinner = Spinner(text='Loading PCs...', values=[])
        pc_layout.add_widget(self.pc_spinner)
        new_booking_layout.add_widget(pc_layout)

        # Date and time
        datetime_layout = GridLayout(cols=2, size_hint_y=None, height=dp(80), spacing=dp(10))
        datetime_layout.add_widget(Label(text='Date:'))
        self.date_input = TextInput(hint_text='YYYY-MM-DD', multiline=False)
        datetime_layout.add_widget(self.date_input)
        datetime_layout.add_widget(Label(text='Time:'))
        self.time_input = TextInput(hint_text='HH:MM', multiline=False)
        datetime_layout.add_widget(self.time_input)
        new_booking_layout.add_widget(datetime_layout)

        # Book button
        self.book_button = Button(text='Book Now', size_hint_y=None, height=dp(40), on_press=self.make_booking)
        new_booking_layout.add_widget(self.book_button)

        self.layout.add_widget(new_booking_layout)

        # Status
        self.status_label = Label(text='', size_hint_y=None, height=dp(30), color=(1, 0, 0, 1))
        self.layout.add_widget(self.status_label)

        self.add_widget(self.layout)

    def go_back(self, instance):
        app = App.get_running_app()
        app.root.current = 'main'

    def refresh_bookings(self):
        # Clear existing bookings
        self.bookings_layout.clear_widgets()

        app = App.get_running_app()
        if not hasattr(app, 'user_id'):
            return

        # Fetch bookings and PCs from server
        threading.Thread(target=self._fetch_bookings, daemon=True).start()
        threading.Thread(target=self._fetch_pcs, daemon=True).start()

    def _fetch_bookings(self):
        app = App.get_running_app()
        try:
            base_url = f"http://{app.server_host}:{app.server_port}"
            url = f"{base_url}/api/mobile/bookings?user_id={app.user_id}"
            
            with http_request.urlopen(url, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                
                if result.get("ok"):
                    bookings = result.get("bookings", [])
                    Clock.schedule_once(lambda dt: self._update_bookings(bookings), 0)
                else:
                    Clock.schedule_once(lambda dt: self._update_bookings([]), 0)
        except Exception as e:
            print(f"Error fetching bookings: {e}")
            Clock.schedule_once(lambda dt: self._update_bookings([]), 0)

    def _update_bookings(self, bookings):
        # Clear existing bookings
        self.bookings_layout.clear_widgets()

        if not bookings:
            self.bookings_layout.add_widget(Label(text="No bookings found", size_hint_y=None, height=dp(40)))
            return

        for booking in bookings:
            booking_card = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(80), padding=dp(10))
            booking_card.add_widget(Label(text=f"PC: {booking['pc_name']} | {booking['date']} {booking['time']}", font_size=dp(14)))
            status_color = (0, 1, 0, 1) if booking['status'] == 'confirmed' else (1, 0.5, 0, 1)
            booking_card.add_widget(Label(text=f"Status: {booking['status']}", font_size=dp(12), color=status_color))
            self.bookings_layout.add_widget(booking_card)

    def _fetch_pcs(self):
        app = App.get_running_app()
        try:
            base_url = f"http://{app.server_host}:{app.server_port}"
            url = f"{base_url}/api/mobile/pcs"
            
            with http_request.urlopen(url, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                
                if result.get("ok"):
                    pcs = result.get("pcs", [])
                    pc_names = [pc['name'] for pc in pcs if not pc['is_occupied']]
                    Clock.schedule_once(lambda dt: self._update_pc_spinner(pc_names), 0)
                else:
                    Clock.schedule_once(lambda dt: self._update_pc_spinner([]), 0)
        except Exception as e:
            print(f"Error fetching PCs: {e}")
            Clock.schedule_once(lambda dt: self._update_pc_spinner([]), 0)

    def _update_pc_spinner(self, pc_names):
        if pc_names:
            self.pc_spinner.values = pc_names
            self.pc_spinner.text = pc_names[0]
        else:
            self.pc_spinner.values = []
            self.pc_spinner.text = 'No PCs available'

    def make_booking(self, instance):
        pc = self.pc_spinner.text
        date = self.date_input.text
        time = self.time_input.text

        if pc == 'Select PC' or pc == 'No PCs available' or not date or not time:
            self.status_label.text = "Please fill all fields"
            return

        app = App.get_running_app()
        if not hasattr(app, 'user_id'):
            self.status_label.text = "Not logged in"
            return

        self.book_button.disabled = True
        self.status_label.text = f"Booking {pc} for {date} {time}..."
        self.status_label.color = (0, 0, 1, 1)

        # Send booking request to server
        threading.Thread(target=self._send_booking, args=(pc, date, time), daemon=True).start()

    def _send_booking(self, pc_name, date, time):
        app = App.get_running_app()
        try:
            base_url = f"http://{app.server_host}:{app.server_port}"
            
            # Find PC ID by name
            pc_id = None
            pcs_url = f"{base_url}/api/mobile/pcs"
            with http_request.urlopen(pcs_url, timeout=10) as response:
                pcs_result = json.loads(response.read().decode('utf-8'))
                if pcs_result.get("ok"):
                    for pc in pcs_result.get("pcs", []):
                        if pc['name'] == pc_name:
                            pc_id = pc['id']
                            break
            
            if not pc_id:
                Clock.schedule_once(lambda dt: self._booking_failed("PC not found"), 0)
                return

            # Send booking request
            booking_data = {
                "user_id": app.user_id,
                "pc_id": pc_id,
                "date": date,
                "time": time
            }
            
            data = http_parse.urlencode(booking_data).encode('utf-8')
            req = http_request.Request(f"{base_url}/api/mobile/book", data=data, method='POST')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')

            with http_request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                
                if result.get("ok"):
                    Clock.schedule_once(lambda dt: self._booking_success(), 0)
                else:
                    Clock.schedule_once(lambda dt: self._booking_failed(result.get("error", "Booking failed")), 0)

        except Exception as e:
            Clock.schedule_once(lambda dt: self._booking_failed(f"Booking failed: {str(e)}"), 0)

    def _booking_success(self):
        self.status_label.text = "Booking successful!"
        self.status_label.color = (0, 1, 0, 1)
        self.book_button.disabled = False
        self.refresh_bookings()

    def _booking_failed(self, message):
        self.status_label.text = message
        self.status_label.color = (1, 0, 0, 1)
        self.book_button.disabled = False


class PyPondoMobileApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.server_host = DEFAULT_SERVER_HOST
        self.server_port = DEFAULT_SERVER_PORT
        self.username = None
        self.user_id = None
        self.balance = 0.0

    def build(self):
        # Set window size for mobile-like experience on desktop
        Window.size = (400, 600)

        sm = ScreenManager()
        sm.add_widget(LoginScreen(name='login'))
        sm.add_widget(MainScreen(name='main'))
        return sm

    def on_start(self):
        # Load saved server settings if available
        try:
            if os.path.exists('mobile_config.json'):
                with open('mobile_config.json', 'r') as f:
                    config = json.load(f)
                    self.server_host = config.get('server_host', DEFAULT_SERVER_HOST)
                    self.server_port = config.get('server_port', DEFAULT_SERVER_PORT)
        except:
            pass


def main():
    if not KIVY_AVAILABLE:
        print("Kivy is required for the mobile app.")
        print("Install with: pip install kivy")
        return

    print("Starting PyPondo Mobile Client...")
    PyPondoMobileApp().run()


if __name__ == '__main__':
    main()