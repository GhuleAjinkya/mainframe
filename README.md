# Stock Trading Settlement with Explainable Reconciliation

An executable, fully offline coursework prototype with COBOL settlement source, dataset-based REXX reporting, JCL templates, a Python audit converter, and a locally runnable Python reference engine. It uses synthetic clients and prices. No IBM account, network service, API key, database, or third-party Python package is required.

The requested local implementation is runnable now. Native COBOL compilation, native REXX execution, and z/OS jobs have **not** been verified: this machine has no available COBOL compiler or REXX runtime, and no IBM system was accessed. The original document's z/OS milestone checklist therefore remains open. See [validation observations](docs/validation.md).

## Run on Windows with PowerShell

### 1. Open the project folder

Open PowerShell or the PowerShell terminal in your editor and run:

```powershell
Set-Location -LiteralPath 'C:\Users\Arya\Documents\ChatGPT\Mainframe'
python --version
```

Python 3.10 or later is required. Python 3.14.7 was used for the saved local validation. If you move the project, change the folder path above. Run commands from this source directory so the `stkcp` package and sample files can be found. No `pip install`, virtual environment, IBM login, Docker, WSL, or internet connection is required for the default demo.

If `python` is unavailable or opens the Microsoft Store, try the installed Windows launcher:

```powershell
py -3 --version
py -3 -m stkcp demo
```

Use `py -3` in place of `python` in the remaining commands if that is your working interpreter. On the development machine, Python can also be invoked explicitly with `& 'C:\Python314\python.exe'`; that path is specific to this machine.

### 2. Run the offline demonstration

```powershell
python -m stkcp demo
$LASTEXITCODE
```

The command explicitly selects the checked-in **synthetic** fixture and uses the Python reference settlement engine. It runs settlement, JSON conversion, reporting, and independent holdings reconciliation locally. It does not invoke native COBOL, native REXX, or JCL.

Expected business result:

```text
RC0 TOTAL=14 SETTLED=4 PENDING=2 REJECTED=8 BALANCE=PASS
Artifacts: ...\build\runs\run-0001
```

`$LASTEXITCODE` should be `0`. Four settled records represent **two matched BUY/SELL pairs**. Pending orders and business rejections are expected outcomes, so they do not make the batch fail.

Each invocation creates a new `build/runs/run-NNNN/` directory. Use the exact `Artifacts:` path printed by your run; its number increases on subsequent runs.

### 3. Watch trades and read every report in the dashboard

```powershell
python -m stkcp dashboard
```

A native Windows window opens with **550 synthetic order records** loaded and paused. The larger demonstration finishes with **500 settled orders in 250 matched BUY/SELL trades, 50 rejected orders, and no pending orders**. Two settled order records make one matched trade. The engine produces these outcomes from the inputs; the dashboard does not substitute expected totals.

Press **Play** to watch the steps automatically, **Pause** to inspect the current state, **Next event** to advance one step, **Finish batch** to jump to completion, or **Restart** to return to the initial state. The default delay is 80 milliseconds per step, and the speed control changes playback speed. You can also select an initial delay:

```powershell
python -m stkcp dashboard --interval-ms 600
```

Read the full results inside the same window using its tabs:

| Dashboard view | What you can inspect |
| --- | --- |
| Replay & Charts | Price charts, cumulative executed trade value, live order classifications, SELL reservations, current holdings, and the event log. |
| Full Report | Batch totals and the complete explainable pending/rejection report. |
| Audit & Settlement | Every final order result, reason code, execution/reference price, and audit details, including the original order. |
| Trade Tape | Every matched BUY/SELL pair with counterpart order IDs, symbol, quantity, execution price, and trade value. |
| Holdings | Seeded and final quantities, settled changes, historical reference prices, and valuation. |
| Inputs & Checks | Original fixed-width inputs and their SHA-256 hashes, plus actual record, audit, inventory, and settled-trade reconciliation results. |

