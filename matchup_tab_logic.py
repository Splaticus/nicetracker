import sqlite3
import json
from collections import Counter
import datetime # Added for load_matchup_details

# Assuming DB_NAME will be accessible, e.g., from a config module or passed
# For now, let's define it here if it's not picked up from nicetracker globally
# If nicetracker.py is the main module, this might work due to Python's import system,
# but it's better to be explicit.
DB_NAME = "snap_match_history.db" # TODO: Refactor DB_NAME to a central config

def load_matchup_data(app_instance, event=None):
    """Load matchup statistics"""
    # Get filter values
    selected_deck = app_instance.matchup_deck_filter_var.get()
    selected_season = app_instance.matchup_season_filter_var.get()

    # Clear current data
    for item in app_instance.matchup_tree.get_children():
        app_instance.matchup_tree.delete(item)

    # Clear details
    if hasattr(app_instance, 'revealed_cards_tree'): # Check if tree exists
        for item in app_instance.revealed_cards_tree.get_children():
            app_instance.revealed_cards_tree.delete(item)

    if hasattr(app_instance, 'matchup_history_tree'): # Check if tree exists
        for item in app_instance.matchup_history_tree.get_children():
            app_instance.matchup_history_tree.delete(item)

    if hasattr(app_instance, 'matchup_summary_var'): # Check if var exists
        app_instance.matchup_summary_var.set("Select an opponent to view matchup details")

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

        wins = wins if wins is not None else 0
        losses = losses if losses is not None else 0
        ties = ties if ties is not None else 0

        # Calculate win rate
        win_rate = (wins / matches * 100) if matches > 0 else 0

        # Calculate average cubes
        avg_cubes = (net_cubes / matches) if matches > 0 and net_cubes is not None else 0

        if hasattr(app_instance, 'matchup_tree'): # Check if tree exists
            app_instance.matchup_tree.insert(
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

# Placeholder for other functions that will be added:
# def on_matchup_select(app_instance, event):
#     pass

# def load_matchup_details(app_instance, opponent_name):
#     pass

def on_matchup_select(app_instance, event):
    """Handle selection of an opponent in the matchup view"""
    selected_item = app_instance.matchup_tree.focus()
    if not selected_item:
        return

    # Get the opponent name
    values = app_instance.matchup_tree.item(selected_item, "values")
    opponent_name = values[0]

    # Update details
    load_matchup_details(app_instance, opponent_name) # Call local function within this module

def load_matchup_details(app_instance, opponent_name):
    """Load detailed matchup information for an opponent"""
    # Get filter values
    selected_deck = app_instance.matchup_deck_filter_var.get()
    selected_season = app_instance.matchup_season_filter_var.get()

    # Clear current data in the details section
    if hasattr(app_instance, 'revealed_cards_tree'):
        for item in app_instance.revealed_cards_tree.get_children():
            app_instance.revealed_cards_tree.delete(item)
    if hasattr(app_instance, 'matchup_history_tree'):
        for item in app_instance.matchup_history_tree.get_children():
            app_instance.matchup_history_tree.delete(item)
    if hasattr(app_instance, 'matchup_summary_var'):
        app_instance.matchup_summary_var.set("Loading details...")

    # Connect to database
    conn = sqlite3.connect(DB_NAME) # Assumes DB_NAME is available
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
        cursor.execute(final_query_summary, tuple(params_summary))
        summary_data = cursor.fetchone()

        matches = 0
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
            if hasattr(app_instance, 'matchup_summary_var'):
                app_instance.matchup_summary_var.set(summary_text)
        else:
            if hasattr(app_instance, 'matchup_summary_var'):
                 app_instance.matchup_summary_var.set(f"Opponent: {opponent_name}\nNo match data found for the selected filters.")

        if matches > 0:
            # --- Get Revealed Cards ---
            query_parts_revealed = ["""
                SELECT m.opp_revealed_cards_json FROM matches m
                LEFT JOIN decks d ON m.deck_id = d.id
                WHERE m.opponent_player_name = ?
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

            cursor.execute(" ".join(query_parts_revealed), tuple(params_revealed))
            revealed_cards_data = cursor.fetchall()

            revealed_card_counter = Counter()
            valid_revealed_games = 0
            for row in revealed_cards_data:
                try:
                    cards_json = row[0]
                    if cards_json:
                        cards = json.loads(cards_json)
                        if isinstance(cards, list):
                            revealed_card_counter.update(cards)
                            valid_revealed_games +=1
                except (json.JSONDecodeError, TypeError): continue

            if hasattr(app_instance, 'revealed_cards_tree'):
                most_common_cards = revealed_card_counter.most_common(20)
                for card_id, count in most_common_cards:
                    card_name = card_id
                    if app_instance.card_db and app_instance.display_card_names_var.get() and card_id in app_instance.card_db:
                        card_name = app_instance.card_db[card_id].get('name', card_id)
                    percentage = (count / valid_revealed_games * 100) if valid_revealed_games > 0 else 0
                    app_instance.revealed_cards_tree.insert("", "end", values=(card_name, count, f"{percentage:.1f}%"), tags=(card_id,))

            # --- Get Match History ---
            query_parts_history = ["""
                SELECT m.timestamp_ended, COALESCE(d.deck_name, 'Unknown Deck'),
                       m.result, m.cubes_changed, m.opp_revealed_cards_json, m.notes, m.game_id
                FROM matches m LEFT JOIN decks d ON m.deck_id = d.id
                WHERE m.opponent_player_name = ?
            """]
            params_history = [opponent_name]
            if selected_deck != "All Decks":
                query_parts_history.append("AND d.deck_name = ?")
                params_history.append(selected_deck)
            if selected_season != "All Seasons":
                query_parts_history.append("AND m.season = ?")
                params_history.append(selected_season)
            query_parts_history.append("ORDER BY m.timestamp_ended DESC")

            cursor.execute(" ".join(query_parts_history), tuple(params_history))
            history_data = cursor.fetchall()

            if hasattr(app_instance, 'matchup_history_tree'):
                for row_hist in history_data:
                    timestamp, deck_name, result, cubes, revealed_json, notes, game_id_hist = row_hist
                    try: date_str = datetime.datetime.strptime(timestamp.split('.')[0], "%Y-%m-%d %H:%M:%S").strftime("%y-%m-%d %H:%M")
                    except: date_str = timestamp

                    revealed_str = "None"
                    if revealed_json and revealed_json.lower() != 'null':
                        try:
                            cards_rev = json.loads(revealed_json)
                            if cards_rev:
                                card_display_list = []
                                if app_instance.card_db and app_instance.display_card_names_var.get():
                                    for cid_rev in cards_rev: card_display_list.append(app_instance.card_db.get(cid_rev, {}).get('name', cid_rev))
                                else: card_display_list = cards_rev
                                revealed_str = ", ".join(card_display_list)
                        except json.JSONDecodeError: revealed_str = "Error Parsing" # More specific

                    app_instance.matchup_history_tree.insert("", "end",
                        values=(date_str, deck_name, result.capitalize() if result else "N/A", cubes if cubes is not None else 0, revealed_str),
                        iid=game_id_hist, tags=(result if result else 'unknown',))

    except sqlite3.Error as db_e:
        # It's better to log errors or handle them rather than just printing to console in a library file
        # For now, keeping print for visibility during development via tool
        print(f"ERROR: Database error loading matchup details for {opponent_name}: {db_e}")
        # Consider using app_instance.log_error if available and appropriate
        if hasattr(app_instance, 'log_error'): app_instance.log_error(f"DB Error loading details for {opponent_name}: {db_e}", "")
        if hasattr(app_instance, 'matchup_summary_var'): app_instance.matchup_summary_var.set(f"Error loading details for {opponent_name}.")
    except Exception as e:
        print(f"ERROR: Unexpected error loading matchup details for {opponent_name}: {e}")
        if hasattr(app_instance, 'log_error'): app_instance.log_error(f"Error loading details for {opponent_name}: {e}", "")
        if hasattr(app_instance, 'matchup_summary_var'): app_instance.matchup_summary_var.set(f"Error loading details for {opponent_name}.")
    finally:
        if conn:
            conn.close()

def sort_matchup_treeview(app_instance, col, reverse):
    """Sort matchup treeview by column"""
    if not hasattr(app_instance, 'matchup_tree'): return

    data = [(app_instance.matchup_tree.set(child, col), child) for child in app_instance.matchup_tree.get_children('')]

    def create_sort_key(value_from_cell):
        s_value = str(value_from_cell)
        if s_value == "N/A": return (0, -float('inf'))
        numeric_candidate_str = s_value.replace('%', '')
        try: return (0, int(numeric_candidate_str))
        except ValueError:
            try: return (0, float(numeric_candidate_str))
            except ValueError:
                if not s_value.strip(): return (1, "")
                return (1, s_value.lower())

    data.sort(key=lambda t: create_sort_key(t[0]), reverse=reverse)

    for index, (val, child) in enumerate(data):
        app_instance.matchup_tree.move(child, '', index)

    app_instance.matchup_tree.heading(col, command=lambda _col=col: sort_matchup_treeview(app_instance, _col, not reverse))
