from db_utils import DB_NAME, init_db
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox, colorchooser
import ui_tabs # Added import for the new module
import json
import os
import glob
import time
import datetime
import traceback
import sqlite3
import hashlib
import shutil
import webbrowser
import csv
import requests
import threading
import re
import math
from PIL import Image, ImageTk
from io import BytesIO
from collections import Counter, defaultdict
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
import numpy as np
import configparser

VERSION = "2.0.1"  # Incremented version
COLLECTION_STATE_FILE = "CollectionState.json"
PLAY_STATE_FILE = "PlayState.json"
DECK_COLLECTION_CACHE = {"data": None, "last_mtime": 0}
CARD_DATA_FILE = "card_data.json"
CONFIG_FILE = "tracker_config.ini"
CARD_IMAGES_DIR = "card_images"

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

# --- Utility and Helper Functions ---
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
        config = get_config()
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

def get_snap_states_folder():
    username = os.getlogin()
    path = os.path.join("C:\\Users", username, "AppData", "LocalLow", "Second Dinner", "SNAP", "Standalone", "States")
    if not os.path.exists(path): 
        print(f"CRITICAL ERROR: Snap States folder not found at {path}")
        # Try alternative location
        alt_path = os.path.join("C:\\Users", username, "AppData", "LocalLow", "Marvel", "SNAP", "Standalone", "States")
        if os.path.exists(alt_path):
            print(f"Found alternative Snap States folder at {alt_path}")
            return alt_path
    return path

def get_game_state_path():
    base_folder = get_snap_states_folder()
    if not base_folder or not os.path.exists(base_folder): return None
    for state_dir_name in ["nvprod", "pvprod"]:
        potential_path = os.path.join(base_folder, state_dir_name, "GameState.json")
        if os.path.exists(potential_path): return potential_path
    direct_path = os.path.join(base_folder, "GameState.json")
    if os.path.exists(direct_path): return direct_path
    return None

def build_id_map(obj, id_map=None, visited_ids=None):
    if id_map is None: id_map = {}
    if visited_ids is None: visited_ids = set()
    if not isinstance(obj, (dict, list)): return id_map
    if isinstance(obj, dict):
        current_id = obj.get("$id")
        if current_id:
            if current_id in visited_ids: return id_map
            visited_ids.add(current_id)
            id_map[current_id] = obj
        for key, value in obj.items():
            if key == "$ref": continue
            build_id_map(value, id_map, visited_ids)
    elif isinstance(obj, list):
        for item in obj: build_id_map(item, id_map, visited_ids)
    return id_map

def resolve_ref(obj, id_map):
    if isinstance(obj, dict) and "$ref" in obj:
        ref_id = obj["$ref"]
        return id_map.get(ref_id, obj)
    return obj

def extract_cards_with_details(zone_data_ref, id_map, include_power=False, include_cost=False, return_card_def_ids_only=False, card_db=None):
    resolved_zone_data = resolve_ref(zone_data_ref, id_map)
    cards_info = []
    card_def_ids_only_list = []
    if resolved_zone_data and isinstance(resolved_zone_data, dict) and '_cards' in resolved_zone_data:
        for card_obj_maybe_ref in resolved_zone_data['_cards']:
            card_obj = resolve_ref(card_obj_maybe_ref, id_map)
            if card_obj and isinstance(card_obj, dict) and 'CardDefId' in card_obj:
                card_def_id = card_obj['CardDefId']
                card_def_ids_only_list.append(card_def_id)
                if return_card_def_ids_only:
                    continue
                
                # Use card name if available in card_db
                card_name = card_def_id
                if card_db and card_def_id in card_db:
                    card_name = card_db[card_def_id].get('name', card_def_id)
                
                details = []
                cost_obj = resolve_ref(card_obj.get('Cost', {}), id_map)
                power_obj = resolve_ref(card_obj.get('Power', {}), id_map)
                if include_cost and isinstance(cost_obj, dict) and 'Value' in cost_obj: 
                    details.append(f"C:{cost_obj['Value']}")
                if include_power and isinstance(power_obj, dict) and 'Value' in power_obj: 
                    details.append(f"P:{power_obj['Value']}")
                if details: 
                    cards_info.append(f"{card_name} ({', '.join(details)})")
                else: 
                    cards_info.append(card_name)
    if return_card_def_ids_only:
        return card_def_ids_only_list
    return cards_info

def load_deck_names_from_collection():
    global DECK_COLLECTION_CACHE
    base_folder = get_snap_states_folder()
    if not base_folder:
        print(f"CRITICAL: Base folder for Snap states not found.")
        return {}
    expected_collection_file_path = os.path.join(base_folder, COLLECTION_STATE_FILE)
    collection_file_path_to_use = None
    if os.path.exists(expected_collection_file_path): 
        collection_file_path_to_use = expected_collection_file_path
    else:
        for state_dir_name in ["nvprod", "pvprod"]:
            potential_alt_path = os.path.join(base_folder, state_dir_name, COLLECTION_STATE_FILE)
            if os.path.exists(potential_alt_path): 
                collection_file_path_to_use = potential_alt_path
                break
        if not collection_file_path_to_use:
            one_level_up_path_base = os.path.dirname(base_folder)
            potential_one_up_path = os.path.join(one_level_up_path_base, COLLECTION_STATE_FILE)
            if os.path.exists(potential_one_up_path): 
                collection_file_path_to_use = potential_one_up_path
    if not collection_file_path_to_use:
        print(f"INFO: {COLLECTION_STATE_FILE} not found. Collection features disabled.")
        return {}
    try:
        current_mtime = os.path.getmtime(collection_file_path_to_use)
        if DECK_COLLECTION_CACHE["data"] is not None and DECK_COLLECTION_CACHE["last_mtime"] == current_mtime:
            return DECK_COLLECTION_CACHE["data"]
        with open(collection_file_path_to_use, 'r', encoding='utf-8-sig') as f: 
            collection_data = json.load(f)
        print(f"DEBUG: Successfully loaded {COLLECTION_STATE_FILE} from {collection_file_path_to_use}")
    except Exception as e:
        print(f"Error reading/parsing {collection_file_path_to_use}: {e}")
        return DECK_COLLECTION_CACHE.get("data", {})

    id_map = build_id_map(collection_data)
    decks_map = {}
    print(f"DEBUG load_collection: Top-level keys in CollectionState: {list(collection_data.keys())}")
    client_state_obj = collection_data.get("ClientState", {})
    server_state_obj = collection_data.get("ServerState", {})
    if isinstance(client_state_obj, dict) and "$ref" in client_state_obj: 
        client_state_obj = resolve_ref(client_state_obj, id_map)
    if isinstance(server_state_obj, dict) and "$ref" in server_state_obj: 
        server_state_obj = resolve_ref(server_state_obj, id_map)

    possible_deck_paths_options = {
        "Decks_direct": collection_data.get("Decks"),
        "ClientState_Decks": client_state_obj.get("Decks") if isinstance(client_state_obj, dict) else None,
        "ServerState_Decks": server_state_obj.get("Decks") if isinstance(server_state_obj, dict) else None,
        "ClientState_PlayerState_Decks": client_state_obj.get("PlayerState", {}).get("Decks") if isinstance(client_state_obj, dict) else None,
        "ClientState_AccountData_Decks": client_state_obj.get("AccountData", {}).get("Decks") if isinstance(client_state_obj, dict) else None,
    }
    decks_container_ref_or_obj = None # Can be a ref or the actual list/dict
    found_path_key = None
    for key, path_attempt in possible_deck_paths_options.items():
        if path_attempt:
            decks_container_ref_or_obj = path_attempt
            found_path_key = key
            print(f"DEBUG load_collection: Found potential decks container via '{key}'. Object type: {type(decks_container_ref_or_obj)}")
            break
    if not decks_container_ref_or_obj:
        print(f"WARNING load_collection: Could not find common paths to decks list in CollectionState.")
        return {}

    decks_container = resolve_ref(decks_container_ref_or_obj, id_map) # Resolve if it was a ref
    print(f"DEBUG load_collection: Final resolved decks_container (type: {type(decks_container)}): {str(decks_container)[:200]}...")
    deck_list_items_to_process = None
    if decks_container and isinstance(decks_container, dict) and "$values" in decks_container:
        deck_list_items_to_process = decks_container["$values"]
        print(f"DEBUG load_collection: Found '$values' in decks_container. Number of deck items: {len(deck_list_items_to_process)}")
    elif decks_container and isinstance(decks_container, list):
        deck_list_items_to_process = decks_container
        print(f"DEBUG load_collection: decks_container is directly a list. Number of deck items: {len(deck_list_items_to_process)}")
    
    if not deck_list_items_to_process:
        print(f"WARNING load_collection: Could not determine list of deck items. Type: {type(decks_container)}")
        return {} # Essential to return empty if no items found

    for i, deck_obj_or_ref in enumerate(deck_list_items_to_process):
        deck_obj = resolve_ref(deck_obj_or_ref, id_map)
        if deck_obj and isinstance(deck_obj, dict):
            coll_deck_id = deck_obj.get("Id")
            deck_name = deck_obj.get("Name")
            cards_property_from_deck_obj = deck_obj.get("Cards")
            cards_list_refs_container = resolve_ref(cards_property_from_deck_obj, id_map)
            card_def_ids = []
            actual_card_list_items_from_cards_prop = None
            if cards_list_refs_container and isinstance(cards_list_refs_container, dict) and '$values' in cards_list_refs_container:
                actual_card_list_items_from_cards_prop = cards_list_refs_container['$values']
            elif cards_list_refs_container and isinstance(cards_list_refs_container, list):
                actual_card_list_items_from_cards_prop = cards_list_refs_container
            if actual_card_list_items_from_cards_prop:
                for card_ref_in_deck_list in actual_card_list_items_from_cards_prop:
                    card_data_obj = resolve_ref(card_ref_in_deck_list, id_map)
                    if card_data_obj and isinstance(card_data_obj, dict) and card_data_obj.get("CardDefId"):
                        card_def_ids.append(str(card_data_obj["CardDefId"]))
            if coll_deck_id and deck_name and card_def_ids:
                unique_norm_list = sorted(list(set(card_def_ids)))
                d_hash = hashlib.sha256(json.dumps(unique_norm_list).encode('utf-8')).hexdigest()
                decks_map[coll_deck_id] = {"name": deck_name, "cards": sorted(card_def_ids), "hash": d_hash}
                print(f"SUCCESS load_collection: Added deck '{deck_name}' (ID: {coll_deck_id}, Cards: {len(card_def_ids)}) to decks_map.")
            else:
                print(f"WARNING load_collection: Skipping deck item #{i} due to missing ID, Name, or Cards. ID: {coll_deck_id}, Name: {deck_name}, Card Count: {len(card_def_ids)}")
        else:
            print(f"WARNING load_collection: deck_obj for item #{i} not a valid dict or None after resolving.")
    print(f"DEBUG load_deck_names_from_collection: Final populated decks_map with {len(decks_map)} entries.")
    DECK_COLLECTION_CACHE["data"] = decks_map
    DECK_COLLECTION_CACHE["last_mtime"] = current_mtime
    return decks_map

