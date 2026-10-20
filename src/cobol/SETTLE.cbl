       >>SOURCE FORMAT FREE
identification division.
program-id. SETTLE.
*> Local compilation: cobc -x -free -DLOCAL=1 SETTLE.cbl -o settle
*> LOCAL selects newline-delimited ASCII files through DD_<ddname>.
*> Without LOCAL, ordinary sequential FB DDs are used on z/OS.
*> Outputs must be temporary: a caller publishes them only on RC 0.
environment division.
input-output section.
file-control.
    select orders-file
        >>IF LOCAL IS DEFINED
        assign to 'ORDERS'
        organization is line sequential
        >>ELSE
        assign to ORDERS
        organization is sequential
        >>END-IF
        file status is orders-status.
    select holdings-file
        >>IF LOCAL IS DEFINED
        assign to 'HOLDINGS'
        organization is line sequential
        >>ELSE
        assign to HOLDINGS
        organization is sequential
        >>END-IF
        file status is holdings-status.
    select prices-file
        >>IF LOCAL IS DEFINED
        assign to 'PRICES'
        organization is line sequential
        >>ELSE
        assign to PRICES
        organization is sequential
        >>END-IF
        file status is prices-status.
    select settle-file
        >>IF LOCAL IS DEFINED
        assign to 'SETTLE'
        organization is line sequential
        >>ELSE
        assign to SETTLE
        organization is sequential
        >>END-IF
        file status is settle-status.
    select audit-file
        >>IF LOCAL IS DEFINED
        assign to 'AUDIT'
        organization is line sequential
        >>ELSE
        assign to AUDIT
        organization is sequential
        >>END-IF
        file status is audit-status.
    select holdout-file
        >>IF LOCAL IS DEFINED
        assign to 'HOLDOUT'
        organization is line sequential
        >>ELSE
        assign to HOLDOUT
        organization is sequential
        >>END-IF
        file status is holdout-status.
data division.
file section.
fd orders-file
    >>IF LOCAL IS DEFINED
    record is varying in size from 0 to 32760
        depending on order-record-length.
01 order-record pic x(32760).
    >>ELSE
    recording mode is F
    record contains 59 characters.
01 order-record pic x(59).
    >>END-IF
fd holdings-file
    >>IF LOCAL IS DEFINED
    record is varying in size from 0 to 32760
        depending on holding-record-length.
01 holding-record pic x(32760).
    >>ELSE
    recording mode is F
    record contains 26 characters.
01 holding-record pic x(26).
    >>END-IF
fd prices-file
    >>IF LOCAL IS DEFINED
    record is varying in size from 0 to 32760
        depending on price-record-length.
01 price-record pic x(32760).
    >>ELSE
    recording mode is F
    record contains 32 characters.
01 price-record pic x(32).
    >>END-IF
fd settle-file
    >>IF LOCAL IS DEFINED
    >>ELSE
    recording mode is F
    >>END-IF
    record contains 110 characters.
01 settle-record pic x(110).
fd audit-file
    >>IF LOCAL IS DEFINED
    >>ELSE
    recording mode is F
    >>END-IF
    record contains 110 characters.
01 audit-record pic x(110).
fd holdout-file
    >>IF LOCAL IS DEFINED
    >>ELSE
    recording mode is F
    >>END-IF
    record contains 56 characters.
01 holdout-record pic x(56).
working-storage section.
01 io-statuses.
    05 orders-status pic xx value spaces.
    05 holdings-status pic xx value spaces.
    05 prices-status pic xx value spaces.
    05 settle-status pic xx value spaces.
    05 audit-status pic xx value spaces.
    05 holdout-status pic xx value spaces.
01 open-flags.
    05 orders-open pic 9 value 0.
    05 holdings-open pic 9 value 0.
    05 prices-open pic 9 value 0.
    05 settle-open pic 9 value 0.
    05 audit-open pic 9 value 0.
    05 holdout-open pic 9 value 0.
