import tkinter as tk
from tkinter import ttk, scrolledtext
import re # For tooltip regex in live game ui
import json # For deck performance tags
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Other imports will be added as needed by other tab setup functions
# For example, some tabs might use functions from other utility modules.
# We'll handle those on a per-function basis to keep dependencies clear.

def _setup_live_game_ui(app_instance, parent_frame):
    """Set up the Live Game tab UI"""
    top_content_frame = ttk.Frame(parent_frame)
    top_content_frame.pack(expand=True, fill=tk.BOTH, side=tk.TOP)

    # Status bar at bottom
    status_bar = ttk.Label(parent_frame, textvariable=app_instance.status_var, relief=tk.SUNKEN, anchor=tk.W)
    status_bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(5,0))

    # Error log frame
    error_log_frame = ttk.LabelFrame(parent_frame, text="Error Log", padding="5")
    error_log_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(5,0), ipady=2)
    app_instance.error_log_text = scrolledtext.ScrolledText(error_log_frame, height=4, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
    app_instance.error_log_text.pack(expand=True, fill=tk.X)

    # Game details frame
    game_details_frame = ttk.LabelFrame(top_content_frame, text="Game Info", padding="5")
    game_details_frame.pack(pady=5, padx=5, fill=tk.X)
    ttk.Label(game_details_frame, textvariable=app_instance.turn_var).pack(side=tk.LEFT, padx=5)
    ttk.Label(game_details_frame, textvariable=app_instance.cubes_var).pack(side=tk.LEFT, padx=5)

    # Deck Stats Modal button
    app_instance.deck_stats_button = ttk.Button( # Store as instance variable
        game_details_frame, # Parent is game_details_frame
        text="Deck Stats",
        command=app_instance.show_deck_modal
    )
    app_instance.deck_stats_button.pack(side=tk.RIGHT, padx=10) # Pack to the right of game_details_frame

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
        ttk.Label(loc_frame, textvariable=app_instance.location_vars[i]["name"], font=('Arial', 10, 'bold')).pack(pady=(2,2), anchor='n')
        ttk.Label(loc_frame, textvariable=app_instance.location_vars[i]["power"]).pack(pady=(0,5), anchor='n')

        # Opponent cards subframe
        opp_cards_sub_frame = ttk.Frame(loc_frame)
        opp_cards_sub_frame.pack(fill=tk.BOTH, expand=True, pady=(0,2), ipady=2)
        ttk.Label(opp_cards_sub_frame, text="Opp Cards:", anchor="w", font=('Arial', 8, 'italic')).pack(fill=tk.X)
        opp_label = ttk.Label(opp_cards_sub_frame, textvariable=app_instance.location_vars[i]["opp_cards"],
                     wraplength=180, justify=tk.LEFT, anchor="nw", relief="sunken",
                     borderwidth=1, padding=(2,5))
        opp_label.pack(fill=tk.BOTH, expand=True)
        opp_label.bind("<Enter>", lambda e, idx=i, player="opp": app_instance.on_card_list_hover(e, idx, player))
        opp_label.bind("<Leave>", lambda e: app_instance.card_tooltip.hide_tooltip())

        # Your cards subframe
        your_cards_sub_frame = ttk.Frame(loc_frame)
        your_cards_sub_frame.pack(fill=tk.BOTH, expand=True, pady=(2,0), ipady=2)
        ttk.Label(your_cards_sub_frame, text="Your Cards:", anchor="w", font=('Arial', 8, 'italic')).pack(fill=tk.X)
        local_label = ttk.Label(your_cards_sub_frame, textvariable=app_instance.location_vars[i]["local_cards"],
                      wraplength=180, justify=tk.LEFT, anchor="nw", relief="sunken",
                      borderwidth=1, padding=(2,5))
        local_label.pack(fill=tk.BOTH, expand=True)
        local_label.bind("<Enter>", lambda e, idx=i, player="local": app_instance.on_card_list_hover(e, idx, player))
        local_label.bind("<Leave>", lambda e: app_instance.card_tooltip.hide_tooltip())

    # Player panels
    paned_window = ttk.PanedWindow(top_content_frame, orient=tk.HORIZONTAL)
    paned_window.pack(expand=True, fill=tk.BOTH, pady=5)

    # Local player frame
    local_player_frame = ttk.LabelFrame(paned_window, text="Local Player", padding="10")
    paned_window.add(local_player_frame, weight=1)

    ttk.Label(local_player_frame, textvariable=app_instance.local_player_name_var, font=('Arial', 12, 'bold')).grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
    ttk.Label(local_player_frame, textvariable=app_instance.local_energy_var).grid(row=1, column=0, sticky="w", pady=1)
    ttk.Label(local_player_frame, textvariable=app_instance.local_snap_status_var).grid(row=1, column=1, sticky="w", pady=1, padx=(5,0))

    # Hand cards with tooltip
    ttk.Label(local_player_frame, text="Hand:").grid(row=2, column=0, sticky="nw", pady=2)
    hand_label = ttk.Label(local_player_frame, textvariable=app_instance.local_hand_var, wraplength=280, justify=tk.LEFT)
    hand_label.grid(row=2, column=1, sticky="new", pady=2)
    hand_label.bind("<Enter>", lambda e, zone="hand": app_instance.on_zone_hover(e, zone))
    hand_label.bind("<Leave>", lambda e: app_instance.card_tooltip.hide_tooltip())

    # Deck count
    ttk.Label(local_player_frame, text="Deck:").grid(row=3, column=0, sticky="nw", pady=2)
    ttk.Label(local_player_frame, textvariable=app_instance.local_deck_var).grid(row=3, column=1, sticky="new", pady=2)

    # Remaining deck with tooltip
    ttk.Label(local_player_frame, text="Remaining:").grid(row=4, column=0, sticky="nw", pady=2)
    remaining_label = ttk.Label(local_player_frame, textvariable=app_instance.local_remaining_deck_var, wraplength=280, justify=tk.LEFT)
    remaining_label.grid(row=4, column=1, sticky="new", pady=2)
    remaining_label.bind("<Enter>", lambda e, zone="remaining": app_instance.on_zone_hover(e, zone))
    remaining_label.bind("<Leave>", lambda e: app_instance.card_tooltip.hide_tooltip())

    # Destroyed cards with tooltip
    ttk.Label(local_player_frame, text="Destroyed:").grid(row=5, column=0, sticky="nw", pady=2)
    graveyard_label = ttk.Label(local_player_frame, textvariable=app_instance.local_graveyard_var, wraplength=280, justify=tk.LEFT)
    graveyard_label.grid(row=5, column=1, sticky="new", pady=2)
    graveyard_label.bind("<Enter>", lambda e, zone="graveyard": app_instance.on_zone_hover(e, zone))
    graveyard_label.bind("<Leave>", lambda e: app_instance.card_tooltip.hide_tooltip())

    # Banished cards with tooltip
    ttk.Label(local_player_frame, text="Banished:").grid(row=6, column=0, sticky="nw", pady=2)
    banished_label = ttk.Label(local_player_frame, textvariable=app_instance.local_banished_var, wraplength=280, justify=tk.LEFT)
    banished_label.grid(row=6, column=1, sticky="new", pady=2)
    banished_label.bind("<Enter>", lambda e, zone="banished": app_instance.on_zone_hover(e, zone))
    banished_label.bind("<Leave>", lambda e: app_instance.card_tooltip.hide_tooltip())

    local_player_frame.grid_columnconfigure(1, weight=1)

    # Opponent frame
    opponent_frame = ttk.LabelFrame(paned_window, text="Opponent", padding="10")
    paned_window.add(opponent_frame, weight=1)

    ttk.Label(opponent_frame, textvariable=app_instance.opponent_name_var, font=('Arial', 12, 'bold')).grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
    ttk.Label(opponent_frame, textvariable=app_instance.opponent_energy_var).grid(row=1, column=0, sticky="w", pady=1)
    ttk.Label(opponent_frame, textvariable=app_instance.opponent_snap_status_var).grid(row=1, column=1, sticky="w", pady=1, padx=(5,0))

    ttk.Label(opponent_frame, text="Hand:").grid(row=2, column=0, sticky="nw", pady=2)
    ttk.Label(opponent_frame, textvariable=app_instance.opponent_hand_var).grid(row=2, column=1, sticky="new", pady=2)

    # Opponent destroyed cards with tooltip
    ttk.Label(opponent_frame, text="Destroyed:").grid(row=3, column=0, sticky="nw", pady=2)
    opp_graveyard_label = ttk.Label(opponent_frame, textvariable=app_instance.opponent_graveyard_var, wraplength=280, justify=tk.LEFT)
    opp_graveyard_label.grid(row=3, column=1, sticky="new", pady=2)
    opp_graveyard_label.bind("<Enter>", lambda e, zone="opp_graveyard": app_instance.on_zone_hover(e, zone))
    opp_graveyard_label.bind("<Leave>", lambda e: app_instance.card_tooltip.hide_tooltip())

    # Opponent banished cards with tooltip
    ttk.Label(opponent_frame, text="Banished:").grid(row=4, column=0, sticky="nw", pady=2)
    opp_banished_label = ttk.Label(opponent_frame, textvariable=app_instance.opponent_banished_var, wraplength=280, justify=tk.LEFT)
    opp_banished_label.grid(row=4, column=1, sticky="new", pady=2)
    opp_banished_label.bind("<Enter>", lambda e, zone="opp_banished": app_instance.on_zone_hover(e, zone))
    opp_banished_label.bind("<Leave>", lambda e: app_instance.card_tooltip.hide_tooltip())

    opponent_frame.grid_columnconfigure(1, weight=1)

    # Encounter history frame
    last_encounter_frame = ttk.LabelFrame(opponent_frame, text="Encounter History", padding="5")
    last_encounter_frame.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(10,0), padx=2)
    opponent_frame.grid_rowconfigure(5, weight=1)
    last_encounter_frame.grid_columnconfigure(1, weight=1)

    name_frame = ttk.Frame(last_encounter_frame)
    name_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=2)
    ttk.Label(name_frame, text="Opponent:").pack(side=tk.LEFT)
    ttk.Label(name_frame, textvariable=app_instance.last_encounter_opponent_name_var).pack(side=tk.LEFT, padx=(5,0))

    app_instance.opponent_encounter_history_text = scrolledtext.ScrolledText(
        last_encounter_frame, height=5, wrap=tk.WORD, state=tk.DISABLED,
        relief="sunken", borderwidth=1, font=("Arial", 8)
    )
    app_instance.opponent_encounter_history_text.grid(row=1, column=0, columnspan=2, sticky="new", pady=(5,1), padx=2)
    last_encounter_frame.grid_rowconfigure(1, weight=1)

