import sqlite3
import json
import os # Not immediately needed for DB_NAME or init_db, but good for a utils file
import hashlib
import csv
import time
import datetime

DB_NAME = "snap_match_history.db"

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

# Functions will be appended below.
