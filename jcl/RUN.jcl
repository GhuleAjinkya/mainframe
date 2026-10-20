//STKRUN JOB (SITEACCT),'STKCP RUN',CLASS=A,MSGCLASS=H,
//             NOTIFY=&SYSUID
//* UNVERIFIED TEMPLATE. Resolve EVERY site value before submission.
//* RUNID must be NEW: 1-8 valid dataset-qualifier characters, no '/'.
//* Existing validated runs are never overwritten by this template.
//         SET HLQ=YOURHLQ
//         SET RUNID=R001
//         SET DISK=SITEUNIT
//         SET USSROOT='/u/REPLACE/stkcp'
//         SET PYTHON='/REPLACE/python3'
//         SET HOSTENC='SITEENC'
//         SET TSOPGM=SITEBTSO
//         EXPORT SYMLIST=(HLQ,RUNID,USSROOT,PYTHON,HOSTENC)
//* The installed code/data must use HOSTENC on MVS, ASCII in USS.
//* RC12 and abends are infrastructure failures; RC0 permits rejects.
//RUNCOB   EXEC PGM=SETTLE
//STEPLIB  DD DSN=&HLQ..STKCP.LOAD,DISP=SHR
//ORDERS   DD DSN=&HLQ..STKCP.ORDERS,DISP=SHR
//HOLDINGS DD DSN=&HLQ..STKCP.HOLDINGS,DISP=SHR
//PRICES   DD DSN=&HLQ..STKCP.PRICES,DISP=SHR
//* PASS keeps new outputs uncataloged until both consumers validate.
//* Unreceived PASS datasets are deleted at job end. No MOD outputs.
//SETTLE   DD DSN=&HLQ..STKCP.&RUNID..SETTLE,
//            DISP=(NEW,PASS,DELETE),UNIT=&DISK,SPACE=(TRK,(5,2)),
//            DCB=(RECFM=FB,LRECL=110,BLKSIZE=0)
//AUDIT    DD DSN=&HLQ..STKCP.&RUNID..AUDIT,
//            DISP=(NEW,PASS,DELETE),UNIT=&DISK,SPACE=(TRK,(5,2)),
//            DCB=(RECFM=FB,LRECL=110,BLKSIZE=0)
//HOLDOUT  DD DSN=&HLQ..STKCP.&RUNID..HOLDOUT,
//            DISP=(NEW,PASS,DELETE),UNIT=&DISK,SPACE=(TRK,(5,2)),
//            DCB=(RECFM=FB,LRECL=56,BLKSIZE=0)
//SYSOUT   DD SYSOUT=*
//SYSUDUMP DD SYSOUT=*
//* Explicit ABEND exclusion also covers non-returning failures.
//COBOK    IF (NOT RUNCOB.ABEND AND RUNCOB.RC = 0) THEN
//* A unique staging directory prevents stale JSON being accepted.
//PREPARE  EXEC PGM=BPXBATCH,PARM='SH /bin/sh -s'
//STDOUT   DD SYSOUT=*
//STDERR   DD SYSOUT=*
//STDIN    DD *,SYMBOLS=JCLONLY
set -eu
root='&USSROOT'
run='&RUNID'
test -d "$root/scripts"
test ! -e "$root/$run"
mkdir "$root/$run"
/*
//PREPOK   IF (NOT PREPARE.ABEND AND PREPARE.RC = 0) THEN
//* OCOPY adds text newlines and preserves all FB data bytes.
//* Do not binary-copy concatenated FB records into the line converter.
//* TSOPGM must propagate a failing command/REXX RC (e.g. IKJEFT1B).
//* Plain IKJEFT01 is unsuitable unless its RC behavior is verified.
//EXPORT   EXEC PGM=&TSOPGM,DYNAMNBR=20
//AUDIT    DD DSN=*.RUNCOB.AUDIT,DISP=(OLD,PASS,DELETE)
//AUDUSS   DD PATH='&USSROOT/&RUNID/audit.ebcdic',
//            PATHOPTS=(OWRONLY,OCREAT,OTRUNC),
//            PATHMODE=(SIRUSR,SIWUSR),FILEDATA=TEXT
//SYSTSPRT DD SYSOUT=*
//SYSPRINT DD SYSOUT=*
//SYSTSIN  DD *
  OCOPY INDD(AUDIT) OUTDD(AUDUSS) TEXT CONVERT(NO)
/*
//EXPOK    IF (NOT EXPORT.ABEND AND EXPORT.RC = 0) THEN
//TOJSON   EXEC PGM=BPXBATCH,PARM='SH /bin/sh -s'
//STDOUT   DD SYSOUT=*
//STDERR   DD SYSOUT=*
//STDIN    DD *,SYMBOLS=JCLONLY
set -eu
root='&USSROOT'
run='&RUNID'
iconv -f '&HOSTENC' -t ISO8859-1 \
  "$root/$run/audit.ebcdic" > "$root/$run/audit.txt"
'&PYTHON' "$root/scripts/audit_to_json.py" \
  --input "$root/$run/audit.txt" \
  --output "$root/$run/audit.candidate.jsonl" --encoding ascii
/*
//JSONOK   IF (NOT TOJSON.ABEND AND TOJSON.RC = 0) THEN
//* Report reads native datasets; it does not parse USS JSON.
//REPORT   EXEC PGM=&TSOPGM,DYNAMNBR=20
//SYSEXEC  DD DSN=&HLQ..STKCP.REXX,DISP=SHR
//AUDIT    DD DSN=*.RUNCOB.AUDIT,DISP=(OLD,PASS,DELETE)
//SETTLE   DD DSN=*.RUNCOB.SETTLE,DISP=(OLD,PASS,DELETE)
//ORDERS   DD DSN=&HLQ..STKCP.ORDERS,DISP=SHR
//SYSTSPRT DD SYSOUT=*
//SYSPRINT DD SYSOUT=*
//SYSTSIN  DD *
  %REPORT
/*
//REPOK    IF (NOT REPORT.ABEND AND REPORT.RC = 0) THEN
//* This step ONLY catalogs validated datasets; REXX did the balance.
//* The final USS SUCCESS marker is still required for acceptance.
//CATALOG  EXEC PGM=IEFBR14
//SETTLE   DD DSN=*.RUNCOB.SETTLE,DISP=(OLD,CATLG,DELETE)
//AUDIT    DD DSN=*.RUNCOB.AUDIT,DISP=(OLD,CATLG,DELETE)
//HOLDOUT  DD DSN=*.RUNCOB.HOLDOUT,DISP=(OLD,CATLG,DELETE)
//CATOK    IF (NOT CATALOG.ABEND AND CATALOG.RC = 0) THEN
//COMMIT   EXEC PGM=BPXBATCH,PARM='SH /bin/sh -s'
//STDOUT   DD SYSOUT=*
//STDERR   DD SYSOUT=*
//STDIN    DD *,SYMBOLS=JCLONLY
set -eu
root='&USSROOT'
run='&RUNID'
mv "$root/$run/audit.candidate.jsonl" "$root/$run/audit.jsonl"
printf '%s\n' 'Validated COBOL, JSON, and REXX steps.' \
  > "$root/$run/SUCCESS"
/*
//         ENDIF
//         ENDIF
//         ENDIF
//         ENDIF
//         ENDIF
//         ENDIF
//* EVEN allows visible failure diagnostics following an abend.
//* Do not infer success from this diagnostic step's own RC0.
//DIAG     EXEC PGM=IEBGENER,COND=EVEN
//SYSPRINT DD SYSOUT=*
//SYSUT1   DD *
STKCP: inspect RUNCOB, PREPARE, EXPORT, TOJSON, REPORT, CATALOG,
and COMMIT completion codes. Any abend or nonzero RC is a failure.
Success requires COMMIT RC0 AND the unique run's USS SUCCESS marker.
Absent prerequisites skip dependent work. Failed runs are not accepted.
Catalog and USS rename are not one transaction; see docs/zos-setup.md.
/*
//SYSUT2   DD SYSOUT=*
//SYSIN    DD DUMMY
