[Feynman: modules/cdp/cdp.vy] The module tracks collateral, debt shares, interest, and bad debt. Its accounting assumes each wrapper transfers the amount recorded.

[Feynman: modules/cdp/cdp_erc20.vy] The module receives and sends collateral tokens. Its accounting assumes an outgoing transfer reduces the contract balance by exactly the requested amount.

[Feynman: modules/cdp/cdp_native.vy] The module receives and sends native coin. Its accounting assumes each payment succeeds or reverts.

[Feynman: modules/tokens/erc20.vy] The module tracks stablecoin balances, supply, allowances, and permits. Its accounting assumes internal mint and burn calls match the CDP debt changes.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does the module measure incoming tokens but accept an outgoing transfer without measuring the contract’s balance change?

[Inversion: _push] An attacker can withdraw their full deposit, use a token that charges the sender an extra fee, or call a path that pays collateral from a reserve.

[Inversion: redeem] A redeemer can set `min_paid` to the quoted amount, use a token that deducts a recipient fee, or redeem after the token changes its fee.

[Inversion: _liquidate] A liquidator can choose a small `max_repay`, target a position below 110%, or target collateral with coarse base units.

[Inversion: _accrue] A caller can invoke `mint(0)`, repeat calls in successive blocks, or act when the total debt is small.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
path: attacker → deposit → withdraw → sender fee consumes collateral credited to another user
invariant: The token balance must cover the sum of credited collateral and reserve.
violation_path: A victim deposits 100 tokens; an attacker deposits 100 tokens and withdraws 100 tokens through a token that charges the sender 10 extra tokens.
proof: Before withdrawal, the contract holds 200 tokens and credits 200 tokens; `_withdraw` removes 100 credits, while `_push` transfers 100 and the token debits 110, leaving 90 tokens against the victim’s 100 credits.
description: An attacker withdraws collateral through a sender-fee token and consumes collateral credited to other users.
fix: The module should reject outgoing transfers that reduce its token balance by more than the accounted amount.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage
path: redeemer → redeem → gross `paid` passes `min_paid` → recipient-fee token delivers less than `min_paid`
invariant: A successful redemption must deliver at least `min_paid` collateral units to the redeemer.
violation_path: The redeemer submits `min_paid = 100`; the accounting returns `paid = 100`; the token deducts a 10-unit recipient fee.
proof: `_redeem` checks `paid >= min_paid` before `redeem` calls `_push(msg.sender, paid)`; the caller receives 90 units although the minimum is 100.
description: A redeemer receives less collateral than `min_paid` when the token deducts a transfer fee.
fix: The module should check the redeemer’s actual balance increase against `min_paid`.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The branch below 110% requires `max_repay >= repay` and clears all debt shares in one call.
unverified: The liquidity available to liquidators and the practical effect on a deployed market remain unverified.
description: A liquidator needs the full repayment amount to close a position below 110%.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: coarse-collateral-zero-seize | group_key: modules/cdp/cdp.vy | _liquidate | coarse-collateral-zero-seize
code_smells: The function calculates `seized = repay * LIQUIDATION_PENALTY // p` and accepts a zero result.
unverified: A material loss to another participant, beyond the liquidator’s voluntary repayment, remains unverified.
description: A liquidator can repay debt and receive zero collateral when the payout rounds down.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: zero-share-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | zero-share-liquidation
code_smells: The function accepts a positive partial repayment while `_repay` can remove zero shares.
unverified: A material loss to another participant remains unverified when the liquidator pays for the call.
description: A liquidator can pay stablecoin while the borrower keeps every debt share.

LEAD | contract: modules/cdp/cdp.vy | function: _accrue | bug_class: caller-driven-compounding | group_key: modules/cdp/cdp.vy | _accrue | caller-driven-compounding
code_smells: `_accrue` updates `rate_index`, and any caller can invoke the exported `mint(0)`.
unverified: The intended compounding frequency and a material difference under deployment parameters remain unverified.
description: A caller can increase the frequency of interest updates for every borrower.

LEAD | contract: modules/cdp/cdp.vy | function: _accrue | bug_class: discarded-interest-fractions | group_key: modules/cdp/cdp.vy | _accrue | discarded-interest-fractions
code_smells: The function floors each fee calculation and advances `last_accrual` without retaining the remainder.
unverified: A material cumulative loss under feasible call frequency and deployment parameters remains unverified.
description: A caller can cause the protocol to discard fractional interest at each update.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: missing-purchase-slippage | group_key: modules/cdp/cdp.vy | _buy_surplus | missing-purchase-slippage
code_smells: The function calculates `bought` from the current oracle price and accepts no minimum output.
unverified: The oracle updates and transaction ordering needed for a material buyer loss remain unverified.
description: A buyer can receive fewer stablecoins after the oracle price changes.

LEAD | contract: modules/cdp/cdp.vy | function: burn | bug_class: no-full-repay-path | group_key: modules/cdp/cdp.vy | burn | no-full-repay-path
code_smells: The caller supplies an exact `amount`, and `_repay` rejects an amount above the accrued debt.
unverified: The practical effect of timestamp movement and available transaction tooling remains unverified.
description: A borrower can retain debt when interest increases after the borrower obtains a repayment quote.

LEAD | contract: modules/cdp/cdp.vy | function: _withdraw | bug_class: oracle-dependent-withdraw-lock | group_key: modules/cdp/cdp.vy | _withdraw | oracle-dependent-withdraw-lock
code_smells: `_withdraw` requires `_collat_ratio`, which reads the oracle whenever the borrower retains debt.
unverified: The duration and likelihood of an oracle outage for a deployed instance remain unverified.
description: An oracle outage blocks a borrower from withdrawing collateral while the borrower retains debt.
