# Acceptance checklist and actual observations

The local scope was implemented on 19 October 2026 without network or IBM access. The attached specification also describes a z/OS milestone; its environment-dependent acceptance items are explicitly unverified below.

## Expected fixture results (specified before running)

`data/expected-results.json` contains independently hand-reasoned per-order classifications, reference/execution prices, and final holdings. Tests compare actual program artifacts to that file; no runner prints hard-coded expected totals.

| Expected result | Count |
| --- | ---: |
| Input / settlement / audit / JSON objects | 14 each |
| Settled order records | 4 (two matched pairs) |
| Pending | 2 |
| Rejected | 8 |
| Final client/stock holdings entries | 6 |
| Business batch return code | 0 |

All seven reason codes occur. Cases include valid BUY/SELL, insufficient holdings, duplicate ID, invalid side, bad price band, malformed quantity/date/short record, unmatched orders and future-only reference data. Final SELLER1/ALPHA is 90; SELLER2/BETA is 15. A rejected SELL reduces neither holdings nor reservations. The pending SELL reserves inventory within this batch but does not reduce final holdings.

## Observed locally

Commands actually executed:

```text
python -m unittest discover -s tests -v
python -m stkcp demo --output build/demo
python scripts/validate_local.py
```

The original milestone suite passed **38 tests**, with zero failures, errors or skips. The executed demo returned RC0 with `TOTAL=14 SETTLED=4 PENDING=2 REJECTED=8 BALANCE=PASS`. Artifacts were produced and their JSON contents, fixed record lengths, every expected classification and every expected holding were inspected by acceptance tests. That saved run is `build/validation/run-0001/demo/`; its parent contains the real test log and observations. A copy of those machine-readable observations is in `docs/validation-results.json`.

## Dashboard verification

The subsequent Python dashboard validation passed **64 tests**, with zero failures, errors or skips, using Python 3.14.7 and native Tk 9.0 on Windows. The evidence is saved under `build/validation/run-0002/`, with observations copied to `docs/dashboard-validation-results.json`. Batch outputs still match the original fixture: 14 records, 4 settled, 2 pending, 8 rejected, with independently reconciled holdings.

Added checks exercise actual native Tk windows and event processing for Play/Pause, completion, cancellation of scheduled steps, manual stepping, Restart, repeated playback without duplicate holdings changes, speed changes, slider/event navigation, empty inputs, clean desktop startup failures, and readable graphs with scrolling at 1280×720. GUI tests explicitly skip if Tk or a graphical display is unavailable; no such skips occurred in this recorded run.

Replay tests verify immutable snapshots from the actual reference engine, validation before clearing, atomic settlement of both trade legs, unique row identities for duplicate IDs, price cutoffs, malformed-row price handling, reservation expiry, and exact final agreement with settlement/audit/holdings records. The dashboard does not simulate external exchange connectivity or execute JCL, COBOL, or TSO/E REXX.

## Expanded dashboard and 550-order fixture

The new default dashboard fixture is `data/dashboard-demo/`; the original 14-order batch fixture remains unchanged and is available in the dashboard using `--sample`. Expected outcomes are derived from the constructed input pairs in `data/dashboard-demo/expected-results.json`. Actual engine replay produced **550 input orders, 500 settled orders in 250 matched pairs, 50 rejected orders, and zero pending orders**. Its 802 events consist of the untouched initial state, 550 validation events, 250 atomic pair settlements, and batch completion.

The rejected orders comprise 10 each for `DUP001`, `HOLD01`, `PRICE01`, `SIDE001`, and `DATA001`. The five fictional stocks have 250 synthetic historical reference observations. Quantities 1 through 250 transfer 31,375 shares in total; matched-pair execution value is INR 5,339,860.85, counted once per pair. Final historical portfolio valuation is INR 8,573,600.00. The larger fixture is reproducible with `python scripts/generate_dashboard_demo.py`.

