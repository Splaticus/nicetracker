import sqlite3
import json
from collections import defaultdict, Counter
import numpy as np
import tkinter as tk # For toggle_card_stats_view
import ui_tabs # For _create_deck_filter_dialog

# Assuming DB_NAME is in db_utils
from db_utils import DB_NAME

# card_db and other app_instance attributes will be accessed via app_instance

def load_card_stats_data(app_instance, event=None):
    """Load and display card statistics with extended metrics."""
    if not hasattr(app_instance, 'card_stats_tree') or not app_instance.card_stats_tree:
        print("LOG_ERROR: card_stats_tree not initialized on app_instance.")
        return

    for item in app_instance.card_stats_tree.get_children():
        app_instance.card_stats_tree.delete(item)

    selected_season = app_instance.card_stats_season_filter_var.get()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

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

    if app_instance.card_stats_selected_deck_names:
        placeholders = ', '.join(['?'] * len(app_instance.card_stats_selected_deck_names))
        match_deck_query_parts.append(f"AND d.deck_name IN ({placeholders})")
        match_deck_params.extend(list(app_instance.card_stats_selected_deck_names))

    if selected_season != "All Seasons":
        match_deck_query_parts.append("AND m.season = ?")
        match_deck_params.append(selected_season)

    cursor.execute(" ".join(match_deck_query_parts), tuple(match_deck_params))
    all_match_deck_data = cursor.fetchall()

    if not all_match_deck_data:
        filter_msg_display = app_instance.card_stats_deck_filter_display_var.get()
        app_instance.card_stats_summary_var.set(f"No match data for {filter_msg_display} / {selected_season}")
        conn.close()
        app_instance.current_card_performance_data = {}
        if app_instance.card_stats_view_var.get() == "Chart":
            update_card_stats_chart(app_instance, app_instance.current_card_performance_data)
        return

    game_ids_for_events = [md[0] for md in all_match_deck_data]
    if not game_ids_for_events:
        app_instance.card_stats_summary_var.set(f"No games to process for events for {app_instance.card_stats_deck_filter_display_var.get()} / {selected_season}")
        conn.close()
        app_instance.current_card_performance_data = {}
        if app_instance.card_stats_view_var.get() == "Chart":
            update_card_stats_chart(app_instance, app_instance.current_card_performance_data)
        return

    event_query_parts = [f"""
        SELECT game_id, card_def_id, event_type
        FROM match_events
        WHERE player_type = 'local'
          AND (event_type = 'drawn' OR event_type = 'played')
          AND game_id IN ({','.join(['?'] * len(game_ids_for_events))})
    """]
    cursor.execute(" ".join(event_query_parts), tuple(game_ids_for_events))
    all_event_data = cursor.fetchall()
    conn.close()

    game_events = defaultdict(lambda: {"drawn": set(), "played": set()})
    for game_id, card_def_id, event_type in all_event_data:
        if event_type == 'drawn': game_events[game_id]["drawn"].add(card_def_id)
        elif event_type == 'played':
            game_events[game_id]["played"].add(card_def_id)
            game_events[game_id]["drawn"].add(card_def_id)

    card_performance = defaultdict(lambda: {
        "total_games_in_deck": 0, "drawn_games": 0, "drawn_wins": 0, "drawn_cubes": 0,
        "played_games": 0, "played_wins": 0, "played_cubes": 0,
        "not_drawn_games": 0, "not_drawn_wins": 0, "not_drawn_cubes": 0,
        "not_played_games": 0, "not_played_wins": 0, "not_played_cubes": 0,
    })

    for game_id, result, cubes, deck_cards_json_str in all_match_deck_data:
        cubes_val = cubes if cubes is not None else 0
        is_win = (result == 'win')
        try:
            deck_cards_for_this_game = set(json.loads(deck_cards_json_str))
        except (json.JSONDecodeError, TypeError):
            print(f"WARN: Could not parse deck_cards_json for game {game_id}: {deck_cards_json_str}")
            continue
        game_specific_drawn_cards = game_events[game_id]["drawn"]
        game_specific_played_cards = game_events[game_id]["played"]
        for card_id in deck_cards_for_this_game:
            stats = card_performance[card_id]
            stats["total_games_in_deck"] += 1
            was_drawn = card_id in game_specific_drawn_cards
            was_played = card_id in game_specific_played_cards
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

    app_instance.current_card_performance_data = card_performance

    if not card_performance:
        app_instance.card_stats_summary_var.set(f"No card performance data for {app_instance.card_stats_deck_filter_display_var.get()} / {selected_season}")
        if app_instance.card_stats_view_var.get() == "Chart":
             update_card_stats_chart(app_instance, app_instance.current_card_performance_data)
        return

    for card_def, stats in card_performance.items():
        card_name = card_def
        if app_instance.card_db and app_instance.display_card_names_var.get() and card_def in app_instance.card_db:
            card_name = app_instance.card_db[card_def].get('name', card_def)
        drawn_win_pct = (stats["drawn_wins"] / stats["drawn_games"] * 100) if stats["drawn_games"] > 0 else 0.0
        avg_cubes_drawn = (stats["drawn_cubes"] / stats["drawn_games"]) if stats["drawn_games"] > 0 else 0.0
        played_win_pct = (stats["played_wins"] / stats["played_games"] * 100) if stats["played_games"] > 0 else 0.0
        avg_cubes_played = (stats["played_cubes"] / stats["played_games"]) if stats["played_games"] > 0 else 0.0
        not_drawn_win_pct = (stats["not_drawn_wins"] / stats["not_drawn_games"] * 100) if stats["not_drawn_games"] > 0 else 0.0
        avg_cubes_not_drawn = (stats["not_drawn_cubes"] / stats["not_drawn_games"]) if stats["not_drawn_games"] > 0 else 0.0
        not_played_win_pct = (stats["not_played_wins"] / stats["not_played_games"] * 100) if stats["not_played_games"] > 0 else 0.0
        avg_cubes_not_played = (stats["not_played_cubes"] / stats["not_played_games"]) if stats["not_played_games"] > 0 else 0.0
        delta_cubes_played_vs_not = (avg_cubes_played - avg_cubes_not_played) if stats["played_games"] > 0 and stats["not_played_games"] > 0 else (avg_cubes_played if stats["played_games"] > 0 else (-avg_cubes_not_played if stats["not_played_games"] > 0 else 0.0))
        delta_cubes_drawn_vs_not = (avg_cubes_drawn - avg_cubes_not_drawn) if stats["drawn_games"] > 0 and stats["not_drawn_games"] > 0 else (avg_cubes_drawn if stats["drawn_games"] > 0 else (-avg_cubes_not_drawn if stats["not_drawn_games"] > 0 else 0.0))
        app_instance.card_stats_tree.insert("", "end", values=(card_name, stats["drawn_games"], f"{drawn_win_pct:.1f}%", stats["drawn_cubes"], f"{avg_cubes_drawn:.2f}", stats["played_games"], f"{played_win_pct:.1f}%", stats["played_cubes"], f"{avg_cubes_played:.2f}", stats["not_drawn_games"], f"{not_drawn_win_pct:.1f}%", stats["not_drawn_cubes"], f"{avg_cubes_not_drawn:.2f}", stats["not_played_games"], f"{not_played_win_pct:.1f}%", stats["not_played_cubes"], f"{avg_cubes_not_played:.2f}", f"{delta_cubes_drawn_vs_not:.2f}", f"{delta_cubes_played_vs_not:.2f}"), tags=(card_def,))
    filter_msg = app_instance.card_stats_deck_filter_display_var.get();
    if selected_season != "All Seasons": filter_msg += f", Season: {selected_season}"
    app_instance.card_stats_summary_var.set(f"Card Stats ({filter_msg}). Unique cards processed: {len(card_performance)}")
    if app_instance.card_stats_view_var.get() == "Chart":
        update_card_stats_chart(app_instance, card_performance)

