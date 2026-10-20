/* REXX: STKCP fixed-record reconciliation report. TSO/E only. */
/* DDs: AUDIT and SETTLE FB110, ORDERS FB59. No JSON parsing. */
/* Return 0: validated report; 8: I/O/contract/balance failure. */
numeric digits 31
address TSO
audit. = ''
settle. = ''
orders. = ''
audit.0 = 0
settle.0 = 0
orders.0 = 0
errors = 0
settled = 0
pending = 0
rejected = 0
unknown = 0
say 'STKCP EXPLAINABLE RECONCILIATION'
say 'Historical batch simulation; amounts are integer INR paise.'

/* Limit reads to one beyond the documented maximum. RC2 is EOF. */
"EXECIO 1001 DISKR AUDIT (STEM audit. FINIS"
readrc = rc
if readrc <> 0 & readrc <> 2 then do
  say 'ERROR: EXECIO AUDIT failed, RC='readrc
  exit 8
end
"EXECIO 1001 DISKR SETTLE (STEM settle. FINIS"
readrc = rc
if readrc <> 0 & readrc <> 2 then do
  say 'ERROR: EXECIO SETTLE failed, RC='readrc
  exit 8
end
"EXECIO 1001 DISKR ORDERS (STEM orders. FINIS"
readrc = rc
if readrc <> 0 & readrc <> 2 then do
  say 'ERROR: EXECIO ORDERS failed, RC='readrc
  exit 8
end
if audit.0 > 1000 | settle.0 > 1000 | orders.0 > 1000 then do
  say 'ERROR: more than the supported 1000 records.'
  exit 8
end
if audit.0 <> orders.0 then do
  say 'ERROR: audit count differs from input order count.'
  errors = errors + 1
end
if audit.0 <> settle.0 then do
  say 'ERROR: audit count differs from settlement count.'
  errors = errors + 1
end

do i = 1 to orders.0
  if length(orders.i) <> 59 then do
    say 'ERROR: order record' i 'does not contain 59 bytes.'
    errors = errors + 1
  end
end
do i = 1 to settle.0
  if length(settle.i) <> 110 then do
    say 'ERROR: settlement record' i 'does not contain 110 bytes.'
    errors = errors + 1
  end
end
do i = 1 to audit.0
  row = audit.i
  if length(row) <> 110 then do
    say 'ERROR: audit record' i 'does not contain 110 bytes.'
    errors = errors + 1
    iterate
  end
  if i <= settle.0 then do
    if row \== settle.i then do
      say 'ERROR: audit/settlement bytes differ at record' i
      errors = errors + 1
    end
  end
  if i <= orders.0 then do
    if substr(row,1,59) \== orders.i then do
      say 'ERROR: audit/input trace differs at record' i
      errors = errors + 1
    end
  end
  orderid = strip(substr(row,1,12))
  status = strip(substr(row,60,8))
  reason = strip(substr(row,68,7))
  select
    when status = 'SETTLED' then settled = settled + 1
    when status = 'PENDING' then pending = pending + 1
    when status = 'REJECTED' then rejected = rejected + 1
    otherwise do
      unknown = unknown + 1
      errors = errors + 1
      say 'ERROR: unknown status at record' i ':' status
    end
  end
  expected = ReasonStatus(reason)
  explanation = Explain(reason)
  if expected = '' then do
    say 'ERROR: unknown reason at record' i ':' reason
    errors = errors + 1
  end
  else if status <> expected then do
    say 'ERROR: status/reason mismatch at record' i
    errors = errors + 1
  end
  if substr(row,60,8) \== left(status,8) |,
     substr(row,68,7) \== left(reason,7) then do
    say 'ERROR: noncanonical status/reason padding at record' i
    errors = errors + 1
  end
  qty = substr(row,30,6)
  limitprice = substr(row,36,10)
  refprice = substr(row,75,10)
  execprice = substr(row,85,10)
  notional = substr(row,95,16)
  derivedok = DigitsOnly(refprice) & DigitsOnly(execprice) &,
              DigitsOnly(notional)
  if \derivedok then do
    say 'ERROR: nonnumeric derived audit values at record' i
    errors = errors + 1
  end
  else do
    if status <> 'SETTLED' & execprice <> 0 then do
      say 'ERROR: unexecuted order has execution price, record' i
      errors = errors + 1
    end
    if status = 'SETTLED' & (execprice = 0 | refprice = 0) then do
      say 'ERROR: settled order lacks prices, record' i
      errors = errors + 1
    end
    if DigitsOnly(qty) then do
      if notional <> qty * refprice then do
        say 'ERROR: incorrect reference notional, record' i
        errors = errors + 1
      end
    end
    else if reason <> 'DATA001' then do
      say 'ERROR: invalid quantity without DATA001, record' i
      errors = errors + 1
    end
  end
  if reason <> 'DATA001' then do
    if \DigitsOnly(qty) | \DigitsOnly(limitprice) then do
      say 'ERROR: invalid original numeric fields, record' i
      errors = errors + 1
    end
    else if qty = 0 | limitprice = 0 then do
      say 'ERROR: nonpositive order numeric fields, record' i
      errors = errors + 1
    end
  end
  if status <> 'SETTLED' | expected = '' then do
    say 'Record' i 'order='orderid 'status='status 'reason='reason
    say '  'explanation
  end
end

say 'INPUT RECORDS:' orders.0
say 'AUDIT RECORDS:' audit.0
say 'SETTLEMENT RECORDS:' settle.0
say 'SETTLED:' settled 'PENDING:' pending 'REJECTED:' rejected
say 'UNKNOWN STATUS:' unknown
if audit.0 = 0 then say 'Empty batch: no orders to classify.'
if errors <> 0 then do
  say 'BALANCE FAILED: validation errors='errors
  say 'No successful batch may be published from this report.'
  exit 8
end
say 'BALANCED: input count = audit count = settlement count.'
say 'Every audit record matches settlement bytes and input tracing.'
say 'Status totals are classifications, not successful settlements.'
exit 0

DigitsOnly: procedure
  parse arg field
  return length(field) > 0 & verify(field,'0123456789') = 0

ReasonStatus: procedure
  parse arg code
  select
    when code = 'OK000' then return 'SETTLED'
    when code = 'PEND01' then return 'PENDING'
    when wordpos(code,'DUP001 HOLD01 PRICE01 DATA001 SIDE001') > 0,
      then return 'REJECTED'
    otherwise return ''
  end

Explain: procedure
  parse arg code
  select
    when code = 'OK000' then return,
      'Order settled under the deterministic batch matching rules.'
    when code = 'PEND01' then return,
      'No compatible counter-order was available in this batch.'
    when code = 'DUP001' then return,
      'Order ID duplicates an earlier structurally valid order.'
    when code = 'HOLD01' then return,
      'SELL quantity exceeds available seeded holdings after reservations.'
    when code = 'PRICE01' then return,
      'Historical reference is missing, stale, or outside the allowed',
      'price band.'
    when code = 'DATA001' then return,
      'Order record has invalid length, identifiers, numeric fields,',
      'or timestamp.'
    when code = 'SIDE001' then return,
      'Side must be B (BUY) or S (SELL).'
    otherwise return,
      'Unrecognized reason code; inspect the audit record.'
  end
