import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import json
import re

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
# import matplotlib.pyplot as plt # Not directly used in ui_tabs, but FigureCanvasTkAgg needs it.
# from matplotlib.dates import DateFormatter # Not directly used in ui_tabs

# Imports for refactored tab logic
import history_tab_logic
import card_stats_tab_logic
import matchup_tab_logic
# Future logic modules:
# import location_stats_tab_logic
# import trends_tab_logic
# import deck_performance_tab_logic

# DEFAULT_COLORS might be needed if app_instance.config is not fully available initially in _create_deck_filter_dialog
# from config_utils import DEFAULT_COLORS # Better to rely on app_instance.config


def _create_deck_filter_dialog(app_instance, title, all_deck_names_list,
                                   selected_deck_names_set, display_var_stringvar,
                                   apply_callback_func):
    dialog = tk.Toplevel(app_instance.root)
    dialog.title(title)
    dialog.geometry("400x550")
    dialog.transient(app_instance.root)
    dialog.grab_set()

    bg_main_color = "#1e1e2e" # Default fallback
    if hasattr(app_instance, 'config') and 'Colors' in app_instance.config and 'bg_main' in app_instance.config['Colors']:
        bg_main_color = app_instance.config['Colors']['bg_main']
    dialog.configure(background=bg_main_color)

    _dialog_data = {'temp_vars': {}, 'all_decks_var': None, '_block_individual_traces': False}

    def apply_selection_command():
        all_decks_var_local = _dialog_data['all_decks_var']
        temp_vars_local = _dialog_data['temp_vars']
        selected_deck_names_set.clear()
        if all_decks_var_local.get():
            display_var_stringvar.set("Decks: All")
        else:
            for deck_name, var_tk in temp_vars_local.items(): # Renamed var to var_tk
                if deck_name != "ALL" and var_tk.get(): # Use var_tk
                    selected_deck_names_set.add(deck_name)
            if not selected_deck_names_set:
                display_var_stringvar.set("Decks: All")
            elif len(selected_deck_names_set) <= 3:
                display_var_stringvar.set(f"Decks: {', '.join(sorted(list(selected_deck_names_set)))}")
            else:
                display_var_stringvar.set(f"Decks: {len(selected_deck_names_set)} selected")
        dialog.destroy()
        if apply_callback_func: apply_callback_func()

    def on_individual_deck_toggle(*args):
        if _dialog_data['_block_individual_traces']: return
        all_decks_var_local = _dialog_data['all_decks_var']
        temp_vars_local = _dialog_data['temp_vars']
        if all_decks_var_local is None: return
        any_individual_selected = any(var_tk.get() for name, var_tk in temp_vars_local.items() if name != "ALL") # Renamed var
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
                    if temp_vars_local[deck_name_key].get(): temp_vars_local[deck_name_key].set(False)
            _dialog_data['_block_individual_traces'] = False
        on_individual_deck_toggle()

    button_frame = ttk.Frame(dialog)
    ttk.Button(button_frame, text="Apply", command=apply_selection_command).pack(side=tk.RIGHT, padx=5)
    ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
    checkbox_area_frame = ttk.Frame(dialog)
    canvas_bg_color = bg_main_color
    scroll_canvas = tk.Canvas(checkbox_area_frame, background=canvas_bg_color)
    scrollbar = ttk.Scrollbar(checkbox_area_frame, orient="vertical", command=scroll_canvas.yview)
    checkbox_display_frame = ttk.Frame(scroll_canvas)
    checkbox_display_frame.bind("<Configure>", lambda e: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")))
    scroll_canvas.create_window((0, 0), window=checkbox_display_frame, anchor="nw")
    scroll_canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    _dialog_data['temp_vars'] = {}
    initial_all_decks_state = not bool(selected_deck_names_set)
    all_decks_var_instance = tk.BooleanVar(value=initial_all_decks_state)
    _dialog_data['all_decks_var'] = all_decks_var_instance
    all_cb = ttk.Checkbutton(checkbox_display_frame, text="All Decks", variable=all_decks_var_instance, command=on_all_decks_toggle_command)
    all_cb.pack(anchor="w", padx=10, pady=2)
    _dialog_data['temp_vars']["ALL"] = all_decks_var_instance
    ttk.Separator(checkbox_display_frame, orient='horizontal').pack(fill='x', pady=5)
    for deck_name_iter in all_deck_names_list:
        is_initially_checked = (deck_name_iter in selected_deck_names_set) and not initial_all_decks_state
        var_tk = tk.BooleanVar(value=is_initially_checked) # Renamed var
        cb = ttk.Checkbutton(checkbox_display_frame, text=deck_name_iter, variable=var_tk) # Use var_tk
        cb.pack(anchor="w", padx=10, pady=2)
        var_tk.trace_add("write", on_individual_deck_toggle) # Use var_tk
        _dialog_data['temp_vars'][deck_name_iter] = var_tk # Use var_tk
    button_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=10, padx=10)
    checkbox_area_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    on_individual_deck_toggle()

