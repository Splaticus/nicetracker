from tracker.config import VERSION, apply_theme, get_config
from tracker.database import init_db
from tracker.ui import SnapTrackerApp
import tkinter as tk

if __name__ == "__main__":
    init_db()
    root = tk.Tk()
    config = get_config()
    apply_theme(root, config['Colors'])
    root.title(f"Marvel Snap Tracker v{VERSION}")
    root.geometry("1200x800")
    root.minsize(1000, 700)
    app = SnapTrackerApp(root)
    root.mainloop()