def _create_deck_filter_dialog(app_instance, title, all_deck_names_list,
                                   selected_deck_names_set, display_var_stringvar,
                                   apply_callback_func):
    """
    Generic helper to create a multi-select deck filter dialog.

    Args:
        app_instance (SnapTrackerApp): The main application instance.
        title (str): The title for the dialog window.
        all_deck_names_list (list): List of all available deck names.
        selected_deck_names_set (set): The set to store/read selected deck names.
        display_var_stringvar (tk.StringVar): StringVar to update with filter status display.
        apply_callback_func (function): Function to call after applying the filter.
    """
    dialog = tk.Toplevel(app_instance.root)
    dialog.title(title)
    dialog.geometry("400x550")
    dialog.transient(app_instance.root)
    dialog.grab_set()
    dialog.configure(background=app_instance.config['Colors']['bg_main'])

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
    scroll_canvas = tk.Canvas(checkbox_area_frame, background=app_instance.config['Colors']['bg_main'])
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

def _setup_history_ui(app_instance, parent_frame):
    """Set up the Match History tab UI"""
    # Filter frame
    filter_frame = ttk.Frame(parent_frame)
    filter_frame.pack(fill=tk.X, pady=5)

    # --- MODIFIED DECK FILTER ---
    app_instance.deck_filter_button = ttk.Button(filter_frame, text="Filter Decks...", command=app_instance.show_history_deck_filter_dialog)
    app_instance.deck_filter_button.pack(side=tk.LEFT, padx=(0, 5))
    ttk.Label(filter_frame, textvariable=app_instance.history_deck_filter_display_var).pack(side=tk.LEFT, padx=5)
    # --- END MODIFIED DECK FILTER ---

    # Add more filter options
    ttk.Label(filter_frame, text="Season:").pack(side=tk.LEFT, padx=(20,5))
    app_instance.season_filter_var = tk.StringVar(value="All Seasons")
    app_instance.season_filter_menu = ttk.OptionMenu(
        filter_frame, app_instance.season_filter_var,
        "All Seasons", "All Seasons", # Initial value, options populated by load_history_tab_data
        command=app_instance.apply_history_filter
    )
    app_instance.season_filter_menu.pack(side=tk.LEFT, padx=5)

    ttk.Label(filter_frame, text="Result:").pack(side=tk.LEFT, padx=(20,5))
    app_instance.result_filter_var = tk.StringVar(value="All Results")
    app_instance.result_filter_menu = ttk.OptionMenu(
        filter_frame, app_instance.result_filter_var,
        "All Results", "All Results", "Win", "Loss", "Tie",
        command=app_instance.apply_history_filter
    )
    app_instance.result_filter_menu.pack(side=tk.LEFT, padx=5)

    # Button frame
    button_frame = ttk.Frame(parent_frame)
    button_frame.pack(fill=tk.X, pady=5)

    ttk.Button(button_frame, text="Refresh History", command=app_instance.load_history_tab_data).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="Export Selected", command=app_instance.export_selected_matches).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="Add Note", command=app_instance.add_match_note).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="Delete Selected", command=app_instance.delete_selected_matches).pack(side=tk.LEFT, padx=5)

    # Search box
    search_frame = ttk.Frame(button_frame)
    search_frame.pack(side=tk.RIGHT)
    ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0,5))
    app_instance.search_var = tk.StringVar()
    app_instance.search_var.trace("w", lambda *args: app_instance.apply_history_filter())
    ttk.Entry(search_frame, textvariable=app_instance.search_var, width=20).pack(side=tk.LEFT)

    # History list frame
    history_list_frame = ttk.LabelFrame(parent_frame, text="Matches", padding="5")
    history_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

    # Create treeview with columns
    cols = ("Timestamp", "Deck", "Opponent", "Result", "Cubes", "Turns", "Location1", "Location2", "Location3")
    app_instance.history_tree = ttk.Treeview(history_list_frame, columns=cols, show="headings", selectmode="extended")

    # Configure columns
    for col in cols:
        app_instance.history_tree.heading(col, text=col, command=lambda _col=col: app_instance.sort_history_treeview(_col, False))
        app_instance.history_tree.column(col, width=100, anchor='w')

    # Adjust column widths
    app_instance.history_tree.column("Timestamp", width=140)
    app_instance.history_tree.column("Deck", width=150)
    app_instance.history_tree.column("Result", width=60, anchor='center')
    app_instance.history_tree.column("Cubes", width=50, anchor='center')
    app_instance.history_tree.column("Turns", width=50, anchor='center')
    app_instance.history_tree.column("Location1", width=100)
    app_instance.history_tree.column("Location2", width=100)
    app_instance.history_tree.column("Location3", width=100)

    # Add scrollbars
    vsb = ttk.Scrollbar(history_list_frame, orient="vertical", command=app_instance.history_tree.yview)
    hsb = ttk.Scrollbar(history_list_frame, orient="horizontal", command=app_instance.history_tree.xview)
    app_instance.history_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    # Pack scrollbars and treeview
    vsb.pack(side='right', fill='y')
    hsb.pack(side='bottom', fill='x')
    app_instance.history_tree.pack(fill=tk.BOTH, expand=True)

    # Bind events
    app_instance.history_tree.bind("<<TreeviewSelect>>", app_instance.on_history_match_select)
    app_instance.history_tree.bind("<Double-1>", app_instance.on_history_match_double_click)

    # Stats and details frame
    stats_frame = ttk.LabelFrame(parent_frame, text="Stats & Details", padding="5")
    stats_frame.pack(fill=tk.X, pady=5, ipady=5)

    # Stats summary at top of frame
    app_instance.stats_summary_var = tk.StringVar(value="No matches selected")
    ttk.Label(stats_frame, textvariable=app_instance.stats_summary_var, font=("Arial", 10, "bold")).pack(fill=tk.X, pady=(0, 5))

    # Text widget for details
    app_instance.stats_text_widget = scrolledtext.ScrolledText(
        stats_frame, height=8, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9)
    )
    app_instance.stats_text_widget.pack(fill=tk.X, expand=True)

