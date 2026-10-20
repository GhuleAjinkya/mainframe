# Shared implementation contract

This file defines the local milestone. No network calls or cloud access are required or performed. Fixed records are ASCII, with a newline only in local text files. z/OS uses FB datasets without newline bytes. All money is integer INR paise. Times are UTC `YYYYMMDDhhmmss`.

## Layouts (one-based, inclusive)

Orders, 59 bytes: order_id 1–12, client_id 13–20, stock_code 21–28, side 29, quantity 30–35 (six digits), limit_price 36–45 (ten digits), timestamp 46–59.

Holdings seed, 26 bytes: client_id 1–8, stock_code 9–16, quantity 17–26 (ten digits).

Prices, 32 bytes: stock_code 1–8, timestamp 9–22, price 23–32 (ten digits). Prices must be positive, unique by symbol/time, and sorted by symbol then time. At most 5,000 prices.

Audit and settlement, 110 bytes: original order fields 1–59 (invalid records truncated/padded for tracing), status 60–67 (eight characters), reason_code 68–74 (seven), reference_price 75–84 (ten digits, zero if unavailable), execution_price 85–94 (ten digits, zero unless settled), reference_notional 95–110 (sixteen digits, quantity times reference). A DATA001 record may retain nonnumeric original fields; the converter emits null for those numeric values and includes raw_order. Status/reason pairs: SETTLED/OK000; PENDING/PEND01; REJECTED/DUP001,HOLD01,PRICE01,DATA001,SIDE001. Missing/stale reference data is PRICE01. Zero output reference/execution means unavailable in JSON (null).

Final holdings, 56 bytes: client_id 1–8, stock_code 9–16, quantity 17–26 (ten), reference_price 27–36 (ten), valuation 37–56 (twenty). Valued at latest price at/before the maximum structurally valid order timestamp, including business rejections, with the same seven-day freshness limit. A zero price means unavailable (not a zero market value); valuation zero must be labelled unavailable too. With no structurally valid orders all valuations are unavailable. Output order is seeded entries followed by new buyers after successful price validation, including pending buyers.

## Deterministic rules

Identifiers: 1–width uppercase ASCII A–Z, digits, underscore or hyphen, followed only by padding spaces. Orders require positive quantity and limit, real calendar timestamps (years 1601–9999). Validate length/basic fields, duplicate ID, side, price, then holdings. First structurally valid occurrence reserves an ID, even if later rejected for side/price/holdings; malformed rows do not reserve IDs. Valid sides B/S. Latest historical reference must be at/before order time and no older than seven days (604800 seconds). Limit must lie inclusively within 90–110% of reference, checked with integer arithmetic.

SELL validation reserves quantity from seeded holdings in input sequence. Earlier valid pending SELL orders consume availability for this batch; purchases cannot fund another SELL in the same batch. Rejected rows reserve no holdings. This conservative policy prevents overcommitment and is deliberately independent of matching. Final holdings change only for settled pairs; reservations on pending orders expire at batch end.

After validation, scan valid pending orders in input sequence. Match the earliest later pending opposite-side order with the same stock and exact quantity, different client, and BUY limit >= SELL limit. No partial fills. Execute both at the seller limit. Do not require identical timestamps. This is batch clearing; timestamps govern reference selection, not event-by-event execution. Every unmatched valid order is PENDING/PEND01. Preserve output order. Update final seeded holdings for SELL and BUY once per pair. Reference notional is valuation of order quantity, not evidence of execution.

Limits: 1,000 orders, 1,000 client/stock holding entries (including new buyer entries), 5,000 prices. Overflow, malformed holdings/prices, duplicate holdings/prices, any I/O failure or holdings arithmetic overflow is fatal RC12. Business rejections and empty orders are RC0. A fatal run must not publish a successful output directory. Python converter/report validation failure is RC8; CLI usage errors RC2. Reporting compares audit with settlement byte-for-byte and count with original orders, not merely summed statuses.

COBOL DDs: ORDERS, HOLDINGS, PRICES, SETTLE, AUDIT, HOLDOUT. REXX: AUDIT, SETTLE, ORDERS; reports status totals, malformed/unknown errors safely. Python JSON conversion uses this exact layout, includes schema_version=1 and deterministic explanation mapping. Local Python is an executable reference implementation, never labelled compiled COBOL or executed REXX. Native COBOL and native REXX are optional locally; z/OS templates remain explicitly unverified.
