# Record layouts and JSON schema

All positions are one-based and inclusive. Local files contain ASCII records separated by LF or CRLF; the newline is not part of the record length. z/OS files are FB datasets encoded in the site's configured EBCDIC code page. Export explicitly to newline-delimited ASCII before Python conversion. Do not trim field padding or binary-concatenate FB records.

Identifiers use uppercase ASCII A–Z, 0–9, `_` and `-`, left aligned with trailing spaces. No leading or embedded spaces. Numeric fields are unsigned, zero-padded ASCII digits locally and ordinary DISPLAY digits in z/OS records. Money is integer INR paise. All timestamps are UTC `YYYYMMDDhhmmss`, real calendar dates with years 1601–9999.

## ORDERS: 59 characters

| Field | Start | End | Width |
| --- | ---: | ---: | ---: |
| Order ID | 1 | 12 | 12 |
| Client ID | 13 | 20 | 8 |
| Stock code | 21 | 28 | 8 |
| Side (`B`/`S`) | 29 | 29 | 1 |
| Quantity | 30 | 35 | 6 |
| Limit price, paise | 36 | 45 | 10 |
| Order timestamp | 46 | 59 | 14 |

Quantity and limit price must be positive. Local short, long or malformed records are auditable `DATA001` classifications. Native local COBOL buffers lines up to 32,760 characters; longer physical records are outside its supported interface. FB59 uploads pad short records, so the sample `SHORT` still fails basic fields after padding. Never truncate an oversized order into a valid record during upload.

## HOLDINGS seed: 26 characters

| Field | Start | End | Width |
| --- | ---: | ---: | ---: |
| Client ID | 1 | 8 | 8 |
| Stock code | 9 | 16 | 8 |
| Seed quantity | 17 | 26 | 10 |

Zero is permitted. Duplicate client/stock entries, malformed fields or capacity overflow fail the batch. Inputs are never modified.

## PRICES replay: 32 characters

| Field | Start | End | Width |
| --- | ---: | ---: | ---: |
| Stock code | 1 | 8 | 8 |
| Observation timestamp | 9 | 22 | 14 |
| Reference price, paise | 23 | 32 | 10 |

Prices must be positive and sorted by ASCII stock code then timestamp, with no duplicate stock/timestamp. The engine may load quotes outside an order's time range but never selects a future quote. The CSV importer additionally rejects quotes after its explicitly requested replay cutoff. An empty replay is permitted by the engine and yields `PRICE01` for otherwise valid orders; the importer rejects an empty source.

## SETTLE and AUDIT: 110 characters

The two output record contracts are intentionally identical.

| Field | Start | End | Width |
| --- | ---: | ---: | ---: |
| Original order fields | 1 | 59 | 59 |
| Status | 60 | 67 | 8 |
| Reason code | 68 | 74 | 7 |
| Historical reference price | 75 | 84 | 10 |
| Actual simulated execution price | 85 | 94 | 10 |
| Quantity × reference price | 95 | 110 | 16 |

Statuses are padded `SETTLED`, `PENDING` or `REJECTED`. Reasons are padded to seven characters: `OK000`, `PEND01`, `DUP001`, `HOLD01`, `PRICE01`, `DATA001`, `SIDE001`. See `stkcp/contracts.py` and REXX `Explain` for deterministic explanations. Unknown codes retain their text and receive a safe explanation; a report with unknown reasons fails validation.

Zero reference means missing/stale/unavailable. Zero execution means unexecuted. A price-band rejection retains a valid reference and notional. DATA/DUP/SIDE failures occur before reference lookup and contain zero derived fields. Malformed original numeric fields are retained, rather than being coerced into fictitious valid orders. Reference notional values the requested quantity and is not a settlement cash transfer.

## HOLDOUT: 56 characters

| Field | Start | End | Width |
| --- | ---: | ---: | ---: |
| Client ID | 1 | 8 | 8 |
| Stock code | 9 | 16 | 8 |
| Final quantity | 17 | 26 | 10 |
| Final reference price | 27 | 36 | 10 |
| Final quantity × reference | 37 | 56 | 20 |

Seed entries retain their input order; valid new buyers are appended in order of validation. This includes pending buyers with zero quantity. With an unavailable reference, both price and valuation fields are zero; consumers must label valuation unavailable. With a known reference, a zero holding has a known zero valuation.

## JSON Lines schema version 1

One independently parseable UTF-8 JSON object per audit record. Fields:

| Field | JSON type / meaning |
| --- | --- |
| `schema_version` | Integer `1` |
| `order_id`, `client_id`, `stock_code`, `side` | Strings with trailing field padding removed |
| `quantity` | Integer, or null if malformed |
| `order_timestamp` | Original UTC14 string, null if blank; may be invalid on DATA001 |
| `requested_price_paise` | Integer, or null if malformed |
| `status`, `reason_code`, `explanation` | Preserved classification and deterministic explanation |
| `reference_price_paise` | Positive integer or null |
| `execution_price_paise` | Positive integer for settled orders; otherwise null |
| `reference_notional_paise` | Integer when reference available; otherwise null |
| `raw_order` | Exactly 59 original characters, truncated/padded for malformed input |

`json.dumps` handles escaping; the converter validates by slices rather than splitting. A malformed audit record fails conversion with its line number and preserves the previous destination. Temporary files are replaced only after all records pass.
