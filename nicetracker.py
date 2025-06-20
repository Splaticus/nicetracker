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
import matchup_tab_logic
import ui_tabs
from config_utils import DEFAULT_COLORS, get_config, save_config, CONFIG_FILE, apply_theme

VERSION = "2.0.1"  # Incremented version
DB_NAME = "snap_match_history.db"
COLLECTION_STATE_FILE = "CollectionState.json"
PLAY_STATE_FILE = "PlayState.json"
DECK_COLLECTION_CACHE = {"data": None, "last_mtime": 0}
CARD_DATA_FILE = "card_data.json"
# CONFIG_FILE = "tracker_config.ini" # Removed
CARD_IMAGES_DIR = "card_images"

# Default theme colors - Removed
# DEFAULT_COLORS = {
#     "bg_main": "#1e1e2e",
#     "bg_secondary": "#181825",
#     "fg_main": "#cdd6f4",
#     "accent_primary": "#74c7ec",
#     "accent_secondary": "#89b4fa",
#     "win": "#a6e3a1",
#     "loss": "#f38ba8",
#     "neutral": "#f9e2af"
# }

# --- Utility and Helper Functions ---
# def get_config(): -- Removed
# def save_config(config): -- Removed
# def apply_theme(root, colors=None): -- Removed

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
    decks_container_ref_or_obj = None
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

    decks_container = resolve_ref(decks_container_ref_or_obj, id_map)
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
        return {}

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
        data = response.json()

        if 'success' in data and 'cards' in data['success']:
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
            with open(CARD_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(card_db, f, indent=2)
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

def import_card_database_from_file():
    """Import card database from a JSON file"""
    filename = filedialog.askopenfilename(
        defaultextension=".json",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        title="Import Card Database"
    )
    if not filename: return None
    try:
        with open(filename, 'r', encoding='utf-8') as f: data = json.load(f)
        card_db = {}
        cards_processed = 0
        if isinstance(data, dict):
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
        if card_db:
            with open(CARD_DATA_FILE, 'w', encoding='utf-8') as f: json.dump(card_db, f, indent=2)
            config = get_config()
            config['CardDB']['last_update'] = str(int(time.time()))
            save_config(config)
            messagebox.showinfo("Import Successful", f"Successfully imported {len(card_db)} cards from {filename}.\n\nProcessed {cards_processed} card entries.")
            return card_db
        else:
            messagebox.showwarning("Import Warning", f"No valid card data found in {filename}.\nMake sure the file has the correct structure.")
            return None
    except Exception as e:
        messagebox.showerror("Import Error", f"Error importing card database: {str(e)}")
        return None

def create_fallback_card_database():
    print("Creating fallback card database")
    return {}

def download_card_image(card_id, card_db):
    if not os.path.exists(CARD_IMAGES_DIR): os.makedirs(CARD_IMAGES_DIR)
    image_path = os.path.join(CARD_IMAGES_DIR, f"{card_id}.jpg")
    if os.path.exists(image_path): return image_path
    if card_id in card_db and 'image_url' in card_db[card_id] and card_db[card_id]['image_url']:
        image_url = card_db[card_id]['image_url']
        try:
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            with open(image_path, 'wb') as f: f.write(response.content)
            return image_path
        except Exception as e: print(f"Error downloading image for {card_id}: {e}")
    return None

def get_card_tooltip_text(card_id, card_db):
    if not card_db or card_id not in card_db: return f"Card ID: {card_id}\nNo additional data available"
    card = card_db[card_id]
    tooltip = f"{card.get('name', card_id)}\n"
    if 'cost' in card and card['cost'] is not None: tooltip += f"Cost: {card['cost']} "
    if 'power' in card and card['power'] is not None: tooltip += f"Power: {card['power']}"
    if 'ability' in card and card['ability']: tooltip += f"\n\n{card['ability']}"
    return tooltip.strip()

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS decks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        deck_name TEXT,
                        card_ids_json TEXT,
                        deck_hash TEXT UNIQUE,
                        collection_deck_id TEXT,
                        first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        tags TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS matches (
                        game_id TEXT PRIMARY KEY,
                        timestamp_ended TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        local_player_name TEXT,
                        opponent_player_name TEXT,
                        deck_id INTEGER,
                        result TEXT,
                        cubes_changed INTEGER,
                        turns_taken INTEGER,
                        loc_1_def_id TEXT,
                        loc_2_def_id TEXT,
                        loc_3_def_id TEXT,
                        snap_turn_player INTEGER,
                        snap_turn_opponent INTEGER,
                        final_snap_state TEXT,
                        opp_revealed_cards_json TEXT,
                        season TEXT,
                        rank TEXT,
                        notes TEXT,
                        FOREIGN KEY (deck_id) REFERENCES decks(id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS match_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        game_id TEXT,
                        turn INTEGER,
                        event_type TEXT,
                        player_type TEXT,
                        card_def_id TEXT,
                        location_index INTEGER,
                        source_zone TEXT,
                        target_zone TEXT,
                        details_json TEXT,
                        FOREIGN KEY (game_id) REFERENCES matches(game_id) ON DELETE CASCADE)''')
    def add_column_if_not_exists(table_name, column_name, column_type):
        cursor.execute(f"PRAGMA table_info({table_name})")
        if not any(col[1] == column_name for col in cursor.fetchall()):
            print(f"Adding column {column_name} to table {table_name}...")
            try: cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            except sqlite3.OperationalError as e: print(f"Could not add column {column_name} to {table_name}: {e}")
    try:
        for col, typ in {"loc_1_def_id": "TEXT", "loc_2_def_id": "TEXT", "loc_3_def_id": "TEXT", "snap_turn_player": "INTEGER", "snap_turn_opponent": "INTEGER", "final_snap_state": "TEXT", "opp_revealed_cards_json": "TEXT", "season": "TEXT", "rank": "TEXT", "notes": "TEXT"}.items(): add_column_if_not_exists("matches", col, typ)
    except sqlite3.Error as e: print(f"DB Error altering matches table structure: {e}")
    try:
        for col, typ in {"collection_deck_id": "TEXT", "last_used": "TIMESTAMP", "tags": "TEXT"}.items(): add_column_if_not_exists("decks", col, typ)
        cursor.execute("PRAGMA table_info(decks)")
        deck_columns = [info[1] for info in cursor.fetchall()]
        if 'last_used' in deck_columns and 'first_seen' in deck_columns: cursor.execute("UPDATE decks SET last_used = first_seen WHERE last_used IS NULL")
    except sqlite3.Error as e: print(f"DB Error altering decks table structure: {e}")
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_deck_id ON matches (deck_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_timestamp ON matches (timestamp_ended)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_opponent ON matches (opponent_player_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_result ON matches (result)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_game_id ON match_events (game_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_card_id ON match_events (card_def_id)")
        try: cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uidx_events_unique ON match_events(game_id, turn, event_type, player_type, card_def_id, location_index, source_zone, target_zone, details_json)")
        except sqlite3.IntegrityError: print("WARNING: Could not create unique index on 'match_events'. Use 'Tools -> Database -> Clean Duplicate Events'.")
        except sqlite3.OperationalError as op_err: print(f"Operational error creating unique index (might be ignorable): {op_err}")
    except sqlite3.Error as e: print(f"Error creating indexes: {e}")
    conn.commit()
    conn.close()

def get_current_season_and_rank(): return "Unknown", "Unknown"

def get_or_create_deck_id(card_ids_list, collection_deck_id, deck_name_override=None, card_db=None, tags=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    unique_normalized_list = sorted(list(set(str(cid) for cid in card_ids_list if cid))) if card_ids_list else []
    deck_hash = hashlib.sha256(json.dumps(unique_normalized_list).encode('utf-8')).hexdigest()
    stored_card_ids_list = sorted([str(cid) for cid in card_ids_list if cid]) if card_ids_list else []
    card_ids_json_for_db = json.dumps(stored_card_ids_list)
    effective_deck_name = deck_name_override if deck_name_override else "Unnamed Deck"
    if not deck_name_override or deck_name_override == "Unnamed Deck":
        if card_db and len(unique_normalized_list) > 0:
            key_cards = [card_db[card_id].get('name', card_id) if card_id in card_db else card_id for card_id in unique_normalized_list[:3]]
            if key_cards: effective_deck_name = f"Deck with {', '.join(key_cards)}"
    tags_json = json.dumps(tags) if tags else None
    cursor.execute("SELECT id, deck_name, collection_deck_id, tags FROM decks WHERE deck_hash = ?", (deck_hash,))
    deck_row = cursor.fetchone()
    if deck_row:
        deck_id, db_deck_name, db_coll_id, db_tags = deck_row
        updates = []
        if deck_name_override and db_deck_name != deck_name_override: updates.append(("deck_name", deck_name_override))
        if collection_deck_id and db_coll_id != collection_deck_id: updates.append(("collection_deck_id", collection_deck_id))
        if tags_json and db_tags != tags_json: updates.append(("tags", tags_json))
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
        details_to_store = json.dumps(details_json_str) if isinstance(details_json_str, dict) else details_json_str if isinstance(details_json_str, str) else json.dumps({})
        cursor.execute("INSERT OR IGNORE INTO match_events (game_id, turn, event_type, player_type, card_def_id, location_index, source_zone, target_zone, details_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (game_id, turn, event_type, player_type, card_def_id, location_index, source_zone, target_zone, details_to_store))
        conn.commit()
    except sqlite3.Error as e: print(f"DB error recording event for {game_id}: {e}")
    finally: conn.close()

def record_match_result(match_data, deck_collection_map, game_events_log, card_db=None):
    if not match_data.get('game_id'): print("DB_RECORD: Cannot record match: Missing game_id."); return False
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM matches WHERE game_id = ?", (match_data['game_id'],))
        if cursor.fetchone(): conn.close(); return False
        deck_name_from_game = match_data.get('deck_name_from_gamestate')
        deck_card_ids = match_data.get('deck_card_ids_from_gamestate')
        deck_name_from_collection, collection_deck_id_for_db = None, None
        if deck_card_ids and deck_collection_map:
            temp_unique_normalized_list = sorted(list(set(str(cid) for cid in deck_card_ids if cid)))
            temp_deck_hash = hashlib.sha256(json.dumps(temp_unique_normalized_list).encode('utf-8')).hexdigest()
            for coll_id, coll_deck_info in deck_collection_map.items():
                if coll_deck_info.get("hash") == temp_deck_hash:
                    deck_name_from_collection, collection_deck_id_for_db = coll_deck_info.get("name"), coll_id; break
        final_deck_name_for_db = deck_name_from_collection if deck_name_from_collection else deck_name_from_game
        deck_tags = ["auto-generated"] if deck_card_ids and card_db else None
        deck_db_id = get_or_create_deck_id(deck_card_ids, collection_deck_id_for_db, final_deck_name_for_db, card_db, deck_tags)
        locs = match_data.get('locations_at_end', [None, None, None]); loc1, loc2, loc3 = (locs + [None]*3)[:3]
        snap_turn_player, snap_turn_opponent, final_snap_state = match_data.get('snap_turn_player', 0), match_data.get('snap_turn_opponent', 0), match_data.get('final_snap_state', 'None')
        opp_revealed_cards = match_data.get('opponent_revealed_cards_at_end', [])
        opp_revealed_cards_json = json.dumps(sorted(list(set(opp_revealed_cards)))) if opp_revealed_cards else None
        season, rank = get_current_season_and_rank()
        cursor.execute("INSERT INTO matches (game_id, local_player_name, opponent_player_name, deck_id, result, cubes_changed, turns_taken, loc_1_def_id, loc_2_def_id, loc_3_def_id, snap_turn_player, snap_turn_opponent, final_snap_state, opp_revealed_cards_json, season, rank) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (match_data['game_id'], match_data.get('local_player_name', 'You'), match_data.get('opponent_player_name', 'Opponent'), deck_db_id, match_data.get('result', 'unknown'), match_data.get('cubes_changed'), match_data.get('turns_taken'), loc1, loc2, loc3, snap_turn_player, snap_turn_opponent, final_snap_state, opp_revealed_cards_json, season, rank))
        conn.commit()
        print(f"Match recorded: {match_data['game_id']} - Deck: '{final_deck_name_for_db or 'Unknown Deck'}' - {match_data.get('result')} ({match_data.get('cubes_changed', '?')} cubes)")
        game_id_for_events = match_data['game_id']
        interim_events = game_events_log.get(game_id_for_events, [])
        final_drawn_cards, final_played_cards = match_data.get('card_def_ids_drawn_at_end', []), match_data.get('card_def_ids_played_at_end', [])
        interim_drawn_logged_cards = {ev['card'] for ev in interim_events if ev['type'] == 'drawn' and ev['player'] == 'local'}
        interim_played_logged_cards = {ev['card'] for ev in interim_events if ev['type'] == 'played' and ev['player'] == 'local'}
        for event_dict in interim_events: record_match_event(game_id_for_events, event_dict.get('turn'), event_dict.get('type'), event_dict.get('player'), event_dict.get('card'), event_dict.get('location_index'), event_dict.get('source_zone'), event_dict.get('target_zone'), event_dict.get('details', {}))
        placeholder_turn_for_missed_events = match_data.get('turns_taken', 0)
        for card_def_id in final_drawn_cards:
            if card_def_id not in interim_drawn_logged_cards:
                record_match_event(game_id_for_events, placeholder_turn_for_missed_events, 'drawn', 'local', card_def_id, None, 'Deck', 'Hand', {'source': 'reconciliation_end_game'})
                interim_drawn_logged_cards.add(card_def_id)
        for card_def_id in final_played_cards:
            if card_def_id not in interim_played_logged_cards:
                record_match_event(game_id_for_events, placeholder_turn_for_missed_events, 'played', 'local', card_def_id, None, 'Hand', 'Board', {'source': 'reconciliation_end_game'})
                interim_played_logged_cards.add(card_def_id)
        return True
    except sqlite3.Error as e: print(f"DB error recording match {match_data.get('game_id', 'UNKNOWN_GAME_ID')}: {e}"); return False
    finally:
        if conn: conn.close()

def analyze_game_state_for_gui(file_path, current_game_events, initial_deck_for_current_game, card_db=None, game_already_recorded_in_db=False):
    if not file_path or not os.path.exists(file_path): return {"error": f"File path invalid/not found: {file_path}", "full_error": ""}
    state_data = None
    for attempt in range(3):
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f: state_data = json.load(f)
            break
        except Exception:
            if attempt == 2: return {"error": "Error reading file after multiple attempts", "full_error": traceback.format_exc()}
            time.sleep(0.1)
    if state_data is None: return {"error": "Failed to load game state.", "full_error": "Max retries reached."}
    id_map = build_id_map(state_data)
    game_info = {"local_player": {"hand": [], "graveyard": [], "banished": [], "board": [[] for _ in range(3)], "remaining_deck_list": None, "snap_info": "Snap: N/A"},
                 "opponent": {"graveyard": [], "banished": [], "board": [[] for _ in range(3)], "snap_info": "Snap: N/A"},
                 "game_details": {"locations": [{} for _ in range(3)], "local_is_gamelogic_player1": False},
                 "error": None, "full_error": None, "end_game_data": None, "current_game_id_for_events": None}
    try:
        remote_game = resolve_ref(state_data.get('RemoteGame'), id_map)
        if not remote_game or not isinstance(remote_game, dict): game_info["error"] = "'RemoteGame' not found/resolvable."; return game_info
        client_game_info = resolve_ref(remote_game.get('ClientGameInfo'), id_map)
        if not client_game_info or not isinstance(client_game_info, dict): game_info["error"] = "'ClientGameInfo' not found/resolvable."; return game_info
        client_side_player_info_ref = remote_game.get('ClientPlayerInfo'); client_side_player_info = resolve_ref(client_side_player_info_ref, id_map)
        local_account_id_from_client = client_side_player_info.get('AccountId') if client_side_player_info and isinstance(client_side_player_info, dict) else None
        local_player_entity_id = client_game_info.get('LocalPlayerEntityId')
        if local_player_entity_id is None: game_info["error"] = "'LocalPlayerEntityId' not found."; return game_info
        enemy_player_entity_id = client_game_info.get('EnemyPlayerEntityId')
        game_logic_state = resolve_ref(remote_game.get('GameState'), id_map)
        current_game_id_for_state = game_logic_state.get("Id") if game_logic_state and isinstance(game_logic_state, dict) else None
        game_info["current_game_id_for_events"] = current_game_id_for_state
        gd, lp_info = game_info["game_details"], game_info["local_player"]
        if game_logic_state and isinstance(game_logic_state, dict):
            gd["turn"], gd["total_turns"], gd["cube_value"] = resolve_ref(game_logic_state.get('Turn'), id_map), resolve_ref(game_logic_state.get('TotalTurns'), id_map), resolve_ref(game_logic_state.get('CubeValue'), id_map)
            game_ended_by_clientresultmessage = bool(resolve_ref(game_logic_state.get('ClientResultMessage'), id_map))
            if game_already_recorded_in_db:
                if current_game_id_for_state in current_game_events: del current_game_events[current_game_id_for_state]
            elif not game_ended_by_clientresultmessage:
                if current_game_id_for_state and client_side_player_info and isinstance(client_side_player_info, dict):
                    if current_game_id_for_state not in current_game_events: current_game_events[current_game_id_for_state] = []
                    existing_played_event_keys = {(e['turn'], e['card'], e.get('location_index'), e.get('details',{}).get('energy_spent',-1)) for e in current_game_events[current_game_id_for_state] if e['type'] == 'played'}
                    client_stage_requests = [resolve_ref(req_ref, id_map) for req_ref in client_side_player_info.get('ClientStageRequests', [])]
                    for req in client_stage_requests:
                        if req and isinstance(req, dict) and req.get('CurrentState') == "EndTurnChangeApplied":
                            card_entity_id_staged, card_obj_staged = req.get('CardEntityId'), None
                            entity_to_entity_map = resolve_ref(game_logic_state.get("_entityIdToEntity"), id_map)
                            if entity_to_entity_map and isinstance(entity_to_entity_map, dict): card_obj_staged = resolve_ref(entity_to_entity_map.get(str(card_entity_id_staged)), id_map)
                            if card_obj_staged and isinstance(card_obj_staged, dict):
                                card_def_id, turn_played, target_zone_entity_id, location_index = card_obj_staged.get('CardDefId'), req.get('Turn'), req.get('TargetZoneEntityId'), None
                                if game_logic_state and isinstance(game_logic_state, dict):
                                    for loc_idx_iter, loc_data_ref in enumerate(game_logic_state.get('_locations',[])):
                                        loc_data = resolve_ref(loc_data_ref, id_map)
                                        if loc_data and isinstance(loc_data, dict) and loc_data.get('EntityId') == target_zone_entity_id: location_index = loc_data.get('SlotIndex', loc_idx_iter); break
                                event_key = (turn_played, card_def_id, location_index, req.get('EnergySpent', -1))
                                if card_def_id and turn_played is not None and event_key not in existing_played_event_keys:
                                    current_game_events[current_game_id_for_state].append({'turn': turn_played, 'type': 'played', 'player': 'local', 'card': card_def_id, 'location_index': location_index, 'source_zone': f"Zone{req.get('SourceZoneEntityId')}", 'target_zone': f"Location{location_index}" if location_index is not None else f"Zone{target_zone_entity_id}", 'details': {'energy_spent': req.get('EnergySpent')}})
                                    existing_played_event_keys.add(event_key)
                    logged_drawn_cards_for_this_game_defs = {ev['card'] for ev in current_game_events.get(current_game_id_for_state, []) if ev['type'] == 'drawn' and ev['player'] == 'local'}
                    cards_drawn_log_refs = client_side_player_info.get('CardsDrawn', []) if client_side_player_info and isinstance(client_side_player_info, dict) else []
                    current_turn_for_logging_draws = gd.get("turn", 0) or 0
                    for card_def_id_drawn in cards_drawn_log_refs:
                        if card_def_id_drawn and card_def_id_drawn != "None" and card_def_id_drawn not in logged_drawn_cards_for_this_game_defs:
                            current_game_events.setdefault(current_game_id_for_state, []).append({'turn': current_turn_for_logging_draws, 'type': 'drawn', 'player': 'local', 'card': card_def_id_drawn, 'source_zone': 'Deck', 'target_zone': 'Hand', 'details': {}})
                            logged_drawn_cards_for_this_game_defs.add(card_def_id_drawn)
            all_players_in_state_refs = game_logic_state.get('_players', []); all_players_in_state = [resolve_ref(p_ref, id_map) for p_ref in all_players_in_state_refs]; all_players_in_state = [p for p in all_players_in_state if p and isinstance(p, dict)]
            player_map = {p.get('EntityId'): p for p in all_players_in_state}; player1_entity_id_from_gamelogic = all_players_in_state[0].get('EntityId') if all_players_in_state else None
            gd["local_is_gamelogic_player1"] = (player1_entity_id_from_gamelogic is not None and local_player_entity_id == player1_entity_id_from_gamelogic)
            turn_snapped_p1, turn_snapped_p2 = game_logic_state.get('TurnSnappedPlayer1', 0), game_logic_state.get('TurnSnappedPlayer2', 0)
            lp_info["snap_info"], game_info["opponent"]["snap_info"] = (f"Snap: T{turn_snapped_p1}" if turn_snapped_p1 > 0 else "Snap: No", f"Snap: T{turn_snapped_p2}" if turn_snapped_p2 > 0 else "Snap: No") if gd["local_is_gamelogic_player1"] else (f"Snap: T{turn_snapped_p2}" if turn_snapped_p2 > 0 else "Snap: No", f"Snap: T{turn_snapped_p1}" if turn_snapped_p1 > 0 else "Snap: No")
            locations_data_from_json_refs = game_logic_state.get('_locations', []); locations_data_from_json = [resolve_ref(l_ref, id_map) for l_ref in locations_data_from_json_refs]; processed_locations = [{} for _ in range(3)]; unassigned_idx_counter = 0
            for loc_obj in locations_data_from_json:
                if not loc_obj or not isinstance(loc_obj, dict): continue
                slot_index, target_idx = loc_obj.get('SlotIndex'), -1
                if slot_index is not None and 0 <= slot_index < 3: target_idx = slot_index
                elif slot_index is None and unassigned_idx_counter < 3: target_idx = unassigned_idx_counter; unassigned_idx_counter += 1
                if 0 <= target_idx < 3: processed_locations[target_idx] = {"name": loc_obj.get('LocationDefId', f'Loc {target_idx+1}'), "p1_power": loc_obj.get('CurPlayer1Power', '?'), "p2_power": loc_obj.get('CurPlayer2Power', '?'), "slot_index": target_idx, "_player1Cards_data_ref": loc_obj.get('_player1Cards', []), "_player2Cards_data_ref": loc_obj.get('_player2Cards', [])}
            gd["locations"] = processed_locations
            local_player_data = player_map.get(local_player_entity_id)
            if local_player_data and isinstance(local_player_data, dict):
                player_info_obj = resolve_ref(local_player_data.get("PlayerInfo", {}), id_map)
                lp_info["name"] = player_info_obj.get("Name", "Local Player") if isinstance(player_info_obj, dict) else "Local Player"
                lp_info["energy"] = f"{resolve_ref(local_player_data.get('CurrentEnergy'),id_map)}/{resolve_ref(local_player_data.get('MaxEnergy'),id_map)}"
                live_deck_obj_ref = local_player_data.get('Deck', {}); live_deck_obj = resolve_ref(live_deck_obj_ref, id_map)
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
                        board_cards_loc_defs = extract_cards_with_details({"_cards": loc_detail.get(cards_key, [])}, id_map, return_card_def_ids_only=True)
                        lp_board_card_defs_flat.extend(board_cards_loc_defs)
                        lp_info["board"][i] = extract_cards_with_details({"_cards": loc_detail.get(cards_key, [])}, id_map, include_power=True, card_db=card_db)
                if initial_deck_for_current_game:
                    cards_out_of_deck = lp_hand_card_defs + lp_board_card_defs_flat + lp_graveyard_card_defs + lp_banished_card_defs
                    remaining_deck_counter = Counter(initial_deck_for_current_game)
                    for card_def_id in cards_out_of_deck:
                        if card_def_id in remaining_deck_counter and remaining_deck_counter[card_def_id] > 0: remaining_deck_counter[card_def_id] -= 1
                    final_remaining_list = []; [final_remaining_list.extend([card_def_id] * count) for card_def_id, count in remaining_deck_counter.items()]
                    lp_info["remaining_deck_list"] = sorted(final_remaining_list)
            opponent_player_data = player_map.get(enemy_player_entity_id) if enemy_player_entity_id else None; op_info = game_info["opponent"]
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
                        op_info["board"][i] = extract_cards_with_details({"_cards": loc_detail.get(cards_key, [])}, id_map, include_power=True, card_db=card_db)
            client_result_message_ref = game_logic_state.get('ClientResultMessage'); client_result_message = resolve_ref(client_result_message_ref, id_map)
            if client_result_message and isinstance(client_result_message, dict):
                is_battle_mode_game = client_result_message.get('IsBattleMode', False)
                game_id_from_crm = client_result_message.get('GameId')
                if is_battle_mode_game:
                    print(f"INFO: Game {game_id_from_crm or 'UnknownCRM_BattleGame'} is Battle Mode (Conquest). Skipping recording.")
                    # self.log_error(f"Skipped recording Battle Mode game: {game_id_from_crm}", "") # 'self' not defined here
                else:
                    end_data = {}; end_data['game_id'] = game_id_from_crm
                    if end_data['game_id']:
                        end_data['turns_taken'] = client_result_message.get('TurnsTaken'); end_data['locations_at_end'] = client_result_message.get('LocationDefIdsAtEndOfGame', [])
                        local_player_result_item = None
                        for item_ref in client_result_message.get('GameResultAccountItems', []):
                            item = resolve_ref(item_ref, id_map)
                            if item and isinstance(item, dict) and item.get('AccountId') == local_account_id_from_client: local_player_result_item = item; break
                        if local_player_result_item:
                            end_data['cubes_changed'] = local_player_result_item.get('CurrencyRewardEarned')
                            card_def_ids_drawn_at_end_refs, card_def_ids_played_at_end_refs = local_player_result_item.get('CardDefIdsDrawn', []), local_player_result_item.get('CardDefIdsPlayed', [])
                            end_data['card_def_ids_drawn_at_end'] = [resolve_ref(card_ref, id_map) for card_ref in card_def_ids_drawn_at_end_refs if resolve_ref(card_ref, id_map)]
                            end_data['card_def_ids_played_at_end'] = [resolve_ref(card_ref, id_map) for card_ref in card_def_ids_played_at_end_refs if resolve_ref(card_ref, id_map)]
                            end_data['card_def_ids_drawn_at_end'] = [cid for cid in end_data['card_def_ids_drawn_at_end'] if cid and cid != "None"]
                            end_data['card_def_ids_played_at_end'] = [cid for cid in end_data['card_def_ids_played_at_end'] if cid and cid != "None"]
                            is_loser = local_player_result_item.get('IsLoser', False)
                            if end_data['cubes_changed'] is not None: end_data['result'] = 'win' if end_data['cubes_changed'] > 0 else 'loss' if end_data['cubes_changed'] < 0 else 'tie'
                            else: end_data['result'] = 'loss' if is_loser else 'win'
                            deck_info_at_game_end_ref = local_player_result_item.get('Deck'); deck_info_at_game_end = resolve_ref(deck_info_at_game_end_ref, id_map)
                            if deck_info_at_game_end and isinstance(deck_info_at_game_end, dict):
                                end_data['deck_name_from_gamestate'] = deck_info_at_game_end.get('Name')
                                cards_container_in_result_deck_ref = deck_info_at_game_end.get('Cards'); cards_container_in_result_deck = resolve_ref(cards_container_in_result_deck_ref, id_map)
                                result_deck_card_defs = []
                                actual_card_list = cards_container_in_result_deck['$values'] if cards_container_in_result_deck and isinstance(cards_container_in_result_deck, dict) and '$values' in cards_container_in_result_deck else cards_container_in_result_deck if cards_container_in_result_deck and isinstance(cards_container_in_result_deck, list) else None
                                if actual_card_list:
                                    for card_ref_item in actual_card_list:
                                        card_obj_item = resolve_ref(card_ref_item, id_map)
                                        if card_obj_item and isinstance(card_obj_item, dict) and card_obj_item.get('CardDefId'): result_deck_card_defs.append(card_obj_item.get('CardDefId'))
                                end_data['deck_card_ids_from_gamestate'] = result_deck_card_defs
                            end_data['local_player_name'] = lp_info.get("name", "You"); end_data['opponent_player_name'] = game_info["opponent"].get("name", "Opponent")
                            opp_revealed_cards = set()
                            if opponent_player_data and game_logic_state and isinstance(game_logic_state, dict) and 'locations' in gd:
                                for loc_idx in range(3):
                                    loc_detail_for_opp_cards = gd["locations"][loc_idx]
                                    if loc_detail_for_opp_cards and isinstance(loc_detail_for_opp_cards, dict):
                                        opp_cards_key = '_player2Cards_data_ref' if gd["local_is_gamelogic_player1"] else '_player1Cards_data_ref'
                                        opp_card_refs_on_loc = loc_detail_for_opp_cards.get(opp_cards_key, [])
                                        for card_ref in opp_card_refs_on_loc:
                                            card_obj = resolve_ref(card_ref, id_map)
                                            if card_obj and isinstance(card_obj, dict) and card_obj.get('Revealed') and card_obj.get('CardDefId'): opp_revealed_cards.add(card_obj['CardDefId'])
                            end_data['opponent_revealed_cards_at_end'] = list(opp_revealed_cards)
                            game_info['end_game_data'] = end_data
        else: game_info["error"] = (game_info.get("error") or "") + " GameState (logic) missing. "
    except Exception as e:
        current_error = game_info.get("error", "") or ""
        game_info["error"] = current_error + f" EXCEPTION: {str(e)[:100]}... "
        game_info["full_error"] = traceback.format_exc()
    return game_info

def export_match_history_to_csv(filename, deck_filter=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    query = "SELECT m.game_id, m.timestamp_ended, COALESCE(d.deck_name, 'Unknown Deck'), m.opponent_player_name, m.result, m.cubes_changed, m.turns_taken, m.loc_1_def_id, m.loc_2_def_id, m.loc_3_def_id, m.snap_turn_player, m.snap_turn_opponent, m.final_snap_state, m.opp_revealed_cards_json, d.card_ids_json, m.season, m.rank, m.notes FROM matches m LEFT JOIN decks d ON m.deck_id = d.id"
    params = []
    if deck_filter and deck_filter != "All Decks": query += " WHERE d.deck_name = ?"; params.append(deck_filter)
    query += " ORDER BY m.timestamp_ended DESC"
    cursor.execute(query, tuple(params)); matches = cursor.fetchall()
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Game ID', 'Timestamp', 'Deck Name', 'Opponent', 'Result', 'Cubes', 'Turns', 'Location 1', 'Location 2', 'Location 3', 'Your Snap Turn', 'Opponent Snap Turn', 'Final Snap State', 'Opponent Revealed Cards', 'Your Deck Cards', 'Season', 'Rank', 'Notes'])
        for match in matches: writer.writerow(match)
    conn.close(); return len(matches)

def import_match_history_from_csv(filename, card_db=None):
    if not os.path.exists(filename): return (False, "File not found")
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    try:
        with open(filename, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile); header = next(reader)
            imported_count, skipped_count = 0, 0
            for row in reader:
                if len(row) < 15: skipped_count += 1; continue
                game_id = row[0]
                cursor.execute("SELECT 1 FROM matches WHERE game_id = ?", (game_id,))
                if cursor.fetchone(): skipped_count += 1; continue
                deck_name, deck_cards_json = row[2], row[14]
                try: deck_cards = json.loads(deck_cards_json)
                except (json.JSONDecodeError, TypeError): deck_cards = []
                deck_id = get_or_create_deck_id(deck_cards, None, deck_name, card_db)
                cursor.execute("INSERT INTO matches (game_id, timestamp_ended, local_player_name, opponent_player_name, deck_id, result, cubes_changed, turns_taken, loc_1_def_id, loc_2_def_id, loc_3_def_id, snap_turn_player, snap_turn_opponent, final_snap_state, opp_revealed_cards_json, season, rank, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (game_id, row[1], "You", row[3], deck_id, row[4], int(row[5]) if row[5] and row[5].strip() and row[5].strip() != '?' else None, int(row[6]) if row[6] and row[6].strip() and row[6].strip() != '?' else None, row[7], row[8], row[9], int(row[10]) if row[10] and row[10].strip() and row[10].strip() != '?' else 0, int(row[11]) if row[11] and row[11].strip() and row[11].strip() != '?' else 0, row[12], row[13], row[15] if len(row) > 15 else None, row[16] if len(row) > 16 else None, row[17] if len(row) > 17 else None))
                imported_count += 1
            conn.commit(); conn.close()
            return (True, f"Imported {imported_count} matches successfully. Skipped {skipped_count} duplicates.")
    except Exception as e: conn.rollback(); conn.close(); return (False, f"Error importing matches: {str(e)}")

def check_for_updates(): return False, VERSION

def calculate_win_rate_over_time(deck_names_set=None, opponent_name=None, days=30):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    query = "SELECT date(m.timestamp_ended) as match_date, COUNT(*) as total_matches, SUM(CASE WHEN m.result = 'win' THEN 1 ELSE 0 END) as wins, SUM(m.cubes_changed) as net_cubes FROM matches m LEFT JOIN decks d ON m.deck_id = d.id WHERE m.timestamp_ended >= date('now', ?)"
    params = [f'-{days} days'] if days else ['-3650 days']
    if deck_names_set: query += f" AND d.deck_name IN ({', '.join(['?'] * len(deck_names_set))})"; params.extend(list(deck_names_set))
    if opponent_name and opponent_name != "All Opponents": query += " AND m.opponent_player_name = ?"; params.append(opponent_name)
    query += " GROUP BY match_date ORDER BY match_date"
    cursor.execute(query, tuple(params)); results = cursor.fetchall()
    dates, win_rates, net_cubes_daily = [], [], []
    for row in results:
        dates.append(row[0]); total_daily_matches, daily_wins, daily_net_cubes = row[1], row[2], row[3]
        win_rates.append((daily_wins / total_daily_matches * 100) if total_daily_matches > 0 else 0)
        net_cubes_daily.append(daily_net_cubes if daily_net_cubes is not None else 0)
    conn.close(); return dates, win_rates, net_cubes_daily

def calculate_matchup_statistics(deck_id=None):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    query = "SELECT m.opponent_player_name, COUNT(*) as matches, SUM(CASE WHEN m.result = 'win' THEN 1 ELSE 0 END) as wins, SUM(CASE WHEN m.result = 'loss' THEN 1 ELSE 0 END) as losses, SUM(CASE WHEN m.result = 'tie' THEN 1 ELSE 0 END) as ties, SUM(m.cubes_changed) as net_cubes, GROUP_CONCAT(m.opp_revealed_cards_json, '|') as all_revealed_cards FROM matches m WHERE m.opponent_player_name IS NOT NULL AND m.opponent_player_name != 'Opponent'"
    params = []
    if deck_id and deck_id != "all": query += " AND m.deck_id = ?"; params.append(deck_id)
    query += " GROUP BY m.opponent_player_name ORDER BY matches DESC, wins DESC"
    cursor.execute(query, tuple(params)); opponent_data = cursor.fetchall()
    matchup_stats = []
    for opponent in opponent_data:
        name, matches, wins, losses, ties, net_cubes, all_revealed_cards = opponent
        win_rate = (wins / matches * 100) if matches > 0 else 0
        all_card_lists = []
        if all_revealed_cards:
            card_lists = all_revealed_cards.split('|')
            for card_list_json in card_lists:
                if card_list_json and card_list_json.lower() != 'null':
                    try: card_list = json.loads(card_list_json); all_card_lists.extend(card_list) if card_list else None
                    except json.JSONDecodeError: pass
        card_counter = Counter(all_card_lists); most_common_cards = card_counter.most_common(5)
        matchup_stats.append({'opponent': name, 'matches': matches, 'wins': wins, 'losses': losses, 'ties': ties, 'win_rate': win_rate, 'net_cubes': net_cubes if net_cubes is not None else 0, 'avg_cubes': (net_cubes / matches) if matches > 0 and net_cubes is not None else 0, 'most_common_cards': most_common_cards})
    conn.close(); return matchup_stats

class CardTooltip:
    def __init__(self, parent, card_db):
        self.parent, self.card_db, self.tooltip_window, self.current_card_id = parent, card_db, None, None
        self.x_offset, self.y_offset, self.delay, self.timer_id = 20, 10, 500, None
    def show_tooltip(self, card_id, event=None):
        self.current_card_id = card_id
        if self.timer_id: self.parent.after_cancel(self.timer_id)
        self.timer_id = self.parent.after(self.delay, lambda: self._show_tooltip(card_id, event))
    def _show_tooltip(self, card_id, event):
        if card_id != self.current_card_id: return
        self.hide_tooltip()
        x, y = self.parent.winfo_pointerx() + self.x_offset, self.parent.winfo_pointery() + self.y_offset
        self.tooltip_window = tk.Toplevel(self.parent); self.tooltip_window.wm_overrideredirect(True); self.tooltip_window.wm_geometry(f"+{x}+{y}")
        config = get_config(); colors = config['Colors']
        frame = ttk.Frame(self.tooltip_window, relief="solid", borderwidth=1); frame.pack(fill="both", expand=True)
        tooltip_text = get_card_tooltip_text(card_id, self.card_db)
        image_path = download_card_image(card_id, self.card_db) if self.card_db and card_id in self.card_db else None
        if image_path and os.path.exists(image_path):
            try:
                pil_image = Image.open(image_path); width, height = pil_image.size; max_width, max_height = 200, 280
                if width > max_width or height > max_height: ratio = min(max_width / width, max_height / height); new_width, new_height = int(width * ratio), int(height * ratio); pil_image = pil_image.resize((new_width, new_height), Image.LANCZOS)
                photo_image = ImageTk.PhotoImage(pil_image)
                image_label = ttk.Label(frame, image=photo_image); image_label.image = photo_image; image_label.pack(pady=5, padx=5)
            except Exception as e: print(f"Error showing card image: {e}")
        text_label = ttk.Label(frame, text=tooltip_text, justify="left", wraplength=250); text_label.pack(pady=5, padx=10)
        frame.configure(style="TFrame"); text_label.configure(style="TLabel")
        self.tooltip_window.update_idletasks(); tooltip_width, tooltip_height = self.tooltip_window.winfo_width(), self.tooltip_window.winfo_height()
        screen_width, screen_height = self.parent.winfo_screenwidth(), self.parent.winfo_screenheight()
        if x + tooltip_width > screen_width: x = screen_width - tooltip_width
        if y + tooltip_height > screen_height: y = screen_height - tooltip_height
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
    def hide_tooltip(self):
        if self.timer_id: self.parent.after_cancel(self.timer_id); self.timer_id = None
        if self.tooltip_window: self.tooltip_window.destroy(); self.tooltip_window = None

class SnapTrackerApp:
    def __init__(self, root_window):
        self.root = root_window
        self.root.title(f"Marvel Snap Tracker v{VERSION}")
        self.root.geometry("1200x800"); self.root.minsize(1000, 700)
        init_db()
        self.config = get_config()
        apply_theme(self.root)
        self.card_db = load_card_database()
        if self.card_db: threading.Thread(target=self.download_all_card_images, daemon=True).start()
        self.last_recorded_game_id = None; self.deck_collection_map = {}; self.current_game_events = {}
        self.game_state_file_path = None; self.last_error_displayed_short = ""; self.last_error_displayed_full = ""
        self.current_game_id_for_deck_tracker = None; self.initial_deck_cards_for_current_game = []
        self.playstate_deck_id_last_seen = None; self.playstate_read_attempt_count = 0
        self.card_tooltip = CardTooltip(self.root, self.card_db)
        self.setup_string_vars(); self.setup_ui(); self.create_deck_stats_modal()
        if self.config.getboolean('Settings', 'check_for_app_updates'): self.check_for_updates_command()
        self.update_deck_collection_cache(); self.update_data_loop()
        self.load_history_tab_data(); self.load_card_stats_data(); matchup_tab_logic.load_matchup_data(self)
        self.load_location_stats(); self.load_deck_performance_data(); self.update_trends()
        self.create_main_menu()
        print(f"Marvel Snap Tracker v{VERSION} initialized")

    def setup_string_vars(self):
        self.status_var = tk.StringVar(value="Initializing...")
        self.turn_var = tk.StringVar(value="Turn: N/A"); self.cubes_var = tk.StringVar(value="Cubes: N/A")
        self.location_vars = [{"name": tk.StringVar(value=f"Loc {i+1}: ---"), "power": tk.StringVar(value="P: ?-?"), "local_cards": tk.StringVar(value=" \n \n "), "opp_cards": tk.StringVar(value=" \n \n ")} for i in range(3)]
        self.local_player_name_var = tk.StringVar(value="You"); self.local_energy_var = tk.StringVar(value="Energy: ?/?")
        self.local_hand_var = tk.StringVar(value="Hand: Empty"); self.local_deck_var = tk.StringVar(value="Deck: ?")
        self.local_graveyard_var = tk.StringVar(value="Destroyed: Empty"); self.local_banished_var = tk.StringVar(value="Banished: Empty")
        self.local_remaining_deck_var = tk.StringVar(value="Deck (Remaining): N/A"); self.local_snap_status_var = tk.StringVar(value="Snap: N/A")
        self.opponent_name_var = tk.StringVar(value="Opponent"); self.opponent_energy_var = tk.StringVar(value="Energy: ?/?")
        self.opponent_hand_var = tk.StringVar(value="Hand: ? cards"); self.opponent_graveyard_var = tk.StringVar(value="Destroyed: Empty")
        self.opponent_banished_var = tk.StringVar(value="Banished: Empty"); self.opponent_snap_status_var = tk.StringVar(value="Snap: N/A")
        self.last_encounter_opponent_name_var = tk.StringVar(value="N/A")
        self.history_selected_deck_names = set(); self.history_deck_filter_display_var = tk.StringVar(value="Decks: All")
        self.history_deck_options = ["All Decks"]
        self.card_stats_selected_deck_names = set(); self.card_stats_deck_filter_display_var = tk.StringVar(value="Decks: All")
        self.card_stats_summary_var = tk.StringVar(value="Select a deck to see card stats.")
        self.location_stats_filter_var = tk.StringVar(value="All Locations"); self.location_selected_deck_names = set()
        self.location_deck_filter_display_var = tk.StringVar(value="Decks: All")
        self.opponent_stats_filter_var = tk.StringVar(value="All Opponents"); self.matchup_selected_deck_names = set()
        self.matchup_deck_filter_display_var = tk.StringVar(value="Decks: All")
        self.trend_days_var = tk.StringVar(value="30"); self.trend_selected_deck_names = set()
        self.trend_deck_filter_display_var = tk.StringVar(value="Decks: All")
        self.all_deck_names_for_filter = []
        self.deck_performance_season_filter_var = tk.StringVar(value="All Seasons")
        self.error_log_text = None; self.history_tree = None; self.stats_text_widget = None; self.card_stats_tree = None
        self.opponent_encounter_history_text = None; self.trends_canvas = None; self.matchup_tree = None
        self.location_stats_tree = None; self.deck_performance_tree = None

    def setup_ui(self):
        main_notebook = ttk.Notebook(self.root)
        tabs = {
            "Live Game": ttk.Frame(main_notebook, padding="10"), "Match History": ttk.Frame(main_notebook, padding="10"),
            "Deck Performance": ttk.Frame(main_notebook, padding="10"), "Card Stats": ttk.Frame(main_notebook, padding="10"),
            "Matchups": ttk.Frame(main_notebook, padding="10"), "Locations": ttk.Frame(main_notebook, padding="10"),
            "Trends": ttk.Frame(main_notebook, padding="10"), "Settings": ttk.Frame(main_notebook, padding="10")
        }
        setup_methods = {
            "Live Game": ui_tabs._setup_live_game_ui, "Match History": ui_tabs._setup_history_ui,
            "Deck Performance": ui_tabs._setup_deck_performance_ui, "Card Stats": ui_tabs._setup_card_stats_ui,
            "Matchups": ui_tabs._setup_matchup_ui, "Locations": ui_tabs._setup_location_stats_ui,
            "Trends": ui_tabs._setup_trends_ui, "Settings": ui_tabs._setup_settings_ui
        }
        for name, frame in tabs.items(): main_notebook.add(frame, text=name); setup_methods[name](self, frame)
        main_notebook.pack(expand=True, fill=tk.BOTH)

    def create_main_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Export Match History...", command=self.export_match_history)
        file_menu.add_command(label="Import Match History...", command=self.import_match_history)
        file_menu.add_separator(); file_menu.add_command(label="Backup Database...", command=self.backup_database)
        file_menu.add_separator(); file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Settings", command=lambda: self.show_settings_dialog())
        menubar.add_cascade(label="Edit", menu=edit_menu)
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Refresh Data", command=self.refresh_all_data); view_menu.add_separator()
        view_menu.add_command(label="Light Theme", command=lambda: self.change_theme("light"))
        view_menu.add_command(label="Dark Theme (Default)", command=lambda: self.change_theme("dark"))
        view_menu.add_command(label="Custom Theme...", command=self.customize_theme)
        menubar.add_cascade(label="View", menu=view_menu)
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Update Card Database (API)", command=self.update_card_db_command)
        tools_menu.add_command(label="Import Card Database (File)", command=self.import_card_db_file_command)
        db_menu = tk.Menu(tools_menu, tearoff=0)
        db_menu.add_command(label="Backup Database", command=self.backup_database)
        db_menu.add_command(label="Clean Duplicate Events", command=self.cleanup_duplicate_events_command)
        db_menu.add_command(label="Reset Database", command=self.reset_database)
        tools_menu.add_cascade(label="Database", menu=db_menu); tools_menu.add_separator()
        tools_menu.add_command(label="Check for App Updates", command=self.check_for_updates_command); tools_menu.add_separator()
        tools_menu.add_command(label="Open Card Images Folder", command=lambda: self.open_folder(CARD_IMAGES_DIR))
        tools_menu.add_command(label="Open Tracker Data Folder", command=lambda: self.open_folder(os.path.dirname(os.path.abspath(__file__))))
        menubar.add_cascade(label="Tools", menu=tools_menu)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about_dialog)
        help_menu.add_command(label="Visit Marvel Snap Zone", command=lambda: webbrowser.open("https://marvelsnapzone.com"))
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)

    def on_card_list_hover(self, event, location_index, player_type):
        cards_var = self.location_vars[location_index]["local_cards"] if player_type == "local" else self.location_vars[location_index]["opp_cards"]
        cards_text = cards_var.get()
        if cards_text and cards_text.strip() != " \n \n ":
            first_card_line = cards_text.strip().split('\n')[0]
            card_name_match = re.match(r"([^(]+)", first_card_line); first_card = card_name_match.group(1).strip() if card_name_match else first_card_line.strip()
            card_id_to_show = first_card
            if self.card_db:
                found = False
                for cid, card_info in self.card_db.items():
                    if first_card == card_info.get('name', ''): card_id_to_show = cid; found = True; break
                if not found and first_card in self.card_db: card_id_to_show = first_card
            self.card_tooltip.show_tooltip(card_id_to_show, event)

    def on_zone_hover(self, event, zone):
        zone_map = {"hand": self.local_hand_var, "graveyard": self.local_graveyard_var, "banished": self.local_banished_var,
                    "remaining": self.local_remaining_deck_var, "opp_graveyard": self.opponent_graveyard_var, "opp_banished": self.opponent_banished_var}
        zone_var = zone_map.get(zone)
        if zone_var:
            cards_text = zone_var.get()
            if cards_text and not cards_text.startswith(("Empty", "Hand:", "Deck:", "N/A", "Deck (Remaining):", "Destroyed:", "Banished:")):
                if zone == "remaining" and cards_text.startswith("("): match = re.match(r"\(\d+\)\s*(.*)", cards_text); cards_text = match.group(1) if match else cards_text
                first_card_line = cards_text.split(',')[0].strip(); card_name_match = re.match(r"([^(]+)", first_card_line); first_card = card_name_match.group(1).strip() if card_name_match else first_card_line.strip()
                card_id_to_show = first_card
                if self.card_db:
                    found = False
                    for cid, card_info in self.card_db.items():
                        if first_card == card_info.get('name', ''): card_id_to_show = cid; found = True; break
                    if not found and first_card in self.card_db: card_id_to_show = first_card
                self.card_tooltip.show_tooltip(card_id_to_show, event)

    def sort_history_treeview(self, col, reverse):
        data = [(self.history_tree.set(child, col), child) for child in self.history_tree.get_children('')]
        def try_convert(val_str): # Restored to multi-line
            val_str = str(val_str).replace('%', '')
            try:
                return int(val_str)
            except (ValueError, TypeError):
                try:
                    return float(val_str)
                except (ValueError, TypeError):
                    return val_str.lower()
        data.sort(key=lambda t: try_convert(t[0]), reverse=reverse)
        for index, (val, child) in enumerate(data): self.history_tree.move(child, '', index)
        self.history_tree.heading(col, command=lambda _col=col: self.sort_history_treeview(_col, not reverse))

    def sort_card_stats_treeview(self, col, reverse):
        data = [(self.card_stats_tree.set(child, col), child) for child in self.card_stats_tree.get_children('')]
        def try_convert(val_str): # Restored to multi-line
            val_str = str(val_str).replace('%', '').replace('N/A', '-9999')
            try:
                return int(val_str)
            except (ValueError, TypeError):
                try:
                    return float(val_str)
                except (ValueError, TypeError):
                    return val_str.lower()
        data.sort(key=lambda t: try_convert(t[0]), reverse=reverse)
        for index, (val, child) in enumerate(data): self.card_stats_tree.move(child, '', index)
        self.card_stats_tree.heading(col, command=lambda _col=col: self.sort_card_stats_treeview(_col, not reverse))

    def sort_location_treeview(self, col, reverse):
        data = [(self.location_stats_tree.set(child, col), child) for child in self.location_stats_tree.get_children('')]
        def try_convert(val_str): # Restored to multi-line
            val_str = str(val_str).replace('%', '').replace('N/A', '-9999')
            try:
                return int(val_str)
            except (ValueError, TypeError):
                try:
                    return float(val_str)
                except (ValueError, TypeError):
                    return val_str.lower()
        data.sort(key=lambda t: try_convert(t[0]), reverse=reverse)
        for index, (val, child) in enumerate(data): self.location_stats_tree.move(child, '', index)
        self.location_stats_tree.heading(col, command=lambda _col=col: self.sort_location_treeview(_col, not reverse))

    def sort_deck_performance_treeview(self, col, reverse):
        data = [(self.deck_performance_tree.set(child, col), child) for child in self.deck_performance_tree.get_children('')]
        def try_convert(val_str): # Restored to multi-line
            val_str = str(val_str).replace('%', '').replace('N/A', '-99999')
            try:
                return float(val_str)
            except (ValueError, TypeError):
                return val_str.lower()
        data.sort(key=lambda t: try_convert(t[0]), reverse=reverse)
        for index, (val, child) in enumerate(data): self.deck_performance_tree.move(child, '', index)
        self.deck_performance_tree.heading(col, command=lambda _col=col: self.sort_deck_performance_treeview(_col, not reverse))

    def load_deck_performance_data(self, event=None):
        if not self.deck_performance_tree: print("WARN: Deck performance tree not initialized yet."); return
        for item in self.deck_performance_tree.get_children(): self.deck_performance_tree.delete(item)
        selected_season = self.deck_performance_season_filter_var.get()
        conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
        query_parts = ["SELECT d.id as deck_db_id, COALESCE(d.deck_name, 'Unknown Deck') as deck_name, COUNT(m.game_id) as games_played, SUM(CASE WHEN m.result = 'win' THEN 1 ELSE 0 END) as wins, SUM(CASE WHEN m.result = 'loss' THEN 1 ELSE 0 END) as losses, SUM(CASE WHEN m.result = 'tie' THEN 1 ELSE 0 END) as ties, SUM(m.cubes_changed) as net_cubes, AVG(CASE WHEN m.result = 'win' THEN m.cubes_changed ELSE NULL END) as avg_cubes_win, AVG(CASE WHEN m.result = 'loss' THEN m.cubes_changed ELSE NULL END) as avg_cubes_loss, d.tags as deck_tags FROM decks d JOIN matches m ON d.id = m.deck_id"]
        params = []
        if selected_season != "All Seasons": query_parts.append("WHERE m.season = ?"); params.append(selected_season)
        query_parts.append("GROUP BY d.id, d.deck_name, d.tags ORDER BY games_played DESC, wins DESC")
        cursor.execute(" ".join(query_parts), tuple(params)); deck_stats = cursor.fetchall(); conn.close()
        for row in deck_stats:
            deck_db_id, name, games, wins, losses, ties, net_cubes, avg_win, avg_loss, tags_json = row
            wins, losses, ties, net_cubes = wins or 0, losses or 0, ties or 0, net_cubes or 0
            win_rate = (wins / games * 100) if games > 0 else 0; avg_cubes_game = (net_cubes / games) if games > 0 else 0
            avg_win_str, avg_loss_str = f"{avg_win:.2f}" if avg_win is not None else "N/A", f"{avg_loss:.2f}" if avg_loss is not None else "N/A"
            deck_tags_display = "None"
            if tags_json:
                try:
                    tags_list = json.loads(tags_json)
                    if isinstance(tags_list, list) and tags_list: deck_tags_display = ", ".join(tags_list)
                except json.JSONDecodeError: deck_tags_display = "Error" # Keep original else logic
            self.deck_performance_tree.insert("", "end", iid=deck_db_id, values=(name, games, wins, losses, ties, f"{win_rate:.1f}%", net_cubes, f"{avg_cubes_game:.2f}", avg_win_str, avg_loss_str, deck_tags_display))

    def load_history_tab_data(self):
        conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT deck_name FROM decks WHERE deck_name IS NOT NULL ORDER BY deck_name")
        self.all_deck_names_for_filter = [row[0] for row in cursor.fetchall() if row[0]]
        cursor.execute("SELECT DISTINCT season FROM matches WHERE season IS NOT NULL ORDER BY season")
        seasons = ["All Seasons"] + [row[0] for row in cursor.fetchall() if row[0]]
        deck_names_for_optionmenu = ["All Decks"] + self.all_deck_names_for_filter
        for menu_widget, str_var, cmd_func in [(self.matchup_deck_filter_menu, self.matchup_deck_filter_var, matchup_tab_logic.load_matchup_data), (self.location_deck_filter_menu, self.location_deck_filter_var, self.load_location_stats)]: # Corrected matchup_tab_logic call
            if menu_widget:
                menu = menu_widget["menu"]; menu.delete(0, "end"); current_val = str_var.get()
                effective_options = deck_names_for_optionmenu if deck_names_for_optionmenu else ["All Decks"]; default_selection = effective_options[0]
                if not effective_options: str_var.set("")
                elif current_val not in effective_options: str_var.set(default_selection)
                for name in effective_options: menu.add_command(label=name, command=lambda n=name, sv=str_var, cf=cmd_func: (sv.set(n), cf(self) if cf == matchup_tab_logic.load_matchup_data else cf())) # Pass self for matchup_tab_logic
                if not str_var.get() and effective_options: str_var.set(effective_options[0])
        for menu_widget, str_var, cmd_func in [(self.season_filter_menu, self.season_filter_var, self.apply_history_filter), (self.card_stats_season_filter_menu, self.card_stats_season_filter_var, self.load_card_stats_data), (self.matchup_season_filter_menu, self.matchup_season_filter_var, matchup_tab_logic.load_matchup_data), (self.location_season_filter_menu, self.location_season_filter_var, self.load_location_stats), (self.deck_perf_season_filter_menu, self.deck_performance_season_filter_var, self.load_deck_performance_data)]: # Corrected matchup_tab_logic call
            if menu_widget:
                menu = menu_widget["menu"]; menu.delete(0, "end"); current_val = str_var.get()
                effective_options = seasons if seasons and seasons[0] else ["All Seasons"]; default_selection = effective_options[0] if effective_options else ""
                if not effective_options: str_var.set("")
                elif current_val not in effective_options: str_var.set(default_selection)
                for season_name in effective_options: menu.add_command(label=season_name, command=lambda s=season_name, sv=str_var, cf=cmd_func: (sv.set(s), cf(self) if cf == matchup_tab_logic.load_matchup_data else cf())) # Pass self for matchup_tab_logic
                if not str_var.get() and effective_options: str_var.set(effective_options[0])
        cursor.execute("SELECT DISTINCT opponent_player_name FROM matches WHERE opponent_player_name IS NOT NULL AND opponent_player_name != 'Opponent' ORDER BY opponent_player_name")
        opponents = ["All Opponents"] + [row[0] for row in cursor.fetchall() if row[0]]
        menu = self.trend_opponent_filter_menu["menu"]; menu.delete(0, "end"); current_opp_val = self.trend_opponent_filter_var.get()
        effective_opp_options = opponents if opponents and opponents[0] else ["All Opponents"]; default_opp_selection = effective_opp_options[0] if effective_opp_options else ""
        if not effective_opp_options: self.trend_opponent_filter_var.set("")
        elif current_opp_val not in effective_opp_options: self.trend_opponent_filter_var.set(default_opp_selection)
        for opponent in effective_opp_options: menu.add_command(label=opponent, command=lambda o=opponent, sv=self.trend_opponent_filter_var, cf=self.update_trends: (sv.set(o), cf() if cf else None))
        if not self.trend_opponent_filter_var.get() and effective_opp_options: self.trend_opponent_filter_var.set(effective_opp_options[0])
        conn.close(); self.apply_history_filter()

    def apply_history_filter(self, event=None):
        for item in self.history_tree.get_children(): self.history_tree.delete(item)
        selected_season, selected_result, search_text = self.season_filter_var.get(), self.result_filter_var.get(), self.search_var.get().lower()
        conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
        query = "SELECT m.timestamp_ended, COALESCE(d.deck_name, 'Unknown Deck'), m.opponent_player_name, m.result, m.cubes_changed, m.turns_taken, m.loc_1_def_id, m.loc_2_def_id, m.loc_3_def_id, m.game_id FROM matches m LEFT JOIN decks d ON m.deck_id = d.id WHERE 1=1"
        params = []
        if self.history_selected_deck_names: query += f" AND d.deck_name IN ({', '.join(['?'] * len(self.history_selected_deck_names))})"; params.extend(list(self.history_selected_deck_names))
        if selected_season != "All Seasons": query += " AND m.season = ?"; params.append(selected_season)
        if selected_result != "All Results": query += " AND m.result = ?"; params.append(selected_result.lower())
        if search_text: query += " AND (lower(COALESCE(d.deck_name, '')) LIKE ? OR lower(COALESCE(m.opponent_player_name, '')) LIKE ? OR lower(COALESCE(m.loc_1_def_id, '')) LIKE ? OR lower(COALESCE(m.loc_2_def_id, '')) LIKE ? OR lower(COALESCE(m.loc_3_def_id, '')) LIKE ? OR lower(COALESCE(m.notes, '')) LIKE ? )"; search_pattern = f"%{search_text}%"; params.extend([search_pattern] * 6)
        query += " ORDER BY m.timestamp_ended DESC"
        cursor.execute(query, tuple(params)); matches = cursor.fetchall()
        for match in matches:
            try: ts_str = datetime.datetime.strptime(match[0].split('.')[0], "%Y-%m-%d %H:%M:%S").strftime("%y-%m-%d %H:%M")
            except (ValueError, TypeError): ts_str = match[0]
            loc1, loc2, loc3 = match[6], match[7], match[8]
            if self.card_db and self.display_card_names_var.get():
                loc1 = self.card_db.get(loc1, {}).get('name', loc1) if loc1 else '?'; loc2 = self.card_db.get(loc2, {}).get('name', loc2) if loc2 else '?'; loc3 = self.card_db.get(loc3, {}).get('name', loc3) if loc3 else '?'
            self.history_tree.insert("", "end", values=(ts_str, match[1], match[2], match[3], match[4] if match[4] is not None else '?', match[5], loc1, loc2, loc3), iid=match[9])
        self.calculate_and_display_stats(matches); conn.close()

    def calculate_and_display_stats(self, filtered_matches): # Restored original
        self.stats_text_widget.config(state=tk.NORMAL); self.stats_text_widget.delete(1.0, tk.END)
        if not filtered_matches: self.stats_summary_var.set("No matches found."); self.stats_text_widget.insert(tk.END, "No matches found."); self.stats_text_widget.config(state=tk.DISABLED); return
        total_games = len(filtered_matches); wins = sum(1 for m in filtered_matches if m[3] == 'win'); losses = sum(1 for m in filtered_matches if m[3] == 'loss'); ties = sum(1 for m in filtered_matches if m[3] == 'tie')
        total_cubes = sum(m[4] for m in filtered_matches if m[4] is not None); win_rate = (wins / total_games * 100) if total_games > 0 else 0; avg_cubes = (total_cubes / total_games) if total_games > 0 else 0
        filter_selection = self.history_deck_filter_display_var.get()
        if self.season_filter_var.get() != "All Seasons": filter_selection += f", Season: {self.season_filter_var.get()}"
        if self.result_filter_var.get() != "All Results": filter_selection += f", Result: {self.result_filter_var.get()}"
        if self.search_var.get(): filter_selection += f", Search: '{self.search_var.get()}'"
        summary = f"{filter_selection}\nTotal: {total_games}, Wins: {wins} ({win_rate:.1f}%), Losses: {losses}, Ties: {ties}\nNet Cubes: {total_cubes}, Avg Cubes/Game: {avg_cubes:.2f}\n\n"
        self.stats_summary_var.set(f"{filter_selection} - Win Rate: {win_rate:.1f}%, Net Cubes: {total_cubes}")
        avg_game_length = sum(m[5] for m in filtered_matches if m[5] is not None) / total_games if total_games > 0 else 0; summary += f"Average Game Length: {avg_game_length:.1f} turns\n"
        location_counter = Counter()
        for m in filtered_matches:
            if m[6]: location_counter[m[6]] += 1
            if m[7]: location_counter[m[7]] += 1
            if m[8]: location_counter[m[8]] += 1
        common_locations = location_counter.most_common(5)
        if common_locations:
            summary += "\nMost Common Locations:\n"
            for loc, count in common_locations:
                loc_name = loc
                if self.card_db and self.display_card_names_var.get() and loc and loc in self.card_db:
                    loc_name = self.card_db[loc].get('name', loc)
                if loc_name: summary += f"  {loc_name}: {count} games\n"
        self.stats_text_widget.insert(tk.END, summary); self.stats_text_widget.config(state=tk.DISABLED)

    def on_history_match_select(self, event):
        selected_items = self.history_tree.selection()
        if not selected_items: self.stats_summary_var.set("No match selected."); self.stats_text_widget.config(state=tk.NORMAL); self.stats_text_widget.delete(1.0, tk.END); self.stats_text_widget.insert(tk.END, "Select a match to see details."); self.stats_text_widget.config(state=tk.DISABLED); return
        selected_item_id = selected_items[0]
        self.stats_text_widget.config(state=tk.NORMAL); self.stats_text_widget.delete(1.0, tk.END)
        conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
        cursor.execute("SELECT m.timestamp_ended, COALESCE(d.deck_name, 'Unknown'), m.opponent_player_name, m.result, m.cubes_changed, m.turns_taken, m.loc_1_def_id, m.loc_2_def_id, m.loc_3_def_id, d.card_ids_json, m.opp_revealed_cards_json, m.notes FROM matches m LEFT JOIN decks d ON m.deck_id = d.id WHERE m.game_id = ?", (selected_item_id,))
        match_details = cursor.fetchone()
        if match_details:
            try: timestamp = datetime.datetime.strptime(match_details[0].split('.')[0], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError): timestamp = match_details[0]
            details_str = f"Game ID: {selected_item_id}\nTime: {timestamp}\nDeck: {match_details[1]}\nOpponent: {match_details[2]}\nResult: {match_details[3]} ({match_details[4] if match_details[4] is not None else '?'} cubes)\nTurns: {match_details[5]}\n"
            locations, loc_names = [match_details[6], match_details[7], match_details[8]], []
            for loc in locations: loc_names.append(self.card_db[loc].get('name', loc) if self.card_db and self.display_card_names_var.get() and loc in self.card_db and loc else loc if loc else "?")
            details_str += f"Locations: {loc_names[0]}, {loc_names[1]}, {loc_names[2]}\n"
            if match_details[11]: details_str += f"\nNotes: {match_details[11]}\n"
            if match_details[9]:
                try:
                    cards = json.loads(match_details[9])
                    named_cards = [(self.card_db[card_id].get('name', card_id) if self.card_db and self.display_card_names_var.get() and card_id in self.card_db else card_id) for card_id in cards] if cards else []
                    details_str += f"\nYour Deck Cards: {', '.join(named_cards)}\n"
                except json.JSONDecodeError: pass
            if match_details[10]:
                try:
                    cards_opp = json.loads(match_details[10])
                    named_cards_opp = [(self.card_db[card_id].get('name', card_id) if self.card_db and self.display_card_names_var.get() and card_id in self.card_db else card_id) for card_id in cards_opp] if cards_opp else []
                    details_str += f"Opponent Revealed: {', '.join(named_cards_opp)}\n"
                except json.JSONDecodeError: pass
            details_str += "\n--- Events ---\n"; self.stats_text_widget.insert(tk.END, details_str)
            cursor.execute("SELECT turn, event_type, player_type, card_def_id, location_index, source_zone, target_zone, details_json FROM match_events WHERE game_id = ? ORDER BY turn, id", (selected_item_id,))
            events = cursor.fetchall()
            if events:
                for ev in events:
                    loc_str = f" @Loc{ev[4]+1}" if ev[4] is not None else ""; card_id = ev[3]; card_name = self.card_db[card_id].get('name', card_id) if self.card_db and self.display_card_names_var.get() and card_id in self.card_db else card_id
                    ev_details_str, details_dict = ev[7], {}
                    if ev_details_str:
                        try:
                            details_dict = json.loads(ev_details_str)
                        except json.JSONDecodeError:
                            details_dict = {"raw_details": ev_details_str}
                    det_parts = [f"{k}:{v}" for k,v in details_dict.items()]; det_final = f" ({', '.join(det_parts)})" if det_parts else ""
                    self.stats_text_widget.insert(tk.END, f"T{ev[0]}: {ev[2].capitalize()} {ev[1]} '{card_name}'{loc_str}{det_final}\n")
            else: self.stats_text_widget.insert(tk.END, "No detailed events logged.\n")
        conn.close(); self.stats_text_widget.config(state=tk.DISABLED)

    def on_history_match_double_click(self, event):
        selected_item_id = self.history_tree.focus()
        if selected_item_id: self.add_match_note(selected_item_id)

    def add_match_note(self, game_id=None):
        if game_id is None:
            selected_items = self.history_tree.selection()
            if not selected_items: messagebox.showinfo("Add Note", "Please select a match first."); return
            game_id = selected_items[0]
        conn = sqlite3.connect(DB_NAME); cursor = conn.cursor(); cursor.execute("SELECT notes FROM matches WHERE game_id = ?", (game_id,)); result = cursor.fetchone(); current_note = result[0] if result and result[0] else ""; conn.close()
        note_dialog = tk.Toplevel(self.root); note_dialog.title("Add/Edit Match Note"); note_dialog.geometry("400x300"); note_dialog.transient(self.root); note_dialog.grab_set(); note_dialog.configure(background=self.config['Colors']['bg_main'])
        ttk.Label(note_dialog, text="Enter note for this match:").pack(pady=(10, 5), padx=10, anchor="w")
        note_text = scrolledtext.ScrolledText(note_dialog, height=10, wrap=tk.WORD); note_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5); note_text.insert(tk.END, current_note)
        button_frame = ttk.Frame(note_dialog); button_frame.pack(fill=tk.X, padx=10, pady=10)
        def save_note():
            note = note_text.get("1.0", tk.END).strip()
            conn_save = sqlite3.connect(DB_NAME); cursor_save = conn_save.cursor(); cursor_save.execute("UPDATE matches SET notes = ? WHERE game_id = ?", (note, game_id)); conn_save.commit(); conn_save.close()
            note_dialog.destroy()
            if self.history_tree.focus() == game_id: self.on_history_match_select(None)
        ttk.Button(button_frame, text="Save", command=save_note).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=note_dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def delete_selected_matches(self):
        selected_items = self.history_tree.selection()
        if not selected_items: messagebox.showinfo("Delete Matches", "Please select at least one match to delete."); return
        if not messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete {len(selected_items)} selected match(es)? This cannot be undone."): return
        conn = sqlite3.connect(DB_NAME); cursor = conn.cursor(); deleted_count = 0
        for game_id in selected_items:
            try: cursor.execute("DELETE FROM match_events WHERE game_id = ?", (game_id,)); cursor.execute("DELETE FROM matches WHERE game_id = ?", (game_id,)); deleted_count += 1
            except sqlite3.Error as e: self.log_error(f"Error deleting match {game_id}: {e}")
        conn.commit(); conn.close(); messagebox.showinfo("Deletion Complete", f"{deleted_count} match(es) deleted."); self.load_history_tab_data()

    def export_selected_matches(self):
        selected_items = self.history_tree.selection()
        if not selected_items: messagebox.showinfo("Export Matches", "Please select at least one match to export."); return
        filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")], title="Export Selected Matches")
        if not filename: return
        conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
        placeholders = ', '.join(['?'] * len(selected_items))
        query = f"SELECT m.game_id, m.timestamp_ended, COALESCE(d.deck_name, 'Unknown Deck'), m.opponent_player_name, m.result, m.cubes_changed, m.turns_taken, m.loc_1_def_id, m.loc_2_def_id, m.loc_3_def_id, m.snap_turn_player, m.snap_turn_opponent, m.final_snap_state, m.opp_revealed_cards_json, d.card_ids_json, m.season, m.rank, m.notes FROM matches m LEFT JOIN decks d ON m.deck_id = d.id WHERE m.game_id IN ({placeholders})"
        cursor.execute(query, selected_items); matches_to_export = cursor.fetchall()
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Game ID', 'Timestamp', 'Deck Name', 'Opponent', 'Result', 'Cubes', 'Turns', 'Location 1', 'Location 2', 'Location 3', 'Your Snap Turn', 'Opponent Snap Turn', 'Final Snap State', 'Opponent Revealed Cards', 'Your Deck Cards', 'Season', 'Rank', 'Notes'])
            for match_row in matches_to_export: writer.writerow(match_row)
        conn.close(); messagebox.showinfo("Export Complete", f"Successfully exported {len(matches_to_export)} matches to {filename}")

    def load_card_stats_data(self, event=None):
        for item in self.card_stats_tree.get_children(): self.card_stats_tree.delete(item)
        selected_season = self.card_stats_season_filter_var.get()
        conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
        match_deck_query_parts = ["SELECT m.game_id, m.result, m.cubes_changed, d.card_ids_json FROM matches m JOIN decks d ON m.deck_id = d.id WHERE 1=1 "]
        match_deck_params = []
        if self.card_stats_selected_deck_names: match_deck_query_parts.append(f"AND d.deck_name IN ({', '.join(['?'] * len(self.card_stats_selected_deck_names))})"); match_deck_params.extend(list(self.card_stats_selected_deck_names))
        if selected_season != "All Seasons": match_deck_query_parts.append("AND m.season = ?"); match_deck_params.append(selected_season)
        cursor.execute(" ".join(match_deck_query_parts), tuple(match_deck_params)); all_match_deck_data = cursor.fetchall()
        if not all_match_deck_data: self.card_stats_summary_var.set(f"No match data for {self.card_stats_deck_filter_display_var.get()} / {selected_season}"); conn.close(); return
        game_ids_for_events = [md[0] for md in all_match_deck_data]
        event_query_parts = [f"SELECT game_id, card_def_id, event_type FROM match_events WHERE player_type = 'local' AND (event_type = 'drawn' OR event_type = 'played') AND game_id IN ({','.join(['?'] * len(game_ids_for_events))})"]
        cursor.execute(" ".join(event_query_parts), tuple(game_ids_for_events)); all_event_data = cursor.fetchall(); conn.close()
        game_events = defaultdict(lambda: {"drawn": set(), "played": set()})
        for game_id, card_def_id, event_type in all_event_data:
            if event_type == 'drawn': game_events[game_id]["drawn"].add(card_def_id)
            elif event_type == 'played': game_events[game_id]["played"].add(card_def_id); game_events[game_id]["drawn"].add(card_def_id)
        card_performance = defaultdict(lambda: {"total_games_in_deck":0, "drawn_games":0, "drawn_wins":0, "drawn_cubes":0, "played_games":0, "played_wins":0, "played_cubes":0, "not_drawn_games":0, "not_drawn_wins":0, "not_drawn_cubes":0, "not_played_games":0, "not_played_wins":0, "not_played_cubes":0})
        for game_id, result, cubes, deck_cards_json_str in all_match_deck_data:
            cubes_val, is_win = cubes if cubes is not None else 0, (result == 'win')
            try: deck_cards_for_this_game = set(json.loads(deck_cards_json_str))
            except (json.JSONDecodeError, TypeError): continue
            game_specific_drawn_cards, game_specific_played_cards = game_events[game_id]["drawn"], game_events[game_id]["played"]
            for card_id in deck_cards_for_this_game:
                stats = card_performance[card_id]; stats["total_games_in_deck"] += 1
                was_drawn, was_played = card_id in game_specific_drawn_cards, card_id in game_specific_played_cards
                if was_drawn:
                    stats["drawn_games"] += 1; stats["drawn_cubes"] += cubes_val
                    if is_win: stats["drawn_wins"] += 1
                else:
                    stats["not_drawn_games"] += 1; stats["not_drawn_cubes"] += cubes_val
                    if is_win: stats["not_drawn_wins"] += 1
                if was_played:
                    stats["played_games"] += 1; stats["played_cubes"] += cubes_val
                    if is_win: stats["played_wins"] += 1
                else:
                    stats["not_played_games"] += 1; stats["not_played_cubes"] += cubes_val
                    if is_win: stats["not_played_wins"] += 1
        if not card_performance: self.card_stats_summary_var.set(f"No card performance data for {self.card_stats_deck_filter_display_var.get()} / {selected_season}"); return
        for card_def, stats in card_performance.items():
            card_name = self.card_db[card_def].get('name', card_def) if self.card_db and self.display_card_names_var.get() and card_def in self.card_db else card_def
            drawn_win_pct, avg_cubes_drawn = (stats["drawn_wins"] / stats["drawn_games"] * 100) if stats["drawn_games"] > 0 else 0.0, (stats["drawn_cubes"] / stats["drawn_games"]) if stats["drawn_games"] > 0 else 0.0
            played_win_pct, avg_cubes_played = (stats["played_wins"] / stats["played_games"] * 100) if stats["played_games"] > 0 else 0.0, (stats["played_cubes"] / stats["played_games"]) if stats["played_games"] > 0 else 0.0
            not_drawn_win_pct, avg_cubes_not_drawn = (stats["not_drawn_wins"] / stats["not_drawn_games"] * 100) if stats["not_drawn_games"] > 0 else 0.0, (stats["not_drawn_cubes"] / stats["not_drawn_games"]) if stats["not_drawn_games"] > 0 else 0.0
            not_played_win_pct, avg_cubes_not_played = (stats["not_played_wins"] / stats["not_played_games"] * 100) if stats["not_played_games"] > 0 else 0.0, (stats["not_played_cubes"] / stats["not_played_games"]) if stats["not_played_games"] > 0 else 0.0
            delta_cubes_played_vs_not = avg_cubes_played - avg_cubes_not_played if stats["played_games"] > 0 and stats["not_played_games"] > 0 else avg_cubes_played if stats["played_games"] > 0 else -avg_cubes_not_played if stats["not_played_games"] > 0 else 0.0
            delta_cubes_drawn_vs_not = avg_cubes_drawn - avg_cubes_not_drawn if stats["drawn_games"] > 0 and stats["not_drawn_games"] > 0 else avg_cubes_drawn if stats["drawn_games"] > 0 else -avg_cubes_not_drawn if stats["not_drawn_games"] > 0 else 0.0
            self.card_stats_tree.insert("", "end", values=(card_name, stats["drawn_games"], f"{drawn_win_pct:.1f}%", stats["drawn_cubes"], f"{avg_cubes_drawn:.2f}", stats["played_games"], f"{played_win_pct:.1f}%", stats["played_cubes"], f"{avg_cubes_played:.2f}", stats["not_drawn_games"], f"{not_drawn_win_pct:.1f}%", stats["not_drawn_cubes"], f"{avg_cubes_not_drawn:.2f}", stats["not_played_games"], f"{not_played_win_pct:.1f}%", stats["not_played_cubes"], f"{avg_cubes_not_played:.2f}", f"{delta_cubes_drawn_vs_not:.2f}", f"{delta_cubes_played_vs_not:.2f}"), tags=(card_def,))
        filter_msg = self.card_stats_deck_filter_display_var.get()
        if selected_season != "All Seasons": filter_msg += f", Season: {selected_season}"
        self.card_stats_summary_var.set(f"Card Stats ({filter_msg}). Unique cards processed: {len(card_performance)}")
        if self.card_stats_view_var.get() == "Chart": self.update_card_stats_chart(card_performance)

    def update_card_stats_chart(self, card_performance):
        self.card_stats_figure.clear(); ax1, ax2 = self.card_stats_figure.add_subplot(211), self.card_stats_figure.add_subplot(212)
        cards, drawn_win_rates, played_win_rates, net_cubes_list, avg_cubes_list = [], [], [], [], []

        sorted_cards_data = sorted(
            [(card_id, stats) for card_id, stats in card_performance.items() if stats["played_games"] > 0],
            key=lambda x: x[1]["played_games"] * (x[1]["played_wins"] / x[1]["played_games"] if x[1]["played_games"] > 0 else 0),
            reverse=True
        )[:10]

        for card_id, stats in sorted_cards_data:
            card_name = self.card_db[card_id].get('name', card_id) if self.card_db and self.display_card_names_var.get() and card_id in self.card_db else card_id; cards.append(card_name)
            drawn_win_rates.append((stats["drawn_wins"] / stats["drawn_games"] * 100) if stats["drawn_games"] > 0 else 0)
            played_win_rates.append((stats["played_wins"] / stats["played_games"] * 100) if stats["played_games"] > 0 else 0)
            net_cubes_list.append(stats["played_cubes"]); avg_cubes_list.append(stats["played_cubes"] / stats["played_games"] if stats["played_games"] > 0 else 0)
        cards.reverse(); drawn_win_rates.reverse(); played_win_rates.reverse(); net_cubes_list.reverse(); avg_cubes_list.reverse()
        win_color, loss_color, neutral_color, bg_color, fg_color = self.config['Colors']['win'], self.config['Colors']['loss'], self.config['Colors']['neutral'], self.config['Colors']['bg_main'], self.config['Colors']['fg_main']
        y_pos = range(len(cards)); ax1.barh(y_pos, played_win_rates, height=0.4, align='center', color=win_color, alpha=0.8, label='Played Win %'); ax1.barh([y + 0.4 for y in y_pos], drawn_win_rates, height=0.4, align='center', color=neutral_color, alpha=0.8, label='Drawn Win %')
        ax1.axvline(x=50, color=fg_color, linestyle='--', alpha=0.5); ax1.set_yticks(y_pos); ax1.set_yticklabels(cards); ax1.set_xlabel('Win %'); ax1.set_title('Card Win Rates'); ax1.legend(); ax1.set_xlim(0, 100)
        ax2.barh(y_pos, avg_cubes_list, height=0.8, align='center', color=[win_color if avg > 0 else loss_color for avg in avg_cubes_list], alpha=0.8)
        ax2.axvline(x=0, color=fg_color, linestyle='--', alpha=0.5); ax2.set_yticks(y_pos); ax2.set_yticklabels(cards); ax2.set_xlabel('Avg. Cubes per Game'); ax2.set_title('Card Cube Value')
        for ax_item in [ax1, ax2]: ax_item.set_facecolor(bg_color); ax_item.tick_params(colors=fg_color); ax_item.xaxis.label.set_color(fg_color); ax_item.yaxis.label.set_color(fg_color); ax_item.title.set_color(fg_color); [spine.set_color(fg_color) for spine in ax_item.spines.values()]
        self.card_stats_figure.patch.set_facecolor(bg_color); self.card_stats_figure.tight_layout(); self.card_stats_canvas.draw()

    def toggle_card_stats_view(self):
        view_mode = self.card_stats_view_var.get()
        if view_mode == "Table": self.card_stats_chart_frame.pack_forget(); self.card_stats_table_frame.pack(fill=tk.BOTH, expand=True)
        else:
            self.card_stats_table_frame.pack_forget(); self.card_stats_chart_frame.pack(fill=tk.BOTH, expand=True)
            card_performance = {}
            for item_id in self.card_stats_tree.get_children():
                values = self.card_stats_tree.item(item_id, "values"); card_name = values[0]
                card_id = card_name
                if self.card_db:
                    for cid, card_info in self.card_db.items():
                        if card_info.get('name') == card_name: card_id = cid; break
                try:
                    drawn_games, drawn_win_pct = int(values[1] or 0), float(values[2].replace("%", "") or 0)
                    played_games, played_win_pct = int(values[5] or 0), float(values[6].replace("%", "") or 0)
                    played_cubes = int(values[7] or 0)
                except (ValueError, IndexError) as e: print(f"Error converting card stats for chart for '{card_name}': {e}. Values: {values}"); continue
                card_performance[card_id] = {"drawn_games": drawn_games, "drawn_wins": int(drawn_games * drawn_win_pct / 100), "played_games": played_games, "played_wins": int(played_games * played_win_pct / 100), "played_cubes": played_cubes}
            self.update_card_stats_chart(card_performance)

    def on_card_stats_select(self, event):
        selected_item = self.card_stats_tree.focus();
        if not selected_item: return
        values = self.card_stats_tree.item(selected_item, "values"); card_name = values[0]
        card_id = None
        if self.card_db:
            for cid, card_info in self.card_db.items():
                if card_info.get('name') == card_name or cid == card_name: card_id = cid; break
        if card_id: self.card_tooltip.show_tooltip(card_id, None)

    def load_location_stats(self, event=None):
        for item in self.location_stats_tree.get_children(): self.location_stats_tree.delete(item)
        selected_deck, selected_season = self.location_deck_filter_var.get(), self.location_season_filter_var.get()
        conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
        subquery_template = "SELECT m.loc_{loc_num}_def_id as loc_id, m.result, m.cubes_changed, d.deck_name as deck_name_alias, m.season as season_alias FROM matches m LEFT JOIN decks d ON m.deck_id = d.id WHERE m.loc_{loc_num}_def_id IS NOT NULL AND m.loc_{loc_num}_def_id != ''"
        subqueries = [subquery_template.format(loc_num=i) for i in range(1, 4)]
        filter_conditions, params_for_each_subquery = [], []
        if selected_deck != "All Decks": filter_conditions.append("deck_name_alias = ?"); params_for_each_subquery.append(selected_deck)
        if selected_season != "All Seasons": filter_conditions.append("season_alias = ?"); params_for_each_subquery.append(selected_season)
        if filter_conditions: filter_string = " AND " + " AND ".join(filter_conditions); subqueries = [sq + filter_string for sq in subqueries]
        full_subquery = " UNION ALL ".join(subqueries)
        query = f"SELECT loc_id, COUNT(*) as matches, SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins, SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses, SUM(CASE WHEN result = 'tie' THEN 1 ELSE 0 END) as ties, SUM(cubes_changed) as net_cubes FROM ({full_subquery}) AS all_locations GROUP BY loc_id ORDER BY matches DESC"
        final_params = params_for_each_subquery * len(subqueries)
        cursor.execute(query, tuple(final_params)); location_data = cursor.fetchall()
        for row in location_data:
            loc_id, matches, wins, losses, ties, net_cubes = row
            loc_name = self.card_db[loc_id].get('name', loc_id) if self.card_db and self.display_card_names_var.get() and loc_id in self.card_db else loc_id
            win_rate = (wins / matches * 100) if matches > 0 else 0; avg_cubes = (net_cubes / matches) if matches > 0 and net_cubes is not None else 0
            self.location_stats_tree.insert("", "end", values=(loc_name, matches, f"{win_rate:.1f}%", wins, losses, ties, net_cubes if net_cubes is not None else 0, f"{avg_cubes:.2f}"), tags=(loc_id,))
        conn.close()
        if self.location_view_var.get() == "Chart": self.update_location_chart()

    def toggle_location_view(self):
        view_mode = self.location_view_var.get()
        if view_mode == "Table": self.location_chart_frame.pack_forget(); self.location_table_frame.pack(fill=tk.BOTH, expand=True)
        else: self.location_table_frame.pack_forget(); self.location_chart_frame.pack(fill=tk.BOTH, expand=True); self.update_location_chart()

    def update_location_chart(self):
        self.location_figure.clear(); ax1, ax2 = self.location_figure.add_subplot(211), self.location_figure.add_subplot(212)
        locations, matches, win_rates, net_cubes_list = [], [], [], []
        items = self.location_stats_tree.get_children(); data = []
        for item in items:
            values = self.location_stats_tree.item(item, "values")
            if len(values) >= 8: data.append((values[0], int(values[1]), float(values[2].replace("%", "")), float(values[6] or 0)))
        data.sort(key=lambda x: x[1], reverse=True); data = data[:15]
        for loc, match_count, wr, nc_val in data: locations.append(loc); matches.append(match_count); win_rates.append(wr); net_cubes_list.append(nc_val)
        locations.reverse(); matches.reverse(); win_rates.reverse(); net_cubes_list.reverse()
        win_color, loss_color, bg_color, fg_color = self.config['Colors']['win'], self.config['Colors']['loss'], self.config['Colors']['bg_main'], self.config['Colors']['fg_main']
        y_pos = range(len(locations)); max_matches = max(matches) if matches else 1; normalized_matches = [m/max_matches*0.8 for m in matches]
        bars = ax1.barh(y_pos, win_rates, height=normalized_matches, align='center', color=win_color, alpha=0.8)
        for i, bar in enumerate(bars): ax1.text(bar.get_width() + 2, bar.get_y() + bar.get_height()/2, f"{matches[i]} matches", va='center', color=fg_color, fontsize=8)
        ax1.axvline(x=50, color=fg_color, linestyle='--', alpha=0.5); ax1.set_yticks(y_pos); ax1.set_yticklabels(locations); ax1.set_xlabel('Win Rate (%)'); ax1.set_title('Location Win Rates'); ax1.set_xlim(0, 100)
        bars2 = ax2.barh(y_pos, net_cubes_list, height=normalized_matches, align='center', color=[win_color if c > 0 else loss_color for c in net_cubes_list], alpha=0.8)
        for i, bar in enumerate(bars2): avg_cubes_val = net_cubes_list[i] / matches[i] if matches[i] > 0 else 0; ax2.text(bar.get_width() + 2 if net_cubes_list[i] >= 0 else bar.get_width() - 2, bar.get_y() + bar.get_height()/2, f"Avg: {avg_cubes_val:.2f}", va='center', ha='left' if net_cubes_list[i] >= 0 else 'right', color=fg_color, fontsize=8)
        ax2.axvline(x=0, color=fg_color, linestyle='--', alpha=0.5); ax2.set_yticks(y_pos); ax2.set_yticklabels(locations); ax2.set_xlabel('Net Cubes'); ax2.set_title('Location Cube Value')
        for ax_item in [ax1, ax2]: ax_item.set_facecolor(bg_color); ax_item.tick_params(colors=fg_color); ax_item.xaxis.label.set_color(fg_color); ax_item.yaxis.label.set_color(fg_color); ax_item.title.set_color(fg_color); [spine.set_color(fg_color) for spine in ax_item.spines.values()]
        self.location_figure.patch.set_facecolor(bg_color); self.location_figure.tight_layout(); self.location_canvas.draw()

    def update_trends(self, event=None):
        days_str, selected_opponent = self.trend_days_var.get(), self.trend_opponent_filter_var.get()
        days = None if days_str == "All" else int(days_str) if days_str.isdigit() else 30
        dates, win_rates_daily, net_cubes_daily = calculate_win_rate_over_time(self.trend_selected_deck_names if self.trend_selected_deck_names else None , selected_opponent, days)
        self.trend_win_rate_ax.clear(); self.trend_cubes_ax.clear()
        if hasattr(self, 'trend_cumulative_cubes_ax'): self.trend_cumulative_cubes_ax.remove(); delattr(self, 'trend_cumulative_cubes_ax')
        if not dates:
            for ax in [self.trend_win_rate_ax, self.trend_cubes_ax]: ax.text(0.5, 0.5, "No daily data for chart", ha='center', va='center', color=self.config['Colors']['fg_main'])
        else:
            win_color, loss_color, neutral_color, bg_color, fg_color = self.config['Colors']['win'], self.config['Colors']['loss'], self.config['Colors']['neutral'], self.config['Colors']['bg_main'], self.config['Colors']['fg_main']
            dates_dt = [datetime.datetime.strptime(d, '%Y-%m-%d') for d in dates]
            self.trend_win_rate_ax.plot(dates_dt, win_rates_daily, marker='o', linestyle='-', color=win_color); self.trend_win_rate_ax.axhline(y=50, color=fg_color, linestyle='--', alpha=0.5)
            self.trend_win_rate_ax.set_ylabel('Win Rate (%)'); self.trend_win_rate_ax.set_title('Win Rate Over Time (Daily)'); self.trend_win_rate_ax.xaxis.set_major_formatter(DateFormatter('%m/%d')); self.trend_win_rate_ax.tick_params(axis='x', rotation=45)
            min_wr, max_wr, padding = min(win_rates_daily or [0]), max(win_rates_daily or [100]), 10; self.trend_win_rate_ax.set_ylim(max(0, min_wr - padding), min(100, max_wr + padding))
            self.trend_cubes_ax.plot(dates_dt, net_cubes_daily, marker='s', linestyle='-', color=neutral_color); self.trend_cubes_ax.axhline(y=0, color=fg_color, linestyle='--', alpha=0.5)
            self.trend_cubes_ax.set_ylabel('Net Cubes (Daily)'); self.trend_cubes_ax.set_xlabel('Date'); self.trend_cubes_ax.set_title('Cube Progression (Daily & Cumulative)'); self.trend_cubes_ax.xaxis.set_major_formatter(DateFormatter('%m/%d')); self.trend_cubes_ax.tick_params(axis='x', rotation=45)
            cumulative_cubes = np.cumsum(net_cubes_daily).tolist()
            self.trend_cumulative_cubes_ax = self.trend_cubes_ax.twinx(); cumulative_line_color = win_color if cumulative_cubes and cumulative_cubes[-1] > 0 else loss_color
            self.trend_cumulative_cubes_ax.plot(dates_dt, cumulative_cubes, marker='^', linestyle='--', color=cumulative_line_color, label='Cumulative Cubes'); self.trend_cumulative_cubes_ax.set_ylabel('Cumulative Cubes', color=cumulative_line_color); self.trend_cumulative_cubes_ax.tick_params(axis='y', labelcolor=cumulative_line_color); self.trend_cumulative_cubes_ax.spines['right'].set_color(cumulative_line_color)
            for ax in [self.trend_win_rate_ax, self.trend_cubes_ax, self.trend_cumulative_cubes_ax]:
                ax.set_facecolor(bg_color); ax.tick_params(colors=fg_color); ax.xaxis.label.set_color(fg_color)
                if ax != self.trend_cumulative_cubes_ax : ax.yaxis.label.set_color(fg_color)
                ax.title.set_color(fg_color); [spine.set_color(fg_color) for name, spine in ax.spines.items() if not (ax == self.trend_cumulative_cubes_ax and name == 'right')]
        self.trend_figure.patch.set_facecolor(self.config['Colors']['bg_main'])
        conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
        summary_query_parts = ["SELECT COUNT(*) as total_matches, SUM(CASE WHEN m.result = 'win' THEN 1 ELSE 0 END) as total_wins, SUM(m.cubes_changed) as total_cubes FROM matches m LEFT JOIN decks d ON m.deck_id = d.id WHERE 1=1"]
        summary_params = []
        if days: summary_query_parts.append("AND m.timestamp_ended >= date('now', ?)"); summary_params.append(f'-{days} days')
        if self.trend_selected_deck_names:
            placeholders = ', '.join(['?'] * len(self.trend_selected_deck_names))
            summary_query_parts.append(f" AND d.deck_name IN ({placeholders})")
            summary_params.extend(list(self.trend_selected_deck_names))
        if selected_opponent and selected_opponent != "All Opponents": summary_query_parts.append("AND m.opponent_player_name = ?"); summary_params.append(selected_opponent)
        try: cursor.execute(" ".join(summary_query_parts), tuple(summary_params)); summary_results = cursor.fetchone()
        except sqlite3.Error as e: print(f"Error fetching trends summary: {e}"); summary_results = (0,0,0)
        finally: conn.close()
        if summary_results:
            total_matches_summary, total_wins_summary, total_net_cubes_summary = summary_results; total_net_cubes_summary = total_net_cubes_summary or 0
            avg_win_rate_summary = (total_wins_summary / total_matches_summary * 100) if total_matches_summary > 0 else 0
            avg_cubes_per_game_summary = (total_net_cubes_summary / total_matches_summary) if total_matches_summary > 0 else 0
            self.trend_total_matches_var.set(str(total_matches_summary)); self.trend_win_rate_var.set(f"{avg_win_rate_summary:.1f}%"); self.trend_net_cubes_var.set(str(total_net_cubes_summary)); self.trend_avg_cubes_var.set(f"{avg_cubes_per_game_summary:.2f}")
        else: self.trend_total_matches_var.set("0"); self.trend_win_rate_var.set("0%"); self.trend_net_cubes_var.set("0"); self.trend_avg_cubes_var.set("0")
        self.trend_figure.tight_layout(); self.trends_canvas.draw()

    def browse_game_state_path(self):
        initial_dir = None; current_path = self.game_state_path_var.get()
        if current_path and current_path != "Auto-detected" and os.path.exists(os.path.dirname(current_path)): initial_dir = os.path.dirname(current_path)
        elif os.path.exists(get_snap_states_folder()): initial_dir = get_snap_states_folder()
        file_path = filedialog.askopenfilename(title="Select GameState.json File", filetypes=[("JSON files", "*.json"), ("All files", "*.*")], initialdir=initial_dir)
        if file_path: self.game_state_path_var.set(file_path); self.game_state_file_path = file_path

    def pick_color(self, color_key, color_label_widget):
        current_color = self.color_vars[color_key].get(); result = colorchooser.askcolor(current_color, title=f"Select {color_key} Color"); color_code = result[1] if result else None
        if color_code: self.color_vars[color_key].set(color_code); color_label_widget.configure(background=color_code)

    def apply_custom_theme(self):
        for color_key, color_var in self.color_vars.items(): self.config['Colors'][color_key] = color_var.get()
        apply_theme(self.root, self.config['Colors']); save_config(self.config)
        messagebox.showinfo("Theme Applied", "Custom theme has been applied and saved.")

    def change_theme(self, theme_name):
        colors = DEFAULT_COLORS if theme_name == "dark" else {"bg_main":"#f0f0f0", "bg_secondary":"#e0e0e0", "fg_main":"#202020", "accent_primary":"#1976d2", "accent_secondary":"#2196f3", "win":"#4caf50", "loss":"#f44336", "neutral":"#ff9800"} if theme_name == "light" else self.config['Colors'] if theme_name == "custom" else None
        if colors is None: return
        for key, value in colors.items(): self.config['Colors'][key] = value; self.color_vars[key].set(value) if key in self.color_vars else None
        apply_theme(self.root, colors); save_config(self.config)

    def customize_theme(self):
        theme_dialog = tk.Toplevel(self.root); theme_dialog.title("Customize Theme"); theme_dialog.geometry("500x400"); theme_dialog.transient(self.root); theme_dialog.grab_set(); theme_dialog.configure(background=self.config['Colors']['bg_main'])
        ttk.Label(theme_dialog, text="Theme Colors", font=("Arial", 14, "bold")).pack(pady=10)
        color_frame = ttk.Frame(theme_dialog); color_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        color_options = [("Background", "bg_main"), ("Secondary Background", "bg_secondary"), ("Text", "fg_main"), ("Primary Accent", "accent_primary"), ("Secondary Accent", "accent_secondary"), ("Win Color", "win"), ("Loss Color", "loss"), ("Neutral Color", "neutral")]
        color_preview_labels = {}
        for i, (label_text, color_key) in enumerate(color_options):
            row, col = i // 2, i % 2 * 2
            ttk.Label(color_frame, text=label_text + ":").grid(row=row, column=col, sticky="e", padx=(0, 10), pady=5)
            color_var = self.color_vars[color_key]
            preview_frame = ttk.Frame(color_frame, width=20, height=20, relief="solid", borderwidth=1); preview_frame.grid(row=row, column=col+1, sticky="w", padx=5, pady=5)
            color_label = tk.Label(preview_frame, background=color_var.get(), width=3, height=1); color_label.pack(fill=tk.BOTH, expand=True); color_preview_labels[color_key] = color_label
            color_label.bind("<Button-1>", lambda e, key=color_key, lbl=color_label: self.pick_color(key, lbl))
            ttk.Entry(color_frame, textvariable=color_var, width=10).grid(row=row, column=col+2, padx=5, pady=5)
        button_frame = ttk.Frame(theme_dialog); button_frame.pack(fill=tk.X, padx=20, pady=20)
        ttk.Button(button_frame, text="Apply & Save", command=lambda: [self.apply_custom_theme(), theme_dialog.destroy()]).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=theme_dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Reset to Default", command=lambda: self.reset_theme_to_default(theme_dialog, color_preview_labels)).pack(side=tk.LEFT, padx=5)

    def reset_theme_to_default(self, dialog=None, preview_labels=None):
        for key, value in DEFAULT_COLORS.items():
            self.config['Colors'][key] = value
            if key in self.color_vars: self.color_vars[key].set(value)
            if preview_labels and key in preview_labels: preview_labels[key].config(background=value)
        apply_theme(self.root, DEFAULT_COLORS); save_config(self.config)
        if dialog: messagebox.showinfo("Theme Reset", "Theme has been reset to default.")

    def save_settings(self):
        self.config['Settings']['auto_update_card_db'] = str(self.auto_update_card_db_var.get())
        self.config['Settings']['check_for_app_updates'] = str(self.check_for_updates_var.get())
        self.config['Settings']['card_name_display'] = str(self.display_card_names_var.get())
        self.config['Settings']['update_interval'] = self.update_interval_var.get()
        self.config['Settings']['max_error_log_entries'] = self.max_error_log_var.get()
        self.config['CardDB']['api_url'] = self.card_db_api_var.get()
        manual_path = self.game_state_path_var.get()
        if manual_path != "Auto-detected": self.game_state_file_path = manual_path; self.config['Settings']['game_state_path'] = manual_path
        else: self.game_state_file_path = None; self.config['Settings'].pop('game_state_path', None)
        save_config(self.config); messagebox.showinfo("Settings Saved", "Settings have been saved successfully.")

    def export_match_history(self):
        filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")], title="Export Match History")
        if filename: count = export_match_history_to_csv(filename, deck_filter=None); messagebox.showinfo("Export Complete", f"Successfully exported {count} matches to {filename}")

    def import_match_history(self):
        filename = filedialog.askopenfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")], title="Import Match History")
        if filename:
            success, message = import_match_history_from_csv(filename, self.card_db)
            if success: messagebox.showinfo("Import Complete", message); self.refresh_all_data()
            else: messagebox.showerror("Import Failed", message)

    def backup_database(self):
        backup_path = filedialog.asksaveasfilename(defaultextension=".db", filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")], title="Backup Snap Match History Database", initialfile=f"snap_match_history_backup_{time.strftime('%Y%m%d_%H%M%S')}.db")
        if not backup_path: return
        try:
            if not os.path.exists(DB_NAME): messagebox.showerror("Backup Failed", f"Database file '{DB_NAME}' not found."); return
            shutil.copy(DB_NAME, backup_path); messagebox.showinfo("Backup Successful", f"Database backed up to:\n{backup_path}")
        except Exception as e: self.log_error(f"Database backup failed: {e}", traceback.format_exc()); messagebox.showerror("Backup Failed", f"Could not backup database:\n{e}")

    def reset_database(self):
        if not messagebox.askyesno("Confirm Reset", "Are you sure you want to reset the database? This will DELETE ALL your match history and statistics. This cannot be undone.", icon=messagebox.WARNING): return
        if not messagebox.askyesno("Final Confirmation", "ALL YOUR MATCH DATA WILL BE PERMANENTLY DELETED. Are you absolutely sure?", icon=messagebox.WARNING): return
        if messagebox.askyesno("Backup", "Would you like to create a backup before resetting the database?", icon=messagebox.QUESTION): self.backup_database()
        try:
            if os.path.exists(DB_NAME): os.remove(DB_NAME)
            init_db(); self.refresh_all_data(); messagebox.showinfo("Reset Complete", "Database has been reset successfully.")
        except Exception as e: self.log_error(f"Database reset failed: {e}", traceback.format_exc()); messagebox.showerror("Reset Failed", f"Could not reset database:\n{e}")

    def open_folder(self, folder_path):
        abs_folder_path = os.path.abspath(folder_path)
        if not os.path.exists(abs_folder_path):
            try: os.makedirs(abs_folder_path); print(f"Created directory: {abs_folder_path}")
            except OSError as e: messagebox.showerror("Error", f"Could not create directory: {abs_folder_path}\n{e}"); return
        try:
            import sys
            if os.name == 'nt': os.startfile(abs_folder_path)
            elif os.name == 'posix': os.system(f'open "{abs_folder_path}"') if sys.platform == 'darwin' else os.system(f'xdg-open "{abs_folder_path}"')
            else: messagebox.showinfo("Open Folder", f"Cannot automatically open folder on this OS.\nPath: {abs_folder_path}")
        except Exception as e: messagebox.showerror("Error", f"Could not open folder: {abs_folder_path}\n{e}")

    def show_about_dialog(self):
        about_dialog = tk.Toplevel(self.root); about_dialog.title("About Marvel Snap Tracker"); about_dialog.geometry("400x300"); about_dialog.transient(self.root); about_dialog.grab_set(); about_dialog.configure(background=self.config['Colors']['bg_main'])
        ttk.Label(about_dialog, text=f"Marvel Snap Tracker v{VERSION}", font=("Arial", 16, "bold")).pack(pady=(20, 5))
        ttk.Label(about_dialog, text="An enhanced tracking tool for Marvel Snap").pack(pady=5)
        ttk.Label(about_dialog, text="This application helps you track your Marvel Snap matches, analyze your performance, and improve your gameplay.", wraplength=300, justify=tk.CENTER).pack(pady=10)
        ttk.Button(about_dialog, text="Close", command=about_dialog.destroy).pack(pady=20)

    def show_settings_dialog(self):
        notebook = next((w for w in self.root.winfo_children() if isinstance(w, ttk.Notebook)), None)
        if notebook:
            for i in range(notebook.index("end")):
                if notebook.tab(i, "text") == "Settings":
                    notebook.select(i)
                    return
            print("ERROR: Could not find Settings tab.")
        else: print("ERROR: Could not find main notebook.")

    def update_card_db_command(self):
        progress_dialog = tk.Toplevel(self.root); progress_dialog.title("Updating Card Database"); progress_dialog.geometry("300x100"); progress_dialog.transient(self.root); progress_dialog.grab_set(); progress_dialog.configure(background=self.config['Colors']['bg_main'])
        ttk.Label(progress_dialog, text="Downloading card data...").pack(pady=(20, 10))
        progress_var = tk.DoubleVar(); progress_bar = ttk.Progressbar(progress_dialog, variable=progress_var, maximum=100); progress_bar.pack(fill=tk.X, padx=20)
        def update_thread():
            try:
                progress_var.set(30); progress_dialog.update_idletasks()
                card_db_result = update_card_database()
                progress_var.set(80); progress_dialog.update_idletasks()
                if card_db_result:
                    self.card_db = card_db_result; self.config['CardDB']['last_update'] = str(int(time.time())); save_config(self.config)
                    threading.Thread(target=self.download_all_card_images, daemon=True).start()
                progress_var.set(100); progress_dialog.update_idletasks(); time.sleep(0.5); progress_dialog.destroy()
                if card_db_result: messagebox.showinfo("Update Complete", f"Card database updated successfully with {len(self.card_db)} cards."); self.refresh_all_data()
                else: messagebox.showerror("Update Failed", "Failed to update card database. Check API URL and network connection.")
            except Exception as e:
                if progress_dialog.winfo_exists(): progress_dialog.destroy()
                messagebox.showerror("Update Error", f"Error updating card database: {str(e)}"); self.log_error(f"Error updating card DB: {e}", traceback.format_exc())
        threading.Thread(target=update_thread, daemon=True).start()

    def import_card_db_file_command(self):
        imported_db = import_card_database_from_file()
        if imported_db is not None: self.card_db = imported_db; threading.Thread(target=self.download_all_card_images, daemon=True).start(); self.refresh_all_data()

    def check_for_updates_command(self):
        update_available, current_version = check_for_updates()
        if update_available:
            if messagebox.askyesno("Update Available", f"A new version of Marvel Snap Tracker might be available (checking placeholder). Would you like to visit the releases page?", icon=messagebox.INFO): webbrowser.open("https://github.com/user/marvel-snap-tracker/releases/latest")
        else: messagebox.showinfo("No Updates Available", f"You are running the latest version (v{current_version}) according to the placeholder check.")

    def log_error(self, short_msg, full_traceback=""):
        if self.error_log_text:
            current_time = time.strftime('%H:%M:%S')
            if short_msg == self.last_error_displayed_short and (not full_traceback or full_traceback == self.last_error_displayed_full): return
            log_entry = f"[{current_time}] {short_msg}\n"; self.last_error_displayed_short = short_msg
            if full_traceback and full_traceback != self.last_error_displayed_full: log_entry += f"  {full_traceback.strip().replace(os.linesep, os.linesep + '  ')}\n"; self.last_error_displayed_full = full_traceback
            elif not full_traceback: self.last_error_displayed_full = ""
            try:
                self.error_log_text.config(state=tk.NORMAL)
                max_entries = int(self.config.get('Settings', 'max_error_log_entries', fallback=50))
                if max_entries > 0:
                    num_lines = int(self.error_log_text.index('end-1c').split('.')[0])
                    if num_lines > max_entries * 3: lines_to_delete = num_lines - (max_entries * 3) + 1; self.error_log_text.delete("1.0", f"{lines_to_delete}.0") if lines_to_delete > 0 else None
                self.error_log_text.insert(tk.END, log_entry); self.error_log_text.see(tk.END); self.error_log_text.config(state=tk.DISABLED)
            except tk.TclError as e: print(f"Error writing to log widget: {e}")

    def display_last_encounter_info(self, opponent_name_current_game):
        self.opponent_encounter_history_text.config(state=tk.NORMAL); self.opponent_encounter_history_text.delete(1.0, tk.END)
        if not opponent_name_current_game or opponent_name_current_game == "Opponent": self.last_encounter_opponent_name_var.set("N/A"); self.opponent_encounter_history_text.insert(tk.END, "N/A"); self.opponent_encounter_history_text.config(state=tk.DISABLED); return
        self.last_encounter_opponent_name_var.set(f"{opponent_name_current_game}")
        conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
        try:
            cursor.execute("SELECT m.timestamp_ended, COALESCE(d.deck_name, 'Unknown Deck (Yours)'), m.opp_revealed_cards_json, m.result, m.cubes_changed, m.turns_taken FROM matches m LEFT JOIN decks d ON m.deck_id = d.id WHERE m.opponent_player_name = ? ORDER BY m.timestamp_ended DESC LIMIT 5", (opponent_name_current_game,))
            past_matches = cursor.fetchall()
            if past_matches:
                history_str = ""
                for i, match_row in enumerate(past_matches):
                    ts, deck_name_we_used, opp_rev_json, result, cubes, turns = match_row
                    try: ts_fmt = datetime.datetime.strptime(ts.split('.')[0], "%Y-%m-%d %H:%M:%S").strftime("%y-%m-%d %H:%M")
                    except: ts_fmt = ts
                    cubes_str = f"{cubes}" if cubes is not None else "?"; result_str = f"{result.capitalize() if result else 'Unknown'} ({cubes_str} cubes, T{turns if turns is not None else '?'})"
                    revealed_cards_str = "None Recorded"
                    if opp_rev_json:
                        try:
                            cards_list = json.loads(opp_rev_json)
                            if cards_list:
                                card_names = [(self.card_db[card_id].get('name', card_id) if self.card_db and self.display_card_names_var.get() and card_id in self.card_db else card_id) for card_id in cards_list]
                                revealed_cards_str = ", ".join(card_names)
                            else: revealed_cards_str = "None Revealed"
                        except json.JSONDecodeError: revealed_cards_str = "Error parsing cards"
                    history_str += f"--- {ts_fmt} ---\nOutcome: {result_str}\nYour Deck: {deck_name_we_used}\nOpponent Revealed: {revealed_cards_str}\n" + ("\n" if i < len(past_matches) - 1 else "")
                self.opponent_encounter_history_text.insert(tk.END, history_str.strip())
            else: self.opponent_encounter_history_text.insert(tk.END, "No prior matches found.")
        except sqlite3.Error as e: self.log_error(f"DB error fetching encounter history: {e}"); self.opponent_encounter_history_text.insert(tk.END, "DB Error fetching history.")
        finally: conn.close(); self.opponent_encounter_history_text.config(state=tk.DISABLED)

    def update_deck_collection_cache(self):
        try: self.deck_collection_map = load_deck_names_from_collection()
        except Exception as e: self.log_error(f"Error updating deck collection cache: {e}", traceback.format_exc())
        self.root.after(120000, self.update_deck_collection_cache)

    def refresh_all_data(self):
        try:
            self.load_history_tab_data(); self.load_card_stats_data(); matchup_tab_logic.load_matchup_data(self)
            self.load_location_stats(); self.load_deck_performance_data(); self.update_trends()
            messagebox.showinfo("Refresh Complete", "All data tabs have been refreshed.")
        except Exception as e: messagebox.showerror("Refresh Error", f"An error occurred while refreshing data:\n{e}"); self.log_error(f"Error during manual refresh: {e}", traceback.format_exc())

    def update_data_loop(self):
        try:
            if not self.game_state_file_path or not os.path.exists(self.game_state_file_path):
                self.game_state_file_path = get_game_state_path()
                if self.game_state_file_path: self.game_state_path_var.set(self.game_state_file_path)
                else: self.status_var.set("Error: GameState.json path not found. Retrying..."); self.log_error("GameState.json path not found."); self.root.after(5000, self.update_data_loop); return
            game_id_in_state_temp, game_already_recorded = None, False
            try:
                 with open(self.game_state_file_path, 'r', encoding='utf-8-sig') as f_check: state_data_check = json.load(f_check)
                 id_map_check = build_id_map(state_data_check); remote_game_check = resolve_ref(state_data_check.get('RemoteGame'), id_map_check)
                 if remote_game_check:
                     game_logic_state_check_ref = remote_game_check.get('GameState')
                     game_logic_state_check = resolve_ref(game_logic_state_check_ref, id_map_check)
                     if game_logic_state_check: game_id_in_state_temp = game_logic_state_check.get("Id")
                 if game_id_in_state_temp:
                      conn_check = sqlite3.connect(DB_NAME); cursor_check = conn_check.cursor()
                      cursor_check.execute("SELECT 1 FROM matches WHERE game_id = ?", (game_id_in_state_temp,)); game_already_recorded = bool(cursor_check.fetchone()); conn_check.close()
            except Exception as e: print(f"DEBUG: Pre-check for game recording status failed: {e}")
            game_data = analyze_game_state_for_gui(self.game_state_file_path, self.current_game_events, self.initial_deck_cards_for_current_game, self.card_db if self.display_card_names_var.get() else None, game_already_recorded)
            active_game_id_in_state = game_data.get("current_game_id_for_events")
            if active_game_id_in_state and active_game_id_in_state != self.current_game_id_for_deck_tracker:
                if not game_already_recorded:
                    self.log_error(f"New game ID detected: {active_game_id_in_state}. Resetting tracker state.")
                    self.current_game_id_for_deck_tracker = active_game_id_in_state; self.initial_deck_cards_for_current_game = []
                    self.playstate_deck_id_last_seen = None; self.playstate_read_attempt_count = 0; self.local_remaining_deck_var.set("Deck (Remaining): Capturing...")
                    if active_game_id_in_state in self.current_game_events: del self.current_game_events[active_game_id_in_state]
                else: self.log_error(f"Game ID {active_game_id_in_state} from file already recorded in DB. Ignoring stale state for event logging.")
            if active_game_id_in_state and not self.initial_deck_cards_for_current_game and self.playstate_read_attempt_count < 3 and not game_already_recorded:
                self.playstate_read_attempt_count += 1; selected_deck_id = get_selected_deck_id_from_playstate()
                if selected_deck_id:
                    self.playstate_deck_id_last_seen = selected_deck_id
                    if self.deck_collection_map and selected_deck_id in self.deck_collection_map:
                        collection_deck_data = self.deck_collection_map[selected_deck_id]; deck_cards = collection_deck_data.get("cards", [])
                        if deck_cards and 10 <= len(deck_cards) <= 15: self.initial_deck_cards_for_current_game = sorted(deck_cards); self.log_error(f"Game {active_game_id_in_state}: Initial deck set from PlayState.json (ID: {selected_deck_id}, {len(deck_cards)} cards)."); self.playstate_read_attempt_count = 0
                        else: self.log_error(f"Game {active_game_id_in_state}: Deck ID {selected_deck_id} from PlayState in collection, but card list invalid (size: {len(deck_cards)}).")
                    else: self.log_error(f"Game {active_game_id_in_state}: Deck ID '{selected_deck_id}' from PlayState NOT FOUND in loaded collection map (map has {len(self.deck_collection_map if self.deck_collection_map else {})} keys).")
                else: self.log_error(f"Game {active_game_id_in_state}: Failed to get SelectedDeckId from PlayState.json (Attempt {self.playstate_read_attempt_count}).")
            current_opponent_name_from_data = game_data.get("opponent", {}).get("name", "Opponent"); previous_displayed_opponent = self.last_encounter_opponent_name_var.get().split(" (")[0]
            if current_opponent_name_from_data and current_opponent_name_from_data != "Opponent":
                if current_opponent_name_from_data != previous_displayed_opponent: self.display_last_encounter_info(current_opponent_name_from_data)
            elif previous_displayed_opponent != "N/A": self.display_last_encounter_info(None)
            if self.last_recorded_game_id and active_game_id_in_state and active_game_id_in_state != self.last_recorded_game_id:
                if self.last_recorded_game_id in self.current_game_events:
                    try: del self.current_game_events[self.last_recorded_game_id]; self.log_error(f"Cleared stale events for recorded game {self.last_recorded_game_id}")
                    except KeyError: pass
                self.last_recorded_game_id = None
            if game_data.get("error"): error_msg, full_tb = game_data.get("error", "Unknown error."), game_data.get("full_error", ""); self.status_var.set(f"Error: {error_msg.strip()}"); self.log_error(error_msg.strip(), full_tb); self.local_remaining_deck_var.set("Deck (Remaining): Error"); self.local_snap_status_var.set("Snap: Error"); self.opponent_snap_status_var.set("Snap: Error"); self.local_deck_var.set("Deck: ?")
            else:
                self.status_var.set(f"OK ({time.strftime('%H:%M:%S')})")
                if self.last_error_displayed_short and not game_data.get("error"): self.log_error("State parsed successfully."); self.last_error_displayed_short = ""; self.last_error_displayed_full = ""
                lp, op, gd = game_data.get("local_player", {}), game_data.get("opponent", {}), game_data.get("game_details", {})
                if self.initial_deck_cards_for_current_game and lp.get("remaining_deck_list") is not None:
                    remaining_cards = lp["remaining_deck_list"]; remaining_text = "Empty"
                    if remaining_cards: remaining_text = ", ".join([self.card_db.get(card_id, {}).get('name', card_id) for card_id in remaining_cards]) if self.card_db and self.display_card_names_var.get() else ", ".join(remaining_cards)
                    self.local_remaining_deck_var.set(f"({len(remaining_cards)}) {remaining_text}")
                elif active_game_id_in_state and not self.initial_deck_cards_for_current_game: self.local_remaining_deck_var.set("Deck (Remaining): Capturing..." if self.playstate_read_attempt_count < 3 else "Deck (Remaining): Capture Failed")
                elif not active_game_id_in_state: self.local_remaining_deck_var.set("Deck (Remaining): N/A")
                self.local_snap_status_var.set(lp.get("snap_info", "Snap: N/A")); self.opponent_snap_status_var.set(op.get("snap_info", "Snap: N/A"))
                self.turn_var.set(f"Turn: {gd.get('turn', '?')} / {gd.get('total_turns', '?')}"); self.cubes_var.set(f"Cubes: {gd.get('cube_value', '?')}")
                loc_gui_data, lp_board, op_board, local_is_p1 = gd.get("locations", [{},{},{}]), lp.get("board", [[],[],[]]), op.get("board", [[],[],[]]), gd.get("local_is_gamelogic_player1", False)
                for i in range(3):
                    loc_info = loc_gui_data[i] if i < len(loc_gui_data) else {}; self.location_vars[i]["name"].set(loc_info.get('name', f'Loc {i+1}'))
                    p1p, p2p = loc_info.get('p1_power', '?'), loc_info.get('p2_power', '?'); self.location_vars[i]["power"].set(f"P: {p1p} (You) - {p2p} (Opp)" if local_is_p1 else f"P: {p1p} (Opp) - {p2p} (You)")
                    self.location_vars[i]["local_cards"].set("\n".join(lp_board[i]) if i < len(lp_board) and lp_board[i] else " \n \n "); self.location_vars[i]["opp_cards"].set("\n".join(op_board[i]) if i < len(op_board) and op_board[i] else " \n \n ")
                self.local_player_name_var.set(lp.get("name", "You")); self.local_energy_var.set(f"Energy: {lp.get('energy', '?/?')}"); self.local_hand_var.set((", ".join(lp.get("hand", [])) if lp.get("hand") else "Empty")); self.local_deck_var.set(f"Deck: {lp.get('deck_count', '?')}"); self.local_graveyard_var.set((", ".join(lp.get("graveyard", [])) if lp.get("graveyard") else "Empty")); self.local_banished_var.set((", ".join(lp.get("banished", [])) if lp.get("banished") else "Empty"))
                self.opponent_name_var.set(current_opponent_name_from_data); self.opponent_energy_var.set(f"Energy: {op.get('energy', '?/?')}"); self.opponent_hand_var.set(f"Hand: {op.get('hand_count', '?')} cards"); self.opponent_graveyard_var.set((", ".join(op.get("graveyard", [])) if op.get("graveyard") else "Empty")); self.opponent_banished_var.set((", ".join(op.get("banished", [])) if op.get("banished") else "Empty"))
                end_game_info = game_data.get('end_game_data')
                if end_game_info and end_game_info.get('game_id') and end_game_info.get('game_id') != self.last_recorded_game_id:
                    game_id_to_record = end_game_info['game_id']; events_for_this_match = self.current_game_events.get(game_id_to_record, [])
                    if record_match_result(end_game_info, self.deck_collection_map, {game_id_to_record: events_for_this_match}, self.card_db):
                        self.last_recorded_game_id = game_id_to_record; self.log_error(f"Match {game_id_to_record} outcome recorded.", "")
                        self.load_history_tab_data(); self.load_card_stats_data(); self.load_matchup_data(); self.load_location_stats(); self.update_trends()
                        if game_id_to_record in self.current_game_events:
                            try:
                                del self.current_game_events[game_id_to_record]
                            except KeyError:
                                pass
                    self.current_game_id_for_deck_tracker = None; self.initial_deck_cards_for_current_game = []; self.playstate_deck_id_last_seen = None; self.playstate_read_attempt_count = 0; self.local_remaining_deck_var.set("Deck (Remaining): N/A")
                elif not end_game_info and self.last_recorded_game_id: self.last_recorded_game_id = None
            if hasattr(self, 'deck_modal') and self.deck_modal.winfo_viewable(): self._update_deck_modal_contents()
        except Exception as e: self.status_var.set(f"Update Loop Error: {e}"); self.log_error(f"Unhandled error in update_data_loop: {e}", traceback.format_exc())
        self.root.after(int(self.config.get('Settings', 'update_interval', fallback=1500)), self.update_data_loop)

    def create_deck_stats_modal(self):
        self.deck_modal = tk.Toplevel(self.root); self.deck_modal.withdraw(); self.deck_modal.title("Deck Statistics"); self.deck_modal.transient(self.root); self.deck_modal.protocol("WM_DELETE_WINDOW", self.hide_deck_modal)
        screen_width, screen_height = self.root.winfo_screenwidth(), self.root.winfo_screenheight(); modal_width, modal_height = min(500, screen_width - 100), min(700, screen_height - 100)
        x, y = (screen_width - modal_width) // 2, (screen_height - modal_height) // 2; self.deck_modal.geometry(f"{modal_width}x{modal_height}+{x}+{y}")
        bg_color = self.config['Colors']['bg_main']; self.deck_modal.configure(background=bg_color)
        main_container = ttk.Frame(self.deck_modal); main_container.pack(fill=tk.BOTH, expand=True)
        header_frame = ttk.Frame(main_container); header_frame.pack(fill=tk.X, pady=(10, 5), padx=10)
        self.deck_modal_name_var = tk.StringVar(value="Current Deck"); ttk.Label(header_frame, textvariable=self.deck_modal_name_var, font=("Arial", 14, "bold")).pack(side=tk.LEFT)
        ttk.Button(header_frame, text="×", command=self.hide_deck_modal, width=3).pack(side=tk.RIGHT)
        stats_frame = ttk.Frame(main_container); stats_frame.pack(fill=tk.X, pady=5, padx=10)
        self.deck_modal_stats = {"Cubes": tk.StringVar(value="+0"), "Avg Win": tk.StringVar(value="0"), "Avg Loss": tk.StringVar(value="0"), "Avg Net": tk.StringVar(value="0"), "Games": tk.StringVar(value="0-0"), "Win %": tk.StringVar(value="0%")}
        for i, (stat_name, stat_var) in enumerate(self.deck_modal_stats.items()):
            stat_frame = ttk.Frame(stats_frame); stat_frame.pack(side=tk.LEFT, padx=5, expand=True)
            ttk.Label(stat_frame, text=stat_name, font=("Arial", 8)).pack(side=tk.TOP); ttk.Label(stat_frame, textvariable=stat_var, font=("Arial", 12, "bold")).pack(side=tk.TOP)
        card_grid_frame = ttk.Frame(main_container); card_grid_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.deck_modal_card_frame = ttk.Frame(card_grid_frame); self.deck_modal_card_frame.pack(fill=tk.BOTH, expand=True)
        bottom_frame = ttk.Frame(main_container); bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5, padx=10)
        self.deck_modal_card_counts = {"In Deck": tk.StringVar(value="0"), "Drawn": tk.StringVar(value="0"), "Played": tk.StringVar(value="0")}
        for i, (count_name, count_var) in enumerate(self.deck_modal_card_counts.items()):
            icon_text = "📚" if count_name == "In Deck" else "👁️" if count_name == "Drawn" else "🎮"; count_frame = ttk.Frame(bottom_frame); count_frame.pack(side=tk.LEFT, padx=20, expand=True)
            ttk.Label(count_frame,text=icon_text,font=("Arial", 14)).pack(side=tk.LEFT, padx=5); ttk.Label(count_frame,textvariable=count_var,font=("Arial", 12, "bold")).pack(side=tk.LEFT)
        self.deck_modal_update_timer = None; self.deck_modal.bind("<Configure>", self.on_deck_modal_resize); self.last_deck_modal_size = (0, 0)

    def on_deck_modal_resize(self, event):
        if event.widget != self.deck_modal: return
        new_width, new_height = event.width, event.height
        if (abs(new_width - self.last_deck_modal_size[0]) > 10 or abs(new_height - self.last_deck_modal_size[1]) > 10): self.last_deck_modal_size = (new_width, new_height); self.update_deck_modal_after_resize()

    def update_deck_modal_after_resize(self):
        if hasattr(self, 'resize_update_id') and self.resize_update_id: self.deck_modal.after_cancel(self.resize_update_id)
        self.resize_update_id = self.deck_modal.after(100, lambda: self.show_deck_modal(is_resize=True))

    def show_deck_modal(self, is_resize=False):
        if not hasattr(self, 'deck_modal') or not self.deck_modal.winfo_exists(): self.create_deck_stats_modal()
        self._update_deck_modal_contents(is_resize=is_resize)
        if not self.deck_modal.winfo_viewable(): self.deck_modal.deiconify(); self.deck_modal.lift(); self.deck_modal.focus_set()
        else: self.deck_modal.lift()
        if hasattr(self, 'resize_update_id') and self.resize_update_id: self.deck_modal.after_cancel(self.resize_update_id); self.resize_update_id = None

    def _update_deck_modal_contents(self, is_resize=False):
        current_deck_name, deck_id = "Current Deck", None
        if self.initial_deck_cards_for_current_game:
            try:
                conn_lookup = sqlite3.connect(DB_NAME); cursor_lookup = conn_lookup.cursor()
                unique_normalized_list = sorted(list(set(str(cid) for cid in self.initial_deck_cards_for_current_game if cid)))
                deck_hash = hashlib.sha256(json.dumps(unique_normalized_list).encode('utf-8')).hexdigest()
                cursor_lookup.execute("SELECT id, deck_name FROM decks WHERE deck_hash = ?", (deck_hash,)); result = cursor_lookup.fetchone()
                if result: deck_id, current_deck_name = result[0], result[1] or "Unnamed Deck"
                conn_lookup.close()
            except Exception as e: print(f"DEBUG: Error looking up current deck by hash: {e}")
        elif self.playstate_deck_id_last_seen and self.deck_collection_map and self.playstate_deck_id_last_seen in self.deck_collection_map:
            deck_info = self.deck_collection_map[self.playstate_deck_id_last_seen]; current_deck_name = deck_info.get("name", "Current Deck"); deck_hash = deck_info.get("hash")
            if deck_hash:
                try:
                    conn_lookup = sqlite3.connect(DB_NAME)
                    cursor_lookup = conn_lookup.cursor()
                    cursor_lookup.execute("SELECT id FROM decks WHERE deck_hash = ?", (deck_hash,))
                    result = cursor_lookup.fetchone()
                    deck_id = result[0] if result else None
                    conn_lookup.close()
                except Exception as e:
                    print(f"DEBUG: Error looking up deck by PlayState hash: {e}")
        self.deck_modal_name_var.set(current_deck_name)
        if not is_resize:
            for key, default_val in {"Cubes": "+0", "Avg Win": "0", "Avg Loss": "0", "Avg Net": "0", "Games": "0-0", "Win %": "0%"}.items(): self.deck_modal_stats[key].set(default_val)
            if deck_id:
                try:
                    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*), SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END), SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END), SUM(cubes_changed), AVG(CASE WHEN result = 'win' THEN cubes_changed ELSE NULL END), AVG(CASE WHEN result = 'loss' THEN ABS(cubes_changed) ELSE NULL END) FROM matches WHERE deck_id = ?", (deck_id,)); stats = cursor.fetchone(); conn.close()
                    if stats and stats[0] > 0:
                        games, wins, losses, net_cubes, avg_win_cubes, avg_loss_cubes = stats; net_cubes, wins, losses, avg_win_cubes, avg_loss_cubes = net_cubes or 0, wins or 0, losses or 0, avg_win_cubes or 0, avg_loss_cubes or 0
                        self.deck_modal_stats["Cubes"].set(f"+{net_cubes}" if net_cubes > 0 else str(net_cubes)); self.deck_modal_stats["Avg Win"].set(f"{avg_win_cubes:.1f}"); self.deck_modal_stats["Avg Loss"].set(f"{avg_loss_cubes:.1f}"); self.deck_modal_stats["Avg Net"].set(f"{(net_cubes/games):.1f}" if games > 0 else "0"); self.deck_modal_stats["Games"].set(f"{wins}-{losses}"); self.deck_modal_stats["Win %"].set(f"{(wins/games*100):.1f}%" if games > 0 else "0%")
                except Exception as e: print(f"DEBUG: Error getting deck stats for modal: {e}"); self.log_error(f"DB Error getting modal stats: {e}")
        if not self.initial_deck_cards_for_current_game or is_resize: self.deck_modal.update_idletasks()
        card_frame_container = self.deck_modal_card_frame; force_redraw = not hasattr(self, 'current_card_widgets') or not self.current_card_widgets
        if not is_resize or force_redraw: [widget.destroy() for widget in card_frame_container.winfo_children()]; self.current_card_widgets = {}
        in_deck_count, drawn_count, played_count = 0,0,0
        if self.initial_deck_cards_for_current_game:
            card_counts = Counter(self.initial_deck_cards_for_current_game); unique_cards = sorted(card_counts.keys())
            current_drawn_cards, current_played_cards = set(), set()
            if self.current_game_id_for_deck_tracker and self.current_game_id_for_deck_tracker in self.current_game_events:
                for event in self.current_game_events[self.current_game_id_for_deck_tracker]:
                    if event['player'] == 'local':
                        if event['type'] == 'drawn': current_drawn_cards.add(event['card'])
                        elif event['type'] == 'played': current_played_cards.add(event['card']); current_drawn_cards.add(event['card'])
            num_cards = len(unique_cards); container_width, container_height = max(200, card_frame_container.winfo_width()), max(200, card_frame_container.winfo_height())
            columns = 3 if num_cards <= 12 else 4; rows = (num_cards + columns - 1) // columns
            h_padding, v_padding = 5 * (columns + 1), 5 * (rows + 1); card_width, card_height = max(60, (container_width - h_padding) // columns), max(84, (container_height - v_padding) // rows) if rows > 0 else container_height
            for c in range(columns): card_frame_container.grid_columnconfigure(c, weight=1, minsize=card_width)
            for r in range(rows): card_frame_container.grid_rowconfigure(r, weight=1, minsize=card_height)
            for i, card_id in enumerate(unique_cards):
                row, col = i // columns, i % columns; is_played, is_drawn = card_id in current_played_cards, card_id in current_drawn_cards and not is_played; status = "played" if is_played else "drawn" if is_drawn else "in_deck"
                if is_played:
                    played_count +=1
                elif is_drawn:
                    drawn_count +=1
                else:
                    in_deck_count +=1
                widget_info = self.current_card_widgets.get(card_id); needs_redraw = not widget_info or widget_info['status'] != status or is_resize or force_redraw
                if needs_redraw:
                    if widget_info: widget_info['frame'].destroy()
                    card_frame = tk.Frame(card_frame_container, bg=self.config['Colors']['bg_secondary'], highlightthickness=1, highlightbackground="#000000" if status == 'in_deck' else ('#888888' if status == 'drawn' else '#555555')); card_frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew"); card_frame.pack_propagate(False); card_frame.grid_propagate(False)
                    fg_color = self.config['Colors']['fg_main'] if status == 'in_deck' else '#AAAAAA' if status == 'drawn' else '#777777'
                    image_path = os.path.join(CARD_IMAGES_DIR, f"{card_id}.jpg"); image_loaded = False
                    if os.path.exists(image_path):
                        try:
                            inner_width, inner_height = card_width - 6, card_height - 6
                            if inner_width > 10 and inner_height > 10:
                                pil_image = Image.open(image_path).convert("RGBA")
                                if status != 'in_deck': pil_image = pil_image.convert('L').convert('RGBA'); overlay = Image.new('RGBA', pil_image.size, (100,100,100,90)); pil_image = Image.alpha_composite(pil_image, overlay)
                                img_w, img_h = pil_image.size; ratio = min(inner_width / img_w, inner_height / img_h); new_w, new_h = int(img_w * ratio), int(img_h * ratio)
                                if new_w > 0 and new_h > 0: pil_image = pil_image.resize((new_w, new_h), Image.LANCZOS); photo = ImageTk.PhotoImage(pil_image); img_label = tk.Label(card_frame, image=photo, bg=card_frame['bg']); img_label.image = photo; img_label.pack(expand=True); image_loaded = True
                        except Exception as img_e: print(f"Error loading img {card_id}: {img_e}")
                    if not image_loaded: card_name = self.card_db.get(card_id, {}).get('name', card_id) if self.card_db else card_id; tk.Label(card_frame, text=card_name, fg=fg_color, bg=card_frame['bg'], font=("Arial", 9, "bold"), wraplength=card_width - 10, justify='center').pack(expand=True, padx=5, pady=5)
                    self.current_card_widgets[card_id] = {'frame': card_frame, 'status': status}
        else:
             if not is_resize: [widget.destroy() for widget in card_frame_container.winfo_children()]; ttk.Label(card_frame_container, text="No deck data available.").pack(expand=True); self.current_card_widgets = {}
        self.deck_modal_card_counts["In Deck"].set(str(in_deck_count)); self.deck_modal_card_counts["Drawn"].set(str(drawn_count)); self.deck_modal_card_counts["Played"].set(str(played_count))

    def hide_deck_modal(self):
        if hasattr(self, 'deck_modal') and self.deck_modal.winfo_exists(): self.deck_modal.withdraw()

    def download_all_card_images(self):
        if not self.card_db: print("No card database available for image download"); return
        if not os.path.exists(CARD_IMAGES_DIR):
            try: os.makedirs(CARD_IMAGES_DIR)
            except OSError as e: print(f"Error creating image directory {CARD_IMAGES_DIR}: {e}"); return
        print(f"Starting background download of card images to {CARD_IMAGES_DIR}"); downloaded, errors, total_cards = 0,0,len(self.card_db)
        for i, (card_id, card_info) in enumerate(self.card_db.items()):
            image_path = os.path.join(CARD_IMAGES_DIR, f"{card_id}.jpg")
            if os.path.exists(image_path): continue
            image_url = card_info.get('image_url')
            if not image_url: continue
            try:
                response = requests.get(image_url, timeout=10, stream=True); response.raise_for_status()
                with open(image_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192): f.write(chunk)
                downloaded += 1
                if downloaded % 20 == 0 or i == total_cards - 1: print(f"Downloaded {downloaded}/{total_cards - i + downloaded + errors} card images...")
            except requests.exceptions.RequestException as e:
                errors += 1; print(f"Error downloading image for {card_id} ({card_info.get('name', '')}) from {image_url}: {e}")
                if os.path.exists(image_path):
                    try: os.remove(image_path)
                    except OSError: pass
            except Exception as e:
                errors += 1; print(f"Unexpected error processing image for {card_id}: {e}")
                if os.path.exists(image_path):
                     try: os.remove(image_path)
                     except OSError: pass
        print(f"Finished downloading images. Added: {downloaded}, Errors: {errors}")

    def cleanup_duplicate_events_command(self):
        if not messagebox.askyesno("Confirm Event Cleanup","This will attempt to remove duplicate entries from the match events log.\nIt's recommended to backup your database first.\n\nProceed with cleanup?",icon=messagebox.WARNING): return
        try:
            conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
            cursor.execute("DELETE FROM match_events WHERE id NOT IN (SELECT MIN(id) FROM match_events GROUP BY game_id, turn, event_type, player_type, card_def_id, location_index, source_zone, target_zone, details_json)"); exact_duplicates_removed = cursor.rowcount; conn.commit()
            cursor.execute("DELETE FROM match_events WHERE event_type = 'drawn' AND player_type = 'local' AND id NOT IN (SELECT MIN(id) FROM match_events WHERE event_type = 'drawn' AND player_type = 'local' GROUP BY game_id, card_def_id)"); drawn_duplicates_removed = cursor.rowcount; conn.commit()
            conn.close(); total_removed = exact_duplicates_removed + drawn_duplicates_removed
            messagebox.showinfo("Cleanup Complete", f"Event cleanup finished.\n- Exact duplicates removed: {exact_duplicates_removed}\n- Redundant 'drawn' events removed: {drawn_duplicates_removed}\n- Total rows removed: {total_removed}")
            self.refresh_all_data()
        except sqlite3.Error as e: messagebox.showerror("Cleanup Error", f"Database error during cleanup:\n{e}"); self.log_error(f"Error during event cleanup: {e}", traceback.format_exc())
        except Exception as e: messagebox.showerror("Cleanup Error", f"An unexpected error occurred:\n{e}"); self.log_error(f"Unexpected error during event cleanup: {e}", traceback.format_exc())

if __name__ == "__main__":
    init_db()
    root = tk.Tk()
    # The necessary get_config() and apply_theme() calls are made within SnapTrackerApp's __init__
    # using the versions that will be imported from config_utils.py.
    app = SnapTrackerApp(root)
    root.mainloop()