def _setup_live_game_ui(app_instance, parent_frame):
    top_content_frame = ttk.Frame(parent_frame)
    top_content_frame.pack(expand=True, fill=tk.BOTH, side=tk.TOP)
    status_bar = ttk.Label(parent_frame, textvariable=app_instance.status_var, relief=tk.SUNKEN, anchor=tk.W)
    status_bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(5,0))
    error_log_frame = ttk.LabelFrame(parent_frame, text="Error Log", padding="5")
    error_log_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(5,0), ipady=2)
    app_instance.error_log_text = scrolledtext.ScrolledText(error_log_frame, height=4, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
    app_instance.error_log_text.pack(expand=True, fill=tk.X)
    game_details_frame = ttk.LabelFrame(top_content_frame, text="Game Info", padding="5")
    game_details_frame.pack(pady=5, padx=5, fill=tk.X)
    ttk.Label(game_details_frame, textvariable=app_instance.turn_var).pack(side=tk.LEFT, padx=5)
    ttk.Label(game_details_frame, textvariable=app_instance.cubes_var).pack(side=tk.LEFT, padx=5)
    app_instance.deck_stats_button = ttk.Button(game_details_frame, text="Deck Stats", command=app_instance.show_deck_modal)
    app_instance.deck_stats_button.pack(side=tk.RIGHT, padx=10)
    locations_outer_frame = ttk.LabelFrame(top_content_frame, text="Locations", padding="5")
    locations_outer_frame.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)
    locations_grid_frame = ttk.Frame(locations_outer_frame)
    locations_grid_frame.pack(fill=tk.BOTH, expand=True)
    for i in range(3):
        loc_frame = ttk.Frame(locations_grid_frame, borderwidth=1, relief="groove")
        loc_frame.grid(row=0, column=i, padx=5, pady=2, sticky="nsew")
        locations_grid_frame.grid_columnconfigure(i, weight=1)
        locations_grid_frame.grid_rowconfigure(0, weight=1)
        ttk.Label(loc_frame, textvariable=app_instance.location_vars[i]["name"], font=('Arial', 10, 'bold')).pack(pady=(2,2), anchor='n')
        ttk.Label(loc_frame, textvariable=app_instance.location_vars[i]["power"]).pack(pady=(0,5), anchor='n')
        opp_cards_sub_frame = ttk.Frame(loc_frame); opp_cards_sub_frame.pack(fill=tk.BOTH, expand=True, pady=(0,2), ipady=2)
        ttk.Label(opp_cards_sub_frame, text="Opp Cards:", anchor="w", font=('Arial', 8, 'italic')).pack(fill=tk.X)
        opp_label = ttk.Label(opp_cards_sub_frame, textvariable=app_instance.location_vars[i]["opp_cards"], wraplength=180, justify=tk.LEFT, anchor="nw", relief="sunken", borderwidth=1, padding=(2,5))
        opp_label.pack(fill=tk.BOTH, expand=True)
        opp_label.bind("<Enter>", lambda e, idx=i, player="opp": app_instance.on_card_list_hover(e, idx, player))
        opp_label.bind("<Leave>", lambda e: app_instance.card_tooltip.hide_tooltip())
        your_cards_sub_frame = ttk.Frame(loc_frame); your_cards_sub_frame.pack(fill=tk.BOTH, expand=True, pady=(2,0), ipady=2)
        ttk.Label(your_cards_sub_frame, text="Your Cards:", anchor="w", font=('Arial', 8, 'italic')).pack(fill=tk.X)
        local_label = ttk.Label(your_cards_sub_frame, textvariable=app_instance.location_vars[i]["local_cards"], wraplength=180, justify=tk.LEFT, anchor="nw", relief="sunken", borderwidth=1, padding=(2,5))
        local_label.pack(fill=tk.BOTH, expand=True)
        local_label.bind("<Enter>", lambda e, idx=i, player="local": app_instance.on_card_list_hover(e, idx, player))
        local_label.bind("<Leave>", lambda e: app_instance.card_tooltip.hide_tooltip())
    paned_window = ttk.PanedWindow(top_content_frame, orient=tk.HORIZONTAL); paned_window.pack(expand=True, fill=tk.BOTH, pady=5)
    local_player_frame = ttk.LabelFrame(paned_window, text="Local Player", padding="10"); paned_window.add(local_player_frame, weight=1)
    ttk.Label(local_player_frame, textvariable=app_instance.local_player_name_var, font=('Arial', 12, 'bold')).grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
    ttk.Label(local_player_frame, textvariable=app_instance.local_energy_var).grid(row=1, column=0, sticky="w", pady=1)
    ttk.Label(local_player_frame, textvariable=app_instance.local_snap_status_var).grid(row=1, column=1, sticky="w", pady=1, padx=(5,0))
    ttk.Label(local_player_frame, text="Hand:").grid(row=2, column=0, sticky="nw", pady=2)
    hand_label = ttk.Label(local_player_frame, textvariable=app_instance.local_hand_var, wraplength=280, justify=tk.LEFT); hand_label.grid(row=2, column=1, sticky="new", pady=2)
    hand_label.bind("<Enter>", lambda e, zone="hand": app_instance.on_zone_hover(e, zone)); hand_label.bind("<Leave>", lambda e: app_instance.card_tooltip.hide_tooltip())
    ttk.Label(local_player_frame, text="Deck:").grid(row=3, column=0, sticky="nw", pady=2)
    ttk.Label(local_player_frame, textvariable=app_instance.local_deck_var).grid(row=3, column=1, sticky="new", pady=2)
    ttk.Label(local_player_frame, text="Remaining:").grid(row=4, column=0, sticky="nw", pady=2)
    remaining_label = ttk.Label(local_player_frame, textvariable=app_instance.local_remaining_deck_var, wraplength=280, justify=tk.LEFT); remaining_label.grid(row=4, column=1, sticky="new", pady=2)
    remaining_label.bind("<Enter>", lambda e, zone="remaining": app_instance.on_zone_hover(e, zone)); remaining_label.bind("<Leave>", lambda e: app_instance.card_tooltip.hide_tooltip())
    ttk.Label(local_player_frame, text="Destroyed:").grid(row=5, column=0, sticky="nw", pady=2)
    graveyard_label = ttk.Label(local_player_frame, textvariable=app_instance.local_graveyard_var, wraplength=280, justify=tk.LEFT); graveyard_label.grid(row=5, column=1, sticky="new", pady=2)
    graveyard_label.bind("<Enter>", lambda e, zone="graveyard": app_instance.on_zone_hover(e, zone)); graveyard_label.bind("<Leave>", lambda e: app_instance.card_tooltip.hide_tooltip())
    ttk.Label(local_player_frame, text="Banished:").grid(row=6, column=0, sticky="nw", pady=2)
    banished_label = ttk.Label(local_player_frame, textvariable=app_instance.local_banished_var, wraplength=280, justify=tk.LEFT); banished_label.grid(row=6, column=1, sticky="new", pady=2)
    banished_label.bind("<Enter>", lambda e, zone="banished": app_instance.on_zone_hover(e, zone)); banished_label.bind("<Leave>", lambda e: app_instance.card_tooltip.hide_tooltip())
    local_player_frame.grid_columnconfigure(1, weight=1)
    opponent_frame = ttk.LabelFrame(paned_window, text="Opponent", padding="10"); paned_window.add(opponent_frame, weight=1)
    ttk.Label(opponent_frame, textvariable=app_instance.opponent_name_var, font=('Arial', 12, 'bold')).grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
    ttk.Label(opponent_frame, textvariable=app_instance.opponent_energy_var).grid(row=1, column=0, sticky="w", pady=1)
    ttk.Label(opponent_frame, textvariable=app_instance.opponent_snap_status_var).grid(row=1, column=1, sticky="w", pady=1, padx=(5,0))
    ttk.Label(opponent_frame, text="Hand:").grid(row=2, column=0, sticky="nw", pady=2)
    ttk.Label(opponent_frame, textvariable=app_instance.opponent_hand_var).grid(row=2, column=1, sticky="new", pady=2)
    ttk.Label(opponent_frame, text="Destroyed:").grid(row=3, column=0, sticky="nw", pady=2)
    opp_graveyard_label = ttk.Label(opponent_frame, textvariable=app_instance.opponent_graveyard_var, wraplength=280, justify=tk.LEFT); opp_graveyard_label.grid(row=3, column=1, sticky="new", pady=2)
    opp_graveyard_label.bind("<Enter>", lambda e, zone="opp_graveyard": app_instance.on_zone_hover(e, zone)); opp_graveyard_label.bind("<Leave>", lambda e: app_instance.card_tooltip.hide_tooltip())
    ttk.Label(opponent_frame, text="Banished:").grid(row=4, column=0, sticky="nw", pady=2)
    opp_banished_label = ttk.Label(opponent_frame, textvariable=app_instance.opponent_banished_var, wraplength=280, justify=tk.LEFT); opp_banished_label.grid(row=4, column=1, sticky="new", pady=2)
    opp_banished_label.bind("<Enter>", lambda e, zone="opp_banished": app_instance.on_zone_hover(e, zone)); opp_banished_label.bind("<Leave>", lambda e: app_instance.card_tooltip.hide_tooltip())
    opponent_frame.grid_columnconfigure(1, weight=1)
    last_encounter_frame = ttk.LabelFrame(opponent_frame, text="Encounter History", padding="5"); last_encounter_frame.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(10,0), padx=2)
    opponent_frame.grid_rowconfigure(5, weight=1); last_encounter_frame.grid_columnconfigure(1, weight=1)
    name_frame = ttk.Frame(last_encounter_frame); name_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=2)
    ttk.Label(name_frame, text="Opponent:").pack(side=tk.LEFT)
    ttk.Label(name_frame, textvariable=app_instance.last_encounter_opponent_name_var).pack(side=tk.LEFT, padx=(5,0))
    app_instance.opponent_encounter_history_text = scrolledtext.ScrolledText(last_encounter_frame, height=5, wrap=tk.WORD, state=tk.DISABLED, relief="sunken", borderwidth=1, font=("Arial", 8))
    app_instance.opponent_encounter_history_text.grid(row=1, column=0, columnspan=2, sticky="new", pady=(5,1), padx=2)
    last_encounter_frame.grid_rowconfigure(1, weight=1)

