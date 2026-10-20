"""Native, offline Tkinter dashboard for deterministic settlement replay."""

import tkinter as tk
from tkinter import ttk

from .replay import load_replay
from .dashboard_reports import build_dashboard_reports
from .dashboard_views import DashboardReportViews


BG = "#0b1220"
PANEL = "#121e30"
INSET = "#0e192a"
BORDER = "#24354b"
TEXT = "#e9eff8"
MUTED = "#91a3ba"
TEAL = "#39d9bd"
BLUE = "#77aaff"
AMBER = "#f6bd60"
RED = "#ff8297"


def money(paise):
    if paise is None:
        return "Unavailable"
    sign = "-" if paise < 0 else ""
    whole, cents = divmod(abs(int(paise)), 100)
    return f"{sign}INR {whole:,}.{cents:02d}"


class SettlementDashboard:
    """A view over immutable engine snapshots; playback never reruns trades."""

    def __init__(self, root, replay, interval_ms=900, source_label="Local inputs · offline replay"):
        self.root, self.replay = root, replay
        self.reports = build_dashboard_reports(replay)
        self.index = 0
        self.interval_ms = interval_ms
        self.is_playing = False
        self.timer_id = None
        self._updating = False
        self._selected_row = None
        self._chart_hits = []
        self._order_cache = {}
        self._holding_cache = {}
        self._event_count = 0
        root.title("STKCP | Settlement Replay")
        root.configure(bg=BG)
        width = min(1540, root.winfo_screenwidth() - 70)
        height = min(1020, root.winfo_screenheight() - 100)
        root.geometry(f"{width}x{height}")
        root.minsize(min(1080, root.winfo_screenwidth() - 70), min(650, root.winfo_screenheight() - 100))
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._style()

        self.notebook = ttk.Notebook(root, style="Replay.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.replay_tab = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(self.replay_tab, text="Replay & Charts")
        viewport_frame = tk.Frame(self.replay_tab, bg=BG)
        viewport_frame.pack(fill="both", expand=True)
        viewport_frame.rowconfigure(0, weight=1)
        viewport_frame.columnconfigure(0, weight=1)
        self.viewport = tk.Canvas(viewport_frame, bg=BG, highlightthickness=0)
        self.viewport.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(viewport_frame, orient="vertical", command=self.viewport.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(viewport_frame, orient="horizontal", command=self.viewport.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.viewport.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        page = tk.Frame(self.viewport, bg=BG, padx=22, pady=18)
        self._page_window = self.viewport.create_window((0, 0), window=page, anchor="nw")
        self.viewport.bind("<Configure>", self._resize_viewport)
        page.bind("<Configure>", lambda _event: self.viewport.configure(scrollregion=self.viewport.bbox("all")))
        root.bind("<MouseWheel>", self._scroll_page)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(3, weight=1)
        header = tk.Frame(page, bg=BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        tk.Label(header, text="STKCP  /  SETTLEMENT LAB", bg=BG, fg=TEAL,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(header, text="Watch every order become explainable.", bg=BG, fg=TEXT,
                 font=("Segoe UI", 23, "bold")).pack(anchor="w", pady=(4, 3))
        tk.Label(header, text=source_label + "  |  Python reference engine  |  Not live market trading",
                 bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w")

        controls = self._panel(page)
        controls.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        controls.columnconfigure(5, weight=1)
        self.play_button = ttk.Button(controls, text="Play", command=self.play, style="Accent.TButton")
        self.play_button.grid(row=0, column=0, padx=(12, 6), pady=12)
        ttk.Button(controls, text="Pause", command=self.pause).grid(row=0, column=1, padx=6)
        ttk.Button(controls, text="Next event", command=self.next_step).grid(row=0, column=2, padx=6)
        ttk.Button(controls, text="Restart", command=self.restart).grid(row=0, column=3, padx=6)
        self.speed_var = tk.StringVar(value="1x")
        speed = ttk.Combobox(controls, textvariable=self.speed_var,
                             values=("0.5x", "1x", "2x", "4x", "10x", "20x"), state="readonly", width=6)
        speed.grid(row=0, column=4, padx=(12, 10))
        speed.bind("<<ComboboxSelected>>", self._speed_changed)
        ttk.Button(controls, text="Finish batch", command=self.finish_batch).grid(row=0, column=5, sticky="w", padx=8)
        self.phase_var = tk.StringVar()
        tk.Label(controls, textvariable=self.phase_var, bg=PANEL, fg=TEAL,
                 font=("Segoe UI", 10, "bold")).grid(row=0, column=6, sticky="e", padx=14)
        controls.columnconfigure(6, weight=1)
        self.progress_var = tk.DoubleVar()
        self.timeline = ttk.Scale(controls, from_=0, to=max(1, len(replay.events) - 1),
                                  variable=self.progress_var, command=self._seek)
        self.timeline.grid(row=1, column=0, columnspan=7, sticky="ew", padx=14, pady=(0, 12))

        cards = tk.Frame(page, bg=BG)
        cards.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        self.counts_vars = {}
        for index, (key, title, color) in enumerate((
            ("processed", "ORDERS REVIEWED", TEXT), ("settled", "SETTLED ORDERS", TEAL),
            ("pending", "AWAITING / PENDING", AMBER), ("rejected", "REJECTED ORDERS", RED),
            ("matched", "MATCHED PAIRS", BLUE), ("notional", "EXECUTED TRADE VALUE", TEAL),
        )):
            cards.columnconfigure(index, weight=1, uniform="cards")
            card = self._panel(cards)
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 5, 0 if index == 5 else 5))
            tk.Label(card, text=title, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=12, pady=(10, 3))
            variable = tk.StringVar()
            self.counts_vars[key] = variable
            tk.Label(card, textvariable=variable, bg=PANEL, fg=color,
                     font=("Segoe UI", 17 if key == "notional" else 23, "bold")).pack(anchor="w", padx=12, pady=(0, 10))

        body = tk.Frame(page, bg=BG)
        body.grid(row=3, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=4)
        body.rowconfigure(1, weight=5)
        chart_panel = self._panel(body)
        chart_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 7), pady=(0, 12))
        chart_panel.columnconfigure(0, weight=1)
        chart_panel.rowconfigure(1, weight=1)
        chart_head = tk.Frame(chart_panel, bg=PANEL)
        chart_head.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 3))
        tk.Label(chart_head, text="Prices through the replay", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        self.symbol_var = tk.StringVar(value=replay.symbols[0] if replay.symbols else "")
        symbol_box = ttk.Combobox(chart_head, textvariable=self.symbol_var, values=replay.symbols,
                                  state="readonly", width=10)
        symbol_box.pack(side="right")
        symbol_box.bind("<<ComboboxSelected>>", lambda _event: self._draw_charts())
        self.price_canvas = tk.Canvas(chart_panel, bg=PANEL, highlightthickness=0, height=190)
        self.price_canvas.grid(row=1, column=0, sticky="nsew", padx=8)
        self.price_canvas.bind("<Configure>", lambda _event: self._draw_charts())
        self.price_canvas.bind("<Motion>", self._price_hover)
        self.chart_hint = tk.StringVar(value="Reference = historical quote; limit = order request; execution = a matched trade.")
        tk.Label(chart_panel, textvariable=self.chart_hint, bg=PANEL, fg=MUTED, anchor="w",
                 font=("Segoe UI", 8), wraplength=770).grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 10))

        volume_panel = self._panel(body)
        volume_panel.grid(row=0, column=1, sticky="nsew", padx=(7, 0), pady=(0, 12))
        volume_panel.columnconfigure(0, weight=1)
        volume_panel.rowconfigure(1, weight=1)
        tk.Label(volume_panel, text="Cumulative executed trade value", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 3))
        self.volume_canvas = tk.Canvas(volume_panel, bg=PANEL, highlightthickness=0, height=190)
        self.volume_canvas.grid(row=1, column=0, sticky="nsew", padx=8)
        self.volume_canvas.bind("<Configure>", lambda _event: self._draw_charts())
        tk.Label(volume_panel, text="Each matched pair is counted once. Validation is followed by batch clearing.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 8), wraplength=450, anchor="w").grid(
                     row=2, column=0, sticky="ew", padx=14, pady=(0, 10))

        order_panel = self._panel(body)
        order_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 7))
        order_panel.columnconfigure(0, weight=1)
        order_panel.rowconfigure(1, weight=1)
        tk.Label(order_panel, text="Order blotter", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 8))
        self.order_tree = self._tree(order_panel, (
            ("row", "#", 32), ("order", "Order", 104), ("symbol", "Symbol", 66),
            ("side", "Side", 43), ("qty", "Qty", 43), ("limit", "Limit / INR", 80),
            ("execution", "Exec / INR", 80), ("status", "Status", 88), ("reason", "Reason", 67),
        ), row=1, height=8)
        self.order_tree.bind("<<TreeviewSelect>>", self._order_selected)
        self.detail_var = tk.StringVar()
        tk.Label(order_panel, textvariable=self.detail_var, bg=PANEL, fg=MUTED, justify="left",
                 anchor="w", wraplength=800, font=("Segoe UI", 9)).grid(row=3, column=0, sticky="ew", padx=14, pady=(8, 12))

        right = tk.Frame(body, bg=BG)
        right.grid(row=1, column=1, sticky="nsew", padx=(7, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        holdings_panel = self._panel(right)
        holdings_panel.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        holdings_panel.columnconfigure(0, weight=1)
        holdings_panel.rowconfigure(1, weight=1)
        tk.Label(holdings_panel, text="Holdings & SELL reservations", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))
        self.holding_tree = self._tree(holdings_panel, (
            ("client", "Client", 84), ("symbol", "Symbol", 68), ("qty", "Held", 48),
            ("reserved", "Reserved", 62), ("available", "Unreserved", 70),
        ), row=1, height=5)
        self.valuation_var = tk.StringVar()
        tk.Label(holdings_panel, textvariable=self.valuation_var, bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8), anchor="w").grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 7))
        events_panel = self._panel(right)
        events_panel.grid(row=1, column=0, sticky="nsew")
        events_panel.columnconfigure(0, weight=1)
        events_panel.rowconfigure(1, weight=1)
        tk.Label(events_panel, text="Event log · select a step to revisit", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(9, 6))
        self.event_tree = self._tree(events_panel, (("step", "#", 32), ("phase", "Phase", 78), ("event", "Event", 270)), row=1, height=4)
        self.event_tree.bind("<<TreeviewSelect>>", self._event_selected)

        self.status_var = tk.StringVar()
        tk.Label(page, textvariable=self.status_var, bg=BG, fg=MUTED, anchor="w", justify="left",
                 wraplength=1450, font=("Segoe UI", 9)).grid(row=4, column=0, sticky="ew", pady=(12, 0))
        root.bind("<space>", self._toggle)
        root.bind("<Right>", self._shortcut_next)
        root.bind("<Home>", self._shortcut_restart)
        self.report_views = DashboardReportViews(self.notebook, replay, self.reports, money, self._tree)
        for attribute in ("report_text", "audit_tree", "report_holdings_tree", "checks_tree", "trade_tree", "summary_text", "inputs_tree"):
            setattr(self, attribute, getattr(self.report_views, attribute))
        self.render_state()

    def _style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TButton", font=("Segoe UI", 10), padding=(10, 7), background=BORDER, foreground=TEXT, borderwidth=0)
        style.map("TButton", background=[("active", "#354d68")])
        style.configure("Accent.TButton", background=TEAL, foreground=BG)
        style.map("Accent.TButton", background=[("active", "#83ead9")])
        style.configure("TCombobox", fieldbackground=INSET, background=BORDER, foreground=TEXT, arrowcolor=TEAL, padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", INSET)], foreground=[("readonly", TEXT)])
        style.configure("Horizontal.TScale", background=PANEL, troughcolor=INSET)
        style.configure("Replay.Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                        font=("Segoe UI", 9), rowheight=25, borderwidth=0)
        style.configure("Replay.Treeview.Heading", background=INSET, foreground=MUTED,
                        font=("Segoe UI", 8, "bold"), padding=(4, 7), relief="flat")
        style.map("Replay.Treeview", background=[("selected", "#29415b")], foreground=[("selected", "#ffffff")])
        style.map("Replay.Treeview.Heading", background=[("active", BORDER)])
        style.configure("Vertical.TScrollbar", background=BORDER, troughcolor=PANEL, borderwidth=0, arrowcolor=MUTED)
        style.configure("Horizontal.TScrollbar", background=BORDER, troughcolor=PANEL, borderwidth=0, arrowcolor=MUTED)
        style.configure("Replay.TNotebook", background=BG, borderwidth=0)
        style.configure("Replay.TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(18, 11), font=("Segoe UI", 10, "bold"))
        style.map("Replay.TNotebook.Tab", background=[("selected", BORDER)], foreground=[("selected", TEAL)])

    @staticmethod
    def _panel(parent):
        return tk.Frame(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)

    def _tree(self, parent, columns, row, height):
        container = tk.Frame(parent, bg=PANEL)
        container.grid(row=row, column=0, sticky="nsew", padx=8)
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        tree = ttk.Treeview(container, columns=[item[0] for item in columns], show="headings",
                            style="Replay.Treeview", height=height, selectmode="browse")
        for key, label, width in columns:
            tree.heading(key, text=label)
            tree.column(key, width=width, minwidth=min(width, 50), anchor="w", stretch=(key in ("event", "order", "client")))
        tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(container, orient="horizontal", command=tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        for status, color in (("QUEUED", MUTED), ("AWAITING", AMBER), ("PENDING", AMBER), ("SETTLED", TEAL), ("REJECTED", RED)):
            tree.tag_configure(status, foreground=color)
        tree.tag_configure("active", background="#20384d", font=("Segoe UI", 9, "bold"))
        return tree

    @staticmethod
    def _price_text(paise):
        return "—" if paise is None else money(paise).removeprefix("INR ")

    def render_state(self):
        state = self.replay.state(self.index)
        self._updating = True
        try:
            self.progress_var.set(self.index)
            self.phase_var.set(f"{state['phase'].upper()}  ·  STEP {self.index} / {len(self.replay.events) - 1}")
            counts = state["counts"]
            for key in ("settled", "rejected"):
                self.counts_vars[key].set(str(counts[key]))
            self.counts_vars["processed"].set(f"{counts['processed']} / {counts['total']}")
            self.counts_vars["pending"].set(str(counts["awaiting"] + counts["pending"]))
            self.counts_vars["matched"].set(str(state["executed_pairs"]))
            self.counts_vars["notional"].set(money(state["executed_notional_paise"]))
            active = set(state.get("active_rows", ()))
            for order in state["orders"]:
                iid = f"o{order['row']}"
                values = (order["row"], order["order_id"] or "(blank)", order["stock_code"], order["side"],
                          order["quantity"] if order["quantity"] is not None else "—",
                          self._price_text(order["requested_price_paise"]), self._price_text(order["execution_price_paise"]),
                          order["status"], order["reason_code"] or "—")
                tags = (order["status"], "active") if order["row"] in active else (order["status"],)
                content = (values, tags)
                if self._order_cache.get(iid) != content:
                    if self.order_tree.exists(iid):
                        self.order_tree.item(iid, values=values, tags=tags)
                    else:
                        self.order_tree.insert("", "end", iid=iid, values=values, tags=tags)
                    self._order_cache[iid] = content
            holding_keys = set()
            for number, holding in enumerate(state["holdings"]):
                iid = f"h{number}"
                holding_keys.add(iid)
                values = (holding["client_id"], holding["stock_code"], holding["quantity"], holding["reserved"], holding["available"])
                if self._holding_cache.get(iid) != values:
                    if self.holding_tree.exists(iid):
                        self.holding_tree.item(iid, values=values)
                    else:
                        self.holding_tree.insert("", "end", iid=iid, values=values)
                    self._holding_cache[iid] = values
            for iid in tuple(self._holding_cache):
                if iid not in holding_keys:
                    self.holding_tree.delete(iid)
                    del self._holding_cache[iid]
            if self._event_count > self.index + 1:
                self.event_tree.delete(*(f"e{step}" for step in range(self.index + 1, self._event_count)))
                self._event_count = self.index + 1
            for event in self.replay.events[self._event_count:self.index + 1]:
                self.event_tree.insert("", "end", iid=f"e{event['step']}", values=(event["step"], event["phase"].title(), event["title"]))
            self._event_count = self.index + 1
            self.event_tree.see(f"e{self.index}")
            value = state["known_valuation_paise"]
            suffix = "known subtotal; some prices unavailable" if not state["valuation_complete"] else "all positions valued"
            self.valuation_var.set(f"Portfolio reference value: {money(value)} · {suffix}")
            self.status_var.set(f"{state['title']} — {state['message']}")
            if active:
                row = min(active)
                self.order_tree.see(f"o{row}")
                self._selected_row = row
                symbol = state["orders"][row - 1]["stock_code"]
                if symbol in self.replay.symbols:
                    self.symbol_var.set(symbol)
            self._update_detail()
            complete = self.index == len(self.replay.events) - 1
            self.play_button.configure(text="Complete" if complete else "Play", state="disabled" if complete else "normal")
        finally:
            self._updating = False
        self._draw_charts()

    def _update_detail(self):
        state = self.replay.state(self.index)
        if self._selected_row and self._selected_row <= len(state["orders"]):
            order = state["orders"][self._selected_row - 1]
            self.detail_var.set(f"{order['order_id'] or '(blank)'} · Client {order['client_id'] or '—'} · "
                                f"Reference {money(order['reference_price_paise'])}\n{order['explanation']}")
        else:
            self.detail_var.set("Select an order for its explanation. Awaiting orders have passed validation; matching happens in the clearing phase.")

    def _order_selected(self, _event=None):
        if self._updating:
            return
        selected = self.order_tree.selection()
        if selected:
            self._selected_row = int(selected[0][1:])
            order = self.replay.state(self.index)["orders"][self._selected_row - 1]
            if order["stock_code"] in self.replay.symbols:
                self.symbol_var.set(order["stock_code"])
            self._update_detail()
            self._draw_charts()

    def _event_selected(self, _event=None):
        if self._updating:
            return
        selected = self.event_tree.selection()
        if selected and int(selected[0][1:]) != self.index:
            self._seek(selected[0][1:])

    def _draw_charts(self):
        if not hasattr(self, "volume_canvas"):
            return
        state = self.replay.state(self.index)
        canvas = self.price_canvas
        canvas.delete("all")
        self._chart_hits = []
        symbol = self.symbol_var.get()
        series = state["price_series"].get(symbol, {})
        points = [(kind, point) for kind in ("reference", "orders", "executions") for point in series.get(kind, ())]
        values = [point["price_paise"] for _kind, point in points if point["price_paise"] is not None]
        axis = self._axes(canvas, values, money_axis=True)
        if not values:
            canvas.create_text(axis[0] + 15, axis[1] + 25, text="No price observations revealed yet.\nPress Play or Next event to begin.", anchor="nw", fill=MUTED, font=("Segoe UI", 11))
        else:
            x0, y0, width, height, low, high = axis
            last_step = max(1, len(self.replay.events) - 1)
            position = lambda point: (x0 + point["step"] / last_step * width,
                                      y0 + height - (point["price_paise"] - low) / (high - low) * height)
            reference = series.get("reference", ())
            coords = [coordinate for point in reference for coordinate in position(point)]
            if len(coords) >= 4:
                canvas.create_line(*coords, fill=TEAL, width=2)
            for kind, point in points:
                x, y = position(point)
                color = TEAL if kind == "reference" else BLUE if kind == "orders" else AMBER
                radius = 4 if kind != "executions" else 6
                if kind == "orders":
                    canvas.create_rectangle(x - radius, y - radius, x + radius, y + radius, fill=PANEL, outline=color, width=2)
                else:
                    canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline=PANEL)
                self._chart_hits.append((x, y, f"{symbol} · {kind.title()} · step {point['step']} · {money(point['price_paise'])} · {point.get('time') or 'batch clearing'}"))
            legend = (("Reference", TEAL), ("Order limit", BLUE), ("Execution", AMBER))
            for index, (label, color) in enumerate(legend):
                canvas.create_text(x0 + index * 115, 13, text="● " + label, fill=color, anchor="w", font=("Segoe UI", 8))

        canvas = self.volume_canvas
        canvas.delete("all")
        past = self.replay.events[:self.index + 1]
        values = [event["executed_notional_paise"] for event in past]
        x0, y0, width, height, low, high = self._axes(canvas, values, money_axis=True, zero=True)
        coords = []
        previous_y = y0 + height
        for event in past:
            x = x0 + event["step"] / max(1, len(self.replay.events) - 1) * width
            y = y0 + height - (event["executed_notional_paise"] - low) / (high - low) * height
            if coords:
                coords.extend((x, previous_y))
            coords.extend((x, y))
            previous_y = y
        if len(coords) >= 4:
            canvas.create_line(*coords, fill=TEAL, width=2)
        if coords:
            canvas.create_oval(coords[-2] - 4, coords[-1] - 4, coords[-2] + 4, coords[-1] + 4, fill=TEAL, outline=PANEL)

    def _axes(self, canvas, values, money_axis=False, zero=False):
        width, height = max(canvas.winfo_width(), 200), max(canvas.winfo_height(), 120)
        left, top, plot_width, plot_height = 91, 32, max(50, width - 110), max(35, height - 65)
        low, high = (min(values), max(values)) if values else (0, 100)
        if zero:
            low = 0
        padding = max(10, (high - low) * 0.12)
        low = 0 if zero else max(0, low - padding)
        high += padding
        if high <= low:
            high = low + 100
        for tick in range(4):
            fraction = tick / 3
            y = top + plot_height * fraction
            value = high - (high - low) * fraction
            label = self._price_text(round(value)) if money_axis else str(round(value))
            canvas.create_line(left, y, left + plot_width, y, fill=BORDER)
            canvas.create_text(left - 8, y, text=label, anchor="e", fill=MUTED, font=("Segoe UI", 8))
        maximum = max(1, len(self.replay.events) - 1)
        for fraction in (0, 0.5, 1):
            step = round(maximum * fraction)
            canvas.create_text(left + fraction * plot_width, top + plot_height + 16, text=f"Step {step}", fill=MUTED, font=("Segoe UI", 8))
        return left, top, plot_width, plot_height, low, high

    def _price_hover(self, event):
        for x, y, text in reversed(self._chart_hits):
            if abs(event.x - x) < 9 and abs(event.y - y) < 9:
                self.chart_hint.set(text)
                return
        self.chart_hint.set("Historical reference • requested limit • matched execution. X-axis is replay step, not elapsed market time.")

    def _resize_viewport(self, event):
        # Preserve useful chart/table heights on laptop screens; scroll the page.
        self.viewport.itemconfigure(self._page_window, width=max(1080, event.width), height=max(970, event.height))
        self.viewport.configure(scrollregion=self.viewport.bbox("all"))

    def _scroll_page(self, event):
        if self.notebook.select() == str(self.replay_tab) and not isinstance(event.widget, (ttk.Treeview, ttk.Combobox)):
            self.viewport.yview_scroll(-int(event.delta / 120), "units")

    def _seek(self, value):
        if self._updating:
            return
        self.pause()
        self.index = max(0, min(len(self.replay.events) - 1, int(float(value))))
        self.render_state()

    def _delay(self):
        return max(10, int(self.interval_ms / float(self.speed_var.get().rstrip("x"))))

    def _schedule(self):
        if self.is_playing and self.timer_id is None:
            self.timer_id = self.root.after(self._delay(), self._tick)

    def _tick(self):
        self.timer_id = None
        if not self.is_playing:
            return
        if self.index < len(self.replay.events) - 1:
            self.index += 1
            self.render_state()
        if self.index >= len(self.replay.events) - 1:
            self.pause()
        else:
            self._schedule()

    def play(self):
        if self.index >= len(self.replay.events) - 1:
            self.pause()
            return
        self.is_playing = True
        self._schedule()

    def pause(self):
        self.is_playing = False
        if self.timer_id is not None:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None

    def next_step(self):
        self.pause()
        if self.index < len(self.replay.events) - 1:
            self.index += 1
            self.render_state()

    def restart(self):
        self.pause()
        self.index = 0
        self._selected_row = None
        self.render_state()

    def finish_batch(self):
        self.pause()
        self.index = len(self.replay.events) - 1
        self.render_state()

    def _speed_changed(self, _event=None):
        if self.is_playing:
            self.pause()
            self.play()

    def _toggle(self, _event=None):
        if self.notebook.select() != str(self.replay_tab):
            return
        self.pause() if self.is_playing else self.play()
        return "break"

    def _shortcut_next(self, _event=None):
        if self.notebook.select() == str(self.replay_tab):
            self.next_step()
            return "break"

    def _shortcut_restart(self, _event=None):
        if self.notebook.select() == str(self.replay_tab):
            self.restart()
            return "break"

    def close(self):
        self.pause()
        self.root.destroy()


def launch_dashboard(*, orders, holdings, prices, interval_ms=80):
    replay = load_replay(orders, holdings, prices)
    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise RuntimeError(f"Tkinter could not open a desktop window: {error}") from error
    from pathlib import Path
    data = Path(__file__).resolve().parents[1] / "data"
    is_fixture = any(all(Path(path).resolve() == (directory / f"{name}.txt").resolve() for name, path in (("orders", orders), ("holdings", holdings), ("prices", prices))) for directory in (data, data / "dashboard-demo"))
    source = "Synthetic sample · offline replay" if is_fixture else "Custom local inputs · offline replay"
    try:
        SettlementDashboard(root, replay, interval_ms=interval_ms, source_label=source)
        root.mainloop()
    except tk.TclError as error:
        raise RuntimeError(f"Tkinter dashboard could not run: {error}") from error
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
    return 0