The reporting tabs show the completed batch and are labelled as final results. The Replay & Charts tab follows the selected processing step. You can inspect reports before, during, and after animation without opening a file or running a separate reporting command.

On a smaller screen, use the page scrollbar or mouse wheel to reach the lower replay panels; the charts keep a readable size. Tables have their own horizontal and vertical scrollbars. Playback stops at completion. Press **Restart** to watch the sequence again.

Select a symbol to inspect its chart, hover over a price marker for details, and select an order for its explanation. Executed trade value counts each matched pair once. The larger fixture includes multiple symbols, changing historical reference prices, and representative malformed-data, duplicate, inventory, price, and side rejections.

Drag the replay slider to inspect any step or select a previous event in the log to revisit it. These controls pause playback. Keyboard shortcuts are **Space** for Play/Pause, **Right Arrow** for the next event, and **Home** for Restart. The charts use processing steps on the horizontal axis, rather than elapsed market time.

Replay follows the existing settlement model: it first validates each order in input sequence, including SELL inventory reservations, then shows whole BUY/SELL pairs settling as atomic matching steps. It does not imply that a pair settled when its first order arrived. **Next** reveals one processing step, which can settle both sides of a trade together. Restart resets holdings, counters, charts, and events so replaying does not apply trades twice.

An order marked `AWAITING` has passed validation and is waiting for the matching phase. Any unmatched order becomes `PENDING` at completion. SELL reservations are released when the batch ends; settled holdings remain updated.

The original 14-order acceptance sample is still available:

```powershell
python -m stkcp dashboard --sample --interval-ms 600
```

That smaller sample ends with 4 settled orders in 2 matched trades, 2 pending orders, and 8 rejections. `python -m stkcp demo` retains this original acceptance sample. The dashboard's larger inputs are checked in under `data/dashboard-demo/`; regenerate them locally with `python scripts/generate_dashboard_demo.py`. Its 50 rejections include 10 each for duplicate IDs, insufficient holdings, bad prices, invalid sides, and malformed data. Five fictional symbols have 250 historical price observations; 50 seeded client/symbol holdings support the trades.

To load your own fixed-width local files, supply all three paths together:

```powershell
python -m stkcp dashboard --orders data/orders.txt --holdings data/holdings.txt --prices data/prices.txt
```

This view runs locally using Python's standard-library `tkinter`; it opens no web server and contacts no cloud or market-data service. The supplied prices are **synthetic historical references**, not live prices. The dashboard uses the Python reference engine and the same audit/report/reconciliation logic as the batch workflow; COBOL, JCL, and REXX remain the batch-language components described below. Reports are available in the dashboard itself. The optional `demo` and `run` batch commands also save artifacts for external use. Close the window to exit.

If the command reports `DASHBOARD FAILED (RC12)` with a Tk/Tcl or display diagnostic, use a desktop Python installation with Tcl/Tk support and an interactive Windows desktop. The command-line batch workflow remains available without Tkinter.

### 4. Run tests or save a complete validation run

```powershell
python -m unittest discover -s tests -v
python scripts/validate_local.py
```

