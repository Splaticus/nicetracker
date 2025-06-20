import configparser
import os
from tkinter import ttk # Added for apply_theme

# Default theme colors
DEFAULT_COLORS = {
    "bg_main": "#1e1e2e",
    "bg_secondary": "#181825",
    "fg_main": "#cdd6f4",
    "accent_primary": "#74c7ec",
    "accent_secondary": "#89b4fa",
    "win": "#a6e3a1",
    "loss": "#f38ba8",
    "neutral": "#f9e2af"
}

CONFIG_FILE = "tracker_config.ini"

def get_config():
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)

    if 'Colors' not in config:
        config['Colors'] = DEFAULT_COLORS

    if 'Settings' not in config:
        config['Settings'] = {
            'auto_update_card_db': 'True',
            'check_for_app_updates': 'True',
            'card_name_display': 'True',
            'update_interval': '1500',
            'max_error_log_entries': '50'
        }

    if 'CardDB' not in config:
        config['CardDB'] = {
            'last_update': '0',
            'api_url': 'https://marvelsnapzone.com/getinfo/?searchtype=cards&searchcardstype=true'
        }

    return config

def save_config(config):
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)

def apply_theme(root, colors=None):
    if colors is None:
        config = get_config() # This will now call the get_config within config_utils.py
        colors = config['Colors']

    style = ttk.Style()
    style.theme_use('default')

    # Configure colors
    style.configure(".",
                    background=colors['bg_main'],
                    foreground=colors['fg_main'],
                    fieldbackground=colors['bg_secondary'])

    # Specific widget styles
    style.configure("TFrame", background=colors['bg_main'])
    style.configure("TLabel", background=colors['bg_main'], foreground=colors['fg_main'])
    style.configure("TButton",
                   background=colors['accent_primary'],
                   foreground=colors['bg_main'])
    style.map("TButton",
             background=[('active', colors['accent_secondary'])],
             foreground=[('active', colors['bg_main'])])

    style.configure("TNotebook", background=colors['bg_main'], foreground=colors['fg_main'])
    style.configure("TNotebook.Tab",
                   background=colors['bg_secondary'],
                   foreground=colors['fg_main'],
                   padding=[10, 2])
    style.map("TNotebook.Tab",
             background=[('selected', colors['accent_primary'])],
             foreground=[('selected', colors['bg_main'])])

    style.configure("Treeview",
                   background=colors['bg_secondary'],
                   foreground=colors['fg_main'],
                   fieldbackground=colors['bg_secondary'])
    style.map("Treeview",
             background=[('selected', colors['accent_primary'])],
             foreground=[('selected', colors['bg_main'])])

    style.configure("TLabelframe", background=colors['bg_main'])
    style.configure("TLabelframe.Label", background=colors['bg_main'], foreground=colors['fg_main'])

    # Custom styles for win/loss/neutral
    style.configure("Win.TLabel", foreground=colors['win'])
    style.configure("Loss.TLabel", foreground=colors['loss'])
    style.configure("Neutral.TLabel", foreground=colors['neutral'])

    # Configure root and child frames
    root.configure(background=colors['bg_main'])

    # Set scrollbar colors (doesn't always work with ttk)
    root.option_add("*TScrollbar*Background", colors['bg_secondary'])
    root.option_add("*TScrollbar*troughColor", colors['bg_main'])
    root.option_add("*TScrollbar*borderColor", colors['accent_primary'])

    # Make text widgets match theme
    root.option_add("*Text*Background", colors['bg_secondary'])
    root.option_add("*Text*Foreground", colors['fg_main'])
    root.option_add("*Text*selectBackground", colors['accent_primary'])
    root.option_add("*Text*selectForeground", colors['bg_main'])

    # Set menu colors
    root.option_add("*Menu*Background", colors['bg_secondary'])
    root.option_add("*Menu*Foreground", colors['fg_main'])
    root.option_add("*Menu*activeBackground", colors['accent_primary'])
    root.option_add("*Menu*activeForeground", colors['bg_main'])
