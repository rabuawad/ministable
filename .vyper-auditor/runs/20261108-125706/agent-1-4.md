[Feynman: modules/cdp/cdp.vy] The module tracks collateral, debt, interest, liquidations, and redemptions. Its accounting assumes each wrapper transfers the recorded collateral amount.

[Feynman: modules/cdp/cdp_erc20.vy] The wrapper takes and sends collateral tokens. Its accounting assumes a token charges no extra amount to the sender on an outgoing transfer.

[Feynman: modules/cdp/cdp_native.vy] The wrapper takes native coin and sends it after the shared module updates accounting. Its calls assume the receiver accepts the coin.

[Feynman: modules/tokens/erc20.vy] The module tracks stablecoin balances, allowances, and signatures. Its callers assume token operations preserve the relationship between balances and total supply.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does the wrapper measure the token balance on receipt but trust the requested amount on payment?

[Inversion: _push] A borrower withdraws with a sender-fee token; a liquidator receives a taxed transfer; a redeemer sets `min_paid` above the tokens actually received.

[Inversion: _liquidate] A caller supplies a small `max_repay`; a position has collateral below its debt; a token rejects a transfer of zero units.

[Inversion: burn] A borrower submits the displayed debt; interest accrues before inclusion; the requested amount becomes a partial repayment.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow  
path: Borrower → `withdraw` → `_withdraw` debits recorded collateral → `_push` transfers tokens and incurs an additional sender fee → other depositors lose backing.  
input: A borrower withdraws 100 tokens from a collateral token that charges the sender an additional 10% fee.  
assumption: The token reduces the contract balance by exactly the requested transfer amount.  
proof: Alice and Bob each deposit 100 tokens, and the contract receives 200. Alice withdraws 100; accounting leaves Bob with 100, but the token debits 110, so the contract holds 90. Bob cannot withdraw his full 100. The same `_push` path serves `liquidate`, `redeem`, and `cover_bad_debt`.  
description: A borrower can withdraw with a sender-fee token and leave other borrowers without their full collateral.  
fix: The wrapper should reject transfers that reduce its token balance by more than the accounted amount.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert  
code_smells: The wrapper calls `_push(msg.sender, seized)` when `seized` is zero.  
unverified: Confirm that a supported collateral token rejects zero-value transfers and that a profitable liquidation requires this zero-value path.  
description: A token that rejects zero transfers can make a liquidation with zero seized collateral revert.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation  
code_smells: The branch below 110% collateral requires `max_repay >= repay` and clears the entire position in one call.  
unverified: Establish a reachable position for which no liquidator can obtain the required mUSD in one transaction and quantify the resulting loss.  
description: A liquidator must supply the full required repayment to close a position below 110% collateral.

LEAD | contract: modules/cdp/cdp.vy | function: burn | bug_class: no-full-repay-path | group_key: modules/cdp/cdp.vy | burn | no-full-repay-path  
code_smells: The caller supplies an exact `amount`, while `_accrue` updates debt before `_repay` checks that amount.  
unverified: Establish whether transaction timing or available client tooling prevents a borrower from supplying the exact debt at inclusion.  
description: A borrower can submit the displayed debt and retain debt when interest accrues before the transaction executes.
