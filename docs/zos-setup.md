# z/OS deployment templates (not submitted or verified)

The repository is an offline project. No IBM Cloud account, remote login,
dataset allocation, upload, job submission, or network request is performed by
the local demonstration. This document describes optional future deployment.
The JCL and TSO/E REXX are implemented source templates. Their presence is not
evidence of an Enterprise COBOL compile, submitted job, or successful spool
validation. Use the local commands in the README for the runnable demonstration.

## Values that must come from the actual site

Read an existing permitted job and the site's compiler instructions before
editing the templates. There are no assumed account permissions or system
library names.

| Template value | Required decision |
| --- | --- |
| JOB card | Replace `SITEACCT`, classes, notification, and other accounting fields using site instructions. |
| `HLQ=YOURHLQ` | An allocated user namespace permitted by the site, not a real ID embedded in this repository. |
| `DISK=SITEUNIT` | Permitted allocation unit or remove it when the site's SMS rules require that. Check PDSE, space, and DCB rules. |
| `COBPROC=SITEPROC` | The documented Enterprise COBOL compile/link procedure. Confirm its step/DD names, PROC search library, options, and error gating. |
| `USSROOT='/u/REPLACE/stkcp'` | An existing writable absolute USS project directory. No spaces, quotes, or shell metacharacters in this template's substituted values. |
| `PYTHON='/REPLACE/python3'` | The actual supported Python 3 executable. The converter uses the standard library only. |
| `HOSTENC='SITEENC'` | The single-byte EBCDIC encoding used for datasets and supported by `iconv`, for example `IBM-1047` only after confirmation. |
| `RUNID=R001` | A new run identifier: 1–8 valid dataset qualifier characters, beginning with a letter; use only letters/digits here. Neither its datasets nor its USS directory may exist. |
| `TSOPGM=SITEBTSO` | Site-supported batch TSO driver that propagates nonzero command/REXX return codes, conventionally `IKJEFT1B`. Verify its semantics using deliberate `EXIT 8` and failed OCOPY tests before the run. |
| TSO/USS programs | Confirm `OCOPY`, `BPXBATCH`, `SH /bin/sh -s`, `iconv`, and DD symbol substitution are supported as shown. |

`RUN.jcl` uses JCL `EXPORT SYMLIST` and `DD *,SYMBOLS=JCLONLY` to substitute
values inside shell input. Confirm these facilities on the target JES/z/OS
version. Substitute literal values into those in-stream sections if the site
does not permit them. Do not replace the templates with unverified system-wide
library names or rely on implicit text conversion.

## Allocate and transfer

1. Review `jcl/ALLOCATE.jcl` and allocate only datasets that do not already
   exist. IEFBR14 performs allocation; it is not a balancing utility.
2. Transfer the files below through the site's documented text upload mechanism
   (such as an existing Zowe Explorer connection). This is a manual deployment
   step and is not invoked by the local project. Convert ASCII source text to
   the confirmed dataset EBCDIC encoding exactly once. Remove local LF/CRLF
   terminators; every dataset record has the specified LRECL.
3. Check the resulting DCB attributes and inspect several records, including
   the last field and a record with trailing spaces. Preserve all field padding.
   Do not split on whitespace or upload a whole LF file as one dataset record.

| Local file | Dataset/member | RECFM/LRECL |
| --- | --- | --- |
| `jcl/*.jcl` | `&HLQ.STKCP.JCL(ALLOCATE/COMPILE/RUN)` | FB/80 |
| `src/cobol/SETTLE.cbl` | `&HLQ.STKCP.COBOL(SETTLE)` | FB/255 |
| `src/rexx/REPORT.rexx` | `&HLQ.STKCP.REXX(REPORT)` | FB/80 |
| `data/orders.txt` | `&HLQ.STKCP.ORDERS` | FB/59 |
| `data/holdings.txt` | `&HLQ.STKCP.HOLDINGS` | FB/26 |
| `data/prices.txt` | `&HLQ.STKCP.PRICES` | FB/32 |

The short malformed sample order is intentional. FB59 uploads pad it with
spaces, so it still rejects as `DATA001` because mandatory fields are absent.
FB storage cannot represent a short record as a physically shorter record.
Reject overlong local records before upload rather than silently truncating
them. Other malformed local line-length tests belong to the local test suite.

The free-format COBOL source contains `>>SOURCE FORMAT FREE`. Upload to FB255,
not FB80; inspect for truncation. REXX is kept within FB80. Sample files contain
synthetic clients and synthetic prices and must remain labelled that way.