01 fatal-flag pic x value 'N'.
    88 fatal-error value 'Y'.
01 eof-flag pic x value 'N'.
    88 end-of-input value 'Y'.
01 error-message pic x(120) value spaces.
01 order-record-length binary-long value 59.
01 holding-record-length binary-long value 26.
01 price-record-length binary-long value 32.
01 order-count binary-long value 0.
01 holding-count binary-long value 0.
01 price-count binary-long value 0.
01 settled-count binary-long value 0.
01 pending-count binary-long value 0.
01 rejected-count binary-long value 0.
01 i binary-long value 0.
01 j binary-long value 0.
01 k binary-long value 0.
01 h binary-long value 0.
01 scan-index binary-long value 0.
01 buy-index binary-long value 0.
01 sell-index binary-long value 0.
01 match-index binary-long value 0.
01 found-holding binary-long value 0.
01 structurally-valid pic 9 value 0.
01 duplicate-found pic 9 value 0.
01 max-order-seconds pic 9(15) comp-3 value 0.
01 order-table.
    05 order-entry occurs 1000 times.
        10 t-original.
            15 t-id pic x(12).
            15 t-client pic x(8).
            15 t-stock pic x(8).
            15 t-side pic x.
            15 t-quantity-text pic x(6).
            15 t-limit-text pic x(10).
            15 t-timestamp pic x(14).
        10 t-quantity pic 9(6) comp-3.
        10 t-limit pic 9(10) comp-3.
        10 t-seconds pic 9(15) comp-3.
        10 t-status pic x(8).
            88 t-settled value 'SETTLED '.
            88 t-pending value 'PENDING '.
            88 t-rejected value 'REJECTED'.
        10 t-reason pic x(7).
            88 t-ok value 'OK000  '.
            88 t-unmatched value 'PEND01 '.
            88 t-duplicate value 'DUP001 '.
            88 t-insufficient value 'HOLD01 '.
            88 t-price-failed value 'PRICE01'.
            88 t-data-failed value 'DATA001'.
            88 t-side-failed value 'SIDE001'.
        10 t-id-reserved pic 9.
        10 t-holding binary-long.
        10 t-reference pic 9(10) comp-3.
        10 t-execution pic 9(10) comp-3.
        10 t-notional pic 9(16) comp-3.
01 holding-table.
    05 holding-entry occurs 1000 times.
        10 h-client pic x(8).
        10 h-stock pic x(8).
        10 h-quantity pic 9(10) comp-3.
        10 h-reserved pic 9(10) comp-3.
01 price-table.
    05 price-entry occurs 5000 times.
        10 p-stock pic x(8).
        10 p-timestamp pic x(14).
        10 p-seconds pic 9(15) comp-3.
        10 p-price pic 9(10) comp-3.
01 holding-input.
    05 in-h-client pic x(8).
    05 in-h-stock pic x(8).
    05 in-h-quantity pic x(10).
01 price-input.
    05 in-p-stock pic x(8).
    05 in-p-timestamp pic x(14).
    05 in-p-price pic x(10).
01 previous-price-key pic x(22) value spaces.
01 current-price-key pic x(22) value spaces.
01 price-key-order binary-long value 0.
01 key-index binary-long value 0.
01 current-key-rank binary-long value 0.
01 previous-key-rank binary-long value 0.
01 current-key-character pic x.
01 previous-key-character pic x.
01 ascii-key-order pic x(39)
    value ' -0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_'.
01 holding-search.
    05 search-client pic x(8).
    05 search-stock pic x(8).
01 reference-search.
    05 reference-stock pic x(8).
    05 reference-seconds pic 9(15) comp-3.
    05 reference-price pic 9(10) comp-3.
    05 reference-time pic 9(15) comp-3.
