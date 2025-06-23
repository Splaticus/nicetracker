import os, json, time, hashlib, requests
from tkinter import filedialog, messagebox
from .config import DECK_COLLECTION_CACHE, COLLECTION_STATE_FILE, PLAY_STATE_FILE, CARD_DATA_FILE, CARD_IMAGES_DIR, get_config, save_config

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