def _setup_deck_performance_ui(app_instance, parent_frame):
    """Set up the Deck Performance tab UI"""
    # Filter frame
    filter_frame = ttk.Frame(parent_frame)
    filter_frame.pack(fill=tk.X, pady=5)

    ttk.Label(filter_frame, text="Season:").pack(side=tk.LEFT, padx=(0, 5))
    app_instance.deck_perf_season_filter_menu = ttk.OptionMenu(
        filter_frame, app_instance.deck_performance_season_filter_var,
        "All Seasons", "All Seasons", # Placeholder, will be populated
        command=app_instance.load_deck_performance_data
    )
    app_instance.deck_perf_season_filter_menu.pack(side=tk.LEFT, padx=5)

    ttk.Button(filter_frame, text="Refresh Stats", command=app_instance.load_deck_performance_data).pack(side=tk.LEFT, padx=5)

    # Deck Performance list frame
    deck_perf_list_frame = ttk.LabelFrame(parent_frame, text="Deck Statistics", padding="5")
    deck_perf_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

    cols = ("Deck Name", "Games", "Wins", "Losses", "Ties", "Win %", "Net Cubes", "Avg Cubes/Game", "Avg Cubes/Win", "Avg Cubes/Loss", "Tags")
    app_instance.deck_performance_tree = ttk.Treeview(deck_perf_list_frame, columns=cols, show="headings", selectmode="browse")

    col_widths = {
        "Deck Name": 200, "Games": 60, "Wins": 50, "Losses": 50, "Ties": 50,
        "Win %": 70, "Net Cubes": 70, "Avg Cubes/Game": 100,
        "Avg Cubes/Win": 100, "Avg Cubes/Loss": 100, "Tags": 100
    }

    for col in cols:
        app_instance.deck_performance_tree.heading(col, text=col, command=lambda _col=col: app_instance.sort_deck_performance_treeview(_col, False))
        anchor_val = 'w' if col == "Deck Name" or col == "Tags" else 'center'
        app_instance.deck_performance_tree.column(col, width=col_widths.get(col, 80), anchor=anchor_val, stretch=(col == "Deck Name"))

    # Add scrollbars
    vsb = ttk.Scrollbar(deck_perf_list_frame, orient="vertical", command=app_instance.deck_performance_tree.yview)
    hsb = ttk.Scrollbar(deck_perf_list_frame, orient="horizontal", command=app_instance.deck_performance_tree.xview)
    app_instance.deck_performance_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    vsb.pack(side='right', fill='y')
    hsb.pack(side='bottom', fill='x')
    app_instance.deck_performance_tree.pack(fill=tk.BOTH, expand=True)

    # Bind select event if needed for a details pane later (optional)
    # app_instance.deck_performance_tree.bind("<<TreeviewSelect>>", app_instance.on_deck_performance_select)