01 available-quantity pic 9(10) comp-3 value 0.
01 band-order pic 9(13) comp-3 value 0.
01 band-low pic 9(13) comp-3 value 0.
01 band-high pic 9(13) comp-3 value 0.
01 identifier-check.
    05 identifier-value pic x(12).
    05 identifier-width binary-long.
    05 identifier-valid pic 9.
    05 identifier-padding pic 9.
    05 identifier-index binary-long.
    05 identifier-character pic x.
    05 character-count binary-long.
    05 allowed-characters pic x(38)
        value 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-'.
01 timestamp-check.
    05 check-timestamp pic x(14).
    05 timestamp-valid pic 9.
    05 timestamp-seconds pic 9(15) comp-3.
    05 stamp-year binary-long.
    05 stamp-month binary-long.
    05 stamp-day binary-long.
    05 stamp-hour binary-long.
    05 stamp-minute binary-long.
    05 stamp-second binary-long.
    05 month-days binary-long.
    05 stamp-date pic 9(8).
01 result-record.
    05 out-original pic x(59).
    05 out-status pic x(8).
    05 out-reason pic x(7).
    05 out-reference pic 9(10).
    05 out-execution pic 9(10).
    05 out-notional pic 9(16).
01 holding-result.
    05 out-h-client pic x(8).
    05 out-h-stock pic x(8).
    05 out-h-quantity pic 9(10).
    05 out-h-reference pic 9(10).
    05 out-h-valuation pic 9(20).
procedure division.
main.
    initialize order-table holding-table price-table
    perform load-holdings
    if not fatal-error perform load-prices end-if
    if not fatal-error perform load-orders end-if
    perform close-inputs
    if not fatal-error perform match-orders end-if
    if not fatal-error perform write-results end-if
    perform close-outputs
    if fatal-error
        move 12 to return-code
    else
        display 'SETTLE orders=' order-count
            ' settled=' settled-count ' pending=' pending-count
            ' rejected=' rejected-count
        move 0 to return-code
    end-if
    goback.

fail-run.
    set fatal-error to true
    display 'SETTLE FATAL: ' function trim(error-message).

load-holdings.
    open input holdings-file
    if holdings-status not = '00'
        move 'OPEN HOLDINGS failed' to error-message
        perform fail-run
    else
        move 1 to holdings-open
        move 'N' to eof-flag
        perform until end-of-input or fatal-error
            move spaces to holding-record
            read holdings-file
            evaluate holdings-status
                when '10' set end-of-input to true
                when '00' perform accept-holding
                when other
                    move 'READ HOLDINGS failed or invalid length'
                        to error-message
                    perform fail-run
            end-evaluate
        end-perform
    end-if.

accept-holding.
    if holding-record-length not = 26
        move 'HOLDINGS record length must be 26' to error-message
        perform fail-run
        exit paragraph
    end-if
    move holding-record(1:26) to holding-input
    move in-h-client to identifier-value
    move 8 to identifier-width
    perform validate-identifier
    if identifier-valid = 0
        move 'HOLDINGS invalid client identifier' to error-message
        perform fail-run
        exit paragraph
    end-if
    move in-h-stock to identifier-value
    perform validate-identifier
    if identifier-valid = 0 or in-h-quantity is not numeric
        move 'HOLDINGS invalid symbol or quantity' to error-message
        perform fail-run
        exit paragraph
    end-if
    move in-h-client to search-client
    move in-h-stock to search-stock
    perform find-holding
    if found-holding not = 0
        move 'HOLDINGS duplicate client/symbol' to error-message
        perform fail-run
        exit paragraph
    end-if
    if holding-count = 1000
        move 'HOLDINGS table capacity 1000 exceeded' to error-message
        perform fail-run
        exit paragraph
    end-if
    add 1 to holding-count
    move search-client to h-client(holding-count)
    move search-stock to h-stock(holding-count)
    move function numval(in-h-quantity) to h-quantity(holding-count)
    move 0 to h-reserved(holding-count).