def _setup_history_ui(app_instance, parent_frame):
    filter_frame = ttk.Frame(parent_frame)
    filter_frame.pack(fill=tk.X, pady=5)
    app_instance.deck_filter_button = ttk.Button(filter_frame, text="Filter Decks...", command=app_instance.show_history_deck_filter_dialog)
    app_instance.deck_filter_button.pack(side=tk.LEFT, padx=(0, 5))
    ttk.Label(filter_frame, textvariable=app_instance.history_deck_filter_display_var).pack(side=tk.LEFT, padx=5)
    ttk.Label(filter_frame, text="Season:").pack(side=tk.LEFT, padx=(20,5))
    # app_instance.season_filter_var is initialized in setup_string_vars
    app_instance.season_filter_menu = ttk.OptionMenu(filter_frame, app_instance.season_filter_var, "All Seasons", "All Seasons", command=lambda event=None: history_tab_logic.apply_history_filter(app_instance, event))
    app_instance.season_filter_menu.pack(side=tk.LEFT, padx=5)
    ttk.Label(filter_frame, text="Result:").pack(side=tk.LEFT, padx=(20,5))
    # app_instance.result_filter_var is initialized in setup_string_vars
    app_instance.result_filter_menu = ttk.OptionMenu(filter_frame, app_instance.result_filter_var, "All Results", "All Results", "Win", "Loss", "Tie", command=lambda event=None: history_tab_logic.apply_history_filter(app_instance, event))
    app_instance.result_filter_menu.pack(side=tk.LEFT, padx=5)
    button_frame = ttk.Frame(parent_frame); button_frame.pack(fill=tk.X, pady=5)
    ttk.Button(button_frame, text="Refresh History", command=lambda: history_tab_logic.load_history_tab_data(app_instance)).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="Export Selected", command=app_instance.export_selected_matches).pack(side=tk.LEFT, padx=5) # Calls SnapTrackerApp method
    ttk.Button(button_frame, text="Add Note", command=lambda: history_tab_logic.add_match_note_external(app_instance)).pack(side=tk.LEFT, padx=5) # Assuming add_match_note was moved
    ttk.Button(button_frame, text="Delete Selected", command=app_instance.delete_selected_matches).pack(side=tk.LEFT, padx=5) # Calls SnapTrackerApp method
    search_frame = ttk.Frame(button_frame); search_frame.pack(side=tk.RIGHT)
    ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0,5))
    # app_instance.search_var is initialized in setup_string_vars
    app_instance.search_var.trace("w", lambda *args: history_tab_logic.apply_history_filter(app_instance))
    ttk.Entry(search_frame, textvariable=app_instance.search_var, width=20).pack(side=tk.LEFT)
    history_list_frame = ttk.LabelFrame(parent_frame, text="Matches", padding="5"); history_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
    cols = ("Timestamp", "Deck", "Opponent", "Result", "Cubes", "Turns", "Location1", "Location2", "Location3")
    app_instance.history_tree = ttk.Treeview(history_list_frame, columns=cols, show="headings", selectmode="extended")
    for col in cols:
        app_instance.history_tree.heading(col, text=col, command=lambda _col=col: history_tab_logic.sort_history_treeview(app_instance, _col, False))
        app_instance.history_tree.column(col, width=100, anchor='w')
    app_instance.history_tree.column("Timestamp", width=140); app_instance.history_tree.column("Deck", width=150); app_instance.history_tree.column("Result", width=60, anchor='center'); app_instance.history_tree.column("Cubes", width=50, anchor='center'); app_instance.history_tree.column("Turns", width=50, anchor='center'); app_instance.history_tree.column("Location1", width=100); app_instance.history_tree.column("Location2", width=100); app_instance.history_tree.column("Location3", width=100)
    vsb = ttk.Scrollbar(history_list_frame, orient="vertical", command=app_instance.history_tree.yview); hsb = ttk.Scrollbar(history_list_frame, orient="horizontal", command=app_instance.history_tree.xview)
    app_instance.history_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set); vsb.pack(side='right', fill='y'); hsb.pack(side='bottom', fill='x'); app_instance.history_tree.pack(fill=tk.BOTH, expand=True)
    app_instance.history_tree.bind("<<TreeviewSelect>>", lambda event: history_tab_logic.on_history_match_select(app_instance, event))
    app_instance.history_tree.bind("<Double-1>", lambda event: history_tab_logic.on_history_match_double_click(app_instance, event))
    stats_frame = ttk.LabelFrame(parent_frame, text="Stats & Details", padding="5"); stats_frame.pack(fill=tk.X, pady=5, ipady=5)
    # app_instance.stats_summary_var is initialized in setup_string_vars
    ttk.Label(stats_frame, textvariable=app_instance.stats_summary_var, font=("Arial", 10, "bold")).pack(fill=tk.X, pady=(0, 5))
    app_instance.stats_text_widget = scrolledtext.ScrolledText(stats_frame, height=8, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
    app_instance.stats_text_widget.pack(fill=tk.X, expand=True)

def _setup_deck_performance_ui(app_instance, parent_frame):
    filter_frame = ttk.Frame(parent_frame); filter_frame.pack(fill=tk.X, pady=5)
    ttk.Label(filter_frame, text="Season:").pack(side=tk.LEFT, padx=(0, 5))
    # app_instance.deck_performance_season_filter_var from setup_string_vars
    app_instance.deck_perf_season_filter_menu = ttk.OptionMenu(filter_frame, app_instance.deck_performance_season_filter_var, "All Seasons", "All Seasons", command=app_instance.load_deck_performance_data)
    app_instance.deck_perf_season_filter_menu.pack(side=tk.LEFT, padx=5)
    ttk.Button(filter_frame, text="Refresh Stats", command=app_instance.load_deck_performance_data).pack(side=tk.LEFT, padx=5)
    deck_perf_list_frame = ttk.LabelFrame(parent_frame, text="Deck Statistics", padding="5"); deck_perf_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
    cols = ("Deck Name", "Games", "Wins", "Losses", "Ties", "Win %", "Net Cubes", "Avg Cubes/Game", "Avg Cubes/Win", "Avg Cubes/Loss", "Tags")
    app_instance.deck_performance_tree = ttk.Treeview(deck_perf_list_frame, columns=cols, show="headings", selectmode="browse")
    col_widths = {"Deck Name": 200, "Games": 60, "Wins": 50, "Losses": 50, "Ties": 50, "Win %": 70, "Net Cubes": 70, "Avg Cubes/Game": 100, "Avg Cubes/Win": 100, "Avg Cubes/Loss": 100, "Tags": 100}
    for col in cols:
        app_instance.deck_performance_tree.heading(col, text=col, command=lambda _col=col: app_instance.sort_deck_performance_treeview(_col, False))
        anchor_val = 'w' if col == "Deck Name" or col == "Tags" else 'center'; app_instance.deck_performance_tree.column(col, width=col_widths.get(col, 80), anchor=anchor_val, stretch=(col == "Deck Name"))
    vsb = ttk.Scrollbar(deck_perf_list_frame, orient="vertical", command=app_instance.deck_performance_tree.yview); hsb = ttk.Scrollbar(deck_perf_list_frame, orient="horizontal", command=app_instance.deck_performance_tree.xview)
    app_instance.deck_performance_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set); vsb.pack(side='right', fill='y'); hsb.pack(side='bottom', fill='x'); app_instance.deck_performance_tree.pack(fill=tk.BOTH, expand=True)