def _setup_card_stats_ui(app_instance, parent_frame):
    """Set up the Card Stats tab UI"""
    # Filter frame
    filter_frame = ttk.Frame(parent_frame)
    filter_frame.pack(fill=tk.X, pady=5)

    ttk.Button(filter_frame, text="Filter Decks...",
        command=app_instance.show_card_stats_deck_filter_dialog).pack(side=tk.LEFT, padx=(0,5))
    ttk.Label(filter_frame, textvariable=app_instance.card_stats_deck_filter_display_var).pack(side=tk.LEFT, padx=5)

    # Add season filter
    ttk.Label(filter_frame, text="Season:").pack(side=tk.LEFT, padx=(20,5))
    app_instance.card_stats_season_filter_var = tk.StringVar(value="All Seasons")
    app_instance.card_stats_season_filter_menu = ttk.OptionMenu(
        filter_frame, app_instance.card_stats_season_filter_var,
        "All Seasons", "All Seasons",
        command=app_instance.load_card_stats_data
    )
    app_instance.card_stats_season_filter_menu.pack(side=tk.LEFT, padx=5)

    # Buttons
    ttk.Button(filter_frame, text="Refresh Stats", command=app_instance.load_card_stats_data).pack(side=tk.LEFT, padx=5)

    # View options
    view_frame = ttk.Frame(parent_frame)
    view_frame.pack(fill=tk.X, pady=5)

    app_instance.card_stats_view_var = tk.StringVar(value="Table")
    ttk.Radiobutton(view_frame, text="Table View", variable=app_instance.card_stats_view_var,
                    value="Table", command=app_instance.toggle_card_stats_view).pack(side=tk.LEFT, padx=5)
    ttk.Radiobutton(view_frame, text="Chart View", variable=app_instance.card_stats_view_var,
                    value="Chart", command=app_instance.toggle_card_stats_view).pack(side=tk.LEFT, padx=5)

    # Card stats frame containing both table and chart views
    app_instance.card_stats_container = ttk.Frame(parent_frame)
    app_instance.card_stats_container.pack(fill=tk.BOTH, expand=True, pady=5)

    # Table view frame
    app_instance.card_stats_table_frame = ttk.LabelFrame(app_instance.card_stats_container, text="Card Performance", padding="5")
    app_instance.card_stats_table_frame.pack(fill=tk.BOTH, expand=True)

    # Create treeview
    cols = (
        "Card",
        "Drawn G", "Drawn Win%", "Net C (D)", "Avg C (D)", # Drawn
        "Played G", "Played Win%", "Net C (P)", "Avg C (P)", # Played
        "Not Drawn G", "Not Drawn Win%", "Net C (ND)", "Avg C (ND)", # Not Drawn
        "Not Played G", "Not Played Win%", "Net C (NP)", "Avg C (NP)",  # Not Played
        "ΔC (Drawn)", "ΔC (Played)" # Delta Columns
    )
    app_instance.card_stats_tree = ttk.Treeview(app_instance.card_stats_table_frame, columns=cols, show="headings", selectmode="browse")

    # Column widths (adjust as needed, these are estimates)
    col_widths = {
        "Card": 150,
        "Drawn G": 60, "Drawn Win%": 70, "Net C (D)": 70, "Avg C (D)": 70,
        "Played G": 60, "Played Win%": 70, "Net C (P)": 70, "Avg C (P)": 70,
        "Not Drawn G": 70, "Not Drawn Win%": 70, "Net C (ND)": 70, "Avg C (ND)": 70,
        "Not Played G": 70, "Not Played Win%": 70, "Net C (NP)": 70, "Avg C (NP)": 70,
        "ΔC (Drawn)": 70,
        "ΔC (Played)": 70
    }

    # Configure columns
    for col in cols:
        app_instance.card_stats_tree.heading(
            col, text=col,
            command=lambda _col=col: app_instance.sort_card_stats_treeview(_col, False)
        )
        anchor_val = 'center' if col != "Card" else "w"
        app_instance.card_stats_tree.column(
            col, width=col_widths.get(col, 80),
            anchor=anchor_val,
            stretch=tk.YES if col == "Card" else tk.NO
        )

    # Add scrollbars
    vsb = ttk.Scrollbar(app_instance.card_stats_table_frame, orient="vertical", command=app_instance.card_stats_tree.yview)
    hsb = ttk.Scrollbar(app_instance.card_stats_table_frame, orient="horizontal", command=app_instance.card_stats_tree.xview)
    app_instance.card_stats_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    # Pack scrollbars and treeview
    vsb.pack(side='right', fill='y')
    hsb.pack(side='bottom', fill='x')
    app_instance.card_stats_tree.pack(fill=tk.BOTH, expand=True)

    # Bind events
    app_instance.card_stats_tree.bind("<<TreeviewSelect>>", app_instance.on_card_stats_select)

    # Chart view frame (hidden initially)
    app_instance.card_stats_chart_frame = ttk.LabelFrame(app_instance.card_stats_container, text="Card Performance Chart", padding="5")
    # Will be packed when view is toggled to chart

    # Create matplotlib figure for chart
    app_instance.card_stats_figure = Figure(figsize=(8, 6), dpi=100)
    app_instance.card_stats_canvas = FigureCanvasTkAgg(app_instance.card_stats_figure, app_instance.card_stats_chart_frame)
    app_instance.card_stats_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # Status bar
    ttk.Label(parent_frame, textvariable=app_instance.card_stats_summary_var, relief=tk.SUNKEN, anchor=tk.W).pack(side=tk.BOTTOM, fill=tk.X, pady=(5,0))

