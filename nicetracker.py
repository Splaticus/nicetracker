from db_utils import DB_NAME, init_db
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox, colorchooser
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
        self._setup_live_game_ui(live_game_tab)
        self._setup_history_ui(history_tab)
        self._setup_deck_performance_ui(deck_performance_tab) # New setup call
        self._setup_card_stats_ui(card_stats_tab)
        self._setup_matchup_ui(matchup_tab)
        self._setup_location_stats_ui(location_tab)
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

    def _setup_live_game_ui(self, parent_frame):
        """Set up the Live Game tab UI"""
        top_content_frame = ttk.Frame(parent_frame)
        top_content_frame.pack(expand=True, fill=tk.BOTH, side=tk.TOP)
        
        # Status bar at bottom
        status_bar = ttk.Label(parent_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(5,0))
        
        # Error log frame
        error_log_frame = ttk.LabelFrame(parent_frame, text="Error Log", padding="5")
        error_log_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(5,0), ipady=2)
        self.error_log_text = scrolledtext.ScrolledText(error_log_frame, height=4, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
        self.error_log_text.pack(expand=True, fill=tk.X)
        
        # Game details frame
        game_details_frame = ttk.LabelFrame(top_content_frame, text="Game Info", padding="5")
        game_details_frame.pack(pady=5, padx=5, fill=tk.X)
        ttk.Label(game_details_frame, textvariable=self.turn_var).pack(side=tk.LEFT, padx=5)
        ttk.Label(game_details_frame, textvariable=self.cubes_var).pack(side=tk.LEFT, padx=5)
        
        # Deck Stats Modal button
        self.deck_stats_button = ttk.Button( # Store as instance variable
            game_details_frame, # Parent is game_details_frame
            text="Deck Stats",
            command=self.show_deck_modal
        )
        self.deck_stats_button.pack(side=tk.RIGHT, padx=10) # Pack to the right of game_details_frame
        
        # Locations frame
        locations_outer_frame = ttk.LabelFrame(top_content_frame, text="Locations", padding="5")
        locations_outer_frame.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)
        locations_grid_frame = ttk.Frame(locations_outer_frame)
        locations_grid_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create location displays
        for i in range(3):
            loc_frame = ttk.Frame(locations_grid_frame, borderwidth=1, relief="groove")
            loc_frame.grid(row=0, column=i, padx=5, pady=2, sticky="nsew")
            locations_grid_frame.grid_columnconfigure(i, weight=1)
            locations_grid_frame.grid_rowconfigure(0, weight=1)
            
            # Location name and power
            ttk.Label(loc_frame, textvariable=self.location_vars[i]["name"], font=('Arial', 10, 'bold')).pack(pady=(2,2), anchor='n')
            ttk.Label(loc_frame, textvariable=self.location_vars[i]["power"]).pack(pady=(0,5), anchor='n')
            
            # Opponent cards subframe
            opp_cards_sub_frame = ttk.Frame(loc_frame)
            opp_cards_sub_frame.pack(fill=tk.BOTH, expand=True, pady=(0,2), ipady=2)
            ttk.Label(opp_cards_sub_frame, text="Opp Cards:", anchor="w", font=('Arial', 8, 'italic')).pack(fill=tk.X)
            opp_label = ttk.Label(opp_cards_sub_frame, textvariable=self.location_vars[i]["opp_cards"], 
                         wraplength=180, justify=tk.LEFT, anchor="nw", relief="sunken", 
                         borderwidth=1, padding=(2,5))
            opp_label.pack(fill=tk.BOTH, expand=True)
            opp_label.bind("<Enter>", lambda e, idx=i, player="opp": self.on_card_list_hover(e, idx, player))
            opp_label.bind("<Leave>", lambda e: self.card_tooltip.hide_tooltip())
            
            # Your cards subframe
            your_cards_sub_frame = ttk.Frame(loc_frame)
            your_cards_sub_frame.pack(fill=tk.BOTH, expand=True, pady=(2,0), ipady=2)
            ttk.Label(your_cards_sub_frame, text="Your Cards:", anchor="w", font=('Arial', 8, 'italic')).pack(fill=tk.X)
            local_label = ttk.Label(your_cards_sub_frame, textvariable=self.location_vars[i]["local_cards"], 
                          wraplength=180, justify=tk.LEFT, anchor="nw", relief="sunken", 
                          borderwidth=1, padding=(2,5))
            local_label.pack(fill=tk.BOTH, expand=True)
            local_label.bind("<Enter>", lambda e, idx=i, player="local": self.on_card_list_hover(e, idx, player))
            local_label.bind("<Leave>", lambda e: self.card_tooltip.hide_tooltip())
        
        # Player panels
        paned_window = ttk.PanedWindow(top_content_frame, orient=tk.HORIZONTAL)
        paned_window.pack(expand=True, fill=tk.BOTH, pady=5)
        
        # Local player frame
        local_player_frame = ttk.LabelFrame(paned_window, text="Local Player", padding="10")
        paned_window.add(local_player_frame, weight=1)
        
        ttk.Label(local_player_frame, textvariable=self.local_player_name_var, font=('Arial', 12, 'bold')).grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Label(local_player_frame, textvariable=self.local_energy_var).grid(row=1, column=0, sticky="w", pady=1)
        ttk.Label(local_player_frame, textvariable=self.local_snap_status_var).grid(row=1, column=1, sticky="w", pady=1, padx=(5,0))
        
        # Hand cards with tooltip
        ttk.Label(local_player_frame, text="Hand:").grid(row=2, column=0, sticky="nw", pady=2)
        hand_label = ttk.Label(local_player_frame, textvariable=self.local_hand_var, wraplength=280, justify=tk.LEFT)
        hand_label.grid(row=2, column=1, sticky="new", pady=2)
        hand_label.bind("<Enter>", lambda e, zone="hand": self.on_zone_hover(e, zone))
        hand_label.bind("<Leave>", lambda e: self.card_tooltip.hide_tooltip())
        
        # Deck count
        ttk.Label(local_player_frame, text="Deck:").grid(row=3, column=0, sticky="nw", pady=2)
        ttk.Label(local_player_frame, textvariable=self.local_deck_var).grid(row=3, column=1, sticky="new", pady=2)
        
        # Remaining deck with tooltip
        ttk.Label(local_player_frame, text="Remaining:").grid(row=4, column=0, sticky="nw", pady=2)
        remaining_label = ttk.Label(local_player_frame, textvariable=self.local_remaining_deck_var, wraplength=280, justify=tk.LEFT)
        remaining_label.grid(row=4, column=1, sticky="new", pady=2)
        remaining_label.bind("<Enter>", lambda e, zone="remaining": self.on_zone_hover(e, zone))
        remaining_label.bind("<Leave>", lambda e: self.card_tooltip.hide_tooltip())
        
        # Destroyed cards with tooltip
        ttk.Label(local_player_frame, text="Destroyed:").grid(row=5, column=0, sticky="nw", pady=2)
        graveyard_label = ttk.Label(local_player_frame, textvariable=self.local_graveyard_var, wraplength=280, justify=tk.LEFT)
        graveyard_label.grid(row=5, column=1, sticky="new", pady=2)
        graveyard_label.bind("<Enter>", lambda e, zone="graveyard": self.on_zone_hover(e, zone))
        graveyard_label.bind("<Leave>", lambda e: self.card_tooltip.hide_tooltip())
        
        # Banished cards with tooltip
        ttk.Label(local_player_frame, text="Banished:").grid(row=6, column=0, sticky="nw", pady=2)
        banished_label = ttk.Label(local_player_frame, textvariable=self.local_banished_var, wraplength=280, justify=tk.LEFT)
        banished_label.grid(row=6, column=1, sticky="new", pady=2)
        banished_label.bind("<Enter>", lambda e, zone="banished": self.on_zone_hover(e, zone))
        banished_label.bind("<Leave>", lambda e: self.card_tooltip.hide_tooltip())
        
        local_player_frame.grid_columnconfigure(1, weight=1)
        
        # Opponent frame
        opponent_frame = ttk.LabelFrame(paned_window, text="Opponent", padding="10")
        paned_window.add(opponent_frame, weight=1)
        
        ttk.Label(opponent_frame, textvariable=self.opponent_name_var, font=('Arial', 12, 'bold')).grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Label(opponent_frame, textvariable=self.opponent_energy_var).grid(row=1, column=0, sticky="w", pady=1)
        ttk.Label(opponent_frame, textvariable=self.opponent_snap_status_var).grid(row=1, column=1, sticky="w", pady=1, padx=(5,0))
        
        ttk.Label(opponent_frame, text="Hand:").grid(row=2, column=0, sticky="nw", pady=2)
        ttk.Label(opponent_frame, textvariable=self.opponent_hand_var).grid(row=2, column=1, sticky="new", pady=2)
        
        # Opponent destroyed cards with tooltip
        ttk.Label(opponent_frame, text="Destroyed:").grid(row=3, column=0, sticky="nw", pady=2)
        opp_graveyard_label = ttk.Label(opponent_frame, textvariable=self.opponent_graveyard_var, wraplength=280, justify=tk.LEFT)
        opp_graveyard_label.grid(row=3, column=1, sticky="new", pady=2)
        opp_graveyard_label.bind("<Enter>", lambda e, zone="opp_graveyard": self.on_zone_hover(e, zone))
        opp_graveyard_label.bind("<Leave>", lambda e: self.card_tooltip.hide_tooltip())
        
        # Opponent banished cards with tooltip
        ttk.Label(opponent_frame, text="Banished:").grid(row=4, column=0, sticky="nw", pady=2)
        opp_banished_label = ttk.Label(opponent_frame, textvariable=self.opponent_banished_var, wraplength=280, justify=tk.LEFT)
        opp_banished_label.grid(row=4, column=1, sticky="new", pady=2)
        opp_banished_label.bind("<Enter>", lambda e, zone="opp_banished": self.on_zone_hover(e, zone))
        opp_banished_label.bind("<Leave>", lambda e: self.card_tooltip.hide_tooltip())
        
        opponent_frame.grid_columnconfigure(1, weight=1)
        
        # Encounter history frame
        last_encounter_frame = ttk.LabelFrame(opponent_frame, text="Encounter History", padding="5")
        last_encounter_frame.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(10,0), padx=2)
        opponent_frame.grid_rowconfigure(5, weight=1)
        last_encounter_frame.grid_columnconfigure(1, weight=1)
        
        name_frame = ttk.Frame(last_encounter_frame)
        name_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=2)
        ttk.Label(name_frame, text="Opponent:").pack(side=tk.LEFT)
        ttk.Label(name_frame, textvariable=self.last_encounter_opponent_name_var).pack(side=tk.LEFT, padx=(5,0))
        
        self.opponent_encounter_history_text = scrolledtext.ScrolledText(
            last_encounter_frame, height=5, wrap=tk.WORD, state=tk.DISABLED,
            relief="sunken", borderwidth=1, font=("Arial", 8)
        )
        self.opponent_encounter_history_text.grid(row=1, column=0, columnspan=2, sticky="new", pady=(5,1), padx=2)
        last_encounter_frame.grid_rowconfigure(1, weight=1)
        
    def _create_deck_filter_dialog(self, title, all_deck_names_list, 
                                   selected_deck_names_set, display_var_stringvar, 
                                   apply_callback_func):
        """
        Generic helper to create a multi-select deck filter dialog.

        Args:
            title (str): The title for the dialog window.
            all_deck_names_list (list): List of all available deck names.
            selected_deck_names_set (set): The set to store/read selected deck names.
            display_var_stringvar (tk.StringVar): StringVar to update with filter status display.
            apply_callback_func (function): Function to call after applying the filter.
        """
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("400x550") 
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(background=self.config['Colors']['bg_main'])

        _dialog_data = {'temp_vars': {}, 'all_decks_var': None, '_block_individual_traces': False}

        def apply_selection_command():
            all_decks_var_local = _dialog_data['all_decks_var']
            temp_vars_local = _dialog_data['temp_vars']
            
            # Update the passed-in selected_deck_names_set
            selected_deck_names_set.clear() 

            if all_decks_var_local.get():
                display_var_stringvar.set("Decks: All")
            else:
                for deck_name, var in temp_vars_local.items():
                    if deck_name != "ALL" and var.get():
                        selected_deck_names_set.add(deck_name)
                
                if not selected_deck_names_set:
                    display_var_stringvar.set("Decks: All") 
                elif len(selected_deck_names_set) <= 3:
                    display_var_stringvar.set(f"Decks: {', '.join(sorted(list(selected_deck_names_set)))}")
                else:
                    display_var_stringvar.set(f"Decks: {len(selected_deck_names_set)} selected")
            
            dialog.destroy()
            if apply_callback_func:
                apply_callback_func()

        def on_individual_deck_toggle(*args):
            if _dialog_data['_block_individual_traces']: return
            
            all_decks_var_local = _dialog_data['all_decks_var']
            temp_vars_local = _dialog_data['temp_vars']
            if all_decks_var_local is None: return

            any_individual_selected = any(var.get() for name, var in temp_vars_local.items() if name != "ALL")
            
            if any_individual_selected:
                if all_decks_var_local.get(): all_decks_var_local.set(False)
            else:
                if not all_decks_var_local.get(): all_decks_var_local.set(True)

        def on_all_decks_toggle_command():
            all_decks_var_local = _dialog_data['all_decks_var']
            temp_vars_local = _dialog_data['temp_vars']
            if all_decks_var_local is None: return

            if all_decks_var_local.get():
                _dialog_data['_block_individual_traces'] = True
                for deck_name_key in temp_vars_local:
                    if deck_name_key != "ALL":
                        if temp_vars_local[deck_name_key].get():
                             temp_vars_local[deck_name_key].set(False)
                _dialog_data['_block_individual_traces'] = False
            on_individual_deck_toggle()


        button_frame = ttk.Frame(dialog)
        ttk.Button(button_frame, text="Apply", command=apply_selection_command).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

        checkbox_area_frame = ttk.Frame(dialog)
        scroll_canvas = tk.Canvas(checkbox_area_frame, background=self.config['Colors']['bg_main'])
        scrollbar = ttk.Scrollbar(checkbox_area_frame, orient="vertical", command=scroll_canvas.yview)
        checkbox_display_frame = ttk.Frame(scroll_canvas)

        checkbox_display_frame.bind(
            "<Configure>", lambda e: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
        )
        scroll_canvas.create_window((0, 0), window=checkbox_display_frame, anchor="nw")
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        _dialog_data['temp_vars'] = {}
        initial_all_decks_state = not bool(selected_deck_names_set) # Use passed-in set
        all_decks_var_instance = tk.BooleanVar(value=initial_all_decks_state)
        _dialog_data['all_decks_var'] = all_decks_var_instance

        all_cb = ttk.Checkbutton(checkbox_display_frame, text="All Decks", variable=all_decks_var_instance, command=on_all_decks_toggle_command)
        all_cb.pack(anchor="w", padx=10, pady=2)
        _dialog_data['temp_vars']["ALL"] = all_decks_var_instance

        ttk.Separator(checkbox_display_frame, orient='horizontal').pack(fill='x', pady=5)

        for deck_name_iter in all_deck_names_list: # Use passed-in list
            is_initially_checked = (deck_name_iter in selected_deck_names_set) and not initial_all_decks_state
            var = tk.BooleanVar(value=is_initially_checked)
            cb = ttk.Checkbutton(checkbox_display_frame, text=deck_name_iter, variable=var)
            cb.pack(anchor="w", padx=10, pady=2)
            var.trace_add("write", on_individual_deck_toggle)
            _dialog_data['temp_vars'][deck_name_iter] = var
        
        button_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=10, padx=10)
        checkbox_area_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        on_individual_deck_toggle() # Initial sync        
    
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
    
    def _setup_history_ui(self, parent_frame):
        """Set up the Match History tab UI"""
        # Filter frame
        filter_frame = ttk.Frame(parent_frame)
        filter_frame.pack(fill=tk.X, pady=5)
        
        # --- MODIFIED DECK FILTER ---
        self.deck_filter_button = ttk.Button(filter_frame, text="Filter Decks...", command=self.show_history_deck_filter_dialog)
        self.deck_filter_button.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(filter_frame, textvariable=self.history_deck_filter_display_var).pack(side=tk.LEFT, padx=5)
        # --- END MODIFIED DECK FILTER ---
        
        # ttk.Label(filter_frame, text="Filter by Deck:").pack(side=tk.LEFT, padx=(0,5))
        # self.deck_filter_menu = ttk.OptionMenu(
            # filter_frame, self.history_deck_filter_var, 
            # self.history_deck_options[0], *self.history_deck_options, 
            # command=self.apply_history_filter
        # )
        # self.deck_filter_menu.pack(side=tk.LEFT, padx=5)
        
        # Add more filter options
        ttk.Label(filter_frame, text="Season:").pack(side=tk.LEFT, padx=(20,5))
        self.season_filter_var = tk.StringVar(value="All Seasons")
        self.season_filter_menu = ttk.OptionMenu(
            filter_frame, self.season_filter_var, 
            "All Seasons", "All Seasons", 
            command=self.apply_history_filter
        )
        self.season_filter_menu.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(filter_frame, text="Result:").pack(side=tk.LEFT, padx=(20,5))
        self.result_filter_var = tk.StringVar(value="All Results")
        self.result_filter_menu = ttk.OptionMenu(
            filter_frame, self.result_filter_var, 
            "All Results", "All Results", "Win", "Loss", "Tie", 
            command=self.apply_history_filter
        )
        self.result_filter_menu.pack(side=tk.LEFT, padx=5)
        
        # Button frame
        button_frame = ttk.Frame(parent_frame)
        button_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(button_frame, text="Refresh History", command=self.load_history_tab_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Export Selected", command=self.export_selected_matches).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Add Note", command=self.add_match_note).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Delete Selected", command=self.delete_selected_matches).pack(side=tk.LEFT, padx=5)
        
        # Search box
        search_frame = ttk.Frame(button_frame)
        search_frame.pack(side=tk.RIGHT)
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0,5))
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *args: self.apply_history_filter())
        ttk.Entry(search_frame, textvariable=self.search_var, width=20).pack(side=tk.LEFT)
        
        # History list frame
        history_list_frame = ttk.LabelFrame(parent_frame, text="Matches", padding="5")
        history_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Create treeview with columns
        cols = ("Timestamp", "Deck", "Opponent", "Result", "Cubes", "Turns", "Location1", "Location2", "Location3")
        self.history_tree = ttk.Treeview(history_list_frame, columns=cols, show="headings", selectmode="extended") # Changed to extended for multi-select
        
        # Configure columns
        for col in cols:
            self.history_tree.heading(col, text=col, command=lambda _col=col: self.sort_history_treeview(_col, False))
            self.history_tree.column(col, width=100, anchor='w')
        
        # Adjust column widths
        self.history_tree.column("Timestamp", width=140)
        self.history_tree.column("Deck", width=150)
        self.history_tree.column("Result", width=60, anchor='center')
        self.history_tree.column("Cubes", width=50, anchor='center')
        self.history_tree.column("Turns", width=50, anchor='center')
        self.history_tree.column("Location1", width=100)
        self.history_tree.column("Location2", width=100)
        self.history_tree.column("Location3", width=100)
        
        # Add scrollbars
        vsb = ttk.Scrollbar(history_list_frame, orient="vertical", command=self.history_tree.yview)
        hsb = ttk.Scrollbar(history_list_frame, orient="horizontal", command=self.history_tree.xview)
        self.history_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Pack scrollbars and treeview
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        self.history_tree.pack(fill=tk.BOTH, expand=True)
        
        # Bind events
        self.history_tree.bind("<<TreeviewSelect>>", self.on_history_match_select)
        self.history_tree.bind("<Double-1>", self.on_history_match_double_click)
        
        # Stats and details frame
        stats_frame = ttk.LabelFrame(parent_frame, text="Stats & Details", padding="5")
        stats_frame.pack(fill=tk.X, pady=5, ipady=5)
        
        # Stats summary at top of frame
        self.stats_summary_var = tk.StringVar(value="No matches selected")
        ttk.Label(stats_frame, textvariable=self.stats_summary_var, font=("Arial", 10, "bold")).pack(fill=tk.X, pady=(0, 5))
        
        # Text widget for details
        self.stats_text_widget = scrolledtext.ScrolledText(
            stats_frame, height=8, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9)
        )
        self.stats_text_widget.pack(fill=tk.X, expand=True)
        
    def _setup_deck_performance_ui(self, parent_frame):
        """Set up the Deck Performance tab UI"""
        # Filter frame
        filter_frame = ttk.Frame(parent_frame)
        filter_frame.pack(fill=tk.X, pady=5)

        ttk.Label(filter_frame, text="Season:").pack(side=tk.LEFT, padx=(0, 5))
        self.deck_perf_season_filter_menu = ttk.OptionMenu(
            filter_frame, self.deck_performance_season_filter_var,
            "All Seasons", "All Seasons", # Placeholder, will be populated
            command=self.load_deck_performance_data
        )
        self.deck_perf_season_filter_menu.pack(side=tk.LEFT, padx=5)

        ttk.Button(filter_frame, text="Refresh Stats", command=self.load_deck_performance_data).pack(side=tk.LEFT, padx=5)

        # Deck Performance list frame
        deck_perf_list_frame = ttk.LabelFrame(parent_frame, text="Deck Statistics", padding="5")
        deck_perf_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        cols = ("Deck Name", "Games", "Wins", "Losses", "Ties", "Win %", "Net Cubes", "Avg Cubes/Game", "Avg Cubes/Win", "Avg Cubes/Loss", "Tags")
        self.deck_performance_tree = ttk.Treeview(deck_perf_list_frame, columns=cols, show="headings", selectmode="browse")

        col_widths = {
            "Deck Name": 200, "Games": 60, "Wins": 50, "Losses": 50, "Ties": 50,
            "Win %": 70, "Net Cubes": 70, "Avg Cubes/Game": 100,
            "Avg Cubes/Win": 100, "Avg Cubes/Loss": 100, "Tags": 100
        }

        for col in cols:
            self.deck_performance_tree.heading(col, text=col, command=lambda _col=col: self.sort_deck_performance_treeview(_col, False))
            anchor_val = 'w' if col == "Deck Name" or col == "Tags" else 'center'
            self.deck_performance_tree.column(col, width=col_widths.get(col, 80), anchor=anchor_val, stretch=(col == "Deck Name"))

        # Add scrollbars
        vsb = ttk.Scrollbar(deck_perf_list_frame, orient="vertical", command=self.deck_performance_tree.yview)
        hsb = ttk.Scrollbar(deck_perf_list_frame, orient="horizontal", command=self.deck_performance_tree.xview)
        self.deck_performance_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        self.deck_performance_tree.pack(fill=tk.BOTH, expand=True)

        # Bind select event if needed for a details pane later (optional)
        # self.deck_performance_tree.bind("<<TreeviewSelect>>", self.on_deck_performance_select)        
        
    def show_card_stats_deck_filter_dialog(self):
        self._create_deck_filter_dialog(
            title="Select Decks for Card Stats",
            all_deck_names_list=self.all_deck_names_for_filter,
            selected_deck_names_set=self.card_stats_selected_deck_names,
            display_var_stringvar=self.card_stats_deck_filter_display_var,
            apply_callback_func=self.load_card_stats_data # This will be called on Apply
        )
        
    def _setup_card_stats_ui(self, parent_frame):
        """Set up the Card Stats tab UI"""
        # Filter frame
        filter_frame = ttk.Frame(parent_frame)
        filter_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(filter_frame, text="Filter Decks...", 
           command=self.show_card_stats_deck_filter_dialog).pack(side=tk.LEFT, padx=(0,5))
        ttk.Label(filter_frame, textvariable=self.card_stats_deck_filter_display_var).pack(side=tk.LEFT, padx=5)
        
        # Add season filter
        ttk.Label(filter_frame, text="Season:").pack(side=tk.LEFT, padx=(20,5))
        self.card_stats_season_filter_var = tk.StringVar(value="All Seasons")
        self.card_stats_season_filter_menu = ttk.OptionMenu(
            filter_frame, self.card_stats_season_filter_var, 
            "All Seasons", "All Seasons", 
            command=self.load_card_stats_data
        )
        self.card_stats_season_filter_menu.pack(side=tk.LEFT, padx=5)
        
        # Buttons
        ttk.Button(filter_frame, text="Refresh Stats", command=self.load_card_stats_data).pack(side=tk.LEFT, padx=5)
        
        # View options
        view_frame = ttk.Frame(parent_frame)
        view_frame.pack(fill=tk.X, pady=5)
        
        self.card_stats_view_var = tk.StringVar(value="Table")
        ttk.Radiobutton(view_frame, text="Table View", variable=self.card_stats_view_var, 
                       value="Table", command=self.toggle_card_stats_view).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(view_frame, text="Chart View", variable=self.card_stats_view_var, 
                       value="Chart", command=self.toggle_card_stats_view).pack(side=tk.LEFT, padx=5)
        
        # Card stats frame containing both table and chart views
        self.card_stats_container = ttk.Frame(parent_frame)
        self.card_stats_container.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Table view frame
        self.card_stats_table_frame = ttk.LabelFrame(self.card_stats_container, text="Card Performance", padding="5")
        self.card_stats_table_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create treeview
        cols = (
            "Card", 
            "Drawn G", "Drawn Win%", "Net C (D)", "Avg C (D)", # Drawn
            "Played G", "Played Win%", "Net C (P)", "Avg C (P)", # Played
            "Not Drawn G", "Not Drawn Win%", "Net C (ND)", "Avg C (ND)", # Not Drawn
            "Not Played G", "Not Played Win%", "Net C (NP)", "Avg C (NP)",  # Not Played
            "ΔC (Drawn)", "ΔC (Played)" # Delta Columns
        )
        self.card_stats_tree = ttk.Treeview(self.card_stats_table_frame, columns=cols, show="headings", selectmode="browse")
        
        # Column widths (adjust as needed, these are estimates)
        # --- MODIFIED WIDTHS ---
        col_widths = {
            "Card": 150, 
            "Drawn G": 60, "Drawn Win%": 70, "Net C (D)": 70, "Avg C (D)": 70,
            "Played G": 60, "Played Win%": 70, "Net C (P)": 70, "Avg C (P)": 70,
            "Not Drawn G": 70, "Not Drawn Win%": 70, "Net C (ND)": 70, "Avg C (ND)": 70,
            "Not Played G": 70, "Not Played Win%": 70, "Net C (NP)": 70, "Avg C (NP)": 70,
            "ΔC (Drawn)": 70, # Delta Cubes Drawn vs Not Drawn
            "ΔC (Played)": 70  # Delta Cubes Played vs Not Played            
        }
        
        # Configure columns
        for col in cols:
            self.card_stats_tree.heading(
                col, text=col, 
                command=lambda _col=col: self.sort_card_stats_treeview(_col, False)
            )
            anchor_val = 'center' if col != "Card" else "w"
            self.card_stats_tree.column(
                col, width=col_widths.get(col, 80), 
                anchor=anchor_val, 
                stretch=tk.YES if col == "Card" else tk.NO
            )
        
        # Add scrollbars
        vsb = ttk.Scrollbar(self.card_stats_table_frame, orient="vertical", command=self.card_stats_tree.yview)
        hsb = ttk.Scrollbar(self.card_stats_table_frame, orient="horizontal", command=self.card_stats_tree.xview)
        self.card_stats_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Pack scrollbars and treeview
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        self.card_stats_tree.pack(fill=tk.BOTH, expand=True)
        
        # Bind events
        self.card_stats_tree.bind("<<TreeviewSelect>>", self.on_card_stats_select)
        
        # Chart view frame (hidden initially)
        self.card_stats_chart_frame = ttk.LabelFrame(self.card_stats_container, text="Card Performance Chart", padding="5")
        # Will be packed when view is toggled to chart
        
        # Create matplotlib figure for chart
        self.card_stats_figure = Figure(figsize=(8, 6), dpi=100)
        self.card_stats_canvas = FigureCanvasTkAgg(self.card_stats_figure, self.card_stats_chart_frame)
        self.card_stats_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Status bar
        ttk.Label(parent_frame, textvariable=self.card_stats_summary_var, relief=tk.SUNKEN, anchor=tk.W).pack(side=tk.BOTTOM, fill=tk.X, pady=(5,0))
    
    def _setup_matchup_ui(self, parent_frame):
        """Set up the Matchups tab UI"""
        # Filter frame
        filter_frame = ttk.Frame(parent_frame)
        filter_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(filter_frame, text="Filter by Deck:").pack(side=tk.LEFT, padx=(0,5))
        self.matchup_deck_filter_var = tk.StringVar(value="All Decks")
        self.matchup_deck_filter_menu = ttk.OptionMenu(
            filter_frame, self.matchup_deck_filter_var, 
            "All Decks", "All Decks", 
            command=self.load_matchup_data
        )
        self.matchup_deck_filter_menu.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(filter_frame, text="Season:").pack(side=tk.LEFT, padx=(20,5))
        self.matchup_season_filter_var = tk.StringVar(value="All Seasons")
        self.matchup_season_filter_menu = ttk.OptionMenu(
            filter_frame, self.matchup_season_filter_var, 
            "All Seasons", "All Seasons", 
            command=self.load_matchup_data
        )
        self.matchup_season_filter_menu.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(filter_frame, text="Refresh Data", command=self.load_matchup_data).pack(side=tk.LEFT, padx=5)
        
        # Paned window for matchup data and details
        paned_window = ttk.PanedWindow(parent_frame, orient=tk.VERTICAL)
        paned_window.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Matchup list frame
        matchup_list_frame = ttk.LabelFrame(paned_window, text="Opponent Matchups", padding="5")
        paned_window.add(matchup_list_frame, weight=3)
        
        # Create matchup treeview
        cols = ("Opponent", "Matches", "Win %", "Wins", "Losses", "Ties", "Net Cubes", "Avg Cubes")
        self.matchup_tree = ttk.Treeview(matchup_list_frame, columns=cols, show="headings", selectmode="browse")
        
        # Configure columns
        for col in cols:
            self.matchup_tree.heading(col, text=col, command=lambda _col=col: self.sort_matchup_treeview(_col, False))
            anchor_val = 'center' if col != "Opponent" else "w"
            self.matchup_tree.column(col, width=80, anchor=anchor_val, stretch=tk.YES if col == "Opponent" else tk.NO)
        
        self.matchup_tree.column("Opponent", width=150, stretch=tk.YES)
        self.matchup_tree.column("Matches", width=60)
        self.matchup_tree.column("Win %", width=60)
        
        # Add scrollbars
        vsb = ttk.Scrollbar(matchup_list_frame, orient="vertical", command=self.matchup_tree.yview)
        hsb = ttk.Scrollbar(matchup_list_frame, orient="horizontal", command=self.matchup_tree.xview)
        self.matchup_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Pack scrollbars and treeview
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        self.matchup_tree.pack(fill=tk.BOTH, expand=True)
        
        # Bind select event
        self.matchup_tree.bind("<<TreeviewSelect>>", self.on_matchup_select)
        
        # Matchup details frame
        matchup_details_frame = ttk.LabelFrame(paned_window, text="Matchup Details", padding="5")
        paned_window.add(matchup_details_frame, weight=2)
        
        # Details notebook
        details_notebook = ttk.Notebook(matchup_details_frame)
        details_notebook.pack(fill=tk.BOTH, expand=True)
        
        # Summary tab
        summary_tab = ttk.Frame(details_notebook)
        details_notebook.add(summary_tab, text="Summary")
        
        # Matchup summary
        self.matchup_summary_var = tk.StringVar(value="Select an opponent to view matchup details")
        ttk.Label(summary_tab, textvariable=self.matchup_summary_var, font=("Arial", 10, "bold")).pack(fill=tk.X, pady=5)
        
        # Revealed cards frame
        revealed_cards_frame = ttk.LabelFrame(summary_tab, text="Most Common Revealed Cards", padding="5")
        revealed_cards_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Create revealed cards treeview
        revealed_cols = ("Card", "Times Seen", "% of Matches")
        self.revealed_cards_tree = ttk.Treeview(revealed_cards_frame, columns=revealed_cols, show="headings", selectmode="browse")
        
        # Configure columns
        for col in revealed_cols:
            self.revealed_cards_tree.heading(col, text=col)
            anchor_val = 'center' if col != "Card" else "w"
            self.revealed_cards_tree.column(col, width=80, anchor=anchor_val, stretch=tk.YES if col == "Card" else tk.NO)
        
        self.revealed_cards_tree.column("Card", width=150, stretch=tk.YES)
        
        # Add scrollbars
        r_vsb = ttk.Scrollbar(revealed_cards_frame, orient="vertical", command=self.revealed_cards_tree.yview)
        r_hsb = ttk.Scrollbar(revealed_cards_frame, orient="horizontal", command=self.revealed_cards_tree.xview)
        self.revealed_cards_tree.configure(yscrollcommand=r_vsb.set, xscrollcommand=r_hsb.set)
        
        # Pack scrollbars and treeview
        r_vsb.pack(side='right', fill='y')
        r_hsb.pack(side='bottom', fill='x')
        self.revealed_cards_tree.pack(fill=tk.BOTH, expand=True)
        
        # History tab
        history_tab = ttk.Frame(details_notebook)
        details_notebook.add(history_tab, text="Match History")
        
        # Create matchup history treeview
        history_cols = ("Date", "Deck", "Result", "Cubes", "Revealed Cards")
        self.matchup_history_tree = ttk.Treeview(history_tab, columns=history_cols, show="headings", selectmode="browse")
        
        # Configure columns
        for col in history_cols:
            self.matchup_history_tree.heading(col, text=col)
            anchor_val = 'center' if col not in ("Deck", "Revealed Cards") else "w"
            self.matchup_history_tree.column(col, width=80, anchor=anchor_val)
        
        self.matchup_history_tree.column("Date", width=100)
        self.matchup_history_tree.column("Deck", width=150)
        self.matchup_history_tree.column("Revealed Cards", width=200, stretch=tk.YES)
        
        # Add scrollbars
        h_vsb = ttk.Scrollbar(history_tab, orient="vertical", command=self.matchup_history_tree.yview)
        h_hsb = ttk.Scrollbar(history_tab, orient="horizontal", command=self.matchup_history_tree.xview)
        self.matchup_history_tree.configure(yscrollcommand=h_vsb.set, xscrollcommand=h_hsb.set)
        
        # Pack scrollbars and treeview
        h_vsb.pack(side='right', fill='y')
        h_hsb.pack(side='bottom', fill='x')
        self.matchup_history_tree.pack(fill=tk.BOTH, expand=True)
    
    def _setup_location_stats_ui(self, parent_frame):
        """Set up the Locations tab UI"""
        # Filter frame
        filter_frame = ttk.Frame(parent_frame)
        filter_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(filter_frame, text="Filter by Deck:").pack(side=tk.LEFT, padx=(0,5))
        self.location_deck_filter_var = tk.StringVar(value="All Decks")
        self.location_deck_filter_menu = ttk.OptionMenu(
            filter_frame, self.location_deck_filter_var, 
            "All Decks", "All Decks", 
            command=self.load_location_stats
        )
        self.location_deck_filter_menu.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(filter_frame, text="Season:").pack(side=tk.LEFT, padx=(20,5))
        self.location_season_filter_var = tk.StringVar(value="All Seasons")
        self.location_season_filter_menu = ttk.OptionMenu(
            filter_frame, self.location_season_filter_var, 
            "All Seasons", "All Seasons", 
            command=self.load_location_stats
        )
        self.location_season_filter_menu.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(filter_frame, text="Refresh Data", command=self.load_location_stats).pack(side=tk.LEFT, padx=5)
        
        # View options
        view_frame = ttk.Frame(parent_frame)
        view_frame.pack(fill=tk.X, pady=5)
        
        self.location_view_var = tk.StringVar(value="Table")
        ttk.Radiobutton(view_frame, text="Table View", variable=self.location_view_var, 
                       value="Table", command=self.toggle_location_view).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(view_frame, text="Chart View", variable=self.location_view_var, 
                       value="Chart", command=self.toggle_location_view).pack(side=tk.LEFT, padx=5)
        
        # Locations container frame
        self.location_container = ttk.Frame(parent_frame)
        self.location_container.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Table view frame
        self.location_table_frame = ttk.LabelFrame(self.location_container, text="Location Performance", padding="5")
        self.location_table_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create location stats treeview
        cols = ("Location", "Games", "Win %", "Wins", "Losses", "Ties", "Net Cubes", "Avg Cubes")
        self.location_stats_tree = ttk.Treeview(self.location_table_frame, columns=cols, show="headings", selectmode="browse")
        
        # Configure columns
        for col in cols:
            self.location_stats_tree.heading(col, text=col, command=lambda _col=col: self.sort_location_treeview(_col, False))
            anchor_val = 'center' if col != "Location" else "w"
            self.location_stats_tree.column(col, width=80, anchor=anchor_val, stretch=tk.YES if col == "Location" else tk.NO)
        
        self.location_stats_tree.column("Location", width=150, stretch=tk.YES)
        
        # Add scrollbars
        vsb = ttk.Scrollbar(self.location_table_frame, orient="vertical", command=self.location_stats_tree.yview)
        hsb = ttk.Scrollbar(self.location_table_frame, orient="horizontal", command=self.location_stats_tree.xview)
        self.location_stats_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Pack scrollbars and treeview
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        self.location_stats_tree.pack(fill=tk.BOTH, expand=True)
        
        # Chart view frame (hidden initially)
        self.location_chart_frame = ttk.LabelFrame(self.location_container, text="Location Performance Chart", padding="5")
        # Will be packed when view is toggled to chart
        
        # Create matplotlib figure for chart
        self.location_figure = Figure(figsize=(8, 6), dpi=100)
        self.location_canvas = FigureCanvasTkAgg(self.location_figure, self.location_chart_frame)
        self.location_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Details area
        self.location_details_frame = ttk.LabelFrame(parent_frame, text="Location Details", padding="5")
        self.location_details_frame.pack(fill=tk.X, pady=5)
        
        self.location_details_var = tk.StringVar(value="Select a location to view details")
        ttk.Label(self.location_details_frame, textvariable=self.location_details_var, font=("Arial", 10)).pack(fill=tk.X, pady=5)
    
    def show_trend_deck_filter_dialog(self):
        self._create_deck_filter_dialog(
            title="Select Decks for Card Stats",
            all_deck_names_list=self.all_deck_names_for_filter,
            selected_deck_names_set=self.trend_selected_deck_names,
            display_var_stringvar=self.trend_deck_filter_display_var,
            apply_callback_func=self.load_trend_data # This will be called on Apply
            )
            
    def _setup_trends_ui(self, parent_frame):
        """Set up the Trends tab UI"""
        # Control frame
        control_frame = ttk.Frame(parent_frame)
        control_frame.pack(fill=tk.X, pady=5)
        
        # Time range selection
        ttk.Label(control_frame, text="Time Range:").pack(side=tk.LEFT, padx=(0,5))
        self.trend_days_combo = ttk.Combobox(control_frame, textvariable=self.trend_days_var, 
                                           values=["7", "14", "30", "60", "90", "All"])
        self.trend_days_combo.pack(side=tk.LEFT, padx=5)
        self.trend_days_combo.current(2)  # Default to 30 days
        
        # Filter frame
        filter_frame = ttk.Frame(parent_frame)
        filter_frame.pack(fill=tk.X, pady=5)
        
        # Deck filter
        ttk.Button(filter_frame, text="Filter Decks...", 
           command=self.show_trend_deck_filter_dialog).pack(side=tk.LEFT, padx=(0,5))
        ttk.Label(filter_frame, textvariable=self.trend_deck_filter_display_var).pack(side=tk.LEFT, padx=5)
        
        # Opponent filter
        ttk.Label(control_frame, text="Opponent:").pack(side=tk.LEFT, padx=(20,5))
        self.trend_opponent_filter_var = tk.StringVar(value="All Opponents")
        self.trend_opponent_filter_menu = ttk.OptionMenu(
            control_frame, self.trend_opponent_filter_var, 
            "All Opponents", "All Opponents", 
            command=self.update_trends
        )
        self.trend_opponent_filter_menu.pack(side=tk.LEFT, padx=5)
        
        # Refresh button
        ttk.Button(control_frame, text="Update Chart", command=self.update_trends).pack(side=tk.LEFT, padx=20)
        
        # Chart frame
        chart_frame = ttk.LabelFrame(parent_frame, text="Performance Trends", padding="5")
        chart_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Create matplotlib figure for trend charts
        self.trend_figure = Figure(figsize=(10, 8), dpi=100)
        
        # Create subplots
        self.trend_win_rate_ax = self.trend_figure.add_subplot(211)
        self.trend_cubes_ax = self.trend_figure.add_subplot(212)
        
        # Add the plot to the tkinter window
        self.trends_canvas = FigureCanvasTkAgg(self.trend_figure, chart_frame)
        self.trends_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Stats summary
        self.trend_summary_frame = ttk.LabelFrame(parent_frame, text="Summary", padding="5")
        self.trend_summary_frame.pack(fill=tk.X, pady=5)
        
        # Create a grid for summary statistics
        summary_grid = ttk.Frame(self.trend_summary_frame)
        summary_grid.pack(fill=tk.X, pady=5)
        
        # Total matches
        ttk.Label(summary_grid, text="Total Matches:").grid(row=0, column=0, sticky="w", padx=10)
        self.trend_total_matches_var = tk.StringVar(value="0")
        ttk.Label(summary_grid, textvariable=self.trend_total_matches_var, font=("Arial", 10, "bold")).grid(row=0, column=1, sticky="w", padx=10)
        
        # Win rate
        ttk.Label(summary_grid, text="Overall Win Rate:").grid(row=0, column=2, sticky="w", padx=10)
        self.trend_win_rate_var = tk.StringVar(value="0%")
        ttk.Label(summary_grid, textvariable=self.trend_win_rate_var, font=("Arial", 10, "bold")).grid(row=0, column=3, sticky="w", padx=10)
        
        # Net cubes
        ttk.Label(summary_grid, text="Net Cubes:").grid(row=1, column=0, sticky="w", padx=10)
        self.trend_net_cubes_var = tk.StringVar(value="0")
        ttk.Label(summary_grid, textvariable=self.trend_net_cubes_var, font=("Arial", 10, "bold")).grid(row=1, column=1, sticky="w", padx=10)
        
        # Avg cubes per game
        ttk.Label(summary_grid, text="Avg Cubes/Game:").grid(row=1, column=2, sticky="w", padx=10)
        self.trend_avg_cubes_var = tk.StringVar(value="0")
        ttk.Label(summary_grid, textvariable=self.trend_avg_cubes_var, font=("Arial", 10, "bold")).grid(row=1, column=3, sticky="w", padx=10)
        
    def _setup_settings_ui(self, parent_frame):
        """Set up the Settings tab UI"""
        # Create a canvas with scrollbar for settings
        canvas = tk.Canvas(parent_frame)
        scrollbar = ttk.Scrollbar(parent_frame, orient="vertical", command=canvas.yview)
        settings_frame = ttk.Frame(canvas)
        
        settings_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=settings_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pack the canvas and scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # General settings section
        general_frame = ttk.LabelFrame(settings_frame, text="General Settings", padding="10")
        general_frame.pack(fill=tk.X, pady=10, padx=10)
        
        # Auto-update card database
        self.auto_update_card_db_var = tk.BooleanVar(value=self.config.getboolean('Settings', 'auto_update_card_db'))
        ttk.Checkbutton(general_frame, text="Auto-update card database on startup", 
                      variable=self.auto_update_card_db_var).pack(anchor="w", pady=5)
        
        # Check for app updates
        self.check_for_updates_var = tk.BooleanVar(value=self.config.getboolean('Settings', 'check_for_app_updates'))
        ttk.Checkbutton(general_frame, text="Check for application updates on startup", 
                      variable=self.check_for_updates_var).pack(anchor="w", pady=5)
        
        # Display card names
        self.display_card_names_var = tk.BooleanVar(value=self.config.getboolean('Settings', 'card_name_display'))
        ttk.Checkbutton(general_frame, text="Display card names instead of IDs when available", 
                      variable=self.display_card_names_var).pack(anchor="w", pady=5)
        
        # Update interval
        interval_frame = ttk.Frame(general_frame)
        interval_frame.pack(fill=tk.X, pady=5)
        ttk.Label(interval_frame, text="Data update interval (ms):").pack(side=tk.LEFT, padx=(0, 10))
        
        self.update_interval_var = tk.StringVar(value=self.config.get('Settings', 'update_interval'))
        interval_entry = ttk.Entry(interval_frame, textvariable=self.update_interval_var, width=6)
        interval_entry.pack(side=tk.LEFT)
        
        # Max error log entries
        error_log_frame = ttk.Frame(general_frame)
        error_log_frame.pack(fill=tk.X, pady=5)
        ttk.Label(error_log_frame, text="Maximum error log entries:").pack(side=tk.LEFT, padx=(0, 10))
        
        self.max_error_log_var = tk.StringVar(value=self.config.get('Settings', 'max_error_log_entries'))
        error_log_entry = ttk.Entry(error_log_frame, textvariable=self.max_error_log_var, width=6)
        error_log_entry.pack(side=tk.LEFT)
        
        # Theme settings
        theme_frame = ttk.LabelFrame(settings_frame, text="Theme Settings", padding="10")
        theme_frame.pack(fill=tk.X, pady=10, padx=10)
        
        # Theme selection
        theme_select_frame = ttk.Frame(theme_frame)
        theme_select_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(theme_select_frame, text="Theme:").pack(side=tk.LEFT, padx=(0, 10))
        
        self.theme_var = tk.StringVar(value="dark")
        theme_combo = ttk.Combobox(theme_select_frame, textvariable=self.theme_var, 
                                 values=["dark", "light", "custom"])
        theme_combo.pack(side=tk.LEFT)
        theme_combo.bind("<<ComboboxSelected>>", lambda e: self.change_theme(self.theme_var.get()))
        
        # Custom theme colors
        color_grid = ttk.Frame(theme_frame)
        color_grid.pack(fill=tk.X, pady=10)
        
        # Create a grid of color pickers
        color_options = [
            ("Background", "bg_main"),
            ("Secondary Background", "bg_secondary"),
            ("Text", "fg_main"),
            ("Primary Accent", "accent_primary"),
            ("Secondary Accent", "accent_secondary"),
            ("Win Color", "win"),
            ("Loss Color", "loss"),
            ("Neutral Color", "neutral")
        ]
        
        self.color_vars = {}
        
        for i, (label_text, color_key) in enumerate(color_options):
            row = i // 2
            col = i % 2 * 2
            
            ttk.Label(color_grid, text=label_text + ":").grid(row=row, column=col, sticky="e", padx=(10 if col > 0 else 0, 5), pady=5)
            
            color_var = tk.StringVar(value=self.config['Colors'][color_key])
            self.color_vars[color_key] = color_var
            
            color_frame = ttk.Frame(color_grid, width=20, height=20, relief="solid", borderwidth=1)
            color_frame.grid(row=row, column=col+1, sticky="w", padx=5, pady=5)
            color_frame.configure(style="TFrame")
            
            # Use a Label inside the frame to show the color
            color_label = tk.Label(color_frame, background=color_var.get(), width=3, height=1)
            color_label.pack(fill=tk.BOTH, expand=True)
            
            # Bind click event to color picker
            color_label.bind("<Button-1>", lambda e, key=color_key, lbl=color_label: self.pick_color(key, lbl))
        
        # Add save button
        save_button = ttk.Button(theme_frame, text="Apply Custom Theme", command=self.apply_custom_theme)
        save_button.pack(pady=10)
        
        # Paths section
        paths_frame = ttk.LabelFrame(settings_frame, text="File Paths", padding="10")
        paths_frame.pack(fill=tk.X, pady=10, padx=10)
        
        # Game state path
        game_state_frame = ttk.Frame(paths_frame)
        game_state_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(game_state_frame, text="Game State Path:").pack(side=tk.LEFT, padx=(0, 10))
        
        self.game_state_path_var = tk.StringVar(value=self.game_state_file_path or "Auto-detected")
        path_entry = ttk.Entry(game_state_frame, textvariable=self.game_state_path_var, width=40)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        path_browse = ttk.Button(game_state_frame, text="Browse...", command=self.browse_game_state_path)
        path_browse.pack(side=tk.LEFT, padx=5)
        
        # Card database
        card_db_frame = ttk.Frame(paths_frame)
        card_db_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(card_db_frame, text="Card Database API:").pack(side=tk.LEFT, padx=(0, 10))
        
        self.card_db_api_var = tk.StringVar(value=self.config['CardDB']['api_url'])
        card_api_entry = ttk.Entry(card_db_frame, textvariable=self.card_db_api_var, width=40)
        card_api_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # About section
        about_frame = ttk.LabelFrame(settings_frame, text="About", padding="10")
        about_frame.pack(fill=tk.X, pady=10, padx=10)
        
        ttk.Label(about_frame, text=f"Marvel Snap Tracker v{VERSION}", font=("Arial", 12, "bold")).pack(pady=5)
        ttk.Label(about_frame, text="An enhanced tracking tool for Marvel Snap").pack(pady=2)
        ttk.Label(about_frame, text="Original by GitHub user (updated by Claude)").pack(pady=2)
        
        # Add a button to check for updates
        ttk.Button(about_frame, text="Check for App Updates", command=self.check_for_updates_command).pack(pady=10)
        
        # Save settings button at the bottom
        save_settings_frame = ttk.Frame(settings_frame)
        save_settings_frame.pack(fill=tk.X, pady=20, padx=10)
        
        ttk.Button(save_settings_frame, text="Save All Settings", command=self.save_settings).pack(pady=5)
    
    def on_card_list_hover(self, event, location_index, player_type):
        """Handle mouse hover over card lists in locations"""
        # Get the variable with the cards
        if player_type == "local":
            cards_var = self.location_vars[location_index]["local_cards"]
        else:  # opponent
            cards_var = self.location_vars[location_index]["opp_cards"]
        
        # Get the card text
        cards_text = cards_var.get()
        
        # If we have cards and they aren't just placeholder spaces
        if cards_text and cards_text.strip() != " \n \n ":
            # Get first card in the list
            first_card_line = cards_text.strip().split('\n')[0]
            
            # Extract card name (before parenthesis if any)
            card_name_match = re.match(r"([^(]+)", first_card_line)
            first_card = card_name_match.group(1).strip() if card_name_match else first_card_line.strip()

            # Extract card ID (assumes card_db is being used for display names)
            card_id_to_show = first_card # Default to name if not found
            if self.card_db:
                # Try to reverse-lookup card ID from name
                found = False
                for cid, card_info in self.card_db.items():
                    if first_card == card_info.get('name', ''):
                        card_id_to_show = cid
                        found = True
                        break
                if not found and first_card in self.card_db: # Maybe it's an ID already
                    card_id_to_show = first_card

            # Show tooltip for this card
            self.card_tooltip.show_tooltip(card_id_to_show, event)
    
    def on_zone_hover(self, event, zone):
        """Handle mouse hover over card zones (hand, graveyard, etc.)"""
        zone_var = None
        
        # Determine which variable to use based on zone
        if zone == "hand":
            zone_var = self.local_hand_var
        elif zone == "graveyard":
            zone_var = self.local_graveyard_var
        elif zone == "banished":
            zone_var = self.local_banished_var
        elif zone == "remaining":
            zone_var = self.local_remaining_deck_var
        elif zone == "opp_graveyard":
            zone_var = self.opponent_graveyard_var
        elif zone == "opp_banished":
            zone_var = self.opponent_banished_var
        
        if zone_var:
            # Get the cards text
            cards_text = zone_var.get()
            
            # If we have cards
            if cards_text and not cards_text.startswith(("Empty", "Hand:", "Deck:", "N/A", "Deck (Remaining):", "Destroyed:", "Banished:")):
                # Remove count prefix for remaining deck
                if zone == "remaining" and cards_text.startswith("("):
                    match = re.match(r"\(\d+\)\s*(.*)", cards_text)
                    if match:
                        cards_text = match.group(1)

                # Get first card in the list
                first_card_line = cards_text.split(',')[0].strip()
                card_name_match = re.match(r"([^(]+)", first_card_line)
                first_card = card_name_match.group(1).strip() if card_name_match else first_card_line.strip()

                # Extract card ID
                card_id_to_show = first_card
                if self.card_db:
                    found = False
                    for cid, card_info in self.card_db.items():
                        if first_card == card_info.get('name', ''):
                            card_id_to_show = cid
                            found = True
                            break
                    if not found and first_card in self.card_db:
                         card_id_to_show = first_card
                
                # Show tooltip for this card
                self.card_tooltip.show_tooltip(card_id_to_show, event)
        
    def sort_history_treeview(self, col, reverse):
        """Sort history treeview by column"""
        data = [(self.history_tree.set(child, col), child) for child in self.history_tree.get_children('')]
        
        def try_convert(val_str):
            val_str = str(val_str).replace('%', '')
            try: 
                return int(val_str)
            except (ValueError, TypeError):
                try: 
                    return float(val_str)
                except (ValueError, TypeError): 
                    return val_str.lower()
        
        data.sort(key=lambda t: try_convert(t[0]), reverse=reverse)
        
        for index, (val, child) in enumerate(data): 
            self.history_tree.move(child, '', index)
        
        self.history_tree.heading(col, command=lambda _col=col: self.sort_history_treeview(_col, not reverse))
    
    def sort_card_stats_treeview(self, col, reverse):
        """Sort card stats treeview by column"""
        data = [(self.card_stats_tree.set(child, col), child) for child in self.card_stats_tree.get_children('')]
        
        def try_convert(val_str):
            val_str = str(val_str).replace('%', '').replace('N/A', '-9999')
            try: 
                return int(val_str)
            except (ValueError, TypeError):
                try: 
                    return float(val_str)
                except (ValueError, TypeError): 
                    return val_str.lower()
        
        data.sort(key=lambda t: try_convert(t[0]), reverse=reverse)
        
        for index, (val, child) in enumerate(data): 
            self.card_stats_tree.move(child, '', index)
        
        self.card_stats_tree.heading(col, command=lambda _col=col: self.sort_card_stats_treeview(_col, not reverse))
    
    def sort_matchup_treeview(self, col, reverse):
        """Sort matchup treeview by column"""
        data = [(self.matchup_tree.set(child, col), child) for child in self.matchup_tree.get_children('')]
        
        # Updated key creation function
        def create_sort_key(value_from_cell):
            s_value = str(value_from_cell)  # Ensure it's a string initially

            # Handle "N/A" specifically for numeric comparison, sorting it as a very small number
            if s_value == "N/A":
                return (0, -float('inf')) 

            # Clean string for potential numeric conversion (remove %, etc.)
            numeric_candidate_str = s_value.replace('%', '')

            try:
                # Attempt to convert to int
                return (0, int(numeric_candidate_str))  # Type 0 for numbers
            except ValueError:
                try:
                    # Attempt to convert to float
                    return (0, float(numeric_candidate_str))  # Type 0 for numbers
                except ValueError:
                    # If it's not a number, treat it as a string
                    # Handle empty strings specifically if needed, or just lowercase
                    if not s_value.strip(): # If original string was empty or whitespace
                        return (1, "") # Sort empty strings together as type 1
                    return (1, s_value.lower()) # Type 1 for strings

        # Sort using the new key
        data.sort(key=lambda t: create_sort_key(t[0]), reverse=reverse)
        
        for index, (val, child) in enumerate(data): 
            self.matchup_tree.move(child, '', index)
        
        self.matchup_tree.heading(col, command=lambda _col=col: self.sort_matchup_treeview(_col, not reverse))
    
    def sort_location_treeview(self, col, reverse):
        """Sort location treeview by column"""
        data = [(self.location_stats_tree.set(child, col), child) for child in self.location_stats_tree.get_children('')]
        
        def try_convert(val_str):
            val_str = str(val_str).replace('%', '').replace('N/A', '-9999')
            try: 
                return int(val_str)
            except (ValueError, TypeError):
                try: 
                    return float(val_str)
                except (ValueError, TypeError): 
                    return val_str.lower()
        
        data.sort(key=lambda t: try_convert(t[0]), reverse=reverse)
        
        for index, (val, child) in enumerate(data): 
            self.location_stats_tree.move(child, '', index)
        
        self.location_stats_tree.heading(col, command=lambda _col=col: self.sort_location_treeview(_col, not reverse))
        
    def sort_deck_performance_treeview(self, col, reverse):
        """Sort deck performance treeview by column"""
        data = [(self.deck_performance_tree.set(child, col), child) for child in self.deck_performance_tree.get_children('')]

        def try_convert(val_str):
            val_str = str(val_str).replace('%', '').replace('N/A', '-99999') # Use a very small number for N/A in sorting
            try:
                return float(val_str) # Convert to float for consistent numeric sorting
            except (ValueError, TypeError):
                return val_str.lower()

        data.sort(key=lambda t: try_convert(t[0]), reverse=reverse)

        for index, (val, child) in enumerate(data):
            self.deck_performance_tree.move(child, '', index)

        self.deck_performance_tree.heading(col, command=lambda _col=col: self.sort_deck_performance_treeview(_col, not reverse))

    def load_deck_performance_data(self, event=None):
        """Load and display statistics for each deck."""
        if not self.deck_performance_tree: # Ensure tree exists
            print("WARN: Deck performance tree not initialized yet.")
            return

        # Clear current items
        for item in self.deck_performance_tree.get_children():
            self.deck_performance_tree.delete(item)

        selected_season = self.deck_performance_season_filter_var.get()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        query_parts = ["""
            SELECT
                d.id as deck_db_id,
                COALESCE(d.deck_name, 'Unknown Deck') as deck_name,
                COUNT(m.game_id) as games_played,
                SUM(CASE WHEN m.result = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN m.result = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN m.result = 'tie' THEN 1 ELSE 0 END) as ties,
                SUM(m.cubes_changed) as net_cubes,
                AVG(CASE WHEN m.result = 'win' THEN m.cubes_changed ELSE NULL END) as avg_cubes_win,
                AVG(CASE WHEN m.result = 'loss' THEN m.cubes_changed ELSE NULL END) as avg_cubes_loss,
                d.tags as deck_tags
            FROM
                decks d
            JOIN
                matches m ON d.id = m.deck_id
        """]
        params = []

        if selected_season != "All Seasons":
            query_parts.append("WHERE m.season = ?")
            params.append(selected_season)

        query_parts.append("GROUP BY d.id, d.deck_name, d.tags")
        query_parts.append("ORDER BY games_played DESC, wins DESC")

        final_query = " ".join(query_parts)
        cursor.execute(final_query, tuple(params))
        deck_stats = cursor.fetchall()
        conn.close()

        for row in deck_stats:
            deck_db_id, name, games, wins, losses, ties, net_cubes, avg_win, avg_loss, tags_json = row

            wins = wins if wins is not None else 0
            losses = losses if losses is not None else 0
            ties = ties if ties is not None else 0
            net_cubes = net_cubes if net_cubes is not None else 0

            win_rate = (wins / games * 100) if games > 0 else 0
            avg_cubes_game = (net_cubes / games) if games > 0 else 0
            
            # Handle None for avg_win and avg_loss (SQLite AVG returns NULL if no matching rows)
            avg_win_str = f"{avg_win:.2f}" if avg_win is not None else "N/A"
            avg_loss_str = f"{avg_loss:.2f}" if avg_loss is not None else "N/A" # avg_loss is already negative if it's a loss

            deck_tags_display = "None"
            if tags_json:
                try:
                    tags_list = json.loads(tags_json)
                    if isinstance(tags_list, list) and tags_list:
                        deck_tags_display = ", ".join(tags_list)
                except json.JSONDecodeError:
                    deck_tags_display = "Error"


            self.deck_performance_tree.insert("", "end", iid=deck_db_id, values=(
                name,
                games,
                wins,
                losses,
                ties,
                f"{win_rate:.1f}%",
                net_cubes,
                f"{avg_cubes_game:.2f}",
                avg_win_str,
                avg_loss_str,
                deck_tags_display
            ))        
        
    def load_history_tab_data(self):
        """Load match history data and populate UI"""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Get all deck names for filter
        cursor.execute("SELECT DISTINCT deck_name FROM decks WHERE deck_name IS NOT NULL ORDER BY deck_name")
        # Store all actual deck names (excluding the "All Decks" placeholder)
        self.all_deck_names_for_filter = [row[0] for row in cursor.fetchall() if row[0]] 
        
        # Get all seasons for filter
        cursor.execute("SELECT DISTINCT season FROM matches WHERE season IS NOT NULL ORDER BY season")
        seasons = ["All Seasons"] + [row[0] for row in cursor.fetchall() if row[0]]
        
        # Update menu options for all filters that use deck names
        #self.history_deck_options = deck_names if deck_names else ["All Decks"]
        
        # Example of how you might handle other tabs' OptionMenus if they still exist:
        # Update deck filter options for *other* tabs that still use OptionMenu
        deck_names_for_optionmenu = ["All Decks"] + self.all_deck_names_for_filter
        
        # Update all menu widgets that use deck names
        for menu_widget, str_var, cmd_func in [
            # (self.deck_filter_menu, self.history_deck_filter_var, self.apply_history_filter), # REMOVE THIS LINE FOR HISTORY
            #(self.card_stats_deck_filter_menu, self.card_stats_deck_filter_var, self.load_card_stats_data),
            (self.matchup_deck_filter_menu, self.matchup_deck_filter_var, self.load_matchup_data),
            (self.location_deck_filter_menu, self.location_deck_filter_var, self.load_location_stats),
            #(self.trend_deck_filter_menu, self.trend_deck_filter_var, self.update_trends)
        ]:
            if menu_widget: 
                menu = menu_widget["menu"]
                menu.delete(0, "end")
                
                current_val = str_var.get()
                # Ensure effective_options has at least one item for default selection
                effective_options = deck_names_for_optionmenu if deck_names_for_optionmenu else ["All Decks"]
                default_selection = effective_options[0]
                
                if not effective_options: # Should not happen if ["All Decks"] is always prepended
                    str_var.set("")
                elif current_val not in effective_options: 
                    str_var.set(default_selection)
                
                for name in effective_options: 
                    menu.add_command(label=name, command=lambda n=name, sv=str_var, cf=cmd_func: (sv.set(n), cf() if cf else None))
                
                if not str_var.get() and effective_options: # If var is empty, set to default
                    str_var.set(effective_options[0])
        
        # Update season filter menus
        for menu_widget, str_var, cmd_func in [ # Added cmd_func for consistency
            (self.season_filter_menu, self.season_filter_var, self.apply_history_filter),
            (self.card_stats_season_filter_menu, self.card_stats_season_filter_var, self.load_card_stats_data),
            (self.matchup_season_filter_menu, self.matchup_season_filter_var, self.load_matchup_data),
            (self.location_season_filter_menu, self.location_season_filter_var, self.load_location_stats),
            (self.deck_perf_season_filter_menu, self.deck_performance_season_filter_var, self.load_deck_performance_data)
        ]:
            if menu_widget:
                menu = menu_widget["menu"]
                menu.delete(0, "end")
                
                current_val = str_var.get()
                effective_options = seasons if seasons and seasons[0] else ["All Seasons"]
                default_selection = effective_options[0] if effective_options else ""

                if not effective_options:
                    str_var.set("")
                elif current_val not in effective_options:
                    str_var.set(default_selection)

                for season_name in effective_options:
                    menu.add_command(label=season_name, command=lambda s=season_name, sv=str_var, cf=cmd_func: (sv.set(s), cf() if cf else None))
                
                if not str_var.get() and effective_options:
                    str_var.set(effective_options[0])

        # Update opponent filter menu for Trends tab
        cursor.execute("SELECT DISTINCT opponent_player_name FROM matches WHERE opponent_player_name IS NOT NULL AND opponent_player_name != 'Opponent' ORDER BY opponent_player_name")
        opponents = ["All Opponents"] + [row[0] for row in cursor.fetchall() if row[0]]
        
        menu = self.trend_opponent_filter_menu["menu"]
        menu.delete(0, "end")
        current_opp_val = self.trend_opponent_filter_var.get()
        effective_opp_options = opponents if opponents and opponents[0] else ["All Opponents"]
        default_opp_selection = effective_opp_options[0] if effective_opp_options else ""

        if not effective_opp_options:
            self.trend_opponent_filter_var.set("")
        elif current_opp_val not in effective_opp_options:
            self.trend_opponent_filter_var.set(default_opp_selection)
            
        for opponent in effective_opp_options:
            menu.add_command(label=opponent, command=lambda o=opponent, sv=self.trend_opponent_filter_var, cf=self.update_trends: (sv.set(o), cf() if cf else None))
        
        if not self.trend_opponent_filter_var.get() and effective_opp_options:
             self.trend_opponent_filter_var.set(effective_opp_options[0])

        conn.close()
        
        # Apply the filter to update the history view
        self.apply_history_filter()
    
    def apply_history_filter(self, event=None):
        """Apply filters to match history view"""
        # Clear current items
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        
        # Get filter values
        #selected_deck_name = self.history_deck_filter_var.get()
        selected_season = self.season_filter_var.get()
        selected_result = self.result_filter_var.get()
        search_text = self.search_var.get().lower()
        
        # Build query
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        query = """
            SELECT 
                m.timestamp_ended, COALESCE(d.deck_name, 'Unknown Deck'), 
                m.opponent_player_name, m.result, m.cubes_changed, m.turns_taken, 
                m.loc_1_def_id, m.loc_2_def_id, m.loc_3_def_id, m.game_id
            FROM 
                matches m 
            LEFT JOIN 
                decks d ON m.deck_id = d.id
            WHERE 1=1
        """
        params = []
        
        # --- MODIFIED DECK FILTERING ---
        print(f"DEBUG apply_history_filter: self.history_selected_deck_names = {self.history_selected_deck_names}") # DEBUG
        if self.history_selected_deck_names: 
            placeholders = ', '.join(['?'] * len(self.history_selected_deck_names))
            query += f" AND d.deck_name IN ({placeholders})"
            params.extend(list(self.history_selected_deck_names))
            print(f"DEBUG apply_history_filter: Added deck filter with params: {list(self.history_selected_deck_names)}") # DEBUG
        else:
            print("DEBUG apply_history_filter: No specific decks selected, showing all.") # DEBUG
        # --- END MODIFIED ---
        
        # if selected_deck_name != "All Decks":
            # query += " AND d.deck_name = ?"
            # params.append(selected_deck_name)
        
        if selected_season != "All Seasons":
            query += " AND m.season = ?"
            params.append(selected_season)
        
        if selected_result != "All Results":
            query += " AND m.result = ?"
            params.append(selected_result.lower())
        
        if search_text:
            query += """ AND (
                lower(COALESCE(d.deck_name, '')) LIKE ? OR 
                lower(COALESCE(m.opponent_player_name, '')) LIKE ? OR 
                lower(COALESCE(m.loc_1_def_id, '')) LIKE ? OR 
                lower(COALESCE(m.loc_2_def_id, '')) LIKE ? OR 
                lower(COALESCE(m.loc_3_def_id, '')) LIKE ? OR
                lower(COALESCE(m.notes, '')) LIKE ? 
            )""" # Added notes to search
            search_pattern = f"%{search_text}%"
            params.extend([search_pattern] * 6) # Increased to 6
        
        query += " ORDER BY m.timestamp_ended DESC"
        
        cursor.execute(query, tuple(params))
        matches = cursor.fetchall()
        
        # Insert matches into treeview
        for match in matches:
            try:
                ts_str = datetime.datetime.strptime(match[0].split('.')[0], "%Y-%m-%d %H:%M:%S").strftime("%y-%m-%d %H:%M")
            except (ValueError, TypeError):
                ts_str = match[0]
            
            # Resolve location names if using card_db
            loc1, loc2, loc3 = match[6], match[7], match[8]
            if self.card_db and self.display_card_names_var.get():
                loc1 = self.card_db.get(loc1, {}).get('name', loc1) if loc1 else '?'
                loc2 = self.card_db.get(loc2, {}).get('name', loc2) if loc2 else '?'
                loc3 = self.card_db.get(loc3, {}).get('name', loc3) if loc3 else '?'
            
            self.history_tree.insert(
                "", "end", 
                values=(
                    ts_str, match[1], match[2], match[3], 
                    match[4] if match[4] is not None else '?', 
                    match[5], loc1, loc2, loc3
                ), 
                iid=match[9] # Use game_id as item ID
            )
        
        # Calculate and display stats for filtered matches
        self.calculate_and_display_stats(matches)
        
        conn.close()
    
    def calculate_and_display_stats(self, filtered_matches):
        """Calculate statistics from filtered matches and display them"""
        self.stats_text_widget.config(state=tk.NORMAL)
        self.stats_text_widget.delete(1.0, tk.END)
        
        if not filtered_matches:
            self.stats_summary_var.set("No matches found.")
            self.stats_text_widget.insert(tk.END, "No matches found.")
            self.stats_text_widget.config(state=tk.DISABLED)
            return
        
        # Calculate basic stats
        total_games = len(filtered_matches)
        wins = sum(1 for m in filtered_matches if m[3] == 'win')
        losses = sum(1 for m in filtered_matches if m[3] == 'loss')
        ties = sum(1 for m in filtered_matches if m[3] == 'tie')
        total_cubes = sum(m[4] for m in filtered_matches if m[4] is not None)
        
        win_rate = (wins / total_games * 100) if total_games > 0 else 0
        avg_cubes = (total_cubes / total_games) if total_games > 0 else 0
        
        # Create summary string
        filter_selection = self.history_deck_filter_display_var.get()
        
        if self.season_filter_var.get() != "All Seasons":
            filter_selection += f", Season: {self.season_filter_var.get()}"
        if self.result_filter_var.get() != "All Results":
            filter_selection += f", Result: {self.result_filter_var.get()}"
        if self.search_var.get():
            filter_selection += f", Search: '{self.search_var.get()}'"

        summary = f"{filter_selection}\n"
        summary += f"Total: {total_games}, Wins: {wins} ({win_rate:.1f}%), Losses: {losses}, Ties: {ties}\n"
        summary += f"Net Cubes: {total_cubes}, Avg Cubes/Game: {avg_cubes:.2f}\n\n"
        
        # Update summary label
        self.stats_summary_var.set(f"{filter_selection} - Win Rate: {win_rate:.1f}%, Net Cubes: {total_cubes}")
        
        # Calculate additional stats
        avg_game_length = sum(m[5] for m in filtered_matches if m[5] is not None) / total_games if total_games > 0 else 0
        summary += f"Average Game Length: {avg_game_length:.1f} turns\n"
        
        # Count most common locations
        location_counter = Counter()
        for match in filtered_matches:
            if match[6]:
                location_counter[match[6]] += 1
            if match[7]:
                location_counter[match[7]] += 1
            if match[8]:
                location_counter[match[8]] += 1
        
        # Display most common locations
        common_locations = location_counter.most_common(5)
        if common_locations:
            summary += "\nMost Common Locations:\n"
            for loc, count in common_locations:
                # Use card name if available
                loc_name = loc
                if self.card_db and self.display_card_names_var.get() and loc in self.card_db:
                    loc_name = self.card_db[loc].get('name', loc)
                summary += f"  {loc_name}: {count} games\n"
        
        # Display in text widget
        self.stats_text_widget.insert(tk.END, summary)
        self.stats_text_widget.config(state=tk.DISABLED)
    
    def on_history_match_select(self, event):
        """Handle selection of a match in the history view"""
        selected_items = self.history_tree.selection()
        if not selected_items:
            self.stats_summary_var.set("No match selected.")
            self.stats_text_widget.config(state=tk.NORMAL)
            self.stats_text_widget.delete(1.0, tk.END)
            self.stats_text_widget.insert(tk.END, "Select a match to see details.")
            self.stats_text_widget.config(state=tk.DISABLED)
            return

        selected_item_id = selected_items[0] # Display details for the first selected item
        
        self.stats_text_widget.config(state=tk.NORMAL)
        self.stats_text_widget.delete(1.0, tk.END)
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                m.timestamp_ended, COALESCE(d.deck_name, 'Unknown'), 
                m.opponent_player_name, m.result, m.cubes_changed, m.turns_taken,
                m.loc_1_def_id, m.loc_2_def_id, m.loc_3_def_id, 
                d.card_ids_json, m.opp_revealed_cards_json, m.notes
            FROM 
                matches m 
            LEFT JOIN 
                decks d ON m.deck_id = d.id 
            WHERE 
                m.game_id = ?
        """, (selected_item_id,))
        
        match_details = cursor.fetchone()
        
        if match_details:
            # Format timestamp
            try:
                timestamp = datetime.datetime.strptime(
                    match_details[0].split('.')[0], 
                    "%Y-%m-%d %H:%M:%S"
                ).strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                timestamp = match_details[0]
            
            # Start building details
            details_str = f"Game ID: {selected_item_id}\n"
            details_str += f"Time: {timestamp}\n"
            details_str += f"Deck: {match_details[1]}\n"
            details_str += f"Opponent: {match_details[2]}\n"
            details_str += f"Result: {match_details[3]} ({match_details[4] if match_details[4] is not None else '?'} cubes)\n"
            details_str += f"Turns: {match_details[5]}\n"
            
            # Add locations with names if available
            locations = [match_details[6], match_details[7], match_details[8]]
            loc_names = []
            
            for loc in locations:
                if not loc:
                    loc_names.append("?")
                elif self.card_db and self.display_card_names_var.get() and loc in self.card_db:
                    loc_names.append(self.card_db[loc].get('name', loc))
                else:
                    loc_names.append(loc)
                    
            details_str += f"Locations: {loc_names[0]}, {loc_names[1]}, {loc_names[2]}\n"
            
            # Add notes if available
            if match_details[11]:
                details_str += f"\nNotes: {match_details[11]}\n"
            
            # Add deck cards with names if available
            if match_details[9]:
                try:
                    cards = json.loads(match_details[9])
                    if self.card_db and self.display_card_names_var.get():
                        named_cards = []
                        for card_id in cards:
                            if card_id in self.card_db:
                                named_cards.append(self.card_db[card_id].get('name', card_id))
                            else:
                                named_cards.append(card_id)
                        details_str += f"\nYour Deck Cards: {', '.join(named_cards)}\n"
                    else:
                        details_str += f"\nYour Deck Cards: {', '.join(cards)}\n"
                except json.JSONDecodeError:
                    pass
            
            # Add opponent revealed cards with names if available
            if match_details[10]:
                try:
                    cards_opp = json.loads(match_details[10])
                    if self.card_db and self.display_card_names_var.get():
                        named_cards_opp = []
                        for card_id in cards_opp:
                            if card_id in self.card_db:
                                named_cards_opp.append(self.card_db[card_id].get('name', card_id))
                            else:
                                named_cards_opp.append(card_id)
                        details_str += f"Opponent Revealed: {', '.join(named_cards_opp)}\n"
                    else:
                        details_str += f"Opponent Revealed: {', '.join(cards_opp)}\n"
                except json.JSONDecodeError:
                    pass
            
            # Add event log
            details_str += "\n--- Events ---\n"
            self.stats_text_widget.insert(tk.END, details_str)
            
            cursor.execute("""
                SELECT 
                    turn, event_type, player_type, card_def_id, 
                    location_index, source_zone, target_zone, details_json 
                FROM 
                    match_events 
                WHERE 
                    game_id = ? 
                ORDER BY 
                    turn, id
            """, (selected_item_id,))
            
            events = cursor.fetchall()
            
            if events:
                for ev in events:
                    # Format location string
                    loc_str = f" @Loc{ev[4]+1}" if ev[4] is not None else ""
                    
                    # Get card name if available
                    card_id = ev[3]
                    card_name = card_id
                    if self.card_db and self.display_card_names_var.get() and card_id in self.card_db:
                        card_name = self.card_db[card_id].get('name', card_id)
                    
                    # Parse details JSON
                    ev_details_str = ev[7]
                    details_dict = {}
                    
                    if ev_details_str:
                        try:
                            details_dict = json.loads(ev_details_str)
                        except json.JSONDecodeError:
                            details_dict = {"raw_details": ev_details_str}  # Show raw if not JSON
                    
                    det_parts = [f"{k}:{v}" for k, v in details_dict.items()]
                    det_final = f" ({', '.join(det_parts)})" if det_parts else ""
                    
                    # Format event line
                    event_line = f"T{ev[0]}: {ev[2].capitalize()} {ev[1]} '{card_name}'{loc_str}{det_final}\n"
                    
                    # Apply color based on player type
                    self.stats_text_widget.insert(tk.END, event_line)
            else:
                self.stats_text_widget.insert(tk.END, "No detailed events logged.\n")
        
        conn.close()
        self.stats_text_widget.config(state=tk.DISABLED)
    
    def on_history_match_double_click(self, event):
        """Handle double-click on a match in the history view"""
        selected_item_id = self.history_tree.focus()
        if not selected_item_id:
            return
        
        # Show dialog to add/edit note
        self.add_match_note(selected_item_id)
    
    def add_match_note(self, game_id=None):
        """Add or edit a note for a match"""
        if game_id is None:
            selected_items = self.history_tree.selection()
            if not selected_items:
                messagebox.showinfo("Add Note", "Please select a match first.")
                return
            game_id = selected_items[0] # Use the first selected item's ID
        
        # Get current note if any
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT notes FROM matches WHERE game_id = ?", (game_id,))
        result = cursor.fetchone()
        current_note = result[0] if result and result[0] else ""
        conn.close()
        
        # Create dialog
        note_dialog = tk.Toplevel(self.root)
        note_dialog.title("Add/Edit Match Note")
        note_dialog.geometry("400x300")
        note_dialog.transient(self.root)
        note_dialog.grab_set()
        
        # Apply theme
        note_dialog.configure(background=self.config['Colors']['bg_main'])
        
        # Create widgets
        ttk.Label(note_dialog, text="Enter note for this match:").pack(pady=(10, 5), padx=10, anchor="w")
        
        note_text = scrolledtext.ScrolledText(note_dialog, height=10, wrap=tk.WORD)
        note_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        note_text.insert(tk.END, current_note)
        
        button_frame = ttk.Frame(note_dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def save_note():
            note = note_text.get("1.0", tk.END).strip()
            
            conn_save = sqlite3.connect(DB_NAME)
            cursor_save = conn_save.cursor()
            cursor_save.execute("UPDATE matches SET notes = ? WHERE game_id = ?", (note, game_id))
            conn_save.commit()
            conn_save.close()
            
            note_dialog.destroy()
            
            # Refresh the match details if this match is still selected
            if self.history_tree.focus() == game_id:
                self.on_history_match_select(None)
        
        ttk.Button(button_frame, text="Save", command=save_note).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=note_dialog.destroy).pack(side=tk.RIGHT, padx=5)
    
    def delete_selected_matches(self):
        """Delete selected matches from the database"""
        selected_items = self.history_tree.selection() # Returns a tuple of item IDs
        if not selected_items:
            messagebox.showinfo("Delete Matches", "Please select at least one match to delete.")
            return
        
        # Confirm deletion
        confirm = messagebox.askyesno(
            "Confirm Deletion",
            f"Are you sure you want to delete {len(selected_items)} selected match(es)? This cannot be undone."
        )
        
        if not confirm:
            return
        
        # Delete matches
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        deleted_count = 0
        for game_id in selected_items:
            try:
                # Delete associated events first (because of foreign key)
                cursor.execute("DELETE FROM match_events WHERE game_id = ?", (game_id,))
                
                # Delete the match
                cursor.execute("DELETE FROM matches WHERE game_id = ?", (game_id,))
                deleted_count += 1
            except sqlite3.Error as e:
                self.log_error(f"Error deleting match {game_id}: {e}")
        
        conn.commit()
        conn.close()
        
        messagebox.showinfo("Deletion Complete", f"{deleted_count} match(es) deleted.")
        # Refresh the view
        self.load_history_tab_data()
    
    def export_selected_matches(self):
        """Export only selected matches to CSV"""
        selected_items = self.history_tree.selection()
        if not selected_items:
            messagebox.showinfo("Export Matches", "Please select at least one match to export.")
            return
        
        # Ask for filename
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export Selected Matches"
        )
        
        if not filename:
            return
        
        # Export the selected matches
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Prepare placeholders for the IN clause
        placeholders = ', '.join(['?'] * len(selected_items))
        
        query = f"""
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
            WHERE
                m.game_id IN ({placeholders})
        """
        
        cursor.execute(query, selected_items)
        matches_to_export = cursor.fetchall() # Renamed to avoid conflict
        
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
            for match_row in matches_to_export: # Use the fetched data
                writer.writerow(match_row)
        
        conn.close()
        
        messagebox.showinfo("Export Complete", f"Successfully exported {len(matches_to_export)} matches to {filename}")
    
    def load_card_stats_data(self, event=None):
        """Load and display card statistics with extended metrics."""
        for item in self.card_stats_tree.get_children():
            self.card_stats_tree.delete(item)

        #selected_deck_name = self.card_stats_deck_filter_var.get()
        selected_season = self.card_stats_season_filter_var.get()

        #print(f"\nDEBUG load_card_stats_data (Extended): Filtering for deck: '{selected_deck_name}', season: '{selected_season}'")

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # --- Part 1: Get all relevant matches and the cards in their decks ---
        match_deck_query_parts = ["""
            SELECT 
                m.game_id, m.result, m.cubes_changed, d.card_ids_json 
            FROM 
                matches m
            JOIN 
                decks d ON m.deck_id = d.id
            WHERE 1=1 
        """]
        match_deck_params = []

        if self.card_stats_selected_deck_names: # If set is not empty
            placeholders = ', '.join(['?'] * len(self.card_stats_selected_deck_names))
            match_deck_query_parts.append(f"AND d.deck_name IN ({placeholders})")
            match_deck_params.extend(list(self.card_stats_selected_deck_names))
        
        
        if selected_season != "All Seasons":
            match_deck_query_parts.append("AND m.season = ?")
            match_deck_params.append(selected_season)
        
        cursor.execute(" ".join(match_deck_query_parts), tuple(match_deck_params))
        all_match_deck_data = cursor.fetchall()
        
        if not all_match_deck_data:
            self.card_stats_summary_var.set(f"No match data for {selected_deck_name} / {selected_season}")
            conn.close()
            return

        # --- Part 2: Get all 'drawn' and 'played' events for local player for these matches ---
        game_ids_for_events = [md[0] for md in all_match_deck_data]
        event_query_parts = [f"""
            SELECT game_id, card_def_id, event_type 
            FROM match_events 
            WHERE player_type = 'local' 
              AND (event_type = 'drawn' OR event_type = 'played')
              AND game_id IN ({','.join(['?'] * len(game_ids_for_events))})
        """]
        # No need for deck/season filter here as game_ids are already filtered
        cursor.execute(" ".join(event_query_parts), tuple(game_ids_for_events))
        all_event_data = cursor.fetchall()
        conn.close() # Close DB connection once data is fetched

        # --- Part 3: Process the data ---
        # Organize events by game_id
        game_events = defaultdict(lambda: {"drawn": set(), "played": set()})
        for game_id, card_def_id, event_type in all_event_data:
            if event_type == 'drawn':
                game_events[game_id]["drawn"].add(card_def_id)
            elif event_type == 'played':
                game_events[game_id]["played"].add(card_def_id)
                game_events[game_id]["drawn"].add(card_def_id) # If played, it must have been drawn

        # Initialize card performance statistics
        # Key: card_def_id
        # Value: dict of stats
        card_performance = defaultdict(lambda: {
            "total_games_in_deck": 0, # Games where this card was part of the deck used
            "drawn_games": 0, "drawn_wins": 0, "drawn_cubes": 0,
            "played_games": 0, "played_wins": 0, "played_cubes": 0,
            "not_drawn_games": 0, "not_drawn_wins": 0, "not_drawn_cubes": 0,
            "not_played_games": 0, "not_played_wins": 0, "not_played_cubes": 0, # Not played (but could have been drawn)
        })

        # Iterate through each match
        for game_id, result, cubes, deck_cards_json_str in all_match_deck_data:
            cubes_val = cubes if cubes is not None else 0
            is_win = (result == 'win')
            
            try:
                deck_cards_for_this_game = set(json.loads(deck_cards_json_str))
            except (json.JSONDecodeError, TypeError):
                print(f"WARN: Could not parse deck_cards_json for game {game_id}: {deck_cards_json_str}")
                continue # Skip this match if deck is unreadable

            game_specific_drawn_cards = game_events[game_id]["drawn"]
            game_specific_played_cards = game_events[game_id]["played"]

            for card_id in deck_cards_for_this_game: # Iterate over all cards that were in the deck for this match
                stats = card_performance[card_id]
                stats["total_games_in_deck"] += 1

                was_drawn = card_id in game_specific_drawn_cards
                was_played = card_id in game_specific_played_cards

                if was_drawn:
                    stats["drawn_games"] += 1
                    stats["drawn_cubes"] += cubes_val
                    if is_win:
                        stats["drawn_wins"] += 1
                else: # Not drawn
                    stats["not_drawn_games"] += 1
                    stats["not_drawn_cubes"] += cubes_val
                    if is_win:
                        stats["not_drawn_wins"] += 1
                
                if was_played:
                    stats["played_games"] += 1
                    stats["played_cubes"] += cubes_val
                    if is_win:
                        stats["played_wins"] += 1
                else: # Not played (but was in deck)
                    stats["not_played_games"] += 1
                    stats["not_played_cubes"] += cubes_val
                    if is_win:
                        stats["not_played_wins"] += 1
        
        # --- Part 4: Populate Treeview ---
        if not card_performance:
            self.card_stats_summary_var.set(f"No card performance data for {selected_deck_name} / {selected_season}")
            return

        for card_def, stats in card_performance.items():
            card_name = card_def
            if self.card_db and self.display_card_names_var.get() and card_def in self.card_db:
                card_name = self.card_db[card_def].get('name', card_def)

            # Calculate percentages and averages, handling division by zero
            drawn_win_pct = (stats["drawn_wins"] / stats["drawn_games"] * 100) if stats["drawn_games"] > 0 else 0.0
            avg_cubes_drawn = (stats["drawn_cubes"] / stats["drawn_games"]) if stats["drawn_games"] > 0 else 0.0
            
            played_win_pct = (stats["played_wins"] / stats["played_games"] * 100) if stats["played_games"] > 0 else 0.0
            avg_cubes_played = (stats["played_cubes"] / stats["played_games"]) if stats["played_games"] > 0 else 0.0

            not_drawn_win_pct = (stats["not_drawn_wins"] / stats["not_drawn_games"] * 100) if stats["not_drawn_games"] > 0 else 0.0
            avg_cubes_not_drawn = (stats["not_drawn_cubes"] / stats["not_drawn_games"]) if stats["not_drawn_games"] > 0 else 0.0
            
            not_played_win_pct = (stats["not_played_wins"] / stats["not_played_games"] * 100) if stats["not_played_games"] > 0 else 0.0
            avg_cubes_not_played = (stats["not_played_cubes"] / stats["not_played_games"]) if stats["not_played_games"] > 0 else 0.0
            
            # --- NEW: Calculate Delta Cubes ---
            # Delta Cubes (Played vs Not Played)
            # Only meaningful if both played_games and not_played_games have entries
            delta_cubes_played_vs_not = 0.0
            if stats["played_games"] > 0 and stats["not_played_games"] > 0:
                delta_cubes_played_vs_not = avg_cubes_played - avg_cubes_not_played
            elif stats["played_games"] > 0: # Played but never *not* played (e.g. card always played if in deck)
                 delta_cubes_played_vs_not = avg_cubes_played # Or could be marked N/A
            elif stats["not_played_games"] > 0: # Never played, but sometimes not played
                 delta_cubes_played_vs_not = -avg_cubes_not_played # Or N/A

            # Delta Cubes (Drawn vs Not Drawn)
            # Only meaningful if both drawn_games and not_drawn_games have entries
            delta_cubes_drawn_vs_not = 0.0
            if stats["drawn_games"] > 0 and stats["not_drawn_games"] > 0:
                delta_cubes_drawn_vs_not = avg_cubes_drawn - avg_cubes_not_drawn
            elif stats["drawn_games"] > 0: # Drawn but never *not* drawn
                delta_cubes_drawn_vs_not = avg_cubes_drawn
            elif stats["not_drawn_games"] > 0: # Never drawn
                delta_cubes_drawn_vs_not = -avg_cubes_not_drawn

            self.card_stats_tree.insert(
                "", "end",
                values=(
                    card_name, # Card
                    stats["drawn_games"], f"{drawn_win_pct:.1f}%", # Drawn Games, Drawn Win %
                    stats["drawn_cubes"], f"{avg_cubes_drawn:.2f}",  # Net Cubes (Drawn), Avg Cubes (Drawn)
                    
                    stats["played_games"], f"{played_win_pct:.1f}%", # Played Games, Played Win %
                    stats["played_cubes"], f"{avg_cubes_played:.2f}", # Net Cubes (Played), Avg Cubes (Played)

                    stats["not_drawn_games"], f"{not_drawn_win_pct:.1f}%", # Not Drawn Games, Not Drawn Win %
                    stats["not_drawn_cubes"], f"{avg_cubes_not_drawn:.2f}", # Net Cubes (Not Drawn), Avg Cubes (Not Drawn)

                    stats["not_played_games"], f"{not_played_win_pct:.1f}%", # Not Played Games, Not Played Win %
                    stats["not_played_cubes"], f"{avg_cubes_not_played:.2f}", # Net Cubes (Not Played), Avg Cubes (Not Played)

                    f"{delta_cubes_drawn_vs_not:.2f}",  # Delta C (Drawn vs ND)
                    f"{delta_cubes_played_vs_not:.2f}"  # Delta C (Played vs NP)                    
                ),
                tags=(card_def,)
            )

        filter_msg = self.card_stats_deck_filter_display_var.get() # NEW
        if selected_season != "All Seasons":
            filter_msg += f", Season: {selected_season}"
        self.card_stats_summary_var.set(f"Card Stats ({filter_msg}). Unique cards processed: {len(card_performance)}")

        if self.card_stats_view_var.get() == "Chart":
            self.update_card_stats_chart(card_performance)
    
    def update_card_stats_chart(self, card_performance):
        """Update the card stats chart with current data"""
        # Clear the figure
        self.card_stats_figure.clear()
        
        # Create subplots
        ax1 = self.card_stats_figure.add_subplot(211)  # Win rates
        ax2 = self.card_stats_figure.add_subplot(212)  # Cube values
        
        # Prepare data for plotting
        cards = []
        drawn_win_rates = []
        played_win_rates = []
        net_cubes_list = [] # Renamed to avoid conflict with a variable name 'net_cubes' if it exists
        avg_cubes_list = [] # Renamed
        
        # Get top 10 most played cards by win rate
        sorted_cards_data = sorted( # Renamed to avoid conflict
            [(card_id, stats) for card_id, stats in card_performance.items() if len(stats["played_games"]) > 0],
            key=lambda x: len(x[1]["played_games"]) * (x[1]["played_wins"] / len(x[1]["played_games"]) if len(x[1]["played_games"]) > 0 else 0),
            reverse=True
        )[:10]
        
        for card_id, stats in sorted_cards_data:
            # Get card name if available
            card_name = card_id
            if self.card_db and self.display_card_names_var.get() and card_id in self.card_db:
                card_name = self.card_db[card_id].get('name', card_id)
            
            cards.append(card_name)
            
            # Calculate statistics
            drawn_win_rate = (stats["drawn_wins"] / len(stats["drawn_games"]) * 100) if len(stats["drawn_games"]) > 0 else 0
            played_win_rate = (stats["played_wins"] / len(stats["played_games"]) * 100) if len(stats["played_games"]) > 0 else 0
            avg_cube_value = stats["played_cubes"] / len(stats["played_games"]) if len(stats["played_games"]) > 0 else 0
            
            drawn_win_rates.append(drawn_win_rate)
            played_win_rates.append(played_win_rate)
            net_cubes_list.append(stats["played_cubes"])
            avg_cubes_list.append(avg_cube_value)
        
        # Reverse lists for better display (highest values at top)
        cards.reverse()
        drawn_win_rates.reverse()
        played_win_rates.reverse()
        net_cubes_list.reverse()
        avg_cubes_list.reverse()
        
        # Set up colors from the theme
        win_color = self.config['Colors']['win']
        loss_color = self.config['Colors']['loss']
        neutral_color = self.config['Colors']['neutral']
        bg_color = self.config['Colors']['bg_main']
        fg_color = self.config['Colors']['fg_main']
        
        # Plot win rates
        y_pos = range(len(cards))
        ax1.barh(y_pos, played_win_rates, height=0.4, align='center', color=win_color, alpha=0.8, label='Played Win %')
        ax1.barh([y + 0.4 for y in y_pos], drawn_win_rates, height=0.4, align='center', color=neutral_color, alpha=0.8, label='Drawn Win %')
        
        # Add a vertical line at 50% win rate
        ax1.axvline(x=50, color=fg_color, linestyle='--', alpha=0.5)
        
        # Set up axes
        ax1.set_yticks(y_pos)
        ax1.set_yticklabels(cards)
        ax1.set_xlabel('Win %')
        ax1.set_title('Card Win Rates')
        ax1.legend()
        
        # Set limits
        ax1.set_xlim(0, 100)
        
        # Plot cube values
        ax2.barh(y_pos, avg_cubes_list, height=0.8, align='center', 
               color=[win_color if avg > 0 else loss_color for avg in avg_cubes_list], alpha=0.8)
        
        # Add a vertical line at 0 cubes
        ax2.axvline(x=0, color=fg_color, linestyle='--', alpha=0.5)
        
        # Set up axes
        ax2.set_yticks(y_pos)
        ax2.set_yticklabels(cards)
        ax2.set_xlabel('Avg. Cubes per Game')
        ax2.set_title('Card Cube Value')
        
        # Set theme colors
        for ax_item in [ax1, ax2]: # Renamed to avoid conflict
            ax_item.set_facecolor(bg_color)
            ax_item.tick_params(colors=fg_color)
            ax_item.xaxis.label.set_color(fg_color)
            ax_item.yaxis.label.set_color(fg_color)
            ax_item.title.set_color(fg_color)
            for spine in ax_item.spines.values():
                spine.set_color(fg_color)
        
        self.card_stats_figure.patch.set_facecolor(bg_color)
        
        # Adjust layout and redraw
        self.card_stats_figure.tight_layout()
        self.card_stats_canvas.draw()
    
    def toggle_card_stats_view(self):
        """Toggle between table and chart view for card stats"""
        view_mode = self.card_stats_view_var.get()
        
        if view_mode == "Table":
            # Show table view
            self.card_stats_chart_frame.pack_forget()
            self.card_stats_table_frame.pack(fill=tk.BOTH, expand=True)
        else:
            # Show chart view
            self.card_stats_table_frame.pack_forget()
            self.card_stats_chart_frame.pack(fill=tk.BOTH, expand=True)
            
            # Update the chart
            # Get current card performance data from the treeview
            card_performance = {}
            
            for item_id in self.card_stats_tree.get_children():
                values = self.card_stats_tree.item(item_id, "values")
                card_name = values[0]
                
                # Try to get card ID
                card_id = card_name
                for cid, card_info in self.card_db.items():
                    if card_info.get('name') == card_name:
                        card_id = cid
                        break
                
                drawn_games = int(values[1])
                drawn_win_pct = float(values[2].replace("%", ""))
                played_games = int(values[3])
                played_win_pct = float(values[4].replace("%", ""))
                played_cubes = int(values[5]) if values[5] else 0
                
                # Calculate derived values
                drawn_wins = int(drawn_games * drawn_win_pct / 100)
                played_wins = int(played_games * played_win_pct / 100)
                
                card_performance[card_id] = {
                    "drawn_games": set(range(drawn_games)),  # Dummy set of appropriate size
                    "drawn_wins": drawn_wins,
                    "played_games": set(range(played_games)),  # Dummy set of appropriate size
                    "played_wins": played_wins,
                    "played_cubes": played_cubes
                }
            
            self.update_card_stats_chart(card_performance)
    
    def on_card_stats_select(self, event):
        """Handle selection of a card in the card stats view"""
        selected_item = self.card_stats_tree.focus()
        if not selected_item:
            return
        
        # Get the card details
        values = self.card_stats_tree.item(selected_item, "values")
        card_name = values[0]
        
        # Look up the card ID
        card_id = None
        for cid, card_info in self.card_db.items():
            if card_info.get('name') == card_name or cid == card_name:
                card_id = cid
                break
        
        if card_id:
            # Create and display a tooltip for this card
            # event_x = self.root.winfo_pointerx() # Not used directly by show_tooltip
            # event_y = self.root.winfo_pointery()
            self.card_tooltip.show_tooltip(card_id, None) # Pass None for event if not relevant for positioning
    
    def load_matchup_data(self, event=None):
        """Load matchup statistics"""
        # Get filter values
        selected_deck = self.matchup_deck_filter_var.get()
        selected_season = self.matchup_season_filter_var.get()
        
        # Clear current data
        for item in self.matchup_tree.get_children():
            self.matchup_tree.delete(item)
        
        # Clear details
        for item in self.revealed_cards_tree.get_children():
            self.revealed_cards_tree.delete(item)
            
        for item in self.matchup_history_tree.get_children():
            self.matchup_history_tree.delete(item)
            
        self.matchup_summary_var.set("Select an opponent to view matchup details")
        
        # Connect to database
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Build query
        query_parts = ["""
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
            LEFT JOIN
                decks d ON m.deck_id = d.id
            WHERE 
                m.opponent_player_name IS NOT NULL
                AND m.opponent_player_name != 'Opponent'
        """]
        
        params = []
        
        if selected_deck != "All Decks":
            query_parts.append("AND d.deck_name = ?")
            params.append(selected_deck)
        
        if selected_season != "All Seasons":
            query_parts.append("AND m.season = ?")
            params.append(selected_season)
        
        query_parts.append("GROUP BY m.opponent_player_name ORDER BY matches DESC, wins DESC")
        final_query = " ".join(query_parts)
        
        cursor.execute(final_query, tuple(params))
        matchup_data = cursor.fetchall()
        
        # Insert data into treeview
        for row in matchup_data:
            name, matches, wins, losses, ties, net_cubes, _ = row
            
            # Calculate win rate
            win_rate = (wins / matches * 100) if matches > 0 else 0
            
            # Calculate average cubes
            avg_cubes = (net_cubes / matches) if matches > 0 and net_cubes is not None else 0
            
            self.matchup_tree.insert(
                "", "end",
                values=(
                    name,
                    matches,
                    f"{win_rate:.1f}%",
                    wins,
                    losses,
                    ties,
                    net_cubes if net_cubes is not None else 0,
                    f"{avg_cubes:.2f}"
                ),
                tags=(name,)  # Use opponent name as tag
            )
        
        conn.close()
    
    def on_matchup_select(self, event):
        """Handle selection of an opponent in the matchup view"""
        selected_item = self.matchup_tree.focus()
        if not selected_item:
            return
        
        # Get the opponent name
        values = self.matchup_tree.item(selected_item, "values")
        opponent_name = values[0]
        
        # Update details
        self.load_matchup_details(opponent_name)
    
    def load_matchup_details(self, opponent_name):
        """Load detailed matchup information for an opponent"""
        # Get filter values
        selected_deck = self.matchup_deck_filter_var.get()
        selected_season = self.matchup_season_filter_var.get()

        print(f"DEBUG: Loading matchup details for Opponent: '{opponent_name}', Deck Filter: '{selected_deck}', Season Filter: '{selected_season}'") # Debug Print

        # Clear current data in the details section
        for item in self.revealed_cards_tree.get_children():
            self.revealed_cards_tree.delete(item)
        for item in self.matchup_history_tree.get_children():
            self.matchup_history_tree.delete(item)
        self.matchup_summary_var.set("Loading details...") # Indicate loading

        # Connect to database
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        try:
            # --- Get Matchup Summary ---
            query_parts_summary = ["""
                SELECT
                    COUNT(*) as matches,
                    SUM(CASE WHEN m.result = 'win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN m.result = 'loss' THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN m.result = 'tie' THEN 1 ELSE 0 END) as ties,
                    SUM(m.cubes_changed) as net_cubes,
                    SUM(CASE WHEN m.cubes_changed > 0 THEN 1 ELSE 0 END) as cube_up_games,
                    AVG(m.turns_taken) as avg_turns
                FROM
                    matches m
                LEFT JOIN
                    decks d ON m.deck_id = d.id
                WHERE
                    m.opponent_player_name = ?
            """]
            params_summary = [opponent_name]

            if selected_deck != "All Decks":
                query_parts_summary.append("AND d.deck_name = ?")
                params_summary.append(selected_deck)
            if selected_season != "All Seasons":
                query_parts_summary.append("AND m.season = ?")
                params_summary.append(selected_season)

            final_query_summary = " ".join(query_parts_summary)
            # print(f"DEBUG: Summary Query: {final_query_summary}") # Optional Debug
            # print(f"DEBUG: Summary Params: {params_summary}")    # Optional Debug
            cursor.execute(final_query_summary, tuple(params_summary))
            summary_data = cursor.fetchone()

            matches = 0 # Default value
            if summary_data and summary_data[0] is not None and summary_data[0] > 0:
                matches, wins, losses, ties, net_cubes, cube_up_games, avg_turns = summary_data
                wins = wins if wins is not None else 0
                losses = losses if losses is not None else 0
                ties = ties if ties is not None else 0
                net_cubes = net_cubes if net_cubes is not None else 0
                cube_up_games = cube_up_games if cube_up_games is not None else 0

                win_rate = (wins / matches * 100) if matches > 0 else 0
                summary_text = f"Opponent: {opponent_name}\n"
                summary_text += f"Matches: {matches}, Wins: {wins} ({win_rate:.1f}%), Losses: {losses}, Ties: {ties}\n"
                summary_text += f"Net Cubes: {net_cubes}, "
                summary_text += f"Cube Up %: {(cube_up_games / matches * 100) if matches > 0 else 0:.1f}%, "
                avg_turns_str = f"{avg_turns:.1f}" if avg_turns is not None else "N/A"
                summary_text += f"Avg Turns: {avg_turns_str}"
                #summary_text += f"Avg Turns: {avg_turns:.1f if avg_turns is not None else 'N/A'}"
                self.matchup_summary_var.set(summary_text)
            else:
                 self.matchup_summary_var.set(f"Opponent: {opponent_name}\nNo match data found for the selected filters.")

            # --- Get Revealed Cards (only if matches > 0) ---
            if matches > 0:
                query_parts_revealed = ["""
                    SELECT
                        m.opp_revealed_cards_json
                    FROM
                        matches m
                    LEFT JOIN
                        decks d ON m.deck_id = d.id
                    WHERE
                        m.opponent_player_name = ?
                        AND m.opp_revealed_cards_json IS NOT NULL
                        AND m.opp_revealed_cards_json != 'null'
                        AND m.opp_revealed_cards_json != '[]'
                """]
                params_revealed = [opponent_name]

                if selected_deck != "All Decks":
                    query_parts_revealed.append("AND d.deck_name = ?")
                    params_revealed.append(selected_deck)
                if selected_season != "All Seasons":
                    query_parts_revealed.append("AND m.season = ?")
                    params_revealed.append(selected_season)

                final_query_revealed = " ".join(query_parts_revealed)
                # print(f"DEBUG: Revealed Query: {final_query_revealed}") # Optional Debug
                # print(f"DEBUG: Revealed Params: {params_revealed}")    # Optional Debug
                cursor.execute(final_query_revealed, tuple(params_revealed))
                revealed_cards_data = cursor.fetchall()

                revealed_card_counter = Counter()
                valid_revealed_games = 0 # Count games where parsing worked
                for row in revealed_cards_data:
                    try:
                        cards_json = row[0]
                        if cards_json:
                            cards = json.loads(cards_json)
                            if isinstance(cards, list): # Ensure it's a list
                                revealed_card_counter.update(cards)
                                valid_revealed_games += 1 # Count this game if parse successful
                    except (json.JSONDecodeError, TypeError) as json_e:
                         print(f"WARN: Error parsing revealed cards JSON for opponent {opponent_name}: {json_e} - JSON: {cards_json[:100]}...")
                         continue # Skip this row

                most_common_cards = revealed_card_counter.most_common(20)
                for card_id, count in most_common_cards:
                    card_name = card_id
                    if self.card_db and self.display_card_names_var.get() and card_id in self.card_db:
                        card_name = self.card_db[card_id].get('name', card_id)

                    # Percentage based on games where revealed cards were successfully parsed
                    percentage = (count / valid_revealed_games * 100) if valid_revealed_games > 0 else 0

                    self.revealed_cards_tree.insert(
                        "", "end",
                        values=(card_name, count, f"{percentage:.1f}%"),
                        tags=(card_id,)
                    )

            # --- Get Match History (only if matches > 0) ---
            if matches > 0:
                query_parts_history = ["""
                    SELECT
                        m.timestamp_ended,
                        COALESCE(d.deck_name, 'Unknown Deck'),
                        m.result,
                        m.cubes_changed,
                        m.opp_revealed_cards_json,
                        m.notes,
                        m.game_id -- Include game_id for potential future use/debugging
                    FROM
                        matches m
                    LEFT JOIN
                        decks d ON m.deck_id = d.id
                    WHERE
                        m.opponent_player_name = ?
                """]
                params_history = [opponent_name]

                if selected_deck != "All Decks":
                    query_parts_history.append("AND d.deck_name = ?")
                    params_history.append(selected_deck)
                if selected_season != "All Seasons":
                    query_parts_history.append("AND m.season = ?")
                    params_history.append(selected_season)

                query_parts_history.append("ORDER BY m.timestamp_ended DESC")
                final_query_history = " ".join(query_parts_history)
                # print(f"DEBUG: History Query: {final_query_history}") # Optional Debug
                # print(f"DEBUG: History Params: {params_history}")    # Optional Debug
                cursor.execute(final_query_history, tuple(params_history))
                history_data = cursor.fetchall()

                for row in history_data:
                    timestamp, deck_name, result, cubes, revealed_cards_json, notes, game_id = row

                    try: date_str = datetime.datetime.strptime(timestamp.split('.')[0], "%Y-%m-%d %H:%M:%S").strftime("%y-%m-%d %H:%M")
                    except: date_str = timestamp

                    revealed_cards_str = "None"
                    if revealed_cards_json and revealed_cards_json.lower() != 'null':
                        try:
                            cards = json.loads(revealed_cards_json)
                            if cards:
                                card_display_list = []
                                if self.card_db and self.display_card_names_var.get():
                                    for card_id_rev in cards:
                                        card_display_list.append(self.card_db.get(card_id_rev, {}).get('name', card_id_rev))
                                else:
                                     card_display_list = cards
                                revealed_cards_str = ", ".join(card_display_list)
                        except json.JSONDecodeError:
                            revealed_cards_str = "Error"

                    self.matchup_history_tree.insert(
                        "", "end",
                        values=(
                            date_str,
                            deck_name,
                            result.capitalize() if result else "Unknown",
                            cubes if cubes is not None else 0,
                            revealed_cards_str
                        ),
                        iid=game_id, # Use game_id as iid
                        tags=(result,)
                    )

        except sqlite3.Error as db_e:
             print(f"ERROR: Database error loading matchup details for {opponent_name}: {db_e}")
             self.log_error(f"DB Error loading details for {opponent_name}: {db_e}", traceback.format_exc())
             self.matchup_summary_var.set(f"Error loading details for {opponent_name}.")
        except Exception as e:
             print(f"ERROR: Unexpected error loading matchup details for {opponent_name}: {e}")
             self.log_error(f"Error loading details for {opponent_name}: {e}", traceback.format_exc())
             self.matchup_summary_var.set(f"Error loading details for {opponent_name}.")
        finally:
            if conn:
                 conn.close()
    
    def load_location_stats(self, event=None):
        """Load and display location statistics"""
        # Clear current data
        for item in self.location_stats_tree.get_children():
            self.location_stats_tree.delete(item)
        
        # Get filter values
        selected_deck = self.location_deck_filter_var.get()
        selected_season = self.location_season_filter_var.get()
        
        # Connect to database
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Build query for locations
        # Construct the subquery parts with aliases for deck name and season
        # This ensures filters can be applied correctly within each part of the UNION ALL
        
        subquery_template = """
            SELECT 
                m.loc_{loc_num}_def_id as loc_id, m.result, m.cubes_changed, d.deck_name as deck_name_alias, m.season as season_alias
            FROM 
                matches m
            LEFT JOIN
                decks d ON m.deck_id = d.id
            WHERE 
                m.loc_{loc_num}_def_id IS NOT NULL AND m.loc_{loc_num}_def_id != ''
        """

        subqueries = []
        for i in range(1, 4):
            subqueries.append(subquery_template.format(loc_num=i))

        # Apply filters to each subquery
        filter_conditions = []
        params_for_each_subquery = []

        if selected_deck != "All Decks":
            filter_conditions.append("deck_name_alias = ?")
            params_for_each_subquery.append(selected_deck)
        
        if selected_season != "All Seasons":
            filter_conditions.append("season_alias = ?")
            params_for_each_subquery.append(selected_season)

        if filter_conditions:
            filter_string = " AND " + " AND ".join(filter_conditions)
            subqueries = [sq.replace("WHERE \n                m.loc_", f"WHERE \n                m.loc_") + filter_string for sq in subqueries]
        
        # Combine subqueries with UNION ALL
        full_subquery = " UNION ALL ".join(subqueries)

        query = f"""
            SELECT 
                loc_id,
                COUNT(*) as matches,
                SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN result = 'tie' THEN 1 ELSE 0 END) as ties,
                SUM(cubes_changed) as net_cubes
            FROM (
                {full_subquery}
            ) AS all_locations
            GROUP BY loc_id 
            ORDER BY matches DESC
        """
        
        # The parameters list needs to be repeated for each subquery
        final_params = params_for_each_subquery * len(subqueries)

        cursor.execute(query, tuple(final_params))
        location_data = cursor.fetchall()
        
        # Insert data into treeview
        for row in location_data:
            loc_id, matches, wins, losses, ties, net_cubes = row
            
            # Get location name if available
            loc_name = loc_id
            if self.card_db and self.display_card_names_var.get() and loc_id in self.card_db:
                loc_name = self.card_db[loc_id].get('name', loc_id)
            
            # Calculate statistics
            win_rate = (wins / matches * 100) if matches > 0 else 0
            avg_cubes = (net_cubes / matches) if matches > 0 and net_cubes is not None else 0
            
            self.location_stats_tree.insert(
                "", "end",
                values=(
                    loc_name,
                    matches,
                    f"{win_rate:.1f}%",
                    wins,
                    losses,
                    ties,
                    net_cubes if net_cubes is not None else 0,
                    f"{avg_cubes:.2f}"
                ),
                tags=(loc_id,)  # Use location ID as tag
            )
        
        conn.close()
        
        # If in chart view, update the chart
        if self.location_view_var.get() == "Chart":
            self.update_location_chart()
    
    def toggle_location_view(self):
        """Toggle between table and chart view for location stats"""
        view_mode = self.location_view_var.get()
        
        if view_mode == "Table":
            # Show table view
            self.location_chart_frame.pack_forget()
            self.location_table_frame.pack(fill=tk.BOTH, expand=True)
        else:
            # Show chart view
            self.location_table_frame.pack_forget()
            self.location_chart_frame.pack(fill=tk.BOTH, expand=True)
            
            # Update the chart
            self.update_location_chart()
    
    def update_location_chart(self):
        """Update the location stats chart with current data"""
        # Clear the figure
        self.location_figure.clear()
        
        # Create subplots
        ax1 = self.location_figure.add_subplot(211)  # Win rates
        ax2 = self.location_figure.add_subplot(212)  # Cube values
        
        # Get data from treeview
        locations = []
        matches = []
        win_rates = []
        net_cubes_list = [] # Renamed to avoid conflict
        
        # Get top 15 locations by number of matches
        items = self.location_stats_tree.get_children()
        data = []
        
        for item in items:
            values = self.location_stats_tree.item(item, "values")
            
            if len(values) >= 8:  # Make sure we have all values
                location = values[0]
                match_count = int(values[1])
                win_rate = float(values[2].replace("%", ""))
                net_cube_val = float(values[6]) if values[6] else 0 # Renamed
                
                data.append((location, match_count, win_rate, net_cube_val))
        
        # Sort by number of matches and take top 15
        data.sort(key=lambda x: x[1], reverse=True)
        data = data[:15]
        
        # Separate data into lists
        for loc, match_count, wr, nc_val in data: # Use renamed variable
            locations.append(loc)
            matches.append(match_count)
            win_rates.append(wr)
            net_cubes_list.append(nc_val)
        
        # Reverse lists for better display (highest values at top)
        locations.reverse()
        matches.reverse()
        win_rates.reverse()
        net_cubes_list.reverse()
        
        # Set up colors from the theme
        win_color = self.config['Colors']['win']
        loss_color = self.config['Colors']['loss']
        # neutral_color = self.config['Colors']['neutral'] # Not used here
        bg_color = self.config['Colors']['bg_main']
        fg_color = self.config['Colors']['fg_main']
        
        # Plot win rates with match count as bar width
        y_pos = range(len(locations))
        
        # Normalize matches for bar width
        max_matches = max(matches) if matches else 1
        normalized_matches = [m/max_matches*0.8 for m in matches]
        
        # Plot win rates
        bars = ax1.barh(y_pos, win_rates, height=normalized_matches, align='center', color=win_color, alpha=0.8)
        
        # Add match count annotation
        for i, bar in enumerate(bars):
            ax1.text(
                bar.get_width() + 2, 
                bar.get_y() + bar.get_height()/2, 
                f"{matches[i]} matches", 
                va='center', 
                color=fg_color,
                fontsize=8
            )
        
        # Add a vertical line at 50% win rate
        ax1.axvline(x=50, color=fg_color, linestyle='--', alpha=0.5)
        
        # Set up axes
        ax1.set_yticks(y_pos)
        ax1.set_yticklabels(locations)
        ax1.set_xlabel('Win Rate (%)')
        ax1.set_title('Location Win Rates')
        
        # Set limits
        ax1.set_xlim(0, 100)
        
        # Plot cube values
        bars2 = ax2.barh(
            y_pos, net_cubes_list, height=normalized_matches, align='center', 
            color=[win_color if c > 0 else loss_color for c in net_cubes_list], alpha=0.8
        )
        
        # Add avg cubes annotation
        for i, bar in enumerate(bars2):
            avg_cubes_val = net_cubes_list[i] / matches[i] if matches[i] > 0 else 0 # Renamed
            ax2.text(
                bar.get_width() + 2 if net_cubes_list[i] >= 0 else bar.get_width() - 2, 
                bar.get_y() + bar.get_height()/2, 
                f"Avg: {avg_cubes_val:.2f}", 
                va='center', 
                ha='left' if net_cubes_list[i] >= 0 else 'right',
                color=fg_color,
                fontsize=8
            )
        
        # Add a vertical line at 0 cubes
        ax2.axvline(x=0, color=fg_color, linestyle='--', alpha=0.5)
        
        # Set up axes
        ax2.set_yticks(y_pos)
        ax2.set_yticklabels(locations)
        ax2.set_xlabel('Net Cubes')
        ax2.set_title('Location Cube Value')
        
        # Set theme colors
        for ax_item in [ax1, ax2]: # Renamed
            ax_item.set_facecolor(bg_color)
            ax_item.tick_params(colors=fg_color)
            ax_item.xaxis.label.set_color(fg_color)
            ax_item.yaxis.label.set_color(fg_color)
            ax_item.title.set_color(fg_color)
            for spine in ax_item.spines.values():
                spine.set_color(fg_color)
        
        self.location_figure.patch.set_facecolor(bg_color)
        
        # Adjust layout and redraw
        self.location_figure.tight_layout()
        self.location_canvas.draw()
    
    def update_trends(self, event=None):
        """Update trend charts based on selected filters"""
        # Get filter values
        days_str = self.trend_days_var.get()
        #selected_decks = self.trend_deck_filter_var.get()
        selected_opponent = self.trend_opponent_filter_var.get()
        
        # Process days value
        if days_str == "All":
            days = None
        else:
            try:
                days = int(days_str)
            except ValueError:
                days = 30  # Default to 30 days
        
        # Calculate trends (daily data for chart)
        dates, win_rates_daily, net_cubes_daily = calculate_win_rate_over_time(self.trend_selected_deck_names if self.trend_selected_deck_names else None , selected_opponent, days)
        
        # Clear existing plots
        self.trend_win_rate_ax.clear()
        self.trend_cubes_ax.clear()
        if hasattr(self, 'trend_cumulative_cubes_ax'): # Remove old twinx axis if exists
            self.trend_cumulative_cubes_ax.remove()
            delattr(self, 'trend_cumulative_cubes_ax')


        # Check if we have data for charts
        if not dates:
            self.trend_win_rate_ax.text(0.5, 0.5, "No daily data for chart", horizontalalignment='center', verticalalignment='center', color=self.config['Colors']['fg_main'])
            self.trend_cubes_ax.text(0.5, 0.5, "No daily data for chart", horizontalalignment='center', verticalalignment='center', color=self.config['Colors']['fg_main'])
        else:
            # Get theme colors
            win_color = self.config['Colors']['win']
            loss_color = self.config['Colors']['loss']
            neutral_color = self.config['Colors']['neutral']
            bg_color = self.config['Colors']['bg_main']
            fg_color = self.config['Colors']['fg_main']
            
            # Convert string dates to datetime objects
            dates_dt = [datetime.datetime.strptime(d, '%Y-%m-%d') for d in dates]
            
            # Plot win rate trend
            self.trend_win_rate_ax.plot(dates_dt, win_rates_daily, marker='o', linestyle='-', color=win_color)
            self.trend_win_rate_ax.axhline(y=50, color=fg_color, linestyle='--', alpha=0.5)
            self.trend_win_rate_ax.set_ylabel('Win Rate (%)')
            self.trend_win_rate_ax.set_title('Win Rate Over Time (Daily)')
            
            self.trend_win_rate_ax.xaxis.set_major_formatter(DateFormatter('%m/%d'))
            self.trend_win_rate_ax.tick_params(axis='x', rotation=45)
            
            min_wr = min(win_rates_daily) if win_rates_daily else 0
            max_wr = max(win_rates_daily) if win_rates_daily else 100
            padding = 10
            self.trend_win_rate_ax.set_ylim(max(0, min_wr - padding), min(100, max_wr + padding))
            
            # Plot net cubes trend (daily)
            self.trend_cubes_ax.plot(dates_dt, net_cubes_daily, marker='s', linestyle='-', color=neutral_color)
            self.trend_cubes_ax.axhline(y=0, color=fg_color, linestyle='--', alpha=0.5)
            self.trend_cubes_ax.set_ylabel('Net Cubes (Daily)')
            self.trend_cubes_ax.set_xlabel('Date')
            self.trend_cubes_ax.set_title('Cube Progression (Daily & Cumulative)')
            
            self.trend_cubes_ax.xaxis.set_major_formatter(DateFormatter('%m/%d'))
            self.trend_cubes_ax.tick_params(axis='x', rotation=45)
            
            # Calculate cumulative cubes
            cumulative_cubes = np.cumsum(net_cubes_daily).tolist()
            
            # Add cumulative line on a twin axis
            self.trend_cumulative_cubes_ax = self.trend_cubes_ax.twinx() # Store twin axis
            cumulative_line_color = win_color if cumulative_cubes and cumulative_cubes[-1] > 0 else loss_color
            self.trend_cumulative_cubes_ax.plot(dates_dt, cumulative_cubes, marker='^', linestyle='--', color=cumulative_line_color, label='Cumulative Cubes')
            self.trend_cumulative_cubes_ax.set_ylabel('Cumulative Cubes', color=cumulative_line_color)
            self.trend_cumulative_cubes_ax.tick_params(axis='y', labelcolor=cumulative_line_color)
            self.trend_cumulative_cubes_ax.spines['right'].set_color(cumulative_line_color)


            # Set theme colors for all axes
            for ax in [self.trend_win_rate_ax, self.trend_cubes_ax, self.trend_cumulative_cubes_ax]:
                ax.set_facecolor(bg_color)
                ax.tick_params(colors=fg_color) # For tick numbers
                ax.xaxis.label.set_color(fg_color)
                ax.yaxis.label.set_color(fg_color) # Primary Y axis label color
                if ax != self.trend_cumulative_cubes_ax : # For primary y-axis label
                     ax.yaxis.label.set_color(fg_color)
                ax.title.set_color(fg_color)
                for spine in ax.spines.values():
                    if ax == self.trend_cumulative_cubes_ax and spine == 'right': # Special handling for twinx right spine
                        continue # Already colored by tick_params and set_ylabel
                    spine.set_color(fg_color)
        
        self.trend_figure.patch.set_facecolor(self.config['Colors']['bg_main'])

        # Fetch summary stats for the period for the labels
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        summary_query_parts = ["""
            SELECT
                COUNT(*) as total_matches,
                SUM(CASE WHEN m.result = 'win' THEN 1 ELSE 0 END) as total_wins,
                SUM(m.cubes_changed) as total_cubes
            FROM
                matches m
            LEFT JOIN
                decks d ON m.deck_id = d.id
            WHERE 1=1
        """]
        summary_params = []

        if days:
            summary_query_parts.append("AND m.timestamp_ended >= date('now', ?)")
            summary_params.append(f'-{days} days')
        else: # All time
             summary_query_parts.append("AND 1=1") # Keep WHERE clause valid

        if self.trend_selected_deck_names: 
            placeholders = ', '.join(['?'] * len(self.trend_selected_deck_names))
            query += f" AND d.deck_name IN ({placeholders})"
            params.extend(list(self.trend_selected_deck_names))
           
        #if selected_deck and selected_deck != "All Decks":
        #    summary_query_parts.append("AND d.deck_name = ?")
        #    summary_params.append(selected_deck)
        
        if selected_opponent and selected_opponent != "All Opponents":
            summary_query_parts.append("AND m.opponent_player_name = ?")
            summary_params.append(selected_opponent)

        final_summary_query = " ".join(summary_query_parts)

        try:
            cursor.execute(final_summary_query, tuple(summary_params))
            summary_results = cursor.fetchone()
        except sqlite3.Error as e:
            print(f"Error fetching trends summary: {e}")
            summary_results = (0, 0, 0) # Default values on error
        finally:
            conn.close()

        # Update summary labels based on the direct query
        if summary_results:
            total_matches_summary, total_wins_summary, total_net_cubes_summary = summary_results
            total_net_cubes_summary = total_net_cubes_summary if total_net_cubes_summary is not None else 0
            avg_win_rate_summary = (total_wins_summary / total_matches_summary * 100) if total_matches_summary > 0 else 0
            avg_cubes_per_game_summary = (total_net_cubes_summary / total_matches_summary) if total_matches_summary > 0 else 0

            self.trend_total_matches_var.set(str(total_matches_summary))
            self.trend_win_rate_var.set(f"{avg_win_rate_summary:.1f}%")
            self.trend_net_cubes_var.set(str(total_net_cubes_summary))
            self.trend_avg_cubes_var.set(f"{avg_cubes_per_game_summary:.2f}")
        else:
            self.trend_total_matches_var.set("0")
            self.trend_win_rate_var.set("0%")
            self.trend_net_cubes_var.set("0")
            self.trend_avg_cubes_var.set("0")

        # Adjust layout and redraw canvas
        self.trend_figure.tight_layout()
        self.trends_canvas.draw()

    def browse_game_state_path(self):
        """Browse for game state file path"""
        initial_dir = None
        current_path = self.game_state_path_var.get()
        if current_path and current_path != "Auto-detected" and os.path.exists(os.path.dirname(current_path)):
             initial_dir = os.path.dirname(current_path)
        elif os.path.exists(get_snap_states_folder()):
             initial_dir = get_snap_states_folder()

        file_path = filedialog.askopenfilename(
            title="Select GameState.json File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=initial_dir
        )
        
        if file_path:
            self.game_state_path_var.set(file_path)
            self.game_state_file_path = file_path # Update the internal path used
    
    def pick_color(self, color_key, color_label_widget):
        """Open color picker for theme customization and update preview"""
        current_color = self.color_vars[color_key].get()
        # askcolor returns (rgb_tuple, hex_string) or (None, None)
        result = colorchooser.askcolor(current_color, title=f"Select {color_key} Color")
        color_code = result[1] if result else None # Get the hex string

        if color_code:
            self.color_vars[color_key].set(color_code)
            # Update the color preview label immediately
            color_label_widget.configure(background=color_code)

    
    def apply_custom_theme(self):
        """Apply custom theme colors"""
        # Update config with custom colors
        for color_key, color_var in self.color_vars.items():
            self.config['Colors'][color_key] = color_var.get()
        
        # Apply theme
        apply_theme(self.root, self.config['Colors'])
        
        # Save config
        save_config(self.config)
        
        # Show confirmation
        messagebox.showinfo("Theme Applied", "Custom theme has been applied and saved.")
    
    def change_theme(self, theme_name):
        """Change to a predefined theme"""
        if theme_name == "light":
            # Light theme colors
            colors = {
                "bg_main": "#f0f0f0",
                "bg_secondary": "#e0e0e0",
                "fg_main": "#202020",
                "accent_primary": "#1976d2",
                "accent_secondary": "#2196f3",
                "win": "#4caf50",
                "loss": "#f44336",
                "neutral": "#ff9800"
            }
        elif theme_name == "dark":
            # Dark theme colors (Catppuccin Mocha inspired)
            colors = DEFAULT_COLORS # Use the defined default
        elif theme_name == "custom":
            # Use current custom theme stored in config
            colors = self.config['Colors']
        else:
            return
        
        # Update config
        for key, value in colors.items():
            self.config['Colors'][key] = value
            if key in self.color_vars:
                self.color_vars[key].set(value)
        
        # Apply theme
        apply_theme(self.root, colors)
        
        # Save config
        save_config(self.config)
    
    def customize_theme(self):
        """Open dialog to customize theme colors"""
        theme_dialog = tk.Toplevel(self.root)
        theme_dialog.title("Customize Theme")
        theme_dialog.geometry("500x400")
        theme_dialog.transient(self.root)
        theme_dialog.grab_set()

        # Apply current theme to dialog
        theme_dialog.configure(background=self.config['Colors']['bg_main'])
        
        # Create color picker widgets
        ttk.Label(theme_dialog, text="Theme Colors", font=("Arial", 14, "bold")).pack(pady=10)
        
        color_frame = ttk.Frame(theme_dialog)
        color_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Create a grid of color pickers
        color_options = [
            ("Background", "bg_main"),
            ("Secondary Background", "bg_secondary"),
            ("Text", "fg_main"),
            ("Primary Accent", "accent_primary"),
            ("Secondary Accent", "accent_secondary"),
            ("Win Color", "win"),
            ("Loss Color", "loss"),
            ("Neutral Color", "neutral")
        ]
        
        # Store references to the color preview labels to update them
        color_preview_labels = {}

        row = 0
        for label_text, color_key in color_options:
            ttk.Label(color_frame, text=label_text + ":").grid(row=row, column=0, sticky="e", padx=(0, 10), pady=5)
            
            # Get the variable holding the color value
            color_var = self.color_vars[color_key]
            
            # Create color display frame and label
            preview_frame = ttk.Frame(color_frame, width=20, height=20, relief="solid", borderwidth=1)
            preview_frame.grid(row=row, column=1, sticky="w", padx=5, pady=5)
            color_label = tk.Label(preview_frame, background=color_var.get(), width=3, height=1)
            color_label.pack(fill=tk.BOTH, expand=True)
            color_preview_labels[color_key] = color_label # Store reference

            # Bind click event to color picker
            color_label.bind("<Button-1>", lambda e, key=color_key, lbl=color_label: self.pick_color(key, lbl))
            
            # Add hexcode entry
            ttk.Entry(color_frame, textvariable=color_var, width=10).grid(row=row, column=2, padx=5, pady=5)
            
            row += 1
        
        # Add buttons
        button_frame = ttk.Frame(theme_dialog)
        button_frame.pack(fill=tk.X, padx=20, pady=20)
        
        ttk.Button(button_frame, text="Apply & Save", command=lambda: [self.apply_custom_theme(), theme_dialog.destroy()]).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=theme_dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Reset to Default", command=lambda: self.reset_theme_to_default(theme_dialog, color_preview_labels)).pack(side=tk.LEFT, padx=5)
    
    def reset_theme_to_default(self, dialog=None, preview_labels=None):
        """Reset theme colors to default"""
        # Set default colors
        for key, value in DEFAULT_COLORS.items():
            self.config['Colors'][key] = value
            if key in self.color_vars:
                self.color_vars[key].set(value)
                # Update preview label in dialog if provided
                if preview_labels and key in preview_labels:
                    preview_labels[key].config(background=value)

        # Apply theme
        apply_theme(self.root, DEFAULT_COLORS)
        
        # Save config
        save_config(self.config)
        
        # Show message if dialog is provided (meaning it was user-initiated)
        if dialog:
            messagebox.showinfo("Theme Reset", "Theme has been reset to default.")
            # No need to destroy dialog, let the user close it or Apply

    def save_settings(self):
        """Save all settings to config file"""
        # Update settings from UI
        self.config['Settings']['auto_update_card_db'] = str(self.auto_update_card_db_var.get())
        self.config['Settings']['check_for_app_updates'] = str(self.check_for_updates_var.get())
        self.config['Settings']['card_name_display'] = str(self.display_card_names_var.get())
        self.config['Settings']['update_interval'] = self.update_interval_var.get()
        self.config['Settings']['max_error_log_entries'] = self.max_error_log_var.get()
        
        # Update card database API
        self.config['CardDB']['api_url'] = self.card_db_api_var.get()
        
        # Save game state path if manually set (or clear if set back to Auto-detected)
        manual_path = self.game_state_path_var.get()
        if manual_path != "Auto-detected":
            self.game_state_file_path = manual_path
            self.config['Settings']['game_state_path'] = manual_path # Optionally save manual path
        else:
            self.game_state_file_path = None # Reset to auto-detect on next loop
            if 'game_state_path' in self.config['Settings']:
                del self.config['Settings']['game_state_path'] # Remove saved path if back to auto
        
        # Save config
        save_config(self.config)
        
        # Show confirmation
        messagebox.showinfo("Settings Saved", "Settings have been saved successfully.")
    
    def export_match_history(self):
        """Export all match history to CSV file"""
        # Ask for filename
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export Match History"
        )
        
        if not filename:
            return
        
        # Export data (exports ALL data, ignoring current filter)
        count = export_match_history_to_csv(filename, deck_filter=None)
        
        # Show confirmation
        messagebox.showinfo(
            "Export Complete", 
            f"Successfully exported {count} matches to {filename}"
        )
    
    def import_match_history(self):
        """Import match history from CSV file"""
        # Ask for filename
        filename = filedialog.askopenfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Import Match History"
        )
        
        if not filename:
            return
        
        # Import data
        success, message = import_match_history_from_csv(filename, self.card_db)
        
        # Show result
        if success:
            messagebox.showinfo("Import Complete", message)
            
            # Refresh data
            self.refresh_all_data()
        else:
            messagebox.showerror("Import Failed", message)
    
    def backup_database(self):
        """Backup the database to a file"""
        # Ask for filename
        backup_path = filedialog.asksaveasfilename(
            defaultextension=".db",
            filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")],
            title="Backup Snap Match History Database",
            initialfile=f"snap_match_history_backup_{time.strftime('%Y%m%d_%H%M%S')}.db"
        )
        
        if not backup_path:
            return
        
        try:
            if not os.path.exists(DB_NAME):
                messagebox.showerror("Backup Failed", f"Database file '{DB_NAME}' not found.")
                return
                
            shutil.copy(DB_NAME, backup_path)
            messagebox.showinfo("Backup Successful", f"Database backed up to:\n{backup_path}")
        except Exception as e:
            self.log_error(f"Database backup failed: {e}", traceback.format_exc())
            messagebox.showerror("Backup Failed", f"Could not backup database:\n{e}")
    
    def reset_database(self):
        """Reset the database (with confirmation)"""
        # Ask for confirmation
        confirm = messagebox.askyesno(
            "Confirm Reset",
            "Are you sure you want to reset the database? This will DELETE ALL your match history and statistics. This cannot be undone.",
            icon=messagebox.WARNING
        )
        
        if not confirm:
            return
        
        # Double-check
        confirm2 = messagebox.askyesno(
            "Final Confirmation",
            "ALL YOUR MATCH DATA WILL BE PERMANENTLY DELETED. Are you absolutely sure?",
            icon=messagebox.WARNING
        )
        
        if not confirm2:
            return
        
        # Offer to backup first
        backup_first = messagebox.askyesno(
            "Backup",
            "Would you like to create a backup before resetting the database?",
            icon=messagebox.QUESTION
        )
        
        if backup_first:
            self.backup_database()
        
        # Reset database
        try:
            # Close connection if open
            try:
                # This is tricky if other threads are using it. Best effort.
                # A better approach would be a connection pool or manager.
                pass # Skip direct close, rely on file removal
            except:
                pass
            
            # Remove database file
            if os.path.exists(DB_NAME):
                os.remove(DB_NAME)
            
            # Reinitialize database
            init_db()
            
            # Refresh data
            self.refresh_all_data()
            
            messagebox.showinfo("Reset Complete", "Database has been reset successfully.")
        except Exception as e:
            self.log_error(f"Database reset failed: {e}", traceback.format_exc())
            messagebox.showerror("Reset Failed", f"Could not reset database:\n{e}")
    
    def open_folder(self, folder_path):
        """Open a folder in file explorer"""
        abs_folder_path = os.path.abspath(folder_path) # Ensure absolute path

        if not os.path.exists(abs_folder_path):
            try:
                 os.makedirs(abs_folder_path)
                 print(f"Created directory: {abs_folder_path}")
            except OSError as e:
                 messagebox.showerror("Error", f"Could not create directory: {abs_folder_path}\n{e}")
                 return

        # Open folder in file explorer
        try:
            if os.name == 'nt':  # Windows
                os.startfile(abs_folder_path)
            elif os.name == 'posix': # macOS, Linux
                try: # Try 'open' first (macOS)
                    os.system(f'open "{abs_folder_path}"')
                except: # Fallback for Linux
                    os.system(f'xdg-open "{abs_folder_path}"')
            else:
                 messagebox.showinfo("Open Folder", f"Cannot automatically open folder on this OS.\nPath: {abs_folder_path}")
        except Exception as e:
             messagebox.showerror("Error", f"Could not open folder: {abs_folder_path}\n{e}")

    def show_about_dialog(self):
        """Show about dialog with app information"""
        about_dialog = tk.Toplevel(self.root)
        about_dialog.title("About Marvel Snap Tracker")
        about_dialog.geometry("400x300")
        about_dialog.transient(self.root)
        about_dialog.grab_set()

        # Apply theme
        about_dialog.configure(background=self.config['Colors']['bg_main'])
        
        # App info
        ttk.Label(about_dialog, text=f"Marvel Snap Tracker v{VERSION}", font=("Arial", 16, "bold")).pack(pady=(20, 5))
        ttk.Label(about_dialog, text="An enhanced tracking tool for Marvel Snap").pack(pady=5)
        
        # Description
        description = ttk.Label(
            about_dialog, 
            text="This application helps you track your Marvel Snap matches, analyze your performance, and improve your gameplay.",
            wraplength=300,
            justify=tk.CENTER
        )
        description.pack(pady=10)
        
        # Features (Optional - uncomment if you want this section)
        # features_frame = ttk.LabelFrame(about_dialog, text="Features", padding=10)
        # features_frame.pack(fill=tk.X, padx=20, pady=10)
        # features_text = """
        # • Live game tracking
        # • Match history
        # • Card statistics
        # • Matchup analysis
        # • Location performance
        # • Win rate trends
        # • Custom themes
        # """
        # ttk.Label(features_frame, text=features_text.strip()).pack()
        
        # Close button
        ttk.Button(about_dialog, text="Close", command=about_dialog.destroy).pack(pady=20)
    
    def show_settings_dialog(self):
        """Show settings dialog by switching to the settings tab"""
        notebook = None
        for widget in self.root.winfo_children():
            if isinstance(widget, ttk.Notebook):
                 notebook = widget
                 break
        
        if notebook:
            for i in range(notebook.index("end")):
                if notebook.tab(i, "text") == "Settings":
                     notebook.select(i)
                     return
            print("ERROR: Could not find Settings tab.")
        else:
            print("ERROR: Could not find main notebook.")

    def update_card_db_command(self):
        """Update card database from API"""
        progress_dialog = tk.Toplevel(self.root)
        progress_dialog.title("Updating Card Database")
        progress_dialog.geometry("300x100")
        progress_dialog.transient(self.root)
        progress_dialog.grab_set()
        progress_dialog.configure(background=self.config['Colors']['bg_main'])

        ttk.Label(progress_dialog, text="Downloading card data...").pack(pady=(20, 10))
        
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(progress_dialog, variable=progress_var, maximum=100)
        progress_bar.pack(fill=tk.X, padx=20)
        
        # Update in a separate thread
        def update_thread():
            try:
                progress_var.set(30)
                progress_dialog.update_idletasks() # Ensure update shows
                
                card_db_result = update_card_database()
                
                progress_var.set(80)
                progress_dialog.update_idletasks()
                
                if card_db_result:
                    self.card_db = card_db_result # Update instance variable
                    
                    self.config['CardDB']['last_update'] = str(int(time.time()))
                    save_config(self.config)
                    
                    # Start image download in another thread
                    threading.Thread(target=self.download_all_card_images, daemon=True).start()
                
                progress_var.set(100)
                progress_dialog.update_idletasks()
                time.sleep(0.5) # Give time to see 100%
                progress_dialog.destroy()
                
                if card_db_result:
                    messagebox.showinfo(
                        "Update Complete", 
                        f"Card database updated successfully with {len(self.card_db)} cards."
                    )
                    self.refresh_all_data() # Refresh UI with potentially new names
                else:
                    messagebox.showerror(
                        "Update Failed", 
                        "Failed to update card database. Check API URL and network connection."
                    )
            except Exception as e:
                if progress_dialog.winfo_exists():
                     progress_dialog.destroy()
                messagebox.showerror("Update Error", f"Error updating card database: {str(e)}")
                self.log_error(f"Error updating card DB: {e}", traceback.format_exc())

        threading.Thread(target=update_thread, daemon=True).start()

    def import_card_db_file_command(self):
        """Import card database from a local JSON file"""
        imported_db = import_card_database_from_file()
        if imported_db is not None:
            self.card_db = imported_db
            threading.Thread(target=self.download_all_card_images, daemon=True).start()
            self.refresh_all_data() # Refresh UI with new card names

    def check_for_updates_command(self):
        """Check for application updates (placeholder action)"""
        # In a real app, this would fetch from a server
        update_available, current_version = check_for_updates() # Uses placeholder function
        
        if update_available:
            confirm = messagebox.askyesno(
                "Update Available",
                f"A new version of Marvel Snap Tracker might be available (checking placeholder). Would you like to visit the releases page?",
                icon=messagebox.INFO
            )
            if confirm:
                webbrowser.open("https://github.com/user/marvel-snap-tracker/releases/latest") # Example URL
        else:
            messagebox.showinfo(
                "No Updates Available",
                f"You are running the latest version (v{current_version}) according to the placeholder check."
            )
    
    def log_error(self, short_msg, full_traceback=""):
        """Log an error message to the error log"""
        if self.error_log_text:
            current_time = time.strftime('%H:%M:%S')
            
            # Skip if same as last error
            if short_msg == self.last_error_displayed_short and (not full_traceback or full_traceback == self.last_error_displayed_full): 
                return
            
            # Format log entry
            log_entry = f"[{current_time}] {short_msg}\n"
            self.last_error_displayed_short = short_msg
            
            if full_traceback and full_traceback != self.last_error_displayed_full:
                indented_tb = "  " + full_traceback.strip().replace(os.linesep, os.linesep + "  ")
                log_entry += f"{indented_tb}\n"
                self.last_error_displayed_full = full_traceback
            elif not full_traceback: 
                self.last_error_displayed_full = ""
            
            # Add to log
            try:
                self.error_log_text.config(state=tk.NORMAL)
                
                # Limit log entries if needed
                max_entries = int(self.config.get('Settings', 'max_error_log_entries', fallback=50))
                if max_entries > 0:
                    # Efficiently trim from the top if needed
                    num_lines = int(self.error_log_text.index('end-1c').split('.')[0])
                    if num_lines > max_entries * 3: # Approximate limit, adjust multiplier as needed
                        # Find the line number to delete up to
                        # This is complex to do accurately without parsing; simple approach:
                        lines_to_delete = num_lines - (max_entries * 3) + 1 # Keep roughly max_entries*3 lines
                        if lines_to_delete > 0:
                            self.error_log_text.delete("1.0", f"{lines_to_delete}.0")

                # Insert new log entry
                self.error_log_text.insert(tk.END, log_entry)
                self.error_log_text.see(tk.END) # Scroll to the end
                self.error_log_text.config(state=tk.DISABLED)
            except tk.TclError as e:
                 print(f"Error writing to log widget: {e}") # Handle case where widget might be destroyed

    def display_last_encounter_info(self, opponent_name_current_game):
        """Display history of encounters with the current opponent"""
        self.opponent_encounter_history_text.config(state=tk.NORMAL)
        self.opponent_encounter_history_text.delete(1.0, tk.END)
        
        if not opponent_name_current_game or opponent_name_current_game == "Opponent":
            self.last_encounter_opponent_name_var.set("N/A")
            self.opponent_encounter_history_text.insert(tk.END, "N/A")
            self.opponent_encounter_history_text.config(state=tk.DISABLED)
            return
        
        self.last_encounter_opponent_name_var.set(f"{opponent_name_current_game}")
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT 
                    m.timestamp_ended, 
                    COALESCE(d.deck_name, 'Unknown Deck (Yours)'),
                    m.opp_revealed_cards_json, 
                    m.result, 
                    m.cubes_changed, 
                    m.turns_taken
                FROM 
                    matches m 
                LEFT JOIN 
                    decks d ON m.deck_id = d.id
                WHERE 
                    m.opponent_player_name = ? 
                ORDER BY 
                    m.timestamp_ended DESC 
                LIMIT 5
            """, (opponent_name_current_game,))
            
            past_matches = cursor.fetchall()
            
            if past_matches:
                history_str = ""
                
                for i, match_row in enumerate(past_matches):
                    ts, deck_name_we_used, opp_rev_json, result, cubes, turns = match_row
                    
                    # Format timestamp
                    try: 
                        ts_fmt = datetime.datetime.strptime(ts.split('.')[0], "%Y-%m-%d %H:%M:%S").strftime("%y-%m-%d %H:%M")
                    except: 
                        ts_fmt = ts
                    
                    # Format result
                    cubes_str = f"{cubes}" if cubes is not None else "?"
                    result_str = f"{result.capitalize() if result else 'Unknown'} ({cubes_str} cubes, T{turns if turns is not None else '?'})"
                    
                    # Process revealed cards
                    revealed_cards_str = "None Recorded"
                    if opp_rev_json:
                        try:
                            cards_list = json.loads(opp_rev_json)
                            if cards_list:
                                if self.card_db and self.display_card_names_var.get():
                                    card_names = []
                                    for card_id in cards_list:
                                        if card_id in self.card_db:
                                            card_names.append(self.card_db[card_id].get('name', card_id))
                                        else:
                                            card_names.append(card_id)
                                    revealed_cards_str = ", ".join(card_names)
                                else:
                                    revealed_cards_str = ", ".join(cards_list)
                            else: 
                                revealed_cards_str = "None Revealed"
                        except json.JSONDecodeError: 
                            revealed_cards_str = "Error parsing cards"
                    
                    # Add to history string
                    history_str += f"--- {ts_fmt} ---\nOutcome: {result_str}\nYour Deck: {deck_name_we_used}\nOpponent Revealed: {revealed_cards_str}\n"
                    
                    if i < len(past_matches) - 1: 
                        history_str += "\n"
                
                self.opponent_encounter_history_text.insert(tk.END, history_str.strip())
            else: 
                self.opponent_encounter_history_text.insert(tk.END, "No prior matches found.")
                
        except sqlite3.Error as e:
            self.log_error(f"DB error fetching encounter history: {e}")
            self.opponent_encounter_history_text.insert(tk.END, "DB Error fetching history.")
        finally: 
            conn.close()
            
        self.opponent_encounter_history_text.config(state=tk.DISABLED)
    
    def update_deck_collection_cache(self):
        """Update the cache of decks from the collection"""
        try:
            self.deck_collection_map = load_deck_names_from_collection()
        except Exception as e:
             self.log_error(f"Error updating deck collection cache: {e}", traceback.format_exc())
        # Schedule next update even if error occurred
        self.root.after(120000, self.update_deck_collection_cache)  # Update every 2 minutes
    
    def refresh_all_data(self):
        """Refresh all data in the UI"""
        try:
            self.load_history_tab_data()
            self.load_card_stats_data()
            self.load_matchup_data()
            self.load_location_stats()
            self.load_deck_performance_data() # New call
            self.update_trends()
            messagebox.showinfo("Refresh Complete", "All data tabs have been refreshed.")
        except Exception as e:
             messagebox.showerror("Refresh Error", f"An error occurred while refreshing data:\n{e}")
             self.log_error(f"Error during manual refresh: {e}", traceback.format_exc())
             
    def update_data_loop(self):
        """Main loop for updating live game data"""
        try:
            # Auto-detect game state file if not set or path invalid
            if not self.game_state_file_path or not os.path.exists(self.game_state_file_path):
                self.game_state_file_path = get_game_state_path()
                if self.game_state_file_path:
                     self.game_state_path_var.set(self.game_state_file_path) # Update settings display
                else:
                    self.status_var.set("Error: GameState.json path not found. Retrying...")
                    self.log_error("GameState.json path not found.")
                    self.root.after(5000, self.update_data_loop) # Retry after longer delay
                    return

            # Check if the game ID from the state is already recorded in the DB
            game_id_in_state_temp = None
            game_already_recorded = False
            try:
                 with open(self.game_state_file_path, 'r', encoding='utf-8-sig') as f_check:
                      state_data_check = json.load(f_check)
                 id_map_check = build_id_map(state_data_check)
                 remote_game_check = resolve_ref(state_data_check.get('RemoteGame'), id_map_check)
                 if remote_game_check:
                      game_logic_state_check = resolve_ref(remote_game_check.get('GameState'), id_map_check)
                      if game_logic_state_check:
                           game_id_in_state_temp = game_logic_state_check.get("Id")

                 if game_id_in_state_temp:
                      conn_check = sqlite3.connect(DB_NAME)
                      cursor_check = conn_check.cursor()
                      cursor_check.execute("SELECT 1 FROM matches WHERE game_id = ?", (game_id_in_state_temp,))
                      game_already_recorded = bool(cursor_check.fetchone())
                      conn_check.close()
            except Exception as e:
                 # Ignore errors here, just proceed with analysis; might be file access issue
                 print(f"DEBUG: Pre-check for game recording status failed: {e}")


            # Analyze the game state
            game_data = analyze_game_state_for_gui(
                self.game_state_file_path,
                self.current_game_events,
                self.initial_deck_cards_for_current_game,
                self.card_db if self.display_card_names_var.get() else None,
                game_already_recorded # Pass the check result
            )
            
            active_game_id_in_state = game_data.get("current_game_id_for_events")
            
            # New game detected (or first run)
            if active_game_id_in_state and active_game_id_in_state != self.current_game_id_for_deck_tracker:
                # Only reset if the new game ID is not already recorded
                if not game_already_recorded:
                    self.log_error(f"New game ID detected: {active_game_id_in_state}. Resetting tracker state.")
                    self.current_game_id_for_deck_tracker = active_game_id_in_state
                    self.initial_deck_cards_for_current_game = [] # Clear old deck
                    self.playstate_deck_id_last_seen = None
                    self.playstate_read_attempt_count = 0
                    self.local_remaining_deck_var.set("Deck (Remaining): Capturing...")
                    if active_game_id_in_state in self.current_game_events:
                        del self.current_game_events[active_game_id_in_state] # Clear events for new game ID just in case
                else:
                    # New ID is already recorded, likely processing a stale file. Don't reset.
                    self.log_error(f"Game ID {active_game_id_in_state} from file already recorded in DB. Ignoring stale state for event logging.")
                    # Keep current_game_id_for_deck_tracker as it was, maybe it's still valid from last run

            # Try to get initial deck from PlayState if needed and game is active
            if active_game_id_in_state and not self.initial_deck_cards_for_current_game and self.playstate_read_attempt_count < 3 and not game_already_recorded:
                self.playstate_read_attempt_count += 1
                selected_deck_id = get_selected_deck_id_from_playstate()
                
                if selected_deck_id:
                    self.playstate_deck_id_last_seen = selected_deck_id # Store for later DB insertion
                    
                    if self.deck_collection_map and selected_deck_id in self.deck_collection_map:
                        collection_deck_data = self.deck_collection_map[selected_deck_id]
                        deck_cards = collection_deck_data.get("cards", [])
                        
                        if deck_cards and 10 <= len(deck_cards) <= 15: # Reasonable deck size check
                            self.initial_deck_cards_for_current_game = sorted(deck_cards)
                            self.log_error(f"Game {active_game_id_in_state}: Initial deck set from PlayState.json (ID: {selected_deck_id}, {len(deck_cards)} cards).")
                            self.playstate_read_attempt_count = 0 # Reset on success
                        else:
                            self.log_error(f"Game {active_game_id_in_state}: Deck ID {selected_deck_id} from PlayState in collection, but card list invalid (size: {len(deck_cards)}).")
                    else:
                        self.log_error(f"Game {active_game_id_in_state}: Deck ID '{selected_deck_id}' from PlayState NOT FOUND in loaded collection map (map has {len(self.deck_collection_map if self.deck_collection_map else {})} keys).")
                else:
                    self.log_error(f"Game {active_game_id_in_state}: Failed to get SelectedDeckId from PlayState.json (Attempt {self.playstate_read_attempt_count}).")
            
            # Process opponent history
            current_opponent_name_from_data = game_data.get("opponent", {}).get("name", "Opponent")
            previous_displayed_opponent = self.last_encounter_opponent_name_var.get().split(" (")[0]
            
            if current_opponent_name_from_data and current_opponent_name_from_data != "Opponent":
                if current_opponent_name_from_data != previous_displayed_opponent:
                    self.display_last_encounter_info(current_opponent_name_from_data)
            elif previous_displayed_opponent != "N/A":
                self.display_last_encounter_info(None)
            
            # Clear game events for last recorded game (if a new game started)
            if self.last_recorded_game_id and active_game_id_in_state and active_game_id_in_state != self.last_recorded_game_id:
                if self.last_recorded_game_id in self.current_game_events:
                    try:
                         del self.current_game_events[self.last_recorded_game_id]
                         self.log_error(f"Cleared stale events for recorded game {self.last_recorded_game_id}")
                    except KeyError:
                         pass # Already gone, fine
                self.last_recorded_game_id = None # Reset flag

            # Handle error or update UI
            if game_data.get("error"):
                error_msg = game_data.get("error", "Unknown error.")
                full_tb = game_data.get("full_error", "")
                self.status_var.set(f"Error: {error_msg.strip()}")
                self.log_error(error_msg.strip(), full_tb)
                # Maybe reset some UI elements to default/error state
                self.local_remaining_deck_var.set("Deck (Remaining): Error")
                self.local_snap_status_var.set("Snap: Error")
                self.opponent_snap_status_var.set("Snap: Error")
                self.local_deck_var.set("Deck: ?")
            else:
                self.status_var.set(f"OK ({time.strftime('%H:%M:%S')})")
                
                # Clear error if previously shown
                if self.last_error_displayed_short and not game_data.get("error"):
                    self.log_error("State parsed successfully.")
                    self.last_error_displayed_short = ""
                    self.last_error_displayed_full = ""
                
                # Update UI with game data
                lp = game_data.get("local_player", {})
                op = game_data.get("opponent", {})
                gd = game_data.get("game_details", {})

                # Handle remaining deck calculation
                if self.initial_deck_cards_for_current_game and lp.get("remaining_deck_list") is not None:
                    remaining_cards = lp["remaining_deck_list"]
                    remaining_text = "Empty"
                    if remaining_cards:
                        if self.card_db and self.display_card_names_var.get():
                            remaining_named = [self.card_db.get(card_id, {}).get('name', card_id) for card_id in remaining_cards]
                            remaining_text = ", ".join(remaining_named)
                        else:
                            remaining_text = ", ".join(remaining_cards)

                    count = len(remaining_cards)
                    self.local_remaining_deck_var.set(f"({count}) {remaining_text}")
                elif active_game_id_in_state and not self.initial_deck_cards_for_current_game:
                    if self.playstate_read_attempt_count < 3:
                        self.local_remaining_deck_var.set("Deck (Remaining): Capturing...")
                    else:
                        self.local_remaining_deck_var.set("Deck (Remaining): Capture Failed")
                elif not active_game_id_in_state: # No active game ID parsed
                    self.local_remaining_deck_var.set("Deck (Remaining): N/A")
                # else: # Case where deck is known but remaining list is None (shouldn't happen often)
                #     self.local_remaining_deck_var.set("Deck (Remaining): Recalculating...")

                # Update other UI elements
                self.local_snap_status_var.set(lp.get("snap_info", "Snap: N/A"))
                self.opponent_snap_status_var.set(op.get("snap_info", "Snap: N/A"))
                self.turn_var.set(f"Turn: {gd.get('turn', '?')} / {gd.get('total_turns', '?')}")
                self.cubes_var.set(f"Cubes: {gd.get('cube_value', '?')}")

                # Update locations
                loc_gui_data = gd.get("locations", [{}, {}, {}])
                lp_board = lp.get("board", [[], [], []])
                op_board = op.get("board", [[], [], []])
                local_is_p1 = gd.get("local_is_gamelogic_player1", False)
                
                for i in range(3):
                    loc_info = loc_gui_data[i] if i < len(loc_gui_data) else {}
                    loc_name = loc_info.get('name', f'Loc {i+1}')
                    self.location_vars[i]["name"].set(f"{loc_name}")
                    
                    p1p, p2p = loc_info.get('p1_power', '?'), loc_info.get('p2_power', '?')
                    power_str = f"P: {p1p} (You) - {p2p} (Opp)" if local_is_p1 else f"P: {p1p} (Opp) - {p2p} (You)"
                    self.location_vars[i]["power"].set(power_str)
                    
                    self.location_vars[i]["local_cards"].set("\n".join(lp_board[i]) if i < len(lp_board) and lp_board[i] else " \n \n ")
                    self.location_vars[i]["opp_cards"].set("\n".join(op_board[i]) if i < len(op_board) and op_board[i] else " \n \n ")
                
                # Update player info
                self.local_player_name_var.set(lp.get("name", "You"))
                self.local_energy_var.set(f"Energy: {lp.get('energy', '?/?')}")
                self.local_hand_var.set((", ".join(lp.get("hand", [])) if lp.get("hand") else "Empty"))
                self.local_deck_var.set(f"Deck: {lp.get('deck_count', '?')}")
                self.local_graveyard_var.set((", ".join(lp.get("graveyard", [])) if lp.get("graveyard") else "Empty"))
                self.local_banished_var.set((", ".join(lp.get("banished", [])) if lp.get("banished") else "Empty"))
                
                self.opponent_name_var.set(current_opponent_name_from_data)
                self.opponent_energy_var.set(f"Energy: {op.get('energy', '?/?')}")
                self.opponent_hand_var.set(f"Hand: {op.get('hand_count', '?')} cards")
                self.opponent_graveyard_var.set((", ".join(op.get("graveyard", [])) if op.get("graveyard") else "Empty"))
                self.opponent_banished_var.set((", ".join(op.get("banished", [])) if op.get("banished") else "Empty"))
                
                # Handle end game data
                end_game_info = game_data.get('end_game_data')
                if end_game_info and end_game_info.get('game_id') and end_game_info.get('game_id') != self.last_recorded_game_id:
                    game_id_to_record = end_game_info['game_id']
                    events_for_this_match = self.current_game_events.get(game_id_to_record, [])
                    
                    if record_match_result(end_game_info, self.deck_collection_map, {game_id_to_record: events_for_this_match}, self.card_db):
                        self.last_recorded_game_id = game_id_to_record
                        self.log_error(f"Match {game_id_to_record} outcome recorded.", "")
                        
                        # Refresh data tabs after recording
                        self.load_history_tab_data()
                        self.load_card_stats_data()
                        self.load_matchup_data()
                        self.load_location_stats()
                        self.update_trends()

                        # Clear events only *after* successfully recording
                        if game_id_to_record in self.current_game_events:
                             try:
                                 del self.current_game_events[game_id_to_record]
                             except KeyError:
                                 pass # Already gone

                    # Reset game tracking state regardless of recording success (prevents re-processing end game)
                    self.current_game_id_for_deck_tracker = None
                    self.initial_deck_cards_for_current_game = []
                    self.playstate_deck_id_last_seen = None
                    self.playstate_read_attempt_count = 0
                    self.local_remaining_deck_var.set("Deck (Remaining): N/A")

                elif not end_game_info and self.last_recorded_game_id:
                    # If state flips from recorded back to no end_game_data (e.g., user starts new game quickly)
                    # reset the last_recorded flag so the *next* game end can be processed.
                    self.last_recorded_game_id = None
                    # Don't reset deck tracker state here, as the game might still be ongoing


            # Update the deck modal if it's visible
            if hasattr(self, 'deck_modal') and self.deck_modal.winfo_viewable():
                self._update_deck_modal_contents() # Force update checks internally if needed

        except Exception as e:
             self.status_var.set(f"Update Loop Error: {e}")
             self.log_error(f"Unhandled error in update_data_loop: {e}", traceback.format_exc())
        
        # Schedule next update
        update_interval = int(self.config.get('Settings', 'update_interval', fallback=1500))
        self.root.after(update_interval, self.update_data_loop)  
        
    def create_deck_stats_modal(self):
        """Create modal overlay to display deck statistics and card draw status"""
        # Create modal overlay frame
        self.deck_modal = tk.Toplevel(self.root)
        self.deck_modal.withdraw()  # Hide initially
        self.deck_modal.title("Deck Statistics")
        self.deck_modal.transient(self.root)
        self.deck_modal.protocol("WM_DELETE_WINDOW", self.hide_deck_modal)
        
        # Get screen dimensions for sizing
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        modal_width = min(500, screen_width - 100)
        modal_height = min(700, screen_height - 100) # Reduced height slightly
        
        # Center on screen
        x = (screen_width - modal_width) // 2
        y = (screen_height - modal_height) // 2
        self.deck_modal.geometry(f"{modal_width}x{modal_height}+{x}+{y}")
        
        # Configure background color
        bg_color = self.config['Colors']['bg_main']
        self.deck_modal.configure(background=bg_color)
        
        # Create main container frame
        main_container = ttk.Frame(self.deck_modal)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Create header for stats
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill=tk.X, pady=(10, 5), padx=10)
        
        # Add deck name and close button
        self.deck_modal_name_var = tk.StringVar(value="Current Deck")
        deck_name_label = ttk.Label(
            header_frame, 
            textvariable=self.deck_modal_name_var, 
            font=("Arial", 14, "bold")
        )
        deck_name_label.pack(side=tk.LEFT)
        
        close_button = ttk.Button(
            header_frame, 
            text="×", 
            command=self.hide_deck_modal,
            width=3
        )
        close_button.pack(side=tk.RIGHT)
        
        # Create stats row
        stats_frame = ttk.Frame(main_container)
        stats_frame.pack(fill=tk.X, pady=5, padx=10)
        
        # Stats variables
        self.deck_modal_stats = {
            "Cubes": tk.StringVar(value="+0"),
            "Avg Win": tk.StringVar(value="0"),
            "Avg Loss": tk.StringVar(value="0"),
            "Avg Net": tk.StringVar(value="0"),
            "Games": tk.StringVar(value="0-0"),
            "Win %": tk.StringVar(value="0%")
        }
        
        # Create stat labels
        for i, (stat_name, stat_var) in enumerate(self.deck_modal_stats.items()):
            stat_frame = ttk.Frame(stats_frame)
            stat_frame.pack(side=tk.LEFT, padx=5, expand=True)
            
            ttk.Label(
                stat_frame, 
                text=stat_name, 
                font=("Arial", 8)
            ).pack(side=tk.TOP)
            
            value_label = ttk.Label(
                stat_frame, 
                textvariable=stat_var, 
                font=("Arial", 12, "bold")
            )
            value_label.pack(side=tk.TOP)
        
        # Create card grid frame with fixed height
        card_grid_frame = ttk.Frame(main_container)
        card_grid_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Card frame will be created directly, no canvas or scrolling
        self.deck_modal_card_frame = ttk.Frame(card_grid_frame)
        self.deck_modal_card_frame.pack(fill=tk.BOTH, expand=True)
        
        # Bottom stats bar
        bottom_frame = ttk.Frame(main_container)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5, padx=10)
        
        # Add indicators for card counts
        self.deck_modal_card_counts = {
            "In Deck": tk.StringVar(value="0"),
            "Drawn": tk.StringVar(value="0"),
            "Played": tk.StringVar(value="0")
        }
        
        # Create card count indicators
        for i, (count_name, count_var) in enumerate(self.deck_modal_card_counts.items()):
            icon_text = "📚" if count_name == "In Deck" else "👁️" if count_name == "Drawn" else "🎮"
            
            count_frame = ttk.Frame(bottom_frame)
            count_frame.pack(side=tk.LEFT, padx=20, expand=True)
            
            ttk.Label(
                count_frame,
                text=icon_text,
                font=("Arial", 14)
            ).pack(side=tk.LEFT, padx=5)
            
            ttk.Label(
                count_frame,
                textvariable=count_var,
                font=("Arial", 12, "bold")
            ).pack(side=tk.LEFT)
        
        # Removed the duplicate button creation from here
        # The button is already created in _setup_live_game_ui
        
        self.deck_modal_update_timer = None

        self.deck_modal.bind("<Configure>", self.on_deck_modal_resize)
        self.last_deck_modal_size = (0, 0)        
        
    def on_deck_modal_resize(self, event):
        """Handle resize events for the deck modal"""
        if event.widget != self.deck_modal:
            return
            
        new_width = event.width
        new_height = event.height
        
        if (abs(new_width - self.last_deck_modal_size[0]) > 10 or 
            abs(new_height - self.last_deck_modal_size[1]) > 10):
            self.last_deck_modal_size = (new_width, new_height)
            self.update_deck_modal_after_resize()

    def update_deck_modal_after_resize(self):
        """Update deck modal after resize with slight delay to avoid flickering"""
        if hasattr(self, 'resize_update_id') and self.resize_update_id:
            self.deck_modal.after_cancel(self.resize_update_id)
        
        self.resize_update_id = self.deck_modal.after(100, lambda: self.show_deck_modal(is_resize=True))

    def show_deck_modal(self, is_resize=False): # Removed force_update, added is_resize back just in case
        """Show the deck stats modal, making it visible and raised if necessary."""
        # Create modal if it doesn't exist or was destroyed
        if not hasattr(self, 'deck_modal') or not self.deck_modal.winfo_exists():
            self.create_deck_stats_modal()

        # Always update the contents when showing is requested
        self._update_deck_modal_contents(is_resize=is_resize)

        # Make visible and raise only if it's currently hidden
        if not self.deck_modal.winfo_viewable():
            self.deck_modal.deiconify() # Make it visible
            self.deck_modal.lift()      # Bring it to the front
            self.deck_modal.focus_set() # Give it focus
        else:
            # If it's already visible, maybe just lift it without focus stealing
            # Or do nothing if it being brought forward is the issue
            self.deck_modal.lift() # Optional: keep it on top if user interacts with main window

        # Clear any pending resize update timer if we manually showed it
        if hasattr(self, 'resize_update_id') and self.resize_update_id:
            self.deck_modal.after_cancel(self.resize_update_id)
            self.resize_update_id = None

    def _update_deck_modal_contents(self, is_resize=False):
        """Update the contents of the deck modal without changing its visibility"""
        # --- Deck Name and Stats Update (No changes needed here) ---
        current_deck_name = "Current Deck"
        deck_id = None

        if self.initial_deck_cards_for_current_game:
            try:
                conn_lookup = sqlite3.connect(DB_NAME)
                cursor_lookup = conn_lookup.cursor()
                unique_normalized_list = sorted(list(set(str(cid) for cid in self.initial_deck_cards_for_current_game if cid)))
                deck_hash = hashlib.sha256(json.dumps(unique_normalized_list).encode('utf-8')).hexdigest()
                cursor_lookup.execute("SELECT id, deck_name FROM decks WHERE deck_hash = ?", (deck_hash,))
                result = cursor_lookup.fetchone()
                if result:
                    deck_id = result[0]
                    current_deck_name = result[1] if result[1] else "Unnamed Deck"
                conn_lookup.close()
            except Exception as e:
                print(f"DEBUG: Error looking up current deck by hash: {e}")
        elif self.playstate_deck_id_last_seen and self.deck_collection_map:
            if self.playstate_deck_id_last_seen in self.deck_collection_map:
                 deck_info = self.deck_collection_map[self.playstate_deck_id_last_seen]
                 current_deck_name = deck_info.get("name", "Current Deck")
                 deck_hash = deck_info.get("hash")
                 if deck_hash:
                      try:
                          conn_lookup = sqlite3.connect(DB_NAME)
                          cursor_lookup = conn_lookup.cursor()
                          cursor_lookup.execute("SELECT id FROM decks WHERE deck_hash = ?", (deck_hash,))
                          result = cursor_lookup.fetchone()
                          if result:
                              deck_id = result[0]
                          conn_lookup.close()
                      except Exception as e:
                           print(f"DEBUG: Error looking up deck by PlayState hash: {e}")

        self.deck_modal_name_var.set(current_deck_name)

        if not is_resize: # Only update stats text if not just resizing
            for key in self.deck_modal_stats:
                default_value = "+0" if key == "Cubes" else "0" if key in ["Avg Win", "Avg Loss", "Avg Net"] else "0-0" if key == "Games" else "0%"
                self.deck_modal_stats[key].set(default_value)

            if deck_id:
                try:
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT
                            COUNT(*) as games,
                            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
                            SUM(cubes_changed) as net_cubes,
                            AVG(CASE WHEN result = 'win' THEN cubes_changed ELSE NULL END) as avg_win_cubes,
                            AVG(CASE WHEN result = 'loss' THEN ABS(cubes_changed) ELSE NULL END) as avg_loss_cubes
                        FROM
                            matches
                        WHERE
                            deck_id = ?
                    """, (deck_id,))
                    stats = cursor.fetchone()
                    conn.close()

                    if stats and stats[0] > 0:
                        games, wins, losses, net_cubes, avg_win_cubes, avg_loss_cubes = stats
                        net_cubes = net_cubes if net_cubes is not None else 0
                        wins = wins if wins is not None else 0
                        losses = losses if losses is not None else 0
                        avg_win_cubes = avg_win_cubes if avg_win_cubes is not None else 0
                        avg_loss_cubes = avg_loss_cubes if avg_loss_cubes is not None else 0

                        win_rate = (wins / games * 100) if games > 0 else 0
                        self.deck_modal_stats["Cubes"].set(f"+{net_cubes}" if net_cubes > 0 else str(net_cubes))
                        self.deck_modal_stats["Avg Win"].set(f"{avg_win_cubes:.1f}")
                        self.deck_modal_stats["Avg Loss"].set(f"{avg_loss_cubes:.1f}")
                        self.deck_modal_stats["Avg Net"].set(f"{(net_cubes/games):.1f}" if games > 0 else "0")
                        self.deck_modal_stats["Games"].set(f"{wins}-{losses}")
                        self.deck_modal_stats["Win %"].set(f"{win_rate:.1f}%")
                except Exception as e:
                    print(f"DEBUG: Error getting deck stats for modal: {e}")
                    self.log_error(f"DB Error getting modal stats: {e}")

        # --- Update Card Grid ---
        # Force the UI to update layout to get correct dimensions
        # Only needed if redrawing cards
        if not self.initial_deck_cards_for_current_game or is_resize:
             self.deck_modal.update_idletasks()

        card_frame_container = self.deck_modal_card_frame # The direct parent of card widgets

        # Clear existing cards if not resizing or forced redraw needed
        force_redraw = not hasattr(self, 'current_card_widgets') or not self.current_card_widgets
        if not is_resize or force_redraw:
            for widget in card_frame_container.winfo_children():
                widget.destroy()
            self.current_card_widgets = {}

        in_deck_count = 0
        drawn_count = 0
        played_count = 0

        if self.initial_deck_cards_for_current_game:
            card_counts = Counter(self.initial_deck_cards_for_current_game)
            unique_cards = sorted(card_counts.keys())

            # Get current game card status (drawn/played)
            current_drawn_cards = set()
            current_played_cards = set()
            if self.current_game_id_for_deck_tracker and self.current_game_id_for_deck_tracker in self.current_game_events:
                for event in self.current_game_events[self.current_game_id_for_deck_tracker]:
                    if event['player'] == 'local':
                        if event['type'] == 'drawn':
                            current_drawn_cards.add(event['card'])
                        elif event['type'] == 'played':
                            current_played_cards.add(event['card'])
                            current_drawn_cards.add(event['card'])

            # Determine grid layout
            num_cards = len(unique_cards)
            container_width = card_frame_container.winfo_width()
            container_height = card_frame_container.winfo_height()
            container_width = max(200, container_width)
            container_height = max(200, container_height)

            columns = 3 if num_cards <= 12 else 4
            rows = (num_cards + columns - 1) // columns

            # Calculate card dimensions based on the container size
            h_padding = 5 * (columns + 1) # Horizontal padding between cards
            v_padding = 5 * (rows + 1)    # Vertical padding between cards
            card_width = max(60, (container_width - h_padding) // columns)
            card_height = max(84, (container_height - v_padding) // rows) if rows > 0 else container_height # Ensure min height

            # Configure grid columns and rows to expand within the container
            for c in range(columns):
                 card_frame_container.grid_columnconfigure(c, weight=1, minsize=card_width)
            for r in range(rows):
                 card_frame_container.grid_rowconfigure(r, weight=1, minsize=card_height) # Allow rows to take space

            # Draw/Update cards
            for i, card_id in enumerate(unique_cards):
                row = i // columns
                col = i % columns

                is_played = card_id in current_played_cards
                is_drawn = card_id in current_drawn_cards and not is_played
                status = "played" if is_played else "drawn" if is_drawn else "in_deck"

                if is_played: played_count += 1
                elif is_drawn: drawn_count += 1
                else: in_deck_count += 1

                widget_info = self.current_card_widgets.get(card_id)
                needs_redraw = not widget_info or widget_info['status'] != status or is_resize or force_redraw

                if needs_redraw:
                    if widget_info:
                        widget_info['frame'].destroy()

                    # Create Card Frame
                    card_frame = tk.Frame(
                        card_frame_container,
                        bg=self.config['Colors']['bg_secondary'], # Use theme color
                        highlightthickness=1,
                        highlightbackground="#000000" if status == 'in_deck' else ('#888888' if status == 'drawn' else '#555555')
                    )
                    # Use sticky="nsew" to make the frame fill its grid cell
                    card_frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
                    # Don't propagate size from children to frame
                    card_frame.pack_propagate(False)
                    card_frame.grid_propagate(False)

                    # --- Image / Text ---
                    fg_color = self.config['Colors']['fg_main']
                    if status == 'drawn': fg_color = '#AAAAAA'
                    elif status == 'played': fg_color = '#777777'

                    image_path = os.path.join(CARD_IMAGES_DIR, f"{card_id}.jpg")
                    image_loaded = False
                    if os.path.exists(image_path):
                        try:
                            # Calculate target inner dimensions (slightly smaller than frame)
                            inner_width = card_width - 6
                            inner_height = card_height - 6

                            if inner_width > 10 and inner_height > 10: # Only proceed if space is reasonable
                                pil_image = Image.open(image_path).convert("RGBA")

                                # Apply grayscale/overlay effect based on status BEFORE resizing
                                if status != 'in_deck':
                                    pil_image = pil_image.convert('L').convert('RGBA')
                                    overlay = Image.new('RGBA', pil_image.size, (100, 100, 100, 90)) # Darker overlay
                                    pil_image = Image.alpha_composite(pil_image, overlay)

                                img_w, img_h = pil_image.size
                                ratio = min(inner_width / img_w, inner_height / img_h)
                                new_w, new_h = int(img_w * ratio), int(img_h * ratio)

                                if new_w > 0 and new_h > 0: # Check for valid dimensions
                                    pil_image = pil_image.resize((new_w, new_h), Image.LANCZOS)
                                    photo = ImageTk.PhotoImage(pil_image)

                                    img_label = tk.Label(card_frame, image=photo, bg=card_frame['bg'])
                                    img_label.image = photo
                                    img_label.pack(expand=True) # Use pack to center naturally
                                    image_loaded = True

                        except Exception as img_e:
                             print(f"Error loading img {card_id}: {img_e}")

                    if not image_loaded:
                        card_name = self.card_db.get(card_id, {}).get('name', card_id) if self.card_db else card_id
                        name_label = tk.Label(
                            card_frame, text=card_name, fg=fg_color, bg=card_frame['bg'],
                            font=("Arial", 9, "bold"), wraplength=card_width - 10, justify='center'
                        )
                        name_label.pack(expand=True, padx=5, pady=5) # Use pack to center

                    self.current_card_widgets[card_id] = {'frame': card_frame, 'status': status}
                # --- End Redraw Logic ---

        else:
             # Clear frame and show message if no deck
             if not is_resize: # Avoid clearing unnecessarily during resize if frame already shows message
                  for widget in card_frame_container.winfo_children():
                      widget.destroy()
                  ttk.Label(card_frame_container, text="No deck data available.").pack(expand=True)
                  self.current_card_widgets = {}


        # Update bottom card counts
        self.deck_modal_card_counts["In Deck"].set(str(in_deck_count))
        self.deck_modal_card_counts["Drawn"].set(str(drawn_count))
        self.deck_modal_card_counts["Played"].set(str(played_count))

    def hide_deck_modal(self):
        """Hide the deck stats modal"""
        if hasattr(self, 'deck_modal') and self.deck_modal.winfo_exists():
            self.deck_modal.withdraw()
            
    def download_all_card_images(self):
        """Download all card images in the background"""
        if not self.card_db:
            print("No card database available for image download")
            return
            
        if not os.path.exists(CARD_IMAGES_DIR):
            try:
                os.makedirs(CARD_IMAGES_DIR)
            except OSError as e:
                print(f"Error creating image directory {CARD_IMAGES_DIR}: {e}")
                return # Cannot proceed without directory
        
        print(f"Starting background download of card images to {CARD_IMAGES_DIR}")
        downloaded = 0
        errors = 0
        total_cards = len(self.card_db)
        
        for i, (card_id, card_info) in enumerate(self.card_db.items()):
            image_path = os.path.join(CARD_IMAGES_DIR, f"{card_id}.jpg")
            
            if os.path.exists(image_path):
                continue
                
            image_url = card_info.get('image_url')
            if not image_url:
                continue
                
            try:
                response = requests.get(image_url, timeout=10, stream=True) # Use stream=True for potentially large files
                response.raise_for_status()
                
                # Save image chunk by chunk
                with open(image_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                         f.write(chunk)
                    
                downloaded += 1
                if downloaded % 20 == 0 or i == total_cards - 1: # Print progress periodically
                    print(f"Downloaded {downloaded}/{total_cards - i + downloaded + errors} card images...")
                    
            except requests.exceptions.RequestException as e:
                errors += 1
                print(f"Error downloading image for {card_id} ({card_info.get('name', '')}) from {image_url}: {e}")
                # Clean up potentially incomplete file
                if os.path.exists(image_path):
                     try: os.remove(image_path)
                     except OSError: pass
            except Exception as e: # Catch other potential errors like file writing
                 errors += 1
                 print(f"Unexpected error processing image for {card_id}: {e}")
                 if os.path.exists(image_path):
                     try: os.remove(image_path)
                     except OSError: pass
                 
        print(f"Finished downloading images. Added: {downloaded}, Errors: {errors}")

    def cleanup_duplicate_events_command(self):
        """Command to clean duplicate match events from the database."""
        confirm = messagebox.askyesno(
            "Confirm Event Cleanup",
            "This will attempt to remove duplicate entries from the match events log.\n"
            "It's recommended to backup your database first.\n\n"
            "Proceed with cleanup?",
            icon=messagebox.WARNING
        )
        if not confirm:
            return

        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            # --- Cleanup Strategy ---
            # 1. Delete rows that are exact duplicates (excluding primary key 'id')
            # 2. For 'drawn' events, keep only the row with the minimum 'id' for each (game_id, card_def_id) pair.

            # Step 1: Delete exact duplicates based on all relevant columns
            cursor.execute("""
                DELETE FROM match_events
                WHERE id NOT IN (
                    SELECT MIN(id)
                    FROM match_events
                    GROUP BY game_id, turn, event_type, player_type, card_def_id, 
                             location_index, source_zone, target_zone, details_json
                )
            """)
            exact_duplicates_removed = cursor.rowcount
            conn.commit()

            # Step 2: Refine 'drawn' events (keep only the first instance per card per game)
            cursor.execute("""
                DELETE FROM match_events
                WHERE event_type = 'drawn' AND player_type = 'local' AND id NOT IN (
                    SELECT MIN(id)
                    FROM match_events
                    WHERE event_type = 'drawn' AND player_type = 'local'
                    GROUP BY game_id, card_def_id
                )
            """)
            drawn_duplicates_removed = cursor.rowcount
            conn.commit()

            conn.close()

            total_removed = exact_duplicates_removed + drawn_duplicates_removed
            messagebox.showinfo(
                "Cleanup Complete",
                f"Event cleanup finished.\n"
                f"- Exact duplicates removed: {exact_duplicates_removed}\n"
                f"- Redundant 'drawn' events removed: {drawn_duplicates_removed}\n"
                f"- Total rows removed: {total_removed}"
            )
            # Refresh relevant views if needed
            self.refresh_all_data()

        except sqlite3.Error as e:
            messagebox.showerror("Cleanup Error", f"Database error during cleanup:\n{e}")
            self.log_error(f"Error during event cleanup: {e}", traceback.format_exc())
        except Exception as e:
             messagebox.showerror("Cleanup Error", f"An unexpected error occurred:\n{e}")
             self.log_error(f"Unexpected error during event cleanup: {e}", traceback.format_exc())


# --- Main Application Execution ---
if __name__ == "__main__":
    # Ensure DB exists and is initialized before loading config/app
    init_db()
    
    # Create root window
    root = tk.Tk()
    
    # Load configuration and apply theme
    config = get_config() # Load config after init_db
    apply_theme(root, config['Colors'])
    
    # Set title and geometry *after* theme might affect defaults
    root.title(f"Marvel Snap Tracker v{VERSION}")
    root.geometry("1200x800")  # Set initial size
    root.minsize(1000, 700)    # Set minimum size
    
    # Create app instance
    app = SnapTrackerApp(root)
    
    # Start main loop
    root.mainloop()
                