load-prices.
    open input prices-file
    if prices-status not = '00'
        move 'OPEN PRICES failed' to error-message
        perform fail-run
    else
        move 1 to prices-open
        move 'N' to eof-flag
        perform until end-of-input or fatal-error
            move spaces to price-record
            read prices-file
            evaluate prices-status
                when '10' set end-of-input to true
                when '00' perform accept-price
                when other
                    move 'READ PRICES failed or invalid length'
                        to error-message
                    perform fail-run
            end-evaluate
        end-perform
    end-if.

accept-price.
    if price-record-length not = 32
        move 'PRICES record length must be 32' to error-message
        perform fail-run
        exit paragraph
    end-if
    move price-record(1:32) to price-input
    move in-p-stock to identifier-value
    move 8 to identifier-width
    perform validate-identifier
    if identifier-valid = 0 or in-p-price is not numeric
        move 'PRICES invalid symbol or numeric price' to error-message
        perform fail-run
        exit paragraph
    end-if
    if function numval(in-p-price) = 0
        move 'PRICES price must be positive' to error-message
        perform fail-run
        exit paragraph
    end-if
    move in-p-timestamp to check-timestamp
    perform validate-timestamp
    if timestamp-valid = 0
        move 'PRICES invalid calendar timestamp' to error-message
        perform fail-run
        exit paragraph
    end-if
    move price-record(1:22) to current-price-key
    if price-count > 0
        perform compare-price-keys
        if price-key-order <= 0
            move 'PRICES duplicate or unsorted symbol/timestamp'
                to error-message
            perform fail-run
            exit paragraph
        end-if
    end-if
    if price-count = 5000
        move 'PRICES table capacity 5000 exceeded' to error-message
        perform fail-run
        exit paragraph
    end-if
    add 1 to price-count
    move in-p-stock to p-stock(price-count)
    move in-p-timestamp to p-timestamp(price-count)
    move timestamp-seconds to p-seconds(price-count)
    move function numval(in-p-price) to p-price(price-count)
    move current-price-key to previous-price-key.

load-orders.
    open input orders-file
    if orders-status not = '00'
        move 'OPEN ORDERS failed' to error-message
        perform fail-run
    else
        move 1 to orders-open
        move 'N' to eof-flag
        perform until end-of-input or fatal-error
            move spaces to order-record
            move 59 to order-record-length
            read orders-file
            evaluate orders-status
                when '10' set end-of-input to true
                when '00' perform accept-order
                when '04'
                    *> A readable size-mismatched order is traceable.
                    move 0 to order-record-length
                    perform accept-order
                when other
                    move 'READ ORDERS failed' to error-message
                    perform fail-run
            end-evaluate
        end-perform
    end-if.