def _setup_location_stats_ui(app_instance, parent_frame):
    """Set up the Location Stats tab UI"""
    # Filter frame
    filter_frame = ttk.Frame(parent_frame)
    filter_frame.pack(fill=tk.X, pady=5)

    # Deck filter
    ttk.Button(filter_frame, text="Filter Decks...",
                command=app_instance.show_location_deck_filter_dialog).pack(side=tk.LEFT, padx=(0,5))
    ttk.Label(filter_frame, textvariable=app_instance.location_deck_filter_display_var).pack(side=tk.LEFT, padx=5)

    # Season filter
    ttk.Label(filter_frame, text="Season:").pack(side=tk.LEFT, padx=(20,5))
    app_instance.loc_stats_season_filter_var = tk.StringVar(value="All Seasons") # Specific for this tab
    app_instance.loc_stats_season_filter_menu = ttk.OptionMenu(
        filter_frame, app_instance.loc_stats_season_filter_var,
        "All Seasons", "All Seasons", # Options populated by load_location_stats
        command=app_instance.load_location_stats
    )
    app_instance.loc_stats_season_filter_menu.pack(side=tk.LEFT, padx=5)

    # Refresh button
    ttk.Button(filter_frame, text="Refresh Stats", command=app_instance.load_location_stats).pack(side=tk.LEFT, padx=5)

    # Location list frame
    location_list_frame = ttk.LabelFrame(parent_frame, text="Location Statistics", padding="5")
    location_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

    cols = ("Location", "Seen", "Win %", "Avg Cubes", "Player Snap %", "Opp Snap %")
    app_instance.location_stats_tree = ttk.Treeview(location_list_frame, columns=cols, show="headings", selectmode="browse")

    col_widths = {"Location": 200, "Seen": 80, "Win %": 80, "Avg Cubes": 80, "Player Snap %": 100, "Opp Snap %": 100}

    for col in cols:
        app_instance.location_stats_tree.heading(col, text=col, command=lambda _col=col: app_instance.sort_location_stats_treeview(_col, False))
        anchor_val = 'w' if col == "Location" else 'center'
        app_instance.location_stats_tree.column(col, width=col_widths.get(col, 100), anchor=anchor_val)

    # Add scrollbars
    vsb = ttk.Scrollbar(location_list_frame, orient="vertical", command=app_instance.location_stats_tree.yview)
    hsb = ttk.Scrollbar(location_list_frame, orient="horizontal", command=app_instance.location_stats_tree.xview)
    app_instance.location_stats_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    vsb.pack(side='right', fill='y')
    hsb.pack(side='bottom', fill='x')
    app_instance.location_stats_tree.pack(fill=tk.BOTH, expand=True)

