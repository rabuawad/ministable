[Feynman: modules/cdp/cdp.vy] The module tracks collateral, debt, interest, liquidations, redemptions, and reserves. It assumes each wrapper transfers the collateral amount that its accounting records.

[Feynman: modules/cdp/cdp_erc20.vy] The wrapper measures collateral received and sends collateral owed. It assumes the token debits and credits the nominal transfer amount on every outgoing transfer.

[Feynman: modules/cdp/cdp_native.vy] The wrapper receives native coin and sends the amounts calculated by the shared module. Its safety assumes the shared module’s accounting remains synchronized with those transfers.

[Feynman: modules/tokens/erc20.vy] The module tracks mUSD balances, allowances, supply, and permits. Its transfer functions can run during collateral callbacks because its nonreentrancy pragma is off.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] What keeps other users’ collateral intact when a token charges the sender more than the nominal transfer amount?

[Inversion: _push] A borrower withdraws with a sender-fee token; a liquidator receives collateral after a position closes; a redeemer receives collateral while other users retain claims.

[Socratic: modules/cdp/cdp_erc20.vy:redeem — why?] What proves the redeemer receives `min_paid` when the token deducts a fee from the recipient?

[Inversion: _accrue] A caller updates interest frequently; a borrower repays after the index changes; a caller invokes `mint(0)` between interest updates.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
assumption: The collateral token debits the contract by exactly `amount`.
violation: A token charges an additional fee to the sender.
path: borrower → `withdraw` → `cdp._withdraw` reduces the borrower’s claim by `amount` → `_push` transfers `amount` and pays an additional sender fee → other users’ collateral backs the fee.
proof: With 200 collateral units held for two users, a withdrawal of 100 reduces the first claim by 100; a 10% sender fee debits 110, leaving 90 units against the second user’s 100-unit claim.
description: A sender fee consumes collateral that the contract owes to other users.
fix: The wrapper should reject an outgoing transfer unless the contract balance decreases by exactly `amount`.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage
assumption: The redeemer receives the nominal amount returned by `cdp._redeem`.
violation: A token deducts a fee from the recipient’s transfer.
path: redeemer → `redeem` → `cdp._redeem` checks nominal `paid` against `min_paid` → `_push` transfers collateral → the redeemer receives less than `min_paid`.
proof: At a $1 price and 150% collateral ratio, redemption of 100 mUSD sets `paid` to 99.5 collateral units; `min_paid = 99.5` passes, but a 10% recipient fee delivers 89.55 units.
description: A redeemer accepts less collateral than `min_paid` when the token deducts a transfer fee.
fix: The wrapper should check the recipient’s balance increase against `min_paid` after the transfer.

LEAD | contract: modules/cdp/cdp.vy | function: _accrue | bug_class: discarded-interest-fractions | group_key: modules/cdp/cdp.vy | _accrue | discarded-interest-fractions
code_smells: The function floors `fee` on each update and advances `last_accrual` without retaining the remainder.
unverified: A reachable deployment and call frequency must show that the accumulated discarded interest causes material harm.
description: Frequent callers discard fractional interest that the protocol does not mint.

LEAD | contract: modules/cdp/cdp.vy | function: burn | bug_class: no-full-repay-path | group_key: modules/cdp/cdp.vy | burn | no-full-repay-path
code_smells: The caller supplies an exact `amount`, and `_accrue` updates debt before `_repay` compares that amount with debt.
unverified: The deployed fee, transaction timing, and available transaction tooling must show that borrowers cannot reliably close positions.
description: A borrower can retain debt when interest increases after the borrower selects the repayment amount.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The low-collateral branch requires `max_repay >= repay` and clears all debt shares in one call.
unverified: The available mUSD liquidity and position sizes must show that a liquidator cannot obtain the required repayment.
description: A liquidator needs the full repayment in one call when the position has insufficient collateral.