If fresh PDSEs or a private load library are not allowed, use existing permitted
user source/exec/load libraries and update the DDs in COMPILE and RUN together.
Do not allocate in another user's namespace or assume RACF privileges. An
environment with no permitted compiler/load library cannot verify this native
path; the local reference run remains available.

Create the USS project directories using the site's permitted terminal or file
tool. For example, after replacing the userid placeholder:

```sh
mkdir -p '/u/<userid>/stkcp/scripts' '/u/<userid>/stkcp/stkcp'
```

Deploy `scripts/audit_to_json.py` and the entire sibling `stkcp/` package under
that root, preserving the hierarchy. The wrapper explicitly adds the project
root to Python's import path. Transfer these Python files as ASCII/UTF-8 bytes
and set any tags required by the site's Python runtime. Do not transfer Python
source as EBCDIC unless the runtime explicitly supports and has been configured
for that. No installation from the internet is needed. Verify the interpreter
can execute this locally deployed code before adapting the job.

## Compile and link

`jcl/COMPILE.jcl` deliberately requires a site-provided procedure. Its sample
overrides assume the procedure has steps `COBOL` and `LKED`, compiler DDs
`SYSIN`, `SYSLIB`, `SYSPRINT`, and binder DDs `SYSLMOD`, `SYSPRINT`. Confirm or
change every override against the actual PROC. Add a permitted `JCLLIB ORDER`
only if the site requires one. Do not invent a procedure name.

The procedure must prevent link after a compiler abend or compiler RC above 4.
Review all warnings at RC4 and require a clean, usable load module. Confirm
`SOURCEFORMAT(FREE)`, `SSRANGE`, and `NUMCHECK` availability for that compiler;
the source already requests free format. Do not define `LOCAL` for Enterprise
COBOL: that switch selects the optional GnuCOBOL line-sequential mode. Inspect
compiler and binder listings and confirm `SETTLE` was written to the load
library selected by RUN. A compile failure can leave an older member in place;
do not run it as though a failed build succeeded.

## Fixed records to USS: preserve length and convert once

MVS datasets hold FB records without newline bytes. The converter expects text
lines containing exactly 110 ASCII data bytes plus LF (or CRLF). A binary copy
of adjacent FB110 records does not meet this interface.

The unverified job template makes the boundary explicit:

1. `EXPORT` allocates the new audit dataset as DD `AUDIT`, and an initially
   empty USS path as `AUDUSS` with `FILEDATA=TEXT`.
2. TSO `OCOPY INDD(AUDIT) OUTDD(AUDUSS) TEXT CONVERT(NO)` writes native EBCDIC
   text lines, preserving the fixed data portion. The configured `TSOPGM` must
   propagate a failing OCOPY return code to the JCL step. Plain `IKJEFT01` can
   conceal a command/exec failure and must not be used without an explicitly
   verified return-code wrapper. Confirm the site's `IKJEFT1B` or equivalent
   single-command pattern with a deliberate failed OCOPY.
3. USS `iconv -f '<confirmed EBCDIC encoding>' -t ISO8859-1` produces
   `audit.txt`. All supported contract characters are in ASCII. A non-ASCII
   result fails the converter's explicit `--encoding ascii` check.
4. Python converts the ASCII lines and writes a complete JSON candidate by
   temporary-file replacement. JSON output is UTF-8. REXX then validates the
   original datasets directly, so JSON parsing is unnecessary in TSO/E.

The corresponding converter command, after substituting real paths, is:

```sh
'/actual/python3' '/u/<userid>/stkcp/scripts/audit_to_json.py' \
  --input '/u/<userid>/stkcp/R001/audit.txt' \
  --output '/u/<userid>/stkcp/R001/audit.candidate.jsonl' \
  --encoding ascii
```

Check one test record at the byte level before accepting this transfer route:
110 data bytes followed by ASCII LF (`0A`), with positions 60–67 containing a
padded status and 68–74 containing a padded reason. Check all record lengths,
not just what an editor displays. If the site maps EBCDIC newline to a different
byte, configure its documented conversion table or line export mechanism; do
not strip arbitrary bytes or trim trailing spaces to make parsing succeed.
Check USS file tagging and automatic conversion settings to avoid a second
conversion by OCOPY, the shell, or Python. Encoding assumptions have not been
verified on an IBM system here.

## Run, validate, publish

