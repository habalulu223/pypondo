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
    from kivy.uix.spinner import Spinner
    from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelHeader, TabbedPanelItem
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

        # Tabbed panel for main content
        self.tab_panel = TabbedPanel(do_default_tab=False, tab_height=dp(40))

        # Bookings tab
        bookings_tab = TabbedPanelHeader(text='Bookings')
        bookings_content = BoxLayout(orientation='vertical')
        
        # Bookings list
        self.bookings_scroll = ScrollView()
        self.bookings_layout = BoxLayout(orientation='vertical', size_hint_y=None)
        self.bookings_layout.bind(minimum_height=self.bookings_layout.setter('height'))
        self.bookings_scroll.add_widget(self.bookings_layout)
        bookings_content.add_widget(self.bookings_scroll)

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

        bookings_content.add_widget(new_booking_layout)
        bookings_tab.content = bookings_content
        self.tab_panel.add_widget(bookings_tab)

        # Top Up tab
        topup_tab = TabbedPanelHeader(text='Top Up')
        self.topup_tab = topup_tab
        topup_content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        topup_content.add_widget(Label(text='Create Top-Up Request', size_hint_y=None, height=dp(30), font_size=dp(16)))

        self.topup_amount_input = TextInput(hint_text='Amount (PHP)', multiline=False, input_filter='float', size_hint_y=None, height=dp(45))
        topup_content.add_widget(self.topup_amount_input)

        quick_topup_row = GridLayout(cols=4, size_hint_y=None, height=dp(45), spacing=dp(8))
        for quick_amount in (100, 200, 500, 1000):
            quick_btn = Button(text=f'PHP {quick_amount}', on_press=lambda inst, amt=quick_amount: self.set_topup_amount(amt))
            quick_topup_row.add_widget(quick_btn)
        topup_content.add_widget(quick_topup_row)

        self.topup_submit_button = Button(text='Submit Top-Up Request', size_hint_y=None, height=dp(45), on_press=self.submit_topup_request)
        topup_content.add_widget(self.topup_submit_button)
        topup_content.add_widget(Label(text='Top-up requests are saved for admin confirmation.', size_hint_y=None, height=dp(28)))

        topup_tab.content = topup_content
        self.tab_panel.add_widget(topup_tab)

        # Updates tab
        updates_tab = TabbedPanelHeader(text='Updates')
        updates_content = BoxLayout(orientation='vertical')
        
        # Updates list
        self.updates_scroll = ScrollView()
        self.updates_layout = BoxLayout(orientation='vertical', size_hint_y=None)
        self.updates_layout.bind(minimum_height=self.updates_layout.setter('height'))
        self.updates_scroll.add_widget(self.updates_layout)
        updates_content.add_widget(self.updates_scroll)
        
        updates_tab.content = updates_content
        self.tab_panel.add_widget(updates_tab)

        # AI Assistant tab
        ai_tab = TabbedPanelHeader(text='AI Assistant')
        ai_content = BoxLayout(orientation='vertical')
        
        # Chat history
        self.chat_scroll = ScrollView()
        self.chat_layout = BoxLayout(orientation='vertical', size_hint_y=None)
        self.chat_layout.bind(minimum_height=self.chat_layout.setter('height'))
        self.chat_scroll.add_widget(self.chat_layout)
        ai_content.add_widget(self.chat_scroll)
        
        # Message input area
        input_layout = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(10), padding=dp(10))
        self.message_input = TextInput(hint_text='Ask me anything about PyPondo...', multiline=False)
        input_layout.add_widget(self.message_input)
        self.send_button = Button(text='Send', size_hint_x=None, width=dp(80), on_press=self.send_message)
        input_layout.add_widget(self.send_button)
        ai_content.add_widget(input_layout)
        
        ai_tab.content = ai_content
        self.tab_panel.add_widget(ai_tab)

        self.layout.add_widget(self.tab_panel)

        # Bottom buttons
        button_layout = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10), padding=dp(10))
        self.topup_button = Button(text='Top Up', on_press=self.show_topup)
        button_layout.add_widget(self.topup_button)
        self.logout_button = Button(text='Logout', on_press=self.do_logout)
        button_layout.add_widget(self.logout_button)
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
            threading.Thread(target=self._fetch_bookings, daemon=True).start()
            threading.Thread(target=self._fetch_pcs, daemon=True).start()
            threading.Thread(target=self._fetch_updates, daemon=True).start()

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

    def _fetch_updates(self):
        app = App.get_running_app()
        try:
            base_url = f"http://{app.server_host}:{app.server_port}"
            url = f"{base_url}/api/mobile/updates"
            
            with http_request.urlopen(url, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                
                if result.get("ok"):
                    updates = result.get("updates", [])
                    Clock.schedule_once(lambda dt: self._update_updates(updates), 0)
                else:
                    Clock.schedule_once(lambda dt: self._update_updates([]), 0)
        except Exception as e:
            print(f"Error fetching updates: {e}")
            Clock.schedule_once(lambda dt: self._update_updates([]), 0)

    def _update_updates(self, updates):
        # Clear existing updates
        self.updates_layout.clear_widgets()

        if not updates:
            self.updates_layout.add_widget(Label(text="No updates available", size_hint_y=None, height=dp(40)))
            return

        for update in updates:
            # Determine color based on update type
            # major: orange, feature: green, bugfix: red, minor: blue
            type_color = {
                'major': (1, 0.5, 0, 1),      # Orange for major updates
                'feature': (0, 0.8, 0, 1),    # Green for features
                'bugfix': (0.8, 0, 0, 1),     # Red for bug fixes
                'minor': (0, 0.5, 1, 1)       # Blue for minor updates
            }.get(update.get('update_type', 'minor'), (0.5, 0.5, 0.5, 1))
            
            update_card = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(120), padding=dp(10))
            
            # Header with version and type
            header_text = f"v{update['version']} - {update['update_type'].upper()}"
            header_label = Label(text=header_text, font_size=dp(14), color=type_color, bold=True, halign='left')
            update_card.add_widget(header_label)
            
            # Title
            title_label = Label(text=update['title'], font_size=dp(16), bold=True, halign='left', valign='top')
            title_label.text_size = (self.updates_layout.width - dp(20), None)
            title_label.bind(size=title_label.setter('text_size'))
            update_card.add_widget(title_label)
            
            # Description
            desc_label = Label(text=update['description'], font_size=dp(12), halign='left', valign='top')
            desc_label.text_size = (self.updates_layout.width - dp(20), None)
            desc_label.bind(size=desc_label.setter('text_size'))
            update_card.add_widget(desc_label)
            
            # Timestamp
            if update.get('timestamp'):
                timestamp_str = update['timestamp'].replace('T', ' ').split('.')[0] if 'T' in update['timestamp'] else update['timestamp']
                time_label = Label(text=timestamp_str, font_size=dp(10), color=(0.5, 0.5, 0.5, 1), halign='right')
                update_card.add_widget(time_label)
            
            self.updates_layout.add_widget(update_card)

    def send_message(self, instance):
        message = self.message_input.text.strip()
        if not message:
            return

        app = App.get_running_app()
        if not hasattr(app, 'user_id'):
            self._add_chat_message("AI", "Please login first to use the assistant.")
            return

        # Add user message to chat
        self._add_chat_message("You", message)
        self.message_input.text = ""
        self.send_button.disabled = True

        # Send message to AI
        threading.Thread(target=self._send_to_ai, args=(message,), daemon=True).start()

    def _send_to_ai(self, message):
        app = App.get_running_app()
        try:
            base_url = f"http://{app.server_host}:{app.server_port}"
            chat_data = {
                "message": message,
                "user_id": app.user_id
            }
            
            data = http_parse.urlencode(chat_data).encode('utf-8')
            req = http_request.Request(f"{base_url}/api/mobile/ai-chat", data=data, method='POST')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')

            with http_request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                
                if result.get("ok"):
                    ai_response = result.get("response", "Sorry, I couldn't understand that.")
                    Clock.schedule_once(lambda dt: self._add_chat_message("AI Assistant", ai_response), 0)
                else:
                    Clock.schedule_once(lambda dt: self._add_chat_message("AI", "Sorry, I'm having trouble responding right now."), 0)

        except Exception as e:
            Clock.schedule_once(lambda dt: self._add_chat_message("AI", f"Sorry, there was an error: {str(e)}"), 0)
        finally:
            Clock.schedule_once(lambda dt: self._enable_send_button(), 0)

    def _add_chat_message(self, sender, message):
        chat_card = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(80), padding=dp(10))
        
        # Sender label
        sender_color = (0, 0.8, 0, 1) if sender == "AI Assistant" else (0, 0.5, 1, 1)
        sender_label = Label(text=f"{sender}:", font_size=dp(12), color=sender_color, bold=True, halign='left', size_hint_y=None, height=dp(20))
        chat_card.add_widget(sender_label)
        
        # Message
        message_label = Label(text=message, font_size=dp(14), halign='left', valign='top')
        message_label.text_size = (self.chat_layout.width - dp(20), None)
        message_label.bind(size=message_label.setter('text_size'))
        chat_card.add_widget(message_label)
        
        self.chat_layout.add_widget(chat_card)
        # Scroll to bottom
        Clock.schedule_once(lambda dt: self.chat_scroll.scroll_to(self.chat_layout.children[-1]), 0.1)

    def _enable_send_button(self):
        self.send_button.disabled = False

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
        self.refresh_data(None)

    def _booking_failed(self, message):
        self.status_label.text = message
        self.status_label.color = (1, 0, 0, 1)
        self.book_button.disabled = False

    def show_topup(self, instance):
        self.tab_panel.switch_to(self.topup_tab)

    def set_topup_amount(self, amount):
        self.topup_amount_input.text = str(amount)

    def submit_topup_request(self, instance):
        raw_amount = self.topup_amount_input.text.strip()
        if not raw_amount:
            self.status_label.text = "Enter top-up amount"
            self.status_label.color = (1, 0, 0, 1)
            return

        self.topup_submit_button.disabled = True
        threading.Thread(target=self._submit_topup_request, args=(raw_amount,), daemon=True).start()

    def _submit_topup_request(self, raw_amount):
        app = App.get_running_app()
        try:
            amount = float(raw_amount)
            if amount <= 0:
                raise ValueError("Amount must be positive")

            payload = {
                "user_id": app.user_id,
                "amount": amount,
            }
            base_url = f"http://{app.server_host}:{app.server_port}"
            req = http_request.Request(
                f"{base_url}/api/mobile/topup",
                data=json.dumps(payload).encode('utf-8'),
                method='POST',
                headers={"Content-Type": "application/json"},
            )

            with http_request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))

            if not result.get("ok"):
                message = result.get("error", "Top-up request failed")
                Clock.schedule_once(lambda dt, msg=message: self._topup_failed(msg), 0)
                return

            message = result.get("message", "Top-up request submitted")
            Clock.schedule_once(lambda dt, msg=message: self._topup_success(msg), 0)
        except Exception as exc:
            Clock.schedule_once(lambda dt, msg=str(exc): self._topup_failed(f"Top-up failed: {msg}"), 0)

    def _topup_success(self, message):
        self.status_label.text = message
        self.status_label.color = (0, 1, 0, 1)
        self.topup_submit_button.disabled = False
        self.topup_amount_input.text = ""
        self.refresh_data(None)

    def _topup_failed(self, message):
        self.status_label.text = message
        self.status_label.color = (1, 0, 0, 1)
        self.topup_submit_button.disabled = False

    def do_logout(self, instance):
        app = App.get_running_app()
        app.root.current = 'login'
        self.status_label.text = ""


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