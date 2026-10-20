"""In-window views of the actual validated batch reports and source records."""

import json
import tkinter as tk
from tkinter import ttk

BG, PANEL, INSET = "#0b1220", "#121e30", "#0e192a"
TEXT, MUTED, TEAL = "#e9eff8", "#91a3ba", "#39d9bd"


class DashboardReportViews:
    """Full-batch results, kept distinct from the animated replay cursor."""

    def __init__(self, notebook, replay, reports, money, tree_factory):
        self.notebook, self.replay, self.reports = notebook, replay, reports
        self.money, self._tree = money, tree_factory
        self._audit_values = {}
        self._trade_values = {}
        self._build_report()
        self._build_trade_tape()
        self._build_audit()
        self._build_holdings()
        self._build_inputs()

    def _tab(self, title, subtitle):
        frame = tk.Frame(self.notebook, bg=BG, padx=18, pady=16)
        frame.columnconfigure(0, weight=1)
        self.notebook.add(frame, text=title)
        tk.Label(frame, text=title, bg=BG, fg=TEXT, font=("Segoe UI", 20, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(frame, text=subtitle, bg=BG, fg=MUTED, font=("Segoe UI", 10),
                 justify="left", anchor="w", wraplength=1350).grid(row=1, column=0, sticky="ew", pady=(6, 14))
        return frame

    def _batch_caption(self):
        total = self.reports.summary["totals"]
        return (f"Full validated batch: {total['total']} orders · {total['settled']} settled · "
                f"{total['pending']} pending · {total['rejected']} rejected · {len(self.reports.trade_pairs)} matched pairs. "
                "These final results stay available while the Replay tab animates the same batch.")

    @staticmethod
    def _text(parent, row=0, column=0, height=16, wrap="none"):
        frame = tk.Frame(parent, bg=INSET)
        frame.grid(row=row, column=column, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        text = tk.Text(frame, bg=INSET, fg=TEXT, insertbackground=TEXT,
                       selectbackground="#29415b", relief="flat", padx=12, pady=10,
                       font=("Consolas", 10), wrap=wrap, height=height, width=35)
        text.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        text.configure(state="disabled")
        return text

    @staticmethod
    def _set_text(widget, content):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")

    def _build_report(self):
        frame = self._tab("Full Report", self._batch_caption())
        frame.rowconfigure(3, weight=1)
        strip = tk.Frame(frame, bg=PANEL, padx=12, pady=10)
        strip.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        rejected = "   |   ".join(f"{item['reason_code']}: {item['count']}" for item in self.reports.rejections)
        tk.Label(strip, text="Rejection breakdown   " + rejected, bg=PANEL, fg=TEAL,
                 font=("Segoe UI", 10), anchor="w", wraplength=1300).pack(fill="x")
        self.report_text = self._text(frame, row=3)
        self._set_text(self.report_text, self.reports.report_text)

    def _build_trade_tape(self):
        frame = self._tab("Trade Tape", self._batch_caption() + " Each row is one executed pair, counted once.")
        frame.rowconfigure(3, weight=1)
        tools = tk.Frame(frame, bg=BG)
        tools.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        tk.Label(tools, text="Find symbol, client or order", bg=BG, fg=MUTED).pack(side="left", padx=(0, 10))
        self.trade_search_var = tk.StringVar()
        ttk.Entry(tools, textvariable=self.trade_search_var, width=35).pack(side="left")
        self.trade_count_var = tk.StringVar()
        tk.Label(tools, textvariable=self.trade_count_var, bg=BG, fg=TEAL).pack(side="right")
        self.trade_tree = self._tree(frame, (
            ("pair", "Pair", 45), ("step", "Step", 45), ("symbol", "Stock", 75),
            ("buy", "BUY order", 125), ("buyer", "Buyer", 95), ("sell", "SELL order", 125),
            ("seller", "Seller", 95), ("qty", "Quantity", 75), ("price", "Exec / INR", 110),
            ("value", "Trade value / INR", 145), ("time", "Batch time / UTC", 190),
        ), row=3, height=20)
        for number, pair in enumerate(self.reports.trade_pairs, 1):
            values = (pair["pair"], pair["step"], pair["stock_code"], pair["buy_order_id"], pair["buyer"],
                      pair["sell_order_id"], pair["seller"], pair["quantity"],
                      self.money(pair["execution_price_paise"]), self.money(pair["notional_paise"]), pair["as_of"])
            iid = f"t{number}"
            self._trade_values[iid] = values
            self.trade_tree.insert("", "end", iid=iid, values=values, tags=("SETTLED",))
        self.trade_search_var.trace_add("write", self._filter_trades)
        self._filter_trades()

    def _filter_trades(self, *_):
        query = self.trade_search_var.get().strip().casefold()
        count = 0
        for iid, values in self._trade_values.items():
            if not query or query in " ".join(map(str, values)).casefold():
                self.trade_tree.move(iid, "", "end")
                count += 1
            else:
                self.trade_tree.detach(iid)
        self.trade_count_var.set(f"{count} / {len(self._trade_values)} matched pairs")

    def _build_audit(self):
        frame = self._tab("Audit & Settlement", self._batch_caption() + " Browse parsed records or the exact JSON and fixed-width outputs.")
        frame.rowconfigure(3, weight=3)
        frame.rowconfigure(5, weight=1)
        tools = tk.Frame(frame, bg=BG)
        tools.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.audit_mode_var = tk.StringVar(value="Parsed audit")
        mode = ttk.Combobox(tools, textvariable=self.audit_mode_var, state="readonly", width=21,
                            values=("Parsed audit", "JSON Lines", "Audit fixed-width", "Settlement fixed-width"))
        mode.pack(side="left", padx=(0, 10))
        mode.bind("<<ComboboxSelected>>", self._audit_mode_changed)
        self.audit_status_var = tk.StringVar(value="ALL")
        status = ttk.Combobox(tools, textvariable=self.audit_status_var, state="readonly", width=12,
                              values=("ALL", "SETTLED", "REJECTED", "PENDING"))
        status.pack(side="left", padx=(0, 10))
        status.bind("<<ComboboxSelected>>", self._filter_audit)
        self.audit_search_var = tk.StringVar()
        ttk.Entry(tools, textvariable=self.audit_search_var, width=30).pack(side="left")
        tk.Label(tools, text="  Search order, client, symbol or reason", bg=BG, fg=MUTED).pack(side="left")
        self.audit_count_var = tk.StringVar()
        tk.Label(tools, textvariable=self.audit_count_var, bg=BG, fg=TEAL).pack(side="right")
        self.audit_container = tk.Frame(frame, bg=BG)
        self.audit_container.grid(row=3, column=0, sticky="nsew")
        self.audit_container.columnconfigure(0, weight=1)
        self.audit_container.rowconfigure(0, weight=1)
        self.audit_parsed_frame = tk.Frame(self.audit_container, bg=BG)
        self.audit_parsed_frame.grid(row=0, column=0, sticky="nsew")
        self.audit_parsed_frame.columnconfigure(0, weight=1)
        self.audit_parsed_frame.rowconfigure(0, weight=1)
        self.audit_tree = self._tree(self.audit_parsed_frame, (
            ("row", "#", 40), ("order", "Order", 120), ("client", "Client", 90), ("symbol", "Stock", 75),
            ("side", "Side", 45), ("qty", "Qty", 65), ("status", "Status", 90), ("reason", "Reason", 80),
            ("limit", "Limit / INR", 105), ("reference", "Reference / INR", 120),
            ("execution", "Exec / INR", 105), ("time", "Order time / UTC14", 165),
        ), row=0, height=13)
        self.audit_raw_frame = tk.Frame(self.audit_container, bg=BG)
        self.audit_raw_frame.grid(row=0, column=0, sticky="nsew")
        self.audit_raw_frame.columnconfigure(0, weight=1)
        self.audit_raw_frame.rowconfigure(0, weight=1)
        self.audit_raw_text = self._text(self.audit_raw_frame)
        self.audit_raw_frame.grid_remove()
        for number, record in enumerate(self.reports.audit_documents, 1):
            values = (number, record["order_id"], record["client_id"], record["stock_code"], record["side"],
                      record["quantity"], record["status"], record["reason_code"],
                      self.money(record["requested_price_paise"]), self.money(record["reference_price_paise"]),
                      self.money(record["execution_price_paise"]), record["order_timestamp"])
            iid = f"a{number}"
            self._audit_values[iid] = values
            self.audit_tree.insert("", "end", iid=iid, values=values, tags=(record["status"],))
        tk.Label(frame, text="Selected record — full explanation, JSON fields and original audit/settlement bytes", bg=BG, fg=MUTED,
                 anchor="w").grid(row=4, column=0, sticky="ew", pady=(10, 5))
        self.audit_detail_text = self._text(frame, row=5, height=7)
        self.audit_tree.bind("<<TreeviewSelect>>", self._audit_selected)
        self.audit_search_var.trace_add("write", self._filter_audit)
        self._filter_audit()
        self._set_text(self.audit_detail_text, "Select any record to inspect all fields, its explanation, and both fixed-width outputs.")

    def _filter_audit(self, *_):
        query = self.audit_search_var.get().strip().casefold()
        status = self.audit_status_var.get()
        count = 0
        for iid, values in self._audit_values.items():
            if (status == "ALL" or values[6] == status) and (not query or query in " ".join(map(str, values)).casefold()):
                self.audit_tree.move(iid, "", "end")
                count += 1
            else:
                self.audit_tree.detach(iid)
        self.audit_count_var.set(f"{count} / {len(self._audit_values)} orders")

    def _audit_mode_changed(self, _event=None):
        mode = self.audit_mode_var.get()
        if mode == "Parsed audit":
            self.audit_raw_frame.grid_remove()
            self.audit_parsed_frame.grid()
            return
        if mode == "JSON Lines":
            content = self.reports.jsonl_text
        elif mode == "Audit fixed-width":
            content = "\n".join(self.reports.audit_records) + ("\n" if self.reports.audit_records else "")
        else:
            content = "\n".join(self.reports.settlement_records) + ("\n" if self.reports.settlement_records else "")
        self._set_text(self.audit_raw_text, content)
        self.audit_parsed_frame.grid_remove()
        self.audit_raw_frame.grid()

    def _audit_selected(self, _event=None):
        selected = self.audit_tree.selection()
        if not selected:
            return
        index = int(selected[0][1:]) - 1
        record = self.reports.audit_documents[index]
        content = (json.dumps(record, indent=2, ensure_ascii=False) + "\n\nAUDIT (110 characters):\n" +
                   self.reports.audit_records[index] + "\n\nSETTLEMENT (110 characters):\n" +
                   self.reports.settlement_records[index])
        self._set_text(self.audit_detail_text, content)

    def _build_holdings(self):
        frame = self._tab("Holdings", self._batch_caption() + " Final quantities and valuations; pending reservations have expired.")
        frame.rowconfigure(3, weight=1)
        frame.rowconfigure(5, weight=1)
        seed = {(row["client_id"], row["stock_code"]): row["quantity"] for row in self.replay.state(0)["holdings"]}
        known = sum(row["valuation_paise"] or 0 for row in self.reports.holdings)
        missing = sum(row["valuation_paise"] is None for row in self.reports.holdings)
        caption = f"Known portfolio reference value: {self.money(known)}   |   {len(self.reports.holdings)} positions   |   {missing} unavailable valuations"
        tk.Label(frame, text=caption, bg=PANEL, fg=TEAL, padx=12, pady=12, anchor="w").grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self.report_holdings_tree = self._tree(frame, (
            ("client", "Client", 130), ("symbol", "Stock", 100), ("seed", "Seed qty", 90),
            ("delta", "Settled change", 120), ("final", "Final qty", 90),
            ("price", "Reference / INR", 150), ("valuation", "Final valuation / INR", 190),
        ), row=3, height=14)
        for number, holding in enumerate(self.reports.holdings, 1):
            initial = seed.get((holding["client_id"], holding["stock_code"]), 0)
            self.report_holdings_tree.insert("", "end", iid=f"p{number}", values=(holding["client_id"], holding["stock_code"], initial,
                holding["quantity"] - initial, holding["quantity"], self.money(holding["reference_price_paise"]), self.money(holding["valuation_paise"])))
        tk.Label(frame, text="Exact HOLDOUT records (56 characters each)", bg=BG, fg=MUTED, anchor="w").grid(row=4, column=0, sticky="ew", pady=(10, 5))
        self.holdings_raw_text = self._text(frame, row=5, height=6)
        self._set_text(self.holdings_raw_text, "\n".join(self.reports.holdings_records) + ("\n" if self.reports.holdings_records else ""))

    def _build_inputs(self):
        frame = self._tab("Inputs & Checks", "Actual engine/converter/report/reconciliation results, source hashes and exact input snapshots. All content is visible here; no external report viewer is required.")
        frame.rowconfigure(2, weight=1)
        body = tk.Frame(frame, bg=BG)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)
        left = tk.Frame(body, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        left.rowconfigure(3, weight=2)
        tk.Label(left, text="Reconciliation checks", bg=BG, fg=TEXT, font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 7))
        self.checks_tree = self._tree(left, (("check", "Check", 290), ("result", "Result", 80)), row=1, height=7)
        for number, (check, result) in enumerate(self.reports.checks.items()):
            self.checks_tree.insert("", "end", iid=f"c{number}", values=(check.replace("_", " ").title(), result), tags=("SETTLED" if result == "PASS" else "REJECTED",))
        tk.Label(left, text="Complete summary / manifest JSON", bg=BG, fg=MUTED).grid(row=2, column=0, sticky="w", pady=(12, 5))
        self.summary_text = self._text(left, row=3, height=12)
        self._set_text(self.summary_text, json.dumps(self.reports.summary, indent=2) + "\n")
        right = tk.Frame(body, bg=BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        selector = tk.Frame(right, bg=BG)
        selector.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        tk.Label(selector, text="Input dataset", bg=BG, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(side="left")
        self.input_kind_var = tk.StringVar(value="orders")
        combo = ttk.Combobox(selector, textvariable=self.input_kind_var, values=("orders", "holdings", "prices"), state="readonly", width=13)
        combo.pack(side="right")
        combo.bind("<<ComboboxSelected>>", self._input_changed)
        self.inputs_tree = self._tree(right, (("row", "#", 45), ("length", "Length", 65), ("raw", "Original fixed-width record", 700)), row=1, height=20)
        self.input_count_var = tk.StringVar()
        tk.Label(right, textvariable=self.input_count_var, bg=BG, fg=MUTED, wraplength=720,
                 justify="left", anchor="w").grid(row=2, column=0, sticky="ew", pady=(7, 0))
        self._input_changed()

    def _input_changed(self, _event=None):
        self.inputs_tree.delete(*self.inputs_tree.get_children())
        kind = self.input_kind_var.get()
        rows = self.reports.inputs[kind]
        for number, raw in enumerate(rows, 1):
            self.inputs_tree.insert("", "end", iid=f"i{number}", values=(number, len(raw), raw))
        source = getattr(self.replay, f"{kind}_path")
        self.input_count_var.set(f"{len(rows)} {kind} records · original padding preserved · snapshot hashes in manifest\nOriginal source path: {source}")