def update_card_stats_chart(app_instance, card_performance):
    app_instance.card_stats_figure.clear()
    ax1 = app_instance.card_stats_figure.add_subplot(211); ax2 = app_instance.card_stats_figure.add_subplot(212)
    cards, drawn_win_rates, played_win_rates, net_cubes_list, avg_cubes_list = [], [], [], [], []
    card_data_for_sorting = []
    for card_id, stats_dict in card_performance.items():
        num_played_games = stats_dict.get("played_games", 0); played_wins = stats_dict.get("played_wins", 0)
        sort_key_value = num_played_games * (played_wins / num_played_games) if num_played_games > 0 else 0
        card_data_for_sorting.append((card_id, stats_dict, sort_key_value))
    sorted_cards_data_tuples = sorted(card_data_for_sorting, key=lambda x: x[2], reverse=True)[:10]
    for card_id, stats, _ in sorted_cards_data_tuples:
        card_name = card_id
        if app_instance.card_db and app_instance.display_card_names_var.get() and card_id in app_instance.card_db:
            card_name = app_instance.card_db[card_id].get('name', card_id)
        cards.append(card_name)
        num_drawn_games = stats.get("drawn_games", 0); drawn_wins = stats.get("drawn_wins", 0)
        num_played_games = stats.get("played_games", 0); played_wins = stats.get("played_wins", 0)
        played_cubes = stats.get("played_cubes", 0)
        drawn_win_rates.append((drawn_wins / num_drawn_games * 100) if num_drawn_games > 0 else 0)
        played_win_rates.append((played_wins / num_played_games * 100) if num_played_games > 0 else 0)
        net_cubes_list.append(played_cubes)
        avg_cubes_list.append(played_cubes / num_played_games if num_played_games > 0 else 0)
    cards.reverse(); drawn_win_rates.reverse(); played_win_rates.reverse(); net_cubes_list.reverse(); avg_cubes_list.reverse()
    win_color, loss_color, neutral_color, bg_color, fg_color = app_instance.config['Colors']['win'], app_instance.config['Colors']['loss'], app_instance.config['Colors']['neutral'], app_instance.config['Colors']['bg_main'], app_instance.config['Colors']['fg_main']
    y_pos = range(len(cards))
    ax1.barh(y_pos, played_win_rates, height=0.4, align='center', color=win_color, alpha=0.8, label='Played Win %')
    ax1.barh([y + 0.4 for y in y_pos], drawn_win_rates, height=0.4, align='center', color=neutral_color, alpha=0.8, label='Drawn Win %')
    ax1.axvline(x=50, color=fg_color, linestyle='--', alpha=0.5); ax1.set_yticks(y_pos); ax1.set_yticklabels(cards); ax1.set_xlabel('Win %'); ax1.set_title('Card Win Rates'); ax1.legend(); ax1.set_xlim(0, 100)
    ax2.barh(y_pos, avg_cubes_list, height=0.8, align='center', color=[win_color if avg > 0 else loss_color for avg in avg_cubes_list], alpha=0.8)
    ax2.axvline(x=0, color=fg_color, linestyle='--', alpha=0.5); ax2.set_yticks(y_pos); ax2.set_yticklabels(cards); ax2.set_xlabel('Avg. Cubes per Game (when played)'); ax2.set_title('Card Cube Value (when played)')
    for ax_item in [ax1, ax2]:
        ax_item.set_facecolor(bg_color); ax_item.tick_params(colors=fg_color); ax_item.xaxis.label.set_color(fg_color); ax_item.yaxis.label.set_color(fg_color); ax_item.title.set_color(fg_color)
        for spine in ax_item.spines.values(): spine.set_color(fg_color)
    app_instance.card_stats_figure.patch.set_facecolor(bg_color); app_instance.card_stats_figure.tight_layout(); app_instance.card_stats_canvas.draw()