def _setup_card_stats_ui(app_instance, parent_frame):
    filter_frame = ttk.Frame(parent_frame); filter_frame.pack(fill=tk.X, pady=5)
    ttk.Button(filter_frame, text="Filter Decks...", command=lambda: card_stats_tab_logic.show_card_stats_deck_filter_dialog(app_instance)).pack(side=tk.LEFT, padx=(0,5))
    ttk.Label(filter_frame, textvariable=app_instance.card_stats_deck_filter_display_var).pack(side=tk.LEFT, padx=5)
    ttk.Label(filter_frame, text="Season:").pack(side=tk.LEFT, padx=(20,5))
    # app_instance.card_stats_season_filter_var from setup_string_vars
    app_instance.card_stats_season_filter_menu = ttk.OptionMenu(filter_frame, app_instance.card_stats_season_filter_var, "All Seasons", "All Seasons", command=lambda event=None: card_stats_tab_logic.load_card_stats_data(app_instance, event))
    app_instance.card_stats_season_filter_menu.pack(side=tk.LEFT, padx=5)
    ttk.Button(filter_frame, text="Refresh Stats", command=lambda: card_stats_tab_logic.load_card_stats_data(app_instance)).pack(side=tk.LEFT, padx=5)
    view_frame = ttk.Frame(parent_frame); view_frame.pack(fill=tk.X, pady=5)
    # app_instance.card_stats_view_var from setup_string_vars
    ttk.Radiobutton(view_frame, text="Table View", variable=app_instance.card_stats_view_var, value="Table", command=lambda: card_stats_tab_logic.toggle_card_stats_view(app_instance)).pack(side=tk.LEFT, padx=5)
    ttk.Radiobutton(view_frame, text="Chart View", variable=app_instance.card_stats_view_var, value="Chart", command=lambda: card_stats_tab_logic.toggle_card_stats_view(app_instance)).pack(side=tk.LEFT, padx=5)
    app_instance.card_stats_container = ttk.Frame(parent_frame); app_instance.card_stats_container.pack(fill=tk.BOTH, expand=True, pady=5)
    app_instance.card_stats_table_frame = ttk.LabelFrame(app_instance.card_stats_container, text="Card Performance", padding="5"); app_instance.card_stats_table_frame.pack(fill=tk.BOTH, expand=True)
    cols = ("Card", "Drawn G", "Drawn Win%", "Net C (D)", "Avg C (D)", "Played G", "Played Win%", "Net C (P)", "Avg C (P)", "Not Drawn G", "Not Drawn Win%", "Net C (ND)", "Avg C (ND)", "Not Played G", "Not Played Win%", "Net C (NP)", "Avg C (NP)", "ΔC (Drawn)", "ΔC (Played)")
    app_instance.card_stats_tree = ttk.Treeview(app_instance.card_stats_table_frame, columns=cols, show="headings", selectmode="browse")
    col_widths = {"Card": 150, "Drawn G": 60, "Drawn Win%": 70, "Net C (D)": 70, "Avg C (D)": 70, "Played G": 60, "Played Win%": 70, "Net C (P)": 70, "Avg C (P)": 70, "Not Drawn G": 70, "Not Drawn Win%": 70, "Net C (ND)": 70, "Avg C (ND)": 70, "Not Played G": 70, "Not Played Win%": 70, "Net C (NP)": 70, "Avg C (NP)": 70, "ΔC (Drawn)": 70, "ΔC (Played)": 70}
    for col in cols:
        app_instance.card_stats_tree.heading(col, text=col, command=lambda _col=col: card_stats_tab_logic.sort_card_stats_treeview(app_instance, _col, False))
        anchor_val = 'center' if col != "Card" else "w"; app_instance.card_stats_tree.column(col, width=col_widths.get(col, 80), anchor=anchor_val, stretch=tk.YES if col == "Card" else tk.NO)
    vsb = ttk.Scrollbar(app_instance.card_stats_table_frame, orient="vertical", command=app_instance.card_stats_tree.yview); hsb = ttk.Scrollbar(app_instance.card_stats_table_frame, orient="horizontal", command=app_instance.card_stats_tree.xview)
    app_instance.card_stats_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set); vsb.pack(side='right', fill='y'); hsb.pack(side='bottom', fill='x'); app_instance.card_stats_tree.pack(fill=tk.BOTH, expand=True)
    app_instance.card_stats_tree.bind("<<TreeviewSelect>>", lambda event: card_stats_tab_logic.on_card_stats_select(app_instance, event))
    app_instance.card_stats_chart_frame = ttk.LabelFrame(app_instance.card_stats_container, text="Card Performance Chart", padding="5") # Not packed initially
    app_instance.card_stats_figure = Figure(figsize=(8, 6), dpi=100)
    app_instance.card_stats_canvas = FigureCanvasTkAgg(app_instance.card_stats_figure, app_instance.card_stats_chart_frame); app_instance.card_stats_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    ttk.Label(parent_frame, textvariable=app_instance.card_stats_summary_var, relief=tk.SUNKEN, anchor=tk.W).pack(side=tk.BOTTOM, fill=tk.X, pady=(5,0)) # card_stats_summary_var from setup_string_vars

