//STKCOMP JOB (SITEACCT),'STKCP BUILD',CLASS=A,MSGCLASS=H,
//             NOTIFY=&SYSUID
//* UNVERIFIED SITE-PROC TEMPLATE; see docs/zos-setup.md.
//* Replace JOB card. Identify a permitted Enterprise COBOL PROC first.
//         SET HLQ=YOURHLQ
//         SET COBPROC=SITEPROC
//* Add a site-approved JCLLIB ORDER statement if its PROC needs one.
//* REQUIRED: PROC steps named COBOL and LKED with the DDs below.
//* Otherwise adapt the overrides to the actual documented PROC names.
//* REQUIRED: PROC must skip link after compile RC > 4 or an abend.
//* Review RC4 warnings before treating a build as usable.
//* Check FREE, SSRANGE and NUMCHECK options against compiler version.
//BUILD    EXEC &COBPROC,
//             PARM.COBOL='SOURCEFORMAT(FREE),SSRANGE,NUMCHECK'
//COBOL.SYSIN DD DSN=&HLQ..STKCP.COBOL(SETTLE),DISP=SHR
//COBOL.SYSLIB DD DSN=&HLQ..STKCP.COPYLIB,DISP=SHR
//COBOL.SYSPRINT DD SYSOUT=*
//LKED.SYSLMOD DD DSN=&HLQ..STKCP.LOAD(SETTLE),DISP=SHR
//LKED.SYSPRINT DD SYSOUT=*
//* Inspect compiler and binder listings. A job's existence is no test.
