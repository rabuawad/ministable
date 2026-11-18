[Feynman: modules/cdp/cdp.vy] The module tracks collateral, debt, interest, liquidations, redemptions, and reserves; its share conversions assume rounding remains economically small.

[Feynman: modules/cdp/cdp_erc20.vy] The module receives and sends collateral tokens; its outflow accounting assumes a transfer debits exactly the requested amount.

[Feynman: modules/cdp/cdp_native.vy] The module receives and sends native collateral; its payouts assume the recipient accepts the call.

[Feynman: modules/tokens/erc20.vy] The module tracks stablecoin balances and allowances; its unchecked balance arithmetic assumes total supply bounds every balance.

[Socratic: modules/cdp/cdp.vy:_accrue — why?] Why does each accrual discard the fractional fee while the index retains its increase?

[Socratic: modules/cdp/cdp.vy:_liquidate — why?] Why must one caller supply the entire repayment when collateral covers less than 110% of debt?

[Inversion: _liquidate] A caller selects a small `max_repay`; a price drop places collateral below 110% of debt; a token rejects a zero transfer.

[Inversion: _accrue] A caller invokes `mint(0)` each block; the index grows while no debt exists; repeated accrual rounds each fee down.

[Inversion: _push] A token charges the sender an extra fee; a token charges the recipient a fee; a token pauses transfers after users deposit.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The function requires one caller to repay the whole amount when collateral value is below 110% of debt.
unverified: Whether liquidators can reliably obtain the required stablecoin balance during stressed markets.
description: A liquidator needs the full repayment balance, so an undercollateralized position can remain open when available balances are smaller.

LEAD | contract: modules/cdp/cdp.vy | function: _accrue | bug_class: caller-driven-compounding | group_key: modules/cdp/cdp.vy | _accrue | caller-driven-compounding
code_smells: The function updates `rate_index` on each call, and `mint(0)` can trigger the update.
unverified: Whether the deployment intends simple interest across accrual intervals or accepts caller-controlled compounding.
description: Any caller can increase the effective interest rate when the caller triggers accrual more often.

LEAD | contract: modules/cdp/cdp.vy | function: _accrue | bug_class: discarded-interest-fractions | group_key: modules/cdp/cdp.vy | _accrue | discarded-interest-fractions
code_smells: The function floors each fee and advances `last_accrual` without retaining the fractional remainder.
unverified: Whether repeated calls can create a material stablecoin shortfall after gas costs and the one-wei bound per accrual.
description: A caller can trigger repeated accruals that discard fractional fees while borrower debt follows the increased index.

LEAD | contract: modules/cdp/cdp.vy | function: mint | bug_class: no-minimum-debt | group_key: modules/cdp/cdp.vy | mint | no-minimum-debt
code_smells: The function accepts a positive debt amount without a minimum position size.
unverified: Whether a deployment has transaction costs that exceed the liquidation reward for reachable positions.
description: A borrower can create a position whose liquidation reward may not cover a liquidator’s costs.

LEAD | contract: modules/cdp/cdp.vy | function: burn | bug_class: no-full-repay-path | group_key: modules/cdp/cdp.vy | burn | no-full-repay-path
code_smells: The function accepts an exact amount and rejects an amount above the debt after accrual.
unverified: Whether borrowers can reliably predict the inclusion timestamp or use an external transaction that computes the debt at execution.
description: A borrower may fail to close a position when interest changes the debt before the transaction executes.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
code_smells: The function records the requested outflow without measuring the contract’s balance change or the recipient’s receipt.
unverified: Whether a deployed collateral token charges a sender-side fee or a recipient-side fee on transfers.
description: A collateral token may debit extra tokens or pay a recipient less than the amount recorded by the module.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert
code_smells: The function calls `_push` even when `_liquidate` returns zero seized collateral.
unverified: Whether a deployed collateral token rejects zero transfers and whether a reachable position produces zero seized collateral.
description: A collateral token that rejects zero transfers can make a liquidator’s transaction revert.
