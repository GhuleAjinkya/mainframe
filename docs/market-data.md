# Offline market data and provenance

The entire delivered demonstration runs locally. It has no market-data network
client, cloud account, credentials, API key, external service, streaming library,
or automatic download. No IBM Cloud or exchange service was accessed. The
attached specification's requirement to obtain real historical prices remains
unverified: no real historical export was supplied, and the user's local-only
instruction takes priority. Historical values must never be described as live.

## Included synthetic fixture

`data/prices.txt`, `data/orders.txt`, `data/holdings.txt` and
`data/synthetic-history.csv` contain invented coursework data. `ALPHA`, `BETA`
and `FUTURE` are fictional instruments. These values are not market observations.
`data/market-data-metadata.json` records this explicitly, with no source provider
or retrieval time and a SHA-256 of the exact LF-terminated price file. The
synthetic fixture was prepared for this project on 2026-10-19. Its January 2026
timestamps are simulated UTC times, with no assertion of a real trading calendar.

The synthetic fallback is selected explicitly by the local demonstration's data
paths. The importer never falls back to it. Invalid or unavailable source data
causes a visible failure and no published snapshot.

The fourteen orders produce the following independently reasoned classifications:

| Lines | Expected result | Reason |
| --- | --- | --- |
| 1–2 | SETTLED / OK000 | ALPHA BUY/SELL pair, quantity 10, seller price 10,100 paise |
| 3–4 | SETTLED / OK000 | BETA SELL/BUY pair, quantity 5, seller price 20,300 paise |
| 5 | PENDING / PEND01 | ALPHA quantity 7 has no compatible SELL |
| 6 | REJECTED / HOLD01 | SELL quantity 999 exceeds remaining seeded availability |
| 7 | REJECTED / DUP001 | A-BUY1 was already seen |
| 8 | REJECTED / SIDE001 | X is not a supported side |
| 9 | REJECTED / PRICE01 | Limit 20,000 falls outside ALPHA's 9,180–11,220 range |
| 10 | REJECTED / DATA001 | Nonnumeric quantity |
| 11 | REJECTED / DATA001 | Deliberately short record, with missing basic fields |
| 12 | REJECTED / PRICE01 | FUTURE has no price at or before this order |
| 13 | REJECTED / DATA001 | February 30 is not a valid date |
| 14 | PENDING / PEND01 | BETA quantity 6 has no compatible BUY |

Expected totals: 14 input rows, 4 settled, 2 pending, 8 rejected, business RC0.
`data/expected-results.json` contains per-line reference prices, execution prices,
reference notionals and six final holding entries. The pending BUYER3 holding has
zero shares and a known zero valuation. FUTCLNT's two FUTURE shares have unknown
valuation because their only observation is later than the valuation cutoff.

Run `python scripts/generate_fixtures.py` to reproduce the checked-in inputs and
the manually reasoned expectation document. This script does not call settlement
logic. Tests compare the expectations with actual pipeline artifacts; the
expectations are not generated from a run's results.

## Importing a supplied local historical CSV

`stkcp/market_data.py` isolates the source-format adapter from settlement. Its
`YahooExportCsvAdapter` reads an existing UTF-8 historical CSV with these column
names: `Date,Open,High,Low,Close`. Optional `Volume`, `Symbol`, `Currency` and
`Adj Close` columns are understood as documented below. The name describes a
CSV schema; the project has not authenticated a Yahoo export, checked current
provider access terms, or asserted redistribution permission.

For real data, the operator must obtain a permitted INR historical export
separately, check its provider's access terms and coursework/redistribution
permissions, record its actual source retrieval time, and identify its symbol
and session interpretation. No source export containing real data is checked in.
Do not commit an export unless permission allows it. A file name or manually
entered provider name is not evidence of authenticity; the manifest records
`real_data_provenance_verified_by_software: false`.

An existing local CSV can be imported with PowerShell. This example deliberately
uses the supplied **synthetic** CSV; its declared retrieval timestamp is the local
import time, not evidence of a provider download:

```powershell
$importedAt = (Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss')
python -m stkcp.market_data `
  --input data/synthetic-history.csv `
  --output-dir output/imported-synthetic `
  --symbol ALPHA --provider-symbol ALPHA `
  --provider 'Synthetic coursework CSV' --data-kind synthetic --currency INR `
  --retrieved-at $importedAt `
  --start-date 2026-01-01 --end-date 2026-01-02 `
  --session-close-utc 090000 `
  --market-session 'Synthetic UTC observations; no exchange calendar' `
  --as-of 20260102100000
