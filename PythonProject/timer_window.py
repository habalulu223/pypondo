import tkinter as tk
from tkinter import ttk
import time
import sys

def create_timer_window():
    timer_window = tk.Tk()
    timer_window.title("PyPondo Timer")
    timer_window.geometry("300x150")
    timer_window.resizable(False, False)
    # Removed -topmost so it can go to background
    timer_window.overrideredirect(True)  # Remove window decorations (no close/minimize buttons)
    timer_window.protocol("WM_DELETE_WINDOW", lambda: None)  # Prevent closing
    
    # Style
    style = ttk.Style()
    style.configure("Timer.TLabel", font=("Arial", 12, "bold"), foreground="cyan", background="black")
    style.configure("Cost.TLabel", font=("Arial", 10), foreground="yellow", background="black")
    
    timer_window.configure(bg="black")
    
    time_label = ttk.Label(timer_window, text="00:00:00", style="Timer.TLabel")
    time_label.pack(pady=10)
    
    cost_label = ttk.Label(timer_window, text="Cost: PHP 0.00", style="Cost.TLabel")
    cost_label.pack(pady=5)
    
    status_label = ttk.Label(timer_window, text="Click and hold to move, click to restore app\n(transparent immediately)", font=("Arial", 8), foreground="white", background="black")
    status_label.pack(pady=5)
    
    start_time = time.time()
    timer_window.attributes("-alpha", 0.4)  # Start transparent immediately
    
    # Drag functionality variables
    drag_data = {"x": 0, "y": 0, "dragging": False}
    
    def update_timer():
        elapsed = time.time() - start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        time_label.config(text=time_str)
        
        # Calculate cost at 15 PHP/hour
        cost = (elapsed / 3600) * 15.0
        cost_label.config(text=f"Cost: PHP {cost:.2f}")
        
        timer_window.after(1000, update_timer)
    
    def start_drag(event):
        timer_window.attributes("-alpha", 1.0)  # Make fully opaque when interacting
        drag_data["x"] = event.x_root - timer_window.winfo_x()
        drag_data["y"] = event.y_root - timer_window.winfo_y()
        drag_data["dragging"] = True
    
    def do_drag(event):
        if drag_data["dragging"]:
            x = event.x_root - drag_data["x"]
            y = event.y_root - drag_data["y"]
            timer_window.geometry(f"+{x}+{y}")
    
    def stop_drag(event):
        drag_data["dragging"] = False
    
    def on_click(event=None):
        if not drag_data["dragging"]:  # Only close if not dragging
            timer_window.attributes("-alpha", 1.0)  # Make fully opaque before closing
            timer_window.destroy()
            sys.exit(0)
    
    def on_enter(event):
        timer_window.attributes("-alpha", 1.0)  # Make fully opaque on hover
    
    def on_leave(event):
        timer_window.attributes("-alpha", 0.4)
    
    timer_window.bind("<Button-1>", start_drag)
    timer_window.bind("<B1-Motion>", do_drag)
    timer_window.bind("<ButtonRelease-1>", stop_drag)
    time_label.bind("<Button-1>", start_drag)
    time_label.bind("<B1-Motion>", do_drag)
    time_label.bind("<ButtonRelease-1>", stop_drag)
    cost_label.bind("<Button-1>", start_drag)
    cost_label.bind("<B1-Motion>", do_drag)
    cost_label.bind("<ButtonRelease-1>", stop_drag)
    status_label.bind("<Button-1>", start_drag)
    status_label.bind("<B1-Motion>", do_drag)
    status_label.bind("<ButtonRelease-1>", stop_drag)
    
    timer_window.bind("<Enter>", on_enter)
    timer_window.bind("<Leave>", on_leave)
    time_label.bind("<Enter>", on_enter)
    time_label.bind("<Leave>", on_leave)
    cost_label.bind("<Enter>", on_enter)
    cost_label.bind("<Leave>", on_leave)
    status_label.bind("<Enter>", on_enter)
    status_label.bind("<Leave>", on_leave)
    
    # Position window at bottom right
    screen_width = timer_window.winfo_screenwidth()
    screen_height = timer_window.winfo_screenheight()
    x = screen_width - 320
    y = screen_height - 170
    timer_window.geometry(f"+{x}+{y}")
    
    update_timer()
    timer_window.mainloop()

if __name__ == "__main__":
    create_timer_window()