def _setup_trends_ui(app_instance, parent_frame):
    """Set up the Trends tab UI for win rate and cube trends"""
    # Filter frame
    filter_frame = ttk.Frame(parent_frame)
    filter_frame.pack(fill=tk.X, pady=5)

    # Deck filter for trends
    ttk.Button(filter_frame, text="Filter Decks...",
                command=app_instance.show_trend_deck_filter_dialog).pack(side=tk.LEFT, padx=(0,5))
    ttk.Label(filter_frame, textvariable=app_instance.trend_deck_filter_display_var).pack(side=tk.LEFT, padx=5)

    # Opponent filter for trends
    ttk.Label(filter_frame, text="Opponent:").pack(side=tk.LEFT, padx=(20,5))
    app_instance.trend_opponent_filter_var = tk.StringVar(value="All Opponents")
    app_instance.trend_opponent_filter_menu = ttk.OptionMenu(
        filter_frame, app_instance.trend_opponent_filter_var,
        "All Opponents", # Default value
        "All Opponents", # First item in list
        # Other opponent names will be populated by load_opponent_names_for_filter
        command=lambda _: app_instance.update_trends() # Use lambda to avoid passing event arg
    )
    app_instance.trend_opponent_filter_menu.pack(side=tk.LEFT, padx=5)


    # Days filter for trends
    ttk.Label(filter_frame, text="Days:").pack(side=tk.LEFT, padx=(20,5))
    days_options = ["7", "14", "30", "60", "90", "All"]
    app_instance.trend_days_var.set("30") # Default
    ttk.OptionMenu(filter_frame, app_instance.trend_days_var, app_instance.trend_days_var.get(), *days_options,
                    command=lambda _: app_instance.update_trends()).pack(side=tk.LEFT, padx=5)

    ttk.Button(filter_frame, text="Refresh Trends", command=app_instance.update_trends).pack(side=tk.LEFT, padx=5)

    # Chart area
    chart_frame = ttk.LabelFrame(parent_frame, text="Trend Charts", padding="10")
    chart_frame.pack(fill=tk.BOTH, expand=True, pady=10)

    # Create a PanedWindow to hold two charts side-by-side or top-bottom
    trends_paned_window = ttk.PanedWindow(chart_frame, orient=tk.VERTICAL) # Changed to VERTICAL
    trends_paned_window.pack(fill=tk.BOTH, expand=True)

    # Win Rate Chart Frame
    win_rate_chart_sub_frame = ttk.Frame(trends_paned_window)
    trends_paned_window.add(win_rate_chart_sub_frame, weight=1)

    app_instance.trends_figure_win_rate = Figure(figsize=(10, 4), dpi=100) # Adjusted figsize
    app_instance.trends_canvas_win_rate = FigureCanvasTkAgg(app_instance.trends_figure_win_rate, master=win_rate_chart_sub_frame)
    app_instance.trends_canvas_win_rate.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    # Net Cubes Chart Frame
    net_cubes_chart_sub_frame = ttk.Frame(trends_paned_window)
    trends_paned_window.add(net_cubes_chart_sub_frame, weight=1)

    app_instance.trends_figure_net_cubes = Figure(figsize=(10, 4), dpi=100) # Adjusted figsize
    app_instance.trends_canvas_net_cubes = FigureCanvasTkAgg(app_instance.trends_figure_net_cubes, master=net_cubes_chart_sub_frame)
    app_instance.trends_canvas_net_cubes.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