The complete suite `python -m unittest discover -s tests -v` passed **87 tests in 11.795 seconds**, with zero failures, errors, or skips; native Tkinter checks ran on Windows. The recorded observations are in [large-dashboard-validation-results.json](large-dashboard-validation-results.json). This includes the unchanged original acceptance checks, large-fixture pipeline/replay consistency, full report construction and reconciliation, snapshot consistency, CLI selection, and the UI checks below.

The native Windows GUI command `python -m unittest tests.test_large_dashboard_gui -v` passed **7 tests**, with no failures, errors, or skips. These checks exercise all six tabs, reports available before playback, 550 audit records and 250 trade rows, final counters and restart stability, table scrolling at 1280×720, filters and search, the exact JSON Lines and 110-character audit/settlement records, all original input datasets, Finish batch timer cancellation, and keyboard controls restricted to the replay tab. Report and reconciliation contents come from the actual captured input bytes, engine audit, converter, report, and holdings checks. Reporting tabs explicitly show final results while the replay tab animates the selected processing step.

A native 1280×720 rendering measurement advanced all 801 steps after the initial state, calling `update_idletasks()` after each step. It completed in 24.766 seconds, with median rendering time 28.874 ms, 95th percentile 52.667 ms, and maximum 90.162 ms on this development machine. These are observed UI rendering timings without playback delays, not claims about settlement throughput or other machines. The default playback delay is 80 ms; the user can change speed or use Finish batch to inspect completion immediately.

| Local check | Observation |
| --- | --- |
| One output of each kind per readable order | Passed |
| Actual execution obeys crossing limits and whole quantities | Passed |
| No self trades, partial fills or order reuse | Passed |
| Earliest compatible matching, stable output order | Passed |
| Duplicate precedence and malformed ID nonreservation | Passed |
| Holdings reservation and rejected SELL behavior | Passed |
| Latest nonfuture reference, exact seven-day boundary | Passed |
| Inclusive price band with integer arithmetic | Passed |
| Real calendar validation and malformed records | Passed |
| Empty batch and unavailable valuations | Passed |
| JSON parsing, escaping, reason explanations and atomic replacement | Passed |
| Audit/input/settlement count, content and input tracing | Passed |
| Final holdings, settled stock quantities and execution-notional reconciliation | Passed; tampered/missing/duplicate holdings and missing counterpart rejected |
| Deterministic artifact bytes across two runs | Passed |
| Bad reference files and table/arithmetic overflow | Passed: fatal infrastructure error |
| Missing input through actual CLI | RC12; no successful run directory |
| Malformed audit through actual converter CLI | RC8; previous destination preserved |
| Offline CSV import, metadata/hash preservation and validation | Passed |

## Remaining environment verification

| Deliverable | Implemented | Compiled / executed / inspected |
| --- | --- | --- |
| Python reference engine, converter, local report | Yes | Executed locally, outputs validated |
| Offline historical CSV adapter | Yes | Tested with synthetic local CSV; no real export imported |
| COBOL `SETTLE` with 88-level reasons and DDs | Yes | No installed compiler available; uncompiled |
| TSO/E REXX dataset report | Yes | No runtime available; unexecuted |
| Allocation, compile/link, success-gated run JCL | Yes, with site placeholders | Never submitted; no spool inspected |
| Enterprise COBOL and native dataset encoding/OCOPY path | Templates and setup notes | Requires real site verification |
| Actual historical market data provenance/licensing | Import support only | No real market data supplied or retrieved |

The local runner labels its engine `python-reference` and `rexx_executed=false`. No Python test is reported as a native COBOL or REXX execution. The native validation helper is provided for an existing local GnuCOBOL installation; it must produce a real successful compilation and compare actual output before native verification can be claimed.

For eventual z/OS acceptance, complete the site checklist in `docs/zos-setup.md`, run all successful/business failure cases, deliberately test missing DDs and failed conversion/reporting, inspect actual compiler/binder/spool output and record step RCs. Confirm failed runs lack the unique final SUCCESS marker. None of these actions was attempted in this local-only implementation.
