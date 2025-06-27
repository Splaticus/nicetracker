import os, sqlite3, json, hashlib, csv, time, traceback
from collections import Counter
from .config import DB_NAME, VERSION
from .utils import build_id_map, resolve_ref, extract_cards_with_details

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Create tables if they don't exist
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
    
    # Function to add columns if they don't exist
    def add_column_if_not_exists(table_name, column_name, column_type):
        cursor.execute(f"PRAGMA table_info({table_name})")
        column_exists = any(col[1] == column_name for col in cursor.fetchall())
        if not column_exists:
            print(f"Adding column {column_name} to table {table_name}...")
            try:
                 cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                 print(f"Successfully added column {column_name}.")
            except sqlite3.OperationalError as e:
                 print(f"Could not add column {column_name} to {table_name}: {e}") # Catch specific error if needed
        # else: # Optional: Print if column already exists
        #     print(f"Column {column_name} already exists in table {table_name}.")


    # Add new columns to matches table
    try:
        match_cols_to_add = {
            "loc_1_def_id": "TEXT", 
            "loc_2_def_id": "TEXT", 
            "loc_3_def_id": "TEXT", 
            "snap_turn_player": "INTEGER", 
            "snap_turn_opponent": "INTEGER", 
            "final_snap_state": "TEXT", 
            "opp_revealed_cards_json": "TEXT",
            "season": "TEXT",
            "rank": "TEXT",
            "notes": "TEXT"
        }
        for col, typ in match_cols_to_add.items(): 
            add_column_if_not_exists("matches", col, typ)
    except sqlite3.Error as e: 
        print(f"DB Error altering matches table structure: {e}")
    
    # Add new columns to decks table
    try:
        deck_cols_to_add = {
            "collection_deck_id": "TEXT", 
            "last_used": "TIMESTAMP",
            "tags": "TEXT"
        }
        for col, typ in deck_cols_to_add.items(): 
            add_column_if_not_exists("decks", col, typ)
        
        # Ensure last_used is populated if the column exists
        cursor.execute("PRAGMA table_info(decks)")
        deck_columns = [info[1] for info in cursor.fetchall()]
        if 'last_used' in deck_columns and 'first_seen' in deck_columns:
             cursor.execute("UPDATE decks SET last_used = first_seen WHERE last_used IS NULL")
    except sqlite3.Error as e: 
        print(f"DB Error altering decks table structure: {e}")
    
    # Create indexes for better performance
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_deck_id ON matches (deck_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_timestamp ON matches (timestamp_ended)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_opponent ON matches (opponent_player_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_result ON matches (result)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_game_id ON match_events (game_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_card_id ON match_events (card_def_id)")

        # --- Handle UNIQUE index creation carefully ---
        try:
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uidx_events_unique 
                ON match_events(game_id, turn, event_type, player_type, card_def_id, 
                                location_index, source_zone, target_zone, details_json)
            """)
        except sqlite3.IntegrityError:
            print("-----------------------------------------------------------")
            print("WARNING: Could not create unique index on 'match_events'.")
            print("This usually means duplicate events already exist in your database.")
            print("Please use the 'Tools -> Database -> Clean Duplicate Events' menu")
            print("option to remove duplicates. The index will be created automatically")
            print("the next time the application starts after successful cleanup.")
            print("-----------------------------------------------------------")
            # Do not crash, allow the application to continue starting.
            pass # Ignore the error for now.
        except sqlite3.OperationalError as op_err:
             # This might happen if the index exists but definition differs, etc.
             print(f"Operational error creating unique index (might be ignorable): {op_err}")
             pass

    except sqlite3.Error as e:
         print(f"Error creating indexes: {e}")


    conn.commit()
    conn.close()

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

def calculate_snap_statistics(deck_id=None):
    """Calculate snap-related statistics."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    query = """
        SELECT
            COUNT(*) as games,
            SUM(CASE WHEN snap_turn_player > 0 THEN 1 ELSE 0 END) as snapped_games,
            SUM(CASE WHEN snap_turn_player > 0 AND result = 'win' THEN 1 ELSE 0 END) as snapped_wins,
            SUM(CASE WHEN snap_turn_opponent > 0 THEN 1 ELSE 0 END) as opp_snapped_games,
            SUM(CASE WHEN snap_turn_opponent > 0 AND result = 'win' THEN 1 ELSE 0 END) as opp_snapped_wins
        FROM matches
    """

    params = []
    if deck_id and deck_id != "all":
        query += " WHERE deck_id = ?"
        params.append(deck_id)

    cursor.execute(query, tuple(params))
    row = cursor.fetchone()
    conn.close()

    if row:
        games, snapped_games, snapped_wins, opp_snapped_games, opp_snapped_wins = row
        return {
            'games': games or 0,
            'snapped_games': snapped_games or 0,
            'snapped_wins': snapped_wins or 0,
            'opp_snapped_games': opp_snapped_games or 0,
            'opp_snapped_wins': opp_snapped_wins or 0
        }
    return None

