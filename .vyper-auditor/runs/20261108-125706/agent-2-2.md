[Feynman: modules/cdp/cdp.vy] The module records collateral and debt, and public callers can repay, liquidate, redeem, and trade with the reserve. The module binding must give it the intended stablecoin state.

[Feynman: modules/cdp/cdp_erc20.vy] The module takes collateral tokens and sends them after the CDP module changes its records. It assumes a successful token transfer removes the recorded amount.

[Feynman: modules/cdp/cdp_native.vy] The module receives native coin and sends it after the CDP module changes its records. The exported CDP functions must use the same stablecoin state.

[Feynman: modules/tokens/erc20.vy] The module moves token balances and accepts signed approvals. The signature recovery and domain modules must bind each approval to its owner, chain, and contract.

[Feynman: permit] The function checks a signature and gives the named spender an allowance. The imported recovery function must reject invalid signatures.

[Inversion: permit] An attacker submits an invalid signer, reuses a nonce, or changes the spender after signature creation.

[Inversion: transferFrom] An attacker selects another owner, requests more than the allowance, or uses an unlimited allowance after the owner changes it.

[Inversion: _push] A caller uses a token with a sender fee, a recipient fee, or a transfer callback.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does a successful transfer prove that the contract lost exactly `amount` collateral?

[Feynman: _liquidate] The function removes debt and sends collateral when a position falls below the required ratio. The caller must supply the required stablecoin balance.

[Inversion: _liquidate] A caller supplies one unit of repayment, selects a position below 110%, or selects collateral whose smallest unit exceeds the calculated payout.

[Feynman: _accrue] The function updates the debt index and mints interest to the contract. The caller controls when the update occurs.

[Inversion: _accrue] A caller invokes `mint(0)` each block, waits one year between updates, or invokes updates while the calculated fee is below one unit.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
path: borrower → withdraw → collateral record decreases by `amount` → token charges the contract an additional sender fee → other users lose collateral backing
guard_gap: `_pull` measures the contract balance change, but `_push` does not check the contract balance change.
proof: With two deposits of 100 tokens and a token that charges the sender 10% extra, `withdraw(100)` reduces the caller’s record by 100 but reduces the contract balance from 200 to 90; the other user still has a claim for 100. The module explicitly supports tokens that charge transfer fees.
description: A borrower can withdraw collateral with a sender fee and consume collateral that belongs to other users.
fix: The module should reject an outflow when the contract balance decreases by more than the recorded amount.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage
path: redeemer → redeem → CDP checks nominal `paid` against `min_paid` → token deducts a recipient fee → redeemer receives less than `min_paid`
guard_gap: `cdp._redeem` checks the nominal amount, but the wrapper does not check the recipient’s balance change.
proof: If `paid = min_paid = 100` and the token deducts a 10% recipient fee, `cdp._redeem` passes, `_push` transfers 100 nominal units, and the redeemer receives 90 units.
description: A redeemer can receive less collateral than `min_paid` when the token charges a recipient fee.
fix: The wrapper should check the recipient’s actual balance increase against `min_paid`.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The function requires `max_repay >= repay` and removes all shares when collateral value is below 110% of debt.
unverified: A deployed position must become large enough that available liquidators cannot obtain the required stablecoin balance.
description: A large position can remain open when no liquidator can supply its full required repayment.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: coarse-collateral-zero-seize | group_key: modules/cdp/cdp.vy | _liquidate | coarse-collateral-zero-seize
code_smells: The function calculates `seized = repay * LIQUIDATION_PENALTY // p` and accepts a result of zero.
unverified: A deployed collateral price and position must make a zero payout prevent an economically viable liquidation.
description: A liquidator can receive zero collateral when the payout rounds below one collateral unit.

LEAD | contract: modules/cdp/cdp.vy | function: _accrue | bug_class: caller-driven-compounding | group_key: modules/cdp/cdp.vy | _accrue | caller-driven-compounding
code_smells: Any caller can invoke exported `mint(0)` to update `rate_index` and set `last_accrual`.
unverified: The intended fee model must specify whether callers may control the compounding frequency.
description: Any caller can change the compounding frequency and increase borrowers’ debt.

LEAD | contract: modules/cdp/cdp.vy | function: _accrue | bug_class: discarded-interest-fractions | group_key: modules/cdp/cdp.vy | _accrue | discarded-interest-fractions
code_smells: The function floors `total_debt_shares * (index - self.rate_index) // PRECISION` on each update.
unverified: A reachable deployment must show a material accumulated difference between debt growth and minted surplus.
description: Frequent callers can discard fractional interest from the surplus.

LEAD | contract: modules/cdp/cdp.vy | function: burn | bug_class: no-full-repay-path | group_key: modules/cdp/cdp.vy | burn | no-full-repay-path
code_smells: The function accepts an exact `amount`, while `_repay` rejects an amount above the current debt.
unverified: A borrower must show that transaction timing prevents a practical exact full repayment for the deployed fee and chain.
description: A borrower can retain debt when interest increases after the borrower obtains a repayment quote.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: missing-purchase-slippage | group_key: modules/cdp/cdp.vy | _buy_surplus | missing-purchase-slippage
code_smells: The function calculates `bought` from the current oracle price and accepts no minimum output.
unverified: A price update must occur between a buyer’s quote and transaction execution.
description: A buyer can receive less stablecoin than expected after an oracle price update.

LEAD | contract: modules/cdp/cdp.vy | function: _price | bug_class: immutable-oracle-no-fallback | group_key: modules/cdp/cdp.vy | _price | immutable-oracle-no-fallback
code_smells: The module stores `ORACLE` as an immutable value and requires every price read to succeed.
unverified: The selected feed must stop returning acceptable answers without a compatible replacement at the same address.
description: A feed failure can block callers of price-dependent functions.

LEAD | contract: modules/cdp/cdp.vy | function: _withdraw | bug_class: oracle-dependent-withdraw-lock | group_key: modules/cdp/cdp.vy | _withdraw | oracle-dependent-withdraw-lock
code_smells: The function calls `_collat_ratio`, which requires `_price` whenever the borrower has debt.
unverified: The selected oracle must fail or exceed `ORACLE_TIMEOUT` while borrowers have debt and excess collateral.
description: An oracle failure can block borrowers from withdrawing excess collateral.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert
code_smells: The wrapper calls `_push` even when `_liquidate` returns `seized = 0`.
unverified: A supported collateral token must reject zero transfers, and a reachable liquidation must calculate zero seized collateral.
description: A token that rejects zero transfers can make a zero-payout liquidation fail.
