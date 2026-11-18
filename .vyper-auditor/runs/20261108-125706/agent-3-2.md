[Feynman: modules/cdp/cdp.vy] The module lets borrowers create and repay debt, and it lets other callers liquidate or redeem positions. It assumes the host binds the intended token module.

[Feynman: modules/cdp/cdp_erc20.vy] The module receives collateral and sends collateral after the shared module updates accounts. It assumes the token debits the amount requested.

[Feynman: modules/cdp/cdp_native.vy] The module receives native coin and sends it after the shared module updates accounts. It assumes the receiver accepts the payment.

[Feynman: modules/tokens/erc20.vy] The module tracks token balances, allowances, and permits. It assumes the host exports only the intended external functions.

[Inversion: _push] An attacker can choose a token with a sender fee, withdraw after another user deposits, or redeem before another user withdraws.

[Socratic: modules/cdp/cdp_erc20.vy — why?] Why does the module measure collateral received on deposit but trust the amount sent on withdrawal?

[Inversion: redeem] A caller can set `min_paid`, choose a collateral token that charges the recipient, or redeem after the token changes its fee.

[Inversion: _liquidate] A caller can choose a small `max_repay`, a position with coarse collateral, or a position whose collateral value falls below its debt.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
path: depositor → withdraw → `_push` → collateral token charges the contract an extra sender fee → other depositors lose collateral
guard_gap: `_pull` measures the contract balance change, but `_push` does not check the contract balance change.
proof: With a token that debits 101 units for `transfer(to, 100)`, two users deposit 100 units each; the first withdrawal removes 101 units while accounting removes 100, leaving 99 units for the second user's 100-unit claim.
description: A depositor can consume another depositor's collateral when the token charges the sender an extra transfer fee.
fix: The module should reject an outgoing transfer when the contract balance falls by more than the accounted amount.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage
path: redeemer → redeem → `_redeem` checks gross `paid` → `_push` transfers less to the redeemer → redeemer receives less than `min_paid`
guard_gap: `_redeem` checks `paid >= min_paid`, but `redeem` does not check the recipient's balance change.
proof: If `_redeem` calculates `paid = 100` and `min_paid = 100`, a token with a 10% recipient fee transfers 90 units to the caller while the transaction succeeds.
description: A redeemer receives less than `min_paid` when the collateral token deducts a transfer fee.
fix: The module should check the recipient's actual balance increase against `min_paid`.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The function requires one caller to repay the full calculated amount when collateral value is below 110% of debt.
unverified: The available liquidity and transaction costs must show that no caller can perform a material liquidation.
description: A large position can remain open when no liquidator can fund the required repayment.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: coarse-collateral-zero-seize | group_key: modules/cdp/cdp.vy | _liquidate | coarse-collateral-zero-seize
code_smells: The function calculates `seized = repay * LIQUIDATION_PENALTY // p`, which can equal zero.
unverified: A supported collateral price and reachable position must show a material liquidation that callers cannot complete profitably.
description: A liquidator can receive zero collateral when the collateral unit has a high value.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: zero-share-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | zero-share-liquidation
code_smells: The function accepts a partial repayment that `_repay` can convert to zero debt shares.
unverified: A reachable index and position must show material harm beyond the caller's own payment.
description: A liquidator can pay tokens without reducing the borrower's debt shares.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert
code_smells: The function calls `_push` even when `seized` equals zero.
unverified: A supported collateral token must reject zero transfers, and a reachable position must require a zero-unit payout.
description: A collateral token that rejects zero transfers can block a liquidation.

LEAD | contract: modules/cdp/cdp.vy | function: _withdraw | bug_class: oracle-dependent-withdraw-lock | group_key: modules/cdp/cdp.vy | _withdraw | oracle-dependent-withdraw-lock
code_smells: The function calls `_collat_ratio` after a withdrawal, and a position with debt requires `_price`.
unverified: The duration and likelihood of an oracle outage must establish the material effect on borrowers.
description: An oracle outage blocks a borrower from withdrawing collateral while the position has debt.