accept-order.
    if order-count = 1000
        move 'ORDERS table capacity 1000 exceeded' to error-message
        perform fail-run
        exit paragraph
    end-if
    add 1 to order-count
    move order-count to i
    initialize order-entry(i)
    move order-record(1:59) to t-original(i)
    set t-rejected(i) t-data-failed(i) to true
    perform check-order-structure
    if structurally-valid = 0 exit paragraph end-if
    *> Every structural timestamp participates in final valuation time.
    if t-seconds(i) > max-order-seconds
        move t-seconds(i) to max-order-seconds
    end-if
    move 0 to duplicate-found
    perform varying j from 1 by 1 until j >= i
        if t-id-reserved(j) = 1 and t-id(j) = t-id(i)
            move 1 to duplicate-found
        end-if
    end-perform
    if duplicate-found = 1
        set t-duplicate(i) to true
        exit paragraph
    end-if
    *> Reserve before side/price/holdings checks, never for malformed rows.
    move 1 to t-id-reserved(i)
    if t-side(i) not = 'B' and t-side(i) not = 'S'
        set t-side-failed(i) to true
        exit paragraph
    end-if
    move t-stock(i) to reference-stock
    move t-seconds(i) to reference-seconds
    perform find-reference
    move reference-price to t-reference(i)
    compute t-notional(i) = t-quantity(i) * reference-price
    set t-price-failed(i) to true
    if reference-price = 0 exit paragraph end-if
    compute band-order = t-limit(i) * 100
    compute band-low = reference-price * 90
    compute band-high = reference-price * 110
    if band-order < band-low or band-order > band-high
        exit paragraph
    end-if
    move t-client(i) to search-client
    move t-stock(i) to search-stock
    perform find-holding
    if t-side(i) = 'S'
        set t-insufficient(i) to true
        if found-holding = 0 exit paragraph end-if
        compute available-quantity = h-quantity(found-holding)
            - h-reserved(found-holding)
        if t-quantity(i) > available-quantity exit paragraph end-if
        add t-quantity(i) to h-reserved(found-holding)
            on size error
                move 'SELL reservation arithmetic overflow'
                    to error-message
                perform fail-run
        end-add
    else
        *> Include valid pending buyers as zero-quantity holdings entries.
        if found-holding = 0
            if holding-count = 1000
                move 'New BUY exceeds HOLDINGS table capacity 1000'
                    to error-message
                perform fail-run
                exit paragraph
            end-if
            add 1 to holding-count
            move holding-count to found-holding
            initialize holding-entry(found-holding)
            move search-client to h-client(found-holding)
            move search-stock to h-stock(found-holding)
        end-if
    end-if
    if fatal-error exit paragraph end-if
    move found-holding to t-holding(i)
    set t-pending(i) t-unmatched(i) to true.

check-order-structure.
    move 0 to structurally-valid
    if order-record-length not = 59 exit paragraph end-if
    move t-id(i) to identifier-value
    move 12 to identifier-width
    perform validate-identifier
    if identifier-valid = 0 exit paragraph end-if
    move t-client(i) to identifier-value
    move 8 to identifier-width
    perform validate-identifier
    if identifier-valid = 0 exit paragraph end-if
    move t-stock(i) to identifier-value
    perform validate-identifier
    if identifier-valid = 0 exit paragraph end-if
    if t-quantity-text(i) is not numeric
        or t-limit-text(i) is not numeric
        exit paragraph
    end-if
    move function numval(t-quantity-text(i)) to t-quantity(i)
    move function numval(t-limit-text(i)) to t-limit(i)
    if t-quantity(i) = 0 or t-limit(i) = 0 exit paragraph end-if
    move t-timestamp(i) to check-timestamp
    perform validate-timestamp
    if timestamp-valid = 0 exit paragraph end-if
    move timestamp-seconds to t-seconds(i)
    move 1 to structurally-valid.

validate-identifier.
    move 1 to identifier-valid
    move 0 to identifier-padding
    if identifier-value(1:1) = space
        move 0 to identifier-valid
    end-if
    perform varying identifier-index from 1 by 1
        until identifier-index > identifier-width
        move identifier-value(identifier-index:1)
            to identifier-character
        if identifier-character = space
            move 1 to identifier-padding
        else
            if identifier-padding = 1
                move 0 to identifier-valid
            end-if
            move 0 to character-count
            inspect allowed-characters tallying character-count
                for all identifier-character
            if character-count = 0 move 0 to identifier-valid end-if
        end-if
    end-perform.

validate-timestamp.
    move 0 to timestamp-valid timestamp-seconds
    if check-timestamp is not numeric exit paragraph end-if
    move function numval(check-timestamp(1:4)) to stamp-year
    move function numval(check-timestamp(5:2)) to stamp-month
    move function numval(check-timestamp(7:2)) to stamp-day
    move function numval(check-timestamp(9:2)) to stamp-hour
    move function numval(check-timestamp(11:2)) to stamp-minute
    move function numval(check-timestamp(13:2)) to stamp-second
    if stamp-year < 1601 or stamp-year > 9999
        or stamp-month < 1 or stamp-month > 12
        or stamp-day < 1 or stamp-hour > 23
        or stamp-minute > 59 or stamp-second > 59
        exit paragraph
    end-if
    evaluate stamp-month
        when 4 when 6 when 9 when 11 move 30 to month-days
        when 2
            move 28 to month-days
            if function mod(stamp-year, 400) = 0
                or (function mod(stamp-year, 4) = 0
                    and function mod(stamp-year, 100) not = 0)
                move 29 to month-days
            end-if
        when other move 31 to month-days
    end-evaluate
    if stamp-day > month-days exit paragraph end-if
    compute stamp-date = stamp-year * 10000
        + stamp-month * 100 + stamp-day
    compute timestamp-seconds = function integer-of-date(stamp-date)
        * 86400 + stamp-hour * 3600 + stamp-minute * 60 + stamp-second
    move 1 to timestamp-valid.

