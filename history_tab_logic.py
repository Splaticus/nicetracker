import csv
import sqlite3
from tkinter import filedialog, messagebox
from db_utils import DB_NAME
import tkinter as tk # For tk.END and tk.StringVar if used by apply_history_filter's dependencies
from tkinter import ttk # Required for OptionMenu if used by apply_history_filter's dependencies
import json # Added for on_history_match_select
import traceback # For potential error logging in export_selected_matches

# from nicetracker import get_card_tooltip_text # Will add later if on_history_match_select needs it

def load_history_tab_data(app_instance):
    """Load/refresh data for the match history tab"""
    if not app_instance.history_tree:
        return

    for i in app_instance.history_tree.get_children():
        app_instance.history_tree.delete(i)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Populate deck names for filter (also used by other tabs)
    cursor.execute("SELECT DISTINCT deck_name FROM decks ORDER BY deck_name")
    deck_names = [row[0] for row in cursor.fetchall() if row[0]]
    app_instance.all_deck_names_for_filter = sorted(list(set(deck_names))) # Update the master list

    # Update history tab deck filter options
    # The actual menu update is handled by _create_deck_filter_dialog or show_history_deck_filter_dialog
    # but we ensure the source list (app_instance.all_deck_names_for_filter) is up-to-date here.

    # Populate season names for filter
    cursor.execute("SELECT DISTINCT season FROM matches WHERE season IS NOT NULL ORDER BY season DESC")
    seasons = ["All Seasons"] + [row[0] for row in cursor.fetchall()]
    if hasattr(app_instance, 'season_filter_menu') and app_instance.season_filter_menu:
        menu = app_instance.season_filter_menu["menu"]
        menu.delete(0, "end")
        for season_name in seasons:
            menu.add_command(label=season_name, command=lambda value=season_name: (app_instance.season_filter_var.set(value), apply_history_filter(app_instance)))
        if app_instance.season_filter_var.get() not in seasons: # Ensure current selection is valid
                app_instance.season_filter_var.set("All Seasons")
    else:
        print("LOG_WARNING: season_filter_menu not found on app_instance in load_history_tab_data")


    conn.close()
    apply_history_filter(app_instance)

