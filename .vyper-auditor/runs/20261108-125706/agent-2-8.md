[Feynman: modules/cdp/cdp.vy] The module tracks collateral, debt, interest, liquidations, and redemptions; its accounting assumes collateral payouts match the amounts it records.

[Feynman: modules/cdp/cdp_erc20.vy] The module measures tokens received but trusts the token to send the recorded amount; the token controls the actual balance changes.

[Feynman: modules/cdp/cdp_native.vy] The module receives and sends native coin around the shared accounting; it assumes each native transfer succeeds.

[Feynman: modules/tokens/erc20.vy] The module tracks stablecoin balances and approvals; its exported functions use the host contract’s token state.

[Inversion: _push] An attacker can withdraw through a sender-fee token, redeem through a recipient-fee token, or liquidate when a token rejects zero transfers.

[Inversion: _liquidate] A caller can choose a small `max_repay`, face an underwater position, or encounter collateral whose base units make the payout round to zero.

[Socratic: modules/cdp/cdp.vy:_accrue — why?] Why does each update discard the fractional fee while the debt index retains its increase?

[Inversion: burn] A borrower can quote the debt before the next block, send the exact quote after interest grows, or send more than the current debt.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow  
pair_or_branch: `_pull` / `_push`  
asymmetry: `_pull` measures the contract’s balance increase, but `_push` does not measure its balance decrease.  
path: depositor → `withdraw` → `_push` → sender fee consumes collateral assigned to other depositors  
proof: Two users each deposit 100 tokens, so the contract holds 200 and records 100 for each. If a token charges the sender 10 extra tokens on a 100-token transfer, the first user withdraws 100 while the contract balance falls to 90. The second user retains a recorded claim of 100 but cannot withdraw it in full. The same `_push` route serves `liquidate`, `redeem`, and `cover_bad_debt`.  
description: A sender-fee token takes other users’ collateral when a caller receives a payout.  
fix: The contract should reject any payout that decreases its token balance by more than the recorded amount.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage  
pair_or_branch: redemption minimum / token payout  
asymmetry: `_redeem` checks `min_paid` against the gross payout, but `redeem` does not check the caller’s actual receipt.  
path: redeemer → `redeem` → gross `min_paid` check → fee-charging token transfer → receipt below the caller’s minimum  
proof: If `_redeem` computes `paid = 100` and the caller sets `min_paid = 100`, the check passes. A token that deducts a 10-token recipient fee transfers only 90 to the caller, while `redeem` returns 100.  
description: A recipient-fee token gives the redeemer less collateral than the minimum they set.  
fix: The contract should compare the redeemer’s token balance increase with `min_paid` after the transfer.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation  
code_smells: The underwater branch requires `max_repay >= repay` and clears all debt shares in one call.  
unverified: Whether an affected position can become large enough that no liquidator can supply the required stablecoin in one transaction.  
description: A large underwater position requires one liquidator to supply the entire repayment.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: coarse-collateral-zero-seize | group_key: modules/cdp/cdp.vy | _liquidate | coarse-collateral-zero-seize  
code_smells: The solvent branch calculates `seized = repay * LIQUIDATION_PENALTY // p` without requiring a positive result.  
unverified: Whether a supported collateral price and position size make zero-payout liquidations economically material.  
description: A liquidator can repay debt and receive zero collateral when the payout rounds down.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert  
code_smells: `liquidate` passes `seized` to `_push` even when `seized` equals zero.  
unverified: Whether a supported collateral token rejects zero transfers and reaches this liquidation state.  
description: A token that rejects zero transfers can block a liquidation with zero collateral payout.

LEAD | contract: modules/cdp/cdp.vy | function: _accrue | bug_class: discarded-interest-fractions | group_key: modules/cdp/cdp.vy | _accrue | discarded-interest-fractions  
code_smells: Each update floors `total_debt_shares * (index - self.rate_index) // PRECISION` and advances `last_accrual`.  
unverified: Whether repeated updates can accumulate a material difference between debt growth and minted surplus under realistic balances and transaction costs.  
description: A caller can trigger updates that discard fractional surplus while the debt index grows.

LEAD | contract: modules/cdp/cdp.vy | function: burn | bug_class: no-full-repay-path | group_key: modules/cdp/cdp.vy | burn | no-full-repay-path  
code_smells: `burn` accepts an exact amount, while `_repay` rejects an amount above current debt and clears all shares only at the current debt.  
unverified: Whether available transaction tooling or a helper contract gives borrowers a reliable way to close debt after interest changes.  
description: A borrower can retain debt when interest increases after they quote a repayment.

LEAD | contract: modules/cdp/cdp.vy | function: _withdraw | bug_class: oracle-dependent-withdraw-lock | group_key: modules/cdp/cdp.vy | _withdraw | oracle-dependent-withdraw-lock  
code_smells: `_withdraw` calls `_collat_ratio`, which reads the oracle whenever the borrower retains debt.  
unverified: The duration and likelihood of an outage or retirement of the configured oracle.  
description: An oracle outage blocks a borrower from withdrawing excess collateral while debt remains.