def _setup_matchup_ui(app_instance, parent_frame):
    filter_frame = ttk.Frame(parent_frame); filter_frame.pack(fill=tk.X, pady=5)
    ttk.Label(filter_frame, text="Filter by Deck:").pack(side=tk.LEFT, padx=(0,5))
    # app_instance.matchup_deck_filter_var from setup_string_vars
    deck_opts = ["All Decks"] + app_instance.all_deck_names_for_filter if hasattr(app_instance, 'all_deck_names_for_filter') else ["All Decks"]
    app_instance.matchup_deck_filter_menu = ttk.OptionMenu(filter_frame, app_instance.matchup_deck_filter_var, deck_opts[0] if deck_opts else "All Decks", *deck_opts, command=lambda event=None: matchup_tab_logic.load_matchup_data(app_instance, event))
    app_instance.matchup_deck_filter_menu.pack(side=tk.LEFT, padx=5)
    ttk.Label(filter_frame, text="Season:").pack(side=tk.LEFT, padx=(20,5))
    # app_instance.matchup_season_filter_var from setup_string_vars
    season_opts = ["All Seasons"] # TODO: Populate from app_instance.seasons if available
    app_instance.matchup_season_filter_menu = ttk.OptionMenu(filter_frame, app_instance.matchup_season_filter_var, "All Seasons", *season_opts, command=lambda event=None: matchup_tab_logic.load_matchup_data(app_instance, event))
    app_instance.matchup_season_filter_menu.pack(side=tk.LEFT, padx=5)
    ttk.Button(filter_frame, text="Refresh Data", command=lambda: matchup_tab_logic.load_matchup_data(app_instance)).pack(side=tk.LEFT, padx=5)
    paned_window = ttk.PanedWindow(parent_frame, orient=tk.VERTICAL); paned_window.pack(fill=tk.BOTH, expand=True, pady=5)
    matchup_list_frame = ttk.LabelFrame(paned_window, text="Opponent Matchups", padding="5"); paned_window.add(matchup_list_frame, weight=3)
    cols = ("Opponent", "Matches", "Win %", "Wins", "Losses", "Ties", "Net Cubes", "Avg Cubes")
    app_instance.matchup_tree = ttk.Treeview(matchup_list_frame, columns=cols, show="headings", selectmode="browse")
    for col in cols:
        app_instance.matchup_tree.heading(col, text=col, command=lambda _col=col: matchup_tab_logic.sort_matchup_treeview(app_instance, _col, False))
        anchor_val = 'center' if col != "Opponent" else "w"; app_instance.matchup_tree.column(col, width=80, anchor=anchor_val, stretch=tk.YES if col == "Opponent" else tk.NO)
    app_instance.matchup_tree.column("Opponent", width=150, stretch=tk.YES); app_instance.matchup_tree.column("Matches", width=60); app_instance.matchup_tree.column("Win %", width=60)
    vsb = ttk.Scrollbar(matchup_list_frame, orient="vertical", command=app_instance.matchup_tree.yview); hsb = ttk.Scrollbar(matchup_list_frame, orient="horizontal", command=app_instance.matchup_tree.xview)
    app_instance.matchup_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set); vsb.pack(side='right', fill='y'); hsb.pack(side='bottom', fill='x'); app_instance.matchup_tree.pack(fill=tk.BOTH, expand=True)
    app_instance.matchup_tree.bind("<<TreeviewSelect>>", lambda event: matchup_tab_logic.on_matchup_select(app_instance, event))
    matchup_details_frame = ttk.LabelFrame(paned_window, text="Matchup Details", padding="5"); paned_window.add(matchup_details_frame, weight=2)
    details_notebook = ttk.Notebook(matchup_details_frame); details_notebook.pack(fill=tk.BOTH, expand=True)
    summary_tab = ttk.Frame(details_notebook); details_notebook.add(summary_tab, text="Summary")
    # app_instance.matchup_summary_var from setup_string_vars
    ttk.Label(summary_tab, textvariable=app_instance.matchup_summary_var, font=("Arial", 10, "bold")).pack(fill=tk.X, pady=5)
    revealed_cards_frame = ttk.LabelFrame(summary_tab, text="Most Common Revealed Cards", padding="5"); revealed_cards_frame.pack(fill=tk.BOTH, expand=True, pady=5)
    revealed_cols = ("Card", "Times Seen", "% of Matches")
    app_instance.revealed_cards_tree = ttk.Treeview(revealed_cards_frame, columns=revealed_cols, show="headings", selectmode="browse")
    for col in revealed_cols:
        app_instance.revealed_cards_tree.heading(col, text=col); anchor_val = 'center' if col != "Card" else "w"; app_instance.revealed_cards_tree.column(col, width=80, anchor=anchor_val, stretch=tk.YES if col == "Card" else tk.NO)
    app_instance.revealed_cards_tree.column("Card", width=150, stretch=tk.YES)
    r_vsb = ttk.Scrollbar(revealed_cards_frame, orient="vertical", command=app_instance.revealed_cards_tree.yview); r_hsb = ttk.Scrollbar(revealed_cards_frame, orient="horizontal", command=app_instance.revealed_cards_tree.xview)
    app_instance.revealed_cards_tree.configure(yscrollcommand=r_vsb.set, xscrollcommand=r_hsb.set); r_vsb.pack(side='right', fill='y'); r_hsb.pack(side='bottom', fill='x'); app_instance.revealed_cards_tree.pack(fill=tk.BOTH, expand=True)
    history_tab_matchup = ttk.Frame(details_notebook); details_notebook.add(history_tab_matchup, text="Match History")
    history_cols_matchup = ("Date", "Deck", "Result", "Cubes", "Revealed Cards")
    app_instance.matchup_history_tree = ttk.Treeview(history_tab_matchup, columns=history_cols_matchup, show="headings", selectmode="browse")
    for col in history_cols_matchup:
        app_instance.matchup_history_tree.heading(col, text=col); anchor_val = 'center' if col not in ("Deck", "Revealed Cards") else "w"; app_instance.matchup_history_tree.column(col, width=80, anchor=anchor_val)
    app_instance.matchup_history_tree.column("Date", width=100); app_instance.matchup_history_tree.column("Deck", width=150); app_instance.matchup_history_tree.column("Revealed Cards", width=200, stretch=tk.YES)
    h_vsb = ttk.Scrollbar(history_tab_matchup, orient="vertical", command=app_instance.matchup_history_tree.yview); h_hsb = ttk.Scrollbar(history_tab_matchup, orient="horizontal", command=app_instance.matchup_history_tree.xview)
    app_instance.matchup_history_tree.configure(yscrollcommand=h_vsb.set, xscrollcommand=h_hsb.set); h_vsb.pack(side='right', fill='y'); h_hsb.pack(side='bottom', fill='x'); app_instance.matchup_history_tree.pack(fill=tk.BOTH, expand=True)