def apply_history_filter(app_instance, event=None):
    """Apply current filters to the match history view and update summary"""
    if not app_instance.history_tree:
        return

    for i in app_instance.history_tree.get_children():
        app_instance.history_tree.delete(i)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    query = """
        SELECT m.game_id, m.timestamp_ended, COALESCE(d.deck_name, 'Unknown Deck'),
               m.opponent_player_name, m.result, m.cubes_changed, m.turns_taken,
               m.loc_1_def_id, m.loc_2_def_id, m.loc_3_def_id, m.id
        FROM matches m
        LEFT JOIN decks d ON m.deck_id = d.id
    """

    conditions = []
    params = []

    if app_instance.history_selected_deck_names:
        deck_placeholders = ','.join(['?'] * len(app_instance.history_selected_deck_names))
        conditions.append(f"COALESCE(d.deck_name, 'Unknown Deck') IN ({deck_placeholders})")
        params.extend(list(app_instance.history_selected_deck_names))

    if hasattr(app_instance, 'season_filter_var'):
        selected_season = app_instance.season_filter_var.get()
        if selected_season != "All Seasons":
            conditions.append("m.season = ?")
            params.append(selected_season)

    if hasattr(app_instance, 'result_filter_var'):
        selected_result = app_instance.result_filter_var.get()
        if selected_result != "All Results":
            conditions.append("m.result = ?")
            params.append(selected_result.lower())

    if hasattr(app_instance, 'search_var'):
        search_term = app_instance.search_var.get()
        if search_term:
            search_pattern = f"%{search_term}%"
            search_conditions = [
                "m.opponent_player_name LIKE ?",
                "COALESCE(d.deck_name, 'Unknown Deck') LIKE ?",
                "m.notes LIKE ?",
                "m.loc_1_def_id LIKE ?",
                "m.loc_2_def_id LIKE ?",
                "m.loc_3_def_id LIKE ?"
            ]
            conditions.append(f"({' OR '.join(search_conditions)})")
            for _ in range(len(search_conditions)):
                params.append(search_pattern)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY m.timestamp_ended DESC"

    cursor.execute(query, tuple(params))

    total_matches = 0
    total_cubes = 0
    wins = 0
    losses = 0
    ties = 0

    for row_data in cursor.fetchall():
        match_db_id = row_data[-1]
        display_row = [str(item) if item is not None else "N/A" for item in row_data[:-1]]

        if app_instance.card_db:
            for i in range(7, 10):
                if display_row[i] != "N/A" and display_row[i] in app_instance.card_db:
                    display_row[i] = app_instance.card_db[display_row[i]].get('name', display_row[i])

        item_id = app_instance.history_tree.insert("", tk.END, values=display_row, iid=str(match_db_id))

        result_val = display_row[4].lower()
        if result_val == 'win':
            app_instance.history_tree.item(item_id, tags=('win',))
            wins += 1
        elif result_val == 'loss':
            app_instance.history_tree.item(item_id, tags=('loss',))
            losses += 1
        elif result_val == 'tie':
            app_instance.history_tree.item(item_id, tags=('neutral',))
            ties += 1

        total_matches +=1
        try:
            total_cubes += int(display_row[5]) if display_row[5] != "N/A" else 0
        except ValueError:
            pass

    conn.close()

    win_rate = (wins / total_matches * 100) if total_matches > 0 else 0
    summary_text = f"Displaying {total_matches} matches. Wins: {wins}, Losses: {losses}, Ties: {ties} (Win Rate: {win_rate:.1f}%). Total Cubes: {total_cubes:+}."
    if hasattr(app_instance, 'stats_summary_var'):
        app_instance.stats_summary_var.set(summary_text)

    if total_matches == 0 or not app_instance.history_tree.selection():
        on_history_match_select(app_instance, None) # Call with app_instance

def sort_history_treeview(app_instance, col, reverse):
    """Sort the history treeview by a column."""
    if not app_instance.history_tree:
        return

    # Get data from treeview
    l = [(app_instance.history_tree.set(k, col), k) for k in app_instance.history_tree.get_children('')]

    # Determine data type for sorting (simple heuristic)
    try:
        # Try to convert to float for numeric sort (e.g., Cubes, Turns)
        # For timestamp, it's already string in a sortable format (usually)
        if col not in ["Timestamp", "Deck", "Opponent", "Result", "Location1", "Location2", "Location3"]:
                l = [(float(val), k) if val != "N/A" else (-float('inf'), k) for val, k in l] # Handle N/A for numeric
        else: # String sort for other columns
            pass # Already strings
    except ValueError:
        pass # Keep as string sort if conversion fails

    l.sort(reverse=reverse)

    # Rearrange items in sorted positions
    for index, (val, k) in enumerate(l):
        app_instance.history_tree.move(k, '', index)

    # Reverse sort next time
    app_instance.history_tree.heading(col, command=lambda: sort_history_treeview(app_instance, col, not reverse))

def on_history_match_double_click(app_instance, event):
    """Handle double-click on a match in the history: offer to delete."""
    if not app_instance.history_tree.selection():
        return

    item_iid = app_instance.history_tree.selection()[0]
    item_values = app_instance.history_tree.item(item_iid, "values")

    match_display_id = item_values[0] if item_values and len(item_values) > 0 and item_values[0] != "N/A" else f"DB ID {item_iid}"

    if messagebox.askyesno("Delete Match", f"Are you sure you want to delete match: {match_display_id}?"):
        delete_selected_matches(app_instance)