compare-price-keys.
    *> Match Python ASCII ordering even when compiled in native EBCDIC.
    *> Identifiers have already been checked against the finite alphabet.
    move 0 to price-key-order
    perform varying key-index from 1 by 1
        until key-index > 8 or price-key-order not = 0
        move current-price-key(key-index:1) to current-key-character
        move previous-price-key(key-index:1) to previous-key-character
        if current-key-character not = previous-key-character
            move 0 to current-key-rank previous-key-rank
            inspect ascii-key-order tallying current-key-rank
                for characters before initial current-key-character
            inspect ascii-key-order tallying previous-key-rank
                for characters before initial previous-key-character
            compute price-key-order = current-key-rank
                - previous-key-rank
        end-if
    end-perform
    if price-key-order = 0
        evaluate true
            when current-price-key(9:14) < previous-price-key(9:14)
                move -1 to price-key-order
            when current-price-key(9:14) > previous-price-key(9:14)
                move 1 to price-key-order
        end-evaluate
    end-if.

find-holding.
    move 0 to found-holding
    perform varying scan-index from 1 by 1
        until scan-index > holding-count or found-holding not = 0
        if h-client(scan-index) = search-client
            and h-stock(scan-index) = search-stock
            move scan-index to found-holding
        end-if
    end-perform.

find-reference.
    move 0 to reference-price reference-time
    perform varying k from 1 by 1 until k > price-count
        if p-stock(k) = reference-stock
            and p-seconds(k) <= reference-seconds
            and p-seconds(k) >= reference-time
            move p-price(k) to reference-price
            move p-seconds(k) to reference-time
        end-if
    end-perform
    if reference-price not = 0
        and reference-seconds - reference-time > 604800
        move 0 to reference-price
    end-if.

match-orders.
    perform varying i from 1 by 1 until i > order-count or fatal-error
        if t-pending(i)
            move 0 to match-index
            compute j = i + 1
            perform until j > order-count or match-index not = 0
                if t-pending(j) and t-stock(j) = t-stock(i)
                    and t-quantity(j) = t-quantity(i)
                    and t-side(j) not = t-side(i)
                    and t-client(j) not = t-client(i)
                    if t-side(i) = 'B'
                        move i to buy-index
                        move j to sell-index
                    else
                        move j to buy-index
                        move i to sell-index
                    end-if
                    if t-limit(buy-index) >= t-limit(sell-index)
                        move j to match-index
                    end-if
                end-if
                add 1 to j
            end-perform
            if match-index not = 0 perform settle-pair end-if
        end-if
    end-perform.

settle-pair.
    move t-holding(sell-index) to h
    if h < 1 or h > holding-count
        move 'Internal SELL holding index invalid' to error-message
        perform fail-run
        exit paragraph
    end-if
    if h-quantity(h) < t-quantity(sell-index)
        move 'Internal SELL would create negative holdings'
            to error-message
        perform fail-run
        exit paragraph
    end-if
    subtract t-quantity(sell-index) from h-quantity(h)
        on size error
            move 'SELL holdings arithmetic overflow' to error-message
            perform fail-run
    end-subtract
    move t-holding(buy-index) to h
    if h < 1 or h > holding-count
        move 'Internal BUY holding index invalid' to error-message
        perform fail-run
        exit paragraph
    end-if
    add t-quantity(buy-index) to h-quantity(h)
        on size error
            move 'BUY holdings arithmetic overflow' to error-message
            perform fail-run
    end-add
    if fatal-error exit paragraph end-if
    move t-limit(sell-index) to t-execution(buy-index)
        t-execution(sell-index)
    set t-settled(buy-index) t-settled(sell-index) to true
    set t-ok(buy-index) t-ok(sell-index) to true.