def _setup_location_stats_ui(app_instance, parent_frame):
    filter_frame = ttk.Frame(parent_frame); filter_frame.pack(fill=tk.X, pady=5)
    ttk.Label(filter_frame, text="Filter by Deck:").pack(side=tk.LEFT, padx=(0,5))
    # app_instance.location_deck_filter_var from setup_string_vars
    loc_deck_opts = ["All Decks"] + app_instance.all_deck_names_for_filter if hasattr(app_instance, 'all_deck_names_for_filter') else ["All Decks"]
    app_instance.location_deck_filter_menu = ttk.OptionMenu(filter_frame, app_instance.location_deck_filter_var, loc_deck_opts[0] if loc_deck_opts else "All Decks", *loc_deck_opts, command=app_instance.load_location_stats)
    app_instance.location_deck_filter_menu.pack(side=tk.LEFT, padx=5)
    ttk.Label(filter_frame, text="Season:").pack(side=tk.LEFT, padx=(20,5))
    # app_instance.location_season_filter_var from setup_string_vars
    loc_season_opts = ["All Seasons"] # TODO: Populate from app_instance
    app_instance.location_season_filter_menu = ttk.OptionMenu(filter_frame, app_instance.location_season_filter_var, "All Seasons", *loc_season_opts, command=app_instance.load_location_stats)
    app_instance.location_season_filter_menu.pack(side=tk.LEFT, padx=5)
    ttk.Button(filter_frame, text="Refresh Data", command=app_instance.load_location_stats).pack(side=tk.LEFT, padx=5)
    view_frame = ttk.Frame(parent_frame); view_frame.pack(fill=tk.X, pady=5)
    # app_instance.location_view_var from setup_string_vars
    ttk.Radiobutton(view_frame, text="Table View", variable=app_instance.location_view_var, value="Table", command=app_instance.toggle_location_view).pack(side=tk.LEFT, padx=5)
    ttk.Radiobutton(view_frame, text="Chart View", variable=app_instance.location_view_var, value="Chart", command=app_instance.toggle_location_view).pack(side=tk.LEFT, padx=5)
    app_instance.location_container = ttk.Frame(parent_frame); app_instance.location_container.pack(fill=tk.BOTH, expand=True, pady=5)
    app_instance.location_table_frame = ttk.LabelFrame(app_instance.location_container, text="Location Performance", padding="5"); app_instance.location_table_frame.pack(fill=tk.BOTH, expand=True)
    cols = ("Location", "Games", "Win %", "Wins", "Losses", "Ties", "Net Cubes", "Avg Cubes")
    app_instance.location_stats_tree = ttk.Treeview(app_instance.location_table_frame, columns=cols, show="headings", selectmode="browse")
    for col in cols:
        app_instance.location_stats_tree.heading(col, text=col, command=lambda _col=col: app_instance.sort_location_treeview(_col, False))
        anchor_val = 'center' if col != "Location" else "w"; app_instance.location_stats_tree.column(col, width=80, anchor=anchor_val, stretch=tk.YES if col == "Location" else tk.NO)
    app_instance.location_stats_tree.column("Location", width=150, stretch=tk.YES)
    vsb = ttk.Scrollbar(app_instance.location_table_frame, orient="vertical", command=app_instance.location_stats_tree.yview); hsb = ttk.Scrollbar(app_instance.location_table_frame, orient="horizontal", command=app_instance.location_stats_tree.xview)
    app_instance.location_stats_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set); vsb.pack(side='right', fill='y'); hsb.pack(side='bottom', fill='x'); app_instance.location_stats_tree.pack(fill=tk.BOTH, expand=True)
    app_instance.location_chart_frame = ttk.LabelFrame(app_instance.location_container, text="Location Performance Chart", padding="5")
    app_instance.location_figure = Figure(figsize=(8, 6), dpi=100)
    app_instance.location_canvas = FigureCanvasTkAgg(app_instance.location_figure, app_instance.location_chart_frame); app_instance.location_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    app_instance.location_details_frame = ttk.LabelFrame(parent_frame, text="Location Details", padding="5"); app_instance.location_details_frame.pack(fill=tk.X, pady=5)
    # app_instance.location_details_var from setup_string_vars
    ttk.Label(app_instance.location_details_frame, textvariable=app_instance.location_details_var, font=("Arial", 10)).pack(fill=tk.X, pady=5)