def get_selected_deck_id_from_playstate():
    base_folder = get_snap_states_folder()
    if not base_folder: return None
    play_state_path = None
    direct_path_playstate = os.path.join(base_folder, PLAY_STATE_FILE)
    if os.path.exists(direct_path_playstate): 
        play_state_path = direct_path_playstate
    else:
        for state_dir_name in ["nvprod", "pvprod"]:
            potential_path = os.path.join(base_folder, state_dir_name, PLAY_STATE_FILE)
            if os.path.exists(potential_path): 
                play_state_path = potential_path
                break
    if not play_state_path:
        print(f"INFO: {PLAY_STATE_FILE} not found in common locations.")
        return None
    try:
        with open(play_state_path, 'r', encoding='utf-8-sig') as f: 
            play_state_data = json.load(f)
        selected_deck_id_obj = play_state_data.get("SelectedDeckId")
        if selected_deck_id_obj and isinstance(selected_deck_id_obj, dict):
            deck_id = selected_deck_id_obj.get("Value")
            if deck_id and isinstance(deck_id, str):
                print(f"DEBUG: Successfully read Deck ID '{deck_id}' from {play_state_path}")
                return deck_id
    except Exception as e:
        print(f"Error reading/parsing {play_state_path}: {e}")
    return None

def load_card_database():
    """Load card database from local file or download if not available"""
    try:
        if os.path.exists(CARD_DATA_FILE):
            with open(CARD_DATA_FILE, 'r', encoding='utf-8') as f:
                card_db = json.load(f)
                print(f"Loaded card database with {len(card_db)} cards")
                return card_db
    except Exception as e:
        print(f"Error loading card database: {e}")
    
    # If we reach here, either file doesn't exist or couldn't be loaded
    return update_card_database()