def toggle_card_stats_view(app_instance):
    """Toggle between table and chart view for card stats"""
    view_mode = app_instance.card_stats_view_var.get()
    if view_mode == "Table":
        app_instance.card_stats_chart_frame.pack_forget()
        app_instance.card_stats_table_frame.pack(fill=tk.BOTH, expand=True)
    else:
        app_instance.card_stats_table_frame.pack_forget()
        app_instance.card_stats_chart_frame.pack(fill=tk.BOTH, expand=True)
        if hasattr(app_instance, 'current_card_performance_data') and app_instance.current_card_performance_data:
            update_card_stats_chart(app_instance, app_instance.current_card_performance_data)
        else:
            print("WARN: current_card_performance_data not found in toggle_card_stats_view, re-loading for chart.")
            load_card_stats_data(app_instance)

def on_card_stats_select(app_instance, event):
    """Handle selection of a card in the card stats view"""
    selected_item = app_instance.card_stats_tree.focus()
    if not selected_item: return
    values = app_instance.card_stats_tree.item(selected_item, "values")
    card_name = values[0]
    card_id = card_name
    if app_instance.card_db:
        for cid, card_info in app_instance.card_db.items():
            if card_info.get('name') == card_name or cid == card_name: # Check against name or ID
                card_id = cid; break
    if card_id: app_instance.card_tooltip.show_tooltip(card_id, None)

def sort_card_stats_treeview(app_instance, col, reverse):
    """Sort card stats treeview by column"""
    data = [(app_instance.card_stats_tree.set(child, col), child) for child in app_instance.card_stats_tree.get_children('')]
    def try_convert(val_str):
        val_str = str(val_str).replace('%', '').replace('N/A', '-9999')
        try: return int(val_str)
        except (ValueError, TypeError):
            try: return float(val_str)
            except (ValueError, TypeError): return val_str.lower()
    data.sort(key=lambda t: try_convert(t[0]), reverse=reverse)
    for index, (val, child) in enumerate(data):
        app_instance.card_stats_tree.move(child, '', index)
    app_instance.card_stats_tree.heading(col, command=lambda _col=col: sort_card_stats_treeview(app_instance, _col, not reverse))

def show_card_stats_deck_filter_dialog(app_instance):
    # Note: _create_deck_filter_dialog is now in ui_tabs module
    ui_tabs._create_deck_filter_dialog(app_instance,
        title="Select Decks for Card Stats",
        all_deck_names_list=app_instance.all_deck_names_for_filter,
        selected_deck_names_set=app_instance.card_stats_selected_deck_names,
        display_var_stringvar=app_instance.card_stats_deck_filter_display_var,
        apply_callback_func=lambda: load_card_stats_data(app_instance) # Corrected to call load_card_stats_data from this module
    )