def on_history_match_select(app_instance, event):
    """Display details for the selected match in the history tab."""
    if not hasattr(app_instance, 'stats_text_widget') or not app_instance.stats_text_widget or not app_instance.history_tree :
        print("LOG_ERROR: History tree or stats widget not initialized. Source: on_history_match_select")
        return

    selection = app_instance.history_tree.selection()
    if not selection:
        if app_instance.stats_text_widget:
            app_instance.stats_text_widget.config(state=tk.NORMAL)
            app_instance.stats_text_widget.delete(1.0, tk.END)
            app_instance.stats_text_widget.insert(tk.END, "No match selected.")
            app_instance.stats_text_widget.config(state=tk.DISABLED)
        return

    selected_item_iid = selection[0]

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            m.game_id, m.timestamp_ended, COALESCE(d.deck_name, 'Unknown Deck'),
            m.opponent_player_name, m.result, m.cubes_changed, m.turns_taken,
            m.loc_1_def_id, m.loc_2_def_id, m.loc_3_def_id,
            m.snap_turn_player, m.snap_turn_opponent, m.final_snap_state,
            m.opp_revealed_cards_json, d.card_ids_json AS player_deck_cards_json,
            m.notes, m.id
        FROM matches m
        LEFT JOIN decks d ON m.deck_id = d.id
        WHERE m.id = ?
    """, (selected_item_iid,))

    match_details = cursor.fetchone()
    conn.close()

    if not match_details:
        app_instance.stats_text_widget.config(state=tk.NORMAL)
        app_instance.stats_text_widget.delete(1.0, tk.END)
        app_instance.stats_text_widget.insert(tk.END, f"Could not retrieve details for match ID {selected_item_iid}.")
        app_instance.stats_text_widget.config(state=tk.DISABLED)
        return

    details_text = f"Match ID (DB): {match_details[16]}\n"
    details_text += f"Game ID (JSON): {match_details[0]}\n"
    details_text += f"Timestamp: {match_details[1]}\n"
    details_text += f"Deck: {match_details[2]}\n"
    details_text += f"Opponent: {match_details[3]}\n"
    details_text += f"Result: {match_details[4]} ({match_details[5] if match_details[5] is not None else '?':+} cubes)\n"
    details_text += f"Turns: {match_details[6]}\n"

    locations = [match_details[7], match_details[8], match_details[9]]
    loc_names = []
    if app_instance.card_db:
        for loc_id in locations:
            loc_names.append(app_instance.card_db.get(loc_id, {}).get('name', loc_id if loc_id else "N/A"))
    else:
        loc_names = [loc_id if loc_id else "N/A" for loc_id in locations]
    details_text += f"Locations: {', '.join(loc_names)}\n"

    details_text += f"Snaps (You/Opp): T{match_details[10]}/T{match_details[11]}\n"
    details_text += f"Final Snap State: {match_details[12]}\n"

    details_text += "\n--- Your Deck ---\n"
    if match_details[14]:
        try:
            deck_cards_list = json.loads(match_details[14])
            if app_instance.card_db:
                deck_card_names = [app_instance.card_db.get(cid, {}).get('name', cid) for cid in deck_cards_list]
                details_text += "\n".join(sorted(deck_card_names))
            else:
                details_text += "\n".join(sorted(deck_cards_list))
        except json.JSONDecodeError:
            details_text += "Could not decode deck card list."
    else:
        details_text += "Deck list not available."
    details_text += "\n"

    details_text += "\n--- Opponent Revealed Cards ---\n"
    if match_details[13]:
        try:
            opp_cards_list = json.loads(match_details[13])
            if app_instance.card_db:
                opp_card_names = [app_instance.card_db.get(cid, {}).get('name', cid) for cid in opp_cards_list]
                details_text += "\n".join(sorted(opp_card_names))
            else:
                details_text += "\n".join(sorted(opp_cards_list))
        except json.JSONDecodeError:
            details_text += "Could not decode opponent card list."
    else:
        details_text += "No opponent cards recorded."
    details_text += "\n"

    details_text += f"\n--- Notes ---\n{match_details[15] if match_details[15] else 'No notes for this match.'}"

    app_instance.stats_text_widget.config(state=tk.NORMAL)
    app_instance.stats_text_widget.delete(1.0, tk.END)
    app_instance.stats_text_widget.insert(tk.END, details_text)
    app_instance.stats_text_widget.config(state=tk.DISABLED)

def export_selected_matches(app_instance):
    """Export selected matches from the history tree to a CSV file."""
    if not app_instance.history_tree:
        messagebox.showerror("Error", "History tree not available.")
        return

    selected_iids = app_instance.history_tree.selection()
    if not selected_iids:
        messagebox.showinfo("No Selection", "No matches selected to export.")
        return

    filename = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        title="Export Selected Matches"
    )

    if not filename:
        return

    matches_to_export = []
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    for item_iid in selected_iids:
        # The IID of the treeview item is the match database ID (m.id)
        cursor.execute("""
            SELECT
                m.game_id, m.timestamp_ended, COALESCE(d.deck_name, 'Unknown Deck'),
                m.opponent_player_name, m.result, m.cubes_changed, m.turns_taken,
                m.loc_1_def_id, m.loc_2_def_id, m.loc_3_def_id,
                m.snap_turn_player, m.snap_turn_opponent, m.final_snap_state,
                m.opp_revealed_cards_json, COALESCE(d.card_ids_json, '[]') AS player_deck_cards_json,
                m.season, m.rank, m.notes
            FROM matches m
            LEFT JOIN decks d ON m.deck_id = d.id
            WHERE m.id = ?
        """, (item_iid,))
        match_data = cursor.fetchone()
        if match_data:
            # Replace LocationDefIds with names if card_db is available
            processed_match_data = list(match_data)
            if app_instance.card_db:
                for i in range(7, 10): # loc_1_def_id, loc_2_def_id, loc_3_def_id
                    if processed_match_data[i] and processed_match_data[i] in app_instance.card_db:
                        processed_match_data[i] = app_instance.card_db[processed_match_data[i]].get('name', processed_match_data[i])
            matches_to_export.append(processed_match_data)

    conn.close()

    if not matches_to_export:
        messagebox.showinfo("No Data", "Could not retrieve data for the selected matches.")
        return

    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            # Write header - consistent with export_match_history_to_csv
            writer.writerow([
                'Game ID', 'Timestamp', 'Deck Name', 'Opponent', 'Result', 'Cubes',
                'Turns', 'Location 1', 'Location 2', 'Location 3',
                'Your Snap Turn', 'Opponent Snap Turn', 'Final Snap State',
                'Opponent Revealed Cards', 'Your Deck Cards', 'Season', 'Rank', 'Notes'
            ])
            # Write data
            for match_row in matches_to_export:
                writer.writerow(match_row)

        messagebox.showinfo("Export Complete", f"Successfully exported {len(matches_to_export)} matches to {filename}")

    except Exception as e:
        print(f"Error exporting selected matches: {e}: {traceback.format_exc()}")
        messagebox.showerror("Export Error", f"Could not export matches: {e}")

def delete_selected_matches(app_instance):
    """Delete selected matches from the history tree and database."""
    if not app_instance.history_tree:
        messagebox.showerror("Error", "History tree not available.")
        return

    selected_iids = app_instance.history_tree.selection()
    if not selected_iids:
        messagebox.showinfo("No Selection", "No matches selected to delete.")
        return

    confirm_delete = messagebox.askyesno(
        "Confirm Delete",
        f"Are you sure you want to delete {len(selected_iids)} selected match(es)?\nThis will also delete associated event data and is irreversible."
    )

    if not confirm_delete:
        return

    conn = None
    deleted_count = 0
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        match_ids_to_delete_from_tree = []

        for item_iid in selected_iids:
            # item_iid is m.id from the matches table
            cursor.execute("SELECT game_id FROM matches WHERE id = ?", (item_iid,))
            row = cursor.fetchone()
            json_game_id = row[0] if row else None

            cursor.execute("DELETE FROM matches WHERE id = ?", (item_iid,))

            if json_game_id:
                cursor.execute("DELETE FROM match_events WHERE game_id = ?", (json_game_id,))

            if cursor.rowcount > 0 :
                 deleted_count +=1
                 match_ids_to_delete_from_tree.append(item_iid)


        conn.commit()

        if deleted_count > 0:
            messagebox.showinfo("Delete Complete", f"Successfully deleted {deleted_count} match(es).")
        else:
            messagebox.showwarning("Delete Note", "No matches were deleted from the primary match table. They might have been removed already or an issue occurred.")

    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        print(f"Error deleting matches: {e}: {traceback.format_exc()}")
        messagebox.showerror("Delete Error", f"Could not delete matches: {e}")
    finally:
        if conn:
            conn.close()
        load_history_tab_data(app_instance)

def copy_selected_matches_deck_code(app_instance):
    """Copies the deck code (card list) of the selected match's deck to the clipboard."""
    if not app_instance.history_tree:
        messagebox.showerror("Error", "History tree not available.")
        return

    selected_iids = app_instance.history_tree.selection()
    if not selected_iids:
        messagebox.showinfo("No Selection", "No match selected to copy deck code from.")
        return

    if len(selected_iids) > 1:
        messagebox.showinfo("Multiple Selections", "Please select only one match to copy its deck code.")
        return

    item_iid = selected_iids[0] # m.id from matches table
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("SELECT deck_id FROM matches WHERE id = ?", (item_iid,))
        match_row = cursor.fetchone()

        if not match_row or match_row[0] is None:
            messagebox.showerror("Error", "Could not find deck information for the selected match.")
            return

        deck_db_id = match_row[0]

        cursor.execute("SELECT card_ids_json, deck_name FROM decks WHERE id = ?", (deck_db_id,))
        deck_row = cursor.fetchone()

        if not deck_row or not deck_row[0]:
            messagebox.showerror("Error", f"Could not find card list for deck ID {deck_db_id}.")
            return

        card_ids_json_str = deck_row[0]
        deck_name = deck_row[1] if deck_row[1] else "Unknown Deck"

        try:
            card_ids_list = json.loads(card_ids_json_str)

            output_lines = [f"# Deck: {deck_name}"]
            if app_instance.card_db:
                for card_id_str in card_ids_list: # Assuming card_ids_list contains strings
                    card_info = app_instance.card_db.get(card_id_str)
                    if card_info:
                        output_lines.append(f"# {card_info.get('name', card_id_str)}")
                    else:
                        output_lines.append(f"# {card_id_str} (Unknown)")
            else:
                 for card_id_str in card_ids_list:
                    output_lines.append(f"# {card_id_str}")

            # For actual game import, a base64 encoded JSON is often used.
            # Here, we provide a human-readable list and the raw JSON for app's use.
            deck_code_to_copy = "\n".join(output_lines) + f"\n{card_ids_json_str}"

            app_instance.root.clipboard_clear()
            app_instance.root.clipboard_append(deck_code_to_copy)
            messagebox.showinfo("Deck Code Copied", f"Deck code for '{deck_name}' copied to clipboard.")

        except json.JSONDecodeError:
            print(f"Error decoding card_ids_json for deck {deck_db_id}: {traceback.format_exc()}")
            messagebox.showerror("Error", "Could not parse the deck's card list.")

    except sqlite3.Error as e:
        print(f"Database error copying deck code: {e}: {traceback.format_exc()}")
        messagebox.showerror("Database Error", f"Could not copy deck code: {e}")
    finally:
        if conn:
            conn.close()