`RUN.jcl` executes COBOL with DDs `ORDERS`, `HOLDINGS`, `PRICES`, `SETTLE`,
`AUDIT`, and `HOLDOUT`. Business rejections are output records and leave COBOL
RC0. Fatal I/O, capacity, input seed, or arithmetic errors yield RC12 in the
program; an abend is a failure regardless of a numeric condition code.

Every downstream block requires its prerequisite to have returned RC0 and not
abended. The path is COBOL → preparation/OCOPY → USS converter → TSO/E REXX →
catalog → JSON publication. No `COND=(0,NE,step)` inversion is used. The final
diagnostic utility has `COND=EVEN` so spool contains acceptance instructions
even after an abend; its own RC0 is never evidence of batch success. BPXBATCH
may encode UNIX exit status in its MVS condition code. Inspect stderr and the
step code; the template depends only on zero versus nonzero.

The REXX `%REPORT` invocation uses `SYSEXEC` and DDs `AUDIT`, `SETTLE`,
`ORDERS`. It returns RC8 for read errors, excess records, malformed audit
values, unknown codes/statuses, or failed count/byte checks. It prints readable
pending/rejection explanations, including a safe unknown-code explanation.
`EXECIO` RC2 is treated as normal EOF when fewer than 1,001 records are read.
An empty batch is valid when all three datasets are empty. The report compares:

- input, audit, and settlement record counts;
- every 110-byte audit record with its corresponding settlement record using
  REXX strict string comparison;
- each original 59-byte order with its audit prefix;
- status/reason consistency, numeric derived values, and reference notional.

Status totals classify orders; they do not claim all orders settled.

Outputs are new, run-specific datasets such as `&HLQ.STKCP.R001.AUDIT`.
They are passed uncataloged during validation. Normal fatal exits do not
catalog them; abend disposition deletes them. Unreceived passed datasets are
deleted at job end. After the converter and REXX both succeed, `CATALOG` uses
IEFBR14 solely to catalog validated datasets. `COMMIT` renames the candidate to
`USSROOT/RUNID/audit.jsonl` and creates `SUCCESS` last. Existing run directories
are refused and existing successful output is never overwritten.

Dataset catalog operations and USS rename are not one transaction. A catalog
failure may leave some validated datasets cataloged; a later COMMIT failure may
leave datasets but no JSON/marker. Such a run is incomplete. Accept a run only
when the compiler/load member was validated, every processing step completed
successfully, COMMIT returned RC0, and that unique directory has its `SUCCESS`
marker. Inspect spool allocation/catalog messages as well as step condition
codes. A marker from another RUNID proves nothing about the current run. Keep
failed artifacts for diagnosis and remove only the explicitly identified failed
run's artifacts using permitted site tools before choosing a fresh RUNID.

## Native acceptance checklist (all remain unverified)

- [ ] Confirm the JOB card, permissions, PROC, compiler options, DDs, and USS
  commands against real site configuration.
- [ ] Inspect the compiler and binder listings and the newly built load member.
- [ ] Inspect uploaded record lengths and the ASCII export's bytes/line endings.
- [ ] Run the checked-in fixture: 14 audit and settlement records, 4 SETTLED,
  2 PENDING, 8 REJECTED; compare every reason against `data/expected-results.json`.
- [ ] Parse all JSON Lines independently and compare the dataset/JSON values.
- [ ] Inspect REXX spool explanations, input count, byte balance, and RC0.
- [ ] Inspect `HOLDOUT` FB56 and its final holdings/valuation. A zero reference
  price means valuation unavailable, not a zero market price.
- [ ] Test missing input/load module, invalid seed, failed USS conversion, and
  altered report inputs in isolated datasets: no success-only path may run
  after the failed prerequisite; no `SUCCESS` marker may appear.
- [ ] Test a deliberate report count mismatch, audit/settlement byte mismatch,
  unknown reason, and three empty datasets. The first three require RC8; empty
  matching datasets require RC0 and zero totals.
- [ ] With the configured batch TSO driver, invoke a small REXX containing
  `EXIT 8` and confirm its JCL step is nonzero. Confirm a failed OCOPY likewise
  fails its step. Then confirm REPORT RC8 actually skips catalog/COMMIT.
- [ ] Test an abend and a normal nonzero return separately; inspect the reachable
  diagnostic step and verify no failed run is accepted as published.

Record actual observations separately from expected results. Until these boxes
are supported by submitted jobs and inspected spool, native z/OS milestone
verification remains outstanding.
