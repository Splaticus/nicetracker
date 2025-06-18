import configparser
import os

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