def _setup_settings_ui(app_instance, parent_frame):
    """Set up the Settings tab UI"""
    settings_content_frame = ttk.Frame(parent_frame, padding="10")
    settings_content_frame.pack(expand=True, fill=tk.BOTH)

    # General Settings
    general_frame = ttk.LabelFrame(settings_content_frame, text="General Settings", padding="10")
    general_frame.pack(fill=tk.X, pady=5)

    # Auto-update card DB
    app_instance.auto_update_card_db_var = tk.BooleanVar(
        value=app_instance.config.getboolean('Settings', 'auto_update_card_db', fallback=True)
    )
    ttk.Checkbutton(general_frame, text="Automatically update card database on startup",
                    variable=app_instance.auto_update_card_db_var,
                    command=lambda: app_instance.save_setting('Settings', 'auto_update_card_db', app_instance.auto_update_card_db_var.get())
                    ).pack(anchor="w", pady=2)

    # Check for app updates
    app_instance.check_for_app_updates_var = tk.BooleanVar(
        value=app_instance.config.getboolean('Settings', 'check_for_app_updates', fallback=True)
    )
    ttk.Checkbutton(general_frame, text="Check for application updates on startup",
                    variable=app_instance.check_for_app_updates_var,
                    command=lambda: app_instance.save_setting('Settings', 'check_for_app_updates', app_instance.check_for_app_updates_var.get())
                    ).pack(anchor="w", pady=2)

    # Display card names (or IDs)
    app_instance.card_name_display_var = tk.BooleanVar(
        value=app_instance.config.getboolean('Settings', 'card_name_display', fallback=True)
    )
    ttk.Checkbutton(general_frame, text="Display card names (instead of IDs) in live tracker where possible",
                    variable=app_instance.card_name_display_var,
                    command=lambda: app_instance.save_setting('Settings', 'card_name_display', app_instance.card_name_display_var.get())
                    ).pack(anchor="w", pady=2)

    # Update interval
    update_interval_frame = ttk.Frame(general_frame)
    update_interval_frame.pack(anchor="w", pady=2)
    ttk.Label(update_interval_frame, text="Live Tracker Update Interval (ms):").pack(side=tk.LEFT)
    app_instance.update_interval_var = tk.StringVar(
        value=app_instance.config.get('Settings', 'update_interval', fallback='1500')
    )
    ttk.Entry(update_interval_frame, textvariable=app_instance.update_interval_var, width=10).pack(side=tk.LEFT, padx=5)
    ttk.Button(update_interval_frame, text="Apply",
                command=lambda: app_instance.save_setting('Settings', 'update_interval', app_instance.update_interval_var.get())
                ).pack(side=tk.LEFT)

    # Max Error Log Entries
    max_log_frame = ttk.Frame(general_frame)
    max_log_frame.pack(anchor="w", pady=2)
    ttk.Label(max_log_frame, text="Max Error Log Entries (Live Tab):").pack(side=tk.LEFT)
    app_instance.max_error_log_var = tk.StringVar(
        value=app_instance.config.get('Settings', 'max_error_log_entries', fallback='50')
    )
    ttk.Entry(max_log_frame, textvariable=app_instance.max_error_log_var, width=8).pack(side=tk.LEFT, padx=5)
    ttk.Button(max_log_frame, text="Apply",
                command=lambda: app_instance.save_setting('Settings', 'max_error_log_entries', app_instance.max_error_log_var.get())
                ).pack(side=tk.LEFT)


    # Theme Settings
    theme_frame = ttk.LabelFrame(settings_content_frame, text="Theme Settings", padding="10")
    theme_frame.pack(fill=tk.X, pady=5)

    ttk.Button(theme_frame, text="Customize Theme Colors...", command=app_instance.customize_theme).pack(pady=5)
    ttk.Button(theme_frame, text="Reset to Default Dark Theme", command=lambda: app_instance.change_theme("dark", True)).pack(pady=5)
    ttk.Button(theme_frame, text="Reset to Default Light Theme", command=lambda: app_instance.change_theme("light", True)).pack(pady=5)

    # Database Settings
    db_frame = ttk.LabelFrame(settings_content_frame, text="Database Settings", padding="10")
    db_frame.pack(fill=tk.X, pady=5)

    ttk.Button(db_frame, text="Update Card Database (from API)", command=app_instance.update_card_db_command).pack(anchor="w", pady=3)
    ttk.Button(db_frame, text="Import Card Database (from JSON file)", command=app_instance.import_card_db_file_command).pack(anchor="w", pady=3)
    ttk.Button(db_frame, text="Backup Database", command=app_instance.backup_database).pack(anchor="w", pady=3)
    ttk.Button(db_frame, text="Clean Duplicate Match Events", command=app_instance.cleanup_duplicate_events_command).pack(anchor="w", pady=3)

    reset_db_button = ttk.Button(db_frame, text="Reset Entire Match Database...", command=app_instance.reset_database)
    reset_db_button.pack(anchor="w", pady=(10,3))
    # Add warning style if possible or just note in text
    ttk.Label(db_frame, text="Warning: Resetting the database is irreversible.", font=('Arial', 8, 'italic')).pack(anchor="w")
