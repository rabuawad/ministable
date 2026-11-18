[Feynman: modules/cdp/cdp.vy] The module records collateral, debt, interest, liquidations, and redemptions; it assumes its wrappers transfer the collateral amounts it records.

[Feynman: modules/cdp/cdp_erc20.vy] The wrapper measures incoming collateral and sends outgoing collateral; it assumes an outgoing transfer removes exactly the requested amount.

[Feynman: modules/cdp/cdp_native.vy] The wrapper accepts and sends native coin; it assumes the recipient accepts the payment.

[Feynman: modules/tokens/erc20.vy] The module records stablecoin balances and allowances; it assumes its caller maintains the relationship between token supply and debt.

[Inversion: _push] An attacker can use a sender-fee token, withdraw after other users deposit, or redeem while the contract holds reserve collateral.

[Inversion: _liquidate] A caller can choose a small `max_repay`, target an underwater position, or call when the collateral payout rounds to zero.

[Inversion: _redeem] A caller can choose `min_paid`, use a token that charges the recipient, or submit a transaction before an oracle update.

[Socratic: modules/cdp/cdp_erc20.vy — _push] Why does the accounting assume the token debits exactly `amount` when the module supports transfer fees?

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
assumption: An outgoing transfer reduces the contract’s collateral balance by exactly `amount`.
violation: A collateral token charges the sender an additional transfer fee.
path: Borrower → `withdraw` → `cdp._withdraw` removes the requested amount from the borrower’s accounting → `_push` removes that amount plus the sender fee → other users lose collateral backing.
proof: If two borrowers each deposit 100 tokens, the contract holds 200 tokens and records 200 tokens of collateral. A token that charges the sender 1% debits 101 tokens for a 100-token withdrawal. The first borrower’s recorded collateral falls by 100, but the contract retains 99 tokens against the second borrower’s recorded 100.
description: A borrower can withdraw collateral through a sender-fee token and consume collateral recorded for other users.
fix: The wrapper should reject any outgoing transfer that reduces its token balance by more than `amount`.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage
assumption: The redeemer receives the amount that `_redeem` calculates before the token transfer.
violation: A collateral token deducts its transfer fee from the recipient’s payment.
path: Redeemer → `redeem` → `_redeem` checks `paid >= min_paid` → `_push` transfers `paid` → the redeemer receives less than `min_paid`.
proof: With `paid = 100`, `min_paid = 100`, and a 1% recipient fee, `_redeem` accepts the payment and `redeem` returns 100, but the redeemer receives 99.
description: A redeemer can receive less collateral than `min_paid` when the collateral token charges a recipient fee.
fix: The wrapper should check the redeemer’s received balance increase against `min_paid` after the transfer.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The underwater branch requires `max_repay >= repay` and removes all debt shares in one call.
unverified: Whether an affected position can exceed the stablecoin liquidity available to a single liquidator or a composed transaction.
description: A large underwater position can require more stablecoin than a liquidator can obtain for one transaction.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert
code_smells: The wrapper calls `_push` even when `_liquidate` calculates `seized = 0`.
unverified: Whether a deployed collateral token rejects zero-value transfers and whether an economically material position can reach that payout.
description: A collateral token that rejects zero transfers can make a liquidation fail when the payout rounds to zero.

LEAD | contract: modules/cdp/cdp.vy | function: burn | bug_class: no-full-repay-path | group_key: modules/cdp/cdp.vy | burn | no-full-repay-path
code_smells: `burn` accrues interest before `_repay`, and `_repay` rejects an amount above the current debt.
unverified: Whether borrowers have an available transaction path that reliably determines and pays the full debt at execution time.
description: A borrower can retain debt when interest increases after the borrower obtains a repayment quote.

LEAD | contract: modules/cdp/cdp.vy | function: mint | bug_class: no-minimum-debt | group_key: modules/cdp/cdp.vy | mint | no-minimum-debt
code_smells: `mint` accepts debt amounts without a minimum position size.
unverified: Whether an attacker can create enough uneconomic positions to cause material protocol losses under the target network’s transaction costs.
description: A borrower can create positions whose liquidation rewards are less than the liquidator’s transaction costs.

LEAD | contract: modules/cdp/cdp.vy | function: _withdraw | bug_class: oracle-dependent-withdraw-lock | group_key: modules/cdp/cdp.vy | _withdraw | oracle-dependent-withdraw-lock
code_smells: `_withdraw` requires `_collat_ratio` to read the oracle whenever the borrower retains debt.
unverified: The duration and operational recovery path for an oracle outage on a deployed instance.
description: An oracle outage can prevent a borrower with debt from withdrawing excess collateral.

LEAD | contract: modules/cdp/cdp.vy | function: _price | bug_class: immutable-oracle-no-fallback | group_key: modules/cdp/cdp.vy | _price | immutable-oracle-no-fallback
code_smells: The constructor fixes `ORACLE`, and price-dependent functions have no replacement path.
unverified: Whether the selected feed has a retirement or failure mode that leaves its address unable to provide usable prices.
description: A retired oracle can block users from actions that require a collateral price.