write-results.
    open output settle-file
    if settle-status = '00'
        move 1 to settle-open
    else
        move 'OPEN SETTLE failed' to error-message
        perform fail-run
    end-if
    if not fatal-error
        open output audit-file
        if audit-status = '00'
            move 1 to audit-open
        else
            move 'OPEN AUDIT failed' to error-message
            perform fail-run
        end-if
    end-if
    if not fatal-error
        open output holdout-file
        if holdout-status = '00'
            move 1 to holdout-open
        else
            move 'OPEN HOLDOUT failed' to error-message
            perform fail-run
        end-if
    end-if
    perform varying i from 1 by 1 until i > order-count or fatal-error
        move t-original(i) to out-original
        move t-status(i) to out-status
        move t-reason(i) to out-reason
        move t-reference(i) to out-reference
        move t-execution(i) to out-execution
        move t-notional(i) to out-notional
        write settle-record from result-record
        if settle-status not = '00'
            move 'WRITE SETTLE failed' to error-message
            perform fail-run
        end-if
        if not fatal-error
            write audit-record from result-record
            if audit-status not = '00'
                move 'WRITE AUDIT failed' to error-message
                perform fail-run
            end-if
        end-if
        evaluate true
            when t-settled(i) add 1 to settled-count
            when t-pending(i) add 1 to pending-count
            when t-rejected(i) add 1 to rejected-count
        end-evaluate
    end-perform
    perform varying h from 1 by 1 until h > holding-count or fatal-error
        move h-client(h) to out-h-client
        move h-stock(h) to out-h-stock reference-stock
        move h-quantity(h) to out-h-quantity
        move max-order-seconds to reference-seconds
        perform find-reference
        move reference-price to out-h-reference
        compute out-h-valuation = h-quantity(h) * reference-price
            on size error
                move 'HOLDOUT valuation arithmetic overflow'
                    to error-message
                perform fail-run
        end-compute
        if not fatal-error
            write holdout-record from holding-result
            if holdout-status not = '00'
                move 'WRITE HOLDOUT failed' to error-message
                perform fail-run
            end-if
        end-if
    end-perform.

close-inputs.
    if holdings-open = 1
        close holdings-file
        move 0 to holdings-open
        if holdings-status not = '00'
            move 'CLOSE HOLDINGS failed' to error-message
            perform fail-run
        end-if
    end-if
    if prices-open = 1
        close prices-file
        move 0 to prices-open
        if prices-status not = '00'
            move 'CLOSE PRICES failed' to error-message
            perform fail-run
        end-if
    end-if
    if orders-open = 1
        close orders-file
        move 0 to orders-open
        if orders-status not = '00'
            move 'CLOSE ORDERS failed' to error-message
            perform fail-run
        end-if
    end-if.

close-outputs.
    if settle-open = 1
        close settle-file
        move 0 to settle-open
        if settle-status not = '00'
            move 'CLOSE SETTLE failed' to error-message
            perform fail-run
        end-if
    end-if
    if audit-open = 1
        close audit-file
        move 0 to audit-open
        if audit-status not = '00'
            move 'CLOSE AUDIT failed' to error-message
            perform fail-run
        end-if
    end-if
    if holdout-open = 1
        close holdout-file
        move 0 to holdout-open
        if holdout-status not = '00'
            move 'CLOSE HOLDOUT failed' to error-message
            perform fail-run
        end-if
    end-if.
end program SETTLE.