def _setup_trends_ui(app_instance, parent_frame):
    control_frame = ttk.Frame(parent_frame); control_frame.pack(fill=tk.X, pady=5)
    ttk.Label(control_frame, text="Time Range:").pack(side=tk.LEFT, padx=(0,5))
    # app_instance.trend_days_var from setup_string_vars
    app_instance.trend_days_combo = ttk.Combobox(control_frame, textvariable=app_instance.trend_days_var, values=["7", "14", "30", "60", "90", "All"])
    app_instance.trend_days_combo.pack(side=tk.LEFT, padx=5); app_instance.trend_days_combo.current(2)
    filter_frame_trends = ttk.Frame(parent_frame); filter_frame_trends.pack(fill=tk.X, pady=5)
    ttk.Button(filter_frame_trends, text="Filter Decks...", command=app_instance.show_trend_deck_filter_dialog).pack(side=tk.LEFT, padx=(0,5))
    ttk.Label(filter_frame_trends, textvariable=app_instance.trend_deck_filter_display_var).pack(side=tk.LEFT, padx=5) # trend_deck_filter_display_var from app
    ttk.Label(control_frame, text="Opponent:").pack(side=tk.LEFT, padx=(20,5))
    # app_instance.trend_opponent_filter_var from setup_string_vars
    app_instance.trend_opponent_filter_menu = ttk.OptionMenu(control_frame, app_instance.trend_opponent_filter_var, "All Opponents", "All Opponents", command=app_instance.update_trends)
    app_instance.trend_opponent_filter_menu.pack(side=tk.LEFT, padx=5)
    ttk.Button(control_frame, text="Update Chart", command=app_instance.update_trends).pack(side=tk.LEFT, padx=20)
    chart_frame = ttk.LabelFrame(parent_frame, text="Performance Trends", padding="5"); chart_frame.pack(fill=tk.BOTH, expand=True, pady=5)
    app_instance.trend_figure = Figure(figsize=(10, 8), dpi=100)
    app_instance.trend_win_rate_ax = app_instance.trend_figure.add_subplot(211); app_instance.trend_cubes_ax = app_instance.trend_figure.add_subplot(212)
    app_instance.trends_canvas = FigureCanvasTkAgg(app_instance.trend_figure, chart_frame); app_instance.trends_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    app_instance.trend_summary_frame = ttk.LabelFrame(parent_frame, text="Summary", padding="5"); app_instance.trend_summary_frame.pack(fill=tk.X, pady=5)
    summary_grid = ttk.Frame(app_instance.trend_summary_frame); summary_grid.pack(fill=tk.X, pady=5)
    ttk.Label(summary_grid, text="Total Matches:").grid(row=0, column=0, sticky="w", padx=10)
    # StringVars for summary (e.g., app_instance.trend_total_matches_var) are defined in SnapTrackerApp's setup_string_vars
    ttk.Label(summary_grid, textvariable=app_instance.trend_total_matches_var, font=("Arial", 10, "bold")).grid(row=0, column=1, sticky="w", padx=10)
    ttk.Label(summary_grid, text="Overall Win Rate:").grid(row=0, column=2, sticky="w", padx=10)
    ttk.Label(summary_grid, textvariable=app_instance.trend_win_rate_var, font=("Arial", 10, "bold")).grid(row=0, column=3, sticky="w", padx=10)
    ttk.Label(summary_grid, text="Net Cubes:").grid(row=1, column=0, sticky="w", padx=10)
    ttk.Label(summary_grid, textvariable=app_instance.trend_net_cubes_var, font=("Arial", 10, "bold")).grid(row=1, column=1, sticky="w", padx=10)
    ttk.Label(summary_grid, text="Avg Cubes/Game:").grid(row=1, column=2, sticky="w", padx=10)
    ttk.Label(summary_grid, textvariable=app_instance.trend_avg_cubes_var, font=("Arial", 10, "bold")).grid(row=1, column=3, sticky="w", padx=10)

