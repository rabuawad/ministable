[Feynman: cdp_erc20] The wrapper receives collateral and sends it after the CDP changes its records; it assumes the token’s transfer side effects match the recorded amount.

[Feynman: cdp_native] The wrapper receives native coin and sends it after the CDP changes its records; it assumes the recipient accepts the payment.

[Feynman: cdp] The module tracks collateral, debt, interest, liquidations, redemptions, and reserves; its exported functions use the host’s token state.

[Feynman: erc20] The module tracks stablecoin balances and approvals; `permit` assumes the imported signature helper identifies the signer correctly.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does a successful token transfer prove that the contract lost exactly `amount` and the recipient received exactly `amount`?

[Inversion: redeem] A caller sets `min_paid`; a token deducts a recipient fee; a token upgrade introduces that fee after deployment.

[Inversion: _push] A borrower withdraws against another borrower’s balance; a token charges the sender extra; a liquidation uses the same transfer helper.

[Inversion: _liquidate] A liquidator supplies a small `max_repay`; a position has less than 110% collateral; a coarse token rounds the payout to zero.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
boundary: Collateral token transfer from the ERC-20 wrapper.
assumption: The wrapper assumes a transfer of `amount` reduces its balance by exactly `amount`.
path: Borrower → `withdraw` → `cdp._withdraw` debits the requested amount → `_push` pays a sender-side fee from pooled collateral → other depositors lose collateral.
proof: If two users each deposit 100 tokens and the token charges the sender an extra 10%, withdrawal of 100 debits the user’s record by 100 but reduces the contract balance from 200 to 90; the other user still has a claim for 100.
description: A borrower can withdraw collateral through a sender-fee token and consume collateral owed to other borrowers.
fix: The wrapper should reject transfers that reduce its collateral balance by more than the recorded debit.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage
boundary: Redemption output crosses the collateral token transfer boundary.
assumption: The wrapper assumes the recipient receives the `paid` amount checked against `min_paid`.
path: Redeemer → `redeem` → `cdp._redeem` checks nominal output → `_push` transfers through a recipient-fee token → redeemer receives less than `min_paid`.
proof: When `paid = min_paid = 100` and the token deducts a 10% recipient fee, the check passes and the redeemer receives 90; `redeem` returns 100.
description: A recipient-fee token lets a redeemer receive less collateral than the minimum they set.
fix: The wrapper should check the recipient’s balance increase against `min_paid` after the transfer.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The function requires `max_repay >= repay` and clears the whole position when collateral value is below 110% of debt.
unverified: Whether a reachable position can exceed the stablecoin balance available to every liquidator and remain open long enough to cause material loss.
description: A large position can require one liquidator to supply the entire repayment.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: coarse-collateral-zero-seize | group_key: modules/cdp/cdp.vy | _liquidate | coarse-collateral-zero-seize
code_smells: The function calculates `seized = repay * LIQUIDATION_PENALTY // p` without requiring a positive payout.
unverified: Whether a supported collateral price and position size make the resulting liquidation failure economically material.
description: A coarse collateral unit can give a liquidator zero collateral for a positive repayment.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: missing-purchase-slippage | group_key: modules/cdp/cdp.vy | _buy_surplus | missing-purchase-slippage
code_smells: The function calculates `bought` from the current oracle price and accepts no minimum output.
unverified: Whether a price change between transaction submission and execution can cause material loss for a buyer in a supported deployment.
description: A buyer can receive fewer stablecoins than expected after an oracle price change.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert
code_smells: The wrapper calls `_push(msg.sender, seized)` even when `seized` is zero.
unverified: Whether a supported collateral token rejects zero transfers and a materially significant position reaches a zero payout.
description: A token that rejects zero transfers can make a liquidation fail.