The current suite has **87 passing tests**, with no failures, errors, or skips on Windows, including native Tkinter controls/layout, the 550-order fixture, every report view, audit filters, JSON/fixed-width modes, and consistency with batch settlement. See [dashboard validation observations](docs/validation.md#expanded-dashboard-and-550-order-fixture) and the [recorded results](docs/large-dashboard-validation-results.json). `validate_local.py` runs the current tests, saves `tests.txt` and `validation-results.json`, then saves a complete demo under a fresh `build/validation/run-NNNN/` directory. It records whether native batch languages were actually executed; a Python or Tkinter test pass does not claim native COBOL/REXX compilation.

### 5. Run your own fixed-width files

```powershell
python -m stkcp run --orders data/orders.txt --holdings data/holdings.txt --prices data/prices.txt --output build/my-run
python scripts/audit_to_json.py --input build/my-run/audit.dat --output build/my-run/audit-copy.jsonl --encoding ascii
```

Replace the three input paths with your files. Use a **new** output directory each time: `build/my-run` is an example, not an overwrite command. Follow [record layouts](docs/record-layouts.md); spreadsheet-style CSV orders are not accepted. Historical CSV prices have a separate [local importer](docs/market-data.md).

### Common Windows problems

| Message or symptom | Action |
| --- | --- |
| `No module named stkcp` | Run `Set-Location` to this project root before invoking `python -m stkcp`. |
| `python` not recognized / Store opens | Use the installed `py -3` launcher or the full path to your existing Python executable. |
| `output already exists` | Omit `--output` to get the next automatic run directory, or supply a new path. Previous runs are preserved. |
| `BATCH FAILED (RC12)` | Read the printed diagnostic; check input paths, field lengths, reference data, capacities, and output permissions. |
| `DOWNSTREAM STEP FAILED (RC8)` | Inspect the audit/conversion/reconciliation error. A successful run directory is not published. |
| GnuCOBOL `UNAVAILABLE` / compiler not found | The optional native path needs an existing compiler; use the normal Python demo on this machine. |
| `DASHBOARD FAILED (RC12)` | Check the supplied local file paths and the printed diagnostic. A graphical session and Python with Tcl/Tk support are required for `dashboard`. |

## Generated outputs

The final verified run is in `build/validation/run-0001/demo/`, with its test log and machine-readable observations in the parent directory. `validate_local.py` repeats this verification into a fresh directory. A run contains:

| File | Contents |
| --- | --- |
| `inputs/` | Exact input snapshots, whose SHA-256 hashes appear in the summary |
| `settlement.dat` | One 110-character classification per input order |
| `audit.dat` | The same fixed-width records, for JSON and reporting |
| `audit.jsonl` | UTF-8 JSON objects with reasons, explanations and exact integer paise |
| `holdings.dat` | Final holdings and historical valuation; unavailable reference is encoded zero |
| `summary.json` | Counts, engine identity, hashes and holdings; unavailable valuation is JSON null |
| `report.txt` | Per-order pending/rejection explanations and reconciliation counts |

Output is staged in a temporary sibling directory. Before publication, independent checks reconcile final holdings against settled orders, and balance BUY/SELL quantities and execution notionals by stock. A failed step publishes no run directory; an existing destination is refused. Repeat runs with the same inputs produce identical artifact bytes. Choose a **new** directory when specifying `--output`.

## Implemented features

The Python runtime features below have been exercised locally. Corresponding COBOL, REXX, and JCL source is supplied where indicated; their native execution status is described separately below.

| Area | Implemented behavior |
| --- | --- |
| Order validation | Exact fixed-width layout; padded uppercase identifiers; positive quantities and limits; real UTC calendar timestamps; BUY/SELL side validation; an auditable result for every readable order. |
| Duplicate detection | Deterministic detection in input sequence. The first structurally valid ID reserves the ID, including later business rejections; malformed rows do not reserve IDs. |
| Historical price selection | Latest price at or before each order time; no future-price use; maximum age of seven days; inclusive 90–110% reference-price band. |
| Exact monetary values | Integer paise in Python records and JSON; packed/display decimal fields in COBOL source; no floating-point settlement arithmetic. |
| Seeded inventory | Per-client/per-symbol holdings, SELL reservations before matching, rejection of overcommitment, no final-inventory change from rejected or pending orders, and final holdings updated for settled pairs. |
| Deterministic matching | Earliest later compatible counter-order; same symbol and exact quantity; different clients; crossing limits; both sides execute at the seller's limit. Whole fills only. |
| Order outcomes | `SETTLED`, `PENDING`, and `REJECTED`, with stable reason codes shared across COBOL source, Python, REXX source, fixtures, and tests. |
| Portfolio valuation | Final quantities valued using the latest eligible historical reference at the batch valuation timestamp. Missing/stale references produce explicitly unavailable valuations. |
| Fixed-width traceability | Separate settlement and audit outputs with identical 110-character records; original 59-character order prefix retained; complete original local inputs preserved in each successful run. |
| JSON Lines audit | One UTF-8 JSON object per audit record; schema version 1; original status/reason; deterministic explanation; prices, timestamp and raw order; proper escaping and nulls for unavailable values. |
| Audit validation | Length, reason/status, numeric, notional, execution-price and price-band checks; malformed audit diagnostics include the record number. |
| Explainable reporting | Per-order pending/rejection explanations, status totals, empty-batch handling, safe unknown-reason text, and failure on unknown or inconsistent classifications. |
| Record balancing | Input/audit/settlement count checks, audit-versus-settlement content comparison, and original-input tracing. |
| Independent inventory reconciliation | Final holdings checked against seeded positions plus actual settled BUY/SELL changes; duplicate/missing holdings rejected; settled quantities and execution notionals balance by symbol. |
| Safe output publication | Input snapshots and SHA-256 hashes; staged run directory; all downstream checks required before publication; existing run directories preserved; deterministic output bytes for identical inputs. |
| Converter publication | Standard-library `json.dumps`; temporary output and atomic replacement after full conversion; existing JSON destination preserved on malformed audit input. |
| Offline historical CSV import | Isolated adapter for existing local INR OHLC exports; missing values, duplicate timestamps, symbol/currency mismatch, invalid dates, range, stale/future values, OHLC consistency and exact paise validation. |
| Data provenance | Original CSV retained unchanged, source/replay hashes, declared provider and symbol, retrieval date, cutoff, adjustment policy and market-session metadata. Software does not authenticate the declared provider. |
| Demonstration fixtures | Explicitly synthetic prices and clients; 550-order dashboard fixture with 500 settled orders in 250 pairs and 50 rejections; original 14-order acceptance fixture covering all seven reason codes; deterministic local generators and independently checked expectations. |
| Capacity and failure handling | Bounded 1,000-order, 1,000-holding, 5,000-price tables; visible fatal errors for bad reference inputs, I/O, capacity and arithmetic failures. |
| Local/native tooling | CLI demo/custom run, standalone JSON converter, validation evidence generator, atomic GnuCOBOL build helper, and optional native/reference comparison helper. |
| Native Python dashboard | Local Tkinter window; Play/Pause/Next/Restart/Finish batch; adjustable replay speed, step slider, event navigation, and keyboard shortcuts; sequential validation followed by atomic matching; order outcomes and explanations, holdings and reservations, counters, event log, symbol-specific price charts with hover details, and cumulative executed trade value. Dedicated tabs expose complete reports, searchable audit and trade tables, JSON Lines and fixed-width audit/settlement records, final holdings/valuation, reconciliation checks, and exact source inputs inside the dashboard. Input bytes are captured for consistent reports even if source files change after loading. No third-party package, web server, or network connection. |
| Acceptance tests | Local tests covering matching, reservations, malformed data, duplicates, price boundaries, JSON, tampered outputs, determinism, failure return codes, imports, source contracts, replay consistency, and dashboard controls. |

The audit reason vocabulary is:

| Code | Status | Meaning |
| --- | --- | --- |
| `OK000` | SETTLED | A compatible pair was processed under the simplified batch rules. |
| `PEND01` | PENDING | No compatible counter-order was available. |
| `DUP001` | REJECTED | The order ID duplicates an earlier structurally valid order. |
| `HOLD01` | REJECTED | SELL quantity exceeds seeded availability after reservations. |
| `PRICE01` | REJECTED | Reference data is missing/stale or the limit is outside the allowed band. |
| `DATA001` | REJECTED | Record length, identifier, numeric fields, or timestamp is malformed. |
| `SIDE001` | REJECTED | Side is neither `B` nor `S`. |

## Settlement model

Validate order structure, duplicate ID, side, reference price, and SELL availability in that order. The first structurally valid ID is reserved even when later business checks reject it. A malformed row receives `DATA001`; it does not reserve an ID. Every readable order has one settlement and audit record. Original input snapshots retain complete malformed lines; the audit retains the first 59 characters padded as needed.

Use the latest reference at or before each simulated order timestamp, at most seven days old. Limits must be within the inclusive 90–110% reference band. Prices are references for validation and valuation, and do not imply execution. No floating-point money is used.

SELL orders reserve seeded inventory in input sequence before matching. Pending SELL reservations prevent later overcommitment but do not reduce final holdings. Purchases become available for resale in a future batch; they cannot fund another SELL in this run. Reservations expire at the end of the run.

Scan valid orders in input order, pairing each with the earliest later compatible counter-order: same symbol and exact quantity, different client, crossing BUY/SELL limits. Both orders execute completely at the SELL limit. No partial fills or exchange order book is claimed. This is batch clearing; timestamps control price selection rather than intrabatch execution chronology. Unmatched orders remain pending.

Final holdings use the latest reference at or before the maximum structurally valid order timestamp, with the same seven-day limit. Unknown valuation is null in JSON, including when all orders are malformed or absent. A known price times zero holdings is a valid zero valuation.

## Historical data

The checked-in fallback is explicitly **synthetic**, never live or downloaded market data. No real historical export was supplied. To honor local-only operation, the provider adapter imports an existing local CSV rather than contacting a provider. It preserves the original file, source declaration, retrieval date, adjustments/session metadata and hashes in a new directory. Import failure never silently selects the fixture.

See [market-data workflow](docs/market-data.md) for a runnable synthetic CSV import and instructions for a lawful, operator-supplied INR historical export. Authentication of external provenance and provider licensing are outside the offline importer. Live streaming is [planned only](docs/market-data.md#planned-live-ingestion).

## How COBOL, JCL, REXX, and Python are used

| Component | Responsibility | Current execution status |
| --- | --- | --- |
| COBOL: `src/cobol/SETTLE.cbl` | Core validation, matching, inventory changes, and fixed-width output generation. | Source implemented; compilation and execution unverified on this machine. Optional local GnuCOBOL path supplied. |
| JCL: `jcl/*.jcl` | Allocate datasets, invoke a site compiler/linker, and orchestrate the mainframe batch with return-code gates. | Site-configurable z/OS templates; never submitted. PowerShell does not execute JCL. |
| REXX: `src/rexx/REPORT.rexx` | Explain audit reason codes and validate dataset counts, content, traceability, and audit values. | TSO/E source implemented; native execution unverified. Windows reporting uses its Python equivalent. |
| Python: `stkcp/` and `scripts/` | Runnable local reference engine, JSON converter, local report, independent inventory reconciliation, offline data import and validation tools. | Executed and tested locally. The default demo uses this path. |

### COBOL: settlement and inventory processing

`SETTLE.cbl` is the native settlement program. Its paragraphs load seed holdings and historical prices, read and validate all orders, reserve SELL availability, match compatible orders, and write the three output files. It contains the same deterministic business rules described above.

COBOL-specific implementation includes:

- Explicit `SELECT`, `ASSIGN TO`, and `FD` definitions for every input and output, with file-status checks for open/read/write/close and end-of-file handling.
- Bounded `OCCURS` tables for orders, holdings, prices and duplicate detection; initialized working storage and counters; explicit capacity failures.
- **88-level condition names** for all three statuses and all seven reasons, such as `t-settled`, `t-pending`, `t-rejected`, `t-duplicate`, and `t-insufficient`.
- Decimal/integer quantity, price, notional and valuation calculations, with arithmetic overflow handling where applicable and no negative SELL holdings.
- Calendar validation before `INTEGER-OF-DATE`, historical-age checks, and explicit ASCII symbol ordering so price sorting follows the same contract under EBCDIC.
- RC0 for a completed batch including business rejections, and RC12 for fatal infrastructure/reference/capacity/arithmetic errors.

Its DD interfaces match the JCL and the local native runner:

| DD | Direction | Record length | Purpose |
| --- | --- | ---: | --- |
| `ORDERS` | Input | 59 | Client orders |
| `HOLDINGS` | Input | 26 | Seeded client/stock quantities |
| `PRICES` | Input | 32 | Validated historical replay |
| `SETTLE` | Output | 110 | One classification per order |
| `AUDIT` | Output | 110 | Shared source for JSON and reporting |
| `HOLDOUT` | Output | 56 | Final holdings and historical valuation |

Without the compile-time `LOCAL` flag, the source uses ordinary sequential FB datasets on z/OS. With `LOCAL`, it uses line-sequential files under GnuCOBOL. The Python native runner sets `DD_ORDERS`, `DD_HOLDINGS`, `DD_PRICES`, `DD_SETTLE`, `DD_AUDIT`, and `DD_HOLDOUT` automatically. Output publication is handled by the surrounding pipeline after the program succeeds; COBOL can leave partial temporary files on a fatal write.

### JCL: mainframe allocation, build, and batch orchestration

JCL defines jobs and their datasets; it supplies the native program's inputs and outputs and decides which downstream steps may run.

| Member | What the supplied source does |
| --- | --- |
| `jcl/ALLOCATE.jcl` | Defines source/exec/load libraries and ORDERS, HOLDINGS and PRICES datasets with documented record attributes. Uses IEFBR14 for allocation only. |
| `jcl/COMPILE.jcl` | Invokes a placeholder for the site's Enterprise COBOL compile/link procedure, with source/library/listing overrides and a SETTLE load-module destination. Procedure names, compiler options and compile-to-link failure gates require site validation. |
| `jcl/RUN.jcl` | Invokes SETTLE, prepares a unique USS staging directory, exports/converts the audit, runs Python JSON conversion, invokes TSO/E REXX, catalogs validated datasets, then publishes JSON and writes a final SUCCESS marker. |

The run template's sequence is:

```text
COBOL SETTLE
  -> unique USS staging directory
  -> OCOPY audit export + explicit EBCDIC-to-ASCII iconv
  -> USS Python audit-to-JSON converter
  -> TSO/E REXX REPORT reading native datasets
  -> catalog validated datasets
  -> rename completed JSON and write SUCCESS last
```

Each success-only block requires its prerequisite's RC0 and no abend. A reachable diagnostic step explains how to inspect failure results. Run-specific output datasets stay uncataloged during processing. IEFBR14 only allocates/catalogs; the reporting code performs the count checks. Dataset cataloging and the USS rename are separate operations, so native acceptance also requires the unique run's final SUCCESS marker.

Reusable JCL uses configurable `&HLQ` plus marked account, storage, compiler, batch-TSO, encoding and USS-path placeholders. The batch-TSO program must propagate REXX/OCOPY errors to its step return code. See [z/OS setup](docs/zos-setup.md) for all substitutions, encoding checks, permission alternatives and required native failure tests. No job has been submitted from this project.

### REXX: explainable reconciliation report

`REPORT.rexx` is a **TSO/E REXX exec**, intended to run from the JCL REPORT step using a site-supported batch-TSO driver. It uses `EXECIO ... DISKR` with stem variables to read the DDs `AUDIT`, `SETTLE`, and `ORDERS`.

It implements:

- One deterministic plain-language explanation for each COBOL reason code, plus a safe fallback for an unknown code.
- Per-order pending/rejection messages and total, settled, pending, rejected and unknown-status counts.
- Empty-batch handling, read-error handling and the 1,000-record limit.
- Fixed record-length checks, input/audit/settlement count agreement, strict audit/settlement byte comparison, and original-order tracing.
- Known status/reason and padding checks, numeric derived-field validation, reference-notional checks, and rejection of execution prices on unexecuted orders.
- RC0 for a valid report and RC8 for I/O, malformed audit, unknown classification or balancing failure.

REXX reads the **fixed-width audit dataset directly**. JSON is produced from that same audit by Python; REXX does not read or parse JSON. Independent final-holdings and execution-notional reconciliation is an additional Python pipeline check, rather than a REXX HOLDOUT calculation.

Because this exec depends on TSO/E `EXECIO`, it cannot be run directly in PowerShell or by assuming any generic Windows REXX interpreter provides TSO services. The default Windows report comes from `stkcp/report.py` and explicitly records that native REXX was not executed.

### Python: the executable Windows path and audit bridge

`stkcp/engine.py` runs the settlement reference rules on Windows. `stkcp/pipeline.py` snapshots inputs, invokes either the reference engine or an existing compiled COBOL executable, gates downstream work, and publishes successful runs. `stkcp/audit_to_json.py` converts audit records; `stkcp/report.py` supplies the local report; `stkcp/reconciliation.py` independently checks final inventory and settled trade balances. `stkcp/market_data.py` imports existing local historical CSV exports. `stkcp/replay.py` builds deterministic progress snapshots from the same settlement rules, and `stkcp/dashboard.py` displays them in a native Tkinter window launched with `python -m stkcp dashboard`.

The JSON converter is also the intended USS audit bridge in the JCL flow. Its wrapper is `scripts/audit_to_json.py`; deploy it together with the sibling `stkcp/` package as documented in the z/OS guide. It needs only the Python standard library.

## Optional native COBOL on Windows

This path requires an **already installed GnuCOBOL compiler** and its runtime dependencies available to the terminal. The project does not install or download them. No compiler was available during this project's local validation.

```powershell
Get-Command cobc -ErrorAction SilentlyContinue
python scripts/build_cobol.py
```

Continue only after the build reports successful compilation. A successful Windows build produces `build/settle.exe`; the helper stages the executable and replaces its destination only after compiler success.

```powershell
python scripts/validate_native.py --cobol-program build/settle.exe
python -m stkcp demo --engine cobol --cobol-program build/settle.exe
```

The native validator compares actual compiled COBOL outputs with the Python reference and checks focused malformed/fatal cases. Alternatively, `python scripts/validate_native.py` compiles a temporary executable using an existing compiler before validating it. Missing compiler/executable or failed validation returns nonzero; it is not a passing native test.

With `--engine cobol`, settlement executes the compiled COBOL program; audit conversion, local reporting, independent holdings reconciliation, and output publication still use Python. JCL and native TSO/E REXX are not invoked by this Windows path. Use `build/settle` rather than `.exe` on Linux/macOS. See [COBOL notes](src/cobol/README.md) for runtime file mapping and limits.

## Contracts and verification

- [Field positions, lengths and JSON schema](docs/record-layouts.md)
- [Detailed shared rules](docs/implementation-contract.md)
- [Manually reasoned expected results](data/expected-results.json)
- [Acceptance checklist and observed results](docs/validation.md)

Return codes are 0 for a completed batch including business rejections, 8 for audit conversion or report validation/balance failure, 12 for fatal I/O, invalid reference input, capacity, arithmetic or final-inventory/trade-balance failures, and 2 for CLI usage errors. Limits are 1,000 orders, 1,000 client/stock holdings including pending buyers, and 5,000 historical prices.

The implementation excludes DB2, persistent multiday holdings, cash/fee accounting, real exchange connectivity, streaming, encryption, CPACF, compression, GDGs and production throughput claims. The local report is a Python equivalent; the REXX source reads fixed-width datasets and never parses JSON.