def _setup_settings_ui(app_instance, parent_frame):
    canvas = tk.Canvas(parent_frame); scrollbar = ttk.Scrollbar(parent_frame, orient="vertical", command=canvas.yview); settings_frame = ttk.Frame(canvas)
    settings_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=settings_frame, anchor="nw"); canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y")
    general_frame = ttk.LabelFrame(settings_frame, text="General Settings", padding="10"); general_frame.pack(fill=tk.X, pady=10, padx=10)
    # Vars like app_instance.auto_update_card_db_var are defined in SnapTrackerApp setup_string_vars
    ttk.Checkbutton(general_frame, text="Auto-update card database on startup", variable=app_instance.auto_update_card_db_var).pack(anchor="w", pady=5)
    ttk.Checkbutton(general_frame, text="Check for application updates on startup", variable=app_instance.check_for_updates_var).pack(anchor="w", pady=5)
    ttk.Checkbutton(general_frame, text="Display card names instead of IDs when available", variable=app_instance.display_card_names_var).pack(anchor="w", pady=5)
    interval_frame = ttk.Frame(general_frame); interval_frame.pack(fill=tk.X, pady=5)
    ttk.Label(interval_frame, text="Data update interval (ms):").pack(side=tk.LEFT, padx=(0, 10))
    ttk.Entry(interval_frame, textvariable=app_instance.update_interval_var, width=6).pack(side=tk.LEFT)
    error_log_frame_s = ttk.Frame(general_frame); error_log_frame_s.pack(fill=tk.X, pady=5)
    ttk.Label(error_log_frame_s, text="Maximum error log entries:").pack(side=tk.LEFT, padx=(0, 10))
    ttk.Entry(error_log_frame_s, textvariable=app_instance.max_error_log_var, width=6).pack(side=tk.LEFT)
    theme_frame = ttk.LabelFrame(settings_frame, text="Theme Settings", padding="10"); theme_frame.pack(fill=tk.X, pady=10, padx=10)
    theme_select_frame = ttk.Frame(theme_frame); theme_select_frame.pack(fill=tk.X, pady=5)
    ttk.Label(theme_select_frame, text="Theme:").pack(side=tk.LEFT, padx=(0, 10))
    # app_instance.theme_var from setup_string_vars
    theme_combo = ttk.Combobox(theme_select_frame, textvariable=app_instance.theme_var, values=["dark", "light", "custom"])
    theme_combo.pack(side=tk.LEFT); theme_combo.bind("<<ComboboxSelected>>", lambda e: app_instance.change_theme(app_instance.theme_var.get()))
    color_grid = ttk.Frame(theme_frame); color_grid.pack(fill=tk.X, pady=10)
    color_options = [("Background", "bg_main"), ("Secondary Background", "bg_secondary"), ("Text", "fg_main"), ("Primary Accent", "accent_primary"), ("Secondary Accent", "accent_secondary"), ("Win Color", "win"), ("Loss Color", "loss"), ("Neutral Color", "neutral")]
    # app_instance.color_vars should be initialized in SnapTrackerApp
    for i, (label_text, color_key) in enumerate(color_options):
        row = i // 2; col = i % 2 * 2
        ttk.Label(color_grid, text=label_text + ":").grid(row=row, column=col, sticky="e", padx=(10 if col > 0 else 0, 5), pady=5)
        # Ensure app_instance.config['Colors'] exists
        color_val_fallback = "#ffffff" # A generic fallback
        if hasattr(app_instance, 'config') and 'Colors' in app_instance.config:
             color_val_fallback = app_instance.config['Colors'].get(color_key, "#ffffff")

        current_color_val = color_val_fallback
        if color_key in app_instance.color_vars: # Use pre-existing StringVar if available
            color_var = app_instance.color_vars[color_key]
            color_var.set(current_color_val) # Update it
        else: # Create if missing (should not happen if setup_string_vars is complete)
            color_var = tk.StringVar(value=current_color_val)
            app_instance.color_vars[color_key] = color_var

        cfp_frame = ttk.Frame(color_grid, width=20, height=20, relief="solid", borderwidth=1); cfp_frame.grid(row=row, column=col+1, sticky="w", padx=5, pady=5)
        color_lbl = tk.Label(cfp_frame, background=color_var.get(), width=3, height=1); color_lbl.pack(fill=tk.BOTH, expand=True)
        color_lbl.bind("<Button-1>", lambda e, key=color_key, lbl=color_lbl: app_instance.pick_color(key, lbl))
    ttk.Button(theme_frame, text="Apply Custom Theme", command=app_instance.apply_custom_theme).pack(pady=10)
    paths_frame = ttk.LabelFrame(settings_frame, text="File Paths", padding="10"); paths_frame.pack(fill=tk.X, pady=10, padx=10)
    game_state_frame_s = ttk.Frame(paths_frame); game_state_frame_s.pack(fill=tk.X, pady=5)
    ttk.Label(game_state_frame_s, text="Game State Path:").pack(side=tk.LEFT, padx=(0, 10))
    # app_instance.game_state_path_var from setup_string_vars
    ttk.Entry(game_state_frame_s, textvariable=app_instance.game_state_path_var, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Button(game_state_frame_s, text="Browse...", command=app_instance.browse_game_state_path).pack(side=tk.LEFT, padx=5)
    card_db_frame_s = ttk.Frame(paths_frame); card_db_frame_s.pack(fill=tk.X, pady=5)
    ttk.Label(card_db_frame_s, text="Card Database API:").pack(side=tk.LEFT, padx=(0, 10))
    # app_instance.card_db_api_var from setup_string_vars
    ttk.Entry(card_db_frame_s, textvariable=app_instance.card_db_api_var, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)
    about_frame_s = ttk.LabelFrame(settings_frame, text="About", padding="10"); about_frame_s.pack(fill=tk.X, pady=10, padx=10)

    version_text = "unknown" # Fallback
    if hasattr(app_instance, 'VERSION'): version_text = app_instance.VERSION

    ttk.Label(about_frame_s, text=f"Marvel Snap Tracker v{version_text}", font=("Arial", 12, "bold")).pack(pady=5)
    ttk.Label(about_frame_s, text="An enhanced tracking tool for Marvel Snap").pack(pady=2)
    ttk.Label(about_frame_s, text="Original by GitHub user (updated by Claude)").pack(pady=2)
    ttk.Button(about_frame_s, text="Check for App Updates", command=app_instance.check_for_updates_command).pack(pady=10)
    save_settings_frame_s = ttk.Frame(settings_frame); save_settings_frame_s.pack(fill=tk.X, pady=20, padx=10)
    ttk.Button(save_settings_frame_s, text="Save All Settings", command=app_instance.save_settings).pack(pady=5)
