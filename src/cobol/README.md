# SETTLE source

`SETTLE.cbl` implements the fixed record contract in
`docs/implementation-contract.md`. The source is free format. It uses six DDs:
`ORDERS`, `HOLDINGS`, `PRICES`, `SETTLE`, `AUDIT`, and `HOLDOUT`. The three
outputs must be staged and published only after return code zero. A run that
fails while writing can leave partial temporary files; discard those files.

The default source branch uses sequential FB datasets with lengths 59, 26,
32, 110, 110, and 56 respectively. Compile on z/OS using the site's Enterprise
COBOL procedure and free source format support. No site compiler or dataset
permission is assumed. Compilation and z/OS execution remain unverified until
performed in the actual environment.

With an **already installed** GnuCOBOL compiler, run from the project root:

```text
python scripts/build_cobol.py
```

The equivalent command is `cobc -x -free -Wall -DLOCAL=1 -o build/settle
src/cobol/SETTLE.cbl` (use `.exe` on Windows). `LOCAL` switches to line
sequential input and output. Set the environment variables `DD_ORDERS`,
`DD_HOLDINGS`, `DD_PRICES`, `DD_SETTLE`, `DD_AUDIT`, and `DD_HOLDOUT` to absolute
file paths before launching the executable. GnuCOBOL's normal runtime file
name mapping must be enabled. Local input buffers accommodate readable lines
up to 32,760 bytes; normal records use the contract lengths. Readable malformed
orders are classified `DATA001`, preserving the first 59 characters padded
with spaces. Malformed holdings/prices and I/O errors are fatal.

Once GnuCOBOL is available, run `python scripts/validate_native.py` to compile
into a temporary directory and compare actual native output against the Python
reference on the fixture and focused edge/fatal cases. To validate an existing
executable, use `python scripts/validate_native.py --cobol-program
build/settle.exe`. Fixed-record bodies are compared byte for byte; local LF and
CRLF terminators are both accepted. This command returns 12 and clearly states
that no validation ran if the compiler is unavailable. These optional native
checks do not claim Enterprise COBOL, JCL, or REXX verification.

The table limits are 1,000 orders, 1,000 holdings including valid pending BUY
entries, and 5,000 prices. The program validates inputs and closes input files
before opening output files. It reserves SELL quantities before matching,
matches in deterministic input order, and changes final holdings only for
settled pairs. Money and valuation arithmetic use exact decimal integers.
All dates are checked before calling `INTEGER-OF-DATE`. Price ordering uses
an explicit ASCII symbol order so EBCDIC compilation follows the same rule.

The 88-level names in the order table centralize all three statuses and all
seven reason codes. Return code 0 includes business rejections and empty
orders. Return code 12 indicates an infrastructure, malformed reference data,
table capacity, or holdings arithmetic failure. No IBM service, network
library, external downloader, or remote connection is used by this program.