def update_card_database():
    """Download and update the card database from Marvel Snap Zone or similar API"""
    config = get_config()
    api_url = config['CardDB']['api_url']
    card_db = {}
    
    try:
        print(f"Downloading card database from {api_url}")
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        
        # Parse the response
        data = response.json()
        
        # Check if the expected structure exists
        if 'success' in data and 'cards' in data['success']:
            # Process cards
            for card in data['success']['cards']:
                card_id = card.get('carddefid')
                if card_id:
                    card_db[card_id] = {
                        'name': card.get('name', card_id),
                        'cost': card.get('cost'),
                        'power': card.get('power'),
                        'ability': card.get('ability', ''),
                        'image_url': card.get('art', '')
                    }
            
            # Save to file
            with open(CARD_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(card_db, f, indent=2)
            
            # Update config
            config['CardDB']['last_update'] = str(int(time.time()))
            save_config(config)
            
            print(f"Downloaded and saved card database with {len(card_db)} cards")
            return card_db
        else:
            print("Unexpected API response format")
            return {}
            
    except Exception as e:
        print(f"Error updating card database: {e}")
        return {}

# Add this function for manual JSON import
def import_card_database_from_file():
    """Import card database from a JSON file"""
    filename = filedialog.askopenfilename(
        defaultextension=".json",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        title="Import Card Database"
    )
    
    if not filename:
        return None
        
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        card_db = {}
        cards_processed = 0
        
        # Try different possible structures
        if isinstance(data, dict):
            # If it's a dictionary with cards array
            if 'cards' in data and isinstance(data['cards'], list):
                for card in data['cards']:
                    card_id = card.get('defId', card.get('id', card.get('cardDefId')))
                    if card_id:
                        card_db[card_id] = {
                            'name': card.get('name', card.get('cardName', card_id)),
                            'cost': card.get('cost'),
                            'power': card.get('power'),
                            'ability': card.get('ability', card.get('text', '')),
                            'image_url': card.get('image', card.get('cardImage', ''))
                        }
                        cards_processed += 1
            
            # If it has a data array
            elif 'data' in data and isinstance(data['data'], list):
                for card in data['data']:
                    card_id = card.get('card_id', card.get('defId', card.get('id')))
                    if card_id:
                        card_db[card_id] = {
                            'name': card.get('card_name', card.get('name', card_id)),
                            'cost': card.get('cost'),
                            'power': card.get('power'),
                            'ability': card.get('ability_text', card.get('text', '')),
                            'image_url': card.get('card_image', card.get('image', ''))
                        }
                        cards_processed += 1
                        
            # If it's a direct mapping of card_id -> card_data
            else:
                for card_id, card_info in data.items():
                    if isinstance(card_info, dict):
                        card_db[card_id] = {
                            'name': card_info.get('name', card_id),
                            'cost': card_info.get('cost'),
                            'power': card_info.get('power'),
                            'ability': card_info.get('ability', card_info.get('text', '')),
                            'image_url': card_info.get('image', '')
                        }
                        cards_processed += 1
                    
        # If it's a direct list of cards
        elif isinstance(data, list):
            for card in data:
                if isinstance(card, dict):
                    card_id = card.get('defId', card.get('id', card.get('cardDefId')))
                    if card_id:
                        card_db[card_id] = {
                            'name': card.get('name', card.get('cardName', card_id)),
                            'cost': card.get('cost'),
                            'power': card.get('power'),
                            'ability': card.get('ability', card.get('text', '')),
                            'image_url': card.get('image', card.get('cardImage', ''))
                        }
                        cards_processed += 1
        
        # Save the imported data
        if card_db:
            with open(CARD_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(card_db, f, indent=2)
                
            config = get_config()
            config['CardDB']['last_update'] = str(int(time.time()))
            save_config(config)
                
            messagebox.showinfo(
                "Import Successful", 
                f"Successfully imported {len(card_db)} cards from {filename}.\n\nProcessed {cards_processed} card entries."
            )
            return card_db
        else:
            messagebox.showwarning(
                "Import Warning",
                f"No valid card data found in {filename}.\nMake sure the file has the correct structure."
            )
            return None
            
    except Exception as e:
        messagebox.showerror("Import Error", f"Error importing card database: {str(e)}")
        return None

def create_fallback_card_database():
    """Create a minimal card database with just IDs as names"""
    # This is just a safety measure to ensure the app works
    # even without proper card data
    print("Creating fallback card database")
    return {}

def download_card_image(card_id, card_db):
    """Download card image if not already available"""
    # Create directory if it doesn't exist
    if not os.path.exists(CARD_IMAGES_DIR):
        os.makedirs(CARD_IMAGES_DIR)
    
    image_path = os.path.join(CARD_IMAGES_DIR, f"{card_id}.jpg")
    
    # Return path if image already exists
    if os.path.exists(image_path):
        return image_path
        
    # Try to download the image
    if card_id in card_db and 'image_url' in card_db[card_id] and card_db[card_id]['image_url']:
        image_url = card_db[card_id]['image_url']
        try:
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            
            with open(image_path, 'wb') as f:
                f.write(response.content)
                
            return image_path
        except Exception as e:
            print(f"Error downloading image for {card_id}: {e}")
    
    return None

def get_card_tooltip_text(card_id, card_db):
    """Generate tooltip text for a card"""
    if not card_db or card_id not in card_db:
        return f"Card ID: {card_id}\nNo additional data available"
    
    card = card_db[card_id]
    tooltip = f"{card.get('name', card_id)}\n"
    
    if 'cost' in card and card['cost'] is not None:
        tooltip += f"Cost: {card['cost']} "
    if 'power' in card and card['power'] is not None:
        tooltip += f"Power: {card['power']}"
    
    if 'ability' in card and card['ability']:
        tooltip += f"\n\n{card['ability']}"
    
    return tooltip.strip()

def get_current_season_and_rank():
    """Try to determine the current season and rank from game files"""
    # This is a placeholder - implementation would depend on where this info is stored in game files
    # For now, return defaults
    return "Unknown", "Unknown"

def get_or_create_deck_id(card_ids_list, collection_deck_id, deck_name_override=None, card_db=None, tags=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Normalize card IDs list
    unique_normalized_list = sorted(list(set(str(cid) for cid in card_ids_list if cid))) if card_ids_list else []
    deck_hash = hashlib.sha256(json.dumps(unique_normalized_list).encode('utf-8')).hexdigest()
    
    # Create JSON string for database storage
    stored_card_ids_list = sorted([str(cid) for cid in card_ids_list if cid]) if card_ids_list else []
    card_ids_json_for_db = json.dumps(stored_card_ids_list)
    
    # Use provided deck name or a default
    effective_deck_name = deck_name_override if deck_name_override else "Unnamed Deck"
    
    # Generate a more descriptive auto-name if appropriate
    if not deck_name_override or deck_name_override == "Unnamed Deck":
        if card_db and len(unique_normalized_list) > 0:
            # Get archetype cards for naming
            key_cards = []
            for card_id in unique_normalized_list[:3]:  # Use first 3 cards for naming
                if card_id in card_db:
                    key_cards.append(card_db[card_id].get('name', card_id))
                else:
                    key_cards.append(card_id)
            if key_cards:
                effective_deck_name = f"Deck with {', '.join(key_cards)}"
    
    # Process tags
    tags_json = json.dumps(tags) if tags else None
    
    # Check if deck already exists
    cursor.execute("SELECT id, deck_name, collection_deck_id, tags FROM decks WHERE deck_hash = ?", (deck_hash,))
    deck_row = cursor.fetchone()
    
    if deck_row:
        deck_id = deck_row[0]
        db_deck_name = deck_row[1]
        db_coll_id = deck_row[2]
        db_tags = deck_row[3]
        
        # Check for changes
        updates = []
        if deck_name_override and db_deck_name != deck_name_override:
            updates.append(("deck_name", deck_name_override))
        if collection_deck_id and db_coll_id != collection_deck_id:
            updates.append(("collection_deck_id", collection_deck_id))
        if tags_json and db_tags != tags_json:
            updates.append(("tags", tags_json))
        
        # Apply updates if needed
        if updates:
            set_clauses = ", ".join([f"{col} = ?" for col, val in updates])
            values = [val for col, val in updates] + [deck_hash]
            cursor.execute(f"UPDATE decks SET {set_clauses}, last_used = CURRENT_TIMESTAMP WHERE deck_hash = ?", tuple(values))
        else:
            cursor.execute("UPDATE decks SET last_used = CURRENT_TIMESTAMP WHERE deck_hash = ?", (deck_hash,))
        
        conn.commit()
        conn.close()
        return deck_id
    else:
        # Insert new deck
        cursor.execute("INSERT INTO decks (deck_name, card_ids_json, deck_hash, collection_deck_id, tags) VALUES (?, ?, ?, ?, ?)", 
                      (effective_deck_name, card_ids_json_for_db, deck_hash, collection_deck_id, tags_json))
        deck_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return deck_id

def record_match_event(game_id, turn, event_type, player_type, card_def_id, location_index, source_zone, target_zone, details_json_str):
    if not game_id: return
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        # Ensure details_json_str is a string. If it's already a dict, dump it.
        if isinstance(details_json_str, dict):
            details_to_store = json.dumps(details_json_str)
        elif isinstance(details_json_str, str):
            details_to_store = details_json_str
        else: # Fallback for None or other types
            details_to_store = json.dumps({})

        # Attempt to insert, ignoring if it's a duplicate (based on uidx_events_unique)
        cursor.execute("""
            INSERT OR IGNORE INTO match_events 
            (game_id, turn, event_type, player_type, card_def_id, location_index, source_zone, target_zone, details_json) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (game_id, turn, event_type, player_type, card_def_id, location_index, source_zone, target_zone, details_to_store))
        conn.commit()
    except sqlite3.Error as e: 
        print(f"DB error recording event for {game_id}: {e}")
    finally: 
        conn.close()

def record_match_result(match_data, deck_collection_map, game_events_log, card_db=None):
    if not match_data.get('game_id'): 
        print("DB_RECORD: Cannot record match: Missing game_id.")
        return False
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        # Check if match already exists
        cursor.execute("SELECT 1 FROM matches WHERE game_id = ?", (match_data['game_id'],))
        if cursor.fetchone(): 
            conn.close()
            return False
        
        # Get deck information
        deck_name_from_game = match_data.get('deck_name_from_gamestate')
        deck_card_ids = match_data.get('deck_card_ids_from_gamestate')
        deck_name_from_collection = None
        collection_deck_id_for_db = None
        
        if deck_card_ids and deck_collection_map:
            temp_unique_normalized_list = sorted(list(set(str(cid) for cid in deck_card_ids if cid)))
            temp_deck_hash = hashlib.sha256(json.dumps(temp_unique_normalized_list).encode('utf-8')).hexdigest()
            
            for coll_id, coll_deck_info in deck_collection_map.items():
                if coll_deck_info.get("hash") == temp_deck_hash:
                    deck_name_from_collection = coll_deck_info.get("name")
                    collection_deck_id_for_db = coll_id
                    break
        
        # Use the best available deck name
        final_deck_name_for_db = deck_name_from_collection if deck_name_from_collection else deck_name_from_game
        
        # Get deck tags based on cards
        deck_tags = None
        if deck_card_ids and card_db:
            # This is a placeholder for deck archetype detection logic
            # You would analyze the deck contents to determine archetypes or themes
            # and add them as tags
            deck_tags = ["auto-generated"] # Example
        
        # Create or get the deck ID
        deck_db_id = get_or_create_deck_id(
            deck_card_ids, 
            collection_deck_id_for_db, 
            final_deck_name_for_db,
            card_db,
            deck_tags
        )
        
        # Prepare location data
        locs = match_data.get('locations_at_end', [None, None, None])
        loc1, loc2, loc3 = (locs + [None]*3)[:3] # Ensure exactly 3 elements
        
        # Prepare snap data
        snap_turn_player = match_data.get('snap_turn_player', 0)
        snap_turn_opponent = match_data.get('snap_turn_opponent', 0)
        final_snap_state = match_data.get('final_snap_state', 'None')
        
        # Prepare opponent card data
        opp_revealed_cards = match_data.get('opponent_revealed_cards_at_end', [])
        opp_revealed_cards_json = json.dumps(sorted(list(set(opp_revealed_cards)))) if opp_revealed_cards else None
        
        # Get current season and rank
        season, rank = get_current_season_and_rank()
        
        # Insert the match record
        cursor.execute('''
            INSERT INTO matches (
                game_id, local_player_name, opponent_player_name, deck_id, 
                result, cubes_changed, turns_taken, 
                loc_1_def_id, loc_2_def_id, loc_3_def_id, 
                snap_turn_player, snap_turn_opponent, final_snap_state, 
                opp_revealed_cards_json, season, rank
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            match_data['game_id'], 
            match_data.get('local_player_name', 'You'), 
            match_data.get('opponent_player_name', 'Opponent'), 
            deck_db_id, 
            match_data.get('result', 'unknown'), 
            match_data.get('cubes_changed'), 
            match_data.get('turns_taken'), 
            loc1, loc2, loc3, 
            snap_turn_player, snap_turn_opponent, final_snap_state, 
            opp_revealed_cards_json,
            season, rank
        ))
        
        conn.commit()
        print(f"Match recorded: {match_data['game_id']} - Deck: '{final_deck_name_for_db or 'Unknown Deck'}' - {match_data.get('result')} ({match_data.get('cubes_changed', '?')} cubes)")
        
        # Record match events
        game_id_for_events = match_data['game_id']
        
        interim_events  = game_events_log.get(game_id_for_events, [])
        
        final_drawn_cards = match_data.get('card_def_ids_drawn_at_end', [])
        final_played_cards = match_data.get('card_def_ids_played_at_end', [])
        
        interim_drawn_logged_cards = {
            ev['card'] for ev in interim_events 
            if ev['type'] == 'drawn' and ev['player'] == 'local'
        }
        interim_played_logged_cards = {
            ev['card'] for ev in interim_events 
            if ev['type'] == 'played' and ev['player'] == 'local'
        }
        
        # NOW IT'S SAFE TO USE interim_events (or a similarly named variable if you prefer)
        print(f"DEBUG record_match_result (Game {game_id_for_events}):")
        print(f"  Final Drawn from GameState: {len(final_drawn_cards)} cards ({final_drawn_cards[:5]}...)")
        print(f"  Final Played from GameState: {len(final_played_cards)} cards ({final_played_cards[:5]}...)")
        # Corrected print statement:
        print(f"  Interim Events Logged (before reconciliation): {len(interim_events)} events")
        print(f"  Interim Drawn Logged (from interim events): {len(interim_drawn_logged_cards)} unique cards")
        print(f"  Interim Played Logged (from interim events): {len(interim_played_logged_cards)} unique cards")
        
        # 1. Record all interim events (they have more detail like turn, location)
        #    The INSERT OR IGNORE in record_match_event will handle potential duplicates
        #    if this function is somehow called multiple times for the same game with same events.
        for event_dict in interim_events:
            # print(f"DEBUG record_match_result: Attempting to record event: {event_dict}")
            record_match_event(
                game_id_for_events,
                event_dict.get('turn'), 
                event_dict.get('type'), 
                event_dict.get('player'),
                event_dict.get('card'), 
                event_dict.get('location_index'),
                event_dict.get('source_zone'), 
                event_dict.get('target_zone'),
                event_dict.get('details', {})
            )
            
        # 2. Reconcile Drawn Cards
        # We need to be careful here. The 'final_drawn_cards' is likely a list of *all* cards
        # that entered the hand during the game. If a card was drawn and then played, it's still "drawn".
        # The interim log should ideally capture each unique draw.
        # The goal here is to add any draws that were missed by the interim logging.
        
        # Convert final_drawn_cards to a Counter to respect multiple copies of a card being drawn (if applicable)
        # For Snap, a card is either in the deck or not, so simple set difference is fine for *which* cards were drawn.
        # If the game reports each *instance* of a draw (e.g. "America Chavez" drawn via effect, then drawn normally),
        # then a Counter based approach might be needed if your interim logging can't catch that.
        # For now, let's assume we just want to ensure each *unique* card reported as drawn by the game is logged at least once.
        
        placeholder_turn_for_missed_events = match_data.get('turns_taken', 0) # Use final turn or 0
        for card_def_id in final_drawn_cards:
            if card_def_id not in interim_drawn_logged_cards:
                print(f"  RECONCILE_DRAWN: Game {game_id_for_events}, Card {card_def_id} in final_drawn but not in interim_drawn. Adding.")
                record_match_event(
                    game_id=game_id_for_events,
                    turn=placeholder_turn_for_missed_events, # Or a special value like -1
                    event_type='drawn',
                    player_type='local',
                    card_def_id=card_def_id,
                    location_index=None, # Not known
                    source_zone='Deck',  # Assumed
                    target_zone='Hand',  # Assumed
                    details_json_str={'source': 'reconciliation_end_game'}
                )
                interim_drawn_logged_cards.add(card_def_id) # Add to set to avoid double-logging if present multiple times in final_drawn_cards
                
        # 3. Reconcile Played Cards
        # Similar to drawn, add any plays missed by interim logging.
        for card_def_id in final_played_cards:
            if card_def_id not in interim_played_logged_cards:
                print(f"  RECONCILE_PLAYED: Game {game_id_for_events}, Card {card_def_id} in final_played but not in interim_played. Adding.")
                record_match_event(
                    game_id=game_id_for_events,
                    turn=placeholder_turn_for_missed_events, # Or a special value
                    event_type='played',
                    player_type='local',
                    card_def_id=card_def_id,
                    location_index=None, # Not known from this list
                    source_zone='Hand',  # Assumed
                    target_zone='Board', # Assumed, could be more specific if needed (e.g., "Location_Unknown")
                    details_json_str={'source': 'reconciliation_end_game'}
                )
                interim_played_logged_cards.add(card_def_id)                
        print(f"DEBUG record_match_result: Finished event reconciliation for game {game_id_for_events}.")
         
        return True
    except sqlite3.Error as e:
        print(f"DB error recording match {match_data.get('game_id', 'UNKNOWN_GAME_ID')}: {e}")
        return False
    finally:
        if conn: conn.close()

def analyze_game_state_for_gui(file_path, current_game_events, initial_deck_for_current_game, card_db=None, game_already_recorded_in_db=False):
    if not file_path or not os.path.exists(file_path): 
        return {"error": f"File path invalid/not found: {file_path}", "full_error": ""}
    
    state_data = None
    for attempt in range(3):
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f: 
                state_data = json.load(f)
            break
        except Exception:
            if attempt == 2: 
                return {
                    "error": f"Error reading file after multiple attempts", 
                    "full_error": traceback.format_exc()
                }
            time.sleep(0.1)
    
    if state_data is None: 
        return {
            "error": "Failed to load game state.", 
            "full_error": "Max retries reached."
        }

    id_map = build_id_map(state_data)
    game_info = {
        "local_player": {
            "hand": [], 
            "graveyard": [], 
            "banished": [], 
            "board": [[] for _ in range(3)], 
            "remaining_deck_list": None, 
            "snap_info": "Snap: N/A"
        },
        "opponent": {
            "graveyard": [], 
            "banished": [], 
            "board": [[] for _ in range(3)], 
            "snap_info": "Snap: N/A"
        },
        "game_details": {
            "locations": [{} for _ in range(3)], 
            "local_is_gamelogic_player1": False
        },
        "error": None, 
        "full_error": None, 
        "end_game_data": None, 
        "current_game_id_for_events": None
    }
    
    try:
        remote_game = resolve_ref(state_data.get('RemoteGame'), id_map)
        if not remote_game or not isinstance(remote_game, dict): 
            game_info["error"] = "'RemoteGame' not found/resolvable."
            return game_info
        
        client_game_info = resolve_ref(remote_game.get('ClientGameInfo'), id_map)
        if not client_game_info or not isinstance(client_game_info, dict): 
            game_info["error"] = "'ClientGameInfo' not found/resolvable."
            return game_info
        
        client_side_player_info_ref = remote_game.get('ClientPlayerInfo')
        client_side_player_info = resolve_ref(client_side_player_info_ref, id_map)
        local_account_id_from_client = client_side_player_info.get('AccountId') if client_side_player_info and isinstance(client_side_player_info, dict) else None
        
        local_player_entity_id = client_game_info.get('LocalPlayerEntityId')
        if local_player_entity_id is None: 
            game_info["error"] = "'LocalPlayerEntityId' not found."
            return game_info
        
        enemy_player_entity_id = client_game_info.get('EnemyPlayerEntityId')
        game_logic_state = resolve_ref(remote_game.get('GameState'), id_map)
        current_game_id_for_state = game_logic_state.get("Id") if game_logic_state and isinstance(game_logic_state, dict) else None
        game_info["current_game_id_for_events"] = current_game_id_for_state
        
        gd = game_info["game_details"]
        lp_info = game_info["local_player"]

        if game_logic_state and isinstance(game_logic_state, dict):
            gd["turn"] = resolve_ref(game_logic_state.get('Turn'), id_map)
            gd["total_turns"] = resolve_ref(game_logic_state.get('TotalTurns'), id_map)
            gd["cube_value"] = resolve_ref(game_logic_state.get('CubeValue'), id_map)
            
            game_ended_by_clientresultmessage = bool(resolve_ref(game_logic_state.get('ClientResultMessage'), id_map))

            if game_already_recorded_in_db:
                # If game is already in DB, clear any in-memory events for it to prevent re-processing
                # or logging from a stale GameState.json file after tracker restart.
                if current_game_id_for_state in current_game_events:
                    del current_game_events[current_game_id_for_state]
            elif not game_ended_by_clientresultmessage: # Only log events if game is active and not already recorded
                # Event Logging from ClientPlayerInfo
                if current_game_id_for_state and client_side_player_info and isinstance(client_side_player_info, dict):
                    if current_game_id_for_state not in current_game_events: 
                        current_game_events[current_game_id_for_state] = []
                    
                    # Played Events
                    existing_played_event_keys = {
                        (e['turn'], e['card'], e.get('location_index'), e.get('details',{}).get('energy_spent',-1)) 
                        for e in current_game_events[current_game_id_for_state] 
                        if e['type'] == 'played'
                    }
                    
                    client_stage_requests = [
                        resolve_ref(req_ref, id_map) 
                        for req_ref in client_side_player_info.get('ClientStageRequests', [])
                    ]
                    
                    for req in client_stage_requests:
                        if req and isinstance(req, dict) and req.get('CurrentState') == "EndTurnChangeApplied":
                            card_entity_id_staged = req.get('CardEntityId')
                            card_obj_staged = None
                            entity_to_entity_map = resolve_ref(game_logic_state.get("_entityIdToEntity"), id_map)
                            
                            if entity_to_entity_map and isinstance(entity_to_entity_map, dict): 
                                card_obj_staged = resolve_ref(entity_to_entity_map.get(str(card_entity_id_staged)), id_map)
                            
                            if card_obj_staged and isinstance(card_obj_staged, dict):
                                card_def_id = card_obj_staged.get('CardDefId')
                                turn_played = req.get('Turn')
                                target_zone_entity_id = req.get('TargetZoneEntityId')
                                location_index = None
                                
                                if game_logic_state and isinstance(game_logic_state, dict):
                                    for loc_idx_iter, loc_data_ref in enumerate(game_logic_state.get('_locations',[])):
                                        loc_data = resolve_ref(loc_data_ref, id_map)
                                        if loc_data and isinstance(loc_data, dict) and loc_data.get('EntityId') == target_zone_entity_id: 
                                            location_index = loc_data.get('SlotIndex', loc_idx_iter)
                                            break
                                
                                event_key = (turn_played, card_def_id, location_index, req.get('EnergySpent', -1))
                                if card_def_id and turn_played is not None and event_key not in existing_played_event_keys:
                                    event_to_add = {
                                        'turn': turn_played, 
                                        'type': 'played', 
                                        'player': 'local', 
                                        'card': card_def_id, 
                                        'location_index': location_index, 
                                        'source_zone': f"Zone{req.get('SourceZoneEntityId')}", 
                                        'target_zone': f"Location{location_index}" if location_index is not None else f"Zone{target_zone_entity_id}", 
                                        'details': {'energy_spent': req.get('EnergySpent')}
                                    }
                                    # print(f"DEBUG analyze_game_state: Logging PLAYED event: {event_to_add}")
                                    current_game_events[current_game_id_for_state].append(event_to_add)
                                    existing_played_event_keys.add(event_key)
                    
                    # Drawn Events
                    logged_drawn_cards_for_this_game_defs = {
                        ev['card'] 
                        for ev in current_game_events.get(current_game_id_for_state, []) 
                        if ev['type'] == 'drawn' and ev['player'] == 'local' # ensure we are checking local player draws
                    }
                    
                    cards_drawn_log_refs = client_side_player_info.get('CardsDrawn', []) if client_side_player_info and isinstance(client_side_player_info, dict) else []
                    current_turn_for_logging_draws = gd.get("turn", 0) or 0 # Use current turn if available
                    
                    for card_def_id_drawn in cards_drawn_log_refs: # Assuming this is a list of CardDefId strings
                        if card_def_id_drawn and card_def_id_drawn != "None" and card_def_id_drawn not in logged_drawn_cards_for_this_game_defs:
                            event_to_add = {
                                'turn': current_turn_for_logging_draws, 
                                'type': 'drawn', 
                                'player': 'local', 
                                'card': card_def_id_drawn, 
                                'source_zone': 'Deck', 
                                'target_zone': 'Hand', 
                                'details': {}
                            }
                            # print(f"DEBUG analyze_game_state: Logging DRAWN event: {event_to_add}")
                            current_game_events.setdefault(current_game_id_for_state, []).append(event_to_add)
                            logged_drawn_cards_for_this_game_defs.add(card_def_id_drawn)
            
            # Process players
            all_players_in_state_refs = game_logic_state.get('_players', [])
            all_players_in_state = [resolve_ref(p_ref, id_map) for p_ref in all_players_in_state_refs]
            all_players_in_state = [p for p in all_players_in_state if p and isinstance(p, dict)]
            player_map = {p.get('EntityId'): p for p in all_players_in_state}
            player1_entity_id_from_gamelogic = all_players_in_state[0].get('EntityId') if all_players_in_state else None
            gd["local_is_gamelogic_player1"] = (player1_entity_id_from_gamelogic is not None and local_player_entity_id == player1_entity_id_from_gamelogic)
            
            # Process snap status
            turn_snapped_p1 = game_logic_state.get('TurnSnappedPlayer1', 0)
            turn_snapped_p2 = game_logic_state.get('TurnSnappedPlayer2', 0)
            if gd["local_is_gamelogic_player1"]:
                lp_info["snap_info"] = f"Snap: T{turn_snapped_p1}" if turn_snapped_p1 > 0 else "Snap: No"
                game_info["opponent"]["snap_info"] = f"Snap: T{turn_snapped_p2}" if turn_snapped_p2 > 0 else "Snap: No"
            else:
                lp_info["snap_info"] = f"Snap: T{turn_snapped_p2}" if turn_snapped_p2 > 0 else "Snap: No"
                game_info["opponent"]["snap_info"] = f"Snap: T{turn_snapped_p1}" if turn_snapped_p1 > 0 else "Snap: No"
            
            # Process locations
            locations_data_from_json_refs = game_logic_state.get('_locations', [])
            locations_data_from_json = [resolve_ref(l_ref, id_map) for l_ref in locations_data_from_json_refs]
            processed_locations = [{} for _ in range(3)]
            unassigned_idx_counter = 0
            
            for loc_obj in locations_data_from_json:
                if not loc_obj or not isinstance(loc_obj, dict): 
                    continue
                
                slot_index = loc_obj.get('SlotIndex')
                target_idx = -1
                
                if slot_index is not None and 0 <= slot_index < 3: 
                    target_idx = slot_index
                elif slot_index is None and unassigned_idx_counter < 3: 
                    target_idx = unassigned_idx_counter
                    unassigned_idx_counter += 1
                
                if 0 <= target_idx < 3: 
                    processed_locations[target_idx] = {
                        "name": loc_obj.get('LocationDefId', f'Loc {target_idx+1}'), 
                        "p1_power": loc_obj.get('CurPlayer1Power', '?'), 
                        "p2_power": loc_obj.get('CurPlayer2Power', '?'), 
                        "slot_index": target_idx, 
                        "_player1Cards_data_ref": loc_obj.get('_player1Cards', []), 
                        "_player2Cards_data_ref": loc_obj.get('_player2Cards', [])
                    }
            
            gd["locations"] = processed_locations
            
            # Process local player data
            local_player_data = player_map.get(local_player_entity_id)
            if local_player_data and isinstance(local_player_data, dict):
                player_info_obj = resolve_ref(local_player_data.get("PlayerInfo", {}), id_map)
                lp_info["name"] = player_info_obj.get("Name", "Local Player") if isinstance(player_info_obj, dict) else "Local Player"
                lp_info["energy"] = f"{resolve_ref(local_player_data.get('CurrentEnergy'),id_map)}/{resolve_ref(local_player_data.get('MaxEnergy'),id_map)}"
                
                live_deck_obj_ref = local_player_data.get('Deck', {})
                live_deck_obj = resolve_ref(live_deck_obj_ref, id_map)
                lp_info["deck_count"] = len(live_deck_obj.get('_cards', [])) if live_deck_obj and isinstance(live_deck_obj, dict) else 0
                
                lp_hand_card_defs = extract_cards_with_details(local_player_data.get('Hand'), id_map, return_card_def_ids_only=True)
                lp_info["hand"] = extract_cards_with_details(local_player_data.get('Hand'), id_map, include_cost=True, card_db=card_db)
                
                lp_graveyard_card_defs = extract_cards_with_details(local_player_data.get('Graveyard'), id_map, return_card_def_ids_only=True)
                lp_info["graveyard"] = extract_cards_with_details(local_player_data.get('Graveyard'), id_map, card_db=card_db)
                
                lp_banished_card_defs = extract_cards_with_details(local_player_data.get('Banished'), id_map, return_card_def_ids_only=True)
                lp_info["banished"] = extract_cards_with_details(local_player_data.get('Banished'), id_map, card_db=card_db)
                
                lp_board_card_defs_flat = []
                for i in range(3):
                    loc_detail = gd["locations"][i]
                    if loc_detail and isinstance(loc_detail, dict):
                        cards_key = '_player1Cards_data_ref' if gd["local_is_gamelogic_player1"] else '_player2Cards_data_ref'
                        board_cards_loc_defs = extract_cards_with_details(
                            {"_cards": loc_detail.get(cards_key, [])}, 
                            id_map, 
                            return_card_def_ids_only=True
                        )
                        lp_board_card_defs_flat.extend(board_cards_loc_defs)
                        lp_info["board"][i] = extract_cards_with_details(
                            {"_cards": loc_detail.get(cards_key, [])}, 
                            id_map, 
                            include_power=True,
                            card_db=card_db
                        )
                
                # Calculate remaining deck
                if initial_deck_for_current_game:
                    cards_out_of_deck = lp_hand_card_defs + lp_board_card_defs_flat + lp_graveyard_card_defs + lp_banished_card_defs
                    remaining_deck_counter = Counter(initial_deck_for_current_game)
                    
                    for card_def_id in cards_out_of_deck:
                        if card_def_id in remaining_deck_counter and remaining_deck_counter[card_def_id] > 0:
                            remaining_deck_counter[card_def_id] -= 1
                    
                    final_remaining_list = []
                    [final_remaining_list.extend([card_def_id] * count) for card_def_id, count in remaining_deck_counter.items()]
                    lp_info["remaining_deck_list"] = sorted(final_remaining_list)
            
            # Process opponent data
            opponent_player_data = player_map.get(enemy_player_entity_id) if enemy_player_entity_id else None
            op_info = game_info["opponent"]
            
            if opponent_player_data and isinstance(opponent_player_data, dict):
                opp_player_info_obj = resolve_ref(opponent_player_data.get("PlayerInfo", {}), id_map)
                op_info["name"] = opp_player_info_obj.get("Name", "Opponent") if isinstance(opp_player_info_obj, dict) else "Opponent"
                op_info["energy"] = f"{resolve_ref(opponent_player_data.get('CurrentEnergy'),id_map)}/{resolve_ref(opponent_player_data.get('MaxEnergy'),id_map)}"
                
                opp_hand_data = resolve_ref(opponent_player_data.get('Hand', {}), id_map)
                op_info["hand_count"] = len(opp_hand_data.get('_cards', [])) if opp_hand_data and isinstance(opp_hand_data, dict) else 0
                
                op_info["graveyard"] = extract_cards_with_details(opponent_player_data.get('Graveyard'), id_map, card_db=card_db)
                op_info["banished"] = extract_cards_with_details(opponent_player_data.get('Banished'), id_map, card_db=card_db)
                
                for i in range(3):
                    loc_detail = gd["locations"][i]
                    if loc_detail and isinstance(loc_detail, dict): 
                        cards_key = '_player2Cards_data_ref' if gd["local_is_gamelogic_player1"] else '_player1Cards_data_ref'
                        op_info["board"][i] = extract_cards_with_details(
                            {"_cards": loc_detail.get(cards_key, [])}, 
                            id_map, 
                            include_power=True,
                            card_db=card_db
                        )
            
            # Process end game data (ClientResultMessage)
            client_result_message_ref = game_logic_state.get('ClientResultMessage')
            client_result_message = resolve_ref(client_result_message_ref, id_map)
            
            if client_result_message and isinstance(client_result_message, dict):
                is_battle_mode_game = client_result_message.get('IsBattleMode', False) 
                
                if is_battle_mode_game:
                    print(f"INFO: Game {game_id_from_crm or 'UnknownCRM_BattleGame'} is Battle Mode (Conquest). Skipping recording.")
                    self.log_error(f"Skipped recording Battle Mode game: {game_id_from_crm}", "")
                    # Do NOT populate game_info['end_game_data']
                    # Any events logged for this game_id in self.current_game_events will eventually be cleared
                    # or ignored since no match result is recorded.
                else:
                    end_data = {}
                    end_data['game_id'] = client_result_message.get('GameId')
                    
                    if end_data['game_id']: # Ensure game_id is present in end_game_data
                        end_data['turns_taken'] = client_result_message.get('TurnsTaken')
                        end_data['locations_at_end'] = client_result_message.get('LocationDefIdsAtEndOfGame', [])
                        
                        local_player_result_item = None
                        for item_ref in client_result_message.get('GameResultAccountItems', []):
                            item = resolve_ref(item_ref, id_map)
                            if item and isinstance(item, dict) and item.get('AccountId') == local_account_id_from_client: 
                                local_player_result_item = item
                                break
                        
                        if local_player_result_item:
                            end_data['cubes_changed'] = local_player_result_item.get('CurrencyRewardEarned')
                            
                            card_def_ids_drawn_at_end_refs = local_player_result_item.get('CardDefIdsDrawn', [])
                            card_def_ids_played_at_end_refs = local_player_result_item.get('CardDefIdsPlayed', [])
                            
                            end_data['card_def_ids_drawn_at_end'] = [
                                resolve_ref(card_ref, id_map) for card_ref in card_def_ids_drawn_at_end_refs
                                if resolve_ref(card_ref, id_map) # Ensure resolved value is not None
                            ]
                            end_data['card_def_ids_played_at_end'] = [
                                resolve_ref(card_ref, id_map) for card_ref in card_def_ids_played_at_end_refs
                                if resolve_ref(card_ref, id_map) # Ensure resolved value is not None
                            ]
                            end_data['card_def_ids_drawn_at_end'] = [cid for cid in end_data['card_def_ids_drawn_at_end'] if cid and cid != "None"]
                            end_data['card_def_ids_played_at_end'] = [cid for cid in end_data['card_def_ids_played_at_end'] if cid and cid != "None"]
                            
                            is_loser = local_player_result_item.get('IsLoser', False)
                            
                            if end_data['cubes_changed'] is not None:
                                if end_data['cubes_changed'] > 0: 
                                    end_data['result'] = 'win'
                                elif end_data['cubes_changed'] < 0: 
                                    end_data['result'] = 'loss'
                                else: 
                                    end_data['result'] = 'tie' # Or could be 'unknown' if cubes can be 0 for other reasons
                            else: # Fallback if cubes_changed is None
                                end_data['result'] = 'loss' if is_loser else 'win' # Or 'tie' if neither explicitly
                            
                            # Get deck info
                            deck_info_at_game_end_ref = local_player_result_item.get('Deck')
                            deck_info_at_game_end = resolve_ref(deck_info_at_game_end_ref, id_map)
                            
                            if deck_info_at_game_end and isinstance(deck_info_at_game_end, dict):
                                end_data['deck_name_from_gamestate'] = deck_info_at_game_end.get('Name')
                                cards_container_in_result_deck_ref = deck_info_at_game_end.get('Cards')
                                cards_container_in_result_deck = resolve_ref(cards_container_in_result_deck_ref, id_map)
                                result_deck_card_defs = []
                                
                                actual_card_list = None
                                if cards_container_in_result_deck and isinstance(cards_container_in_result_deck, dict) and '$values' in cards_container_in_result_deck:
                                    actual_card_list = cards_container_in_result_deck['$values']
                                elif cards_container_in_result_deck and isinstance(cards_container_in_result_deck, list):
                                    actual_card_list = cards_container_in_result_deck
                                
                                if actual_card_list:
                                    for card_ref_item in actual_card_list:
                                        card_obj_item = resolve_ref(card_ref_item, id_map)
                                        if card_obj_item and isinstance(card_obj_item, dict) and card_obj_item.get('CardDefId'): 
                                            result_deck_card_defs.append(card_obj_item.get('CardDefId'))
                                
                                end_data['deck_card_ids_from_gamestate'] = result_deck_card_defs
                            
                            end_data['local_player_name'] = lp_info.get("name", "You")
                            end_data['opponent_player_name'] = game_info["opponent"].get("name", "Opponent")
                            
                            # Get opponent revealed cards
                            opp_revealed_cards = set()
                            if opponent_player_data and game_logic_state and isinstance(game_logic_state, dict) and 'locations' in gd:
                                for loc_idx in range(3):
                                    loc_detail_for_opp_cards = gd["locations"][loc_idx]
                                    if loc_detail_for_opp_cards and isinstance(loc_detail_for_opp_cards, dict):
                                        opp_cards_key = '_player2Cards_data_ref' if gd["local_is_gamelogic_player1"] else '_player1Cards_data_ref'
                                        opp_card_refs_on_loc = loc_detail_for_opp_cards.get(opp_cards_key, [])
                                        
                                        for card_ref in opp_card_refs_on_loc:
                                            card_obj = resolve_ref(card_ref, id_map)
                                            if card_obj and isinstance(card_obj, dict) and card_obj.get('Revealed') and card_obj.get('CardDefId'): 
                                                opp_revealed_cards.add(card_obj['CardDefId'])
                            
                            end_data['opponent_revealed_cards_at_end'] = list(opp_revealed_cards)
                            
                            # Store in game_info
                            game_info['end_game_data'] = end_data
        else: 
            game_info["error"] = (game_info.get("error") or "") + " GameState (logic) missing. "
            
    except Exception as e:
        current_error = game_info.get("error", "") or ""
        game_info["error"] = current_error + f" EXCEPTION: {str(e)[:100]}... "
        game_info["full_error"] = traceback.format_exc()
    
    return game_info

def export_match_history_to_csv(filename, deck_filter=None):
    """Export match history to CSV file"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    query = """
        SELECT 
            m.game_id, m.timestamp_ended, COALESCE(d.deck_name, 'Unknown Deck'), 
            m.opponent_player_name, m.result, m.cubes_changed, m.turns_taken,
            m.loc_1_def_id, m.loc_2_def_id, m.loc_3_def_id,
            m.snap_turn_player, m.snap_turn_opponent, m.final_snap_state,
            m.opp_revealed_cards_json, d.card_ids_json, m.season, m.rank, m.notes
        FROM 
            matches m
        LEFT JOIN 
            decks d ON m.deck_id = d.id
    """
    
    params = []
    if deck_filter and deck_filter != "All Decks":
        query += " WHERE d.deck_name = ?"
        params.append(deck_filter)
    
    query += " ORDER BY m.timestamp_ended DESC"
    
    cursor.execute(query, tuple(params))
    matches = cursor.fetchall()
    
    # Write to CSV
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        # Write header
        writer.writerow([
            'Game ID', 'Timestamp', 'Deck Name', 'Opponent', 'Result', 'Cubes',
            'Turns', 'Location 1', 'Location 2', 'Location 3',
            'Your Snap Turn', 'Opponent Snap Turn', 'Final Snap State',
            'Opponent Revealed Cards', 'Your Deck Cards', 'Season', 'Rank', 'Notes'
        ])
        
        # Write data
        for match in matches:
            writer.writerow(match)
    
    conn.close()
    return len(matches)

def import_match_history_from_csv(filename, card_db=None):
    """Import match history from CSV file"""
    if not os.path.exists(filename):
        return (False, "File not found")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        with open(filename, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            header = next(reader)  # Skip header
            
            imported_count = 0
            skipped_count = 0
            
            for row in reader:
                if len(row) < 15:  # Make sure we have the minimum required fields
                    skipped_count += 1
                    continue
                
                game_id = row[0]
                
                # Check if match already exists
                cursor.execute("SELECT 1 FROM matches WHERE game_id = ?", (game_id,))
                if cursor.fetchone():
                    skipped_count += 1
                    continue
                
                # Get deck ID or create new one
                deck_name = row[2]
                deck_cards_json = row[14]
                
                try:
                    deck_cards = json.loads(deck_cards_json)
                except (json.JSONDecodeError, TypeError):
                    deck_cards = []
                
                deck_id = get_or_create_deck_id(deck_cards, None, deck_name, card_db)
                
                # Insert match
                cursor.execute("""
                    INSERT INTO matches (
                        game_id, timestamp_ended, local_player_name, opponent_player_name, 
                        deck_id, result, cubes_changed, turns_taken,
                        loc_1_def_id, loc_2_def_id, loc_3_def_id, 
                        snap_turn_player, snap_turn_opponent, final_snap_state,
                        opp_revealed_cards_json, season, rank, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    game_id, row[1], "You", row[3], 
                    deck_id, row[4], int(row[5]) if row[5] and row[5].strip() and row[5].strip() != '?' else None, 
                    int(row[6]) if row[6] and row[6].strip() and row[6].strip() != '?' else None,
                    row[7], row[8], row[9], 
                    int(row[10]) if row[10] and row[10].strip() and row[10].strip() != '?' else 0, 
                    int(row[11]) if row[11] and row[11].strip() and row[11].strip() != '?' else 0, 
                    row[12], row[13],
                    row[15] if len(row) > 15 else None, 
                    row[16] if len(row) > 16 else None,
                    row[17] if len(row) > 17 else None
                ))
                
                imported_count += 1
            
            conn.commit()
            conn.close()
            
            return (True, f"Imported {imported_count} matches successfully. Skipped {skipped_count} duplicates.")
    
    except Exception as e:
        conn.rollback()
        conn.close()
        return (False, f"Error importing matches: {str(e)}")

def check_for_updates():
    """Check for updates to the application (placeholder)"""
    # This is a placeholder. In a real implementation, you would:
    # 1. Check a repository or website for the latest version
    # 2. Compare with the current version
    # 3. Offer to download and install if an update is available
    return False, VERSION

def calculate_win_rate_over_time(deck_names_set=None, opponent_name=None, days=30):
    """Calculate win rate over time for charting"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    query = """
        SELECT 
            date(m.timestamp_ended) as match_date,
            COUNT(*) as total_matches,
            SUM(CASE WHEN m.result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(m.cubes_changed) as net_cubes
        FROM 
            matches m
        LEFT JOIN 
            decks d ON m.deck_id = d.id
        WHERE 
            m.timestamp_ended >= date('now', ?)
    """
    
    params = [f'-{days} days'] if days else ['-3650 days']  # Default to ~10 years if "All"
    
    if deck_names_set: # If not None and not empty
        placeholders = ', '.join(['?'] * len(deck_names_set))
        query += f" AND d.deck_name IN ({placeholders})"
        params.extend(list(deck_names_set))
    
    if opponent_name and opponent_name != "All Opponents":
        query += " AND m.opponent_player_name = ?"
        params.append(opponent_name)
    
    query += " GROUP BY match_date ORDER BY match_date"
    
    cursor.execute(query, tuple(params))
    results = cursor.fetchall()
    
    dates = []
    win_rates = []
    net_cubes_daily = []
    
    for row in results:
        dates.append(row[0]) # match_date
        total_daily_matches = row[1]
        daily_wins = row[2]
        daily_net_cubes = row[3]

        win_rate = (daily_wins / total_daily_matches * 100) if total_daily_matches > 0 else 0
        win_rates.append(win_rate)
        net_cubes_daily.append(daily_net_cubes if daily_net_cubes is not None else 0)
    
    conn.close()
    
    return dates, win_rates, net_cubes_daily


def calculate_matchup_statistics(deck_id=None):
    """Calculate statistics for deck vs opponent matchups"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Base query to get opponent matchup data
    query = """
        SELECT 
            m.opponent_player_name,
            COUNT(*) as matches,
            SUM(CASE WHEN m.result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN m.result = 'loss' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN m.result = 'tie' THEN 1 ELSE 0 END) as ties,
            SUM(m.cubes_changed) as net_cubes,
            GROUP_CONCAT(m.opp_revealed_cards_json, '|') as all_revealed_cards
        FROM 
            matches m
        WHERE 
            m.opponent_player_name IS NOT NULL
            AND m.opponent_player_name != 'Opponent'
    """
    
    params = []
    
    if deck_id and deck_id != "all":
        query += " AND m.deck_id = ?"
        params.append(deck_id)
    
    query += " GROUP BY m.opponent_player_name ORDER BY matches DESC, wins DESC"
    
    cursor.execute(query, tuple(params))
    opponent_data = cursor.fetchall()
    
    matchup_stats = []
    
    for opponent in opponent_data:
        name, matches, wins, losses, ties, net_cubes, all_revealed_cards = opponent
        win_rate = (wins / matches * 100) if matches > 0 else 0
        
        # Process revealed cards to find most common cards
        all_card_lists = []
        
        if all_revealed_cards:
            card_lists = all_revealed_cards.split('|')
            for card_list_json in card_lists:
                if card_list_json and card_list_json.lower() != 'null':
                    try:
                        card_list = json.loads(card_list_json)
                        if card_list:
                            all_card_lists.extend(card_list)
                    except json.JSONDecodeError:
                        pass
        
        # Count most frequent cards
        card_counter = Counter(all_card_lists)
        most_common_cards = card_counter.most_common(5)
        
        matchup_stats.append({
            'opponent': name,
            'matches': matches,
            'wins': wins,
            'losses': losses,
            'ties': ties,
            'win_rate': win_rate,
            'net_cubes': net_cubes if net_cubes is not None else 0,
            'avg_cubes': (net_cubes / matches) if matches > 0 and net_cubes is not None else 0,
            'most_common_cards': most_common_cards
        })
    
    conn.close()
    return matchup_stats

class CardTooltip:
    """Tooltip widget for displaying card information"""
    def __init__(self, parent, card_db):
        self.parent = parent
        self.card_db = card_db
        self.tooltip_window = None
        self.current_card_id = None
        self.x_offset = 20
        self.y_offset = 10
        self.delay = 500  # ms
        self.timer_id = None
    
    def show_tooltip(self, card_id, event=None):
        """Schedule tooltip to be shown after delay"""
        self.current_card_id = card_id
        
        if self.timer_id:
            self.parent.after_cancel(self.timer_id)
            
        self.timer_id = self.parent.after(self.delay, lambda: self._show_tooltip(card_id, event))
    
    def _show_tooltip(self, card_id, event):
        """Actually show the tooltip"""
        if card_id != self.current_card_id:
            return
        
        self.hide_tooltip()
        
        x = self.parent.winfo_pointerx() + self.x_offset
        y = self.parent.winfo_pointery() + self.y_offset
        
        # Create tooltip window
        self.tooltip_window = tk.Toplevel(self.parent)
        self.tooltip_window.wm_overrideredirect(True)  # No window decorations
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        
        # Apply theme colors
        config = get_config()
        colors = config['Colors']
        
        # Create content frame
        frame = ttk.Frame(self.tooltip_window, relief="solid", borderwidth=1)
        frame.pack(fill="both", expand=True)
        
        # Get tooltip text
        tooltip_text = get_card_tooltip_text(card_id, self.card_db)
        
        # Try to get card image
        image_path = None
        if self.card_db and card_id in self.card_db:
            image_path = download_card_image(card_id, self.card_db)
        
        # If we have an image, show it
        if image_path and os.path.exists(image_path):
            try:
                pil_image = Image.open(image_path)
                
                # Resize image while maintaining aspect ratio
                width, height = pil_image.size
                max_width = 200
                max_height = 280
                
                if width > max_width or height > max_height:
                    ratio = min(max_width / width, max_height / height)
                    new_width = int(width * ratio)
                    new_height = int(height * ratio)
                    pil_image = pil_image.resize((new_width, new_height), Image.LANCZOS)
                
                photo_image = ImageTk.PhotoImage(pil_image)
                
                # Create and place image label
                image_label = ttk.Label(frame, image=photo_image)
                image_label.image = photo_image  # Keep a reference
                image_label.pack(pady=5, padx=5)
            except Exception as e:
                print(f"Error showing card image: {e}")
        
        # Add text label
        text_label = ttk.Label(frame, text=tooltip_text, justify="left", wraplength=250)
        text_label.pack(pady=5, padx=10)
        
        # Configure colors
        frame.configure(style="TFrame")
        text_label.configure(style="TLabel")
        
        # Make sure tooltip fits on screen
        self.tooltip_window.update_idletasks()
        tooltip_width = self.tooltip_window.winfo_width()
        tooltip_height = self.tooltip_window.winfo_height()
        
        screen_width = self.parent.winfo_screenwidth()
        screen_height = self.parent.winfo_screenheight()
        
        # Adjust position if tooltip would go off screen
        if x + tooltip_width > screen_width:
            x = screen_width - tooltip_width
        
        if y + tooltip_height > screen_height:
            y = screen_height - tooltip_height
        
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
    
    def hide_tooltip(self):
        """Hide the tooltip"""
        if self.timer_id:
            self.parent.after_cancel(self.timer_id)
            self.timer_id = None
            
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

class SnapTrackerApp:
    def __init__(self, root_window):
        self.root = root_window
        self.root.title(f"Marvel Snap Tracker v{VERSION}")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        
        # Initialize database
        init_db()
        
        # Load configuration
        self.config = get_config()
        
        # Apply theme
        apply_theme(self.root)
        
        # Load card database
        self.card_db = load_card_database()
        
        if self.card_db:
            threading.Thread(target=self.download_all_card_images, daemon=True).start()
        
        # Initialize state variables
        self.last_recorded_game_id = None
        self.deck_collection_map = {}
        self.current_game_events = {}
        self.game_state_file_path = None
        self.last_error_displayed_short = ""
        self.last_error_displayed_full = ""
        self.current_game_id_for_deck_tracker = None
        self.initial_deck_cards_for_current_game = []
        self.playstate_deck_id_last_seen = None
        self.playstate_read_attempt_count = 0
        
        # Set up tooltip handler
        self.card_tooltip = CardTooltip(self.root, self.card_db)
        
        # Create stringvars for UI
        self.setup_string_vars()
        
        # Setup UI components
        self.setup_ui()
        
        self.create_deck_stats_modal() # This should be created early
        
        # Check for updates
        if self.config.getboolean('Settings', 'check_for_app_updates'):
            self.check_for_updates_command() 
        
        # Start background processes
        self.update_deck_collection_cache()
        self.update_data_loop()
        
        # Load data for history and stats tabs
        self.load_history_tab_data() # This populates deck filter options
        self.load_card_stats_data()
        self.load_matchup_data()
        self.load_location_stats()
        self.load_deck_performance_data() # New call
        self.update_trends() # Initial trend load
        
        # Create and configure main menu
        self.create_main_menu()
        
        print(f"Marvel Snap Tracker v{VERSION} initialized")

    def setup_string_vars(self):
        """Initialize all string variables used in the UI"""
        # Status variables
        self.status_var = tk.StringVar(value="Initializing...")
        self.turn_var = tk.StringVar(value="Turn: N/A")
        self.cubes_var = tk.StringVar(value="Cubes: N/A")
        
        # Location variables
        self.location_vars = [
            {
                "name": tk.StringVar(value=f"Loc {i+1}: ---"), 
                "power": tk.StringVar(value="P: ?-?"), 
                "local_cards": tk.StringVar(value=" \n \n "), 
                "opp_cards": tk.StringVar(value=" \n \n ")
            } for i in range(3)
        ]
        
        # Local player variables
        self.local_player_name_var = tk.StringVar(value="You")
        self.local_energy_var = tk.StringVar(value="Energy: ?/?")
        self.local_hand_var = tk.StringVar(value="Hand: Empty")
        self.local_deck_var = tk.StringVar(value="Deck: ?")
        self.local_graveyard_var = tk.StringVar(value="Destroyed: Empty")
        self.local_banished_var = tk.StringVar(value="Banished: Empty")
        self.local_remaining_deck_var = tk.StringVar(value="Deck (Remaining): N/A")
        self.local_snap_status_var = tk.StringVar(value="Snap: N/A")
        
        # Opponent variables
        self.opponent_name_var = tk.StringVar(value="Opponent")
        self.opponent_energy_var = tk.StringVar(value="Energy: ?/?")
        self.opponent_hand_var = tk.StringVar(value="Hand: ? cards")
        self.opponent_graveyard_var = tk.StringVar(value="Destroyed: Empty")
        self.opponent_banished_var = tk.StringVar(value="Banished: Empty")
        self.opponent_snap_status_var = tk.StringVar(value="Snap: N/A")
        self.last_encounter_opponent_name_var = tk.StringVar(value="N/A")
        
        # Filter variables
        #self.history_deck_filter_var = tk.StringVar(value="All Decks")

        self.history_selected_deck_names = set() # Store selected deck names
        self.history_deck_filter_display_var = tk.StringVar(value="Decks: All") # For display
        
        self.history_deck_options = ["All Decks"]
        #self.card_stats_deck_filter_var = tk.StringVar(value="All Decks")
        self.card_stats_selected_deck_names = set()
        self.card_stats_deck_filter_display_var = tk.StringVar(value="Decks: All")        
        self.card_stats_summary_var = tk.StringVar(value="Select a deck to see card stats.")
        self.location_stats_filter_var = tk.StringVar(value="All Locations")
        self.location_selected_deck_names = set()
        self.location_deck_filter_display_var = tk.StringVar(value="Decks: All")
        
        self.opponent_stats_filter_var = tk.StringVar(value="All Opponents")
        self.matchup_selected_deck_names = set()
        self.matchup_deck_filter_display_var = tk.StringVar(value="Decks: All")
        
        self.trend_days_var = tk.StringVar(value="30")
        self.trend_selected_deck_names = set()
        self.trend_deck_filter_display_var = tk.StringVar(value="Decks: All")


        self.all_deck_names_for_filter = [] # To populate the selection dialog
        
         # New filter var for Deck Performance Tab
        self.deck_performance_season_filter_var = tk.StringVar(value="All Seasons")
        
        # Widgets that will be created later
        self.error_log_text = None
        self.history_tree = None
        self.stats_text_widget = None
        self.card_stats_tree = None
        self.opponent_encounter_history_text = None
        self.trends_canvas = None
        self.matchup_tree = None
        self.location_stats_tree = None
        self.deck_performance_tree = None # For the new tab's treeview

    def setup_ui(self):
        """Set up the main UI components"""
        # Create main notebook
        main_notebook = ttk.Notebook(self.root)
        
        # Create tabs
        live_game_tab = ttk.Frame(main_notebook, padding="10")
        history_tab = ttk.Frame(main_notebook, padding="10")
        deck_performance_tab = ttk.Frame(main_notebook, padding="10") # New Tab
        card_stats_tab = ttk.Frame(main_notebook, padding="10")
        matchup_tab = ttk.Frame(main_notebook, padding="10")
        location_tab = ttk.Frame(main_notebook, padding="10")
        trends_tab = ttk.Frame(main_notebook, padding="10")
        settings_tab = ttk.Frame(main_notebook, padding="10")
        
        # Add tabs to notebook
        main_notebook.add(live_game_tab, text="Live Game")
        main_notebook.add(history_tab, text="Match History")
        main_notebook.add(deck_performance_tab, text="Deck Performance") # New Tab
        main_notebook.add(card_stats_tab, text="Card Stats")
        main_notebook.add(matchup_tab, text="Matchups")
        main_notebook.add(location_tab, text="Locations")
        main_notebook.add(trends_tab, text="Trends")
        main_notebook.add(settings_tab, text="Settings")
        
        # Set up each tab
        ui_tabs._setup_live_game_ui(self, live_game_tab)
        ui_tabs._setup_history_ui(self, history_tab)
        ui_tabs._setup_deck_performance_ui(self, deck_performance_tab) # New setup call
        ui_tabs._setup_card_stats_ui(self, card_stats_tab)
        ui_tabs._setup_matchup_ui(self, matchup_tab) # Changed
        ui_tabs._setup_location_stats_ui(self, location_tab) # Changed
        self._setup_trends_ui(trends_tab)
        self._setup_settings_ui(settings_tab)
        
        # Pack the notebook
        main_notebook.pack(expand=True, fill=tk.BOTH)

    def create_main_menu(self):
        """Create the application menu bar"""
        menubar = tk.Menu(self.root)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Export Match History...", command=self.export_match_history)
        file_menu.add_command(label="Import Match History...", command=self.import_match_history)
        file_menu.add_separator()
        file_menu.add_command(label="Backup Database...", command=self.backup_database)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Settings", command=lambda: self.show_settings_dialog()) # Points to Settings tab
        menubar.add_cascade(label="Edit", menu=edit_menu)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Refresh Data", command=self.refresh_all_data)
        view_menu.add_separator()
        view_menu.add_command(label="Light Theme", command=lambda: self.change_theme("light"))
        view_menu.add_command(label="Dark Theme (Default)", command=lambda: self.change_theme("dark"))
        view_menu.add_command(label="Custom Theme...", command=self.customize_theme)
        menubar.add_cascade(label="View", menu=view_menu)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Update Card Database (API)", command=self.update_card_db_command)
        tools_menu.add_command(label="Import Card Database (File)", command=self.import_card_db_file_command)

        db_menu = tk.Menu(tools_menu, tearoff=0)
        db_menu.add_command(label="Backup Database", command=self.backup_database)
        db_menu.add_command(label="Clean Duplicate Events", command=self.cleanup_duplicate_events_command)
        db_menu.add_command(label="Reset Database", command=self.reset_database)
        tools_menu.add_cascade(label="Database", menu=db_menu)
        
        tools_menu.add_separator()
        tools_menu.add_command(label="Check for App Updates", command=self.check_for_updates_command)
        tools_menu.add_separator()
        tools_menu.add_command(label="Open Card Images Folder", command=lambda: self.open_folder(CARD_IMAGES_DIR))
        tools_menu.add_command(label="Open Tracker Data Folder", command=lambda: self.open_folder(os.path.dirname(os.path.abspath(__file__))))
        menubar.add_cascade(label="Tools", menu=tools_menu)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about_dialog)
        help_menu.add_command(label="Visit Marvel Snap Zone", command=lambda: webbrowser.open("https://marvelsnapzone.com"))
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.root.config(menu=menubar)

        
    
    def show_history_deck_filter_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Select Decks for History Filter")
        dialog.geometry("400x550") # Increased default height
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(background=self.config['Colors']['bg_main'])

        # --- Define apply_selection and other local functions FIRST ---
        # They need to be defined before they are used as commands for buttons
        # And they need access to temp_vars and all_decks_var which are defined later in this scope.
        # This requires a bit of restructuring or passing them around.
        # For simplicity, let's define them, and then ensure variables are in scope.

        # Placeholder for temp_vars and all_decks_var, will be properly initialized later
        # This is a common pattern if functions need to be defined before all their data.
        _dialog_data = {'temp_vars': {}, 'all_decks_var': None}


        def apply_selection_command(): # Renamed to avoid conflict with a potential future instance method
            # Access variables through the _dialog_data dictionary
            all_decks_var_local = _dialog_data['all_decks_var']
            temp_vars_local = _dialog_data['temp_vars']

            print(f"DEBUG: apply_selection_command called. 'All Decks' var: {all_decks_var_local.get()}")
            
            selected_in_dialog = set()
            for deck_name, var in temp_vars_local.items():
                if deck_name != "ALL" and var.get(): 
                    selected_in_dialog.add(deck_name)
            print(f"DEBUG: Decks selected in dialog (before processing 'All Decks'): {selected_in_dialog}")
            
            if all_decks_var_local.get(): 
                self.history_selected_deck_names.clear()
                self.history_deck_filter_display_var.set("Decks: All")
                print("DEBUG: 'All Decks' is selected, clearing specific deck selections.")
            else: 
                self.history_selected_deck_names.clear() 
                self.history_selected_deck_names.update(selected_in_dialog) 

                if not self.history_selected_deck_names: 
                    self.history_selected_deck_names.clear() 
                    self.history_deck_filter_display_var.set("Decks: All")
                    print("DEBUG: No individual decks selected, defaulting to 'All Decks'.")
                elif len(self.history_selected_deck_names) <= 3:
                    display_text = f"Decks: {', '.join(sorted(list(self.history_selected_deck_names)))}"
                    self.history_deck_filter_display_var.set(display_text)
                    print(f"DEBUG: Selected specific decks (<=3): {display_text}")
                else:
                    display_text = f"Decks: {len(self.history_selected_deck_names)} selected"
                    self.history_deck_filter_display_var.set(display_text)
                    print(f"DEBUG: Selected specific decks (>3): {display_text}")
            
            print(f"DEBUG: Final self.history_selected_deck_names: {self.history_selected_deck_names}")
            dialog.destroy()
            self.apply_history_filter()


        def update_all_decks_checkbox_command(*args): # Renamed
            # Access variables through _dialog_data
            all_decks_var_local = _dialog_data['all_decks_var']
            temp_vars_local = _dialog_data['temp_vars']
            if all_decks_var_local is None: return # Not initialized yet

            an_individual_deck_is_checked = any(var.get() for name, var in temp_vars_local.items() if name != "ALL")
            
            if an_individual_deck_is_checked and all_decks_var_local.get():
                all_decks_var_local.set(False)
            elif not an_individual_deck_is_checked and not all_decks_var_local.get():
                 all_decks_var_local.set(True)
        

        def toggle_all_decks_command(): # Renamed
            # Access variables through _dialog_data
            all_decks_var_local = _dialog_data['all_decks_var']
            temp_vars_local = _dialog_data['temp_vars']

            if all_decks_var_local.get(): 
                for deck_name_key in temp_vars_local: # Iterate over keys
                    if deck_name_key != "ALL": 
                        temp_vars_local[deck_name_key].set(False)
            update_all_decks_checkbox_command() # Ensure consistency

        # --- UI Elements ---
        # Button Frame (defined early, packed late)
        button_frame = ttk.Frame(dialog)
        # Use the command functions defined above
        ttk.Button(button_frame, text="Apply", command=apply_selection_command).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

        # Scrollable Checkbox Area
        checkbox_area_frame = ttk.Frame(dialog)
        scroll_canvas = tk.Canvas(checkbox_area_frame, background=self.config['Colors']['bg_main'])
        scrollbar = ttk.Scrollbar(checkbox_area_frame, orient="vertical", command=scroll_canvas.yview)
        
        # *** THIS IS THE PARENT FOR CHECKBOXES ***
        checkbox_display_frame = ttk.Frame(scroll_canvas) 

        checkbox_display_frame.bind(
            "<Configure>",
            lambda e: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
        )
        scroll_canvas.create_window((0, 0), window=checkbox_display_frame, anchor="nw")
        scroll_canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # --- Populate checkboxes INTO checkbox_display_frame ---
        # temp_vars and all_decks_var are now correctly scoped for the command functions via _dialog_data
        _dialog_data['temp_vars'] = {} # Initialize fresh for this dialog

        # "All Decks" option
        # Initial value based on the app's persistent state
        initial_all_decks_state = not bool(self.history_selected_deck_names)
        all_decks_var_instance = tk.BooleanVar(value=initial_all_decks_state)
        _dialog_data['all_decks_var'] = all_decks_var_instance # Store in shared dict

        # *** Checkboxes parented to checkbox_display_frame ***
        all_cb = ttk.Checkbutton(checkbox_display_frame, text="All Decks", variable=all_decks_var_instance, command=toggle_all_decks_command)
        all_cb.pack(anchor="w", padx=10, pady=2)
        _dialog_data['temp_vars']["ALL"] = all_decks_var_instance # For logic in update_all_decks_checkbox_command

        ttk.Separator(checkbox_display_frame, orient='horizontal').pack(fill='x', pady=5)

        for deck_name in self.all_deck_names_for_filter:
            # Initial state of individual checkbox
            is_initially_checked = (deck_name in self.history_selected_deck_names) and not initial_all_decks_state
            var = tk.BooleanVar(value=is_initially_checked)
            
            # *** Checkboxes parented to checkbox_display_frame ***
            cb = ttk.Checkbutton(checkbox_display_frame, text=deck_name, variable=var)
            cb.pack(anchor="w", padx=10, pady=2)
            var.trace_add("write", update_all_decks_checkbox_command) 
            _dialog_data['temp_vars'][deck_name] = var
       
        # --- Pack main sections into dialog ---
        button_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=10, padx=10)
        checkbox_area_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Call once to set initial state correctly after all vars are set up
        update_all_decks_checkbox_command()
    
        