```

For a genuine export, change the input, provider, symbols, range, session,
cutoff and actual retrieval timestamp, and use `--data-kind historical_export`.
The historical replay cutoff can be earlier than retrieval: it specifies the
simulation's information boundary, not today's clock. The source retrieval
timestamp cannot be in the future, and source observations cannot postdate their
declared retrieval. The output directory must be new; select a
different name for another import. CLI usage errors return RC2; data/I/O failures
return RC12. Importing data is optional and requires only Python's standard
library.

Each successful import publishes a complete directory containing:

- `source.csv`: unchanged original bytes, preserved for provenance.
- `prices.txt`: sorted fixed-width records for the selected internal symbol.
- `market-data-metadata.json`: source and replay hashes, declared provider,
  provider/internal symbols, retrieval UTC time, date range, replay cutoff,
  currency, session interpretation, adjustment policy and record count.

All rows are validated before any output directory is published. Files are
written in a temporary sibling directory, then the directory is renamed on the
same filesystem. Existing output directories are refused. Failure removes the
temporary directory; no successful snapshot is published. This provides atomic
visibility, rather than a guarantee against storage-device failure.

## Validation and price interpretation

- Internal symbols must be 1–8 uppercase ASCII letters, digits, underscore or
  hyphen. The provider symbol is explicit; if `Symbol` is present, every row must
  match it. Without that column, metadata admits that symbol identity was
  operator-supplied and could not be confirmed from the CSV.
- CSV `Date` must be an exact, real `YYYY-MM-DD` date in the explicitly requested
  inclusive range. Duplicates are rejected. No rows are silently trimmed to the
  range. Missing required fields, duplicate headers, inconsistent row widths and
  empty sources are errors. Maximum snapshot size is 5,000 observations.
- Date-only rows are combined with the explicit `--session-close-utc HHMMSS` time
  to produce contract UTC14 timestamps. The source date must map to that UTC
  calendar date. The operator must normalize exports from sessions crossing UTC
  dates before importing; automatic exchange calendars, timezone conversion and
  daylight-saving inference are not implemented. Do not pretend a daily close
  existed earlier in that day.
- Open, High, Low and Close must be positive decimal INR prices representable
  exactly as integer paise within ten digits. Decimal arithmetic rejects
  fractional paise instead of rounding. High/Low must enclose Open and Close.
  Optional Volume must be a nonnegative integer; optional Currency must be INR.
  Currency conversion is not implemented.
- Only unadjusted `Close` supplies the reference. `Adj Close` is ignored,
  including its numeric precision, and this is recorded in metadata. It does not
  affect settlement. The project does not model splits, dividends or adjusted
  holdings, so avoid simulation windows containing such corporate actions.
- Any source observation later than the replay cutoff fails import. The latest
  quote must be at most seven days old relative to that cutoff; older history
  within the requested range is retained for earlier orders. Calendar holidays
  and missing trading sessions are not inferred. Missing numeric values and a
  stale final observation are errors; a weekend gap is not itself an error.

The fixed price record is exactly 32 ASCII bytes: symbol 1–8, UTC14 observation
timestamp 9–22, positive ten-digit integer paise 23–32. The local file has one LF
after each record. z/OS FB32 datasets contain the records without LF bytes. Rows
are sorted by symbol and timestamp; duplicate symbol/timestamp pairs are fatal.
No value is an executed trade merely because it appears in this file.

Settlement independently selects the latest observation at or before each
simulated order time, with a maximum age of seven days. A snapshot can contain
later observations for other replay times; these must not affect an earlier
order or valuation. The checked-in FUTURE instrument deliberately tests this.
Limits must lie inclusively within 90–110% of the reference. Execution occurs
only for an actual compatible batch pair, at the seller's limit. See the shared
implementation contract for matching and holdings reservation rules.

<a id="planned-live-ingestion"></a>

## Planned / not implemented

If network use is authorized later, a separate opt-in Python acquisition adapter
could write the same local source/metadata format. It would need a provider
offering licensed historical access, separately stored credentials, measured rate
limits and retry handling. Its failure must never silently create synthetic
prices. No download function is currently available.

A future streaming adapter would first verify whether a licensed streaming or
polling API exists and whether USS can reach it. If USS cannot, an authorized
external ingestion process could transfer a validated file. It would timestamp
observations, reconnect with bounded backoff, reject duplicates/out-of-order
events according to a documented policy, detect stale updates, buffer safely and
publish snapshots only at complete boundaries. Quotes would remain distinct
from executable orders. COBOL/JCL would continue consuming ordinary files, with
no continuously open network connection, and every stream capture would support
deterministic replay. None of these services, credentials or streaming libraries
is part of the local runtime.
